"""Shared pytest fixtures: isolated storage, offline LLM, clean caches."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    """Every test runs offline against a throwaway SQLite database."""
    monkeypatch.setenv("LLM_PROVIDER", "none")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("MONGODB_URL", "")
    monkeypatch.setenv("TEMPLATE_SEARCH_ENABLED", "false")
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("GENERATED_DIR", str(tmp_path / "generated"))
    monkeypatch.setenv("UPLOADS_DIR", str(tmp_path / "generated" / "uploads"))
    monkeypatch.setenv("DOWNLOADED_TEMPLATES_DIR", str(tmp_path / "downloaded"))
    monkeypatch.setenv("UPLOADED_TEMPLATES_DIR", str(tmp_path / "uploaded"))

    from core.config import get_settings
    from services import llm_service, storage

    get_settings.cache_clear()
    storage.reset_store()
    llm_service.reset_llm()

    from agents import coordinator

    coordinator.reset_coordinator()
    yield
    storage.reset_store()
    get_settings.cache_clear()


@pytest.fixture
def sample_resume():
    from services.sample_data import SAMPLE_RESUME

    return SAMPLE_RESUME.model_copy(deep=True)


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from main import app

    with TestClient(app) as test_client:
        yield test_client
