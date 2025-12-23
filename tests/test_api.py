"""
API endpoint tests.
"""
import time
import pytest


class TestHealthEndpoint:
    """Tests for health check endpoint."""
    
    def test_health_returns_ok(self, client):
        """Health endpoint should return ok status."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"


class TestAuthentication:
    """Tests for API key authentication."""
    
    def test_missing_api_key_returns_401(self, client):
        """Requests without API key should return 401."""
        response = client.get("/agent/jobs")
        assert response.status_code == 401
        # API returns "Missing API key" detail
        assert response.json()["detail"] == "Missing API key"
    
    def test_invalid_api_key_returns_401(self, client, invalid_auth_headers):
        """Requests with invalid API key should return 401."""
        response = client.get("/agent/jobs", headers=invalid_auth_headers)
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid API key"
    
    def test_valid_api_key_allows_access(self, client, auth_headers):
        """Requests with valid API key should succeed."""
        response = client.get("/agent/jobs", headers=auth_headers)
        assert response.status_code == 200


class TestMetricsEndpoint:
    """Tests for metrics endpoint."""
    
    def test_metrics_requires_auth(self, client):
        """Metrics endpoint should require authentication."""
        response = client.get("/metrics")
        assert response.status_code == 401
    
    def test_metrics_returns_prometheus_format(self, client, auth_headers):
        """Metrics endpoint should return Prometheus format."""
        response = client.get("/metrics", headers=auth_headers)
        assert response.status_code == 200
        assert "text/plain" in response.headers["content-type"]
        # Check for expected metric names
        content = response.text
        assert "agent_requests_total" in content
        assert "agent_job_created_total" in content


class TestToolMode:
    """Tests for tool-mode job execution."""
    
    def test_run_echo_tool(self, client, auth_headers):
        """Echo tool should return 202 Accepted (async)."""
        response = client.post(
            "/agent/run",
            json={"tool": "echo", "input": {"message": "hello world"}},
            headers=auth_headers,
        )
        # API returns 202 Accepted for async job creation
        assert response.status_code == 202
        data = response.json()
        assert "job_id" in data
        assert data["status"] in ["queued", "running", "done"]
    
    def test_get_job_status(self, client, auth_headers):
        """Should be able to get job status by ID."""
        # Create a job first
        response = client.post(
            "/agent/run",
            json={"tool": "echo", "input": {"message": "test"}},
            headers=auth_headers,
        )
        job_id = response.json()["job_id"]
        
        # Wait briefly for job to complete
        time.sleep(0.5)
        
        # Get status
        response = client.get(f"/agent/status/{job_id}", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["job_id"] == job_id
        assert data["status"] == "done"
    
    def test_list_jobs(self, client, auth_headers):
        """Should be able to list jobs."""
        response = client.get("/agent/jobs", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        # API uses "items" instead of "jobs"
        assert "items" in data
        assert "total" in data
        assert isinstance(data["items"], list)
    
    def test_invalid_tool_returns_422(self, client, auth_headers):
        """Invalid tool name should return 422."""
        response = client.post(
            "/agent/run",
            json={"tool": "invalid_tool", "input": {}},
            headers=auth_headers,
        )
        assert response.status_code == 422


class TestAgentMode:
    """Tests for agent-mode job execution."""
    
    def test_run_agent_mode(self, client, auth_headers):
        """Agent mode should accept a prompt and return 202."""
        response = client.post(
            "/agent/run",
            json={"prompt": "echo hello"},
            headers=auth_headers,
        )
        # API returns 202 Accepted for async job creation
        assert response.status_code == 202
        data = response.json()
        assert "job_id" in data
        assert data["mode"] == "agent"
    
    def test_get_agent_steps(self, client, auth_headers):
        """Should be able to get agent steps."""
        # Create an agent job
        response = client.post(
            "/agent/run",
            json={"prompt": "echo test message"},
            headers=auth_headers,
        )
        job_id = response.json()["job_id"]
        
        # Wait for job to complete
        time.sleep(1.0)
        
        # Get steps
        response = client.get(f"/agent/steps/{job_id}", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "steps" in data
    
    def test_get_agent_result(self, client, auth_headers):
        """Should be able to get agent result."""
        # Create an agent job
        response = client.post(
            "/agent/run",
            json={"prompt": "echo final answer"},
            headers=auth_headers,
        )
        job_id = response.json()["job_id"]
        
        # Wait for job to complete
        time.sleep(1.0)
        
        # Get result
        response = client.get(f"/agent/result/{job_id}", headers=auth_headers)
        assert response.status_code == 200


class TestJobManagement:
    """Tests for job management endpoints."""
    
    def test_delete_job(self, client, auth_headers):
        """Should be able to delete a job."""
        # Create a job first
        response = client.post(
            "/agent/run",
            json={"tool": "echo", "input": {"message": "to delete"}},
            headers=auth_headers,
        )
        job_id = response.json()["job_id"]
        
        # Wait briefly
        time.sleep(0.5)
        
        # Delete
        response = client.delete(f"/agent/jobs/{job_id}", headers=auth_headers)
        assert response.status_code == 200
        
        # Verify deleted
        response = client.get(f"/agent/status/{job_id}", headers=auth_headers)
        assert response.status_code == 404
    
    def test_cancel_completed_job_returns_409(self, client, auth_headers):
        """Cannot cancel a completed job - returns 409 Conflict."""
        # Create a job
        response = client.post(
            "/agent/run",
            json={"tool": "echo", "input": {"message": "complete first"}},
            headers=auth_headers,
        )
        job_id = response.json()["job_id"]
        
        # Wait for completion
        time.sleep(0.5)
        
        # Try to cancel - should return 409 Conflict
        response = client.post(f"/agent/cancel/{job_id}", headers=auth_headers)
        assert response.status_code == 409
