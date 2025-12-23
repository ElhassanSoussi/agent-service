"""
Agent executor: runs execution plans step by step.
Stores step results in the database.
"""
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from app.core.planner import Plan, PlanStep, PlanMetadata, summarize_content
from app.core.tools import execute_tool
from app.core.auth import check_tool_quota, increment_tool_call
from app.db.database import SessionLocal
from app.db.models import Job as JobModel, AgentStep as AgentStepModel
from app.schemas.agent import JobStatus, StepStatus
from app.core.metrics import metrics

logger = logging.getLogger(__name__)

# Maximum summary length stored in DB
MAX_SUMMARY_LENGTH = 500


def _create_planner_step(
    db,
    job_id: str,
    metadata: PlanMetadata,
) -> AgentStepModel:
    """Create a planner step record to track planning phase."""
    step_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    
    # Store planning metadata (safe, no secrets)
    input_summary = {
        "type": "planner",
        "mode": metadata.mode,
    }
    
    # Output includes plan info or error
    output_data = {
        "planner_mode": metadata.mode,
        "step_count": metadata.step_count,
    }
    if metadata.fallback_reason:
        output_data["fallback_reason"] = metadata.fallback_reason
    if metadata.error:
        output_data["error"] = metadata.error
    
    # Determine status
    status = StepStatus.DONE.value if metadata.mode in ("rules", "llm") else StepStatus.DONE.value
    if metadata.mode == "llm_fallback":
        # Still mark as done since we fell back successfully
        status = StepStatus.DONE.value
    
    step = AgentStepModel(
        id=step_id,
        job_id=job_id,
        step_number=0,  # Planner is step 0
        tool="planner",
        input_json=json.dumps(input_summary),
        output_summary=json.dumps(output_data),
        status=status,
        created_at=now,
        started_at=now,
        completed_at=now,
        duration_ms=0,
    )
    db.add(step)
    db.commit()
    db.refresh(step)
    
    logger.info(f"planner_step_created job_id={job_id} step_id={step_id} mode={metadata.mode}")
    return step


def _create_step_record(
    db,
    job_id: str,
    step_number: int,
    plan_step: PlanStep,
) -> AgentStepModel:
    """Create a step record in the database."""
    step_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    
    # Store minimal input info (no secrets)
    input_summary = {}
    if plan_step.tool == "http_fetch":
        input_summary = {"url": plan_step.input.get("url", "?")}
    elif plan_step.tool == "web_page_text":
        input_summary = {"url": plan_step.input.get("url", "?")}
    elif plan_step.tool == "web_search":
        input_summary = {"query": plan_step.input.get("query", "?")[:50]}
    elif plan_step.tool == "web_summarize":
        input_summary = {"text_len": len(plan_step.input.get("text", ""))}
    elif plan_step.tool == "echo":
        # Don't store full echo content, just indicate it's an echo
        input_summary = {"action": plan_step.input.get("action", "echo")}
    else:
        input_summary = {"tool": plan_step.tool}
    
    step = AgentStepModel(
        id=step_id,
        job_id=job_id,
        step_number=step_number,
        tool=plan_step.tool,
        input_json=json.dumps(input_summary),
        status=StepStatus.PENDING.value,
        created_at=now,
    )
    db.add(step)
    db.commit()
    db.refresh(step)
    
    logger.info(f"step_created job_id={job_id} step_id={step_id} step_number={step_number}")
    return step


def _update_step_running(db, step: AgentStepModel) -> None:
    """Mark a step as running."""
    now = datetime.now(timezone.utc).isoformat()
    step.status = StepStatus.RUNNING.value
    step.started_at = now
    db.commit()


def _update_step_done(
    db,
    step: AgentStepModel,
    output_summary: str,
) -> None:
    """Mark a step as completed successfully."""
    now = datetime.now(timezone.utc)
    step.status = StepStatus.DONE.value
    step.completed_at = now.isoformat()
    step.output_summary = output_summary
    
    if step.started_at:
        started = datetime.fromisoformat(step.started_at)
        step.duration_ms = int((now - started).total_seconds() * 1000)
    
    db.commit()
    logger.info(f"step_done step_id={step.id} duration_ms={step.duration_ms}")

    metrics.inc("agent_steps_total")

def _update_step_error(
    db,
    step: AgentStepModel,
    error: str,
) -> None:
    """Mark a step as failed."""
    now = datetime.now(timezone.utc)
    step.status = StepStatus.ERROR.value
    step.completed_at = now.isoformat()
    step.error = error[:500]  # Truncate error message
    
    if step.started_at:
        started = datetime.fromisoformat(step.started_at)
        step.duration_ms = int((now - started).total_seconds() * 1000)
    
    db.commit()
    logger.info(f"step_error step_id={step.id} error_type=execution")


def _create_output_summary(tool: str, result: dict[str, Any]) -> str:
    """Create a safe summary of tool output for storage."""
    if tool == "http_fetch":
        status = result.get("status_code", "?")
        body_len = len(result.get("body", ""))
        headers = list(result.get("headers", {}).keys())[:5]
        return json.dumps({
            "status_code": status,
            "body_length": body_len,
            "headers_sample": headers,
        })
    
    elif tool == "echo":
        # Echo returns the input, summarize it
        return json.dumps({"echoed": True, "keys": list(result.get("result", {}).keys()) if isinstance(result.get("result"), dict) else []})
    
    elif tool == "web_search":
        results = result.get("results", [])
        return json.dumps({
            "result_count": len(results),
            "urls": [r.get("url", "") for r in results[:5]],
        })
    
    elif tool == "web_page_text":
        return json.dumps({
            "url": result.get("url", ""),
            "title": result.get("title", "")[:100],
            "text_length": len(result.get("text", "")),
            "truncated": result.get("truncated", False),
        })
    
    elif tool == "web_summarize":
        return json.dumps({
            "bullet_count": len(result.get("bullets", [])),
            "method": result.get("method", "unknown"),
        })
    
    else:
        # Generic summary
        return json.dumps({"completed": True})


async def execute_plan(
    job_id: str,
    plan: Plan,
    prompt: str,
    metadata: Optional[PlanMetadata] = None,
) -> tuple[bool, str, Optional[str]]:
    """
    Execute a plan step by step.
    
    Args:
        job_id: The job ID
        plan: The execution plan
        prompt: Original user prompt
        metadata: Planning metadata (if available)
    
    Returns:
        Tuple of (success, final_output, error_message)
    """
    db = SessionLocal()
    results: list[dict[str, Any]] = []
    citations: list[dict[str, str]] = []  # Track URLs used
    
    try:
        # Store plan in job
        job = db.query(JobModel).filter(JobModel.id == job_id).first()
        if not job:
            return False, "", "Job not found"
        
        # Get tenant_id for quota tracking
        tenant_id = job.tenant_id or "legacy"
        
        job.plan_json = json.dumps([
            {"tool": s.tool, "description": s.description}
            for s in plan.steps
        ])
        db.commit()
        
        # Store planner metadata as step 0
        if metadata:
            _create_planner_step(db, job_id, metadata)
        
        # Execute each step
        for i, plan_step in enumerate(plan.steps):
            step_number = i + 1
            
            # Check tool quota before executing
            allowed, quota_error = check_tool_quota(tenant_id)
            if not allowed:
                logger.warning(f"tool_quota_exceeded job_id={job_id} step={step_number} tenant_id={tenant_id}")
                return False, "", f"Step {step_number} failed: {quota_error}"
            
            # Create step record
            step = _create_step_record(db, job_id, step_number, plan_step)
            
            # Mark as running
            _update_step_running(db, step)
            
            try:
                # Prepare input - may need to reference previous step results
                step_input = _prepare_step_input(plan_step, results)
                
                # Execute the tool
                result = await execute_tool(plan_step.tool, step_input)
                results.append(result)
                
                # Track tool call usage with bytes fetched
                bytes_fetched = _calculate_bytes_fetched(plan_step.tool, result)
                increment_tool_call(tenant_id, plan_step.tool, bytes_fetched)
                
                # Track citations from web tools
                _extract_citations(plan_step.tool, result, citations)
                
                # Create summary and update step
                output_summary = _create_output_summary(plan_step.tool, result)
                _update_step_done(db, step, output_summary)
                
            except Exception as e:
                error_msg = str(e)
                _update_step_error(db, step, error_msg)
                
                # Stop on first error
                logger.error(f"plan_execution_failed job_id={job_id} step={step_number} error_type={type(e).__name__}")
                return False, "", f"Step {step_number} failed: {error_msg}"
        
        # Generate final output with citations
        final_output = _generate_final_output(prompt, plan, results, citations)
        
        # Update job with final output
        job.final_output = final_output
        db.commit()
        
        return True, final_output, None
        
    finally:
        db.close()


def _calculate_bytes_fetched(tool: str, result: dict[str, Any]) -> int:
    """Calculate bytes fetched from a tool result for quota tracking."""
    bytes_count = 0
    
    if tool == "http_fetch":
        body = result.get("body", "")
        bytes_count = len(body.encode("utf-8")) if body else 0
    
    elif tool == "web_page_text":
        text = result.get("text", "")
        bytes_count = len(text.encode("utf-8")) if text else 0
    
    elif tool == "web_search":
        # Count all result text as bytes
        for r in result.get("results", []):
            snippet = r.get("snippet", "")
            bytes_count += len(snippet.encode("utf-8")) if snippet else 0
    
    elif tool == "web_summarize":
        # Summarize doesn't fetch, but we track input text size
        for bullet in result.get("bullets", []):
            bytes_count += len(bullet.encode("utf-8")) if bullet else 0
    
    return bytes_count


def _prepare_step_input(plan_step: PlanStep, results: list[dict[str, Any]]) -> dict[str, Any]:
    """Prepare input for a step, potentially using results from previous steps."""
    step_input = plan_step.input.copy()
    
    # Handle template references like {{search_result_0_url}}
    for key, value in step_input.items():
        if isinstance(value, str) and value.startswith("{{") and value.endswith("}}"):
            template = value[2:-2]
            
            # Handle search result URL references
            if template.startswith("search_result_") and template.endswith("_url"):
                try:
                    idx = int(template.split("_")[2])
                    if results and "results" in results[-1]:
                        search_results = results[-1]["results"]
                        if idx < len(search_results):
                            step_input[key] = search_results[idx].get("url", "")
                except (ValueError, IndexError):
                    pass
            
            # Handle previous text reference
            elif template == "previous_text":
                if results:
                    last = results[-1]
                    if "text" in last:
                        step_input[key] = last["text"]
                    elif "body" in last:
                        step_input[key] = last["body"]
    
    # Legacy handling for source=previous_step
    if step_input.get("source") == "previous_step" and results:
        last_result = results[-1]
        if plan_step.tool == "echo":
            if "body" in last_result:
                step_input["content"] = summarize_content(
                    last_result.get("body", ""),
                    max_length=1000
                )
        elif plan_step.tool == "web_summarize":
            if "text" in last_result:
                step_input["text"] = last_result["text"]
            elif "body" in last_result:
                step_input["text"] = last_result["body"]
    
    return step_input


def _extract_citations(tool: str, result: dict[str, Any], citations: list[dict[str, str]]) -> None:
    """Extract citations from tool results."""
    if tool == "web_search":
        for r in result.get("results", []):
            url = r.get("url", "")
            title = r.get("title", "")
            if url.startswith("https://"):
                citations.append({"url": url, "title": title})
    
    elif tool == "web_page_text":
        url = result.get("url", "")
        title = result.get("title", "")
        if url.startswith("https://"):
            citations.append({"url": url, "title": title})
    
    elif tool == "http_fetch":
        # http_fetch doesn't have title, but track URL
        url = result.get("url", "")
        if url and url.startswith("https://"):
            citations.append({"url": url, "title": ""})


def _generate_final_output(
    prompt: str,
    plan: Plan,
    results: list[dict[str, Any]],
    citations: list[dict[str, str]] = None,
) -> str:
    """Generate final output from executed steps."""
    if not results:
        return json.dumps({"summary": "No results generated.", "citations": []})
    
    # Build output based on what was executed
    output_parts = []
    bullets = []
    
    for i, (step, result) in enumerate(zip(plan.steps, results)):
        if step.tool == "http_fetch":
            status = result.get("status_code", "?")
            body = result.get("body", "")
            excerpt = summarize_content(body, max_length=400)
            output_parts.append(f"Fetched URL (status {status}): {excerpt}")
        
        elif step.tool == "echo":
            if "result" in result:
                output_parts.append(f"Echo result: {json.dumps(result['result'])[:300]}")
            else:
                output_parts.append(f"Step {i+1} completed")
        
        elif step.tool == "web_search":
            search_results = result.get("results", [])
            if search_results:
                output_parts.append(f"Found {len(search_results)} search results")
        
        elif step.tool == "web_page_text":
            title = result.get("title", "")
            text_len = len(result.get("text", ""))
            output_parts.append(f"Extracted text from '{title}' ({text_len} chars)")
        
        elif step.tool == "web_summarize":
            bullets = result.get("bullets", [])
            method = result.get("method", "unknown")
            output_parts.append(f"Generated {len(bullets)} summary bullets ({method})")
    
    # Deduplicate citations
    unique_citations = []
    seen_urls = set()
    for c in (citations or []):
        if c["url"] not in seen_urls:
            seen_urls.add(c["url"])
            unique_citations.append(c)
    
    # Build structured output
    output = {
        "summary": "\n".join(output_parts) if output_parts else "Execution completed.",
        "bullets": bullets,
        "citations": unique_citations[:10],  # Limit to 10 citations
    }
    
    return json.dumps(output)


def get_job_steps(job_id: str) -> list[AgentStepModel]:
    """Get all steps for a job, ordered by step number."""
    db = SessionLocal()
    try:
        steps = db.query(AgentStepModel).filter(
            AgentStepModel.job_id == job_id
        ).order_by(AgentStepModel.step_number).all()
        
        # Detach from session for use outside
        for step in steps:
            db.expunge(step)
        
        return steps
    finally:
        db.close()


def get_job_plan(job_id: str) -> Optional[dict]:
    """Get the planner step (step 0) for a job."""
    db = SessionLocal()
    try:
        step = db.query(AgentStepModel).filter(
            AgentStepModel.job_id == job_id,
            AgentStepModel.step_number == 0,
        ).first()
        
        if not step:
            return None
        
        return {
            "mode": json.loads(step.input_json).get("mode", "rules") if step.input_json else "rules",
            "output": json.loads(step.output_summary) if step.output_summary else {},
            "status": step.status,
        }
    finally:
        db.close()


def get_job_result(job_id: str) -> Optional[str]:
    """Get the final output for a job."""
    db = SessionLocal()
    try:
        job = db.query(JobModel).filter(JobModel.id == job_id).first()
        if not job:
            return None
        return job.final_output
    finally:
        db.close()


def get_job_result_with_citations(job_id: str, include_steps: bool = False) -> Optional[dict]:
    """
    Get the final result for a job with citations.
    
    Args:
        job_id: The job ID
        include_steps: Whether to include step outputs
    
    Returns:
        Dict with final_output, citations, and optionally steps
    """
    db = SessionLocal()
    try:
        job = db.query(JobModel).filter(JobModel.id == job_id).first()
        if not job:
            return None
        
        # Parse final output
        final_output = job.final_output or "{}"
        try:
            output_data = json.loads(final_output)
        except json.JSONDecodeError:
            # Legacy format - plain string
            output_data = {"summary": final_output, "bullets": [], "citations": []}
        
        result = {
            "job_id": job_id,
            "status": job.status,
            "final_output": output_data.get("summary", final_output),
            "bullets": output_data.get("bullets", []),
            "citations": output_data.get("citations", []),
        }
        
        if include_steps:
            steps = db.query(AgentStepModel).filter(
                AgentStepModel.job_id == job_id,
                AgentStepModel.step_number > 0,  # Exclude planner step
            ).order_by(AgentStepModel.step_number).all()
            
            result["steps"] = [
                {
                    "step_number": s.step_number,
                    "tool": s.tool,
                    "status": s.status,
                    "output_summary": s.output_summary,
                    "error": s.error,
                    "duration_ms": s.duration_ms,
                }
                for s in steps
            ]
        
        return result
    finally:
        db.close()
