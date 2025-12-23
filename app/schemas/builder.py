"""
Pydantic schemas for Codebase Builder Mode API requests and responses.
"""
from datetime import datetime
from enum import Enum
from typing import Any, Optional, List, Union

from pydantic import BaseModel, Field, field_validator, model_validator


class BuilderJobStatus(str, Enum):
    """Builder job execution status."""
    QUEUED = "queued"
    ANALYZING = "analyzing"
    PLANNING = "planning"
    GENERATING = "generating"
    DONE = "done"
    ERROR = "error"


class DiffType(str, Enum):
    """Type of file change in a diff."""
    ADD = "add"
    MODIFY = "modify"
    DELETE = "delete"
    RENAME = "rename"


class BuilderMode(str, Enum):
    """Builder operation mode."""
    BUILDER = "builder"
    SCAFFOLD = "scaffold"
    FIX = "fix"


class ScaffoldTemplate(str, Enum):
    """Available scaffold templates."""
    NEXTJS = "nextjs"
    FASTAPI = "fastapi"
    FULLSTACK = "fullstack"


class OutputFormat(str, Enum):
    """Output format for scaffold."""
    FILES = "files"
    PATCHES = "patches"


# =============================================================================
# Request Schemas
# =============================================================================

class BuilderRunRequest(BaseModel):
    """Request body for POST /builder/run - Builder mode (default)."""
    
    # Mode selection - default to builder for backwards compatibility
    mode: BuilderMode = Field(
        default=BuilderMode.BUILDER,
        description="Operation mode: 'builder', 'scaffold', or 'fix'",
    )
    
    # Repository information (required for builder and fix modes)
    repo_url: Optional[str] = Field(
        default=None,
        description="GitHub repository URL (e.g., https://github.com/owner/repo)",
        max_length=500,
    )
    ref: str = Field(
        default="HEAD",
        description="Git reference (branch, tag, or commit SHA)",
        max_length=100,
    )
    
    # Task description
    prompt: Optional[str] = Field(
        default=None,
        description="Natural language description of the code changes to make",
        min_length=10,
        max_length=8192,
    )
    
    # Optional constraints
    target_paths: Optional[List[str]] = Field(
        default=None,
        description="Limit changes to specific paths (e.g., ['src/', 'tests/'])",
        max_length=20,
    )
    exclude_paths: Optional[List[str]] = Field(
        default=None,
        description="Exclude paths from changes (e.g., ['vendor/', 'node_modules/'])",
        max_length=20,
    )
    max_files: int = Field(
        default=10,
        description="Maximum number of files to modify",
        ge=1,
        le=50,
    )
    
    # LLM configuration
    model: Optional[str] = Field(
        default=None,
        description="LLM model to use (defaults to environment config)",
    )
    
    # Scaffold mode fields
    template: Optional[ScaffoldTemplate] = Field(
        default=None,
        description="Scaffold template: 'nextjs', 'fastapi', or 'fullstack'",
    )
    project: Optional[dict] = Field(
        default=None,
        description="Project configuration for scaffold mode",
    )
    output: Optional[dict] = Field(
        default=None,
        description="Output configuration for scaffold mode",
    )
    
    # Fix mode fields
    repo: Optional[dict] = Field(
        default=None,
        description="Repository configuration for fix mode",
    )
    task: Optional[dict] = Field(
        default=None,
        description="Task configuration for fix mode",
    )
    
    @field_validator("repo_url")
    @classmethod
    def validate_github_url(cls, v: Optional[str]) -> Optional[str]:
        """Validate that repo_url is a valid GitHub URL."""
        if v is None:
            return None
        v = v.strip()
        if not v.startswith("https://github.com/"):
            raise ValueError("Only GitHub repositories are supported (https://github.com/...)")
        return v
    
    @field_validator("target_paths", "exclude_paths", mode="before")
    @classmethod
    def ensure_list(cls, v):
        """Ensure paths are lists."""
        if v is None:
            return None
        if isinstance(v, str):
            return [v]
        return v
    
    @model_validator(mode="after")
    def validate_mode_requirements(self):
        """Validate that required fields are present for each mode."""
        if self.mode == BuilderMode.BUILDER:
            if not self.repo_url:
                raise ValueError("repo_url is required for builder mode")
            if not self.prompt:
                raise ValueError("prompt is required for builder mode")
        elif self.mode == BuilderMode.SCAFFOLD:
            if not self.template:
                raise ValueError("template is required for scaffold mode")
            if not self.project or not self.project.get("name"):
                raise ValueError("project.name is required for scaffold mode")
        elif self.mode == BuilderMode.FIX:
            if not self.repo and not self.repo_url:
                raise ValueError("repo or repo_url is required for fix mode")
            if not self.task and not self.prompt:
                raise ValueError("task or prompt is required for fix mode")
        return self


class BuilderGetFilesRequest(BaseModel):
    """Request for getting generated files."""
    format: str = Field(
        default="unified",
        description="Output format: 'unified' (diff), 'files' (full content), or 'zip'",
    )
    
    @field_validator("format")
    @classmethod
    def validate_format(cls, v: str) -> str:
        """Validate output format."""
        allowed = {"unified", "files", "zip"}
        if v not in allowed:
            raise ValueError(f"Format must be one of: {', '.join(allowed)}")
        return v


# =============================================================================
# Response Schemas
# =============================================================================

class BuilderRunResponse(BaseModel):
    """Response for POST /builder/run."""
    job_id: str
    status: BuilderJobStatus
    mode: BuilderMode = BuilderMode.BUILDER
    repo_url: Optional[str] = None
    template: Optional[str] = None  # For scaffold mode
    created_at: datetime


class ScaffoldFile(BaseModel):
    """A generated scaffold file."""
    path: str = Field(description="File path relative to base_path")
    content: str = Field(description="File content")
    size: int = Field(description="File size in bytes")


class ReproStep(BaseModel):
    """A step in the reproduction plan for fix mode."""
    step_number: int
    description: str
    command: Optional[str] = None
    expected_result: Optional[str] = None


class VerificationItem(BaseModel):
    """An item in the verification checklist for fix mode."""
    description: str
    command: Optional[str] = None
    is_manual: bool = False


class FileDiff(BaseModel):
    """A single file diff in the builder output."""
    path: str = Field(description="File path relative to repository root")
    diff_type: DiffType = Field(description="Type of change")
    original_content: Optional[str] = Field(
        default=None,
        description="Original file content (for modify/delete)"
    )
    new_content: Optional[str] = Field(
        default=None,
        description="New file content (for add/modify)"
    )
    unified_diff: Optional[str] = Field(
        default=None,
        description="Unified diff format"
    )
    old_path: Optional[str] = Field(
        default=None,
        description="Original path (for rename)"
    )
    description: Optional[str] = Field(
        default=None,
        description="Description of the change"
    )
    confidence: Optional[str] = Field(
        default=None,
        description="Confidence level: high, medium, low"
    )


class BuilderResultResponse(BaseModel):
    """Response for GET /builder/result/{job_id}."""
    job_id: str
    status: BuilderJobStatus
    mode: BuilderMode = BuilderMode.BUILDER
    repo_url: Optional[str] = None
    ref: Optional[str] = None
    prompt: Optional[str] = None
    
    # Result data (builder mode)
    files_analyzed: int = Field(default=0, description="Number of files analyzed")
    files_modified: int = Field(default=0, description="Number of files modified")
    
    # Generated changes (builder and fix modes)
    diffs: Optional[List[FileDiff]] = Field(
        default=None,
        description="List of file diffs"
    )
    
    # Summary
    summary: Optional[str] = Field(
        default=None,
        description="AI-generated summary of changes"
    )
    
    # Scaffold mode fields
    scaffold_files: Optional[List[ScaffoldFile]] = Field(
        default=None,
        description="Generated scaffold files (scaffold mode)"
    )
    scaffold_base_path: Optional[str] = Field(
        default=None,
        description="Base path for scaffold files"
    )
    scaffold_template: Optional[str] = Field(
        default=None,
        description="Template used for scaffolding"
    )
    scaffold_total_bytes: Optional[int] = Field(
        default=None,
        description="Total bytes of generated scaffold"
    )
    
    # Fix mode fields
    repo_summary: Optional[str] = Field(
        default=None,
        description="Summary of repository structure (fix mode)"
    )
    likely_cause: Optional[str] = Field(
        default=None,
        description="Likely root cause of the issue (fix mode)"
    )
    repro_plan: Optional[List[ReproStep]] = Field(
        default=None,
        description="Steps to reproduce the issue (fix mode)"
    )
    verification_checklist: Optional[List[VerificationItem]] = Field(
        default=None,
        description="Checklist to verify the fix (fix mode)"
    )
    risk_notes: Optional[str] = Field(
        default=None,
        description="Risk notes for proposed changes"
    )
    
    # Error information
    error: Optional[str] = Field(default=None, description="Error message if failed")
    
    # Timing
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: Optional[int] = None


class BuilderFilesResponse(BaseModel):
    """Response for GET /builder/files/{job_id}."""
    job_id: str
    status: BuilderJobStatus
    format: str
    
    # For unified diff format
    unified_patch: Optional[str] = Field(
        default=None,
        description="Complete unified diff patch"
    )
    
    # For files format
    files: Optional[List[dict]] = Field(
        default=None,
        description="List of file contents with paths"
    )
    
    # Metadata
    total_files: int = Field(default=0)
    total_lines_added: int = Field(default=0)
    total_lines_removed: int = Field(default=0)


class RepoTreeEntry(BaseModel):
    """A single entry in the repository tree."""
    path: str
    type: str = Field(description="'file' or 'dir'")
    size: Optional[int] = None


class RepoTreeResponse(BaseModel):
    """Response for repository tree operations."""
    owner: str
    repo: str
    ref: str
    path: str = ""
    tree: List[RepoTreeEntry]
    truncated: bool = False
    total_entries: int


class RepoFileResponse(BaseModel):
    """Response for repository file fetch."""
    owner: str
    repo: str
    path: str
    ref: str
    content: str
    encoding: str = "utf-8"
    size: int
    truncated: bool = False


class RepoSearchResult(BaseModel):
    """A single search result."""
    path: str
    name: str
    url: str
    sha: str


class RepoSearchResponse(BaseModel):
    """Response for repository code search."""
    owner: str
    repo: str
    query: str
    results: List[RepoSearchResult]
    total_count: int


class BuilderAnalysisStep(BaseModel):
    """Information about an analysis step."""
    step_number: int
    action: str = Field(description="Action taken (e.g., 'fetch_tree', 'read_file', 'search')")
    target: str = Field(description="Target of action (e.g., file path, search query)")
    status: str = Field(description="'pending', 'done', 'error'")
    duration_ms: Optional[int] = None
    result_summary: Optional[str] = None


class BuilderStatusResponse(BaseModel):
    """Detailed status response for a builder job."""
    job_id: str
    status: BuilderJobStatus
    repo_url: str
    ref: str
    prompt: str
    
    # Progress information
    current_phase: str = Field(
        description="Current phase: 'queued', 'analyzing', 'planning', 'generating', 'done'"
    )
    progress_pct: int = Field(
        default=0,
        description="Progress percentage (0-100)",
        ge=0,
        le=100,
    )
    
    # Analysis steps
    analysis_steps: Optional[List[BuilderAnalysisStep]] = None
    
    # Timing
    created_at: datetime
    started_at: Optional[datetime] = None
    estimated_completion: Optional[datetime] = None
    
    # Error
    error: Optional[str] = None


class BuilderJobListItem(BaseModel):
    """Single builder job in list response."""
    job_id: str
    status: BuilderJobStatus
    repo_url: str
    prompt_preview: str = Field(description="First 100 chars of prompt")
    files_modified: int = 0
    created_at: datetime
    completed_at: Optional[datetime] = None
    duration_ms: Optional[int] = None


class BuilderJobListResponse(BaseModel):
    """Response for GET /builder/jobs."""
    items: List[BuilderJobListItem]
    limit: int
    offset: int
    total: int
