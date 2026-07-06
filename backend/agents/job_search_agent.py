"""Agent 8 — Job Search.

Fans a query out across every enabled job source in parallel, normalizes and
deduplicates the postings, scores each one for genuineness, and returns a
ranked list with direct apply links. Results are cached briefly so repeated
searches don't hammer the boards.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from models.schemas import JobPosting, JobSearchResponse, ResumeData
from services.embedding_service import cosine, get_embedder, tfidf_similarities
from services.job_sources import all_sources, query_words
from services.trust_service import score_job
from .base_agent import BaseAgent


EXP_RANGE_RE = re.compile(r"(\d{1,2})\s*(?:-|–|—|to)\s*(\d{1,2})\s*\+?\s*(?:years?|yrs?)\b", re.I)
EXP_PLUS_RE = re.compile(r"(\d{1,2})\s*\+\s*(?:years?|yrs?)\b", re.I)
EXP_MIN_RE = re.compile(r"(?:at least|minimum(?: of)?|min\.?)\s*(\d{1,2})\s*(?:years?|yrs?)\b", re.I)
EXP_BARE_RE = re.compile(r"(\d{1,2})\s*(?:years?|yrs?)(?:\s+of)?\s+(?:experience|exp)\b", re.I)

EXP_BUCKETS = {"0-1": (0, 1), "1-3": (1, 3), "3-5": (3, 5), "5+": (5, 99)}


def required_experience(job: JobPosting) -> tuple[int, int] | None:
    """Infer the years-of-experience requirement from the posting text."""
    text = f"{job.title} {job.description}"
    if re.search(r"\bfreshers?\b|\bentry[- ]level\b|\bno experience\b", text, re.I):
        return (0, 1)
    if match := EXP_RANGE_RE.search(text):
        low, high = int(match.group(1)), int(match.group(2))
        return (min(low, high), max(low, high))
    if match := EXP_PLUS_RE.search(text):
        return (int(match.group(1)), 99)
    if match := EXP_MIN_RE.search(text):
        return (int(match.group(1)), 99)
    if match := EXP_BARE_RE.search(text):
        return (int(match.group(1)), 99)
    return None


def matches_experience(job: JobPosting, bucket: str) -> bool:
    """True when the posting fits the bucket — unknown requirements are kept."""
    wanted = EXP_BUCKETS.get(bucket)
    if wanted is None:
        return True
    required = required_experience(job)
    if required is None:
        return True  # no stated requirement — don't hide it
    return required[0] <= wanted[1] and required[1] >= wanted[0]


def relevance(job: JobPosting, query: str) -> int:
    """Title hits weigh most, then tags, then description."""
    score = 0
    title = job.title.lower()
    desc = job.description.lower()
    tags = " ".join(job.tags).lower()
    for word in query_words(query, max_words=5):
        pattern = rf"\b{re.escape(word)}\b"
        if re.search(pattern, title):
            score += 10
        elif re.search(pattern, tags):
            score += 5
        elif re.search(pattern, desc):
            score += 2
    return score

CACHE_TTL_SECONDS = 600


class JobSearchAgent(BaseAgent):
    name = "job_search"

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._cache: dict[tuple, tuple[float, JobSearchResponse]] = {}

    def sources_status(self) -> dict[str, dict]:
        return {
            s.name: {"enabled": s.enabled, "needs_key": s.needs_key}
            for s in all_sources()
        }

    def search(
        self,
        query: str,
        location: str = "",
        remote_only: bool = False,
        source: str = "",
        limit: int = 60,
    ) -> JobSearchResponse:
        key = (query.lower().strip(), location.lower().strip(), remote_only, source)
        cached = self._cache.get(key)
        if cached and time.time() - cached[0] < CACHE_TTL_SECONDS:
            return cached[1]
        # persistent day-cache: identical searches within ~a day reuse stored
        # results instead of burning free-plan API quota (results barely change intraday)
        day_cached = self._day_cache_get(key)
        if day_cached is not None:
            self._cache[key] = (time.time(), day_cached)
            return day_cached

        sources = [s for s in all_sources() if s.enabled]
        if source:
            sources = [s for s in sources if s.name == source]
        used: list[str] = []
        jobs: list[JobPosting] = []
        with ThreadPoolExecutor(max_workers=len(sources) or 1) as pool:
            futures = {pool.submit(s.safe_search, query, location): s for s in sources}
            for future in as_completed(futures):
                result = future.result()
                if result:
                    used.append(futures[future].name)
                jobs.extend(result)

        jobs = self._dedupe(jobs)
        if remote_only:
            jobs = [j for j in jobs if j.remote]
        if location.strip():
            jobs = [j for j in jobs if self._location_matches(j, location)]
        scored: list[tuple[int, JobPosting]] = []
        for job in jobs:
            job.trust = score_job(job)
            rel = relevance(job, query)
            if rel >= 2:  # drop postings that merely mention a query word in passing
                scored.append((rel, job))
        # rank: relevance first, then trust, then freshness
        scored.sort(key=lambda pair: (pair[0], pair[1].trust.score, pair[1].posted_at or ""), reverse=True)
        jobs = [job for _, job in scored][:limit]

        response = JobSearchResponse(
            query=query,
            location=location,
            total=len(jobs),
            sources_used=sorted(used),
            sources_available=[s.name for s in all_sources() if s.enabled],
            jobs=jobs,
        )
        self._cache[key] = (time.time(), response)
        if len(self._cache) > 50:
            oldest = min(self._cache, key=lambda k: self._cache[k][0])
            del self._cache[oldest]
        self._day_cache_put(key, response)
        return response

    # ------------------------------------------------------ persistent cache

    @staticmethod
    def _cache_doc_id(key: tuple) -> str:
        return "search-" + hashlib.sha1(json.dumps(key).encode()).hexdigest()[:16]

    def _day_cache_get(self, key: tuple) -> JobSearchResponse | None:
        from core.config import get_settings
        from services.storage import get_store

        doc = get_store().get("job_cache", self._cache_doc_id(key))
        if doc is None:
            return None
        try:
            age_hours = (
                datetime.now(timezone.utc)
                - datetime.fromisoformat(doc["cached_at"])
            ).total_seconds() / 3600
        except (KeyError, ValueError):
            return None
        if age_hours > get_settings().jobs_cache_hours:
            return None
        return JobSearchResponse.model_validate(doc["response"])

    def _day_cache_put(self, key: tuple, response: JobSearchResponse) -> None:
        from services.storage import get_store

        if not response.jobs:  # don't pin empty results for a whole day
            return
        get_store().put("job_cache", {
            "id": self._cache_doc_id(key),
            "cached_at": datetime.now(timezone.utc).isoformat(),
            "response": response.model_dump(mode="json"),
        })

    def search_multi(
        self,
        queries: list[str],
        location: str = "",
        remote_only: bool = False,
        exp_bucket: str = "",
        limit: int = 60,
    ) -> JobSearchResponse:
        """Search several roles at once; each query has its own day-cache entry,
        results are merged, deduped and re-ranked by best relevance across roles."""
        queries = [q.strip() for q in queries if q.strip()][:5] or ["software engineer"]
        if len(queries) == 1:
            return self.filter_experience(
                self.search(queries[0], location, remote_only, limit=limit), exp_bucket, limit
            )
        merged: list[JobPosting] = []
        used: set[str] = set()
        available: list[str] = []
        for query in queries:
            response = self.search(query, location, remote_only, limit=limit)
            merged.extend(response.jobs)
            used.update(response.sources_used)
            available = response.sources_available
        merged = self._dedupe(merged)
        scored = [(max(relevance(j, q) for q in queries), j) for j in merged]
        scored.sort(key=lambda pair: (pair[0], pair[1].trust.score, pair[1].posted_at or ""), reverse=True)
        response = JobSearchResponse(
            query=" | ".join(queries),
            location=location,
            total=len(scored),
            sources_used=sorted(used),
            sources_available=available,
            jobs=[j for _, j in scored][:limit * 2],
        )
        return self.filter_experience(response, exp_bucket, limit)

    def filter_experience(self, response: JobSearchResponse, bucket: str, limit: int = 60) -> JobSearchResponse:
        """Apply the years-of-experience filter AFTER caching so buckets never
        trigger extra API calls."""
        jobs = [j for j in response.jobs if matches_experience(j, bucket)] if bucket else response.jobs
        jobs = jobs[:limit]
        return response.model_copy(update={"jobs": jobs, "total": len(jobs)})

    # ------------------------------------------------------------- matching

    def match(
        self,
        resume: ResumeData,
        query: str = "",
        location: str = "",
        remote_only: bool = False,
        limit: int = 40,
    ) -> JobSearchResponse:
        """RAG-style matching: embed the resume profile and every job posting,
        rank by cosine similarity blended with skill overlap."""
        profile = self._profile_text(resume)
        search_query = query.strip() or resume.headline or ", ".join(resume.flat_skills()[:4]) or "software engineer"
        base = self.search(search_query, location, remote_only, limit=80)
        jobs = [job.model_copy(deep=True) for job in base.jobs]
        if not jobs:
            return base

        job_texts = [f"{j.title} at {j.company}. {j.description[:1500]}" for j in jobs]
        sims = self._similarities(profile, job_texts)

        lo, hi = min(sims), max(sims)
        spread = (hi - lo) or 1.0
        skills = resume.flat_skills()
        for job, sim in zip(jobs, sims):
            semantic = 35 + 60 * (sim - lo) / spread  # 35-95 within this result set
            overlap = self._matching_skills(skills, f"{job.title} {job.description}")
            job.matching_skills = overlap
            skill_bonus = min(100.0, len(overlap) * 14.0)
            job.match_score = int(max(0, min(100, 0.75 * semantic + 0.25 * skill_bonus)))

        jobs.sort(key=lambda j: (j.match_score or 0, j.trust.score), reverse=True)
        return JobSearchResponse(
            query=search_query,
            location=location,
            total=min(len(jobs), limit),
            sources_used=base.sources_used,
            sources_available=base.sources_available,
            jobs=jobs[:limit],
        )

    def _profile_text(self, resume: ResumeData) -> str:
        parts = [resume.headline, resume.summary, ", ".join(resume.flat_skills())]
        for exp in resume.experience:
            parts.append(f"{exp.title} at {exp.company}. " + " ".join(exp.bullets))
        for proj in resume.projects:
            parts.append(f"{proj.name}: {proj.description} {', '.join(proj.technologies)}")
        return "\n".join(p for p in parts if p)[:8000]

    def _similarities(self, profile: str, job_texts: list[str]) -> list[float]:
        embedder = get_embedder()
        if embedder.available:
            try:
                vectors = embedder.embed([profile] + job_texts)
                return [cosine(vectors[0], v) for v in vectors[1:]]
            except Exception as exc:  # noqa: BLE001
                self.logger.warning("Embedding failed (%s); using TF-IDF fallback", exc)
        return tfidf_similarities(profile, job_texts)

    GLOBAL_LOCATION_HINTS = ("anywhere", "worldwide", "global", "work from anywhere")

    @staticmethod
    def _location_matches(job: JobPosting, location: str) -> bool:
        """Keep jobs in the requested place, plus truly location-free remote roles.

        Region-locked remote postings (e.g. 'Remote · Brazil') are excluded when
        the user asked for a different location.
        """
        wanted = location.lower().strip()
        job_loc = (job.location or "").lower()
        if not job_loc:
            return job.remote  # unspecified location: keep only if remote
        if any(hint in job_loc for hint in JobSearchAgent.GLOBAL_LOCATION_HINTS):
            return True
        words = [w for w in re.split(r"\W+", wanted) if len(w) > 1]
        return any(re.search(rf"\b{re.escape(w)}\b", job_loc) for w in words)

    @staticmethod
    def _matching_skills(skills: list[str], job_text: str) -> list[str]:
        job_text = job_text.lower()
        found = []
        for skill in skills:
            cleaned = skill.strip()
            if len(cleaned) < 2:
                continue
            if re.search(rf"(?<![a-z0-9]){re.escape(cleaned.lower())}(?![a-z0-9])", job_text):
                found.append(cleaned)
        return found[:8]

    @staticmethod
    def _normalize(text: str) -> str:
        return re.sub(r"[^a-z0-9]+", "", text.lower())

    def _dedupe(self, jobs: list[JobPosting]) -> list[JobPosting]:
        seen: set[tuple[str, str]] = set()
        out: list[JobPosting] = []
        for job in jobs:
            key = (self._normalize(job.title)[:60], self._normalize(job.company)[:40])
            if key in seen:
                continue
            seen.add(key)
            out.append(job)
        return out


_agent: JobSearchAgent | None = None


def get_job_search_agent() -> JobSearchAgent:
    global _agent
    if _agent is None:
        _agent = JobSearchAgent()
    return _agent
