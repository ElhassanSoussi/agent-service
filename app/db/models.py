"""
SQLAlchemy models for job persistence and multi-tenant security.
"""
from sqlalchemy import Column, Text, Integer, Index, ForeignKey
from sqlalchemy.orm import relationship

from app.db.database import Base


class Tenant(Base):
    """SQLite model for tenants (organizations/accounts)."""
    __tablename__ = "tenants"

    id = Column(Text, primary_key=True, index=True)
    name = Column(Text, unique=True, nullable=False, index=True)
    created_at = Column(Text, nullable=False)
    
    # Quota limits (per day)
    max_requests_per_day = Column(Integer, default=500, nullable=False)
    max_tool_calls_per_day = Column(Integer, default=200, nullable=False)
    max_bytes_fetched_per_day = Column(Integer, default=5_000_000, nullable=False)  # 5MB
    
    # Relationships
    api_keys = relationship("ApiKey", back_populates="tenant", cascade="all, delete-orphan")
    jobs = relationship("Job", back_populates="tenant")
    usage_daily = relationship("UsageDaily", back_populates="tenant", cascade="all, delete-orphan")


class ApiKey(Base):
    """SQLite model for API keys."""
    __tablename__ = "api_keys"

    id = Column(Text, primary_key=True, index=True)
    tenant_id = Column(Text, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    key_hash = Column(Text, unique=True, nullable=False, index=True)  # HMAC-SHA256 hash
    key_prefix = Column(Text, nullable=False)  # e.g., "agk_live_ab12" (first 12 chars)
    label = Column(Text, nullable=True)  # User-friendly label
    status = Column(Text, nullable=False, default="active", index=True)  # active, revoked
    created_at = Column(Text, nullable=False)
    revoked_at = Column(Text, nullable=True)
    last_used_at = Column(Text, nullable=True)
    
    # Relationship
    tenant = relationship("Tenant", back_populates="api_keys")


class UsageDaily(Base):
    """SQLite model for daily usage tracking per tenant."""
    __tablename__ = "usage_daily"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(Text, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    day = Column(Text, nullable=False, index=True)  # YYYY-MM-DD
    
    # Usage counters
    requests_total = Column(Integer, default=0, nullable=False)
    agent_jobs_total = Column(Integer, default=0, nullable=False)
    tool_calls_total = Column(Integer, default=0, nullable=False)
    bytes_fetched_total = Column(Integer, default=0, nullable=False)
    
    # Per-tool breakdown (JSON: {"web_search": 3, "http_fetch": 5})
    per_tool_json = Column(Text, nullable=True)
    
    # Relationship
    tenant = relationship("Tenant", back_populates="usage_daily")
    
    __table_args__ = (
        Index("ix_usage_daily_tenant_day", "tenant_id", "day", unique=True),
    )


class Job(Base):
    """SQLite model for agent jobs."""
    __tablename__ = "jobs"

    id = Column(Text, primary_key=True, index=True)
    tenant_id = Column(Text, ForeignKey("tenants.id", ondelete="SET NULL"), nullable=True, index=True)
    status = Column(Text, nullable=False, index=True)
    tool = Column(Text, nullable=True, index=True)  # nullable for agent mode
    input = Column(Text, nullable=False)  # JSON string
    output = Column(Text, nullable=True)  # JSON string
    error = Column(Text, nullable=True)
    created_at = Column(Text, nullable=False, index=True)  # ISO timestamp
    started_at = Column(Text, nullable=True)
    completed_at = Column(Text, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    
    # Agent mode columns (nullable for backwards compatibility)
    mode = Column(Text, nullable=True, default="tool")  # "tool" or "agent"
    prompt = Column(Text, nullable=True)  # Original user prompt for agent mode
    plan_json = Column(Text, nullable=True)  # JSON array of planned steps
    final_output = Column(Text, nullable=True)  # Final agent output/summary
    
    # Artifact columns (for scaffold builder)
    artifact_path = Column(Text, nullable=True)  # Server path to ZIP file
    artifact_name = Column(Text, nullable=True)  # Original filename (e.g., "my-app.zip")
    artifact_size_bytes = Column(Integer, nullable=True)  # ZIP file size
    artifact_sha256 = Column(Text, nullable=True)  # SHA256 hash for verification
    builder_template = Column(Text, nullable=True)  # Template used (e.g., "nextjs_web")
    builder_project_name = Column(Text, nullable=True)  # Sanitized project name
    
    # Repo builder columns (Phase 15)
    repo_url = Column(Text, nullable=True)  # Source GitHub repo URL
    repo_ref = Column(Text, nullable=True)  # Git ref (branch/tag/commit)
    patch_artifact_path = Column(Text, nullable=True)  # Path to .diff file
    patch_sha256 = Column(Text, nullable=True)  # SHA256 of patch file
    patch_size_bytes = Column(Integer, nullable=True)  # Size of patch file
    
    # Relationships
    tenant = relationship("Tenant", back_populates="jobs")
    steps = relationship("AgentStep", back_populates="job", cascade="all, delete-orphan")

    # Composite index for common list query (status filter + created_at sort)
    __table_args__ = (
        Index("ix_jobs_status_created", "status", "created_at"),
        Index("ix_jobs_mode", "mode"),
        Index("ix_jobs_tenant_created", "tenant_id", "created_at"),
    )


class AgentStep(Base):
    """SQLite model for agent execution steps."""
    __tablename__ = "agent_steps"

    id = Column(Text, primary_key=True, index=True)
    job_id = Column(Text, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    step_number = Column(Integer, nullable=False)
    tool = Column(Text, nullable=False)
    input_json = Column(Text, nullable=False)  # JSON string (minimal, no secrets)
    status = Column(Text, nullable=False, default="pending")  # pending, running, done, error
    output_summary = Column(Text, nullable=True)  # Short summary only (max 500 chars)
    error = Column(Text, nullable=True)
    created_at = Column(Text, nullable=False, index=True)
    started_at = Column(Text, nullable=True)
    completed_at = Column(Text, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    
    # Relationship back to job
    job = relationship("Job", back_populates="steps")

    __table_args__ = (
        Index("ix_agent_steps_job_created", "job_id", "created_at"),
    )


class Memory(Base):
    """SQLite model for agent memory (Phase 21)."""
    __tablename__ = "memories"

    id = Column(Text, primary_key=True, index=True)
    tenant_id = Column(Text, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True)
    scope = Column(Text, nullable=False, default="global", index=True)  # global, conversation, user
    conversation_id = Column(Text, nullable=True, index=True)  # For conversation-scoped memories
    key = Column(Text, nullable=False, index=True)  # Memory key/title
    value = Column(Text, nullable=False)  # Memory content
    tags = Column(Text, nullable=True)  # Comma-separated tags
    created_at = Column(Text, nullable=False, index=True)
    updated_at = Column(Text, nullable=False)

    __table_args__ = (
        Index("ix_memories_tenant_scope", "tenant_id", "scope"),
        Index("ix_memories_conversation", "conversation_id"),
    )


class Feedback(Base):
    """SQLite model for user feedback on agent responses (Phase 21)."""
    __tablename__ = "feedback"

    id = Column(Text, primary_key=True, index=True)
    tenant_id = Column(Text, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True)
    conversation_id = Column(Text, nullable=True, index=True)
    message_id = Column(Text, nullable=True, index=True)
    user_prompt = Column(Text, nullable=True)  # The user's message
    agent_response = Column(Text, nullable=True)  # The agent's response
    rating = Column(Integer, nullable=False)  # +1 (thumbs up) or -1 (thumbs down)
    notes = Column(Text, nullable=True)  # Optional user notes
    created_at = Column(Text, nullable=False, index=True)

    __table_args__ = (
        Index("ix_feedback_tenant_created", "tenant_id", "created_at"),
        Index("ix_feedback_rating", "rating"),
    )


# =============================================================================
# Phase A1: Approval Gate Models
# =============================================================================

class ActionBatch(Base):
    """
    SQLite model for action batches (Phase A1).
    
    A batch contains one or more actions that Xone proposes.
    Admin must approve and explicitly run batches.
    """
    __tablename__ = "action_batches"

    id = Column(Text, primary_key=True, index=True)
    tenant_id = Column(Text, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True)
    title = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    created_by = Column(Text, nullable=False, default="xone")  # "xone" or "admin"
    status = Column(Text, nullable=False, default="draft", index=True)
    # Status enum: draft | pending | approved | rejected | executing | executed | failed
    created_at = Column(Text, nullable=False, index=True)
    updated_at = Column(Text, nullable=False)
    approved_at = Column(Text, nullable=True)
    approved_by = Column(Text, nullable=True)
    executed_at = Column(Text, nullable=True)
    execution_summary = Column(Text, nullable=True)

    # Relationships
    actions = relationship("BatchAction", back_populates="batch", cascade="all, delete-orphan", order_by="BatchAction.seq")
    audit_logs = relationship("AuditLog", back_populates="batch", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_action_batches_status_created", "status", "created_at"),
        Index("ix_action_batches_tenant_status", "tenant_id", "status"),
    )


class BatchAction(Base):
    """
    SQLite model for individual actions within a batch (Phase A1).
    
    Each action has a kind (shell, file_write, etc.), risk level, and payload.
    """
    __tablename__ = "batch_actions"

    id = Column(Text, primary_key=True, index=True)
    batch_id = Column(Text, ForeignKey("action_batches.id", ondelete="CASCADE"), nullable=False, index=True)
    seq = Column(Integer, nullable=False)  # Sequence number within batch
    kind = Column(Text, nullable=False)  # shell | file_write | file_patch | http_request | git | note
    risk = Column(Text, nullable=False, default="safe")  # safe | medium | risky
    payload_json = Column(Text, nullable=False)  # JSON with action details
    preview_text = Column(Text, nullable=False)  # Human-readable description
    status = Column(Text, nullable=False, default="pending")  # pending | running | done | error | skipped
    output_summary = Column(Text, nullable=True)  # Execution output summary
    error = Column(Text, nullable=True)  # Error message if failed
    created_at = Column(Text, nullable=False)
    started_at = Column(Text, nullable=True)
    completed_at = Column(Text, nullable=True)

    # Relationship
    batch = relationship("ActionBatch", back_populates="actions")

    __table_args__ = (
        Index("ix_batch_actions_batch_seq", "batch_id", "seq"),
    )


class AuditLog(Base):
    """
    SQLite model for audit logs (Phase A1).
    
    Tracks all significant events: batch creation, approval, rejection, execution.
    """
    __tablename__ = "audit_logs"

    id = Column(Text, primary_key=True, index=True)
    ts = Column(Text, nullable=False, index=True)  # ISO timestamp
    actor = Column(Text, nullable=False)  # "xone" | "admin" | "system"
    event_type = Column(Text, nullable=False)  # No index=True here, defined below
    # Event types: batch_created | batch_submitted | batch_approved | batch_rejected |
    #              batch_run_requested | action_started | action_finished | batch_finished | batch_failed
    batch_id = Column(Text, ForeignKey("action_batches.id", ondelete="CASCADE"), nullable=True, index=True)
    action_id = Column(Text, ForeignKey("batch_actions.id", ondelete="SET NULL"), nullable=True)  # No index needed
    message = Column(Text, nullable=False)
    data_json = Column(Text, nullable=True)  # Additional JSON data

    # Relationship
    batch = relationship("ActionBatch", back_populates="audit_logs")

    __table_args__ = (
        Index("ix_audit_logs_batch_ts", "batch_id", "ts"),
        Index("ix_audit_logs_event_type", "event_type"),
    )
