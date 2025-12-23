"""
Tests for Phase 13: Scaffolder + Issue Fixer Mode.
"""
import os
import sys
import pytest
from unittest.mock import patch, AsyncMock, MagicMock

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
    with patch("app.api.builder.run_builder_job_background", new_callable=AsyncMock):
        yield TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def auth_headers():
    """Return valid authentication headers."""
    return {"X-API-Key": "test-api-key"}


# =============================================================================
# Scaffold Mode Tests
# =============================================================================

class TestScaffoldMode:
    """Tests for scaffold mode."""
    
    def test_scaffold_mode_returns_job_id(self, client, auth_headers):
        """Test that scaffold mode returns a job_id."""
        response = client.post(
            "/builder/run",
            headers=auth_headers,
            json={
                "mode": "scaffold",
                "template": "nextjs",
                "project": {
                    "name": "my-app",
                    "description": "A test application",
                },
            }
        )
        assert response.status_code == 202
        data = response.json()
        assert "job_id" in data
        assert data["status"] == "queued"
        assert data["mode"] == "scaffold"
        assert data["template"] == "nextjs"
    
    def test_scaffold_mode_requires_template(self, client, auth_headers):
        """Test that scaffold mode requires template."""
        response = client.post(
            "/builder/run",
            headers=auth_headers,
            json={
                "mode": "scaffold",
                "project": {"name": "my-app"},
            }
        )
        assert response.status_code == 422
    
    def test_scaffold_mode_requires_project_name(self, client, auth_headers):
        """Test that scaffold mode requires project.name."""
        response = client.post(
            "/builder/run",
            headers=auth_headers,
            json={
                "mode": "scaffold",
                "template": "nextjs",
                "project": {"description": "No name"},
            }
        )
        assert response.status_code == 422
    
    def test_scaffold_mode_accepts_fastapi_template(self, client, auth_headers):
        """Test scaffold mode accepts fastapi template."""
        response = client.post(
            "/builder/run",
            headers=auth_headers,
            json={
                "mode": "scaffold",
                "template": "fastapi",
                "project": {"name": "api-server"},
            }
        )
        assert response.status_code == 202
        assert response.json()["template"] == "fastapi"
    
    def test_scaffold_mode_accepts_fullstack_template(self, client, auth_headers):
        """Test scaffold mode accepts fullstack template."""
        response = client.post(
            "/builder/run",
            headers=auth_headers,
            json={
                "mode": "scaffold",
                "template": "fullstack",
                "project": {"name": "fullstack-app"},
            }
        )
        assert response.status_code == 202
        assert response.json()["template"] == "fullstack"
    
    def test_scaffold_mode_accepts_output_format(self, client, auth_headers):
        """Test scaffold mode accepts output format configuration."""
        response = client.post(
            "/builder/run",
            headers=auth_headers,
            json={
                "mode": "scaffold",
                "template": "nextjs",
                "project": {"name": "my-app"},
                "output": {
                    "format": "patches",
                    "base_path": "/src",
                },
            }
        )
        assert response.status_code == 202


# =============================================================================
# Scaffold Generator Tests
# =============================================================================

class TestScaffoldGenerator:
    """Tests for the scaffold generator module."""
    
    def test_generate_nextjs_scaffold(self):
        """Test generating Next.js scaffold."""
        from app.core.scaffold import generate_scaffold
        
        result = generate_scaffold(
            template="nextjs",
            project_name="test-app",
            description="Test application",
        )
        
        assert result.error is None
        assert result.template == "nextjs"
        assert result.total_files > 0
        assert result.total_bytes > 0
        
        # Check for expected files
        paths = [f.path for f in result.files]
        assert any("package.json" in p for p in paths)
        assert any("tsconfig.json" in p for p in paths)
    
    def test_generate_fastapi_scaffold(self):
        """Test generating FastAPI scaffold."""
        from app.core.scaffold import generate_scaffold
        
        result = generate_scaffold(
            template="fastapi",
            project_name="api-server",
        )
        
        assert result.error is None
        assert result.template == "fastapi"
        assert result.total_files > 0
        
        paths = [f.path for f in result.files]
        assert any("requirements.txt" in p for p in paths)
        assert any("main.py" in p for p in paths)
    
    def test_generate_fullstack_scaffold(self):
        """Test generating fullstack scaffold."""
        from app.core.scaffold import generate_scaffold
        
        result = generate_scaffold(
            template="fullstack",
            project_name="full-app",
        )
        
        assert result.error is None
        assert result.template == "fullstack"
        assert result.total_files > 0
        
        paths = [f.path for f in result.files]
        # Should have both frontend and backend
        assert any("frontend" in p for p in paths)
        assert any("backend" in p for p in paths)
    
    def test_scaffold_rejects_invalid_template(self):
        """Test scaffold rejects invalid template."""
        from app.core.scaffold import generate_scaffold, ScaffoldError
        
        with pytest.raises(ScaffoldError) as exc:
            generate_scaffold(
                template="invalid",
                project_name="test-app",
            )
        assert "Unknown template" in str(exc.value)
    
    def test_scaffold_validates_project_name(self):
        """Test scaffold validates project name."""
        from app.core.scaffold import generate_scaffold, ScaffoldError
        
        with pytest.raises(ScaffoldError):
            generate_scaffold(
                template="nextjs",
                project_name="123-invalid",  # Can't start with number
            )
    
    def test_files_to_patches_conversion(self):
        """Test converting files to patches."""
        from app.core.scaffold import files_to_patches, GeneratedFile
        
        files = [
            GeneratedFile(path="test.py", content="print('hello')"),
            GeneratedFile(path="readme.md", content="# Test"),
        ]
        
        patches = files_to_patches(files)
        
        assert len(patches) == 2
        assert all(p["diff_type"] == "add" for p in patches)
        assert all("unified_diff" in p for p in patches)


# =============================================================================
# Scaffold Size Limits Tests
# =============================================================================

class TestScaffoldSizeLimits:
    """Tests for scaffold size limits."""
    
    def test_scaffold_max_files_constant(self):
        """Test MAX_FILES constant is 80."""
        from app.core.scaffold import MAX_FILES
        assert MAX_FILES == 80
    
    def test_scaffold_max_file_size_constant(self):
        """Test MAX_FILE_SIZE is 80KB."""
        from app.core.scaffold import MAX_FILE_SIZE
        assert MAX_FILE_SIZE == 80 * 1024
    
    def test_scaffold_max_total_size_constant(self):
        """Test MAX_TOTAL_SIZE is 1.5MB."""
        from app.core.scaffold import MAX_TOTAL_SIZE
        assert MAX_TOTAL_SIZE == 1.5 * 1024 * 1024
    
    def test_scaffold_respects_file_count_limit(self):
        """Test scaffold respects file count limit."""
        from app.core.scaffold import generate_scaffold, MAX_FILES
        
        result = generate_scaffold(
            template="fullstack",  # Largest template
            project_name="big-app",
        )
        
        assert result.total_files <= MAX_FILES
    
    def test_scaffold_respects_total_size_limit(self):
        """Test scaffold respects total size limit."""
        from app.core.scaffold import generate_scaffold, MAX_TOTAL_SIZE
        
        result = generate_scaffold(
            template="fullstack",
            project_name="big-app",
        )
        
        assert result.total_bytes <= MAX_TOTAL_SIZE


# =============================================================================
# Fix Mode Tests
# =============================================================================

class TestFixMode:
    """Tests for fix mode."""
    
    def test_fix_mode_requires_repo(self, client, auth_headers):
        """Test that fix mode requires repo or repo_url."""
        response = client.post(
            "/builder/run",
            headers=auth_headers,
            json={
                "mode": "fix",
                "task": {"prompt": "Fix the bug"},
            }
        )
        assert response.status_code == 422
    
    def test_fix_mode_requires_task_or_prompt(self, client, auth_headers):
        """Test that fix mode requires task or prompt."""
        response = client.post(
            "/builder/run",
            headers=auth_headers,
            json={
                "mode": "fix",
                "repo_url": "https://github.com/owner/repo",
            }
        )
        assert response.status_code == 422
    
    def test_fix_mode_accepts_repo_url(self, client, auth_headers):
        """Test fix mode accepts repo_url."""
        response = client.post(
            "/builder/run",
            headers=auth_headers,
            json={
                "mode": "fix",
                "repo_url": "https://github.com/owner/repo",
                "prompt": "Fix the authentication bug",
            }
        )
        assert response.status_code == 202
        data = response.json()
        assert data["mode"] == "fix"
        assert data["repo_url"] == "https://github.com/owner/repo"
    
    def test_fix_mode_accepts_repo_dict(self, client, auth_headers):
        """Test fix mode accepts repo dict."""
        response = client.post(
            "/builder/run",
            headers=auth_headers,
            json={
                "mode": "fix",
                "repo": {
                    "provider": "github",
                    "owner": "test-org",
                    "name": "test-repo",
                    "ref": "main",
                },
                "task": {
                    "prompt": "Fix the database connection issue",
                },
            }
        )
        assert response.status_code == 202
        assert response.json()["mode"] == "fix"
    
    def test_fix_mode_accepts_task_context(self, client, auth_headers):
        """Test fix mode accepts task context with error details."""
        response = client.post(
            "/builder/run",
            headers=auth_headers,
            json={
                "mode": "fix",
                "repo_url": "https://github.com/owner/repo",
                "task": {
                    "prompt": "Fix the TypeError",
                    "context": {
                        "error_log": "TypeError: Cannot read property 'x' of undefined",
                        "stacktrace": "at line 42 in main.js",
                        "failing_test": "test_main.py::test_handler",
                        "expected_behavior": "Should return valid JSON",
                    },
                },
            }
        )
        assert response.status_code == 202


# =============================================================================
# Fixer Module Tests
# =============================================================================

class TestFixerModule:
    """Tests for the fixer module."""
    
    def test_fixer_dataclasses_exist(self):
        """Test fixer dataclasses are defined."""
        from app.core.fixer import (
            ReproStep,
            VerificationItem,
            FixerPatch,
            FixerAnalysis,
            FixerError,
        )
        
        # Test ReproStep
        step = ReproStep(
            step_number=1,
            description="Clone the repository",
            command="git clone https://github.com/test/repo",
        )
        assert step.step_number == 1
        
        # Test VerificationItem
        item = VerificationItem(
            description="Run tests",
            command="pytest",
            is_manual=False,
        )
        assert item.is_manual is False
        
        # Test FixerPatch
        patch = FixerPatch(
            path="test.py",
            diff_type="modify",
            description="Fix the bug",
            unified_diff="--- a/test.py\n+++ b/test.py\n@@ -1 +1 @@\n-old\n+new",
            confidence="high",
        )
        assert patch.confidence == "high"
    
    @pytest.mark.asyncio
    async def test_analyze_issue_returns_analysis(self):
        """Test analyze_issue returns FixerAnalysis."""
        from app.core.fixer import analyze_issue, FixerAnalysis
        
        # Mock the repo_tools functions
        with patch("app.core.fixer.repo_get_info") as mock_info, \
             patch("app.core.fixer.repo_get_tree") as mock_tree, \
             patch("app.core.fixer.repo_get_readme") as mock_readme, \
             patch("app.core.fixer.repo_get_file") as mock_file:
            
            mock_info.return_value = {
                "name": "test-repo",
                "language": "Python",
                "default_branch": "main",
            }
            mock_tree.return_value = {
                "tree": [
                    {"path": "main.py", "type": "file"},
                    {"path": "tests", "type": "dir"},
                ],
                "total_entries": 2,
            }
            mock_readme.return_value = {"content": "# Test Repo"}
            mock_file.return_value = {"content": "print('hello')"}
            
            result = await analyze_issue(
                owner="test",
                repo="repo",
                ref="main",
                prompt="Fix the import error",
                error_log="ImportError: No module named 'foo'",
            )
            
            assert isinstance(result, FixerAnalysis)
            assert result.owner == "test"
            assert result.repo == "repo"
            assert result.repo_summary is not None


# =============================================================================
# Response Schema Tests
# =============================================================================

class TestResponseSchemas:
    """Tests for response schema stability."""
    
    def test_scaffold_file_schema(self):
        """Test ScaffoldFile schema."""
        from app.schemas.builder import ScaffoldFile
        
        sf = ScaffoldFile(
            path="test.py",
            content="print('hello')",
            size=14,
        )
        assert sf.path == "test.py"
        assert sf.size == 14
    
    def test_repro_step_schema(self):
        """Test ReproStep schema."""
        from app.schemas.builder import ReproStep
        
        step = ReproStep(
            step_number=1,
            description="Install dependencies",
            command="npm install",
            expected_result="All packages installed",
        )
        assert step.step_number == 1
        assert step.command == "npm install"
    
    def test_verification_item_schema(self):
        """Test VerificationItem schema."""
        from app.schemas.builder import VerificationItem
        
        item = VerificationItem(
            description="Check tests pass",
            command="pytest",
            is_manual=False,
        )
        assert item.is_manual is False
    
    def test_builder_result_response_has_scaffold_fields(self):
        """Test BuilderResultResponse has scaffold mode fields."""
        from app.schemas.builder import BuilderResultResponse
        
        # Check that the model has scaffold fields
        fields = BuilderResultResponse.model_fields
        assert "scaffold_files" in fields
        assert "scaffold_base_path" in fields
        assert "scaffold_template" in fields
        assert "scaffold_total_bytes" in fields
    
    def test_builder_result_response_has_fix_fields(self):
        """Test BuilderResultResponse has fix mode fields."""
        from app.schemas.builder import BuilderResultResponse
        
        fields = BuilderResultResponse.model_fields
        assert "repo_summary" in fields
        assert "likely_cause" in fields
        assert "repro_plan" in fields
        assert "verification_checklist" in fields
        assert "risk_notes" in fields
    
    def test_builder_run_response_has_mode(self):
        """Test BuilderRunResponse has mode field."""
        from app.schemas.builder import BuilderRunResponse
        
        fields = BuilderRunResponse.model_fields
        assert "mode" in fields
        assert "template" in fields


# =============================================================================
# Mode Enum Tests
# =============================================================================

class TestModeEnums:
    """Tests for mode-related enums."""
    
    def test_builder_mode_enum(self):
        """Test BuilderMode enum values."""
        from app.schemas.builder import BuilderMode
        
        assert BuilderMode.BUILDER.value == "builder"
        assert BuilderMode.SCAFFOLD.value == "scaffold"
        assert BuilderMode.FIX.value == "fix"
    
    def test_scaffold_template_enum(self):
        """Test ScaffoldTemplate enum values."""
        from app.schemas.builder import ScaffoldTemplate
        
        assert ScaffoldTemplate.NEXTJS.value == "nextjs"
        assert ScaffoldTemplate.FASTAPI.value == "fastapi"
        assert ScaffoldTemplate.FULLSTACK.value == "fullstack"
    
    def test_output_format_enum(self):
        """Test OutputFormat enum values."""
        from app.schemas.builder import OutputFormat
        
        assert OutputFormat.FILES.value == "files"
        assert OutputFormat.PATCHES.value == "patches"


# =============================================================================
# Builder Mode Backward Compatibility Tests
# =============================================================================

class TestBuilderModeBackwardCompatibility:
    """Tests to ensure builder mode still works."""
    
    def test_default_mode_is_builder(self, client, auth_headers):
        """Test that default mode is builder."""
        response = client.post(
            "/builder/run",
            headers=auth_headers,
            json={
                "repo_url": "https://github.com/owner/repo",
                "prompt": "Add error handling to the API",
            }
        )
        assert response.status_code == 202
        # When mode is not specified, it defaults to builder
        assert response.json()["mode"] == "builder"
    
    def test_explicit_builder_mode(self, client, auth_headers):
        """Test explicit builder mode."""
        response = client.post(
            "/builder/run",
            headers=auth_headers,
            json={
                "mode": "builder",
                "repo_url": "https://github.com/owner/repo",
                "prompt": "Refactor the database layer",
            }
        )
        assert response.status_code == 202
        assert response.json()["mode"] == "builder"


# =============================================================================
# Integration Tests (Mocked)
# =============================================================================

class TestMockedIntegration:
    """Integration tests with mocked external calls."""
    
    @pytest.mark.asyncio
    async def test_scaffold_job_execution(self):
        """Test scaffold job background execution."""
        from app.api.builder import _run_scaffold_job
        from app.core.jobs import job_store, JobStatus
        from app.schemas.agent import JobMode
        
        # Create a mock job
        job = job_store.create_job(
            mode=JobMode.BUILDER,
            prompt="Scaffold nextjs",
            input_data={
                "mode": "scaffold",
                "template": "nextjs",
                "project": {"name": "test-app"},
                "output": {"format": "files"},
            },
            tenant_id="test",
        )
        
        try:
            # Run the scaffold job
            await _run_scaffold_job(job.id, job.input)
            
            # Check result
            updated_job = job_store.get(job.id)
            assert updated_job.status == JobStatus.DONE
            assert updated_job.output is not None
            assert updated_job.output.get("mode") == "scaffold"
            assert updated_job.output.get("template") == "nextjs"
            assert "scaffold_files" in updated_job.output or "diffs" in updated_job.output
        finally:
            job_store.delete(job.id)
    
    @pytest.mark.asyncio
    async def test_fix_job_execution(self):
        """Test fix job background execution with mocked repo calls."""
        from app.api.builder import _run_fix_job
        from app.core.jobs import job_store, JobStatus
        from app.schemas.agent import JobMode
        
        # Create a mock job
        job = job_store.create_job(
            mode=JobMode.BUILDER,
            prompt="Fix the bug",
            input_data={
                "mode": "fix",
                "repo_url": "https://github.com/test/repo",
                "repo": {"owner": "test", "name": "repo"},
                "ref": "main",
                "task": {
                    "prompt": "Fix the import error",
                    "context": {
                        "error_log": "ImportError: No module named 'foo'",
                    },
                },
                "prompt": "Fix the import error",
            },
            tenant_id="test",
        )
        
        try:
            with patch("app.core.fixer.repo_get_info") as mock_info, \
                 patch("app.core.fixer.repo_get_tree") as mock_tree, \
                 patch("app.core.fixer.repo_get_readme") as mock_readme, \
                 patch("app.core.fixer.repo_get_file") as mock_file:
                
                mock_info.return_value = {
                    "name": "repo",
                    "language": "Python",
                    "default_branch": "main",
                }
                mock_tree.return_value = {
                    "tree": [{"path": "main.py", "type": "file"}],
                    "total_entries": 1,
                }
                mock_readme.return_value = {"content": "# Test"}
                mock_file.return_value = {"content": "import foo"}
                
                await _run_fix_job(job.id, job.input)
                
                updated_job = job_store.get(job.id)
                assert updated_job.status == JobStatus.DONE
                assert updated_job.output is not None
                assert updated_job.output.get("mode") == "fix"
        finally:
            job_store.delete(job.id)


# =============================================================================
# Error Handling Tests
# =============================================================================

class TestErrorHandling:
    """Tests for error handling."""
    
    def test_invalid_mode_rejected(self, client, auth_headers):
        """Test invalid mode is rejected."""
        response = client.post(
            "/builder/run",
            headers=auth_headers,
            json={
                "mode": "invalid_mode",
                "repo_url": "https://github.com/owner/repo",
                "prompt": "Do something",
            }
        )
        assert response.status_code == 422
    
    def test_scaffold_invalid_template_rejected(self, client, auth_headers):
        """Test invalid scaffold template is rejected."""
        response = client.post(
            "/builder/run",
            headers=auth_headers,
            json={
                "mode": "scaffold",
                "template": "invalid_template",
                "project": {"name": "test"},
            }
        )
        assert response.status_code == 422
