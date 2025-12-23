"""
Agent API routes for job management.
"""
import json
import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request

from app.core.jobs import job_store, JobStatus
from app.core.tools import execute_tool, ALLOWED_TOOLS
from app.core.planner import create_plan_async, PlanMetadata
from app.core.executor import execute_plan, get_job_steps, get_job_result, get_job_plan, get_job_result_with_citations
from app.core.auth import increment_job_count
from app.schemas.agent import (
    AgentRunRequest,
    AgentRunResponse,
    AgentStatusResponse,
    JobListItem,
    JobListResponse,
    JobDeleteResponse,
    JobCancelResponse,
    ToolName,
    JobMode,
    StepsResponse,
    StepInfo,
    StepStatus,
    AgentResultResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent", tags=["agent"])


def get_tenant_id(request: Request) -> str:
    """Get tenant_id from request state, set by auth middleware."""
    auth_context = getattr(request.state, "auth", None)
    if auth_context:
        return auth_context.tenant_id
    return "legacy"  # Fallback for backwards compatibility


async def run_tool_job_background(job_id: str) -> None:
    """
    Background task to execute a tool-mode job.
    Updates job status and stores result/error.
    Logs only job_id, status, duration (no payloads).
    """
    job = job_store.get(job_id)
    if not job:
        logger.error(f"job_not_found job_id={job_id}")
        return
    
    # Mark as running
    job_store.update_status(job_id, JobStatus.RUNNING)
    
    try:
        # Execute the tool
        result = await execute_tool(job.tool.value, job.input)
        job_store.update_status(job_id, JobStatus.DONE, output=result)
    except Exception as e:
        # Log error type only (not full message which could contain sensitive data)
        logger.error(f"job_failed job_id={job_id} error_type={type(e).__name__}")
        job_store.update_status(job_id, JobStatus.ERROR, error=str(e))


async def run_agent_job_background(job_id: str) -> None:
    """
    Background task to execute an agent-mode job.
    Creates a plan and executes it step by step.
    """
    job = job_store.get(job_id)
    if not job:
        logger.error(f"job_not_found job_id={job_id}")
        return
    
    # Mark as running
    job_store.update_status(job_id, JobStatus.RUNNING)
    
    try:
        # Parse input to get agent config
        config = job.input
        prompt = config.get("prompt", "")
        max_steps = config.get("max_steps", 5)
        # Default to all allowed tools including web tools
        allowed_tools = config.get("allowed_tools", ALLOWED_TOOLS)
        
        # Create execution plan (async, may use LLM)
        plan, metadata = await create_plan_async(prompt, allowed_tools, max_steps)
        
        logger.info(f"plan_created job_id={job_id} steps={len(plan.steps)} mode={metadata.mode}")
        
        # Execute the plan
        success, final_output, error = await execute_plan(job_id, plan, prompt, metadata)
        
        if success:
            job_store.update_status(job_id, JobStatus.DONE, output={"result": final_output})
        else:
            job_store.update_status(job_id, JobStatus.ERROR, error=error)
            
    except Exception as e:
        logger.error(f"agent_job_failed job_id={job_id} error_type={type(e).__name__}")
        job_store.update_status(job_id, JobStatus.ERROR, error=str(e))


@router.post("/run", status_code=202, response_model=AgentRunResponse)
async def run_agent(
    request: AgentRunRequest,
    background_tasks: BackgroundTasks,
    http_request: Request,
) -> AgentRunResponse:
    """
    Submit a job to run a tool or agent.
    
    **Tool Mode** (default, backwards compatible):
    ```json
    {"tool": "echo", "input": {"message": "hello"}}
    ```
    
    **Agent Mode** (new):
    ```json
    {"mode": "agent", "prompt": "Fetch and summarize https://example.com", "max_steps": 3}
    ```
    
    Returns immediately with job_id. Use GET /agent/status/{job_id} to check result.
    """
    # Validate request
    try:
        request.validate_request()
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    
    # Get tenant context
    tenant_id = get_tenant_id(http_request)
    
    mode = request.get_mode()
    
    if mode == JobMode.TOOL:
        # Tool mode - create and run tool job
        job = job_store.create(tool=request.tool, input_data=request.input, tenant_id=tenant_id)
        background_tasks.add_task(run_tool_job_background, job.id)
    else:
        # Agent mode - create and run agent job
        # Use allowed_tools from request, or default to all tools if None
        if request.allowed_tools:
            allowed_tools = [t.value for t in request.allowed_tools]
        else:
            allowed_tools = ALLOWED_TOOLS  # From tools module - includes all web tools
        job = job_store.create_job(
            mode=JobMode.AGENT,
            prompt=request.prompt,
            allowed_tools=allowed_tools,
            max_steps=request.max_steps,
            tenant_id=tenant_id,
        )
        # Track agent job creation
        increment_job_count(tenant_id)
        background_tasks.add_task(run_agent_job_background, job.id)
    
    return AgentRunResponse(
        job_id=job.id,
        status=job.status,
        mode=job.mode,
        created_at=job.created_at,
    )


@router.get("/status/{job_id}", response_model=AgentStatusResponse)
async def get_job_status(job_id: str, http_request: Request) -> AgentStatusResponse:
    """
    Get the status of a job.
    
    Returns job details including output (if done) or error (if failed).
    For agent-mode jobs, includes step_count.
    Returns 404 if job doesn't exist or belongs to a different tenant.
    """
    tenant_id = get_tenant_id(http_request)
    job = job_store.get_for_tenant(job_id, tenant_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Get step count for agent jobs
    step_count = None
    if job.mode == JobMode.AGENT:
        steps = get_job_steps(job_id)
        step_count = len(steps)
    
    return AgentStatusResponse(
        job_id=job.id,
        status=job.status,
        mode=job.mode,
        tool=job.tool,
        prompt=job.prompt,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        duration_ms=job.duration_ms,
        output=job.output if job.status == JobStatus.DONE else None,
        error=job.error if job.status == JobStatus.ERROR else None,
        step_count=step_count,
    )


@router.get("/plan/{job_id}")
async def get_job_plan_endpoint(job_id: str, http_request: Request):
    """
    Get the planning information for an agent-mode job.
    
    Returns details about which planner was used and the generated plan.
    This endpoint is useful for debugging and understanding agent behavior.
    Returns 404 if job doesn't exist or belongs to a different tenant.
    """
    tenant_id = get_tenant_id(http_request)
    job = job_store.get_for_tenant(job_id, tenant_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job.mode != JobMode.AGENT:
        raise HTTPException(status_code=400, detail="Plan only available for agent-mode jobs")
    
    plan_info = get_job_plan(job_id)
    
    # Parse the stored plan JSON
    plan_steps = []
    if job.plan_json:
        try:
            plan_steps = json.loads(job.plan_json)
        except json.JSONDecodeError:
            pass
    
    return {
        "job_id": job_id,
        "planner": plan_info if plan_info else {"mode": "unknown"},
        "plan": {
            "steps": plan_steps,
            "total_steps": len(plan_steps),
        },
    }


@router.get("/steps/{job_id}", response_model=StepsResponse)
async def get_job_steps_endpoint(job_id: str, http_request: Request) -> StepsResponse:
    """
    Get execution steps for an agent-mode job.
    
    Returns detailed information about each step in the execution plan.
    For tool-mode jobs, returns an empty list.
    Returns 404 if job doesn't exist or belongs to a different tenant.
    """
    tenant_id = get_tenant_id(http_request)
    job = job_store.get_for_tenant(job_id, tenant_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    steps = get_job_steps(job_id)
    
    return StepsResponse(
        job_id=job_id,
        mode=job.mode,
        steps=[
            StepInfo(
                step_id=s.id,
                step_number=s.step_number,
                tool=s.tool,
                status=StepStatus(s.status),
                output_summary=s.output_json if hasattr(s, 'output_json') else s.output_summary,
                error=s.error,
                created_at=s.created_at,
                started_at=s.started_at,
                completed_at=s.completed_at,
                duration_ms=s.duration_ms,
            )
            for s in steps
        ],
        total_steps=len(steps),
    )


@router.get("/result/{job_id}", response_model=AgentResultResponse)
async def get_job_result_endpoint(
    job_id: str,
    http_request: Request,
    include_steps: int = Query(default=0, ge=0, le=1, description="Include step outputs (0 or 1)"),
) -> AgentResultResponse:
    """
    Get the final output for a job with citations.
    
    For agent-mode jobs, returns the synthesized final output with citations.
    For tool-mode jobs, returns the tool output as a string.
    Returns 404 if job doesn't exist or belongs to a different tenant.
    
    Query params:
        include_steps: 0 (default) or 1 - include step outputs in response
    """
    tenant_id = get_tenant_id(http_request)
    job = job_store.get_for_tenant(job_id, tenant_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    final_output = None
    citations = []
    bullets = []
    steps = None
    
    if job.mode == JobMode.AGENT:
        # Get result with citations
        result = get_job_result_with_citations(job_id, include_steps=bool(include_steps))
        if result:
            final_output = result.get("final_output")
            citations = result.get("citations", [])
            bullets = result.get("bullets", [])
            if include_steps:
                steps = result.get("steps")
    elif job.output:
        # For tool mode, stringify the output
        final_output = json.dumps(job.output)
    
    response = AgentResultResponse(
        job_id=job_id,
        status=job.status,
        mode=job.mode,
        final_output=final_output,
        error=job.error,
        citations=citations,
        bullets=bullets,
    )
    
    # Add steps if requested (we'll need to handle this in the schema)
    if steps is not None:
        response.steps = steps
    
    return response


@router.get("/jobs", response_model=JobListResponse)
async def list_jobs(
    http_request: Request,
    limit: int = Query(default=20, ge=1, le=100, description="Max items to return"),
    offset: int = Query(default=0, ge=0, description="Offset for pagination"),
    status: Optional[JobStatus] = Query(default=None, description="Filter by status"),
    tool: Optional[ToolName] = Query(default=None, description="Filter by tool"),
) -> JobListResponse:
    """
    List jobs with pagination and optional filters.
    
    Returns lightweight job summaries (no input/output bodies).
    Most recent jobs first. Only shows jobs belonging to the authenticated tenant.
    """
    tenant_id = get_tenant_id(http_request)
    items, total = job_store.list_jobs(
        limit=limit, offset=offset, status=status, tool=tool, tenant_id=tenant_id
    )
    
    def get_tool(item) -> Optional[ToolName]:
        if item.tool:
            try:
                return ToolName(item.tool)
            except ValueError:
                return None
        return None
    
    def get_mode(item) -> JobMode:
        if item.mode:
            try:
                return JobMode(item.mode)
            except ValueError:
                return JobMode.TOOL
        return JobMode.TOOL
    
    return JobListResponse(
        items=[
            JobListItem(
                job_id=item.id,
                status=JobStatus(item.status),
                mode=get_mode(item),
                tool=get_tool(item),
                created_at=item.created_at,
                started_at=item.started_at,
                completed_at=item.completed_at,
                duration_ms=item.duration_ms,
                has_output=item.output is not None,
                has_error=item.error is not None,
            )
            for item in items
        ],
        limit=limit,
        offset=offset,
        total=total,
    )


@router.delete("/jobs/{job_id}", response_model=JobDeleteResponse)
async def delete_job(job_id: str, http_request: Request) -> JobDeleteResponse:
    """
    Delete a job by ID.
    
    Returns 200 if deleted, 404 if not found or belongs to different tenant.
    """
    tenant_id = get_tenant_id(http_request)
    deleted = job_store.delete_for_tenant(job_id, tenant_id)
    
    if deleted is None:
        # Wrong tenant - return 404 (don't reveal job exists)
        raise HTTPException(status_code=404, detail="Job not found")
    if not deleted:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return JobDeleteResponse(deleted=True)


@router.post("/cancel/{job_id}", response_model=JobCancelResponse)
async def cancel_job(job_id: str, http_request: Request) -> JobCancelResponse:
    """
    Cancel a queued or running job.
    
    Sets status to 'error' with error='cancelled'.
    Returns 404 if job doesn't exist or belongs to different tenant.
    
    Note: For running jobs, this is best-effort. The background task
    may complete before the cancellation takes effect.
    """
    tenant_id = get_tenant_id(http_request)
    job, message, is_owner = job_store.cancel_for_tenant(job_id, tenant_id)
    
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # If job was already done/error, return 409 Conflict
    if job.status in (JobStatus.DONE,) or (job.status == JobStatus.ERROR and job.error != "cancelled"):
        raise HTTPException(status_code=409, detail=message)
    
    return JobCancelResponse(
        job_id=job.id,
        status=job.status,
        message=message,
    )
