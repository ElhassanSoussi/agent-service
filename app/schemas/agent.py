"""
Pydantic schemas for Agent API requests and responses.
"""
from datetime import datetime
from enum import Enum
from typing import Any, Optional, List, Union

from pydantic import BaseModel, Field, field_validator


class ToolName(str, Enum):
    """Available tools."""
    ECHO = "echo"
    HTTP_FETCH = "http_fetch"
    WEB_SEARCH = "web_search"
    WEB_PAGE_TEXT = "web_page_text"
    WEB_SUMMARIZE = "web_summarize"


class JobStatus(str, Enum):
    """Job execution status."""
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"


class StepStatus(str, Enum):
    """Step execution status."""
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"


class JobMode(str, Enum):
    """Job execution mode."""
    TOOL = "tool"
    AGENT = "agent"
    BUILDER = "builder"


# --- Tool Mode Request (legacy, backwards compatible) ---
class ToolModeRequest(BaseModel):
    """Legacy request body for tool mode."""
    tool: ToolName
    input: dict[str, Any] = Field(..., max_length=32768)


# --- Agent Mode Request ---
class AgentModeRequest(BaseModel):
    """Request body for agent mode."""
    mode: JobMode = JobMode.AGENT
    prompt: str = Field(..., min_length=1, max_length=4096)
    max_steps: int = Field(default=3, ge=1, le=5)
    allowed_tools: Optional[List[ToolName]] = None  # None = all tools
    
    @field_validator("allowed_tools", mode="before")
    @classmethod
    def default_allowed_tools(cls, v):
        if v is None:
            return [
                ToolName.ECHO,
                ToolName.HTTP_FETCH,
                ToolName.WEB_SEARCH,
                ToolName.WEB_PAGE_TEXT,
                ToolName.WEB_SUMMARIZE,
            ]
        return v


# --- Unified Request (accepts both modes) ---
class AgentRunRequest(BaseModel):
    """
    Unified request body for POST /agent/run.
    Accepts either:
    - Tool mode: {"tool": "echo", "input": {...}}
    - Agent mode: {"mode": "agent", "prompt": "...", ...}
    """
    # Tool mode fields (optional)
    tool: Optional[ToolName] = None
    input: Optional[dict[str, Any]] = Field(default=None, max_length=32768)
    
    # Agent mode fields (optional)
    mode: Optional[JobMode] = None
    prompt: Optional[str] = Field(default=None, min_length=1, max_length=4096)
    max_steps: int = Field(default=3, ge=1, le=5)
    allowed_tools: Optional[List[ToolName]] = None
    
    def get_mode(self) -> JobMode:
        """Determine the actual mode from the request."""
        if self.mode == JobMode.AGENT:
            return JobMode.AGENT
        if self.tool is not None:
            return JobMode.TOOL
        if self.prompt is not None:
            return JobMode.AGENT
        return JobMode.TOOL
    
    def validate_request(self) -> None:
        """Validate that required fields are present for the detected mode."""
        mode = self.get_mode()
        if mode == JobMode.TOOL:
            if self.tool is None:
                raise ValueError("Tool mode requires 'tool' field")
            if self.input is None:
                raise ValueError("Tool mode requires 'input' field")
        else:  # AGENT mode
            if self.prompt is None:
                raise ValueError("Agent mode requires 'prompt' field")


class AgentRunResponse(BaseModel):
    """Response for POST /agent/run."""
    job_id: str
    status: JobStatus
    mode: JobMode = JobMode.TOOL
    created_at: datetime


class AgentStatusResponse(BaseModel):
    """Response for GET /agent/status/{job_id}."""
    job_id: str
    status: JobStatus
    mode: JobMode = JobMode.TOOL
    tool: Optional[ToolName] = None  # For tool mode
    prompt: Optional[str] = None  # For agent mode
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    output: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    step_count: Optional[int] = None  # For agent mode


# --- Step schemas ---
class StepInfo(BaseModel):
    """Information about a single execution step."""
    step_id: str
    step_number: int
    tool: str
    status: StepStatus
    output_summary: Optional[str] = None
    error: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: Optional[int] = None


class StepsResponse(BaseModel):
    """Response for GET /agent/steps/{job_id}."""
    job_id: str
    mode: JobMode
    steps: List[StepInfo]
    total_steps: int


class Citation(BaseModel):
    """Citation from web research tools."""
    url: str
    title: Optional[str] = None


class AgentResultResponse(BaseModel):
    """Response for GET /agent/result/{job_id}."""
    job_id: str
    status: JobStatus
    mode: JobMode
    final_output: Optional[str] = None
    bullets: Optional[List[str]] = None
    citations: Optional[List[Citation]] = None
    error: Optional[str] = None
    steps: Optional[List[StepInfo]] = None


# --- List/Delete/Cancel schemas (unchanged) ---
class JobListItem(BaseModel):
    """Single job in list response (no input/output bodies)."""
    job_id: str
    status: JobStatus
    mode: JobMode = JobMode.TOOL
    tool: Optional[ToolName] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    has_output: bool = False
    has_error: bool = False


class JobListResponse(BaseModel):
    """Response for GET /agent/jobs."""
    items: List[JobListItem]
    limit: int
    offset: int
    total: int


class JobDeleteResponse(BaseModel):
    """Response for DELETE /agent/jobs/{job_id}."""
    deleted: bool


class JobCancelResponse(BaseModel):
    """Response for POST /agent/cancel/{job_id}."""
    job_id: str
    status: JobStatus
    message: str
