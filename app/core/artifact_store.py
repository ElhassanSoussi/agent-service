"""
Artifact storage for scaffold ZIP files.
Manages creation, storage, retrieval, and cleanup of generated project artifacts.

Security:
- Path traversal prevention
- Size limits enforced
- SHA256 verification
- No shell execution
"""
import hashlib
import io
import logging
import os
import re
import shutil
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# =============================================================================
# Constants
# =============================================================================

# Size limits
MAX_FILES = 300
MAX_UNCOMPRESSED_BYTES = 8 * 1024 * 1024  # 8MB
MAX_ZIP_BYTES = 5 * 1024 * 1024  # 5MB

# Artifact retention
ARTIFACT_RETENTION_HOURS = 24

# Valid project name pattern
PROJECT_NAME_PATTERN = re.compile(r"^[a-zA-Z][a-zA-Z0-9_-]{0,63}$")

# Valid template names
VALID_TEMPLATES = {"nextjs_web", "fastapi_api", "fullstack_nextjs_fastapi"}

# Artifact directory
PROJECT_ROOT = Path(__file__).parent.parent.parent
ARTIFACTS_DIR = PROJECT_ROOT / "data" / "artifacts"


@dataclass
class ArtifactInfo:
    """Information about a stored artifact."""
    job_id: str
    path: Path
    name: str
    size_bytes: int
    sha256: str
    template: str
    project_name: str
    created_at: datetime


class ArtifactError(Exception):
    """Error during artifact operations."""
    pass


def validate_project_name(name: str) -> str:
    """Validate and return sanitized project name."""
    if not name:
        raise ArtifactError("Project name is required")
    
    name = name.strip()
    if not PROJECT_NAME_PATTERN.match(name):
        raise ArtifactError(
            "Project name must start with a letter and contain only "
            "letters, numbers, hyphens, and underscores (max 64 chars)"
        )
    return name


def validate_template(template: str) -> str:
    """Validate template name."""
    if template not in VALID_TEMPLATES:
        raise ArtifactError(
            f"Invalid template: {template}. "
            f"Valid templates: {', '.join(sorted(VALID_TEMPLATES))}"
        )
    return template


class ArtifactStore:
    """Manages artifact storage and retrieval."""
    
    def __init__(self, artifacts_dir: Optional[Path] = None):
        """Initialize artifact store."""
        self._artifacts_dir = Path(artifacts_dir) if artifacts_dir else ARTIFACTS_DIR
        self._artifacts_dir.mkdir(parents=True, exist_ok=True)
    
    @property
    def artifacts_dir(self) -> Path:
        """Get artifacts directory as Path."""
        return self._artifacts_dir
    
    @artifacts_dir.setter
    def artifacts_dir(self, value) -> None:
        """Set artifacts directory, converting to Path if needed."""
        self._artifacts_dir = Path(value) if value else ARTIFACTS_DIR
        self._artifacts_dir.mkdir(parents=True, exist_ok=True)
    
    def _cleanup_old_artifacts(self) -> int:
        """Delete artifacts older than retention period. Returns count deleted."""
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=ARTIFACT_RETENTION_HOURS)
            deleted = 0
            
            for item in self.artifacts_dir.iterdir():
                if item.is_file() and item.suffix == ".zip":
                    # Get file modification time
                    mtime = datetime.fromtimestamp(item.stat().st_mtime, tz=timezone.utc)
                    if mtime < cutoff:
                        item.unlink()
                        deleted += 1
            
            if deleted > 0:
                logger.info(f"cleanup_artifacts deleted={deleted}")
            return deleted
        except Exception as e:
            logger.warning(f"cleanup_artifacts_failed error_type={type(e).__name__}")
            return 0
    
    def run_startup_cleanup(self) -> int:
        """Run cleanup at startup. Safe to call multiple times."""
        return self._cleanup_old_artifacts()
    
    def create_artifact(
        self,
        job_id: str,
        files: dict[str, str],
        project_name: str,
        template: str,
    ) -> ArtifactInfo:
        """
        Create a ZIP artifact from generated files.
        
        Args:
            job_id: Job ID to associate with artifact
            files: Dict of file_path -> file_content
            project_name: Sanitized project name
            template: Template name used
            
        Returns:
            ArtifactInfo with artifact metadata
            
        Raises:
            ArtifactError: If validation fails or limits exceeded
        """
        # Validate inputs
        project_name = validate_project_name(project_name)
        template = validate_template(template)
        
        # Validate file count
        if len(files) > MAX_FILES:
            raise ArtifactError(f"Too many files: {len(files)} > {MAX_FILES}")
        
        # Calculate total uncompressed size and validate paths
        total_size = 0
        for path, content in files.items():
            # Validate path (no traversal)
            normalized = os.path.normpath(path)
            if normalized.startswith("..") or normalized.startswith("/"):
                raise ArtifactError(f"Invalid path: {path}")
            
            # Calculate size
            content_bytes = content.encode("utf-8")
            total_size += len(content_bytes)
        
        if total_size > MAX_UNCOMPRESSED_BYTES:
            raise ArtifactError(
                f"Total size exceeds limit: {total_size} > {MAX_UNCOMPRESSED_BYTES} bytes"
            )
        
        # Opportunistic cleanup
        self._cleanup_old_artifacts()
        
        # Create ZIP in memory first to check size
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for path, content in files.items():
                # Ensure LF line endings
                content = content.replace("\r\n", "\n")
                
                # Add file with project_name as root folder
                full_path = f"{project_name}/{path}"
                zf.writestr(full_path, content.encode("utf-8"))
        
        zip_bytes = zip_buffer.getvalue()
        zip_size = len(zip_bytes)
        
        if zip_size > MAX_ZIP_BYTES:
            raise ArtifactError(
                f"ZIP size exceeds limit: {zip_size} > {MAX_ZIP_BYTES} bytes"
            )
        
        # Calculate SHA256
        sha256 = hashlib.sha256(zip_bytes).hexdigest()
        
        # Save to disk
        artifact_name = f"{project_name}.zip"
        artifact_path = self.artifacts_dir / f"{job_id}_{artifact_name}"
        artifact_path.write_bytes(zip_bytes)
        
        logger.info(
            f"artifact_created job_id={job_id} size={zip_size} files={len(files)}"
        )
        
        return ArtifactInfo(
            job_id=job_id,
            path=artifact_path,
            name=artifact_name,
            size_bytes=zip_size,
            sha256=sha256,
            template=template,
            project_name=project_name,
            created_at=datetime.now(timezone.utc),
        )
    
    def get_artifact(self, job_id: str) -> Optional[tuple[bytes, str]]:
        """
        Get artifact bytes and filename for a job.
        
        Returns:
            Tuple of (zip_bytes, filename) or None if not found
        """
        # Find artifact file
        for item in self.artifacts_dir.iterdir():
            if item.is_file() and item.name.startswith(f"{job_id}_"):
                # Extract original filename (remove job_id prefix)
                filename = item.name[len(job_id) + 1:]
                return item.read_bytes(), filename
        
        return None
    
    def delete_artifact(self, job_id: str) -> bool:
        """Delete artifact for a job. Returns True if deleted."""
        for item in self.artifacts_dir.iterdir():
            if item.is_file() and item.name.startswith(f"{job_id}_"):
                item.unlink()
                logger.info(f"artifact_deleted job_id={job_id}")
                return True
        return False
    
    def verify_artifact(self, job_id: str, expected_sha256: str) -> bool:
        """Verify artifact integrity using SHA256."""
        result = self.get_artifact(job_id)
        if not result:
            return False
        
        zip_bytes, _ = result
        actual_sha256 = hashlib.sha256(zip_bytes).hexdigest()
        return actual_sha256 == expected_sha256


# Global artifact store instance
artifact_store = ArtifactStore()
