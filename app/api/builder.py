"""
Codebase Builder Mode API routes.
Provides endpoints for analyzing GitHub repositories and generating code changes.

Modes:
- builder: Analyze repo and generate patches for code changes
- scaffold: Generate complete project skeletons
- fix: Diagnose issues and propose fixes based on error logs
- build_runner: Execute predefined CI-style pipelines (lint/test/build)

Endpoints:
- POST /builder/run - Start a new builder job
- GET /builder/status/{job_id} - Get detailed job status
- GET /builder/result/{job_id} - Get job result with diffs
- GET /builder/files/{job_id} - Get generated files in various formats
- GET /builder/jobs - List builder jobs
- DELETE /builder/jobs/{job_id} - Delete a builder job
- POST /builder/build - Start a build runner job (Phase 16)
- GET /builder/build/{job_id}/logs - Get build runner logs (Phase 16)
- GET /builder/build/{job_id}/status - Get build runner status (Phase 16)
"""
import json
import logging
import re
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator

from app.core.jobs import job_store, JobStatus
from app.schemas.agent import JobMode
from app.core.repo_tools import (
    repo_get_tree,
    repo_get_file,
    repo_search_code,
    repo_get_readme,
    repo_get_info,
)
from app.core.scaffold import (
    generate_scaffold,
    files_to_patches,
    ScaffoldError,
    MAX_FILES,
    MAX_FILE_SIZE,
    MAX_TOTAL_SIZE,
)
from app.core.fixer import analyze_issue, FixerError
from app.schemas.builder import (
    BuilderRunRequest,
    BuilderRunResponse,
    BuilderResultResponse,
    BuilderFilesResponse,
    BuilderStatusResponse,
    BuilderJobListItem,
    BuilderJobListResponse,
    BuilderJobStatus,
    BuilderAnalysisStep,
    BuilderMode,
    FileDiff,
    DiffType,
    ScaffoldFile,
    ReproStep,
    VerificationItem,
)
from app.core.artifact_store import (
    artifact_store,
    ArtifactError,
    validate_project_name as validate_artifact_project_name,
    validate_template,
    VALID_TEMPLATES,
    MAX_FILES as ARTIFACT_MAX_FILES,
    MAX_UNCOMPRESSED_BYTES,
    MAX_ZIP_BYTES,
)
from app.core.scaffold_templates import generate_project, TEMPLATES
from app.core.repo_builder import (
    build_from_repo,
    RepoBuilderError,
    validate_repo_url,
    ALLOWED_DOMAINS,
    MAX_DOWNLOAD_SIZE,
    MAX_EXTRACTED_SIZE,
    MAX_FILES as REPO_MAX_FILES,
)
from app.core.build_runner import (
    run_build,
    validate_repo_url as validate_build_repo_url,
    BuildRunnerError,
    BuildResult,
    PipelineStatus,
    ProjectType,
    workspace_manager,
    ALLOWED_DOMAINS as BUILD_ALLOWED_DOMAINS,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/builder", tags=["builder"])


def get_tenant_id(request: Request) -> str:
    """Get tenant_id from request state, set by auth middleware."""
    auth_context = getattr(request.state, "auth", None)
    if auth_context:
        return auth_context.tenant_id
    return "legacy"


def parse_github_url(url: str) -> tuple[str, str]:
    """
    Parse GitHub URL to extract owner and repo.
    
    Supports:
    - https://github.com/owner/repo
    - https://github.com/owner/repo.git
    - https://github.com/owner/repo/tree/branch
    """
    parsed = urlparse(url)
    
    if parsed.netloc != "github.com":
        raise ValueError("Only GitHub repositories are supported")
    
    # Extract path parts
    path = parsed.path.strip("/")
    parts = path.split("/")
    
    if len(parts) < 2:
        raise ValueError("Invalid GitHub URL: must include owner and repo")
    
    owner = parts[0]
    repo = parts[1]
    
    # Remove .git suffix if present
    if repo.endswith(".git"):
        repo = repo[:-4]
    
    return owner, repo


def generate_unified_diff(
    path: str,
    original: Optional[str],
    modified: Optional[str],
    old_path: Optional[str] = None,
) -> str:
    """
    Generate a unified diff for a file change.
    """
    import difflib
    
    if original is None:
        original = ""
    if modified is None:
        modified = ""
    
    original_lines = original.splitlines(keepends=True)
    modified_lines = modified.splitlines(keepends=True)
    
    # Ensure lines end with newline for diff
    if original_lines and not original_lines[-1].endswith("\n"):
        original_lines[-1] += "\n"
    if modified_lines and not modified_lines[-1].endswith("\n"):
        modified_lines[-1] += "\n"
    
    from_file = old_path if old_path else path
    to_file = path
    
    diff = difflib.unified_diff(
        original_lines,
        modified_lines,
        fromfile=f"a/{from_file}",
        tofile=f"b/{to_file}",
        lineterm="\n",
    )
    
    return "".join(diff)


async def analyze_repository(owner: str, repo: str, ref: str, target_paths: Optional[list], exclude_paths: Optional[list]) -> dict:
    """
    Analyze a repository to understand its structure.
    Returns analysis data including file tree, key files, and language info.
    """
    analysis = {
        "owner": owner,
        "repo": repo,
        "ref": ref,
        "steps": [],
        "files": [],
        "readme": None,
        "info": None,
        "error": None,
    }
    
    # Step 1: Get repository info
    step = {"step_number": 1, "action": "get_info", "target": f"{owner}/{repo}", "status": "pending"}
    analysis["steps"].append(step)
    
    info_result = await repo_get_info(owner, repo)
    if "error" in info_result:
        step["status"] = "error"
        step["result_summary"] = info_result["error"]
        analysis["error"] = info_result["error"]
        return analysis
    
    step["status"] = "done"
    step["result_summary"] = f"Language: {info_result.get('language', 'Unknown')}"
    analysis["info"] = info_result
    
    # Step 2: Get file tree
    step = {"step_number": 2, "action": "get_tree", "target": ref, "status": "pending"}
    analysis["steps"].append(step)
    
    tree_result = await repo_get_tree(owner, repo, ref=ref, recursive=True)
    if "error" in tree_result:
        step["status"] = "error"
        step["result_summary"] = tree_result["error"]
        analysis["error"] = tree_result["error"]
        return analysis
    
    step["status"] = "done"
    step["result_summary"] = f"{tree_result.get('total_entries', 0)} entries"
    
    # Filter tree by target/exclude paths
    tree = tree_result.get("tree", [])
    if target_paths:
        tree = [f for f in tree if any(f["path"].startswith(p.rstrip("/")) for p in target_paths)]
    if exclude_paths:
        tree = [f for f in tree if not any(f["path"].startswith(p.rstrip("/")) for p in exclude_paths)]
    
    analysis["files"] = tree
    
    # Step 3: Get README
    step = {"step_number": 3, "action": "get_readme", "target": "README.md", "status": "pending"}
    analysis["steps"].append(step)
    
    readme_result = await repo_get_readme(owner, repo, ref=ref)
    if "error" not in readme_result:
        step["status"] = "done"
        step["result_summary"] = f"{readme_result.get('size', 0)} bytes"
        analysis["readme"] = readme_result.get("content", "")
    else:
        step["status"] = "done"
        step["result_summary"] = "No README found"
    
    return analysis


async def run_builder_job_background(job_id: str) -> None:
    """
    Background task to execute a builder job.
    
    Handles three modes:
    - builder: Analyze repo and generate patches
    - scaffold: Generate project skeleton
    - fix: Diagnose issues and propose fixes
    """
    job = job_store.get(job_id)
    if not job:
        logger.error(f"builder_job_not_found job_id={job_id}")
        return
    
    # Mark as running
    job_store.update_status(job_id, JobStatus.RUNNING)
    
    try:
        config = job.input
        mode = config.get("mode", "builder")
        
        if mode == "scaffold":
            await _run_scaffold_job(job_id, config)
        elif mode == "fix":
            await _run_fix_job(job_id, config)
        else:
            await _run_builder_job(job_id, config)
            
    except ValueError as e:
        logger.error(f"builder_job_validation_error job_id={job_id} error={str(e)}")
        job_store.update_status(job_id, JobStatus.ERROR, error=str(e))
    except ScaffoldError as e:
        logger.error(f"scaffold_error job_id={job_id} error={str(e)}")
        job_store.update_status(job_id, JobStatus.ERROR, error=str(e))
    except FixerError as e:
        logger.error(f"fixer_error job_id={job_id} error={str(e)}")
        job_store.update_status(job_id, JobStatus.ERROR, error=str(e))
    except Exception as e:
        logger.error(f"builder_job_failed job_id={job_id} error_type={type(e).__name__}")
        job_store.update_status(job_id, JobStatus.ERROR, error=f"Job failed: {type(e).__name__}")


async def _run_builder_job(job_id: str, config: dict) -> None:
    """Execute a builder mode job."""
    repo_url = config.get("repo_url", "")
    ref = config.get("ref", "HEAD")
    prompt = config.get("prompt", "")
    target_paths = config.get("target_paths")
    exclude_paths = config.get("exclude_paths")
    max_files = config.get("max_files", 10)
    
    # Parse GitHub URL
    owner, repo = parse_github_url(repo_url)
    
    logger.info(f"builder_job_start job_id={job_id} repo={owner}/{repo}")
    
    # Phase 1: Analyzing
    analysis = await analyze_repository(owner, repo, ref, target_paths, exclude_paths)
    
    if analysis.get("error"):
        job_store.update_status(
            job_id,
            JobStatus.ERROR,
            error=f"Analysis failed: {analysis['error']}"
        )
        return
    
    # Phase 2: Planning
    relevant_files = []
    files = analysis.get("files", [])
    
    # Simple heuristic: find files that might be relevant based on prompt keywords
    prompt_lower = prompt.lower()
    keywords = re.findall(r'\b\w+\b', prompt_lower)
    
    for f in files:
        if f.get("type") != "file":
            continue
        path = f.get("path", "").lower()
        if any(kw in path for kw in keywords if len(kw) > 3):
            relevant_files.append(f)
    
    # Limit to max_files
    relevant_files = relevant_files[:max_files]
    
    # If no relevant files found, look at common entry points
    if not relevant_files:
        common_files = ["main.py", "app.py", "index.js", "index.ts", "main.go", "main.rs", "lib.rs"]
        for f in files:
            if f.get("type") == "file" and any(f.get("path", "").endswith(cf) for cf in common_files):
                relevant_files.append(f)
                if len(relevant_files) >= max_files:
                    break
    
    # Phase 3: Generating
    diffs = []
    files_analyzed = len(files)
    
    for rf in relevant_files:
        file_path = rf.get("path", "")
        file_result = await repo_get_file(owner, repo, file_path, ref=ref)
        
        if "error" in file_result:
            logger.warning(f"builder_file_fetch_error job_id={job_id} path={file_path}")
            continue
        
        original_content = file_result.get("content", "")
        
        diff = FileDiff(
            path=file_path,
            diff_type=DiffType.MODIFY,
            original_content=original_content,
            new_content=original_content,
            unified_diff=generate_unified_diff(file_path, original_content, original_content),
        )
        diffs.append(diff)
    
    # Build result
    result = {
        "mode": "builder",
        "repo_url": repo_url,
        "owner": owner,
        "repo": repo,
        "ref": analysis.get("info", {}).get("default_branch", ref),
        "prompt": prompt,
        "files_analyzed": files_analyzed,
        "files_modified": len(diffs),
        "diffs": [d.model_dump() for d in diffs],
        "analysis_steps": analysis.get("steps", []),
        "summary": f"Analyzed {files_analyzed} files, identified {len(relevant_files)} files for potential modification based on prompt.",
    }
    
    job_store.update_status(job_id, JobStatus.DONE, output=result)
    logger.info(f"builder_job_done job_id={job_id} files_modified={len(diffs)}")


async def _run_scaffold_job(job_id: str, config: dict) -> None:
    """Execute a scaffold mode job."""
    template = config.get("template", "")
    project = config.get("project", {})
    output = config.get("output", {})
    
    project_name = project.get("name", "my-app")
    description = project.get("description", "")
    features = project.get("features", [])
    
    output_format = output.get("format", "files")
    base_path = output.get("base_path", "")
    
    logger.info(f"scaffold_job_start job_id={job_id} template={template} project={project_name}")
    
    # Generate scaffold
    scaffold_result = generate_scaffold(
        template=template,
        project_name=project_name,
        description=description,
        features=features,
        base_path=base_path,
    )
    
    if scaffold_result.error:
        job_store.update_status(job_id, JobStatus.ERROR, error=scaffold_result.error)
        return
    
    # Build result based on output format
    if output_format == "patches":
        patches = files_to_patches(scaffold_result.files, base_path)
        result = {
            "mode": "scaffold",
            "template": template,
            "project_name": project_name,
            "scaffold_base_path": scaffold_result.base_path,
            "scaffold_total_bytes": scaffold_result.total_bytes,
            "files_modified": scaffold_result.total_files,
            "diffs": patches,
            "summary": f"Generated {scaffold_result.total_files} files ({scaffold_result.total_bytes} bytes) using {template} template.",
        }
    else:
        # files format
        scaffold_files = [
            {"path": f.path, "content": f.content, "size": f.size}
            for f in scaffold_result.files
        ]
        result = {
            "mode": "scaffold",
            "template": template,
            "project_name": project_name,
            "scaffold_base_path": scaffold_result.base_path,
            "scaffold_total_bytes": scaffold_result.total_bytes,
            "scaffold_files": scaffold_files,
            "files_modified": scaffold_result.total_files,
            "summary": f"Generated {scaffold_result.total_files} files ({scaffold_result.total_bytes} bytes) using {template} template.",
        }
    
    job_store.update_status(job_id, JobStatus.DONE, output=result)
    logger.info(f"scaffold_job_done job_id={job_id} files={scaffold_result.total_files}")


async def _run_fix_job(job_id: str, config: dict) -> None:
    """Execute a fix mode job."""
    # Extract repo info from either repo_url or repo dict
    repo_config = config.get("repo", {})
    repo_url = config.get("repo_url", "")
    
    if repo_config:
        owner = repo_config.get("owner", "")
        repo = repo_config.get("name", "")
        ref = repo_config.get("ref", "HEAD")
        path_prefix = repo_config.get("path_prefix", "")
    elif repo_url:
        owner, repo = parse_github_url(repo_url)
        ref = config.get("ref", "HEAD")
        path_prefix = ""
    else:
        job_store.update_status(job_id, JobStatus.ERROR, error="No repository specified")
        return
    
    # Extract task info
    task = config.get("task", {})
    prompt = task.get("prompt", config.get("prompt", ""))
    context = task.get("context", {})
    
    error_log = context.get("error_log")
    stacktrace = context.get("stacktrace")
    failing_test = context.get("failing_test")
    expected_behavior = context.get("expected_behavior")
    
    logger.info(f"fix_job_start job_id={job_id} repo={owner}/{repo}")
    
    # Analyze the issue
    analysis = await analyze_issue(
        owner=owner,
        repo=repo,
        ref=ref,
        prompt=prompt,
        error_log=error_log,
        stacktrace=stacktrace,
        failing_test=failing_test,
        expected_behavior=expected_behavior,
        path_prefix=path_prefix,
    )
    
    if analysis.error:
        job_store.update_status(job_id, JobStatus.ERROR, error=analysis.error)
        return
    
    # Convert patches to diffs
    diffs = [
        {
            "path": p.path,
            "diff_type": p.diff_type,
            "description": p.description,
            "unified_diff": p.unified_diff,
            "original_content": p.original_content,
            "new_content": p.new_content,
            "confidence": p.confidence,
        }
        for p in analysis.patches
    ]
    
    # Convert repro plan
    repro_plan = [
        {
            "step_number": s.step_number,
            "description": s.description,
            "command": s.command,
            "expected_result": s.expected_result,
        }
        for s in analysis.repro_plan
    ]
    
    # Convert verification checklist
    verification_checklist = [
        {
            "description": v.description,
            "command": v.command,
            "is_manual": v.is_manual,
        }
        for v in analysis.verification_checklist
    ]
    
    result = {
        "mode": "fix",
        "repo_url": f"https://github.com/{owner}/{repo}",
        "owner": owner,
        "repo": repo,
        "ref": ref,
        "prompt": prompt,
        "repo_summary": analysis.repo_summary,
        "likely_cause": analysis.likely_cause,
        "files_analyzed": analysis.files_analyzed,
        "files_modified": len(analysis.patches),
        "diffs": diffs,
        "repro_plan": repro_plan,
        "verification_checklist": verification_checklist,
        "risk_notes": analysis.risk_notes,
        "analysis_steps": analysis.analysis_steps,
        "summary": f"Analyzed {analysis.files_analyzed} files. Likely cause: {analysis.likely_cause[:100]}...",
    }
    
    job_store.update_status(job_id, JobStatus.DONE, output=result)
    logger.info(f"fix_job_done job_id={job_id} patches={len(analysis.patches)}")


@router.post("/run", status_code=202, response_model=BuilderRunResponse)
async def run_builder(
    request: BuilderRunRequest,
    background_tasks: BackgroundTasks,
    http_request: Request,
) -> BuilderRunResponse:
    """
    Start a new builder job.
    
    Supports three modes:
    - builder (default): Analyze repo and generate patches for code changes
    - scaffold: Generate complete project skeletons
    - fix: Diagnose issues and propose fixes based on error logs
    
    Returns immediately with job_id. Use GET /builder/result/{job_id} to check result.
    """
    # Get tenant context
    tenant_id = get_tenant_id(http_request)
    
    mode = request.mode.value
    repo_url = None
    template = None
    prompt = request.prompt
    
    # Mode-specific validation and input preparation
    if mode == "builder":
        # Parse and validate GitHub URL
        try:
            owner, repo = parse_github_url(request.repo_url)
            repo_url = request.repo_url
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        
        input_data = {
            "mode": mode,
            "repo_url": request.repo_url,
            "ref": request.ref,
            "prompt": request.prompt,
            "target_paths": request.target_paths,
            "exclude_paths": request.exclude_paths,
            "max_files": request.max_files,
            "model": request.model,
        }
        
    elif mode == "scaffold":
        template = request.template.value if request.template else None
        project = request.project or {}
        output = request.output or {}
        
        input_data = {
            "mode": mode,
            "template": template,
            "project": project,
            "output": output,
        }
        prompt = f"Scaffold {template} project: {project.get('name', '')}"
        
    elif mode == "fix":
        # Get repo info from either repo_url or repo dict
        repo_config = request.repo or {}
        if repo_config:
            owner = repo_config.get("owner", "")
            repo = repo_config.get("name", "")
            repo_url = f"https://github.com/{owner}/{repo}"
        elif request.repo_url:
            try:
                owner, repo = parse_github_url(request.repo_url)
                repo_url = request.repo_url
            except ValueError as e:
                raise HTTPException(status_code=422, detail=str(e))
        
        task = request.task or {}
        prompt = task.get("prompt", request.prompt)
        
        input_data = {
            "mode": mode,
            "repo_url": repo_url,
            "repo": repo_config,
            "ref": request.ref,
            "task": task,
            "prompt": prompt,
        }
    else:
        raise HTTPException(status_code=422, detail=f"Unknown mode: {mode}")
    
    # Create job
    job = job_store.create_job(
        mode=JobMode.BUILDER,
        prompt=prompt,
        input_data=input_data,
        tenant_id=tenant_id,
    )
    
    # Start background task
    background_tasks.add_task(run_builder_job_background, job.id)
    
    logger.info(f"builder_job_created job_id={job.id} mode={mode}")
    
    return BuilderRunResponse(
        job_id=job.id,
        status=BuilderJobStatus.QUEUED,
        mode=BuilderMode(mode),
        repo_url=repo_url,
        template=template,
        created_at=job.created_at,
    )


@router.get("/status/{job_id}", response_model=BuilderStatusResponse)
async def get_builder_status(
    job_id: str,
    http_request: Request,
) -> BuilderStatusResponse:
    """
    Get detailed status of a builder job including analysis steps.
    """
    tenant_id = get_tenant_id(http_request)
    job = job_store.get_for_tenant(job_id, tenant_id)
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Map job status to builder status
    status_map = {
        JobStatus.QUEUED: BuilderJobStatus.QUEUED,
        JobStatus.RUNNING: BuilderJobStatus.ANALYZING,
        JobStatus.DONE: BuilderJobStatus.DONE,
        JobStatus.ERROR: BuilderJobStatus.ERROR,
    }
    
    builder_status = status_map.get(job.status, BuilderJobStatus.QUEUED)
    
    # Determine current phase and progress
    current_phase = "queued"
    progress_pct = 0
    
    if job.status == JobStatus.RUNNING:
        current_phase = "analyzing"
        progress_pct = 30
    elif job.status == JobStatus.DONE:
        current_phase = "done"
        progress_pct = 100
    elif job.status == JobStatus.ERROR:
        current_phase = "error"
        progress_pct = 0
    
    # Get analysis steps from output if available
    analysis_steps = None
    if job.output and isinstance(job.output, dict):
        steps_data = job.output.get("analysis_steps", [])
        analysis_steps = [
            BuilderAnalysisStep(
                step_number=s.get("step_number", 0),
                action=s.get("action", ""),
                target=s.get("target", ""),
                status=s.get("status", "pending"),
                result_summary=s.get("result_summary"),
            )
            for s in steps_data
        ]
    
    return BuilderStatusResponse(
        job_id=job.id,
        status=builder_status,
        repo_url=job.input.get("repo_url", ""),
        ref=job.input.get("ref", "HEAD"),
        prompt=job.input.get("prompt", ""),
        current_phase=current_phase,
        progress_pct=progress_pct,
        analysis_steps=analysis_steps,
        created_at=job.created_at,
        started_at=job.started_at,
        error=job.error,
    )


@router.get("/result/{job_id}", response_model=BuilderResultResponse)
async def get_builder_result(
    job_id: str,
    http_request: Request,
) -> BuilderResultResponse:
    """
    Get the result of a completed builder job including generated diffs.
    
    Response varies by mode:
    - builder: diffs, files_analyzed, files_modified, summary
    - scaffold: scaffold_files or diffs (patches), scaffold_base_path, scaffold_total_bytes
    - fix: diffs, repo_summary, likely_cause, repro_plan, verification_checklist, risk_notes
    """
    tenant_id = get_tenant_id(http_request)
    job = job_store.get_for_tenant(job_id, tenant_id)
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Map status
    status_map = {
        JobStatus.QUEUED: BuilderJobStatus.QUEUED,
        JobStatus.RUNNING: BuilderJobStatus.ANALYZING,
        JobStatus.DONE: BuilderJobStatus.DONE,
        JobStatus.ERROR: BuilderJobStatus.ERROR,
    }
    builder_status = status_map.get(job.status, BuilderJobStatus.QUEUED)
    
    # Get mode from input or output
    mode = job.input.get("mode", "builder")
    if job.output and isinstance(job.output, dict):
        mode = job.output.get("mode", mode)
    
    # Parse common fields from output
    diffs = None
    files_analyzed = 0
    files_modified = 0
    summary = None
    
    # Scaffold mode fields
    scaffold_files = None
    scaffold_base_path = None
    scaffold_template = None
    scaffold_total_bytes = None
    
    # Fix mode fields
    repo_summary = None
    likely_cause = None
    repro_plan = None
    verification_checklist = None
    risk_notes = None
    
    if job.output and isinstance(job.output, dict):
        files_analyzed = job.output.get("files_analyzed", 0)
        files_modified = job.output.get("files_modified", 0)
        summary = job.output.get("summary")
        
        # Parse diffs if present
        diffs_data = job.output.get("diffs", [])
        if diffs_data:
            diffs = [
                FileDiff(
                    path=d.get("path", ""),
                    diff_type=DiffType(d.get("diff_type", "modify")),
                    original_content=d.get("original_content"),
                    new_content=d.get("new_content"),
                    unified_diff=d.get("unified_diff"),
                    old_path=d.get("old_path"),
                    description=d.get("description"),
                    confidence=d.get("confidence"),
                )
                for d in diffs_data
            ]
        
        # Scaffold mode specific fields
        if mode == "scaffold":
            scaffold_template = job.output.get("template")
            scaffold_base_path = job.output.get("scaffold_base_path")
            scaffold_total_bytes = job.output.get("scaffold_total_bytes")
            
            scaffold_files_data = job.output.get("scaffold_files", [])
            if scaffold_files_data:
                scaffold_files = [
                    ScaffoldFile(
                        path=f.get("path", ""),
                        content=f.get("content", ""),
                        size=f.get("size", 0),
                    )
                    for f in scaffold_files_data
                ]
        
        # Fix mode specific fields
        if mode == "fix":
            repo_summary = job.output.get("repo_summary")
            likely_cause = job.output.get("likely_cause")
            risk_notes = job.output.get("risk_notes")
            
            repro_plan_data = job.output.get("repro_plan", [])
            if repro_plan_data:
                repro_plan = [
                    ReproStep(
                        step_number=s.get("step_number", 0),
                        description=s.get("description", ""),
                        command=s.get("command"),
                        expected_result=s.get("expected_result"),
                    )
                    for s in repro_plan_data
                ]
            
            verification_checklist_data = job.output.get("verification_checklist", [])
            if verification_checklist_data:
                verification_checklist = [
                    VerificationItem(
                        description=v.get("description", ""),
                        command=v.get("command"),
                        is_manual=v.get("is_manual", False),
                    )
                    for v in verification_checklist_data
                ]
    
    return BuilderResultResponse(
        job_id=job.id,
        status=builder_status,
        mode=BuilderMode(mode),
        repo_url=job.input.get("repo_url", ""),
        ref=job.input.get("ref", "HEAD"),
        prompt=job.input.get("prompt", ""),
        files_analyzed=files_analyzed,
        files_modified=files_modified,
        diffs=diffs,
        summary=summary,
        # Scaffold mode fields
        scaffold_files=scaffold_files,
        scaffold_base_path=scaffold_base_path,
        scaffold_template=scaffold_template,
        scaffold_total_bytes=scaffold_total_bytes,
        # Fix mode fields
        repo_summary=repo_summary,
        likely_cause=likely_cause,
        repro_plan=repro_plan,
        verification_checklist=verification_checklist,
        risk_notes=risk_notes,
        # Common fields
        error=job.error,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        duration_ms=job.duration_ms,
    )


@router.get("/files/{job_id}", response_model=BuilderFilesResponse)
async def get_builder_files(
    job_id: str,
    http_request: Request,
    format: str = Query(default="unified", description="Output format: 'unified', 'files', or 'zip'"),
) -> BuilderFilesResponse:
    """
    Get generated files from a completed builder job.
    
    Formats:
    - unified: Single unified diff patch
    - files: List of file contents
    - zip: (Not yet implemented) Downloadable ZIP
    """
    tenant_id = get_tenant_id(http_request)
    job = job_store.get_for_tenant(job_id, tenant_id)
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job.status != JobStatus.DONE:
        raise HTTPException(
            status_code=400,
            detail=f"Job not completed. Current status: {job.status.value}"
        )
    
    # Map status
    builder_status = BuilderJobStatus.DONE
    
    # Get diffs from output
    diffs_data = []
    if job.output and isinstance(job.output, dict):
        diffs_data = job.output.get("diffs", [])
    
    # Calculate totals
    total_files = len(diffs_data)
    total_lines_added = 0
    total_lines_removed = 0
    
    for diff in diffs_data:
        unified = diff.get("unified_diff", "")
        for line in unified.split("\n"):
            if line.startswith("+") and not line.startswith("+++"):
                total_lines_added += 1
            elif line.startswith("-") and not line.startswith("---"):
                total_lines_removed += 1
    
    if format == "unified":
        # Combine all diffs into single patch
        unified_patch = ""
        for diff in diffs_data:
            if diff.get("unified_diff"):
                unified_patch += diff["unified_diff"]
                if not unified_patch.endswith("\n"):
                    unified_patch += "\n"
        
        return BuilderFilesResponse(
            job_id=job.id,
            status=builder_status,
            format="unified",
            unified_patch=unified_patch,
            total_files=total_files,
            total_lines_added=total_lines_added,
            total_lines_removed=total_lines_removed,
        )
    
    elif format == "files":
        # Return list of file contents
        files = []
        for diff in diffs_data:
            files.append({
                "path": diff.get("path", ""),
                "diff_type": diff.get("diff_type", "modify"),
                "content": diff.get("new_content", ""),
            })
        
        return BuilderFilesResponse(
            job_id=job.id,
            status=builder_status,
            format="files",
            files=files,
            total_files=total_files,
            total_lines_added=total_lines_added,
            total_lines_removed=total_lines_removed,
        )
    
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported format: {format}")


@router.get("/jobs", response_model=BuilderJobListResponse)
async def list_builder_jobs(
    http_request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    status: Optional[str] = Query(default=None, description="Filter by status"),
) -> BuilderJobListResponse:
    """
    List builder jobs for the current tenant.
    """
    tenant_id = get_tenant_id(http_request)
    
    # Get jobs from store
    # Note: list_jobs returns (list[JobModel], total_count)
    job_models, total = job_store.list_jobs(
        limit=limit * 2,  # Fetch extra to account for filtering by mode
        offset=offset,
        status=JobStatus(status) if status else None,
        tenant_id=tenant_id,
    )
    
    # Filter to builder mode only and convert to response items
    items = []
    for job_model in job_models:
        if job_model.mode != "builder":
            continue
        if len(items) >= limit:
            break
        
        # Parse input JSON
        import json
        input_data = json.loads(job_model.input) if job_model.input else {}
        output_data = json.loads(job_model.output) if job_model.output else {}
        
        files_modified = output_data.get("files_modified", 0) if isinstance(output_data, dict) else 0
        
        prompt_text = input_data.get("prompt", "")
        prompt_preview = prompt_text[:100]
        if len(prompt_text) > 100:
            prompt_preview += "..."
        
        status_map = {
            "queued": BuilderJobStatus.QUEUED,
            "running": BuilderJobStatus.ANALYZING,
            "done": BuilderJobStatus.DONE,
            "error": BuilderJobStatus.ERROR,
        }
        
        items.append(BuilderJobListItem(
            job_id=job_model.id,
            status=status_map.get(job_model.status, BuilderJobStatus.QUEUED),
            repo_url=input_data.get("repo_url", ""),
            prompt_preview=prompt_preview,
            files_modified=files_modified,
            created_at=datetime.fromisoformat(job_model.created_at.replace("Z", "+00:00")),
            completed_at=datetime.fromisoformat(job_model.completed_at.replace("Z", "+00:00")) if job_model.completed_at else None,
            duration_ms=job_model.duration_ms,
        ))
    
    return BuilderJobListResponse(
        items=items,
        limit=limit,
        offset=offset,
        total=len(items),
    )


@router.delete("/jobs/{job_id}")
async def delete_builder_job(
    job_id: str,
    http_request: Request,
) -> dict:
    """
    Delete a builder job.
    """
    tenant_id = get_tenant_id(http_request)
    job = job_store.get_for_tenant(job_id, tenant_id)
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job_store.delete(job_id)
    
    return {"deleted": True, "job_id": job_id}


# =============================================================================
# Scaffold Builder Endpoints (Phase 14)
# =============================================================================

class ScaffoldRequest(BaseModel):
    """Request body for POST /builder/scaffold."""
    template: str = Field(
        description=f"Template name: {', '.join(sorted(VALID_TEMPLATES))}"
    )
    project_name: str = Field(
        description="Project name (alphanumeric, hyphens, underscores)",
        min_length=1,
        max_length=64,
    )
    options: Optional[dict] = Field(
        default=None,
        description="Template options: use_docker (bool), include_ci (bool)"
    )
    
    @field_validator("template")
    @classmethod
    def validate_template_name(cls, v: str) -> str:
        """Validate template name."""
        if v not in VALID_TEMPLATES:
            raise ValueError(
                f"Invalid template: {v}. Valid: {', '.join(sorted(VALID_TEMPLATES))}"
            )
        return v
    
    @field_validator("project_name")
    @classmethod
    def validate_project_name_field(cls, v: str) -> str:
        """Validate and sanitize project name."""
        import re
        v = v.strip()
        if not re.match(r"^[a-zA-Z][a-zA-Z0-9_-]*$", v):
            raise ValueError(
                "Project name must start with a letter and contain only "
                "letters, numbers, hyphens, and underscores"
            )
        return v


class ScaffoldResponse(BaseModel):
    """Response for POST /builder/scaffold."""
    job_id: str
    status: str
    template: str
    project_name: str
    created_at: datetime


class ArtifactInfoResponse(BaseModel):
    """Response for artifact info."""
    job_id: str
    artifact_name: str
    artifact_size_bytes: int
    artifact_sha256: str
    template: str
    project_name: str
    artifact_url: str


async def run_scaffold_artifact_job(job_id: str) -> None:
    """
    Background task to generate scaffold and create ZIP artifact.
    """
    job = job_store.get(job_id)
    if not job:
        logger.error(f"scaffold_job_not_found job_id={job_id}")
        return
    
    # Mark as running
    job_store.update_status(job_id, JobStatus.RUNNING)
    
    try:
        config = job.input
        template = config.get("template", "")
        project_name = config.get("project_name", "")
        options = config.get("options", {}) or {}
        
        use_docker = options.get("use_docker", False)
        include_ci = options.get("include_ci", False)
        
        logger.info(f"scaffold_job_start job_id={job_id} template={template}")
        
        # Generate project files
        files = generate_project(
            template=template,
            project_name=project_name,
            use_docker=use_docker,
            include_ci=include_ci,
        )
        
        # Create ZIP artifact
        artifact_info = artifact_store.create_artifact(
            job_id=job_id,
            files=files,
            project_name=project_name,
            template=template,
        )
        
        # Update job with artifact metadata
        job_store.update_artifact(
            job_id=job_id,
            artifact_path=str(artifact_info.path),
            artifact_name=artifact_info.name,
            artifact_size_bytes=artifact_info.size_bytes,
            artifact_sha256=artifact_info.sha256,
            builder_template=template,
            builder_project_name=project_name,
        )
        
        # Build result output
        result = {
            "template": template,
            "project_name": project_name,
            "files_generated": len(files),
            "artifact_name": artifact_info.name,
            "artifact_size_bytes": artifact_info.size_bytes,
            "artifact_sha256": artifact_info.sha256,
            "artifact_url": f"/builder/artifact/{job_id}",
            "summary": f"Generated {len(files)} files for {template} project '{project_name}' ({artifact_info.size_bytes} bytes ZIP)",
        }
        
        job_store.update_status(job_id, JobStatus.DONE, output=result)
        logger.info(f"scaffold_job_done job_id={job_id} files={len(files)}")
        
    except ArtifactError as e:
        logger.error(f"scaffold_artifact_error job_id={job_id} error={str(e)}")
        job_store.update_status(job_id, JobStatus.ERROR, error=str(e))
    except ValueError as e:
        logger.error(f"scaffold_validation_error job_id={job_id} error={str(e)}")
        job_store.update_status(job_id, JobStatus.ERROR, error=str(e))
    except Exception as e:
        logger.error(f"scaffold_job_failed job_id={job_id} error_type={type(e).__name__}")
        job_store.update_status(job_id, JobStatus.ERROR, error=f"Scaffold failed: {type(e).__name__}")


@router.post("/scaffold", status_code=202, response_model=ScaffoldResponse)
async def create_scaffold(
    request: ScaffoldRequest,
    background_tasks: BackgroundTasks,
    http_request: Request,
) -> ScaffoldResponse:
    """
    Create a new scaffold builder job.
    
    Generates a project skeleton from templates and creates a downloadable ZIP artifact.
    
    Templates:
    - nextjs_web: Next.js + TypeScript + ESLint
    - fastapi_api: FastAPI + pytest skeleton
    - fullstack_nextjs_fastapi: Combined web/ and api/ folders
    
    Options:
    - use_docker: Include Dockerfile and docker-compose.yml
    - include_ci: Include GitHub Actions CI workflow
    
    Returns immediately with job_id. Use GET /builder/artifact/{job_id} to download.
    """
    tenant_id = get_tenant_id(http_request)
    
    # Extract options
    options = request.options or {}
    
    # Create job
    job = job_store.create_job(
        mode=JobMode.BUILDER,
        prompt=f"scaffold {request.template} named {request.project_name}",
        input_data={
            "template": request.template,
            "project_name": request.project_name,
            "options": options,
        },
        tenant_id=tenant_id,
    )
    
    # Start background task
    background_tasks.add_task(run_scaffold_artifact_job, job.id)
    
    logger.info(f"scaffold_job_created job_id={job.id} template={request.template}")
    
    return ScaffoldResponse(
        job_id=job.id,
        status="queued",
        template=request.template,
        project_name=request.project_name,
        created_at=job.created_at,
    )


@router.get("/artifact/{job_id}")
async def download_artifact(
    job_id: str,
    http_request: Request,
) -> Response:
    """
    Download the generated scaffold artifact as a ZIP file.
    
    Returns application/zip with Content-Disposition header for download.
    """
    tenant_id = get_tenant_id(http_request)
    job = job_store.get_for_tenant(job_id, tenant_id)
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job.status != JobStatus.DONE:
        raise HTTPException(
            status_code=400,
            detail=f"Job not completed. Current status: {job.status.value}"
        )
    
    if not job.artifact_name:
        raise HTTPException(
            status_code=404,
            detail="No artifact found for this job"
        )
    
    # Get artifact bytes
    result = artifact_store.get_artifact(job_id)
    if not result:
        raise HTTPException(
            status_code=404,
            detail="Artifact file not found"
        )
    
    zip_bytes, filename = result
    
    # Verify integrity
    if job.artifact_sha256 and not artifact_store.verify_artifact(job_id, job.artifact_sha256):
        raise HTTPException(
            status_code=500,
            detail="Artifact integrity check failed"
        )
    
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(zip_bytes)),
            "X-Artifact-SHA256": job.artifact_sha256 or "",
        }
    )


@router.get("/artifact/{job_id}/info", response_model=ArtifactInfoResponse)
async def get_artifact_info(
    job_id: str,
    http_request: Request,
) -> ArtifactInfoResponse:
    """
    Get artifact metadata without downloading the file.
    """
    tenant_id = get_tenant_id(http_request)
    job = job_store.get_for_tenant(job_id, tenant_id)
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if not job.artifact_name:
        raise HTTPException(
            status_code=404,
            detail="No artifact found for this job"
        )
    
    return ArtifactInfoResponse(
        job_id=job_id,
        artifact_name=job.artifact_name,
        artifact_size_bytes=job.artifact_size_bytes or 0,
        artifact_sha256=job.artifact_sha256 or "",
        template=job.builder_template or "",
        project_name=job.builder_project_name or "",
        artifact_url=f"/builder/artifact/{job_id}",
    )


# =============================================================================
# Phase 15: Repo Builder Endpoints
# =============================================================================

class RepoBuilderRequest(BaseModel):
    """Request body for repo builder endpoint."""
    repo_url: str = Field(..., description="GitHub repository URL", min_length=10, max_length=500)
    ref: str = Field(default="main", description="Git ref (branch, tag, or commit)", max_length=100)
    template: str = Field(default="fastapi_api", description="Template to apply")
    options: Optional[dict] = Field(default=None, description="Template options")
    
    @field_validator("repo_url")
    @classmethod
    def validate_repo_url(cls, v: str) -> str:
        """Validate GitHub URL."""
        try:
            validate_repo_url(v)
        except RepoBuilderError as e:
            raise ValueError(str(e))
        return v
    
    @field_validator("template")
    @classmethod
    def validate_template(cls, v: str) -> str:
        """Validate template name."""
        allowed = {"fastapi_api"}  # Currently only fastapi_api is implemented
        if v not in allowed:
            raise ValueError(f"Invalid template: {v}. Allowed: {', '.join(sorted(allowed))}")
        return v


class RepoBuilderResponse(BaseModel):
    """Response body for repo builder endpoint."""
    job_id: str
    status: str
    message: str
    repo_url: str
    ref: str
    template: str
    status_url: str
    steps_url: str
    result_url: str
    download_url: str
    patch_url: str
    info_url: str


class RepoBuilderInfoResponse(BaseModel):
    """Response body for repo builder info endpoint."""
    job_id: str
    repo_url: str
    ref: str
    template: str
    created_at: str
    status: str
    # Artifact info
    modified_zip_path: Optional[str] = None
    modified_zip_sha256: Optional[str] = None
    modified_zip_size: Optional[int] = None
    patch_path: Optional[str] = None
    patch_sha256: Optional[str] = None
    patch_size: Optional[int] = None
    # Summary
    files_added: Optional[list[str]] = None
    files_modified: Optional[list[str]] = None
    notes: Optional[list[str]] = None


async def run_repo_builder_job(job_id: str) -> None:
    """Background task to run repo builder pipeline."""
    job = job_store.get(job_id)
    if not job:
        logger.error(f"repo_builder_job_not_found job_id={job_id}")
        return
    
    # Update status to running
    job_store.update_status(job_id, JobStatus.RUNNING)
    
    try:
        config = job.input
        repo_url = config.get("repo_url", "")
        ref = config.get("ref", "main")
        template = config.get("template", "fastapi_api")
        options = config.get("options", {}) or {}
        
        logger.info(f"repo_builder_job_start job_id={job_id} repo_url={repo_url} template={template}")
        
        # Run the build pipeline
        result = await build_from_repo(
            job_id=job_id,
            repo_url=repo_url,
            ref=ref,
            template=template,
            options=options,
        )
        
        # Update job with artifact metadata
        job_store.update_repo_builder_result(
            job_id=job_id,
            repo_url=repo_url,
            repo_ref=ref,
            artifact_path=str(result.modified_zip_path) if result.modified_zip_path else "",
            artifact_name=f"{result.repo}-modified.zip",
            artifact_size_bytes=result.modified_zip_size or 0,
            artifact_sha256=result.modified_zip_sha256 or "",
            patch_artifact_path=str(result.patch_path) if result.patch_path else "",
            patch_sha256=result.patch_sha256 or "",
            patch_size_bytes=result.patch_size or 0,
            builder_template=template,
        )
        
        # Build result output
        output = {
            "owner": result.owner,
            "repo": result.repo,
            "ref": result.ref,
            "template": result.template,
            "files_added": result.files_added,
            "files_modified": result.files_modified,
            "files_unchanged_count": len(result.files_unchanged),
            "notes": result.notes,
            "modified_zip_sha256": result.modified_zip_sha256,
            "modified_zip_size": result.modified_zip_size,
            "patch_sha256": result.patch_sha256,
            "patch_size": result.patch_size,
            "download_url": f"/builder/from_repo/{job_id}/download",
            "patch_url": f"/builder/from_repo/{job_id}/patch",
            "summary": f"Applied {template} template: {len(result.files_added)} files added, "
                       f"{len(result.files_modified)} files modified",
        }
        
        job_store.update_status(job_id, JobStatus.DONE, output=output)
        logger.info(
            f"repo_builder_job_done job_id={job_id} "
            f"added={len(result.files_added)} modified={len(result.files_modified)}"
        )
        
    except RepoBuilderError as e:
        logger.error(f"repo_builder_error job_id={job_id} error={str(e)}")
        job_store.update_status(job_id, JobStatus.ERROR, error=str(e))
    except Exception as e:
        logger.error(f"repo_builder_job_failed job_id={job_id} error_type={type(e).__name__}")
        job_store.update_status(job_id, JobStatus.ERROR, error=f"Build failed: {type(e).__name__}")


@router.post("/from_repo", status_code=202, response_model=RepoBuilderResponse)
async def create_repo_builder_job(
    request: RepoBuilderRequest,
    background_tasks: BackgroundTasks,
    http_request: Request,
) -> RepoBuilderResponse:
    """
    Start a new repo builder job.
    
    Downloads a GitHub repository, applies template transforms, and generates:
    - A modified repo ZIP file
    - A unified diff patch for PR creation
    - A summary of changes
    
    Allowed domains: github.com, codeload.github.com
    Size limits: 25MB download, 80MB extracted, 10,000 files max
    """
    tenant_id = get_tenant_id(http_request)
    
    # Create job
    job = job_store.create_job(
        mode=JobMode.BUILDER,
        prompt=f"Build from repo: {request.repo_url}",
        input_data={
            "repo_url": request.repo_url,
            "ref": request.ref,
            "template": request.template,
            "options": request.options or {},
        },
        tenant_id=tenant_id,
    )
    
    # Schedule background task
    background_tasks.add_task(run_repo_builder_job, job.id)
    
    return RepoBuilderResponse(
        job_id=job.id,
        status="queued",
        message="Repo builder job created",
        repo_url=request.repo_url,
        ref=request.ref,
        template=request.template,
        status_url=f"/agent/status/{job.id}",
        steps_url=f"/agent/steps/{job.id}",
        result_url=f"/agent/result/{job.id}",
        download_url=f"/builder/from_repo/{job.id}/download",
        patch_url=f"/builder/from_repo/{job.id}/patch",
        info_url=f"/builder/from_repo/{job.id}/info",
    )


@router.get("/from_repo/{job_id}/download")
async def download_repo_artifact(
    job_id: str,
    http_request: Request,
) -> Response:
    """
    Download the modified repository as a ZIP file.
    """
    tenant_id = get_tenant_id(http_request)
    job = job_store.get_for_tenant(job_id, tenant_id)
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job.status != JobStatus.DONE:
        raise HTTPException(
            status_code=400,
            detail=f"Job not complete. Status: {job.status.value}"
        )
    
    if not job.artifact_path:
        raise HTTPException(
            status_code=404,
            detail="No artifact found for this job"
        )
    
    # Read the artifact file
    artifact_path = Path(job.artifact_path)
    if not artifact_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Artifact file not found"
        )
    
    zip_bytes = artifact_path.read_bytes()
    filename = job.artifact_name or f"{job_id}_modified_repo.zip"
    
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(zip_bytes)),
            "X-Artifact-SHA256": job.artifact_sha256 or "",
        }
    )


@router.get("/from_repo/{job_id}/patch")
async def get_repo_patch(
    job_id: str,
    http_request: Request,
) -> Response:
    """
    Get the unified diff patch for the modified repository.
    
    This patch can be used to create a pull request:
    ```
    curl -o changes.diff https://domain/builder/from_repo/{job_id}/patch
    git apply changes.diff
    ```
    """
    tenant_id = get_tenant_id(http_request)
    job = job_store.get_for_tenant(job_id, tenant_id)
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job.status != JobStatus.DONE:
        raise HTTPException(
            status_code=400,
            detail=f"Job not complete. Status: {job.status.value}"
        )
    
    if not job.patch_artifact_path:
        raise HTTPException(
            status_code=404,
            detail="No patch found for this job"
        )
    
    # Read the patch file
    patch_path = Path(job.patch_artifact_path)
    if not patch_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Patch file not found"
        )
    
    patch_content = patch_path.read_text()
    
    return Response(
        content=patch_content,
        media_type="text/plain",
        headers={
            "Content-Disposition": f'attachment; filename="{job_id}_changes.diff"',
            "Content-Length": str(len(patch_content)),
            "X-Patch-SHA256": job.patch_sha256 or "",
        }
    )


@router.get("/from_repo/{job_id}/info", response_model=RepoBuilderInfoResponse)
async def get_repo_builder_info(
    job_id: str,
    http_request: Request,
) -> RepoBuilderInfoResponse:
    """
    Get metadata about a repo builder job.
    """
    tenant_id = get_tenant_id(http_request)
    job = job_store.get_for_tenant(job_id, tenant_id)
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Parse output for additional info
    files_added = None
    files_modified = None
    notes = None
    
    if job.output:
        files_added = job.output.get("files_added")
        files_modified = job.output.get("files_modified")
        notes = job.output.get("notes")
    
    return RepoBuilderInfoResponse(
        job_id=job_id,
        repo_url=job.repo_url or "",
        ref=job.repo_ref or "",
        template=job.builder_template or "",
        created_at=job.created_at.isoformat(),
        status=job.status.value,
        modified_zip_path=job.artifact_path,
        modified_zip_sha256=job.artifact_sha256,
        modified_zip_size=job.artifact_size_bytes,
        patch_path=job.patch_artifact_path,
        patch_sha256=job.patch_sha256,
        patch_size=job.patch_size_bytes,
        files_added=files_added,
        files_modified=files_modified,
        notes=notes,
    )


# =============================================================================
# Build Runner Endpoints (Phase 16)
# =============================================================================

class BuildRunnerRequest(BaseModel):
    """Request body for POST /builder/build."""
    repo_url: str = Field(
        description="Repository URL (GitHub or GitLab only)",
        examples=["https://github.com/owner/repo"],
    )
    ref: str = Field(
        default="main",
        description="Git ref (branch, tag, or commit)",
    )
    pipeline: str = Field(
        default="auto",
        description="Pipeline type: 'auto', 'python', or 'node'",
    )
    
    @field_validator("repo_url")
    @classmethod
    def validate_repo_url_field(cls, v: str) -> str:
        """Validate repository URL against allowlist."""
        try:
            validate_build_repo_url(v)
        except BuildRunnerError as e:
            raise ValueError(str(e))
        return v
    
    @field_validator("pipeline")
    @classmethod
    def validate_pipeline(cls, v: str) -> str:
        """Validate pipeline type."""
        allowed = {"auto", "python", "node"}
        if v not in allowed:
            raise ValueError(f"Invalid pipeline: {v}. Allowed: {', '.join(sorted(allowed))}")
        return v


class BuildRunnerResponse(BaseModel):
    """Response for POST /builder/build."""
    job_id: str
    status: str
    message: str
    repo_url: str
    ref: str
    pipeline: str
    status_url: str
    logs_url: str


class BuildRunnerStatusResponse(BaseModel):
    """Response for GET /builder/build/{job_id}/status."""
    job_id: str
    status: str
    repo_url: Optional[str] = None
    ref: Optional[str] = None
    project_type: Optional[str] = None
    pipeline_steps: list[dict] = Field(default_factory=list)
    overall_status: Optional[str] = None
    build_log_url: Optional[str] = None
    error: Optional[str] = None
    notes: list[str] = Field(default_factory=list)
    total_duration_ms: Optional[int] = None
    created_at: Optional[str] = None
    completed_at: Optional[str] = None


class BuildRunnerLogsResponse(BaseModel):
    """Response for GET /builder/build/{job_id}/logs."""
    job_id: str
    log_content: str
    log_size: int
    log_sha256: Optional[str] = None


async def run_build_runner_job(job_id: str) -> None:
    """
    Background task to execute a build runner job.
    
    Executes predefined CI-style pipelines (setup, install, test, build)
    in an isolated workspace. NO shell=True, NO arbitrary commands.
    """
    job = job_store.get(job_id)
    if not job:
        logger.error(f"build_runner_job_not_found job_id={job_id}")
        return
    
    # Mark as running
    job_store.update_status(job_id, JobStatus.RUNNING)
    
    try:
        config = job.input
        repo_url = config.get("repo_url", "")
        ref = config.get("ref", "main")
        pipeline = config.get("pipeline", "auto")
        
        logger.info(f"build_runner_start job_id={job_id} repo={repo_url} ref={ref}")
        
        # Execute build pipeline
        result: BuildResult = await run_build(
            job_id=job_id,
            repo_url=repo_url,
            ref=ref,
            pipeline=pipeline,
        )
        
        # Build output
        steps_data = []
        for step in result.pipeline_steps:
            step_data = {
                "name": step.name,
                "description": step.description,
                "status": step.status.value,
                "duration_ms": step.duration_ms,
                "error": step.error,
                "command_count": len(step.command_results),
            }
            # Add command summaries (no secrets, just exit codes)
            step_data["commands"] = [
                {
                    "command": " ".join(cmd.command[:3]) + ("..." if len(cmd.command) > 3 else ""),
                    "exit_code": cmd.exit_code,
                    "timed_out": cmd.timed_out,
                    "duration_ms": cmd.duration_ms,
                }
                for cmd in step.command_results
            ]
            steps_data.append(step_data)
        
        output = {
            "mode": "build_runner",
            "repo_url": result.repo_url,
            "ref": result.ref,
            "project_type": result.project_type.value,
            "pipeline_steps": steps_data,
            "overall_status": result.overall_status.value,
            "build_log_path": str(result.build_log_path) if result.build_log_path else None,
            "build_log_sha256": result.build_log_sha256,
            "build_log_size": result.build_log_size,
            "notes": result.notes,
            "total_duration_ms": result.total_duration_ms,
            "error": result.error,
        }
        
        # Update job with build results
        if result.overall_status == PipelineStatus.SUCCESS:
            job_store.update_status(job_id, JobStatus.DONE, output=output)
            logger.info(f"build_runner_success job_id={job_id}")
        else:
            job_store.update_status(
                job_id,
                JobStatus.ERROR,
                error=result.error or "Build failed",
                output=output,
            )
            logger.info(f"build_runner_failed job_id={job_id} error={result.error}")
            
    except BuildRunnerError as e:
        logger.error(f"build_runner_error job_id={job_id} error={str(e)}")
        job_store.update_status(job_id, JobStatus.ERROR, error=str(e))
    except Exception as e:
        logger.error(f"build_runner_unexpected_error job_id={job_id} error_type={type(e).__name__}")
        job_store.update_status(job_id, JobStatus.ERROR, error=f"Build failed: {type(e).__name__}")


@router.post("/build", status_code=202, response_model=BuildRunnerResponse)
async def create_build_runner_job(
    request: BuildRunnerRequest,
    background_tasks: BackgroundTasks,
    http_request: Request,
) -> BuildRunnerResponse:
    """
    Start a safe build runner job for a repository.
    
    Executes predefined CI-style pipelines in an isolated workspace:
    
    **Python projects** (detected by pyproject.toml or requirements.txt):
    - Create virtual environment
    - Install dependencies (pip install -r requirements.txt / pip install -e .)
    - Run tests (pytest)
    
    **Node.js projects** (detected by package.json):
    - Install dependencies (npm ci / npm install)
    - Run lint (if npm run lint exists)
    - Run tests (if npm test exists)
    - Run build (if npm run build exists)
    
    **Security:**
    - Only GitHub and GitLab repositories allowed
    - No shell=True, no arbitrary command execution
    - Isolated workspace per job with 24h auto-cleanup
    - Command timeouts (5min per command, 15min total)
    - No secrets stored in logs
    """
    tenant_id = get_tenant_id(http_request)
    
    # Create job using create_job (not create) for builder mode
    job = job_store.create_job(
        mode=JobMode.BUILDER,
        input_data={
            "mode": "build_runner",
            "repo_url": request.repo_url,
            "ref": request.ref,
            "pipeline": request.pipeline,
        },
        prompt=f"Build runner for {request.repo_url}",
        tenant_id=tenant_id,
    )
    
    logger.info(f"build_runner_job_created job_id={job.id} repo={request.repo_url}")
    
    # Schedule background task
    background_tasks.add_task(run_build_runner_job, job.id)
    
    return BuildRunnerResponse(
        job_id=job.id,
        status="queued",
        message="Build runner job created",
        repo_url=request.repo_url,
        ref=request.ref,
        pipeline=request.pipeline,
        status_url=f"/builder/build/{job.id}/status",
        logs_url=f"/builder/build/{job.id}/logs",
    )


@router.get("/build/{job_id}/status", response_model=BuildRunnerStatusResponse)
async def get_build_runner_status(
    job_id: str,
    http_request: Request,
) -> BuildRunnerStatusResponse:
    """
    Get the status of a build runner job.
    
    Returns pipeline steps with their status, duration, and any errors.
    """
    tenant_id = get_tenant_id(http_request)
    job = job_store.get_for_tenant(job_id, tenant_id)
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Extract build runner data from output
    output = job.output or {}
    
    # Check if this is actually a build runner job
    if output.get("mode") != "build_runner" and job.input.get("mode") != "build_runner":
        raise HTTPException(status_code=400, detail="Not a build runner job")
    
    pipeline_steps = output.get("pipeline_steps", [])
    
    return BuildRunnerStatusResponse(
        job_id=job_id,
        status=job.status.value,
        repo_url=output.get("repo_url") or job.input.get("repo_url"),
        ref=output.get("ref") or job.input.get("ref"),
        project_type=output.get("project_type"),
        pipeline_steps=pipeline_steps,
        overall_status=output.get("overall_status"),
        build_log_url=f"/builder/build/{job_id}/logs" if output.get("build_log_path") else None,
        error=job.error or output.get("error"),
        notes=output.get("notes", []),
        total_duration_ms=output.get("total_duration_ms"),
        created_at=job.created_at.isoformat() if job.created_at else None,
        completed_at=job.completed_at.isoformat() if job.completed_at else None,
    )


@router.get("/build/{job_id}/logs", response_model=BuildRunnerLogsResponse)
async def get_build_runner_logs(
    job_id: str,
    http_request: Request,
) -> BuildRunnerLogsResponse:
    """
    Get the build logs for a build runner job.
    
    Returns the full build log including stdout/stderr from all pipeline commands.
    """
    tenant_id = get_tenant_id(http_request)
    job = job_store.get_for_tenant(job_id, tenant_id)
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    output = job.output or {}
    
    # Check if this is actually a build runner job
    if output.get("mode") != "build_runner" and job.input.get("mode") != "build_runner":
        raise HTTPException(status_code=400, detail="Not a build runner job")
    
    log_path_str = output.get("build_log_path")
    if not log_path_str:
        raise HTTPException(status_code=404, detail="No build log available yet")
    
    log_path = Path(log_path_str)
    if not log_path.exists():
        raise HTTPException(status_code=404, detail="Build log file not found")
    
    log_content = log_path.read_text(errors="replace")
    
    return BuildRunnerLogsResponse(
        job_id=job_id,
        log_content=log_content,
        log_size=output.get("build_log_size", len(log_content)),
        log_sha256=output.get("build_log_sha256"),
    )


@router.get("/build/{job_id}/logs/download")
async def download_build_runner_logs(
    job_id: str,
    http_request: Request,
) -> Response:
    """
    Download build logs as a text file.
    """
    tenant_id = get_tenant_id(http_request)
    job = job_store.get_for_tenant(job_id, tenant_id)
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    output = job.output or {}
    
    log_path_str = output.get("build_log_path")
    if not log_path_str:
        raise HTTPException(status_code=404, detail="No build log available")
    
    log_path = Path(log_path_str)
    if not log_path.exists():
        raise HTTPException(status_code=404, detail="Build log file not found")
    
    log_content = log_path.read_bytes()
    
    return Response(
        content=log_content,
        media_type="text/plain",
        headers={
            "Content-Disposition": f'attachment; filename="{job_id}_build.log"',
            "Content-Length": str(len(log_content)),
            "X-Log-SHA256": output.get("build_log_sha256", ""),
        }
    )
