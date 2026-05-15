"""Set env before any `app` import so Settings + engine use the test database."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

_tmp = tempfile.mkdtemp(prefix="ridebot_")
_db_path = Path(_tmp) / "test.db"
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_db_path.as_posix()}"
os.environ["LLM_PROVIDER"] = "mock"

import app.config as app_config

app_config.get_settings.cache_clear()


@pytest.fixture(scope="session")
def app():
    from app.main import app as fastapi_app

    return fastapi_app
