"""
SQLite-backed job store for agent tasks.
Logs only job_id, status, duration - never inputs/outputs/secrets.
"""
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Optional, List

from app.db.database import SessionLocal
from app.db.models import Job as JobModel, AgentStep as AgentStepModel
from app.schemas.agent import JobStatus, ToolName, JobMode
from app.core.metrics import metrics

# Configure minimal logging (no payloads)
logger = logging.getLogger(__name__)

# Job retention period
JOB_RETENTION_HOURS = 24


@dataclass
class Job:
    """Represents an agent job (in-memory representation)."""
    id: str
    tool: Optional[ToolName]
    input: dict[str, Any]
    status: JobStatus = JobStatus.QUEUED
    output: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    # Agent mode fields
    mode: JobMode = JobMode.TOOL
    prompt: Optional[str] = None
    plan_json: Optional[str] = None
    final_output: Optional[str] = None
    # Multi-tenant field
    tenant_id: Optional[str] = None
    # Artifact fields (for scaffold builder)
    artifact_path: Optional[str] = None
    artifact_name: Optional[str] = None
    artifact_size_bytes: Optional[int] = None
    artifact_sha256: Optional[str] = None
    builder_template: Optional[str] = None
    builder_project_name: Optional[str] = None
    # Repo builder fields (Phase 15)
    repo_url: Optional[str] = None
    repo_ref: Optional[str] = None
    patch_artifact_path: Optional[str] = None
    patch_sha256: Optional[str] = None
    patch_size_bytes: Optional[int] = None


def _model_to_job(model: JobModel) -> Job:
    """Convert SQLAlchemy model to Job dataclass."""
    tool = None
    if model.tool:
        try:
            tool = ToolName(model.tool)
        except ValueError:
            tool = None
    
    mode = JobMode.TOOL
    if model.mode:
        try:
            mode = JobMode(model.mode)
        except ValueError:
            mode = JobMode.TOOL
    
    return Job(
        id=model.id,
        tool=tool,
        input=json.loads(model.input) if model.input else {},
        status=JobStatus(model.status),
        output=json.loads(model.output) if model.output else None,
        error=model.error,
        created_at=datetime.fromisoformat(model.created_at),
        started_at=datetime.fromisoformat(model.started_at) if model.started_at else None,
        completed_at=datetime.fromisoformat(model.completed_at) if model.completed_at else None,
        duration_ms=model.duration_ms,
        mode=mode,
        prompt=model.prompt,
        plan_json=model.plan_json,
        final_output=model.final_output,
        tenant_id=model.tenant_id,
        # Artifact fields
        artifact_path=model.artifact_path,
        artifact_name=model.artifact_name,
        artifact_size_bytes=model.artifact_size_bytes,
        artifact_sha256=model.artifact_sha256,
        builder_template=model.builder_template,
        builder_project_name=model.builder_project_name,
        # Repo builder fields (Phase 15)
        repo_url=model.repo_url,
        repo_ref=model.repo_ref,
        patch_artifact_path=model.patch_artifact_path,
        patch_sha256=model.patch_sha256,
        patch_size_bytes=model.patch_size_bytes,
    )


class JobStore:
    """SQLite-backed job store."""
    
    def _cleanup_old_jobs(self, db) -> int:
        """Delete jobs older than retention period. Returns count deleted."""
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=JOB_RETENTION_HOURS)
            cutoff_str = cutoff.isoformat()
            
            result = db.query(JobModel).filter(JobModel.created_at < cutoff_str).delete()
            db.commit()
            
            if result > 0:
                logger.info(f"cleanup_jobs deleted={result}")
            return result
        except Exception as e:
            # Never crash request on cleanup failure
            logger.warning(f"cleanup_jobs_failed error_type={type(e).__name__}")
            db.rollback()
            return 0
    
    def run_startup_cleanup(self) -> int:
        """Run cleanup at startup. Safe to call multiple times."""
        db = SessionLocal()
        try:
            return self._cleanup_old_jobs(db)
        finally:
            db.close()
    
    def create(self, tool: ToolName, input_data: dict[str, Any], tenant_id: Optional[str] = None) -> Job:
        """Create a new tool-mode job and return it."""
        return self.create_job(
            mode=JobMode.TOOL,
            tool=tool,
            input_data=input_data,
            tenant_id=tenant_id,
        )
    
    def create_job(
        self,
        mode: JobMode,
        tool: Optional[ToolName] = None,
        input_data: Optional[dict[str, Any]] = None,
        prompt: Optional[str] = None,
        allowed_tools: Optional[List[str]] = None,
        max_steps: int = 3,
        tenant_id: Optional[str] = None,
    ) -> Job:
        """Create a new job (tool or agent mode) and return it."""
        job_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        
        db = SessionLocal()
        try:
            # Opportunistic cleanup on job creation
            self._cleanup_old_jobs(db)
            
            # Prepare input based on mode
            if mode == JobMode.TOOL:
                input_json = json.dumps(input_data or {})
                tool_value = tool.value if tool else None
            elif mode == JobMode.BUILDER:
                # Builder mode - store full input_data
                input_json = json.dumps(input_data or {})
                tool_value = None
            else:
                # Agent mode - store config in input
                input_json = json.dumps({
                    "prompt": prompt,
                    "max_steps": max_steps,
                    "allowed_tools": allowed_tools or ["echo", "http_fetch"],
                })
                tool_value = None
            
            # Create new job
            job_model = JobModel(
                id=job_id,
                mode=mode.value,
                tool=tool_value,
                input=input_json,
                status=JobStatus.QUEUED.value,
                created_at=now.isoformat(),
                prompt=prompt if mode in (JobMode.AGENT, JobMode.BUILDER) else None,
                tenant_id=tenant_id,
            )
            db.add(job_model)
            db.commit()
            db.refresh(job_model)
            
            job = _model_to_job(job_model)
            
            # Log only job_id and status (no payload)
            logger.info(f"job_created job_id={job_id} mode={mode.value} status={job.status.value}")
            metrics.inc("job_created_total")
            return job
        finally:
            db.close()
    
    def get(self, job_id: str) -> Optional[Job]:
        """Get a job by ID."""
        db = SessionLocal()
        try:
            job_model = db.query(JobModel).filter(JobModel.id == job_id).first()
            if not job_model:
                return None
            return _model_to_job(job_model)
        finally:
            db.close()
    
    def get_for_tenant(self, job_id: str, tenant_id: str) -> Optional[Job]:
        """
        Get a job by ID, scoped to a tenant.
        Returns None if job doesn't exist OR belongs to a different tenant.
        For legacy tenant, returns job regardless of tenant_id.
        """
        db = SessionLocal()
        try:
            job_model = db.query(JobModel).filter(JobModel.id == job_id).first()
            if not job_model:
                return None
            
            # Legacy tenant can access any job (backwards compatibility)
            if tenant_id == "legacy":
                return _model_to_job(job_model)
            
            # Check tenant ownership
            if job_model.tenant_id != tenant_id:
                return None
            
            return _model_to_job(job_model)
        finally:
            db.close()
    
    def update_status(
        self,
        job_id: str,
        status: JobStatus,
        output: Optional[dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> Optional[Job]:
        """Update job status and optionally set output/error."""
        db = SessionLocal()
        try:
            job_model = db.query(JobModel).filter(JobModel.id == job_id).first()
            if not job_model:
                return None
            
            now = datetime.now(timezone.utc)
            job_model.status = status.value
            
            if status == JobStatus.RUNNING:
                job_model.started_at = now.isoformat()
            elif status in (JobStatus.DONE, JobStatus.ERROR):
                job_model.completed_at = now.isoformat()
                if job_model.started_at:
                    started = datetime.fromisoformat(job_model.started_at)
                    job_model.duration_ms = int((now - started).total_seconds() * 1000)
                if output is not None:
                    job_model.output = json.dumps(output)
                if error is not None:
                    job_model.error = error
            
            db.commit()
            db.refresh(job_model)
            
            job = _model_to_job(job_model)
            
            # Log only job_id, status, duration (no payload)
            logger.info(
                f"job_updated job_id={job_id} status={status.value} "
                f"duration_ms={job.duration_ms}"
            )
            
            # Emit metrics for job completion
            if status == JobStatus.DONE:
                metrics.inc("job_completed_total")
            elif status == JobStatus.ERROR:
                metrics.inc("job_error_total")
            return job
        finally:
            db.close()
    
    def update_artifact(
        self,
        job_id: str,
        artifact_path: str,
        artifact_name: str,
        artifact_size_bytes: int,
        artifact_sha256: str,
        builder_template: str,
        builder_project_name: str,
    ) -> Optional[Job]:
        """Update job with artifact metadata."""
        db = SessionLocal()
        try:
            job_model = db.query(JobModel).filter(JobModel.id == job_id).first()
            if not job_model:
                return None
            
            job_model.artifact_path = artifact_path
            job_model.artifact_name = artifact_name
            job_model.artifact_size_bytes = artifact_size_bytes
            job_model.artifact_sha256 = artifact_sha256
            job_model.builder_template = builder_template
            job_model.builder_project_name = builder_project_name
            
            db.commit()
            db.refresh(job_model)
            
            logger.info(
                f"artifact_stored job_id={job_id} size={artifact_size_bytes}"
            )
            
            return _model_to_job(job_model)
        finally:
            db.close()
    
    def update_repo_builder_result(
        self,
        job_id: str,
        repo_url: str,
        repo_ref: str,
        artifact_path: str,
        artifact_name: str,
        artifact_size_bytes: int,
        artifact_sha256: str,
        patch_artifact_path: str,
        patch_sha256: str,
        patch_size_bytes: int,
        builder_template: str,
    ) -> Optional[Job]:
        """Update job with repo builder result metadata."""
        db = SessionLocal()
        try:
            job_model = db.query(JobModel).filter(JobModel.id == job_id).first()
            if not job_model:
                return None
            
            job_model.repo_url = repo_url
            job_model.repo_ref = repo_ref
            job_model.artifact_path = artifact_path
            job_model.artifact_name = artifact_name
            job_model.artifact_size_bytes = artifact_size_bytes
            job_model.artifact_sha256 = artifact_sha256
            job_model.patch_artifact_path = patch_artifact_path
            job_model.patch_sha256 = patch_sha256
            job_model.patch_size_bytes = patch_size_bytes
            job_model.builder_template = builder_template
            
            db.commit()
            db.refresh(job_model)
            
            logger.info(
                f"repo_builder_result_stored job_id={job_id} "
                f"zip_size={artifact_size_bytes} patch_size={patch_size_bytes}"
            )
            
            return _model_to_job(job_model)
        finally:
            db.close()
    
    def list_jobs(
        self,
        limit: int = 20,
        offset: int = 0,
        status: Optional[JobStatus] = None,
        tool: Optional[ToolName] = None,
        tenant_id: Optional[str] = None,
    ) -> tuple[list[JobModel], int]:
        """
        List jobs with pagination and optional filters.
        Returns (list of JobModel, total count).
        Does NOT load input/output to keep response lightweight.
        If tenant_id is provided (and not 'legacy'), filters to that tenant's jobs.
        """
        db = SessionLocal()
        try:
            query = db.query(JobModel)
            
            # Apply tenant filter (unless legacy)
            if tenant_id and tenant_id != "legacy":
                query = query.filter(JobModel.tenant_id == tenant_id)
            
            # Apply filters
            if status is not None:
                query = query.filter(JobModel.status == status.value)
            if tool is not None:
                query = query.filter(JobModel.tool == tool.value)
            
            # Get total count before pagination
            total = query.count()
            
            # Order by created_at desc (most recent first), apply pagination
            items = query.order_by(JobModel.created_at.desc()).offset(offset).limit(limit).all()
            
            return items, total
        finally:
            db.close()
    
    def delete(self, job_id: str) -> bool:
        """Delete a job by ID. Returns True if deleted, False if not found."""
        db = SessionLocal()
        try:
            result = db.query(JobModel).filter(JobModel.id == job_id).delete()
            db.commit()
            
            if result > 0:
                logger.info(f"job_deleted job_id={job_id}")
                return True
            return False
        finally:
            db.close()
    
    def delete_for_tenant(self, job_id: str, tenant_id: str) -> Optional[bool]:
        """
        Delete a job by ID, scoped to a tenant.
        Returns True if deleted, False if not found, None if wrong tenant.
        """
        db = SessionLocal()
        try:
            job_model = db.query(JobModel).filter(JobModel.id == job_id).first()
            if not job_model:
                return False
            
            # Legacy tenant can delete any job
            if tenant_id != "legacy" and job_model.tenant_id != tenant_id:
                return None  # Wrong tenant
            
            db.delete(job_model)
            db.commit()
            
            logger.info(f"job_deleted job_id={job_id}")
            return True
        finally:
            db.close()
    
    def cancel(self, job_id: str) -> tuple[Optional[Job], str]:
        """
        Cancel a job if it's queued or running.
        Returns (job, message) where job is None if not found,
        or message explains why cancellation failed/succeeded.
        """
        db = SessionLocal()
        try:
            job_model = db.query(JobModel).filter(JobModel.id == job_id).first()
            if not job_model:
                return None, "Job not found"
            
            current_status = JobStatus(job_model.status)
            
            # Can only cancel queued or running jobs
            if current_status in (JobStatus.DONE, JobStatus.ERROR):
                job = _model_to_job(job_model)
                return job, f"Cannot cancel job with status '{current_status.value}'"
            
            # Mark as error with cancelled message
            now = datetime.now(timezone.utc)
            job_model.status = JobStatus.ERROR.value
            job_model.error = "cancelled"
            job_model.completed_at = now.isoformat()
            if job_model.started_at:
                started = datetime.fromisoformat(job_model.started_at)
                job_model.duration_ms = int((now - started).total_seconds() * 1000)
            
            db.commit()
            db.refresh(job_model)
            
            job = _model_to_job(job_model)
            logger.info(f"job_cancelled job_id={job_id}")
            return job, "Job cancelled successfully"
        finally:
            db.close()
    
    def cancel_for_tenant(self, job_id: str, tenant_id: str) -> tuple[Optional[Job], str, bool]:
        """
        Cancel a job if it's queued or running, scoped to a tenant.
        Returns (job, message, is_owner) where:
        - job is None if not found
        - is_owner is False if job belongs to different tenant
        """
        db = SessionLocal()
        try:
            job_model = db.query(JobModel).filter(JobModel.id == job_id).first()
            if not job_model:
                return None, "Job not found", True
            
            # Check tenant ownership (legacy can access all)
            if tenant_id != "legacy" and job_model.tenant_id != tenant_id:
                return None, "Job not found", False
            
            current_status = JobStatus(job_model.status)
            
            # Can only cancel queued or running jobs
            if current_status in (JobStatus.DONE, JobStatus.ERROR):
                job = _model_to_job(job_model)
                return job, f"Cannot cancel job with status '{current_status.value}'", True
            
            # Mark as error with cancelled message
            now = datetime.now(timezone.utc)
            job_model.status = JobStatus.ERROR.value
            job_model.error = "cancelled"
            job_model.completed_at = now.isoformat()
            if job_model.started_at:
                started = datetime.fromisoformat(job_model.started_at)
                job_model.duration_ms = int((now - started).total_seconds() * 1000)
            
            db.commit()
            db.refresh(job_model)
            
            job = _model_to_job(job_model)
            logger.info(f"job_cancelled job_id={job_id}")
            return job, "Job cancelled successfully", True
        finally:
            db.close()


# Global job store instance
job_store = JobStore()
