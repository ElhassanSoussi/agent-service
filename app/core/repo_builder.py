"""
Repo Builder - Download GitHub repos, apply transforms, generate patches.

Security:
- Domain allowlist for downloads (github.com, codeload.github.com only)
- Zip-slip prevention (no .. or absolute paths)
- Size limits enforced
- No shell execution
- No secrets in logs
"""
import hashlib
import io
import logging
import os
import re
import tarfile
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

# =============================================================================
# Constants
# =============================================================================

# Domain allowlist for repo downloads
ALLOWED_DOMAINS = {"github.com", "codeload.github.com"}

# Size limits
MAX_DOWNLOAD_SIZE = 25 * 1024 * 1024  # 25MB download
MAX_EXTRACTED_SIZE = 80 * 1024 * 1024  # 80MB extracted
MAX_FILES = 10_000  # Max files in repo

# Timeout for downloads
DOWNLOAD_TIMEOUT = 60  # seconds

# Artifact directory
PROJECT_ROOT = Path(__file__).parent.parent.parent
ARTIFACTS_DIR = PROJECT_ROOT / "data" / "artifacts"


class RepoBuilderError(Exception):
    """Error during repo builder operations."""
    pass


@dataclass
class RepoDownloadInfo:
    """Information about a downloaded repository."""
    owner: str
    repo: str
    ref: str
    files: dict[str, bytes]  # path -> content (bytes)
    total_size: int
    file_count: int


@dataclass 
class RepoBuildResult:
    """Result of building/transforming a repository."""
    job_id: str
    owner: str
    repo: str
    ref: str
    template: str
    # Original files
    original_files: dict[str, bytes]
    # Modified files
    modified_files: dict[str, bytes]
    # Summary
    files_added: list[str]
    files_modified: list[str]
    files_unchanged: list[str]
    notes: list[str]
    # Artifacts
    modified_zip_path: Optional[Path] = None
    modified_zip_sha256: Optional[str] = None
    modified_zip_size: Optional[int] = None
    patch_path: Optional[Path] = None
    patch_sha256: Optional[str] = None
    patch_size: Optional[int] = None
    summary_path: Optional[Path] = None


def validate_repo_url(url: str) -> tuple[str, str]:
    """
    Validate and parse a GitHub repo URL.
    
    Returns:
        Tuple of (owner, repo)
        
    Raises:
        RepoBuilderError: If URL is invalid or domain not allowed
    """
    try:
        parsed = urlparse(url)
    except Exception:
        raise RepoBuilderError(f"Invalid URL format: {url}")
    
    if parsed.scheme != "https":
        raise RepoBuilderError("Only HTTPS URLs are allowed")
    
    if parsed.netloc not in ALLOWED_DOMAINS:
        raise RepoBuilderError(
            f"Domain not allowed: {parsed.netloc}. "
            f"Allowed: {', '.join(sorted(ALLOWED_DOMAINS))}"
        )
    
    # Extract owner and repo from path
    path = parsed.path.strip("/")
    parts = path.split("/")
    
    if len(parts) < 2:
        raise RepoBuilderError("Invalid GitHub URL: must include owner and repo")
    
    owner = parts[0]
    repo = parts[1]
    
    # Remove .git suffix if present
    if repo.endswith(".git"):
        repo = repo[:-4]
    
    # Validate owner/repo format
    if not re.match(r"^[a-zA-Z0-9_.-]+$", owner):
        raise RepoBuilderError(f"Invalid owner name: {owner}")
    if not re.match(r"^[a-zA-Z0-9_.-]+$", repo):
        raise RepoBuilderError(f"Invalid repo name: {repo}")
    
    return owner, repo


def _is_safe_path(path: str) -> bool:
    """Check if a path is safe (no traversal, not absolute)."""
    # Normalize the path
    normalized = os.path.normpath(path)
    
    # Reject absolute paths
    if os.path.isabs(normalized):
        return False
    
    # Reject paths that try to escape (contain ..)
    if ".." in normalized.split(os.sep):
        return False
    
    # Reject paths that start with /
    if normalized.startswith("/"):
        return False
    
    return True


async def download_repo(
    owner: str,
    repo: str,
    ref: str = "HEAD",
) -> RepoDownloadInfo:
    """
    Download a GitHub repository as a ZIP/tarball and extract files.
    
    Args:
        owner: Repository owner
        repo: Repository name
        ref: Git ref (branch, tag, or commit)
        
    Returns:
        RepoDownloadInfo with extracted files
        
    Raises:
        RepoBuilderError: If download fails or limits exceeded
    """
    # GitHub archive URL
    download_url = f"https://codeload.github.com/{owner}/{repo}/zip/refs/heads/{ref}"
    
    logger.info(f"repo_download_start owner={owner} repo={repo} ref={ref}")
    
    try:
        async with httpx.AsyncClient(timeout=DOWNLOAD_TIMEOUT, follow_redirects=True) as client:
            response = await client.get(download_url)
            
            if response.status_code == 404:
                # Try without refs/heads/ for tags or commits
                download_url = f"https://codeload.github.com/{owner}/{repo}/zip/{ref}"
                response = await client.get(download_url)
            
            if response.status_code != 200:
                raise RepoBuilderError(
                    f"Failed to download repository: HTTP {response.status_code}"
                )
            
            content = response.content
            download_size = len(content)
            
            if download_size > MAX_DOWNLOAD_SIZE:
                raise RepoBuilderError(
                    f"Download size exceeds limit: {download_size} > {MAX_DOWNLOAD_SIZE} bytes"
                )
    except httpx.TimeoutException:
        raise RepoBuilderError("Download timed out")
    except httpx.RequestError as e:
        raise RepoBuilderError(f"Download failed: {type(e).__name__}")
    
    # Extract files from ZIP
    files: dict[str, bytes] = {}
    total_size = 0
    
    try:
        with zipfile.ZipFile(io.BytesIO(content), "r") as zf:
            # Check for too many files
            if len(zf.namelist()) > MAX_FILES:
                raise RepoBuilderError(
                    f"Too many files in repository: {len(zf.namelist())} > {MAX_FILES}"
                )
            
            for name in zf.namelist():
                # Skip directories
                if name.endswith("/"):
                    continue
                
                # Remove the root directory (e.g., "repo-main/")
                parts = name.split("/", 1)
                if len(parts) < 2:
                    continue
                relative_path = parts[1]
                
                if not relative_path:
                    continue
                
                # Validate path (zip-slip prevention)
                if not _is_safe_path(relative_path):
                    logger.warning(f"repo_download_unsafe_path path={relative_path}")
                    raise RepoBuilderError(f"Unsafe path in archive: {relative_path}")
                
                # Extract file content
                file_info = zf.getinfo(name)
                file_size = file_info.file_size
                total_size += file_size
                
                if total_size > MAX_EXTRACTED_SIZE:
                    raise RepoBuilderError(
                        f"Extracted size exceeds limit: {total_size} > {MAX_EXTRACTED_SIZE} bytes"
                    )
                
                files[relative_path] = zf.read(name)
    except zipfile.BadZipFile:
        raise RepoBuilderError("Invalid ZIP archive")
    
    logger.info(
        f"repo_download_done owner={owner} repo={repo} "
        f"files={len(files)} size={total_size}"
    )
    
    return RepoDownloadInfo(
        owner=owner,
        repo=repo,
        ref=ref,
        files=files,
        total_size=total_size,
        file_count=len(files),
    )


def _decode_file_content(content: bytes) -> Optional[str]:
    """Try to decode file content as text. Returns None if binary."""
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        try:
            return content.decode("latin-1")
        except UnicodeDecodeError:
            return None


def generate_unified_diff(
    original_files: dict[str, bytes],
    modified_files: dict[str, bytes],
) -> str:
    """
    Generate a unified diff between original and modified files.
    
    Returns:
        Unified diff string
    """
    import difflib
    
    diff_parts = []
    all_paths = set(original_files.keys()) | set(modified_files.keys())
    
    for path in sorted(all_paths):
        original = original_files.get(path, b"")
        modified = modified_files.get(path, b"")
        
        if original == modified:
            continue
        
        # Try to decode as text
        original_text = _decode_file_content(original) if original else ""
        modified_text = _decode_file_content(modified) if modified else ""
        
        # Skip binary files
        if original_text is None or modified_text is None:
            diff_parts.append(f"Binary file {path} differs\n")
            continue
        
        # Generate diff
        original_lines = original_text.splitlines(keepends=True)
        modified_lines = modified_text.splitlines(keepends=True)
        
        # Ensure lines end with newline for proper diff
        if original_lines and not original_lines[-1].endswith("\n"):
            original_lines[-1] += "\n"
        if modified_lines and not modified_lines[-1].endswith("\n"):
            modified_lines[-1] += "\n"
        
        from_file = f"a/{path}" if original else "/dev/null"
        to_file = f"b/{path}" if modified else "/dev/null"
        
        diff = difflib.unified_diff(
            original_lines,
            modified_lines,
            fromfile=from_file,
            tofile=to_file,
        )
        diff_text = "".join(diff)
        if diff_text:
            diff_parts.append(diff_text)
    
    return "\n".join(diff_parts)


# =============================================================================
# Template Transforms
# =============================================================================

def apply_fastapi_template(
    files: dict[str, bytes],
    options: dict,
) -> tuple[dict[str, bytes], list[str], list[str], list[str], list[str]]:
    """
    Apply fastapi_api template transforms to a repository.
    
    Args:
        files: Original files (path -> bytes)
        options: Transform options (add_docker, add_github_actions, add_readme)
        
    Returns:
        Tuple of (modified_files, files_added, files_modified, files_unchanged, notes)
    """
    modified_files = dict(files)  # Copy
    files_added = []
    files_modified = []
    files_unchanged = list(files.keys())
    notes = []
    
    add_docker = options.get("add_docker", False)
    add_github_actions = options.get("add_github_actions", False)
    add_readme = options.get("add_readme", False)
    
    # Check for existing FastAPI indicators
    has_fastapi = False
    has_health = False
    has_ruff = False
    
    for path, content in files.items():
        text = _decode_file_content(content)
        if text:
            if "fastapi" in text.lower() or "from fastapi" in text:
                has_fastapi = True
            if "/health" in text or "@app.get(\"/health\")" in text or "@router.get(\"/health\")" in text:
                has_health = True
            if "ruff" in path.lower() or "ruff.toml" in path:
                has_ruff = True
    
    # Add README.md if requested
    if add_readme:
        readme_path = "README.md"
        if readme_path in files:
            # Append to existing README
            existing = _decode_file_content(files[readme_path]) or ""
            if "## How to Run" not in existing and "## Getting Started" not in existing:
                new_content = existing.rstrip() + "\n\n" + _generate_readme_section()
                modified_files[readme_path] = new_content.encode("utf-8")
                files_unchanged.remove(readme_path)
                files_modified.append(readme_path)
                notes.append("Appended 'How to Run' section to README.md")
            else:
                notes.append("README.md already has a 'How to Run' or 'Getting Started' section")
        else:
            modified_files[readme_path] = _generate_full_readme().encode("utf-8")
            files_added.append(readme_path)
            notes.append("Created README.md with project documentation")
    
    # Add Dockerfile if requested
    if add_docker:
        dockerfile_path = "Dockerfile"
        compose_path = "docker-compose.yml"
        
        if dockerfile_path not in files:
            modified_files[dockerfile_path] = _generate_dockerfile().encode("utf-8")
            files_added.append(dockerfile_path)
            notes.append("Created Dockerfile for containerization")
        else:
            notes.append("Dockerfile already exists, skipping")
        
        if compose_path not in files:
            modified_files[compose_path] = _generate_docker_compose().encode("utf-8")
            files_added.append(compose_path)
            notes.append("Created docker-compose.yml")
        else:
            notes.append("docker-compose.yml already exists, skipping")
    
    # Add GitHub Actions CI if requested
    if add_github_actions:
        ci_path = ".github/workflows/ci.yml"
        if ci_path not in files:
            modified_files[ci_path] = _generate_github_ci().encode("utf-8")
            files_added.append(ci_path)
            notes.append("Created GitHub Actions CI workflow")
        else:
            notes.append("GitHub Actions CI workflow already exists, skipping")
    
    # Add health endpoint example if missing
    if not has_health and has_fastapi:
        health_example_path = "health_example.py"
        modified_files[health_example_path] = _generate_health_example().encode("utf-8")
        files_added.append(health_example_path)
        notes.append("Added health endpoint example (health_example.py)")
    elif not has_fastapi:
        notes.append("No FastAPI detected in repository")
    else:
        notes.append("Health endpoint already exists in repository")
    
    # Add ruff config if missing
    if not has_ruff:
        ruff_path = "ruff.toml"
        if ruff_path not in files:
            modified_files[ruff_path] = _generate_ruff_config().encode("utf-8")
            files_added.append(ruff_path)
            notes.append("Created ruff.toml for linting configuration")
    else:
        notes.append("Ruff configuration already exists")
    
    return modified_files, files_added, files_modified, files_unchanged, notes


def _generate_readme_section() -> str:
    """Generate a 'How to Run' section for README."""
    return '''## How to Run

### Prerequisites
- Python 3.10+
- pip or poetry

### Installation
```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\\Scripts\\activate

# Install dependencies
pip install -r requirements.txt
```

### Running the Application
```bash
# Development server
uvicorn main:app --reload

# Production
uvicorn main:app --host 0.0.0.0 --port 8000
```

### Running with Docker
```bash
docker-compose up --build
```

### Testing
```bash
pytest
```
'''


def _generate_full_readme() -> str:
    """Generate a full README.md."""
    return '''# FastAPI Application

A FastAPI application with best practices.

## Features

- FastAPI web framework
- Docker support
- GitHub Actions CI
- Health endpoint
- Ruff linting

''' + _generate_readme_section()


def _generate_dockerfile() -> str:
    """Generate a Dockerfile for FastAPI."""
    return '''FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Run application
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
'''


def _generate_docker_compose() -> str:
    """Generate docker-compose.yml."""
    return '''version: "3.9"

services:
  app:
    build: .
    ports:
      - "8000:8000"
    environment:
      - ENVIRONMENT=development
    volumes:
      - .:/app
    restart: unless-stopped
'''


def _generate_github_ci() -> str:
    """Generate GitHub Actions CI workflow."""
    return '''name: CI

on:
  push:
    branches: [main, master]
  pull_request:
    branches: [main, master]

jobs:
  test:
    runs-on: ubuntu-latest
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt
          pip install pytest ruff
      
      - name: Lint with ruff
        run: ruff check .
      
      - name: Run tests
        run: pytest -v

  docker:
    runs-on: ubuntu-latest
    needs: test
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Build Docker image
        run: docker build -t app .
'''


def _generate_health_example() -> str:
    """Generate a health endpoint example."""
    return '''"""
Health endpoint example.
Add this to your FastAPI application for health checks.
"""
from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health_check():
    """Health check endpoint for load balancers and monitoring."""
    return {"status": "ok"}


# Usage: Include this router in your main app
# from health_example import router as health_router
# app.include_router(health_router)
'''


def _generate_ruff_config() -> str:
    """Generate ruff.toml configuration."""
    return '''# Ruff configuration
# https://docs.astral.sh/ruff/

line-length = 120
target-version = "py311"

[lint]
select = [
    "E",   # pycodestyle errors
    "W",   # pycodestyle warnings
    "F",   # Pyflakes
    "I",   # isort
    "B",   # flake8-bugbear
    "C4",  # flake8-comprehensions
    "UP",  # pyupgrade
]
ignore = [
    "E501",  # line too long (handled by formatter)
    "B008",  # do not perform function calls in argument defaults
]

[lint.isort]
known-first-party = ["app"]
'''


# =============================================================================
# Artifact Creation
# =============================================================================

def create_repo_artifacts(
    job_id: str,
    result: RepoBuildResult,
    artifacts_dir: Optional[Path] = None,
) -> RepoBuildResult:
    """
    Create ZIP and patch artifacts from build result.
    
    Args:
        job_id: Job ID to associate with artifacts
        result: Build result with modified files
        artifacts_dir: Directory to store artifacts
        
    Returns:
        Updated RepoBuildResult with artifact paths
    """
    if artifacts_dir is None:
        artifacts_dir = ARTIFACTS_DIR
    
    artifacts_dir = Path(artifacts_dir)
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    
    # Create modified repo ZIP
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        root_name = f"{result.repo}-modified"
        for path, content in sorted(result.modified_files.items()):
            full_path = f"{root_name}/{path}"
            zf.writestr(full_path, content)
    
    zip_bytes = zip_buffer.getvalue()
    zip_sha256 = hashlib.sha256(zip_bytes).hexdigest()
    zip_path = artifacts_dir / f"{job_id}_modified_repo.zip"
    zip_path.write_bytes(zip_bytes)
    
    result.modified_zip_path = zip_path
    result.modified_zip_sha256 = zip_sha256
    result.modified_zip_size = len(zip_bytes)
    
    # Create patch diff
    patch_content = generate_unified_diff(result.original_files, result.modified_files)
    patch_bytes = patch_content.encode("utf-8")
    patch_sha256 = hashlib.sha256(patch_bytes).hexdigest()
    patch_path = artifacts_dir / f"{job_id}_changes.diff"
    patch_path.write_bytes(patch_bytes)
    
    result.patch_path = patch_path
    result.patch_sha256 = patch_sha256
    result.patch_size = len(patch_bytes)
    
    # Create summary JSON
    import json
    summary = {
        "job_id": job_id,
        "owner": result.owner,
        "repo": result.repo,
        "ref": result.ref,
        "template": result.template,
        "files_added": result.files_added,
        "files_modified": result.files_modified,
        "files_unchanged_count": len(result.files_unchanged),
        "notes": result.notes,
        "modified_zip_sha256": zip_sha256,
        "modified_zip_size": len(zip_bytes),
        "patch_sha256": patch_sha256,
        "patch_size": len(patch_bytes),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    summary_bytes = json.dumps(summary, indent=2).encode("utf-8")
    summary_path = artifacts_dir / f"{job_id}_summary.json"
    summary_path.write_bytes(summary_bytes)
    result.summary_path = summary_path
    
    logger.info(
        f"repo_artifacts_created job_id={job_id} "
        f"zip_size={len(zip_bytes)} patch_size={len(patch_bytes)}"
    )
    
    return result


async def build_from_repo(
    job_id: str,
    repo_url: str,
    ref: str = "main",
    template: str = "fastapi_api",
    options: Optional[dict] = None,
    artifacts_dir: Optional[Path] = None,
) -> RepoBuildResult:
    """
    Main entry point: Download repo, apply transforms, create artifacts.
    
    Args:
        job_id: Job ID to associate with build
        repo_url: GitHub repository URL
        ref: Git ref (branch, tag, commit)
        template: Template to apply
        options: Template options
        artifacts_dir: Directory to store artifacts
        
    Returns:
        RepoBuildResult with all artifacts
        
    Raises:
        RepoBuilderError: If any step fails
    """
    # Validate URL
    owner, repo = validate_repo_url(repo_url)
    
    # Download repository
    download_info = await download_repo(owner, repo, ref)
    
    # Apply template transforms
    options = options or {}
    
    if template == "fastapi_api":
        modified_files, files_added, files_modified, files_unchanged, notes = \
            apply_fastapi_template(download_info.files, options)
    else:
        raise RepoBuilderError(f"Unknown template: {template}")
    
    # Create result
    result = RepoBuildResult(
        job_id=job_id,
        owner=owner,
        repo=repo,
        ref=ref,
        template=template,
        original_files=download_info.files,
        modified_files=modified_files,
        files_added=files_added,
        files_modified=files_modified,
        files_unchanged=files_unchanged,
        notes=notes,
    )
    
    # Create artifacts
    result = create_repo_artifacts(job_id, result, artifacts_dir)
    
    return result
