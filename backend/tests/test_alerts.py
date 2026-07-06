"""Job alerts, day-cache quota protection, and cover letter fallback."""
from datetime import datetime, timezone

import pytest

from models.schemas import JobPosting, JobSearchResponse, SavedSearch


@pytest.fixture
def alerts_agent(monkeypatch):
    from agents.job_alerts_agent import JobAlertsAgent

    agent = JobAlertsAgent()
    fake_jobs = [
        JobPosting(title="AI Engineer", company="Acme", url="https://a.example/1"),
        JobPosting(title="ML Engineer", company="Beta", url="https://a.example/2"),
    ]
    monkeypatch.setattr(
        "agents.job_search_agent.JobSearchAgent.search",
        lambda self, q, loc="", remote=False, source="", limit=60: JobSearchResponse(
            query=q, total=len(fake_jobs), jobs=fake_jobs
        ),
    )
    return agent


def test_alert_reports_only_new_jobs(alerts_agent):
    search = alerts_agent.save(SavedSearch(query="ai engineer"))
    first = alerts_agent.run_search(search, force=True)
    assert first["ran"] is True
    assert len(first["new_jobs"]) == 2

    # second run same day: guarded, returns stored digest without an API call
    stored = alerts_agent.get(search.id)
    second = alerts_agent.run_search(stored)
    assert second["ran"] is False

    # forced re-run: everything already seen -> 0 new
    third = alerts_agent.run_search(alerts_agent.get(search.id), force=True)
    assert third["ran"] is True
    assert len(third["new_jobs"]) == 0


def test_run_due_respects_schedule(alerts_agent):
    today = datetime.now().weekday()
    off_day = (today + 3) % 7
    alerts_agent.save(SavedSearch(query="scheduled", days=[today]))
    alerts_agent.save(SavedSearch(query="not-today", days=[off_day]))
    alerts_agent.save(SavedSearch(query="disabled", days=[today], enabled=False))
    result = alerts_agent.run_due()
    assert result["ran"] == 1


def test_day_cache_prevents_repeat_source_calls(monkeypatch):
    from agents.job_search_agent import JobSearchAgent

    calls = {"n": 0}

    class FakeSource:
        name = "fake"
        enabled = True
        needs_key = False

        def safe_search(self, query, location=""):
            calls["n"] += 1
            return [JobPosting(title="AI Engineer", company="X", url="https://x.example/1",
                               description="ai engineer role")]

    monkeypatch.setattr("agents.job_search_agent.all_sources", lambda: [FakeSource()])
    agent = JobSearchAgent()
    agent.search("ai engineer")
    agent._cache.clear()  # simulate a fresh process (in-memory cache gone)
    agent.search("ai engineer")  # served from the persistent day-cache
    assert calls["n"] == 1


def test_jsearch_quota_counter(monkeypatch):
    from services.job_sources import _jsearch_consume, jsearch_quota

    start = jsearch_quota()
    assert start["used"] == 0
    assert _jsearch_consume() is True
    assert jsearch_quota()["used"] == 1

    monkeypatch.setattr("core.config.get_settings",
                        lambda: type("S", (), {"jsearch_monthly_budget": 1})())
    # budget of 1 already consumed -> next call refused
    from services import job_sources
    monkeypatch.setattr(job_sources, "get_settings",
                        lambda: type("S", (), {"jsearch_monthly_budget": 1})())
    assert _jsearch_consume() is False


def test_cover_letter_template_fallback(sample_resume):
    from services.apply_service import draft_cover_letter

    job = JobPosting(title="Platform Engineer", company="Acme", description="Python role")
    letter = draft_cover_letter(sample_resume, job)
    assert letter["source"] == "template"
    assert "Platform Engineer" in letter["body"]
    assert "Sincerely" in letter["body"]
    assert sample_resume.name in letter["body"]
