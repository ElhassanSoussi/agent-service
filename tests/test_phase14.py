"""
Tests for Phase 14: Project Scaffold + Downloadable Artifacts + Swagger Auth.
"""
import io
import os
import sys
import zipfile
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
    """Create a test client."""
    yield TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def auth_headers():
    """Return valid authentication headers."""
    return {"X-API-Key": "test-api-key"}


# =============================================================================
# Swagger UI / OpenAPI Security Tests
# =============================================================================

class TestSwaggerAuth:
    """Tests for Swagger UI authentication."""
    
    def test_openapi_json_accessible_without_auth(self, client):
        """Test that /openapi.json is accessible without auth."""
        response = client.get("/openapi.json")
        assert response.status_code == 200
        data = response.json()
        assert "openapi" in data
        assert "paths" in data
    
    def test_docs_accessible_without_auth(self, client):
        """Test that /docs is accessible without auth."""
        response = client.get("/docs")
        assert response.status_code == 200
    
    def test_redoc_accessible_without_auth(self, client):
        """Test that /redoc is accessible without auth."""
        response = client.get("/redoc")
        assert response.status_code == 200
    
    def test_openapi_has_security_schemes(self, client):
        """Test that OpenAPI schema includes security schemes."""
        response = client.get("/openapi.json")
        assert response.status_code == 200
        data = response.json()
        
        # Check security schemes exist
        assert "components" in data
        assert "securitySchemes" in data["components"]
        
        schemes = data["components"]["securitySchemes"]
        assert "apiKeyHeader" in schemes
        assert "bearerAuth" in schemes
        
        # Check apiKeyHeader scheme
        assert schemes["apiKeyHeader"]["type"] == "apiKey"
        assert schemes["apiKeyHeader"]["in"] == "header"
        assert schemes["apiKeyHeader"]["name"] == "X-API-Key"
        
        # Check bearerAuth scheme
        assert schemes["bearerAuth"]["type"] == "http"
        assert schemes["bearerAuth"]["scheme"] == "bearer"
    
    def test_protected_endpoints_have_security(self, client):
        """Test that protected endpoints have security requirements."""
        response = client.get("/openapi.json")
        data = response.json()
        
        # Check that /agent/run has security
        agent_run = data["paths"].get("/agent/run", {})
        if "post" in agent_run:
            assert "security" in agent_run["post"]
        
        # Check that /builder/scaffold has security
        scaffold = data["paths"].get("/builder/scaffold", {})
        if "post" in scaffold:
            assert "security" in scaffold["post"]
    
    def test_health_endpoint_no_security(self, client):
        """Test that /health has no security requirements."""
        response = client.get("/openapi.json")
        data = response.json()
        
        health = data["paths"].get("/health", {})
        if "get" in health:
            # Health should not have security or have empty security
            security = health["get"].get("security", [])
            # If security exists, it should allow unauthenticated access
            assert security == [] or "security" not in health["get"]


# =============================================================================
# Scaffold Template Tests
# =============================================================================

class TestScaffoldTemplates:
    """Tests for scaffold templates."""
    
    def test_generate_nextjs_web(self):
        """Test generating Next.js web template."""
        from app.core.scaffold_templates import generate_project
        
        files = generate_project("nextjs_web", "test-app")
        
        assert "package.json" in files
        assert "tsconfig.json" in files
        assert "src/app/page.tsx" in files
        assert "README.md" in files
        
        # Check package.json content
        import json
        pkg = json.loads(files["package.json"])
        assert pkg["name"] == "test-app"
        assert "next" in pkg["dependencies"]
    
    def test_generate_fastapi_api(self):
        """Test generating FastAPI API template."""
        from app.core.scaffold_templates import generate_project
        
        files = generate_project("fastapi_api", "test-api")
        
        assert "requirements.txt" in files
        assert "app/main.py" in files
        assert "tests/test_api.py" in files
        assert "README.md" in files
        
        # Check FastAPI is in requirements
        assert "fastapi" in files["requirements.txt"]
    
    def test_generate_fullstack(self):
        """Test generating fullstack template."""
        from app.core.scaffold_templates import generate_project
        
        files = generate_project("fullstack_nextjs_fastapi", "test-fullstack")
        
        # Should have both web/ and api/ folders
        web_files = [f for f in files.keys() if f.startswith("web/")]
        api_files = [f for f in files.keys() if f.startswith("api/")]
        
        assert len(web_files) > 0
        assert len(api_files) > 0
        assert "README.md" in files
    
    def test_generate_with_docker(self):
        """Test generating template with Docker option."""
        from app.core.scaffold_templates import generate_project
        
        files = generate_project("nextjs_web", "docker-app", use_docker=True)
        
        assert "Dockerfile" in files
        assert ".dockerignore" in files
    
    def test_generate_with_ci(self):
        """Test generating template with CI option."""
        from app.core.scaffold_templates import generate_project
        
        files = generate_project("fastapi_api", "ci-app", include_ci=True)
        
        assert ".github/workflows/ci.yml" in files
    
    def test_invalid_template_rejected(self):
        """Test that invalid template is rejected."""
        from app.core.scaffold_templates import generate_project
        
        with pytest.raises(ValueError) as exc:
            generate_project("invalid_template", "test-app")
        assert "Unknown template" in str(exc.value)


# =============================================================================
# Artifact Store Tests
# =============================================================================

class TestArtifactStore:
    """Tests for artifact store."""
    
    def test_validate_project_name(self):
        """Test project name validation."""
        from app.core.artifact_store import validate_project_name, ArtifactError
        
        # Valid names
        assert validate_project_name("myapp") == "myapp"
        assert validate_project_name("my-app") == "my-app"
        assert validate_project_name("my_app") == "my_app"
        assert validate_project_name("App123") == "App123"
        
        # Invalid names
        with pytest.raises(ArtifactError):
            validate_project_name("123app")  # Starts with number
        
        with pytest.raises(ArtifactError):
            validate_project_name("-app")  # Starts with hyphen
        
        with pytest.raises(ArtifactError):
            validate_project_name("my app")  # Contains space
        
        with pytest.raises(ArtifactError):
            validate_project_name("../etc/passwd")  # Path traversal
    
    def test_validate_template(self):
        """Test template validation."""
        from app.core.artifact_store import validate_template, ArtifactError, VALID_TEMPLATES
        
        for t in VALID_TEMPLATES:
            assert validate_template(t) == t
        
        with pytest.raises(ArtifactError):
            validate_template("invalid")
    
    def test_create_artifact(self):
        """Test creating artifact."""
        from app.core.artifact_store import ArtifactStore
        import tempfile
        
        with tempfile.TemporaryDirectory() as tmpdir:
            store = ArtifactStore(artifacts_dir=tmpdir)
            
            files = {
                "README.md": "# Test",
                "src/main.py": "print('hello')",
            }
            
            info = store.create_artifact(
                job_id="test-job-123",
                files=files,
                project_name="test-app",
                template="nextjs_web",
            )
            
            assert info.job_id == "test-job-123"
            assert info.name == "test-app.zip"
            assert info.size_bytes > 0
            assert len(info.sha256) == 64  # SHA256 hex length
    
    def test_artifact_contains_expected_files(self):
        """Test that created artifact contains expected files."""
        from app.core.artifact_store import ArtifactStore
        import tempfile
        
        with tempfile.TemporaryDirectory() as tmpdir:
            store = ArtifactStore(artifacts_dir=tmpdir)
            
            files = {
                "README.md": "# Test Project",
                "src/index.js": "console.log('hello');",
            }
            
            store.create_artifact(
                job_id="test-job-456",
                files=files,
                project_name="myproject",
                template="nextjs_web",
            )
            
            # Get and verify
            result = store.get_artifact("test-job-456")
            assert result is not None
            
            zip_bytes, filename = result
            assert filename == "myproject.zip"
            
            # Extract and verify contents
            with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
                names = zf.namelist()
                assert "myproject/README.md" in names
                assert "myproject/src/index.js" in names
    
    def test_artifact_file_limit(self):
        """Test that file count limit is enforced."""
        from app.core.artifact_store import ArtifactStore, ArtifactError, MAX_FILES
        import tempfile
        
        with tempfile.TemporaryDirectory() as tmpdir:
            store = ArtifactStore(artifacts_dir=tmpdir)
            
            # Create too many files
            files = {f"file_{i}.txt": "content" for i in range(MAX_FILES + 1)}
            
            with pytest.raises(ArtifactError) as exc:
                store.create_artifact(
                    job_id="test-too-many",
                    files=files,
                    project_name="big-app",
                    template="nextjs_web",
                )
            assert "Too many files" in str(exc.value)
    
    def test_artifact_size_limit(self):
        """Test that total size limit is enforced."""
        from app.core.artifact_store import ArtifactStore, ArtifactError, MAX_UNCOMPRESSED_BYTES
        import tempfile
        
        with tempfile.TemporaryDirectory() as tmpdir:
            store = ArtifactStore(artifacts_dir=tmpdir)
            
            # Create files that exceed total size
            large_content = "x" * (MAX_UNCOMPRESSED_BYTES + 1000)
            files = {"large.txt": large_content}
            
            with pytest.raises(ArtifactError) as exc:
                store.create_artifact(
                    job_id="test-too-large",
                    files=files,
                    project_name="large-app",
                    template="nextjs_web",
                )
            assert "exceeds limit" in str(exc.value)
    
    def test_path_traversal_rejected(self):
        """Test that path traversal attempts are rejected."""
        from app.core.artifact_store import ArtifactStore, ArtifactError
        import tempfile
        
        with tempfile.TemporaryDirectory() as tmpdir:
            store = ArtifactStore(artifacts_dir=tmpdir)
            
            files = {"../etc/passwd": "malicious content"}
            
            with pytest.raises(ArtifactError) as exc:
                store.create_artifact(
                    job_id="test-traversal",
                    files=files,
                    project_name="evil-app",
                    template="nextjs_web",
                )
            assert "Invalid path" in str(exc.value)


# =============================================================================
# Scaffold API Endpoint Tests
# =============================================================================

class TestScaffoldEndpoint:
    """Tests for scaffold API endpoint."""
    
    def test_scaffold_endpoint_returns_202(self, client, auth_headers):
        """Test that scaffold endpoint returns 202."""
        with patch("app.api.builder.run_scaffold_artifact_job", new_callable=AsyncMock):
            response = client.post(
                "/builder/scaffold",
                headers=auth_headers,
                json={
                    "template": "nextjs_web",
                    "project_name": "my-app",
                }
            )
        
        assert response.status_code == 202
        data = response.json()
        assert "job_id" in data
        assert data["status"] == "queued"
        assert data["template"] == "nextjs_web"
        assert data["project_name"] == "my-app"
    
    def test_scaffold_with_options(self, client, auth_headers):
        """Test scaffold with Docker and CI options."""
        with patch("app.api.builder.run_scaffold_artifact_job", new_callable=AsyncMock):
            response = client.post(
                "/builder/scaffold",
                headers=auth_headers,
                json={
                    "template": "fastapi_api",
                    "project_name": "api-server",
                    "options": {
                        "use_docker": True,
                        "include_ci": True,
                    }
                }
            )
        
        assert response.status_code == 202
    
    def test_scaffold_invalid_template_rejected(self, client, auth_headers):
        """Test that invalid template is rejected."""
        response = client.post(
            "/builder/scaffold",
            headers=auth_headers,
            json={
                "template": "invalid_template",
                "project_name": "my-app",
            }
        )
        
        assert response.status_code == 422
    
    def test_scaffold_invalid_project_name_rejected(self, client, auth_headers):
        """Test that invalid project name is rejected."""
        response = client.post(
            "/builder/scaffold",
            headers=auth_headers,
            json={
                "template": "nextjs_web",
                "project_name": "../etc/passwd",
            }
        )
        
        assert response.status_code == 422
    
    def test_scaffold_requires_auth(self, client):
        """Test that scaffold requires authentication."""
        response = client.post(
            "/builder/scaffold",
            json={
                "template": "nextjs_web",
                "project_name": "my-app",
            }
        )
        
        assert response.status_code == 401


# =============================================================================
# Artifact Download Tests
# =============================================================================

class TestArtifactDownload:
    """Tests for artifact download endpoint."""
    
    def test_artifact_download_not_found(self, client, auth_headers):
        """Test download returns 404 for non-existent job."""
        response = client.get(
            "/builder/artifact/non-existent-job",
            headers=auth_headers,
        )
        
        assert response.status_code == 404
    
    def test_artifact_download_requires_auth(self, client):
        """Test that artifact download requires auth."""
        response = client.get("/builder/artifact/some-job-id")
        
        assert response.status_code == 401
    
    def test_artifact_info_not_found(self, client, auth_headers):
        """Test artifact info returns 404 for non-existent job."""
        response = client.get(
            "/builder/artifact/non-existent-job/info",
            headers=auth_headers,
        )
        
        assert response.status_code == 404


# =============================================================================
# Integration Tests
# =============================================================================

class TestScaffoldIntegration:
    """Integration tests for scaffold workflow."""
    
    @pytest.mark.asyncio
    async def test_scaffold_job_creates_artifact(self):
        """Test that scaffold job creates valid artifact."""
        from app.api.builder import run_scaffold_artifact_job
        from app.core.jobs import job_store, JobStatus
        from app.core.artifact_store import artifact_store
        from app.schemas.agent import JobMode
        import tempfile
        
        # Use temp directory for artifacts
        original_dir = artifact_store.artifacts_dir
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                artifact_store.artifacts_dir = tmpdir
                
                # Create job
                job = job_store.create_job(
                    mode=JobMode.BUILDER,
                    prompt="scaffold test",
                    input_data={
                        "template": "fastapi_api",
                        "project_name": "test-api",
                        "options": {},
                    },
                    tenant_id="test",
                )
                
                # Run scaffold
                await run_scaffold_artifact_job(job.id)
                
                # Verify job completed
                updated_job = job_store.get(job.id)
                assert updated_job.status == JobStatus.DONE
                assert updated_job.artifact_name == "test-api.zip"
                assert updated_job.artifact_size_bytes > 0
                assert updated_job.builder_template == "fastapi_api"
                
                # Verify artifact exists and is valid ZIP
                result = artifact_store.get_artifact(job.id)
                assert result is not None
                
                zip_bytes, filename = result
                with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
                    names = zf.namelist()
                    assert any("requirements.txt" in n for n in names)
                    assert any("main.py" in n for n in names)
                
                # Cleanup
                job_store.delete(job.id)
        finally:
            artifact_store.artifacts_dir = original_dir


# =============================================================================
# Constants Tests
# =============================================================================

class TestScaffoldConstants:
    """Tests for scaffold constants."""
    
    def test_max_files_limit(self):
        """Test MAX_FILES constant."""
        from app.core.artifact_store import MAX_FILES
        assert MAX_FILES == 300
    
    def test_max_uncompressed_bytes(self):
        """Test MAX_UNCOMPRESSED_BYTES constant (8MB)."""
        from app.core.artifact_store import MAX_UNCOMPRESSED_BYTES
        assert MAX_UNCOMPRESSED_BYTES == 8 * 1024 * 1024
    
    def test_max_zip_bytes(self):
        """Test MAX_ZIP_BYTES constant (5MB)."""
        from app.core.artifact_store import MAX_ZIP_BYTES
        assert MAX_ZIP_BYTES == 5 * 1024 * 1024
    
    def test_valid_templates(self):
        """Test VALID_TEMPLATES constant."""
        from app.core.artifact_store import VALID_TEMPLATES
        assert "nextjs_web" in VALID_TEMPLATES
        assert "fastapi_api" in VALID_TEMPLATES
        assert "fullstack_nextjs_fastapi" in VALID_TEMPLATES
