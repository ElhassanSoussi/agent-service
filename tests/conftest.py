"""
Pytest configuration and fixtures.
"""
import os
import sys

# Set test API key before importing app
os.environ["AGENT_API_KEY"] = "test-api-key"
os.environ["AGENT_ADMIN_KEY"] = "test-admin-key"
os.environ["AGENT_KEY_HASH_SECRET"] = "test-hash-secret"

import pytest
from fastapi.testclient import TestClient

# Add parent directory to path
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


@pytest.fixture
def invalid_auth_headers():
    """Return invalid authentication headers."""
    return {"X-API-Key": "invalid-key"}
