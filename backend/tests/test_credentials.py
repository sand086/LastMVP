"""
Shared test credentials — reads from environment variables with defaults.
Import from this module in all test files instead of hardcoding credentials.
"""
import os

TEST_API_URL = os.environ.get("TEST_API_URL", "https://lastmile-mvp.preview.emergentagent.com")

CREDENTIALS = {
    "developer": {"email": os.environ.get("TEST_DEV_EMAIL", "dev@me.mx"), "password": os.environ.get("TEST_DEV_PASSWORD", "LastMile2026")},
    "coordinator": {"email": os.environ.get("TEST_COORD_EMAIL", "yael@me.mx"), "password": os.environ.get("TEST_COORD_PASSWORD", "LastMile2026")},
    "agent": {"email": os.environ.get("TEST_AGENT_EMAIL", "agente@me.mx"), "password": os.environ.get("TEST_AGENT_PASSWORD", "LastMile2026")},
    "executive": {"email": os.environ.get("TEST_EXEC_EMAIL", "karina@me.mx"), "password": os.environ.get("TEST_EXEC_PASSWORD", "LastMile2026")},
}
