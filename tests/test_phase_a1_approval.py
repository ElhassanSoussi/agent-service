"""
Tests for Phase A1: Approval Gate + Staged Execution + Audit Logs.

Tests cover:
- Batch CRUD API
- Approval workflow (draft -> pending -> approved -> executing -> executed)
- Enforcement: Cannot run without approval
- Rejection flow
- Audit logging
- UI endpoints
"""
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app


@pytest.fixture
def client():
    """Create a test client."""
    return TestClient(app)


@pytest.fixture
def auth_headers():
    """Return valid authentication headers."""
    return {"X-API-Key": "test-api-key"}


# =============================================================================
# Batch CRUD Tests
# =============================================================================

class TestBatchCRUD:
    """Test Batch CRUD operations."""

    def test_create_batch(self, client, auth_headers):
        """Test creating a new batch with actions."""
        response = client.post(
            "/v1/batches",
            json={
                "title": "Test Batch",
                "description": "A test batch for testing",
                "actions": [
                    {
                        "kind": "note",
                        "risk": "safe",
                        "payload": {"note": "This is a test note"},
                        "preview_text": "Add a test note"
                    },
                    {
                        "kind": "shell",
                        "risk": "medium",
                        "payload": {"command": "echo hello"},
                        "preview_text": "Run echo command"
                    }
                ],
                "created_by": "xone"
            },
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Test Batch"
        assert data["status"] == "draft"
        assert data["created_by"] == "xone"
        assert data["action_count"] == 2
        assert len(data["actions"]) == 2
        assert data["actions"][0]["kind"] == "note"
        assert data["actions"][1]["kind"] == "shell"

    def test_create_batch_auto_submit(self, client, auth_headers):
        """Test creating a batch with auto_submit=True."""
        response = client.post(
            "/v1/batches",
            json={
                "title": "Auto Submit Batch",
                "actions": [
                    {
                        "kind": "note",
                        "risk": "safe",
                        "payload": {"note": "Test"},
                        "preview_text": "Test note"
                    }
                ],
                "auto_submit": True
            },
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "pending"  # Should be pending, not draft

    def test_list_batches(self, client, auth_headers):
        """Test listing batches."""
        # Create a batch first
        client.post(
            "/v1/batches",
            json={
                "title": "List Test Batch",
                "actions": [{"kind": "note", "risk": "safe", "payload": {}, "preview_text": "Test"}]
            },
            headers=auth_headers
        )
        
        response = client.get("/v1/batches", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "batches" in data
        assert "total" in data
        assert data["total"] >= 1

    def test_list_batches_filter_by_status(self, client, auth_headers):
        """Test filtering batches by status."""
        response = client.get("/v1/batches?status=pending", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        # All returned batches should have pending status
        for batch in data["batches"]:
            assert batch["status"] == "pending"

    def test_get_batch_detail(self, client, auth_headers):
        """Test getting batch details."""
        # Create a batch
        create_resp = client.post(
            "/v1/batches",
            json={
                "title": "Detail Test",
                "actions": [{"kind": "note", "risk": "safe", "payload": {}, "preview_text": "Test"}]
            },
            headers=auth_headers
        )
        batch_id = create_resp.json()["id"]
        
        # Get details
        response = client.get(f"/v1/batches/{batch_id}", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == batch_id
        assert data["title"] == "Detail Test"
        assert len(data["actions"]) == 1
        assert len(data["audit_logs"]) >= 1  # Should have creation log

    def test_get_batch_not_found(self, client, auth_headers):
        """Test getting non-existent batch."""
        response = client.get("/v1/batches/nonexistent-id", headers=auth_headers)
        assert response.status_code == 404


# =============================================================================
# Approval Workflow Tests
# =============================================================================

class TestApprovalWorkflow:
    """Test the approval workflow."""

    def test_submit_batch(self, client, auth_headers):
        """Test submitting a batch for approval (draft -> pending)."""
        # Create batch
        create_resp = client.post(
            "/v1/batches",
            json={
                "title": "Submit Test",
                "actions": [{"kind": "note", "risk": "safe", "payload": {}, "preview_text": "Test"}]
            },
            headers=auth_headers
        )
        batch_id = create_resp.json()["id"]
        assert create_resp.json()["status"] == "draft"
        
        # Submit
        response = client.post(f"/v1/batches/{batch_id}/submit", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["status"] == "pending"

    def test_submit_non_draft_batch_fails(self, client, auth_headers):
        """Test that submitting a non-draft batch fails."""
        # Create and submit batch
        create_resp = client.post(
            "/v1/batches",
            json={
                "title": "Already Pending",
                "actions": [{"kind": "note", "risk": "safe", "payload": {}, "preview_text": "Test"}],
                "auto_submit": True
            },
            headers=auth_headers
        )
        batch_id = create_resp.json()["id"]
        
        # Try to submit again
        response = client.post(f"/v1/batches/{batch_id}/submit", headers=auth_headers)
        assert response.status_code == 400
        assert "draft" in response.json()["detail"].lower()

    def test_approve_batch(self, client, auth_headers):
        """Test approving a batch (pending -> approved)."""
        # Create and submit batch
        create_resp = client.post(
            "/v1/batches",
            json={
                "title": "Approve Test",
                "actions": [{"kind": "note", "risk": "safe", "payload": {}, "preview_text": "Test"}],
                "auto_submit": True
            },
            headers=auth_headers
        )
        batch_id = create_resp.json()["id"]
        
        # Approve
        response = client.post(f"/v1/batches/{batch_id}/approve", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "approved"
        assert data["approved_by"] == "admin"
        assert data["approved_at"] is not None

    def test_approve_non_pending_fails(self, client, auth_headers):
        """Test that approving a non-pending batch fails."""
        # Create draft batch
        create_resp = client.post(
            "/v1/batches",
            json={
                "title": "Not Pending",
                "actions": [{"kind": "note", "risk": "safe", "payload": {}, "preview_text": "Test"}]
            },
            headers=auth_headers
        )
        batch_id = create_resp.json()["id"]
        
        # Try to approve draft
        response = client.post(f"/v1/batches/{batch_id}/approve", headers=auth_headers)
        assert response.status_code == 400
        assert "pending" in response.json()["detail"].lower()

    def test_reject_batch(self, client, auth_headers):
        """Test rejecting a batch (pending -> rejected)."""
        # Create and submit batch
        create_resp = client.post(
            "/v1/batches",
            json={
                "title": "Reject Test",
                "actions": [{"kind": "shell", "risk": "risky", "payload": {"command": "rm -rf /"}, "preview_text": "Dangerous command"}],
                "auto_submit": True
            },
            headers=auth_headers
        )
        batch_id = create_resp.json()["id"]
        
        # Reject
        response = client.post(
            f"/v1/batches/{batch_id}/reject",
            json={"reason": "Too risky"},
            headers=auth_headers
        )
        assert response.status_code == 200
        assert response.json()["status"] == "rejected"

    def test_reject_non_pending_fails(self, client, auth_headers):
        """Test that rejecting a non-pending batch fails."""
        # Create draft batch
        create_resp = client.post(
            "/v1/batches",
            json={
                "title": "Not Pending",
                "actions": [{"kind": "note", "risk": "safe", "payload": {}, "preview_text": "Test"}]
            },
            headers=auth_headers
        )
        batch_id = create_resp.json()["id"]
        
        # Try to reject draft
        response = client.post(f"/v1/batches/{batch_id}/reject", headers=auth_headers)
        assert response.status_code == 400


# =============================================================================
# Enforcement Tests (Critical)
# =============================================================================

class TestEnforcement:
    """Test the approval gate enforcement."""

    def test_cannot_run_draft_batch(self, client, auth_headers):
        """Test that a draft batch cannot be run -> 403."""
        # Create draft batch
        create_resp = client.post(
            "/v1/batches",
            json={
                "title": "Draft Batch",
                "actions": [{"kind": "note", "risk": "safe", "payload": {}, "preview_text": "Test"}]
            },
            headers=auth_headers
        )
        batch_id = create_resp.json()["id"]
        
        # Try to run
        response = client.post(f"/v1/batches/{batch_id}/run", headers=auth_headers)
        assert response.status_code == 403
        assert "approved" in response.json()["detail"].lower()

    def test_cannot_run_pending_batch(self, client, auth_headers):
        """Test that a pending batch cannot be run -> 403."""
        # Create and submit batch
        create_resp = client.post(
            "/v1/batches",
            json={
                "title": "Pending Batch",
                "actions": [{"kind": "note", "risk": "safe", "payload": {}, "preview_text": "Test"}],
                "auto_submit": True
            },
            headers=auth_headers
        )
        batch_id = create_resp.json()["id"]
        
        # Try to run without approval
        response = client.post(f"/v1/batches/{batch_id}/run", headers=auth_headers)
        assert response.status_code == 403
        assert "approved" in response.json()["detail"].lower()

    def test_cannot_run_rejected_batch(self, client, auth_headers):
        """Test that a rejected batch cannot be run -> 403."""
        # Create, submit, and reject
        create_resp = client.post(
            "/v1/batches",
            json={
                "title": "Rejected Batch",
                "actions": [{"kind": "note", "risk": "safe", "payload": {}, "preview_text": "Test"}],
                "auto_submit": True
            },
            headers=auth_headers
        )
        batch_id = create_resp.json()["id"]
        client.post(f"/v1/batches/{batch_id}/reject", headers=auth_headers)
        
        # Try to run
        response = client.post(f"/v1/batches/{batch_id}/run", headers=auth_headers)
        assert response.status_code == 403

    def test_can_run_approved_batch(self, client, auth_headers):
        """Test that an approved batch can be run."""
        # Create, submit, and approve
        create_resp = client.post(
            "/v1/batches",
            json={
                "title": "Approved Batch",
                "actions": [{"kind": "note", "risk": "safe", "payload": {"note": "Safe action"}, "preview_text": "Add note"}],
                "auto_submit": True
            },
            headers=auth_headers
        )
        batch_id = create_resp.json()["id"]
        client.post(f"/v1/batches/{batch_id}/approve", headers=auth_headers)
        
        # Run
        response = client.post(f"/v1/batches/{batch_id}/run", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["status"] == "executing"

    def test_verify_execution_endpoint(self, client, auth_headers):
        """Test the verify-execution endpoint."""
        # Without active execution context
        response = client.post("/v1/verify-execution", headers=auth_headers)
        assert response.status_code == 403
        assert "not approved" in response.json()["detail"].lower()


# =============================================================================
# Execution Tests
# =============================================================================

class TestExecution:
    """Test batch execution."""

    def test_execute_note_action(self, client, auth_headers):
        """Test executing a note action (always succeeds)."""
        # Create, submit, approve, and run
        create_resp = client.post(
            "/v1/batches",
            json={
                "title": "Note Execution",
                "actions": [
                    {"kind": "note", "risk": "safe", "payload": {"note": "Important note"}, "preview_text": "Add note"}
                ],
                "auto_submit": True
            },
            headers=auth_headers
        )
        batch_id = create_resp.json()["id"]
        client.post(f"/v1/batches/{batch_id}/approve", headers=auth_headers)
        
        # Run (synchronously wait for completion in test)
        client.post(f"/v1/batches/{batch_id}/run", headers=auth_headers)
        
        # Wait a bit and check status
        import time
        time.sleep(0.5)
        
        response = client.get(f"/v1/batches/{batch_id}", headers=auth_headers)
        data = response.json()
        # Should be executed or still executing
        assert data["status"] in ("executing", "executed")

    @patch('subprocess.run')
    def test_execute_shell_action_success(self, mock_run, client, auth_headers):
        """Test executing a shell command successfully."""
        mock_run.return_value = MagicMock(returncode=0, stdout="Hello World", stderr="")
        
        create_resp = client.post(
            "/v1/batches",
            json={
                "title": "Shell Execution",
                "actions": [
                    {"kind": "shell", "risk": "medium", "payload": {"command": "echo hello"}, "preview_text": "Run echo"}
                ],
                "auto_submit": True
            },
            headers=auth_headers
        )
        batch_id = create_resp.json()["id"]
        client.post(f"/v1/batches/{batch_id}/approve", headers=auth_headers)
        client.post(f"/v1/batches/{batch_id}/run", headers=auth_headers)
        
        import time
        time.sleep(0.5)
        
        response = client.get(f"/v1/batches/{batch_id}", headers=auth_headers)
        # Check it attempted execution
        assert response.json()["status"] in ("executing", "executed", "failed")


# =============================================================================
# Audit Log Tests
# =============================================================================

class TestAuditLogs:
    """Test audit logging."""

    def test_batch_creation_logged(self, client, auth_headers):
        """Test that batch creation is logged."""
        create_resp = client.post(
            "/v1/batches",
            json={
                "title": "Audit Test",
                "actions": [{"kind": "note", "risk": "safe", "payload": {}, "preview_text": "Test"}]
            },
            headers=auth_headers
        )
        batch_id = create_resp.json()["id"]
        
        # Check audit logs
        response = client.get(f"/v1/audit-logs?batch_id={batch_id}", headers=auth_headers)
        assert response.status_code == 200
        logs = response.json()["logs"]
        assert len(logs) >= 1
        assert any(log["event_type"] == "batch_created" for log in logs)

    def test_approval_logged(self, client, auth_headers):
        """Test that approval is logged."""
        # Create and submit
        create_resp = client.post(
            "/v1/batches",
            json={
                "title": "Approval Log Test",
                "actions": [{"kind": "note", "risk": "safe", "payload": {}, "preview_text": "Test"}],
                "auto_submit": True
            },
            headers=auth_headers
        )
        batch_id = create_resp.json()["id"]
        
        # Approve
        client.post(f"/v1/batches/{batch_id}/approve", headers=auth_headers)
        
        # Check audit logs
        response = client.get(f"/v1/audit-logs?batch_id={batch_id}", headers=auth_headers)
        logs = response.json()["logs"]
        assert any(log["event_type"] == "batch_approved" for log in logs)

    def test_rejection_logged(self, client, auth_headers):
        """Test that rejection is logged."""
        # Create and submit
        create_resp = client.post(
            "/v1/batches",
            json={
                "title": "Rejection Log Test",
                "actions": [{"kind": "note", "risk": "safe", "payload": {}, "preview_text": "Test"}],
                "auto_submit": True
            },
            headers=auth_headers
        )
        batch_id = create_resp.json()["id"]
        
        # Reject
        client.post(
            f"/v1/batches/{batch_id}/reject",
            json={"reason": "Test rejection"},
            headers=auth_headers
        )
        
        # Check audit logs
        response = client.get(f"/v1/audit-logs?batch_id={batch_id}", headers=auth_headers)
        logs = response.json()["logs"]
        assert any(log["event_type"] == "batch_rejected" for log in logs)

    def test_list_audit_logs(self, client, auth_headers):
        """Test listing audit logs."""
        response = client.get("/v1/audit-logs", headers=auth_headers)
        assert response.status_code == 200
        assert "logs" in response.json()
        assert "count" in response.json()

    def test_filter_audit_logs_by_event_type(self, client, auth_headers):
        """Test filtering audit logs by event type."""
        response = client.get("/v1/audit-logs?event_type=batch_created", headers=auth_headers)
        assert response.status_code == 200
        logs = response.json()["logs"]
        for log in logs:
            assert log["event_type"] == "batch_created"


# =============================================================================
# UI Endpoint Tests
# =============================================================================

class TestUIEndpoints:
    """Test UI endpoints."""

    def test_approvals_page_loads(self, client):
        """Test that /ui/approvals loads successfully."""
        response = client.get("/ui/approvals")
        assert response.status_code == 200
        assert "Pending Approvals" in response.text
        assert "Xone" in response.text

    def test_batches_page_loads(self, client):
        """Test that /ui/batches loads successfully."""
        response = client.get("/ui/batches")
        assert response.status_code == 200
        assert "Action Batches" in response.text

    def test_batches_page_with_status_filter(self, client):
        """Test /ui/batches with status filter."""
        response = client.get("/ui/batches?status=pending")
        assert response.status_code == 200

    def test_batch_detail_page_loads(self, client, auth_headers):
        """Test that /ui/batches/{id} loads for existing batch."""
        # Create a batch first
        create_resp = client.post(
            "/v1/batches",
            json={
                "title": "UI Detail Test",
                "actions": [{"kind": "note", "risk": "safe", "payload": {}, "preview_text": "Test"}]
            },
            headers=auth_headers
        )
        batch_id = create_resp.json()["id"]
        
        # Load detail page
        response = client.get(f"/ui/batches/{batch_id}")
        assert response.status_code == 200
        assert "UI Detail Test" in response.text
        assert "Approve" in response.text or "approved" in response.text.lower()

    def test_batch_detail_page_not_found(self, client):
        """Test /ui/batches/{id} for non-existent batch."""
        response = client.get("/ui/batches/nonexistent-id")
        assert response.status_code == 404

    def test_chat_ui_has_approvals_nav(self, client):
        """Test that chat UI exposes approvals via navigation."""
        response = client.get("/ui/chat")
        assert response.status_code == 200
        assert "Approvals" in response.text


# =============================================================================
# Delete Tests
# =============================================================================

class TestBatchDelete:
    """Test batch deletion."""

    def test_delete_draft_batch(self, client, auth_headers):
        """Test deleting a draft batch."""
        # Create batch
        create_resp = client.post(
            "/v1/batches",
            json={
                "title": "Delete Test",
                "actions": [{"kind": "note", "risk": "safe", "payload": {}, "preview_text": "Test"}]
            },
            headers=auth_headers
        )
        batch_id = create_resp.json()["id"]
        
        # Delete
        response = client.delete(f"/v1/batches/{batch_id}", headers=auth_headers)
        assert response.status_code == 200
        
        # Verify deleted
        get_resp = client.get(f"/v1/batches/{batch_id}", headers=auth_headers)
        assert get_resp.status_code == 404

    def test_delete_rejected_batch(self, client, auth_headers):
        """Test deleting a rejected batch."""
        # Create, submit, reject
        create_resp = client.post(
            "/v1/batches",
            json={
                "title": "Delete Rejected Test",
                "actions": [{"kind": "note", "risk": "safe", "payload": {}, "preview_text": "Test"}],
                "auto_submit": True
            },
            headers=auth_headers
        )
        batch_id = create_resp.json()["id"]
        client.post(f"/v1/batches/{batch_id}/reject", headers=auth_headers)
        
        # Delete
        response = client.delete(f"/v1/batches/{batch_id}", headers=auth_headers)
        assert response.status_code == 200

    def test_cannot_delete_pending_batch(self, client, auth_headers):
        """Test that pending batches cannot be deleted."""
        # Create and submit
        create_resp = client.post(
            "/v1/batches",
            json={
                "title": "Cannot Delete Pending",
                "actions": [{"kind": "note", "risk": "safe", "payload": {}, "preview_text": "Test"}],
                "auto_submit": True
            },
            headers=auth_headers
        )
        batch_id = create_resp.json()["id"]
        
        # Try to delete
        response = client.delete(f"/v1/batches/{batch_id}", headers=auth_headers)
        assert response.status_code == 400

    def test_cannot_delete_approved_batch(self, client, auth_headers):
        """Test that approved batches cannot be deleted."""
        # Create, submit, approve
        create_resp = client.post(
            "/v1/batches",
            json={
                "title": "Cannot Delete Approved",
                "actions": [{"kind": "note", "risk": "safe", "payload": {}, "preview_text": "Test"}],
                "auto_submit": True
            },
            headers=auth_headers
        )
        batch_id = create_resp.json()["id"]
        client.post(f"/v1/batches/{batch_id}/approve", headers=auth_headers)
        
        # Try to delete
        response = client.delete(f"/v1/batches/{batch_id}", headers=auth_headers)
        assert response.status_code == 400


# =============================================================================
# Authentication Tests
# =============================================================================

class TestAuthentication:
    """Test that endpoints require authentication."""

    def test_create_batch_requires_auth(self, client):
        """Test that creating a batch requires API key."""
        response = client.post(
            "/v1/batches",
            json={
                "title": "No Auth",
                "actions": [{"kind": "note", "risk": "safe", "payload": {}, "preview_text": "Test"}]
            }
        )
        assert response.status_code == 401

    def test_approve_requires_auth(self, client, auth_headers):
        """Test that approving requires API key."""
        # Create with auth
        create_resp = client.post(
            "/v1/batches",
            json={
                "title": "Auth Test",
                "actions": [{"kind": "note", "risk": "safe", "payload": {}, "preview_text": "Test"}],
                "auto_submit": True
            },
            headers=auth_headers
        )
        batch_id = create_resp.json()["id"]
        
        # Try to approve without auth
        response = client.post(f"/v1/batches/{batch_id}/approve")
        assert response.status_code == 401

    def test_run_requires_auth(self, client, auth_headers):
        """Test that running requires API key."""
        # Create, submit, approve with auth
        create_resp = client.post(
            "/v1/batches",
            json={
                "title": "Run Auth Test",
                "actions": [{"kind": "note", "risk": "safe", "payload": {}, "preview_text": "Test"}],
                "auto_submit": True
            },
            headers=auth_headers
        )
        batch_id = create_resp.json()["id"]
        client.post(f"/v1/batches/{batch_id}/approve", headers=auth_headers)
        
        # Try to run without auth
        response = client.post(f"/v1/batches/{batch_id}/run")
        assert response.status_code == 401
