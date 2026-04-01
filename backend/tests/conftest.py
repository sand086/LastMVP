"""
Shared test fixtures for LastMile OS tests.
Credentials are loaded from environment variables with test defaults.
"""
import os
import pytest

# Test credentials from environment (never hardcode in test files)
TEST_API_URL = os.environ.get("TEST_API_URL", "https://lastmile-mvp.preview.emergentagent.com")
TEST_DEV_EMAIL = os.environ.get("TEST_DEV_EMAIL", "dev@me.mx")
TEST_DEV_PASSWORD = os.environ.get("TEST_DEV_PASSWORD", "LastMile2026")
TEST_AGENT_EMAIL = os.environ.get("TEST_AGENT_EMAIL", "agente@me.mx")
TEST_AGENT_PASSWORD = os.environ.get("TEST_AGENT_PASSWORD", "LastMile2026")
TEST_COORD_EMAIL = os.environ.get("TEST_COORD_EMAIL", "yael@me.mx")
TEST_COORD_PASSWORD = os.environ.get("TEST_COORD_PASSWORD", "LastMile2026")
TEST_EXEC_EMAIL = os.environ.get("TEST_EXEC_EMAIL", "karina@me.mx")
TEST_EXEC_PASSWORD = os.environ.get("TEST_EXEC_PASSWORD", "LastMile2026")


@pytest.fixture
def api_url():
    return TEST_API_URL


@pytest.fixture
def dev_credentials():
    return {"email": TEST_DEV_EMAIL, "password": TEST_DEV_PASSWORD}


@pytest.fixture
def agent_credentials():
    return {"email": TEST_AGENT_EMAIL, "password": TEST_AGENT_PASSWORD}


@pytest.fixture
def coord_credentials():
    return {"email": TEST_COORD_EMAIL, "password": TEST_COORD_PASSWORD}


@pytest.fixture
def exec_credentials():
    return {"email": TEST_EXEC_EMAIL, "password": TEST_EXEC_PASSWORD}
