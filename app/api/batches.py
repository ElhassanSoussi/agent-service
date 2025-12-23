"""
Phase A1: Approval Gate API

Provides endpoints for managing action batches with approval workflow:
- POST /v1/batches - Create a new batch with actions
- POST /v1/batches/{id}/submit - Submit for approval (draft -> pending)
- POST /v1/batches/{id}/approve - Approve batch (pending -> approved)
- POST /v1/batches/{id}/reject - Reject batch (pending -> rejected)
- POST /v1/batches/{id}/run - Execute approved batch (approved -> executing -> executed/failed)
- GET /v1/batches - List batches with filters
- GET /v1/batches/{id} - Get batch details with actions and audit trail

ENFORCEMENT: Execution only happens when:
1. Batch exists
2. Batch status is "approved" (at run request) or "executing" (during execution)
3. Action belongs to the batch
"""
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional, List, Literal
from enum import Enum

from fastapi import APIRouter, HTTPException, Request, Query, BackgroundTasks
from pydantic import BaseModel, Field

from app.db.database import SessionLocal
from app.db.models import ActionBatch, BatchAction, AuditLog

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["batches"])


# =============================================================================
# Enums and Schemas
# =============================================================================

class BatchStatus(str, Enum):
    DRAFT = "draft"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTING = "executing"
    EXECUTED = "executed"
    FAILED = "failed"


class ActionKind(str, Enum):
    SHELL = "shell"
    FILE_WRITE = "file_write"
    FILE_PATCH = "file_patch"
    HTTP_REQUEST = "http_request"
    GIT = "git"
    NOTE = "note"


class ActionRisk(str, Enum):
    SAFE = "safe"
    MEDIUM = "medium"
    RISKY = "risky"


class ActionPayload(BaseModel):
    """Payload for an action - structure depends on kind."""
    # Shell action
    command: Optional[str] = None
    cwd: Optional[str] = None
    
    # File write action
    path: Optional[str] = None
    content: Optional[str] = None
    
    # File patch action
    original: Optional[str] = None
    modified: Optional[str] = None
    
    # HTTP request action
    method: Optional[str] = None
    url: Optional[str] = None
    headers: Optional[dict] = None
    body: Optional[str] = None
    
    # Git action
    git_command: Optional[str] = None
    repo_path: Optional[str] = None
    
    # Note action (informational)
    note: Optional[str] = None


class ActionCreate(BaseModel):
    """Schema for creating an action within a batch."""
    kind: ActionKind
    risk: ActionRisk = ActionRisk.SAFE
    payload: dict = Field(default_factory=dict)
    preview_text: str = Field(..., min_length=1, max_length=500)


class BatchCreate(BaseModel):
    """Schema for creating a new batch."""
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=2000)
    actions: List[ActionCreate] = Field(..., min_length=1, max_length=50)
    created_by: Literal["xone", "admin"] = "xone"
    auto_submit: bool = False  # If True, immediately submit for approval


class BatchReject(BaseModel):
    """Schema for rejecting a batch."""
    reason: Optional[str] = Field(None, max_length=500)


class ActionResponse(BaseModel):
    """Response schema for an action."""
    id: str
    seq: int
    kind: str
    risk: str
    payload: dict
    preview_text: str
    status: str
    output_summary: Optional[str]
    error: Optional[str]
    created_at: str
    started_at: Optional[str]
    completed_at: Optional[str]


class AuditLogResponse(BaseModel):
    """Response schema for an audit log entry."""
    id: str
    ts: str
    actor: str
    event_type: str
    message: str
    data: Optional[dict]


class BatchResponse(BaseModel):
    """Response schema for a batch."""
    id: str
    title: str
    description: Optional[str]
    created_by: str
    status: str
    created_at: str
    updated_at: str
    approved_at: Optional[str]
    approved_by: Optional[str]
    executed_at: Optional[str]
    execution_summary: Optional[str]
    actions: List[ActionResponse] = []
    audit_logs: List[AuditLogResponse] = []
    action_count: int = 0
    risk_summary: dict = {}


class BatchListResponse(BaseModel):
    """Response schema for batch list."""
    batches: List[BatchResponse]
    total: int
    page: int
    page_size: int


# =============================================================================
# Helper Functions
# =============================================================================

def get_tenant_id(request: Request) -> Optional[str]:
    """Get tenant_id from request state."""
    return getattr(request.state, "tenant_id", None)


def create_audit_log(
    db,
    actor: str,
    event_type: str,
    message: str,
    batch_id: Optional[str] = None,
    action_id: Optional[str] = None,
    data: Optional[dict] = None,
) -> AuditLog:
    """Create an audit log entry."""
    log = AuditLog(
        id=str(uuid.uuid4()),
        ts=datetime.now(timezone.utc).isoformat(),
        actor=actor,
        event_type=event_type,
        batch_id=batch_id,
        action_id=action_id,
        message=message,
        data_json=json.dumps(data) if data else None,
    )
    db.add(log)
    return log


def batch_to_response(batch: ActionBatch, include_details: bool = True) -> dict:
    """Convert batch model to response dict."""
    actions = []
    risk_summary = {"safe": 0, "medium": 0, "risky": 0}
    
    if include_details:
        for action in batch.actions:
            actions.append({
                "id": action.id,
                "seq": action.seq,
                "kind": action.kind,
                "risk": action.risk,
                "payload": json.loads(action.payload_json) if action.payload_json else {},
                "preview_text": action.preview_text,
                "status": action.status,
                "output_summary": action.output_summary,
                "error": action.error,
                "created_at": action.created_at,
                "started_at": action.started_at,
                "completed_at": action.completed_at,
            })
            if action.risk in risk_summary:
                risk_summary[action.risk] += 1
    else:
        for action in batch.actions:
            if action.risk in risk_summary:
                risk_summary[action.risk] += 1
    
    audit_logs = []
    if include_details:
        for log in batch.audit_logs:
            audit_logs.append({
                "id": log.id,
                "ts": log.ts,
                "actor": log.actor,
                "event_type": log.event_type,
                "message": log.message,
                "data": json.loads(log.data_json) if log.data_json else None,
            })
    
    return {
        "id": batch.id,
        "title": batch.title,
        "description": batch.description,
        "created_by": batch.created_by,
        "status": batch.status,
        "created_at": batch.created_at,
        "updated_at": batch.updated_at,
        "approved_at": batch.approved_at,
        "approved_by": batch.approved_by,
        "executed_at": batch.executed_at,
        "execution_summary": batch.execution_summary,
        "actions": actions,
        "audit_logs": audit_logs,
        "action_count": len(batch.actions),
        "risk_summary": risk_summary,
    }


# =============================================================================
# Execution Context (for enforcement)
# =============================================================================

# Global execution context - tracks which batch is currently executing
_execution_context: dict = {}


def set_execution_context(batch_id: str, action_ids: List[str]):
    """Set the current execution context."""
    _execution_context["batch_id"] = batch_id
    _execution_context["action_ids"] = set(action_ids)
    _execution_context["active"] = True


def clear_execution_context():
    """Clear the execution context."""
    _execution_context.clear()


def get_execution_context() -> dict:
    """Get the current execution context."""
    return _execution_context.copy()


def verify_execution_allowed(batch_id: Optional[str] = None, action_id: Optional[str] = None) -> tuple[bool, str]:
    """
    Verify that execution is allowed.
    
    Returns (allowed, error_message).
    
    Rules:
    1. Execution context must be active
    2. If batch_id provided, must match context
    3. If action_id provided, must be in context action_ids
    """
    if not _execution_context.get("active"):
        return False, "No approved batch is currently executing"
    
    if batch_id and _execution_context.get("batch_id") != batch_id:
        return False, "Batch ID does not match executing batch"
    
    if action_id and action_id not in _execution_context.get("action_ids", set()):
        return False, "Action is not part of the executing batch"
    
    return True, ""


# =============================================================================
# Action Executor
# =============================================================================

def execute_action(action: BatchAction, db) -> tuple[bool, str, Optional[str]]:
    """
    Execute a single action.
    
    Returns (success, output_summary, error_message).
    
    NOTE: This is a controlled executor. It only runs actions from approved batches.
    """
    now = datetime.now(timezone.utc)
    action.started_at = now.isoformat()
    action.status = "running"
    db.commit()
    
    try:
        payload = json.loads(action.payload_json) if action.payload_json else {}
        
        if action.kind == "note":
            # Notes are informational, always succeed
            output = f"Note recorded: {payload.get('note', action.preview_text)}"
            return True, output, None
        
        elif action.kind == "shell":
            # Execute shell command
            import subprocess
            command = payload.get("command", "")
            cwd = payload.get("cwd")
            
            if not command:
                return False, None, "No command specified"
            
            # Security: Only allow specific safe patterns
            # For now, run with timeout and capture output
            try:
                result = subprocess.run(
                    command,
                    shell=True,
                    cwd=cwd,
                    capture_output=True,
                    text=True,
                    timeout=60,  # 60 second timeout
                )
                output = result.stdout[:500] if result.stdout else ""
                if result.returncode != 0:
                    error = result.stderr[:500] if result.stderr else f"Exit code: {result.returncode}"
                    return False, output, error
                return True, output or "Command completed successfully", None
            except subprocess.TimeoutExpired:
                return False, None, "Command timed out (60s limit)"
            except Exception as e:
                return False, None, str(e)[:500]
        
        elif action.kind == "file_write":
            # Write file
            path = payload.get("path")
            content = payload.get("content", "")
            
            if not path:
                return False, None, "No file path specified"
            
            try:
                import os
                # Create parent directories if needed
                os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
                with open(path, "w") as f:
                    f.write(content)
                return True, f"Wrote {len(content)} bytes to {path}", None
            except Exception as e:
                return False, None, str(e)[:500]
        
        elif action.kind == "file_patch":
            # Apply patch (simplified: just write the modified content)
            path = payload.get("path")
            modified = payload.get("modified", "")
            
            if not path:
                return False, None, "No file path specified"
            
            try:
                with open(path, "w") as f:
                    f.write(modified)
                return True, f"Patched {path}", None
            except Exception as e:
                return False, None, str(e)[:500]
        
        elif action.kind == "http_request":
            # HTTP request
            import httpx
            method = payload.get("method", "GET")
            url = payload.get("url")
            headers = payload.get("headers", {})
            body = payload.get("body")
            
            if not url:
                return False, None, "No URL specified"
            
            try:
                with httpx.Client(timeout=30) as client:
                    response = client.request(method, url, headers=headers, content=body)
                output = f"{method} {url} -> {response.status_code}"
                if response.status_code >= 400:
                    return False, output, f"HTTP {response.status_code}: {response.text[:200]}"
                return True, output, None
            except Exception as e:
                return False, None, str(e)[:500]
        
        elif action.kind == "git":
            # Git command
            import subprocess
            git_command = payload.get("git_command", "")
            repo_path = payload.get("repo_path", ".")
            
            if not git_command:
                return False, None, "No git command specified"
            
            try:
                result = subprocess.run(
                    f"git {git_command}",
                    shell=True,
                    cwd=repo_path,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                output = result.stdout[:500] if result.stdout else ""
                if result.returncode != 0:
                    error = result.stderr[:500] if result.stderr else f"Exit code: {result.returncode}"
                    return False, output, error
                return True, output or "Git command completed", None
            except subprocess.TimeoutExpired:
                return False, None, "Git command timed out"
            except Exception as e:
                return False, None, str(e)[:500]
        
        else:
            return False, None, f"Unknown action kind: {action.kind}"
    
    except Exception as e:
        logger.exception(f"Action execution failed: {action.id}")
        return False, None, str(e)[:500]


def execute_batch_actions(batch_id: str):
    """
    Execute all actions in a batch sequentially.
    
    This is the main execution function, called when admin clicks "Run".
    """
    db = SessionLocal()
    try:
        batch = db.query(ActionBatch).filter(ActionBatch.id == batch_id).first()
        if not batch:
            logger.error(f"Batch not found for execution: {batch_id}")
            return
        
        # Verify status is executing
        if batch.status != BatchStatus.EXECUTING.value:
            logger.error(f"Batch {batch_id} not in executing status: {batch.status}")
            return
        
        # Set execution context
        action_ids = [a.id for a in batch.actions]
        set_execution_context(batch_id, action_ids)
        
        # Execute actions in sequence
        all_success = True
        results = []
        
        for action in sorted(batch.actions, key=lambda a: a.seq):
            now = datetime.now(timezone.utc)
            
            # Create audit log for action start
            create_audit_log(
                db, "system", "action_started",
                f"Started action {action.seq}: {action.preview_text[:50]}...",
                batch_id=batch_id, action_id=action.id,
            )
            db.commit()
            
            # Execute the action
            success, output, error = execute_action(action, db)
            
            # Update action status
            action.completed_at = datetime.now(timezone.utc).isoformat()
            if success:
                action.status = "done"
                action.output_summary = output
            else:
                action.status = "error"
                action.error = error
                action.output_summary = output
                all_success = False
            
            # Create audit log for action finish
            create_audit_log(
                db, "system", "action_finished",
                f"Finished action {action.seq}: {'success' if success else 'failed'}",
                batch_id=batch_id, action_id=action.id,
                data={"success": success, "output": output, "error": error},
            )
            db.commit()
            
            results.append({"seq": action.seq, "success": success, "output": output, "error": error})
            
            # Stop on first error (fail-fast)
            if not success:
                # Mark remaining actions as skipped
                for remaining in batch.actions:
                    if remaining.status == "pending":
                        remaining.status = "skipped"
                break
        
        # Update batch status
        now = datetime.now(timezone.utc).isoformat()
        batch.executed_at = now
        batch.updated_at = now
        
        if all_success:
            batch.status = BatchStatus.EXECUTED.value
            batch.execution_summary = f"All {len(results)} actions completed successfully"
            create_audit_log(
                db, "system", "batch_finished",
                f"Batch executed successfully: {len(results)} actions",
                batch_id=batch_id,
            )
        else:
            batch.status = BatchStatus.FAILED.value
            failed_count = sum(1 for r in results if not r["success"])
            batch.execution_summary = f"Execution failed: {failed_count} action(s) failed"
            create_audit_log(
                db, "system", "batch_failed",
                f"Batch execution failed",
                batch_id=batch_id,
                data={"results": results},
            )
        
        db.commit()
        logger.info(f"Batch execution completed: {batch_id}, status={batch.status}")
    
    except Exception as e:
        logger.exception(f"Batch execution error: {batch_id}")
        # Try to update batch status to failed
        try:
            batch = db.query(ActionBatch).filter(ActionBatch.id == batch_id).first()
            if batch:
                batch.status = BatchStatus.FAILED.value
                batch.execution_summary = f"Execution error: {str(e)[:200]}"
                batch.updated_at = datetime.now(timezone.utc).isoformat()
                create_audit_log(
                    db, "system", "batch_failed",
                    f"Batch execution error: {str(e)[:100]}",
                    batch_id=batch_id,
                )
                db.commit()
        except:
            pass
    finally:
        clear_execution_context()
        db.close()


# =============================================================================
# API Endpoints
# =============================================================================

@router.post("/batches", response_model=BatchResponse)
def create_batch(batch_data: BatchCreate, request: Request):
    """
    Create a new action batch.
    
    The batch starts in 'draft' status unless auto_submit is True.
    Actions are validated and stored with the batch.
    """
    tenant_id = get_tenant_id(request)
    now = datetime.now(timezone.utc).isoformat()
    
    db = SessionLocal()
    try:
        # Create batch
        batch_id = str(uuid.uuid4())
        batch = ActionBatch(
            id=batch_id,
            tenant_id=tenant_id,
            title=batch_data.title,
            description=batch_data.description,
            created_by=batch_data.created_by,
            status=BatchStatus.DRAFT.value,
            created_at=now,
            updated_at=now,
        )
        db.add(batch)
        
        # Create actions
        for seq, action_data in enumerate(batch_data.actions, start=1):
            action = BatchAction(
                id=str(uuid.uuid4()),
                batch_id=batch_id,
                seq=seq,
                kind=action_data.kind.value,
                risk=action_data.risk.value,
                payload_json=json.dumps(action_data.payload),
                preview_text=action_data.preview_text,
                status="pending",
                created_at=now,
            )
            db.add(action)
        
        # Create audit log
        create_audit_log(
            db, batch_data.created_by, "batch_created",
            f"Batch created: {batch_data.title}",
            batch_id=batch_id,
            data={"action_count": len(batch_data.actions)},
        )
        
        db.commit()
        db.refresh(batch)
        
        # Auto-submit if requested
        if batch_data.auto_submit:
            batch.status = BatchStatus.PENDING.value
            batch.updated_at = datetime.now(timezone.utc).isoformat()
            create_audit_log(
                db, batch_data.created_by, "batch_submitted",
                f"Batch submitted for approval: {batch_data.title}",
                batch_id=batch_id,
            )
            db.commit()
            db.refresh(batch)
        
        logger.info(f"Batch created: {batch_id}, status={batch.status}")
        return batch_to_response(batch)
    
    finally:
        db.close()


@router.post("/batches/{batch_id}/submit", response_model=BatchResponse)
def submit_batch(batch_id: str, request: Request):
    """
    Submit a batch for approval (draft -> pending).
    
    Only batches in 'draft' status can be submitted.
    """
    tenant_id = get_tenant_id(request)
    
    db = SessionLocal()
    try:
        batch = db.query(ActionBatch).filter(
            ActionBatch.id == batch_id
        ).first()
        
        if not batch:
            raise HTTPException(status_code=404, detail="Batch not found")
        
        if batch.status != BatchStatus.DRAFT.value:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot submit batch in '{batch.status}' status. Must be 'draft'."
            )
        
        # Update status
        now = datetime.now(timezone.utc).isoformat()
        batch.status = BatchStatus.PENDING.value
        batch.updated_at = now
        
        create_audit_log(
            db, "admin", "batch_submitted",
            f"Batch submitted for approval",
            batch_id=batch_id,
        )
        
        db.commit()
        db.refresh(batch)
        
        logger.info(f"Batch submitted: {batch_id}")
        return batch_to_response(batch)
    
    finally:
        db.close()


@router.post("/batches/{batch_id}/approve", response_model=BatchResponse)
def approve_batch(batch_id: str, request: Request):
    """
    Approve a batch (pending -> approved).
    
    Admin only. Only batches in 'pending' status can be approved.
    Approval does NOT execute the batch - admin must click "Run" separately.
    """
    tenant_id = get_tenant_id(request)
    
    db = SessionLocal()
    try:
        batch = db.query(ActionBatch).filter(
            ActionBatch.id == batch_id
        ).first()
        
        if not batch:
            raise HTTPException(status_code=404, detail="Batch not found")
        
        if batch.status != BatchStatus.PENDING.value:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot approve batch in '{batch.status}' status. Must be 'pending'."
            )
        
        # Update status
        now = datetime.now(timezone.utc).isoformat()
        batch.status = BatchStatus.APPROVED.value
        batch.approved_at = now
        batch.approved_by = "admin"  # TODO: Get actual admin identity
        batch.updated_at = now
        
        create_audit_log(
            db, "admin", "batch_approved",
            f"Batch approved by admin",
            batch_id=batch_id,
        )
        
        db.commit()
        db.refresh(batch)
        
        logger.info(f"Batch approved: {batch_id}")
        return batch_to_response(batch)
    
    finally:
        db.close()


@router.post("/batches/{batch_id}/reject", response_model=BatchResponse)
def reject_batch(batch_id: str, request: Request, reject_data: Optional[BatchReject] = None):
    """
    Reject a batch (pending -> rejected).
    
    Admin only. Only batches in 'pending' status can be rejected.
    """
    tenant_id = get_tenant_id(request)
    reason = reject_data.reason if reject_data else None
    
    db = SessionLocal()
    try:
        batch = db.query(ActionBatch).filter(
            ActionBatch.id == batch_id
        ).first()
        
        if not batch:
            raise HTTPException(status_code=404, detail="Batch not found")
        
        if batch.status != BatchStatus.PENDING.value:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot reject batch in '{batch.status}' status. Must be 'pending'."
            )
        
        # Update status
        now = datetime.now(timezone.utc).isoformat()
        batch.status = BatchStatus.REJECTED.value
        batch.updated_at = now
        
        create_audit_log(
            db, "admin", "batch_rejected",
            f"Batch rejected by admin" + (f": {reason}" if reason else ""),
            batch_id=batch_id,
            data={"reason": reason} if reason else None,
        )
        
        db.commit()
        db.refresh(batch)
        
        logger.info(f"Batch rejected: {batch_id}")
        return batch_to_response(batch)
    
    finally:
        db.close()


@router.post("/batches/{batch_id}/run", response_model=BatchResponse)
def run_batch(batch_id: str, request: Request, background_tasks: BackgroundTasks):
    """
    Execute an approved batch (approved -> executing).
    
    ENFORCEMENT: This is the gate. Only batches in 'approved' status can be run.
    
    Admin only. Execution happens in background via BackgroundTasks.
    """
    tenant_id = get_tenant_id(request)
    
    db = SessionLocal()
    try:
        batch = db.query(ActionBatch).filter(
            ActionBatch.id == batch_id
        ).first()
        
        if not batch:
            raise HTTPException(status_code=404, detail="Batch not found")
        
        # ENFORCEMENT: Only approved batches can be run
        if batch.status != BatchStatus.APPROVED.value:
            raise HTTPException(
                status_code=403,
                detail=f"Cannot run batch in '{batch.status}' status. Must be 'approved'. "
                       f"This is the approval gate - batches must be approved before execution."
            )
        
        # Update status to executing
        now = datetime.now(timezone.utc).isoformat()
        batch.status = BatchStatus.EXECUTING.value
        batch.updated_at = now
        
        create_audit_log(
            db, "admin", "batch_run_requested",
            f"Batch execution started by admin",
            batch_id=batch_id,
        )
        
        db.commit()
        db.refresh(batch)
        
        # Queue execution in background
        background_tasks.add_task(execute_batch_actions, batch_id)
        
        logger.info(f"Batch execution started: {batch_id}")
        return batch_to_response(batch)
    
    finally:
        db.close()


@router.get("/batches", response_model=BatchListResponse)
def list_batches(
    request: Request,
    status: Optional[str] = Query(None, description="Filter by status"),
    created_by: Optional[str] = Query(None, description="Filter by creator"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """
    List batches with optional filters.
    
    Supports filtering by status and creator, with pagination.
    """
    tenant_id = get_tenant_id(request)
    
    db = SessionLocal()
    try:
        query = db.query(ActionBatch)
        
        # Apply filters
        if status:
            query = query.filter(ActionBatch.status == status)
        if created_by:
            query = query.filter(ActionBatch.created_by == created_by)
        
        # Get total count
        total = query.count()
        
        # Apply pagination and order
        query = query.order_by(ActionBatch.created_at.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)
        
        batches = query.all()
        
        return {
            "batches": [batch_to_response(b, include_details=False) for b in batches],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    
    finally:
        db.close()


@router.get("/batches/{batch_id}", response_model=BatchResponse)
def get_batch(batch_id: str, request: Request):
    """
    Get batch details including actions and audit trail.
    """
    tenant_id = get_tenant_id(request)
    
    db = SessionLocal()
    try:
        batch = db.query(ActionBatch).filter(
            ActionBatch.id == batch_id
        ).first()
        
        if not batch:
            raise HTTPException(status_code=404, detail="Batch not found")
        
        return batch_to_response(batch, include_details=True)
    
    finally:
        db.close()


@router.delete("/batches/{batch_id}")
def delete_batch(batch_id: str, request: Request):
    """
    Delete a batch.
    
    Only batches in draft or rejected status can be deleted.
    """
    tenant_id = get_tenant_id(request)
    
    db = SessionLocal()
    try:
        batch = db.query(ActionBatch).filter(
            ActionBatch.id == batch_id
        ).first()
        
        if not batch:
            raise HTTPException(status_code=404, detail="Batch not found")
        
        if batch.status not in (BatchStatus.DRAFT.value, BatchStatus.REJECTED.value):
            raise HTTPException(
                status_code=400,
                detail=f"Cannot delete batch in '{batch.status}' status. Must be 'draft' or 'rejected'."
            )
        
        db.delete(batch)
        db.commit()
        
        logger.info(f"Batch deleted: {batch_id}")
        return {"message": "Batch deleted", "id": batch_id}
    
    finally:
        db.close()


# =============================================================================
# Audit Log Endpoints
# =============================================================================

@router.get("/audit-logs")
def list_audit_logs(
    request: Request,
    batch_id: Optional[str] = Query(None),
    event_type: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    """
    List audit logs with optional filters.
    """
    db = SessionLocal()
    try:
        query = db.query(AuditLog)
        
        if batch_id:
            query = query.filter(AuditLog.batch_id == batch_id)
        if event_type:
            query = query.filter(AuditLog.event_type == event_type)
        
        query = query.order_by(AuditLog.ts.desc()).limit(limit)
        logs = query.all()
        
        return {
            "logs": [
                {
                    "id": log.id,
                    "ts": log.ts,
                    "actor": log.actor,
                    "event_type": log.event_type,
                    "batch_id": log.batch_id,
                    "action_id": log.action_id,
                    "message": log.message,
                    "data": json.loads(log.data_json) if log.data_json else None,
                }
                for log in logs
            ],
            "count": len(logs),
        }
    
    finally:
        db.close()


# =============================================================================
# Execution Verification Endpoint (for enforcement)
# =============================================================================

@router.post("/verify-execution")
def verify_execution(
    request: Request,
    batch_id: Optional[str] = None,
    action_id: Optional[str] = None,
):
    """
    Verify that execution is allowed for a batch/action.
    
    This endpoint can be called by execution code to verify approval.
    Returns 200 if allowed, 403 if not.
    """
    allowed, error = verify_execution_allowed(batch_id, action_id)
    
    if not allowed:
        raise HTTPException(status_code=403, detail=f"Not Approved: {error}")
    
    return {"allowed": True, "batch_id": _execution_context.get("batch_id")}
