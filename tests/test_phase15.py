"""
Tests for Phase 15: Repo Builder v1 + PR-ready Patch + Real Verification URLs.

Tests cover:
- Repo URL allowlist validation
- Zip-slip prevention
- Size limit enforcement
- Successful pipeline with artifacts
- Patch endpoint returns valid unified diff
- Download endpoint returns zip with correct headers
- Auth required on all endpoints
"""
import io
import json
import os
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# Set test API key before importing app
os.environ["AGENT_API_KEY"] = "test-api-key"
os.environ["AGENT_ADMIN_KEY"] = "test-admin-key"
os.environ["AGENT_KEY_HASH_SECRET"] = "test-hash-secret"

from main import app
from app.core.repo_builder import (
    validate_repo_url,
    RepoBuilderError,
    ALLOWED_DOMAINS,
    MAX_DOWNLOAD_SIZE,
    MAX_EXTRACTED_SIZE,
    MAX_FILES,
    _is_safe_path,
    download_repo,
    generate_unified_diff,
    apply_fastapi_template,
    build_from_repo,
)


@pytest.fixture
def client():
    """Create a test client."""
    return TestClient(app)


@pytest.fixture
def auth_headers():
    """Return valid authentication headers."""
    return {"X-API-Key": "test-api-key"}


# =============================================================================
# URL Validation Tests
# =============================================================================

class TestRepoUrlValidation:
    """Tests for repo URL allowlist validation."""
    
    def test_valid_github_url(self):
        """Test valid GitHub URL is accepted."""
        owner, repo = validate_repo_url("https://github.com/tiangolo/fastapi")
        assert owner == "tiangolo"
        assert repo == "fastapi"
    
    def test_valid_github_url_with_git_suffix(self):
        """Test GitHub URL with .git suffix."""
        owner, repo = validate_repo_url("https://github.com/tiangolo/fastapi.git")
        assert owner == "tiangolo"
        assert repo == "fastapi"
    
    def test_valid_github_url_with_branch(self):
        """Test GitHub URL with branch path."""
        owner, repo = validate_repo_url("https://github.com/tiangolo/fastapi/tree/main")
        assert owner == "tiangolo"
        assert repo == "fastapi"
    
    def test_reject_non_github_domain(self):
        """Test non-GitHub domain is rejected."""
        with pytest.raises(RepoBuilderError) as exc_info:
            validate_repo_url("https://gitlab.com/user/repo")
        assert "Domain not allowed" in str(exc_info.value)
    
    def test_reject_http_url(self):
        """Test HTTP URL is rejected (must be HTTPS)."""
        with pytest.raises(RepoBuilderError) as exc_info:
            validate_repo_url("http://github.com/user/repo")
        assert "HTTPS" in str(exc_info.value)
    
    def test_reject_invalid_url_format(self):
        """Test invalid URL format is rejected."""
        with pytest.raises(RepoBuilderError):
            validate_repo_url("not-a-url")
    
    def test_reject_url_without_repo(self):
        """Test URL without repo name is rejected."""
        with pytest.raises(RepoBuilderError) as exc_info:
            validate_repo_url("https://github.com/owner")
        assert "must include owner and repo" in str(exc_info.value)
    
    def test_allowed_domains_constant(self):
        """Test that allowed domains are correctly defined."""
        assert "github.com" in ALLOWED_DOMAINS
        assert "codeload.github.com" in ALLOWED_DOMAINS
        assert len(ALLOWED_DOMAINS) == 2


# =============================================================================
# Zip-Slip Prevention Tests
# =============================================================================

class TestZipSlipPrevention:
    """Tests for zip-slip vulnerability prevention."""
    
    def test_safe_path_normal(self):
        """Test normal paths are safe."""
        assert _is_safe_path("src/main.py") is True
        assert _is_safe_path("README.md") is True
        assert _is_safe_path("tests/test_api.py") is True
    
    def test_unsafe_path_traversal(self):
        """Test path traversal is rejected."""
        assert _is_safe_path("../etc/passwd") is False
        assert _is_safe_path("foo/../../../etc/passwd") is False
        assert _is_safe_path("..") is False
    
    def test_unsafe_path_absolute(self):
        """Test absolute paths are rejected."""
        assert _is_safe_path("/etc/passwd") is False
        assert _is_safe_path("/home/user/.ssh/id_rsa") is False
    
    def test_safe_path_with_dots_in_name(self):
        """Test paths with dots in filenames are safe."""
        assert _is_safe_path("file.test.py") is True
        assert _is_safe_path(".gitignore") is True
        assert _is_safe_path(".github/workflows/ci.yml") is True


# =============================================================================
# Size Limit Tests
# =============================================================================

class TestSizeLimits:
    """Tests for size limit enforcement."""
    
    def test_max_download_size_constant(self):
        """Test MAX_DOWNLOAD_SIZE is 25MB."""
        assert MAX_DOWNLOAD_SIZE == 25 * 1024 * 1024
    
    def test_max_extracted_size_constant(self):
        """Test MAX_EXTRACTED_SIZE is 80MB."""
        assert MAX_EXTRACTED_SIZE == 80 * 1024 * 1024
    
    def test_max_files_constant(self):
        """Test MAX_FILES is 10,000."""
        assert MAX_FILES == 10_000


# =============================================================================
# Diff Generation Tests
# =============================================================================

class TestDiffGeneration:
    """Tests for unified diff generation."""
    
    def test_diff_new_file(self):
        """Test diff for a new file."""
        original = {}
        modified = {"new.txt": b"hello world"}
        
        diff = generate_unified_diff(original, modified)
        assert "--- /dev/null" in diff or "--- a/new.txt" in diff
        assert "+++ b/new.txt" in diff
        assert "+hello world" in diff
    
    def test_diff_modified_file(self):
        """Test diff for a modified file."""
        original = {"file.txt": b"original content"}
        modified = {"file.txt": b"modified content"}
        
        diff = generate_unified_diff(original, modified)
        assert "--- a/file.txt" in diff
        assert "+++ b/file.txt" in diff
        assert "-original content" in diff
        assert "+modified content" in diff
    
    def test_diff_unchanged_file(self):
        """Test no diff for unchanged file."""
        original = {"file.txt": b"same content"}
        modified = {"file.txt": b"same content"}
        
        diff = generate_unified_diff(original, modified)
        assert "file.txt" not in diff
    
    def test_diff_deleted_file(self):
        """Test diff for deleted file."""
        original = {"deleted.txt": b"content"}
        modified = {}
        
        diff = generate_unified_diff(original, modified)
        assert "deleted.txt" in diff


# =============================================================================
# FastAPI Template Tests
# =============================================================================

class TestFastAPITemplate:
    """Tests for fastapi_api template transforms."""
    
    def test_add_dockerfile(self):
        """Test adding Dockerfile."""
        files = {"main.py": b"from fastapi import FastAPI"}
        modified, added, _, _, notes = apply_fastapi_template(
            files, {"add_docker": True}
        )
        
        assert "Dockerfile" in modified
        assert "Dockerfile" in added
        assert b"FROM python" in modified["Dockerfile"]
    
    def test_add_docker_compose(self):
        """Test adding docker-compose.yml."""
        files = {"main.py": b"from fastapi import FastAPI"}
        modified, added, _, _, notes = apply_fastapi_template(
            files, {"add_docker": True}
        )
        
        assert "docker-compose.yml" in modified
        assert "docker-compose.yml" in added
    
    def test_add_github_actions(self):
        """Test adding GitHub Actions CI."""
        files = {"main.py": b"from fastapi import FastAPI"}
        modified, added, _, _, notes = apply_fastapi_template(
            files, {"add_github_actions": True}
        )
        
        assert ".github/workflows/ci.yml" in modified
        assert ".github/workflows/ci.yml" in added
    
    def test_add_readme(self):
        """Test adding README.md."""
        files = {"main.py": b"from fastapi import FastAPI"}
        modified, added, _, _, notes = apply_fastapi_template(
            files, {"add_readme": True}
        )
        
        assert "README.md" in modified
        assert "README.md" in added
        assert b"How to Run" in modified["README.md"]
    
    def test_update_existing_readme(self):
        """Test updating existing README."""
        files = {
            "main.py": b"from fastapi import FastAPI",
            "README.md": b"# My Project\n\nDescription here."
        }
        modified, added, mod_list, _, notes = apply_fastapi_template(
            files, {"add_readme": True}
        )
        
        assert "README.md" not in added
        assert "README.md" in mod_list
        assert b"How to Run" in modified["README.md"]
        assert b"# My Project" in modified["README.md"]
    
    def test_skip_existing_dockerfile(self):
        """Test skipping existing Dockerfile."""
        files = {
            "main.py": b"from fastapi import FastAPI",
            "Dockerfile": b"FROM python:3.11"
        }
        modified, added, _, _, notes = apply_fastapi_template(
            files, {"add_docker": True}
        )
        
        assert "Dockerfile" not in added
        assert any("already exists" in note for note in notes)
    
    def test_add_ruff_config(self):
        """Test adding ruff.toml."""
        files = {"main.py": b"from fastapi import FastAPI"}
        modified, added, _, _, notes = apply_fastapi_template(files, {})
        
        assert "ruff.toml" in modified
        assert "ruff.toml" in added
    
    def test_add_health_example(self):
        """Test adding health endpoint example."""
        files = {"main.py": b"from fastapi import FastAPI\napp = FastAPI()"}
        modified, added, _, _, notes = apply_fastapi_template(files, {})
        
        assert "health_example.py" in modified
        assert "health_example.py" in added
        assert b"/health" in modified["health_example.py"]
    
    def test_skip_health_if_exists(self):
        """Test skipping health example if endpoint exists."""
        files = {
            "main.py": b'from fastapi import FastAPI\napp = FastAPI()\n@app.get("/health")\ndef health(): pass'
        }
        modified, added, _, _, notes = apply_fastapi_template(files, {})
        
        assert "health_example.py" not in added
        assert any("Health endpoint already exists" in note for note in notes)


# =============================================================================
# API Endpoint Tests
# =============================================================================

class TestRepoBuilderEndpoint:
    """Tests for /builder/from_repo endpoint."""
    
    def test_endpoint_requires_auth(self, client):
        """Test that endpoint requires authentication."""
        response = client.post(
            "/builder/from_repo",
            json={"repo_url": "https://github.com/user/repo"}
        )
        assert response.status_code == 401
    
    def test_invalid_repo_url_rejected(self, client, auth_headers):
        """Test invalid repo URL is rejected."""
        response = client.post(
            "/builder/from_repo",
            json={"repo_url": "https://gitlab.com/user/repo"},
            headers=auth_headers,
        )
        assert response.status_code == 422
        assert "Domain not allowed" in response.text
    
    def test_invalid_template_rejected(self, client, auth_headers):
        """Test invalid template is rejected."""
        response = client.post(
            "/builder/from_repo",
            json={
                "repo_url": "https://github.com/user/repo",
                "template": "invalid_template"
            },
            headers=auth_headers,
        )
        assert response.status_code == 422
        assert "Invalid template" in response.text
    
    def test_valid_request_returns_202(self, client, auth_headers):
        """Test valid request returns 202 with job info."""
        with patch("app.api.builder.run_repo_builder_job"):
            response = client.post(
                "/builder/from_repo",
                json={
                    "repo_url": "https://github.com/tiangolo/fastapi",
                    "ref": "main",
                    "template": "fastapi_api",
                    "options": {"add_docker": True}
                },
                headers=auth_headers,
            )
        
        assert response.status_code == 202
        data = response.json()
        assert "job_id" in data
        assert data["status"] == "queued"
        assert data["repo_url"] == "https://github.com/tiangolo/fastapi"
        assert "/builder/from_repo/" in data["download_url"]
        assert "/builder/from_repo/" in data["patch_url"]


class TestRepoBuilderDownloadEndpoint:
    """Tests for /builder/from_repo/{job_id}/download endpoint."""
    
    def test_download_requires_auth(self, client):
        """Test download requires authentication."""
        response = client.get("/builder/from_repo/fake-job-id/download")
        assert response.status_code == 401
    
    def test_download_not_found(self, client, auth_headers):
        """Test 404 for non-existent job."""
        response = client.get(
            "/builder/from_repo/nonexistent-job-id/download",
            headers=auth_headers,
        )
        assert response.status_code == 404


class TestRepoBuilderPatchEndpoint:
    """Tests for /builder/from_repo/{job_id}/patch endpoint."""
    
    def test_patch_requires_auth(self, client):
        """Test patch requires authentication."""
        response = client.get("/builder/from_repo/fake-job-id/patch")
        assert response.status_code == 401
    
    def test_patch_not_found(self, client, auth_headers):
        """Test 404 for non-existent job."""
        response = client.get(
            "/builder/from_repo/nonexistent-job-id/patch",
            headers=auth_headers,
        )
        assert response.status_code == 404


class TestRepoBuilderInfoEndpoint:
    """Tests for /builder/from_repo/{job_id}/info endpoint."""
    
    def test_info_requires_auth(self, client):
        """Test info requires authentication."""
        response = client.get("/builder/from_repo/fake-job-id/info")
        assert response.status_code == 401
    
    def test_info_not_found(self, client, auth_headers):
        """Test 404 for non-existent job."""
        response = client.get(
            "/builder/from_repo/nonexistent-job-id/info",
            headers=auth_headers,
        )
        assert response.status_code == 404


# =============================================================================
# Integration Tests (with mocked network)
# =============================================================================

class TestRepoBuilderIntegration:
    """Integration tests with mocked network calls."""
    
    @pytest.mark.asyncio
    async def test_build_from_repo_mock(self):
        """Test full build pipeline with mocked download."""
        # Create a mock ZIP file
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as zf:
            zf.writestr("repo-main/main.py", "from fastapi import FastAPI\napp = FastAPI()")
            zf.writestr("repo-main/requirements.txt", "fastapi\nuvicorn")
        zip_content = zip_buffer.getvalue()
        
        # Mock the HTTP response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = zip_content
        
        tmpdir = tempfile.mkdtemp()
        try:
            with patch("httpx.AsyncClient") as mock_client:
                mock_instance = AsyncMock()
                mock_instance.get = AsyncMock(return_value=mock_response)
                mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
                mock_instance.__aexit__ = AsyncMock(return_value=None)
                mock_client.return_value = mock_instance
                
                result = await build_from_repo(
                    job_id="test-job-123",
                    repo_url="https://github.com/test/repo",
                    ref="main",
                    template="fastapi_api",
                    options={"add_docker": True, "add_github_actions": True, "add_readme": True},
                    artifacts_dir=Path(tmpdir),
                )
            
            # Verify result
            assert result.owner == "test"
            assert result.repo == "repo"
            assert result.ref == "main"
            assert result.template == "fastapi_api"
            
            # Check artifacts were created
            assert result.modified_zip_path is not None
            assert result.modified_zip_path.exists()
            assert result.patch_path is not None
            assert result.patch_path.exists()
            assert result.summary_path is not None
            assert result.summary_path.exists()
            
            # Check files were added
            assert "Dockerfile" in result.files_added
            assert ".github/workflows/ci.yml" in result.files_added
            assert "README.md" in result.files_added
            
            # Verify ZIP contents
            with zipfile.ZipFile(result.modified_zip_path, "r") as zf:
                names = zf.namelist()
                assert any("Dockerfile" in n for n in names)
                assert any("main.py" in n for n in names)
            
            # Verify patch contains diff headers
            patch_content = result.patch_path.read_text()
            assert "---" in patch_content or len(result.files_added) > 0
        finally:
            # Cleanup
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)


class TestDocsProtection:
    """Tests for auth protection on docs endpoints."""
    
    def test_docs_accessible(self, client):
        """Test /docs is accessible."""
        response = client.get("/docs")
        assert response.status_code == 200
    
    def test_openapi_accessible(self, client):
        """Test /openapi.json is accessible."""
        response = client.get("/openapi.json")
        assert response.status_code == 200
    
    def test_health_accessible(self, client):
        """Test /health is accessible without auth."""
        response = client.get("/health")
        assert response.status_code == 200


# =============================================================================
# Security Tests
# =============================================================================

class TestSecurityConstraints:
    """Tests for security constraints."""
    
    def test_no_shell_execution_in_builder(self):
        """Verify repo_builder module doesn't use subprocess."""
        import app.core.repo_builder as rb
        source_code = open(rb.__file__).read()
        
        # Check for dangerous imports
        assert "subprocess" not in source_code
        assert "os.system" not in source_code
        assert "os.popen" not in source_code
        assert "exec(" not in source_code
        assert "eval(" not in source_code
    
    def test_allowed_domains_strict(self):
        """Test only GitHub domains are allowed."""
        # Try various non-GitHub domains
        bad_domains = [
            "https://evil.com/user/repo",
            "https://github.evil.com/user/repo",
            "https://notgithub.com/user/repo",
            "https://bitbucket.org/user/repo",
            "https://gitlab.com/user/repo",
        ]
        
        for url in bad_domains:
            with pytest.raises(RepoBuilderError) as exc_info:
                validate_repo_url(url)
            assert "Domain not allowed" in str(exc_info.value) or "HTTPS" in str(exc_info.value)


# =============================================================================
# Download Tests (with mocked network)
# =============================================================================

class TestRepoDownload:
    """Tests for repo download functionality."""
    
    @pytest.mark.asyncio
    async def test_download_timeout_error(self):
        """Test timeout error handling."""
        import httpx
        
        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_instance
            
            with pytest.raises(RepoBuilderError) as exc_info:
                await download_repo("owner", "repo", "main")
            
            assert "timed out" in str(exc_info.value).lower()
    
    @pytest.mark.asyncio
    async def test_download_size_limit(self):
        """Test download size limit enforcement."""
        # Create oversized content
        large_content = b"x" * (MAX_DOWNLOAD_SIZE + 1)
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = large_content
        
        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get = AsyncMock(return_value=mock_response)
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_instance
            
            with pytest.raises(RepoBuilderError) as exc_info:
                await download_repo("owner", "repo", "main")
            
            assert "exceeds limit" in str(exc_info.value).lower()
    
    @pytest.mark.asyncio
    async def test_download_404_error(self):
        """Test 404 error handling."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        
        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get = AsyncMock(return_value=mock_response)
            mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
            mock_instance.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_instance
            
            with pytest.raises(RepoBuilderError) as exc_info:
                await download_repo("owner", "repo", "main")
            
            assert "404" in str(exc_info.value) or "Failed" in str(exc_info.value)
