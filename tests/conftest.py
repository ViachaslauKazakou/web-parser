import os

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["PARSER_ALLOWED_HOSTS"] = "searchengines.guru"
os.environ["MAX_REQUEST_BODY_BYTES"] = "4096"

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client
