"""
Phase 15 UI Tests - Agent Control Panel Web UI.

Tests for the web UI endpoints including:
- Auth required on /ui endpoints
- Job list page works
- Job details page shows steps/citations
- Form submission creates jobs
- Download endpoints return correct files
"""
import json
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from main import app
from app.core.jobs import job_store, JobStatus
from app.schemas.agent import JobMode, ToolName


# Test client with valid API key
@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def auth_headers():
    """Headers with valid API key."""
    return {"X-API-Key": "test-key"}


@pytest.fixture
def mock_auth():
    """Mock authentication to always pass."""
    with patch("app.core.security.authenticate_api_key") as mock:
        mock.return_value = MagicMock(
            tenant_id="test-tenant",
            api_key_id="test-key-id"
        )
        with patch("app.core.security.check_request_quota") as quota_mock:
            quota_mock.return_value = (True, None)
            yield mock


class TestUIAuth:
    """Test that UI pages are PUBLIC (no server-side auth required).
    
    Note: UI pages are intentionally public. Authentication is handled
    client-side via JavaScript that stores API key in localStorage and
    attaches it to fetch() requests to protected API endpoints.
    """
    
    def test_ui_root_is_public(self, client):
        """GET /ui is public (redirects to jobs)."""
        response = client.get("/ui", follow_redirects=False)
        assert response.status_code == 302
    
    def test_ui_jobs_is_public(self, client):
        """GET /ui/jobs is public (returns HTML)."""
        response = client.get("/ui/jobs")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
    
    def test_ui_job_detail_is_public(self, client):
        """GET /ui/jobs/{job_id} is public (returns 404 for non-existent job)."""
        response = client.get("/ui/jobs/test-job-id")
        assert response.status_code == 404  # Job not found, but page is accessible
    
    def test_ui_run_form_is_public(self, client):
        """GET /ui/run is public (returns HTML)."""
        response = client.get("/ui/run")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
    
    def test_ui_submit_tool_is_public(self, client):
        """POST /ui/run/tool is public (creates job with legacy tenant)."""
        response = client.post("/ui/run/tool", data={
            "tool": "echo",
            "input_json": '{"message": "test"}'
        }, follow_redirects=False)
        # Form submission redirects to job detail page
        assert response.status_code in [200, 302, 303]
    
    def test_ui_submit_agent_is_public(self, client):
        """POST /ui/run/agent is public (creates job with legacy tenant)."""
        response = client.post("/ui/run/agent", data={
            "prompt": "test prompt"
        }, follow_redirects=False)
        # Form submission redirects to job detail page
        assert response.status_code in [200, 302, 303]
    
    def test_ui_submit_builder_is_public(self, client):
        """POST /ui/run/builder is public (creates job with legacy tenant)."""
        response = client.post("/ui/run/builder", data={
            "repo_url": "https://github.com/test/repo"
        }, follow_redirects=False)
        # Form submission redirects to job detail page
        assert response.status_code in [200, 302, 303]


class TestUIJobsList:
    """Test job list page."""
    
    def test_ui_root_redirects_to_jobs(self, client, mock_auth, auth_headers):
        """GET /ui redirects to /ui/jobs."""
        response = client.get("/ui", headers=auth_headers, follow_redirects=False)
        assert response.status_code == 302
        assert "/ui/jobs" in response.headers.get("location", "")
    
    def test_ui_jobs_returns_html(self, client, mock_auth, auth_headers):
        """GET /ui/jobs returns HTML page."""
        response = client.get("/ui/jobs", headers=auth_headers)
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
        assert "Agent Control Panel" in response.text
    
    def test_ui_jobs_shows_empty_state(self, client, mock_auth, auth_headers):
        """Jobs list shows empty state when no jobs."""
        with patch.object(job_store, "list_jobs", return_value=([], 0)):
            response = client.get("/ui/jobs", headers=auth_headers)
            assert response.status_code == 200
            assert "No jobs found" in response.text
    
    def test_ui_jobs_shows_job_list(self, client, mock_auth, auth_headers):
        """Jobs list shows jobs when present."""
        # Create a mock job
        mock_job = MagicMock()
        mock_job.id = "test-job-123"
        mock_job.mode = "agent"
        mock_job.status = "done"
        mock_job.tool = None
        mock_job.created_at = datetime.now(timezone.utc).isoformat()
        mock_job.started_at = None
        mock_job.completed_at = None
        mock_job.duration_ms = 1500
        
        with patch.object(job_store, "list_jobs", return_value=([mock_job], 1)):
            response = client.get("/ui/jobs", headers=auth_headers)
            assert response.status_code == 200
            assert "test-job-123" in response.text or "test-job" in response.text
    
    def test_ui_jobs_pagination(self, client, mock_auth, auth_headers):
        """Jobs list supports pagination."""
        with patch.object(job_store, "list_jobs", return_value=([], 100)):
            response = client.get("/ui/jobs?limit=10&offset=20", headers=auth_headers)
            assert response.status_code == 200
            # Check pagination controls are present
            assert "Next" in response.text or "Prev" in response.text
    
    def test_ui_jobs_filter_by_status(self, client, mock_auth, auth_headers):
        """Jobs list can filter by status."""
        with patch.object(job_store, "list_jobs") as mock_list:
            mock_list.return_value = ([], 0)
            response = client.get("/ui/jobs?status=done", headers=auth_headers)
            assert response.status_code == 200
            # Verify list_jobs was called with status filter
            call_args = mock_list.call_args
            assert call_args[1].get("status") == JobStatus.DONE


class TestUIJobDetail:
    """Test job detail page."""
    
    def test_ui_job_detail_not_found(self, client, mock_auth, auth_headers):
        """Job detail returns 404 for missing job."""
        with patch.object(job_store, "get_for_tenant", return_value=None):
            response = client.get("/ui/jobs/nonexistent", headers=auth_headers)
            assert response.status_code == 404
    
    def test_ui_job_detail_returns_html(self, client, mock_auth, auth_headers):
        """Job detail returns HTML page."""
        # Create a mock job
        mock_job = MagicMock()
        mock_job.id = "test-job-123"
        mock_job.mode = JobMode.TOOL
        mock_job.status = JobStatus.DONE
        mock_job.tool = ToolName.ECHO
        mock_job.input = {"message": "test"}
        mock_job.output = {"result": "test"}
        mock_job.error = None
        mock_job.prompt = None
        mock_job.created_at = datetime.now(timezone.utc)
        mock_job.started_at = datetime.now(timezone.utc)
        mock_job.completed_at = datetime.now(timezone.utc)
        mock_job.duration_ms = 100
        mock_job.artifact_path = None
        mock_job.artifact_name = None
        mock_job.artifact_size_bytes = None
        mock_job.patch_artifact_path = None
        mock_job.patch_size_bytes = None
        
        with patch.object(job_store, "get_for_tenant", return_value=mock_job):
            response = client.get("/ui/jobs/test-job-123", headers=auth_headers)
            assert response.status_code == 200
            assert "text/html" in response.headers.get("content-type", "")
            assert "test-job-123" in response.text
    
    def test_ui_job_detail_shows_error(self, client, mock_auth, auth_headers):
        """Job detail shows error message for failed jobs."""
        mock_job = MagicMock()
        mock_job.id = "failed-job"
        mock_job.mode = JobMode.TOOL
        mock_job.status = JobStatus.ERROR
        mock_job.tool = ToolName.ECHO
        mock_job.input = {}
        mock_job.output = None
        mock_job.error = "Something went wrong"
        mock_job.prompt = None
        mock_job.created_at = datetime.now(timezone.utc)
        mock_job.started_at = None
        mock_job.completed_at = None
        mock_job.duration_ms = None
        mock_job.artifact_path = None
        mock_job.artifact_name = None
        mock_job.artifact_size_bytes = None
        mock_job.patch_artifact_path = None
        mock_job.patch_size_bytes = None
        
        with patch.object(job_store, "get_for_tenant", return_value=mock_job):
            response = client.get("/ui/jobs/failed-job", headers=auth_headers)
            assert response.status_code == 200
            assert "Something went wrong" in response.text
            assert "Error" in response.text
    
    def test_ui_job_detail_shows_steps(self, client, mock_auth, auth_headers):
        """Job detail shows execution steps for agent jobs."""
        mock_job = MagicMock()
        mock_job.id = "agent-job"
        mock_job.mode = JobMode.AGENT
        mock_job.status = JobStatus.DONE
        mock_job.tool = None
        mock_job.input = {}
        mock_job.output = None
        mock_job.error = None
        mock_job.prompt = "Search for AI news"
        mock_job.created_at = datetime.now(timezone.utc)
        mock_job.started_at = datetime.now(timezone.utc)
        mock_job.completed_at = datetime.now(timezone.utc)
        mock_job.duration_ms = 2000
        mock_job.artifact_path = None
        mock_job.artifact_name = None
        mock_job.artifact_size_bytes = None
        mock_job.patch_artifact_path = None
        mock_job.patch_size_bytes = None
        
        mock_step = MagicMock()
        mock_step.step_number = 1
        mock_step.tool = "web_search"
        mock_step.status = "done"
        mock_step.output_summary = '{"result_count": 5}'
        mock_step.error = None
        mock_step.duration_ms = 500
        
        with patch.object(job_store, "get_for_tenant", return_value=mock_job):
            with patch("app.api.ui.get_job_steps", return_value=[mock_step]):
                with patch("app.api.ui.get_job_result_with_citations", return_value={
                    "final_output": "Found 5 results",
                    "bullets": ["AI is advancing"],
                    "citations": [{"url": "https://example.com", "title": "Example"}]
                }):
                    response = client.get("/ui/jobs/agent-job", headers=auth_headers)
                    assert response.status_code == 200
                    assert "Step 1" in response.text
                    assert "web_search" in response.text
    
    def test_ui_job_detail_shows_artifacts(self, client, mock_auth, auth_headers):
        """Job detail shows download links for artifacts."""
        mock_job = MagicMock()
        mock_job.id = "builder-job"
        mock_job.mode = JobMode.BUILDER
        mock_job.status = JobStatus.DONE
        mock_job.tool = None
        mock_job.input = {}
        mock_job.output = None
        mock_job.error = None
        mock_job.prompt = "Build project"
        mock_job.created_at = datetime.now(timezone.utc)
        mock_job.started_at = datetime.now(timezone.utc)
        mock_job.completed_at = datetime.now(timezone.utc)
        mock_job.duration_ms = 5000
        mock_job.artifact_path = "/path/to/artifact.zip"
        mock_job.artifact_name = "my-project.zip"
        mock_job.artifact_size_bytes = 12345
        mock_job.patch_artifact_path = "/path/to/patch.diff"
        mock_job.patch_size_bytes = 1234
        
        with patch.object(job_store, "get_for_tenant", return_value=mock_job):
            response = client.get("/ui/jobs/builder-job", headers=auth_headers)
            assert response.status_code == 200
            assert "Download ZIP" in response.text
            assert "Download Patch" in response.text
            assert "12,345" in response.text or "12345" in response.text


class TestUIRunForm:
    """Test job creation form."""
    
    def test_ui_run_form_returns_html(self, client, mock_auth, auth_headers):
        """GET /ui/run returns HTML form."""
        response = client.get("/ui/run", headers=auth_headers)
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
        assert "Create New Job" in response.text
    
    def test_ui_run_form_has_mode_tabs(self, client, mock_auth, auth_headers):
        """Form has tabs for different modes."""
        response = client.get("/ui/run", headers=auth_headers)
        assert response.status_code == 200
        assert "Tool Mode" in response.text
        assert "Agent Mode" in response.text
        assert "Repo Builder" in response.text
    
    def test_ui_run_form_has_tool_options(self, client, mock_auth, auth_headers):
        """Form has tool selection options."""
        response = client.get("/ui/run", headers=auth_headers)
        assert response.status_code == 200
        assert "echo" in response.text
        assert "http_fetch" in response.text


class TestUIFormSubmission:
    """Test form submission endpoints."""
    
    def test_ui_submit_tool_invalid_json(self, client, mock_auth, auth_headers):
        """Tool submission rejects invalid JSON."""
        response = client.post(
            "/ui/run/tool",
            headers=auth_headers,
            data={"tool": "echo", "input_json": "not valid json"}
        )
        assert response.status_code == 400
        assert "Invalid JSON" in response.text
    
    def test_ui_submit_tool_invalid_tool(self, client, mock_auth, auth_headers):
        """Tool submission rejects invalid tool name."""
        response = client.post(
            "/ui/run/tool",
            headers=auth_headers,
            data={"tool": "nonexistent", "input_json": "{}"}
        )
        assert response.status_code == 400
        assert "Invalid Tool" in response.text
    
    def test_ui_submit_tool_creates_job(self, client, mock_auth, auth_headers):
        """Tool submission creates job and redirects."""
        with patch.object(job_store, "create") as mock_create:
            mock_job = MagicMock()
            mock_job.id = "new-job-123"
            mock_create.return_value = mock_job
            
            with patch("asyncio.create_task"):
                response = client.post(
                    "/ui/run/tool",
                    headers=auth_headers,
                    data={"tool": "echo", "input_json": '{"message": "hello"}'},
                    follow_redirects=False
                )
                assert response.status_code == 303
                assert "/ui/jobs/new-job-123" in response.headers.get("location", "")
    
    def test_ui_submit_agent_creates_job(self, client, mock_auth, auth_headers):
        """Agent submission creates job and redirects."""
        with patch.object(job_store, "create_job") as mock_create:
            mock_job = MagicMock()
            mock_job.id = "agent-job-456"
            mock_create.return_value = mock_job
            
            with patch("asyncio.create_task"):
                response = client.post(
                    "/ui/run/agent",
                    headers=auth_headers,
                    data={"prompt": "Search for news", "max_steps": "3"},
                    follow_redirects=False
                )
                assert response.status_code == 303
                assert "/ui/jobs/agent-job-456" in response.headers.get("location", "")
    
    def test_ui_submit_builder_invalid_url(self, client, mock_auth, auth_headers):
        """Builder submission rejects invalid repo URL."""
        with patch("app.core.repo_builder.validate_repo_url", side_effect=ValueError("Invalid URL")):
            response = client.post(
                "/ui/run/builder",
                headers=auth_headers,
                data={"repo_url": "not-a-url"}
            )
            assert response.status_code == 400
            assert "Invalid" in response.text
    
    def test_ui_submit_builder_creates_job(self, client, mock_auth, auth_headers):
        """Builder submission creates job and redirects."""
        # Patch at the place where the import happens
        with patch("app.core.repo_builder.validate_repo_url"):
            with patch.object(job_store, "create_job") as mock_create:
                mock_job = MagicMock()
                mock_job.id = "builder-job-789"
                mock_create.return_value = mock_job
                
                # The UI code uses a local import and direct SessionLocal call
                # We need to patch where it's used, not where it's defined
                from app.db import database
                original_session = database.SessionLocal
                
                mock_db = MagicMock()
                mock_db.query.return_value.filter.return_value.first.return_value = MagicMock()
                mock_db.commit = MagicMock()
                mock_db.close = MagicMock()
                
                database.SessionLocal = MagicMock(return_value=mock_db)
                
                try:
                    with patch("asyncio.create_task"):
                        response = client.post(
                            "/ui/run/builder",
                            headers=auth_headers,
                            data={
                                "repo_url": "https://github.com/test/repo",
                                "ref": "main",
                                "template": "fastapi_api"
                            },
                            follow_redirects=False
                        )
                        assert response.status_code == 303
                        assert "/ui/jobs/builder-job-789" in response.headers.get("location", "")
                finally:
                    database.SessionLocal = original_session


class TestUIHelpers:
    """Test UI helper functions."""
    
    def test_format_datetime(self):
        """Test datetime formatting."""
        from app.api.ui import format_datetime
        
        # None returns dash
        assert format_datetime(None) == "-"
        
        # Datetime object formats correctly
        dt = datetime(2025, 12, 20, 10, 30, 45, tzinfo=timezone.utc)
        result = format_datetime(dt)
        assert "2025-12-20" in result
        assert "10:30:45" in result
    
    def test_format_duration(self):
        """Test duration formatting."""
        from app.api.ui import format_duration
        
        # None returns dash
        assert format_duration(None) == "-"
        
        # Milliseconds
        assert format_duration(500) == "500ms"
        
        # Seconds
        assert "1.5s" in format_duration(1500)
        
        # Minutes
        assert "1.5m" in format_duration(90000)
    
    def test_status_badge_class(self):
        """Test status badge CSS classes."""
        from app.api.ui import status_badge_class
        
        assert "green" in status_badge_class("done")
        assert "red" in status_badge_class("error")
        assert "blue" in status_badge_class("running")
        assert "yellow" in status_badge_class("queued")
    
    def test_mode_badge_class(self):
        """Test mode badge CSS classes."""
        from app.api.ui import mode_badge_class
        
        assert "purple" in mode_badge_class("tool")
        assert "indigo" in mode_badge_class("agent")
        assert "cyan" in mode_badge_class("builder")


class TestUINavigation:
    """Test UI navigation elements."""
    
    def test_jobs_page_has_new_job_link(self, client, mock_auth, auth_headers):
        """Jobs page has link to create new job."""
        with patch.object(job_store, "list_jobs", return_value=([], 0)):
            response = client.get("/ui/jobs", headers=auth_headers)
            assert response.status_code == 200
            assert "/ui/run" in response.text
            assert "New Job" in response.text
    
    def test_job_detail_has_back_link(self, client, mock_auth, auth_headers):
        """Job detail page has link back to jobs list."""
        mock_job = MagicMock()
        mock_job.id = "test-job"
        mock_job.mode = JobMode.TOOL
        mock_job.status = JobStatus.DONE
        mock_job.tool = ToolName.ECHO
        mock_job.input = {}
        mock_job.output = {}
        mock_job.error = None
        mock_job.prompt = None
        mock_job.created_at = datetime.now(timezone.utc)
        mock_job.started_at = None
        mock_job.completed_at = None
        mock_job.duration_ms = None
        mock_job.artifact_path = None
        mock_job.artifact_name = None
        mock_job.artifact_size_bytes = None
        mock_job.patch_artifact_path = None
        mock_job.patch_size_bytes = None
        
        with patch.object(job_store, "get_for_tenant", return_value=mock_job):
            response = client.get("/ui/jobs/test-job", headers=auth_headers)
            assert response.status_code == 200
            assert "/ui/jobs" in response.text
            assert "Back" in response.text
    
    def test_pages_have_api_docs_link(self, client, mock_auth, auth_headers):
        """Pages have link to API documentation."""
        with patch.object(job_store, "list_jobs", return_value=([], 0)):
            response = client.get("/ui/jobs", headers=auth_headers)
            assert response.status_code == 200
            assert "/docs" in response.text
            assert "API Docs" in response.text
    
    def test_pages_have_health_link(self, client, mock_auth, auth_headers):
        """Pages have link to health check."""
        with patch.object(job_store, "list_jobs", return_value=([], 0)):
            response = client.get("/ui/jobs", headers=auth_headers)
            assert response.status_code == 200
            assert "/health" in response.text


class TestUICurlExamples:
    """Test curl example generation."""
    
    def test_job_detail_has_curl_example(self, client, mock_auth, auth_headers):
        """Job detail page has curl example."""
        mock_job = MagicMock()
        mock_job.id = "test-job-abc"
        mock_job.mode = JobMode.TOOL
        mock_job.status = JobStatus.DONE
        mock_job.tool = ToolName.ECHO
        mock_job.input = {}
        mock_job.output = {}
        mock_job.error = None
        mock_job.prompt = None
        mock_job.created_at = datetime.now(timezone.utc)
        mock_job.started_at = None
        mock_job.completed_at = None
        mock_job.duration_ms = None
        mock_job.artifact_path = None
        mock_job.artifact_name = None
        mock_job.artifact_size_bytes = None
        mock_job.patch_artifact_path = None
        mock_job.patch_size_bytes = None
        
        with patch.object(job_store, "get_for_tenant", return_value=mock_job):
            response = client.get("/ui/jobs/test-job-abc", headers=auth_headers)
            assert response.status_code == 200
            assert "curl" in response.text
            assert "test-job-abc" in response.text
            assert "X-API-Key" in response.text
