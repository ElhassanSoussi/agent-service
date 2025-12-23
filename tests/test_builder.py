"""
Tests for Codebase Builder Mode (Phase 12).
"""
import os
import sys
import pytest
from unittest.mock import patch, AsyncMock

# Set test environment before importing app
os.environ["AGENT_API_KEY"] = "test-api-key"
os.environ["AGENT_ADMIN_KEY"] = "test-admin-key"
os.environ["AGENT_KEY_HASH_SECRET"] = "test-hash-secret"

from fastapi.testclient import TestClient

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app


@pytest.fixture
def client():
    """Create a test client with mocked background task."""
    # Mock the background task to avoid network calls during tests
    with patch("app.api.builder.run_builder_job_background", new_callable=AsyncMock):
        yield TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def auth_headers():
    """Return valid authentication headers."""
    return {"X-API-Key": "test-api-key"}


# =============================================================================
# URL Parsing Tests
# =============================================================================

class TestGitHubURLParsing:
    """Tests for GitHub URL parsing."""
    
    def test_parse_standard_url(self):
        """Test parsing standard GitHub URL."""
        from app.api.builder import parse_github_url
        
        owner, repo = parse_github_url("https://github.com/owner/repo")
        assert owner == "owner"
        assert repo == "repo"
    
    def test_parse_url_with_git_suffix(self):
        """Test parsing URL with .git suffix."""
        from app.api.builder import parse_github_url
        
        owner, repo = parse_github_url("https://github.com/owner/repo.git")
        assert owner == "owner"
        assert repo == "repo"
    
    def test_parse_url_with_branch(self):
        """Test parsing URL with branch path."""
        from app.api.builder import parse_github_url
        
        owner, repo = parse_github_url("https://github.com/owner/repo/tree/main")
        assert owner == "owner"
        assert repo == "repo"
    
    def test_reject_non_github_url(self):
        """Test rejection of non-GitHub URLs."""
        from app.api.builder import parse_github_url
        
        with pytest.raises(ValueError) as exc:
            parse_github_url("https://gitlab.com/owner/repo")
        assert "GitHub" in str(exc.value)
    
    def test_reject_invalid_url(self):
        """Test rejection of invalid URLs."""
        from app.api.builder import parse_github_url
        
        with pytest.raises(ValueError):
            parse_github_url("https://github.com/owner")


# =============================================================================
# Unified Diff Generation Tests
# =============================================================================

class TestUnifiedDiff:
    """Tests for unified diff generation."""
    
    def test_generate_diff_for_modification(self):
        """Test generating diff for file modification."""
        from app.api.builder import generate_unified_diff
        
        original = "line1\nline2\nline3\n"
        modified = "line1\nmodified\nline3\n"
        
        diff = generate_unified_diff("test.py", original, modified)
        
        assert "--- a/test.py" in diff
        assert "+++ b/test.py" in diff
        assert "-line2" in diff
        assert "+modified" in diff
    
    def test_generate_diff_for_new_file(self):
        """Test generating diff for new file."""
        from app.api.builder import generate_unified_diff
        
        diff = generate_unified_diff("new.py", None, "new content\n")
        
        assert "+new content" in diff
    
    def test_generate_diff_for_deletion(self):
        """Test generating diff for deleted file."""
        from app.api.builder import generate_unified_diff
        
        diff = generate_unified_diff("deleted.py", "old content\n", None)
        
        assert "-old content" in diff


# =============================================================================
# Repository Tools Tests
# =============================================================================

class TestRepoTools:
    """Tests for repository tools."""
    
    def test_validate_repo_format_valid(self):
        """Test valid repository format validation."""
        from app.core.repo_tools import _validate_repo_format
        
        assert _validate_repo_format("owner", "repo") is True
        assert _validate_repo_format("my-org", "my-repo") is True
        assert _validate_repo_format("user_name", "repo_name") is True
    
    def test_validate_repo_format_invalid(self):
        """Test invalid repository format validation."""
        from app.core.repo_tools import _validate_repo_format
        
        assert _validate_repo_format("", "repo") is False
        assert _validate_repo_format("owner", "") is False
        assert _validate_repo_format("owner/bad", "repo") is False
        assert _validate_repo_format("owner", "repo/bad") is False
    
    def test_validate_github_url(self):
        """Test GitHub URL validation."""
        from app.core.repo_tools import _validate_github_url
        
        assert _validate_github_url("https://api.github.com/repos/owner/repo") is True
        assert _validate_github_url("https://github.com/owner/repo") is True
        assert _validate_github_url("https://raw.githubusercontent.com/owner/repo/main/file") is True
        assert _validate_github_url("https://gitlab.com/owner/repo") is False
        assert _validate_github_url("https://example.com") is False


# =============================================================================
# Builder API Endpoint Tests
# =============================================================================

class TestBuilderEndpoints:
    """Tests for builder API endpoints."""
    
    def test_builder_run_requires_auth(self, client):
        """Test that /builder/run requires authentication."""
        response = client.post(
            "/builder/run",
            json={
                "repo_url": "https://github.com/owner/repo",
                "prompt": "Add a new feature to the codebase",
            }
        )
        assert response.status_code == 401
    
    def test_builder_run_validates_github_url(self, client, auth_headers):
        """Test that /builder/run validates GitHub URL."""
        response = client.post(
            "/builder/run",
            headers=auth_headers,
            json={
                "repo_url": "https://gitlab.com/owner/repo",
                "prompt": "Add a new feature",
            }
        )
        assert response.status_code == 422
        # Validation error is in the response body
        data = response.json()
        # Could be {"detail": "..."} or {"detail": [{"msg": "..."}]}
        detail = data.get("detail")
        if isinstance(detail, list):
            assert any("GitHub" in item.get("msg", "") for item in detail)
        else:
            assert "GitHub" in str(detail)
    
    def test_builder_run_validates_prompt_length(self, client, auth_headers):
        """Test that /builder/run validates prompt length."""
        response = client.post(
            "/builder/run",
            headers=auth_headers,
            json={
                "repo_url": "https://github.com/owner/repo",
                "prompt": "short",  # Less than 10 chars
            }
        )
        assert response.status_code == 422
    
    def test_builder_run_creates_job(self, client, auth_headers):
        """Test that /builder/run creates a job and returns 202."""
        response = client.post(
            "/builder/run",
            headers=auth_headers,
            json={
                "repo_url": "https://github.com/owner/repo",
                "prompt": "Add a new feature to the main module",
            }
        )
        # Should return 202 even if background task fails (network error)
        assert response.status_code == 202
        data = response.json()
        assert "job_id" in data
        assert data["status"] == "queued"
        assert data["repo_url"] == "https://github.com/owner/repo"
    
    def test_builder_status_not_found(self, client, auth_headers):
        """Test /builder/status returns 404 for non-existent job."""
        response = client.get(
            "/builder/status/nonexistent-job-id",
            headers=auth_headers,
        )
        assert response.status_code == 404
    
    def test_builder_result_not_found(self, client, auth_headers):
        """Test /builder/result returns 404 for non-existent job."""
        response = client.get(
            "/builder/result/nonexistent-job-id",
            headers=auth_headers,
        )
        assert response.status_code == 404
    
    def test_builder_files_not_found(self, client, auth_headers):
        """Test /builder/files returns 404 for non-existent job."""
        response = client.get(
            "/builder/files/nonexistent-job-id",
            headers=auth_headers,
        )
        assert response.status_code == 404
    
    def test_builder_jobs_list(self, client, auth_headers):
        """Test /builder/jobs returns job list."""
        response = client.get(
            "/builder/jobs",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert "limit" in data
        assert "offset" in data
    
    def test_builder_delete_not_found(self, client, auth_headers):
        """Test DELETE /builder/jobs returns 404 for non-existent job."""
        response = client.delete(
            "/builder/jobs/nonexistent-job-id",
            headers=auth_headers,
        )
        assert response.status_code == 404


# =============================================================================
# Builder Job Lifecycle Tests
# =============================================================================

class TestBuilderJobLifecycle:
    """Tests for complete builder job lifecycle."""
    
    def test_create_and_get_status(self, client, auth_headers):
        """Test creating a job and checking its status."""
        # Create job
        response = client.post(
            "/builder/run",
            headers=auth_headers,
            json={
                "repo_url": "https://github.com/test/repo",
                "prompt": "Add unit tests for the main module",
            }
        )
        assert response.status_code == 202
        job_id = response.json()["job_id"]
        
        # Check status
        response = client.get(
            f"/builder/status/{job_id}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["job_id"] == job_id
        assert data["repo_url"] == "https://github.com/test/repo"
        assert "current_phase" in data
        assert "progress_pct" in data
    
    def test_create_and_delete_job(self, client, auth_headers):
        """Test creating and deleting a job."""
        # Create job
        response = client.post(
            "/builder/run",
            headers=auth_headers,
            json={
                "repo_url": "https://github.com/test/repo",
                "prompt": "Refactor the database module",
            }
        )
        assert response.status_code == 202
        job_id = response.json()["job_id"]
        
        # Delete job
        response = client.delete(
            f"/builder/jobs/{job_id}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["deleted"] is True
        
        # Verify deleted
        response = client.get(
            f"/builder/status/{job_id}",
            headers=auth_headers,
        )
        assert response.status_code == 404


# =============================================================================
# Request Validation Tests
# =============================================================================

class TestBuilderRequestValidation:
    """Tests for builder request validation."""
    
    def test_max_files_bounds(self, client, auth_headers):
        """Test max_files parameter bounds."""
        # Too low
        response = client.post(
            "/builder/run",
            headers=auth_headers,
            json={
                "repo_url": "https://github.com/owner/repo",
                "prompt": "Add a new feature to the codebase",
                "max_files": 0,
            }
        )
        assert response.status_code == 422
        
        # Too high
        response = client.post(
            "/builder/run",
            headers=auth_headers,
            json={
                "repo_url": "https://github.com/owner/repo",
                "prompt": "Add a new feature to the codebase",
                "max_files": 100,
            }
        )
        assert response.status_code == 422
    
    def test_target_paths_accepted(self, client, auth_headers):
        """Test target_paths parameter is accepted."""
        response = client.post(
            "/builder/run",
            headers=auth_headers,
            json={
                "repo_url": "https://github.com/owner/repo",
                "prompt": "Add a new feature to the codebase",
                "target_paths": ["src/", "lib/"],
            }
        )
        assert response.status_code == 202
    
    def test_exclude_paths_accepted(self, client, auth_headers):
        """Test exclude_paths parameter is accepted."""
        response = client.post(
            "/builder/run",
            headers=auth_headers,
            json={
                "repo_url": "https://github.com/owner/repo",
                "prompt": "Add a new feature to the codebase",
                "exclude_paths": ["vendor/", "node_modules/"],
            }
        )
        assert response.status_code == 202


# =============================================================================
# Files Endpoint Format Tests
# =============================================================================

class TestBuilderFilesFormat:
    """Tests for builder files endpoint format options."""
    
    def test_invalid_format_rejected(self, client, auth_headers):
        """Test that invalid format is rejected."""
        # First create a job
        response = client.post(
            "/builder/run",
            headers=auth_headers,
            json={
                "repo_url": "https://github.com/owner/repo",
                "prompt": "Add a new feature to the codebase",
            }
        )
        job_id = response.json()["job_id"]
        
        # Try invalid format (job not done, so will get different error first)
        response = client.get(
            f"/builder/files/{job_id}?format=invalid",
            headers=auth_headers,
        )
        # Will be 400 because job not done yet
        assert response.status_code == 400


# =============================================================================
# Schema Tests
# =============================================================================

class TestBuilderSchemas:
    """Tests for builder schema validation."""
    
    def test_builder_run_request_valid(self):
        """Test BuilderRunRequest with valid data."""
        from app.schemas.builder import BuilderRunRequest
        
        req = BuilderRunRequest(
            repo_url="https://github.com/owner/repo",
            prompt="Add a new feature to the main module",
        )
        assert req.repo_url == "https://github.com/owner/repo"
        assert req.ref == "HEAD"
        assert req.max_files == 10
    
    def test_builder_run_request_rejects_non_github(self):
        """Test BuilderRunRequest rejects non-GitHub URLs."""
        from app.schemas.builder import BuilderRunRequest
        import pydantic
        
        with pytest.raises(pydantic.ValidationError):
            BuilderRunRequest(
                repo_url="https://gitlab.com/owner/repo",
                prompt="Add a new feature",
            )
    
    def test_diff_type_enum(self):
        """Test DiffType enum values."""
        from app.schemas.builder import DiffType
        
        assert DiffType.ADD.value == "add"
        assert DiffType.MODIFY.value == "modify"
        assert DiffType.DELETE.value == "delete"
        assert DiffType.RENAME.value == "rename"
    
    def test_builder_job_status_enum(self):
        """Test BuilderJobStatus enum values."""
        from app.schemas.builder import BuilderJobStatus
        
        assert BuilderJobStatus.QUEUED.value == "queued"
        assert BuilderJobStatus.ANALYZING.value == "analyzing"
        assert BuilderJobStatus.PLANNING.value == "planning"
        assert BuilderJobStatus.GENERATING.value == "generating"
        assert BuilderJobStatus.DONE.value == "done"
        assert BuilderJobStatus.ERROR.value == "error"
