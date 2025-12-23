import os
import traceback
os.environ["AGENT_API_KEY"] = "test-api-key"
os.environ["AGENT_ADMIN_KEY"] = "test-admin-key"
os.environ["AGENT_KEY_HASH_SECRET"] = "test-hash-secret"

from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from main import app

try:
    with patch("app.api.builder.run_builder_job_background", new_callable=AsyncMock):
        client = TestClient(app, raise_server_exceptions=True)
        response = client.post(
            "/builder/run",
            headers={"X-API-Key": "test-api-key"},
            json={
                "repo_url": "https://github.com/owner/repo",
                "prompt": "Add a new feature to the main module",
            }
        )
        print(f"Status: {response.status_code}")
        print(f"Body: {response.text}")
except Exception as e:
    print(f"Exception: {e}")
    traceback.print_exc()
