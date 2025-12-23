"""
Build Runner - Safe, deterministic build execution for repositories.

Executes predefined CI-style pipelines (lint/test/build) in isolated workspaces.
NO arbitrary shell commands - only predetermined safe subprocess calls.

Security:
- No shell=True anywhere
- Only subprocess.run([...]) with timeouts
- Domain allowlist for repo sources (GitHub, GitLab)
- Isolated workspace per job
- No secrets in logs
- Auto-cleanup of old workspaces
"""
import hashlib
import io
import logging
import os
import re
import shutil
import subprocess
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

# =============================================================================
# Constants
# =============================================================================

# Domain allowlist for repo sources
ALLOWED_DOMAINS = {
    "github.com",
    "codeload.github.com",
    "gitlab.com",
}

# Timeouts (seconds)
DOWNLOAD_TIMEOUT = 60
COMMAND_TIMEOUT = 300  # 5 minutes per command
TOTAL_BUILD_TIMEOUT = 900  # 15 minutes total

# Size limits
MAX_DOWNLOAD_SIZE = 50 * 1024 * 1024  # 50MB download
MAX_EXTRACTED_SIZE = 200 * 1024 * 1024  # 200MB extracted
MAX_FILES = 20_000
MAX_LOG_SIZE = 1 * 1024 * 1024  # 1MB per log file

# Workspace config
WORKSPACE_RETENTION_HOURS = 24

# Directories
PROJECT_ROOT = Path(__file__).parent.parent.parent
WORKSPACES_DIR = PROJECT_ROOT / "data" / "workspaces"
ARTIFACTS_DIR = PROJECT_ROOT / "data" / "artifacts"


class ProjectType(str, Enum):
    """Detected project type."""
    PYTHON = "python"
    NODE = "node"
    UNKNOWN = "unknown"


class PipelineStatus(str, Enum):
    """Pipeline execution status."""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class BuildRunnerError(Exception):
    """Error during build runner operations."""
    pass


@dataclass
class CommandResult:
    """Result of a subprocess command."""
    command: list[str]
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    timed_out: bool = False


@dataclass
class PipelineStep:
    """A single step in the build pipeline."""
    name: str
    description: str
    status: PipelineStatus = PipelineStatus.PENDING
    command_results: list[CommandResult] = field(default_factory=list)
    error: Optional[str] = None
    duration_ms: int = 0


@dataclass
class BuildResult:
    """Result of a build runner execution."""
    job_id: str
    repo_url: str
    ref: str
    project_type: ProjectType
    pipeline_steps: list[PipelineStep]
    overall_status: PipelineStatus
    workspace_path: Optional[Path] = None
    # Logs
    build_log_path: Optional[Path] = None
    build_log_sha256: Optional[str] = None
    build_log_size: Optional[int] = None
    test_log_path: Optional[Path] = None
    test_log_sha256: Optional[str] = None
    test_log_size: Optional[int] = None
    # Summary
    total_duration_ms: int = 0
    error: Optional[str] = None
    notes: list[str] = field(default_factory=list)


# =============================================================================
# Validation Functions
# =============================================================================

def validate_repo_url(url: str) -> tuple[str, str]:
    """
    Validate and parse a repository URL.
    
    Returns:
        Tuple of (owner, repo)
        
    Raises:
        BuildRunnerError: If URL is invalid or domain not allowed
    """
    try:
        parsed = urlparse(url)
    except Exception:
        raise BuildRunnerError(f"Invalid URL format: {url}")
    
    if parsed.scheme != "https":
        raise BuildRunnerError("Only HTTPS URLs are allowed")
    
    if parsed.netloc not in ALLOWED_DOMAINS:
        raise BuildRunnerError(
            f"Domain not allowed: {parsed.netloc}. "
            f"Allowed: {', '.join(sorted(ALLOWED_DOMAINS))}"
        )
    
    # Extract owner and repo from path
    path = parsed.path.strip("/")
    parts = path.split("/")
    
    if len(parts) < 2:
        raise BuildRunnerError("Invalid repo URL: must include owner and repo")
    
    owner = parts[0]
    repo = parts[1]
    
    # Remove .git suffix if present
    if repo.endswith(".git"):
        repo = repo[:-4]
    
    # Validate owner/repo format
    if not re.match(r"^[a-zA-Z0-9_.-]+$", owner):
        raise BuildRunnerError(f"Invalid owner name: {owner}")
    if not re.match(r"^[a-zA-Z0-9_.-]+$", repo):
        raise BuildRunnerError(f"Invalid repo name: {repo}")
    
    return owner, repo


def _is_safe_path(path: str) -> bool:
    """Check if a path is safe (no traversal, not absolute)."""
    normalized = os.path.normpath(path)
    if os.path.isabs(normalized):
        return False
    if ".." in normalized.split(os.sep):
        return False
    if normalized.startswith("/"):
        return False
    return True


# =============================================================================
# Workspace Management
# =============================================================================

class WorkspaceManager:
    """Manages isolated workspaces for build jobs."""
    
    def __init__(self, base_dir: Optional[Path] = None):
        self._base_dir = Path(base_dir) if base_dir else WORKSPACES_DIR
        self._base_dir.mkdir(parents=True, exist_ok=True)
    
    @property
    def base_dir(self) -> Path:
        return self._base_dir
    
    def create_workspace(self, job_id: str) -> Path:
        """Create an isolated workspace directory for a job."""
        workspace = self._base_dir / job_id
        workspace.mkdir(parents=True, exist_ok=True)
        logger.info(f"workspace_created job_id={job_id}")
        return workspace
    
    def get_workspace(self, job_id: str) -> Optional[Path]:
        """Get workspace path if it exists."""
        workspace = self._base_dir / job_id
        if workspace.exists():
            return workspace
        return None
    
    def cleanup_workspace(self, job_id: str) -> bool:
        """Remove workspace for a job."""
        workspace = self._base_dir / job_id
        if workspace.exists():
            shutil.rmtree(workspace, ignore_errors=True)
            logger.info(f"workspace_cleaned job_id={job_id}")
            return True
        return False
    
    def cleanup_old_workspaces(self) -> int:
        """Remove workspaces older than retention period."""
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=WORKSPACE_RETENTION_HOURS)
            deleted = 0
            
            for item in self._base_dir.iterdir():
                if item.is_dir():
                    mtime = datetime.fromtimestamp(item.stat().st_mtime, tz=timezone.utc)
                    if mtime < cutoff:
                        shutil.rmtree(item, ignore_errors=True)
                        deleted += 1
            
            if deleted > 0:
                logger.info(f"cleanup_workspaces deleted={deleted}")
            return deleted
        except Exception as e:
            logger.warning(f"cleanup_workspaces_failed error={type(e).__name__}")
            return 0


# Global workspace manager
workspace_manager = WorkspaceManager()


# =============================================================================
# Project Detection
# =============================================================================

def detect_project_type(workspace: Path) -> tuple[ProjectType, dict]:
    """
    Detect project type from workspace files.
    
    Returns:
        Tuple of (ProjectType, metadata dict)
    """
    metadata = {
        "has_pyproject": False,
        "has_requirements": False,
        "has_setup_py": False,
        "has_package_json": False,
        "has_pytest_ini": False,
        "has_npm_scripts": {},
    }
    
    # Check Python indicators
    pyproject_path = workspace / "pyproject.toml"
    if pyproject_path.exists():
        metadata["has_pyproject"] = True
    
    requirements_path = workspace / "requirements.txt"
    if requirements_path.exists():
        metadata["has_requirements"] = True
    
    setup_py_path = workspace / "setup.py"
    if setup_py_path.exists():
        metadata["has_setup_py"] = True
    
    pytest_ini_path = workspace / "pytest.ini"
    if pytest_ini_path.exists():
        metadata["has_pytest_ini"] = True
    
    # Check Node.js indicators
    package_json_path = workspace / "package.json"
    if package_json_path.exists():
        metadata["has_package_json"] = True
        try:
            import json
            content = package_json_path.read_text()
            pkg = json.loads(content)
            scripts = pkg.get("scripts", {})
            metadata["has_npm_scripts"] = {
                "test": "test" in scripts,
                "build": "build" in scripts,
                "lint": "lint" in scripts,
            }
        except Exception:
            pass
    
    # Determine primary type (Python takes priority)
    if metadata["has_pyproject"] or metadata["has_requirements"] or metadata["has_setup_py"]:
        return ProjectType.PYTHON, metadata
    elif metadata["has_package_json"]:
        return ProjectType.NODE, metadata
    else:
        return ProjectType.UNKNOWN, metadata


# =============================================================================
# Safe Command Execution
# =============================================================================

def _sanitize_env() -> dict:
    """Create a sanitized environment for subprocess execution."""
    # Start with minimal environment
    safe_env = {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "HOME": "/tmp",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        # Prevent various tools from accessing network during build
        "NO_PROXY": "*",
        "no_proxy": "*",
    }
    
    # Add Python-specific env vars
    safe_env["PYTHONDONTWRITEBYTECODE"] = "1"
    safe_env["PYTHONUNBUFFERED"] = "1"
    
    # Add Node-specific env vars
    safe_env["NODE_ENV"] = "test"
    safe_env["CI"] = "true"
    
    return safe_env


def run_command(
    cmd: list[str],
    cwd: Path,
    timeout: int = COMMAND_TIMEOUT,
    env_override: Optional[dict] = None,
) -> CommandResult:
    """
    Execute a command safely with no shell.
    
    Args:
        cmd: Command as list of strings (NO shell=True!)
        cwd: Working directory
        timeout: Timeout in seconds
        env_override: Additional environment variables
        
    Returns:
        CommandResult with output and status
    """
    # Validate command is a list (never a string for shell execution)
    if not isinstance(cmd, list):
        raise BuildRunnerError("Command must be a list, not a string")
    
    if len(cmd) == 0:
        raise BuildRunnerError("Command cannot be empty")
    
    # Build environment
    env = _sanitize_env()
    if env_override:
        env.update(env_override)
    
    start_time = datetime.now(timezone.utc)
    timed_out = False
    
    try:
        result = subprocess.run(
            cmd,
            cwd=str(cwd),
            env=env,
            capture_output=True,
            timeout=timeout,
            text=True,
            # CRITICAL: No shell=True!
        )
        
        stdout = result.stdout or ""
        stderr = result.stderr or ""
        exit_code = result.returncode
        
    except subprocess.TimeoutExpired as e:
        stdout = e.stdout.decode("utf-8", errors="replace") if e.stdout else ""
        stderr = e.stderr.decode("utf-8", errors="replace") if e.stderr else ""
        exit_code = -1
        timed_out = True
        logger.warning(f"command_timeout cmd={cmd[0]} timeout={timeout}")
        
    except subprocess.SubprocessError as e:
        stdout = ""
        stderr = str(e)
        exit_code = -1
    
    end_time = datetime.now(timezone.utc)
    duration_ms = int((end_time - start_time).total_seconds() * 1000)
    
    # Truncate output if too large
    max_output = MAX_LOG_SIZE // 2
    if len(stdout) > max_output:
        stdout = stdout[:max_output] + f"\n... (truncated, {len(stdout)} total chars)"
    if len(stderr) > max_output:
        stderr = stderr[:max_output] + f"\n... (truncated, {len(stderr)} total chars)"
    
    return CommandResult(
        command=cmd,
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        duration_ms=duration_ms,
        timed_out=timed_out,
    )


# =============================================================================
# Download Repository
# =============================================================================

async def download_repo_to_workspace(
    owner: str,
    repo: str,
    ref: str,
    workspace: Path,
    source_domain: str = "github.com",
) -> int:
    """
    Download a repository and extract to workspace.
    
    Returns:
        Number of files extracted
    """
    # Build download URL
    if source_domain == "github.com":
        download_url = f"https://codeload.github.com/{owner}/{repo}/zip/refs/heads/{ref}"
    elif source_domain == "gitlab.com":
        download_url = f"https://gitlab.com/{owner}/{repo}/-/archive/{ref}/{repo}-{ref}.zip"
    else:
        raise BuildRunnerError(f"Unsupported source domain: {source_domain}")
    
    logger.info(f"download_start owner={owner} repo={repo} ref={ref}")
    
    try:
        async with httpx.AsyncClient(timeout=DOWNLOAD_TIMEOUT, follow_redirects=True) as client:
            response = await client.get(download_url)
            
            if response.status_code == 404:
                # Try without refs/heads/ for tags/commits
                if source_domain == "github.com":
                    download_url = f"https://codeload.github.com/{owner}/{repo}/zip/{ref}"
                    response = await client.get(download_url)
            
            if response.status_code != 200:
                raise BuildRunnerError(
                    f"Failed to download repository: HTTP {response.status_code}"
                )
            
            content = response.content
            download_size = len(content)
            
            if download_size > MAX_DOWNLOAD_SIZE:
                raise BuildRunnerError(
                    f"Download size exceeds limit: {download_size} > {MAX_DOWNLOAD_SIZE} bytes"
                )
    except httpx.TimeoutException:
        raise BuildRunnerError("Download timed out")
    except httpx.RequestError as e:
        raise BuildRunnerError(f"Download failed: {type(e).__name__}")
    
    # Extract to workspace
    file_count = 0
    total_size = 0
    
    try:
        with zipfile.ZipFile(io.BytesIO(content), "r") as zf:
            if len(zf.namelist()) > MAX_FILES:
                raise BuildRunnerError(
                    f"Too many files: {len(zf.namelist())} > {MAX_FILES}"
                )
            
            for name in zf.namelist():
                if name.endswith("/"):
                    continue
                
                # Remove root directory prefix
                parts = name.split("/", 1)
                if len(parts) < 2:
                    continue
                relative_path = parts[1]
                
                if not relative_path:
                    continue
                
                # Validate path
                if not _is_safe_path(relative_path):
                    raise BuildRunnerError(f"Unsafe path in archive: {relative_path}")
                
                file_info = zf.getinfo(name)
                total_size += file_info.file_size
                
                if total_size > MAX_EXTRACTED_SIZE:
                    raise BuildRunnerError(
                        f"Extracted size exceeds limit: {total_size} > {MAX_EXTRACTED_SIZE}"
                    )
                
                # Extract file
                dest_path = workspace / relative_path
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                dest_path.write_bytes(zf.read(name))
                file_count += 1
                
    except zipfile.BadZipFile:
        raise BuildRunnerError("Invalid ZIP archive")
    
    logger.info(f"download_done files={file_count} size={total_size}")
    return file_count


# =============================================================================
# Pipeline Builders
# =============================================================================

def build_python_pipeline(workspace: Path, metadata: dict) -> list[PipelineStep]:
    """Build Python pipeline steps."""
    steps = []
    venv_path = workspace / ".venv"
    python_bin = venv_path / "bin" / "python"
    pip_bin = venv_path / "bin" / "pip"
    
    # Step 1: Create virtual environment
    steps.append(PipelineStep(
        name="setup",
        description="Create Python virtual environment",
    ))
    
    # Step 2: Install dependencies
    steps.append(PipelineStep(
        name="install",
        description="Install Python dependencies",
    ))
    
    # Step 3: Run tests (if pytest available)
    steps.append(PipelineStep(
        name="test",
        description="Run pytest tests",
    ))
    
    return steps


def build_node_pipeline(workspace: Path, metadata: dict) -> list[PipelineStep]:
    """Build Node.js pipeline steps."""
    steps = []
    scripts = metadata.get("has_npm_scripts", {})
    
    # Step 1: Install dependencies
    steps.append(PipelineStep(
        name="install",
        description="Install Node.js dependencies (npm ci)",
    ))
    
    # Step 2: Lint (if available)
    if scripts.get("lint"):
        steps.append(PipelineStep(
            name="lint",
            description="Run linter (npm run lint)",
        ))
    
    # Step 3: Test (if available)
    if scripts.get("test"):
        steps.append(PipelineStep(
            name="test",
            description="Run tests (npm test)",
        ))
    
    # Step 4: Build (if available)
    if scripts.get("build"):
        steps.append(PipelineStep(
            name="build",
            description="Build project (npm run build)",
        ))
    
    return steps


# =============================================================================
# Pipeline Execution
# =============================================================================

def execute_python_pipeline(
    workspace: Path,
    metadata: dict,
    steps: list[PipelineStep],
) -> bool:
    """Execute Python pipeline. Returns True if successful."""
    venv_path = workspace / ".venv"
    python_bin = venv_path / "bin" / "python"
    pip_bin = venv_path / "bin" / "pip"
    
    # Custom env with venv paths
    venv_env = {
        "VIRTUAL_ENV": str(venv_path),
        "PATH": f"{venv_path / 'bin'}:/usr/local/bin:/usr/bin:/bin",
    }
    
    overall_success = True
    
    for step in steps:
        if step.name == "setup":
            step.status = PipelineStatus.RUNNING
            start = datetime.now(timezone.utc)
            
            # Create venv
            result = run_command(
                ["python3", "-m", "venv", str(venv_path)],
                cwd=workspace,
            )
            step.command_results.append(result)
            
            if result.exit_code != 0:
                step.status = PipelineStatus.FAILED
                step.error = f"Failed to create venv: {result.stderr}"
                overall_success = False
                break
            
            step.status = PipelineStatus.SUCCESS
            step.duration_ms = int((datetime.now(timezone.utc) - start).total_seconds() * 1000)
            
        elif step.name == "install":
            step.status = PipelineStatus.RUNNING
            start = datetime.now(timezone.utc)
            
            # Upgrade pip
            result = run_command(
                [str(pip_bin), "install", "--upgrade", "pip"],
                cwd=workspace,
                env_override=venv_env,
            )
            step.command_results.append(result)
            
            # Install from requirements.txt if exists
            if metadata.get("has_requirements"):
                result = run_command(
                    [str(pip_bin), "install", "-r", "requirements.txt"],
                    cwd=workspace,
                    env_override=venv_env,
                )
                step.command_results.append(result)
            
            # Install from pyproject.toml if exists
            if metadata.get("has_pyproject"):
                result = run_command(
                    [str(pip_bin), "install", "-e", "."],
                    cwd=workspace,
                    env_override=venv_env,
                )
                step.command_results.append(result)
            
            # Always install pytest
            result = run_command(
                [str(pip_bin), "install", "pytest"],
                cwd=workspace,
                env_override=venv_env,
            )
            step.command_results.append(result)
            
            # Check for failures
            failed = any(r.exit_code != 0 for r in step.command_results)
            if failed:
                step.status = PipelineStatus.FAILED
                step.error = "Dependency installation failed"
                overall_success = False
            else:
                step.status = PipelineStatus.SUCCESS
            
            step.duration_ms = int((datetime.now(timezone.utc) - start).total_seconds() * 1000)
            
        elif step.name == "test":
            if not overall_success:
                step.status = PipelineStatus.SKIPPED
                step.error = "Skipped due to previous failure"
                continue
            
            step.status = PipelineStatus.RUNNING
            start = datetime.now(timezone.utc)
            
            # Run pytest
            result = run_command(
                [str(python_bin), "-m", "pytest", "-q", "--tb=short"],
                cwd=workspace,
                env_override=venv_env,
                timeout=COMMAND_TIMEOUT,
            )
            step.command_results.append(result)
            
            if result.exit_code != 0 and not result.timed_out:
                # Check if it's just "no tests found" (exit code 5)
                if result.exit_code == 5:
                    step.status = PipelineStatus.SUCCESS
                    step.error = "No tests found"
                else:
                    step.status = PipelineStatus.FAILED
                    step.error = f"Tests failed with exit code {result.exit_code}"
                    overall_success = False
            elif result.timed_out:
                step.status = PipelineStatus.FAILED
                step.error = "Test execution timed out"
                overall_success = False
            else:
                step.status = PipelineStatus.SUCCESS
            
            step.duration_ms = int((datetime.now(timezone.utc) - start).total_seconds() * 1000)
    
    return overall_success


def execute_node_pipeline(
    workspace: Path,
    metadata: dict,
    steps: list[PipelineStep],
) -> bool:
    """Execute Node.js pipeline. Returns True if successful."""
    overall_success = True
    
    for step in steps:
        if not overall_success and step.name != "install":
            step.status = PipelineStatus.SKIPPED
            step.error = "Skipped due to previous failure"
            continue
        
        step.status = PipelineStatus.RUNNING
        start = datetime.now(timezone.utc)
        
        if step.name == "install":
            # Prefer npm ci for reproducible builds
            package_lock = workspace / "package-lock.json"
            if package_lock.exists():
                result = run_command(["npm", "ci"], cwd=workspace)
            else:
                result = run_command(["npm", "install"], cwd=workspace)
            step.command_results.append(result)
            
            if result.exit_code != 0:
                step.status = PipelineStatus.FAILED
                step.error = f"npm install failed: {result.stderr[:200]}"
                overall_success = False
            else:
                step.status = PipelineStatus.SUCCESS
                
        elif step.name == "lint":
            result = run_command(["npm", "run", "lint"], cwd=workspace)
            step.command_results.append(result)
            
            if result.exit_code != 0:
                step.status = PipelineStatus.FAILED
                step.error = "Lint failed"
                overall_success = False
            else:
                step.status = PipelineStatus.SUCCESS
                
        elif step.name == "test":
            result = run_command(["npm", "test"], cwd=workspace, timeout=COMMAND_TIMEOUT)
            step.command_results.append(result)
            
            if result.exit_code != 0 and not result.timed_out:
                step.status = PipelineStatus.FAILED
                step.error = f"Tests failed with exit code {result.exit_code}"
                overall_success = False
            elif result.timed_out:
                step.status = PipelineStatus.FAILED
                step.error = "Test execution timed out"
                overall_success = False
            else:
                step.status = PipelineStatus.SUCCESS
                
        elif step.name == "build":
            result = run_command(["npm", "run", "build"], cwd=workspace)
            step.command_results.append(result)
            
            if result.exit_code != 0:
                step.status = PipelineStatus.FAILED
                step.error = "Build failed"
                overall_success = False
            else:
                step.status = PipelineStatus.SUCCESS
        
        step.duration_ms = int((datetime.now(timezone.utc) - start).total_seconds() * 1000)
    
    return overall_success


# =============================================================================
# Log Artifacts
# =============================================================================

def save_build_logs(
    job_id: str,
    steps: list[PipelineStep],
    artifacts_dir: Optional[Path] = None,
) -> tuple[Optional[Path], Optional[str], Optional[int]]:
    """
    Save build logs as artifact.
    
    Returns:
        Tuple of (log_path, sha256, size) or (None, None, None) if failed
    """
    artifacts_dir = artifacts_dir or ARTIFACTS_DIR
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    
    log_lines = []
    log_lines.append(f"Build Log for Job: {job_id}")
    log_lines.append(f"Generated: {datetime.now(timezone.utc).isoformat()}")
    log_lines.append("=" * 60)
    log_lines.append("")
    
    for step in steps:
        log_lines.append(f"## Step: {step.name}")
        log_lines.append(f"Description: {step.description}")
        log_lines.append(f"Status: {step.status.value}")
        if step.error:
            log_lines.append(f"Error: {step.error}")
        log_lines.append(f"Duration: {step.duration_ms}ms")
        log_lines.append("")
        
        for i, cmd_result in enumerate(step.command_results):
            log_lines.append(f"### Command {i + 1}: {' '.join(cmd_result.command)}")
            log_lines.append(f"Exit code: {cmd_result.exit_code}")
            if cmd_result.timed_out:
                log_lines.append("TIMED OUT")
            log_lines.append("")
            
            if cmd_result.stdout:
                log_lines.append("--- STDOUT ---")
                log_lines.append(cmd_result.stdout)
                log_lines.append("")
            
            if cmd_result.stderr:
                log_lines.append("--- STDERR ---")
                log_lines.append(cmd_result.stderr)
                log_lines.append("")
        
        log_lines.append("-" * 40)
        log_lines.append("")
    
    log_content = "\n".join(log_lines)
    
    # Truncate if too large
    if len(log_content) > MAX_LOG_SIZE:
        log_content = log_content[:MAX_LOG_SIZE] + "\n... (log truncated)"
    
    log_bytes = log_content.encode("utf-8")
    sha256 = hashlib.sha256(log_bytes).hexdigest()
    
    log_path = artifacts_dir / f"{job_id}_build.log"
    log_path.write_bytes(log_bytes)
    
    logger.info(f"build_log_saved job_id={job_id} size={len(log_bytes)}")
    
    return log_path, sha256, len(log_bytes)


# =============================================================================
# Main Build Function
# =============================================================================

async def run_build(
    job_id: str,
    repo_url: str,
    ref: str = "main",
    pipeline: str = "auto",
    patch_content: Optional[str] = None,
) -> BuildResult:
    """
    Run a complete build pipeline for a repository.
    
    Args:
        job_id: Job ID for workspace isolation
        repo_url: GitHub/GitLab repository URL
        ref: Git ref (branch/tag/commit)
        pipeline: Pipeline type ("auto", "python", "node")
        patch_content: Optional unified diff to apply before building
        
    Returns:
        BuildResult with pipeline status and logs
    """
    start_time = datetime.now(timezone.utc)
    notes = []
    
    # Validate URL
    owner, repo = validate_repo_url(repo_url)
    parsed = urlparse(repo_url)
    source_domain = parsed.netloc
    
    # Clean up old workspaces opportunistically
    workspace_manager.cleanup_old_workspaces()
    
    # Create workspace
    workspace = workspace_manager.create_workspace(job_id)
    
    try:
        # Download repository
        notes.append(f"Downloading {owner}/{repo}@{ref}")
        file_count = await download_repo_to_workspace(
            owner, repo, ref, workspace, source_domain
        )
        notes.append(f"Downloaded {file_count} files")
        
        # Apply patch if provided
        if patch_content:
            # TODO: Implement patch application
            notes.append("Patch application not yet implemented")
        
        # Detect project type
        project_type, metadata = detect_project_type(workspace)
        notes.append(f"Detected project type: {project_type.value}")
        
        if project_type == ProjectType.UNKNOWN:
            return BuildResult(
                job_id=job_id,
                repo_url=repo_url,
                ref=ref,
                project_type=project_type,
                pipeline_steps=[],
                overall_status=PipelineStatus.FAILED,
                workspace_path=workspace,
                error="Could not detect project type (no pyproject.toml, requirements.txt, or package.json)",
                notes=notes,
                total_duration_ms=int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000),
            )
        
        # Build and execute pipeline
        if project_type == ProjectType.PYTHON:
            steps = build_python_pipeline(workspace, metadata)
            success = execute_python_pipeline(workspace, metadata, steps)
        else:  # NODE
            steps = build_node_pipeline(workspace, metadata)
            success = execute_node_pipeline(workspace, metadata, steps)
        
        # Save logs
        log_path, log_sha256, log_size = save_build_logs(job_id, steps)
        
        overall_status = PipelineStatus.SUCCESS if success else PipelineStatus.FAILED
        
        return BuildResult(
            job_id=job_id,
            repo_url=repo_url,
            ref=ref,
            project_type=project_type,
            pipeline_steps=steps,
            overall_status=overall_status,
            workspace_path=workspace,
            build_log_path=log_path,
            build_log_sha256=log_sha256,
            build_log_size=log_size,
            notes=notes,
            total_duration_ms=int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000),
        )
        
    except BuildRunnerError as e:
        return BuildResult(
            job_id=job_id,
            repo_url=repo_url,
            ref=ref,
            project_type=ProjectType.UNKNOWN,
            pipeline_steps=[],
            overall_status=PipelineStatus.FAILED,
            workspace_path=workspace,
            error=str(e),
            notes=notes,
            total_duration_ms=int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000),
        )
    except Exception as e:
        logger.exception(f"build_error job_id={job_id}")
        return BuildResult(
            job_id=job_id,
            repo_url=repo_url,
            ref=ref,
            project_type=ProjectType.UNKNOWN,
            pipeline_steps=[],
            overall_status=PipelineStatus.FAILED,
            workspace_path=workspace,
            error=f"Unexpected error: {type(e).__name__}",
            notes=notes,
            total_duration_ms=int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000),
        )
