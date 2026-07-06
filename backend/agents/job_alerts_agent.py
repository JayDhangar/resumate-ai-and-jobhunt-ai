"""Agent 9 — Job Alerts.

Saved searches that run on a flexible per-day schedule (daily / weekdays /
weekends / any custom day set) and report only jobs you haven't seen before.

Quota-friendly by design:
* at most ONE live run per saved search per day (the scheduler skips a search
  whose last_run is already today);
* runs share the JobSearchAgent's persistent day-cache, so a manual search and
  an alert for the same query cost a single API call;
* the JSearch monthly budget guard applies underneath everything.
"""
from __future__ import annotations

from datetime import datetime, timezone

from models.schemas import JobPosting, ResumeData, SavedSearch
from services.storage import get_store
from .base_agent import BaseAgent
from .job_search_agent import get_job_search_agent

ALERTS_COLLECTION = "saved_searches"
MAX_SEEN_URLS = 800


class JobAlertsAgent(BaseAgent):
    name = "job_alerts"

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.store = get_store()

    # ------------------------------------------------------------- CRUD

    def list(self) -> list[SavedSearch]:
        searches = [SavedSearch.model_validate(d) for d in self.store.list(ALERTS_COLLECTION)]
        return sorted(searches, key=lambda s: str(s.created_at))

    def get(self, search_id: str) -> SavedSearch | None:
        doc = self.store.get(ALERTS_COLLECTION, search_id)
        return SavedSearch.model_validate(doc) if doc else None

    def save(self, search: SavedSearch) -> SavedSearch:
        self.store.put(ALERTS_COLLECTION, search.model_dump(mode="json"))
        return search

    def delete(self, search_id: str) -> bool:
        return self.store.delete(ALERTS_COLLECTION, search_id)

    # -------------------------------------------------------------- runs

    def run_search(self, search: SavedSearch, force: bool = False) -> dict:
        """Run one saved search and keep only never-seen-before jobs."""
        today = datetime.now(timezone.utc).date()
        if not force and search.last_run and search.last_run.date() == today:
            return {
                "ran": False,
                "detail": "Already ran today — using stored digest (protects your free API quota)",
                "new_jobs": [j.model_dump(mode="json") for j in search.last_new_jobs],
            }

        response = get_job_search_agent().search(
            search.query, search.location, search.remote_only, limit=60
        )
        seen = set(search.seen_urls)
        new_jobs = [j for j in response.jobs if j.url and j.url not in seen]

        if search.resume_id:
            new_jobs = self._score_against_resume(search.resume_id, new_jobs)

        search.seen_urls = (search.seen_urls + [j.url for j in new_jobs])[-MAX_SEEN_URLS:]
        search.last_run = datetime.now(timezone.utc)
        search.last_new_jobs = new_jobs[:25]
        self.save(search)

        emailed = False
        if search.email_digest and new_jobs:
            emailed = self._email_digest(search, new_jobs)

        self.logger.info("Alert '%s': %d new of %d total jobs%s",
                         search.name or search.query, len(new_jobs), response.total,
                         " (digest emailed)" if emailed else "")
        return {
            "ran": True,
            "detail": f"{len(new_jobs)} new job(s) out of {response.total} results",
            "new_jobs": [j.model_dump(mode="json") for j in new_jobs[:25]],
            "emailed": emailed,
        }

    def run_due(self) -> dict:
        """Run every enabled search scheduled for today that hasn't run yet."""
        today = datetime.now(timezone.utc).date()
        weekday = datetime.now().weekday()  # local day-of-week drives the schedule
        ran, skipped = 0, 0
        for search in self.list():
            if not search.enabled or weekday not in search.days:
                continue
            if search.last_run and search.last_run.date() == today:
                skipped += 1
                continue
            try:
                self.run_search(search)
                ran += 1
            except Exception as exc:  # noqa: BLE001 - one bad alert must not stop the rest
                self.logger.warning("Alert '%s' failed: %s", search.name or search.query, exc)
        return {"ran": ran, "skipped": skipped}

    # ------------------------------------------------------------ helpers

    def _score_against_resume(self, resume_id: str, jobs: list[JobPosting]) -> list[JobPosting]:
        try:
            from agents.coordinator import get_coordinator

            resume: ResumeData = get_coordinator().get_resume(resume_id).data
        except Exception:  # noqa: BLE001
            return jobs
        agent = get_job_search_agent()
        if not jobs:
            return jobs
        texts = [f"{j.title} at {j.company}. {j.description[:1200]}" for j in jobs]
        sims = agent._similarities(agent._profile_text(resume), texts)
        lo, hi = min(sims), max(sims)
        spread = (hi - lo) or 1.0
        skills = resume.flat_skills()
        for job, sim in zip(jobs, sims):
            job.matching_skills = agent._matching_skills(skills, f"{job.title} {job.description}")
            semantic = 35 + 60 * (sim - lo) / spread
            job.match_score = int(max(0, min(100, 0.75 * semantic + 0.25 * min(100, len(job.matching_skills) * 14))))
        jobs.sort(key=lambda j: (j.match_score or 0, j.trust.score), reverse=True)
        return jobs

    def _email_digest(self, search: SavedSearch, jobs: list[JobPosting]) -> bool:
        from services.email_service import email_configured, send_email

        if not email_configured():
            return False
        lines = [f"JobHunt AI daily digest — {len(jobs)} new job(s) for “{search.name or search.query}”", ""]
        for job in jobs[:15]:
            match = f" · {job.match_score}% match" if job.match_score is not None else ""
            lines.append(f"• {job.title} @ {job.company} ({job.location or 'n/a'}){match}")
            lines.append(f"  apply: {job.url}")
            lines.append("")
        lines.append("— sent automatically by JobHunt AI")
        try:
            from core.config import get_settings

            send_email(get_settings().smtp_user, f"🔔 {len(jobs)} new jobs: {search.name or search.query}",
                       "\n".join(lines))
            return True
        except Exception as exc:  # noqa: BLE001
            self.logger.warning("Digest email failed: %s", exc)
            return False


_agent: JobAlertsAgent | None = None


def get_job_alerts_agent() -> JobAlertsAgent:
    global _agent
    if _agent is None:
        _agent = JobAlertsAgent()
    return _agent
