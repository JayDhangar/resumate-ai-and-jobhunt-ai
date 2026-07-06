"""Pluggable job-board sources.

Keyless sources (always on): Remotive, Arbeitnow, RemoteOK, The Muse.
Key-based sources (enabled when the key is set in .env):

* Adzuna   — ADZUNA_APP_ID + ADZUNA_APP_KEY (free at developer.adzuna.com)
* JSearch  — RAPIDAPI_KEY (free tier at rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch);
             aggregates Google-for-Jobs, which indexes LinkedIn, Indeed, Monster, Naukri…
* Jooble   — JOOBLE_API_KEY (free at jooble.org/api/about)

Each source returns normalized ``JobPosting`` objects. Failures are logged and
skipped so one dead board never breaks a search.
"""
from __future__ import annotations

import re
from abc import ABC, abstractmethod

import httpx

from core.config import get_settings
from core.logging_config import get_logger
from models.schemas import JobPosting

logger = get_logger("jobs")

_TAG_RE = re.compile(r"<[^>]+>")


def strip_html(text: str, limit: int = 8000) -> str:
    text = _TAG_RE.sub(" ", text or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def query_words(query: str, max_words: int = 3) -> list[str]:
    return [w for w in re.split(r"\W+", query.lower()) if w][:max_words]


def text_matches(query: str, haystack: str) -> bool:
    """Whole-word match for every query word ('ai' must not match 'maintain')."""
    haystack = haystack.lower()
    return all(re.search(rf"\b{re.escape(w)}\b", haystack) for w in query_words(query))


class JobSource(ABC):
    name: str = "base"
    needs_key: bool = False

    def __init__(self) -> None:
        self.settings = get_settings()
        self.timeout = self.settings.jobs_timeout_seconds

    @property
    def enabled(self) -> bool:
        return True

    @abstractmethod
    def search(self, query: str, location: str = "") -> list[JobPosting]: ...

    def safe_search(self, query: str, location: str = "") -> list[JobPosting]:
        try:
            jobs = self.search(query, location)
            logger.info("%s: %d results for '%s'", self.name, len(jobs), query)
            return jobs
        except Exception as exc:  # noqa: BLE001 - one dead board must not break the search
            logger.warning("%s failed: %s", self.name, exc)
            return []


class RemotiveSource(JobSource):
    name = "remotive"

    def search(self, query: str, location: str = "") -> list[JobPosting]:
        resp = httpx.get(
            "https://remotive.com/api/remote-jobs",
            params={"search": query, "limit": 25},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return [
            JobPosting(
                title=j.get("title", ""),
                company=j.get("company_name", ""),
                location=j.get("candidate_required_location", "Remote"),
                remote=True,
                salary=j.get("salary", ""),
                description=strip_html(j.get("description", "")),
                url=j.get("url", ""),
                source=self.name,
                posted_at=(j.get("publication_date") or "")[:10],
                tags=j.get("tags", [])[:6],
            )
            for j in resp.json().get("jobs", [])
        ]


class ArbeitnowSource(JobSource):
    name = "arbeitnow"

    def search(self, query: str, location: str = "") -> list[JobPosting]:
        resp = httpx.get("https://www.arbeitnow.com/api/job-board-api", timeout=self.timeout)
        resp.raise_for_status()
        out = []
        for j in resp.json().get("data", []):
            haystack = f"{j.get('title','')} {j.get('description','')} {' '.join(j.get('tags', []))}"
            if text_matches(query, haystack):
                out.append(JobPosting(
                    title=j.get("title", ""),
                    company=j.get("company_name", ""),
                    location=j.get("location", ""),
                    remote=bool(j.get("remote")),
                    description=strip_html(j.get("description", "")),
                    url=j.get("url", ""),
                    source=self.name,
                    posted_at="",
                    tags=(j.get("tags") or [])[:6],
                ))
        return out[:20]


class RemoteOKSource(JobSource):
    name = "remoteok"

    def search(self, query: str, location: str = "") -> list[JobPosting]:
        resp = httpx.get(
            "https://remoteok.com/api",
            headers={"User-Agent": "ResuMateAI/1.0 job search"},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        out = []
        for j in resp.json():
            if not isinstance(j, dict) or not j.get("position"):
                continue
            haystack = f"{j.get('position','')} {' '.join(j.get('tags', []))} {j.get('description','')}"
            if text_matches(query, haystack):
                salary_min, salary_max = j.get("salary_min"), j.get("salary_max")
                salary = f"${salary_min:,} – ${salary_max:,}" if salary_min and salary_max else ""
                out.append(JobPosting(
                    title=j.get("position", ""),
                    company=j.get("company", ""),
                    location=j.get("location", "Remote"),
                    remote=True,
                    salary=salary,
                    description=strip_html(j.get("description", "")),
                    url=j.get("url", ""),
                    source=self.name,
                    posted_at=(j.get("date") or "")[:10],
                    tags=(j.get("tags") or [])[:6],
                ))
        return out[:20]


class TheMuseSource(JobSource):
    name = "themuse"

    def search(self, query: str, location: str = "") -> list[JobPosting]:
        params: dict = {"page": 0}
        if location:
            params["location"] = location
        resp = httpx.get("https://www.themuse.com/api/public/jobs", params=params, timeout=self.timeout)
        resp.raise_for_status()
        out = []
        for j in resp.json().get("results", []):
            if not text_matches(query, j.get("name", "")):
                continue
            locations = ", ".join(l.get("name", "") for l in j.get("locations", [])[:2])
            out.append(JobPosting(
                title=j.get("name", ""),
                company=(j.get("company") or {}).get("name", ""),
                location=locations,
                remote="remote" in locations.lower() or "flexible" in locations.lower(),
                description=strip_html(j.get("contents", "")),
                url=(j.get("refs") or {}).get("landing_page", ""),
                source=self.name,
                posted_at=(j.get("publication_date") or "")[:10],
                tags=[level.get("name", "") for level in j.get("levels", [])][:3],
            ))
        return out[:20]


class AdzunaSource(JobSource):
    name = "adzuna"
    needs_key = True

    @property
    def enabled(self) -> bool:
        return bool(self.settings.adzuna_app_id and self.settings.adzuna_app_key)

    def search(self, query: str, location: str = "") -> list[JobPosting]:
        country = self.settings.jobs_default_country or "in"
        params = {
            "app_id": self.settings.adzuna_app_id,
            "app_key": self.settings.adzuna_app_key,
            "what": query,
            "results_per_page": 25,
            "content-type": "application/json",
        }
        if location:
            params["where"] = location
        resp = httpx.get(
            f"https://api.adzuna.com/v1/api/jobs/{country}/search/1",
            params=params, timeout=self.timeout,
        )
        resp.raise_for_status()
        out = []
        for j in resp.json().get("results", []):
            salary_min, salary_max = j.get("salary_min"), j.get("salary_max")
            salary = f"{int(salary_min):,} – {int(salary_max):,}" if salary_min and salary_max else ""
            out.append(JobPosting(
                title=j.get("title", "").replace("<strong>", "").replace("</strong>", ""),
                company=(j.get("company") or {}).get("display_name", ""),
                location=(j.get("location") or {}).get("display_name", ""),
                salary=salary,
                description=strip_html(j.get("description", "")),
                url=j.get("redirect_url", ""),
                source=self.name,
                posted_at=(j.get("created") or "")[:10],
            ))
        return out


COUNTRY_CODES = {
    "india": "in", "united states": "us", "usa": "us", "america": "us",
    "united kingdom": "gb", "uk": "gb", "london": "gb", "germany": "de",
    "canada": "ca", "australia": "au", "singapore": "sg",
    "uae": "ae", "dubai": "ae", "netherlands": "nl", "france": "fr",
}

CODE_TO_COUNTRY = {
    "in": "India", "us": "United States", "gb": "United Kingdom", "de": "Germany",
    "ca": "Canada", "au": "Australia", "sg": "Singapore", "ae": "UAE",
    "nl": "Netherlands", "fr": "France",
}


def jsearch_quota() -> dict:
    """Current calendar-month JSearch usage vs budget (persisted)."""
    from datetime import datetime, timezone

    from services.storage import get_store

    month = datetime.now(timezone.utc).strftime("%Y-%m")
    store = get_store()
    doc = store.get("quota", "jsearch") or {"id": "jsearch", "month": month, "used": 0}
    if doc.get("month") != month:  # new month, reset
        doc = {"id": "jsearch", "month": month, "used": 0}
        store.put("quota", doc)
    budget = get_settings().jsearch_monthly_budget
    return {"month": doc["month"], "used": doc["used"], "budget": budget,
            "remaining": max(0, budget - doc["used"])}


def _jsearch_consume() -> bool:
    """Reserve one JSearch call; False when the monthly budget is exhausted."""
    from services.storage import get_store

    quota = jsearch_quota()
    if quota["remaining"] <= 0:
        logger.warning("JSearch monthly budget (%d) exhausted — skipping call", quota["budget"])
        return False
    get_store().put("quota", {"id": "jsearch", "month": quota["month"], "used": quota["used"] + 1})
    return True


class JSearchSource(JobSource):
    """RapidAPI JSearch v5 — Google-for-Jobs aggregation (LinkedIn/Indeed/Naukri/Monster…)."""

    name = "jsearch"
    needs_key = True

    @property
    def enabled(self) -> bool:
        return bool(self.settings.rapidapi_key)

    def _country_for(self, location: str) -> str:
        loc = location.lower()
        for name, code in COUNTRY_CODES.items():
            if name in loc:
                return code
        return self.settings.jobs_default_country or "in"

    def search(self, query: str, location: str = "") -> list[JobPosting]:
        if not _jsearch_consume():
            return []
        q = f"{query} in {location}" if location else query
        resp = httpx.get(
            "https://jsearch.p.rapidapi.com/search-v2",
            params={"query": q, "num_pages": 1, "country": self._country_for(location)},
            headers={
                "X-RapidAPI-Key": self.settings.rapidapi_key,
                "X-RapidAPI-Host": "jsearch.p.rapidapi.com",
            },
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json().get("data", {})
        # v5 nests results under data.jobs; older versions returned data as a list
        items = data.get("jobs", []) if isinstance(data, dict) else data
        out = []
        for j in items:
            city = j.get("job_city") or ""
            country = j.get("job_country") or ""
            if len(country) == 2:  # expand ISO code so display + location filter work
                country = CODE_TO_COUNTRY.get(country.lower(), country)
            salary = ""
            if j.get("job_min_salary") and j.get("job_max_salary"):
                salary = f"{int(j['job_min_salary']):,} – {int(j['job_max_salary']):,} {j.get('job_salary_currency') or ''}"
            out.append(JobPosting(
                title=j.get("job_title", ""),
                company=j.get("employer_name", ""),
                location=", ".join(x for x in (city, country) if x),
                remote=bool(j.get("job_is_remote")),
                salary=salary,
                description=strip_html(j.get("job_description", "")),
                url=j.get("job_apply_link", ""),
                source=self.name,
                via=(j.get("job_publisher") or "").lower(),
                posted_at=(j.get("job_posted_at_datetime_utc") or "")[:10],
            ))
        return out


class JoobleSource(JobSource):
    name = "jooble"
    needs_key = True

    @property
    def enabled(self) -> bool:
        return bool(self.settings.jooble_api_key)

    def search(self, query: str, location: str = "") -> list[JobPosting]:
        resp = httpx.post(
            f"https://jooble.org/api/{self.settings.jooble_api_key}",
            json={"keywords": query, "location": location},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return [
            JobPosting(
                title=j.get("title", ""),
                company=j.get("company", ""),
                location=j.get("location", ""),
                salary=j.get("salary", ""),
                description=strip_html(j.get("snippet", "")),
                url=j.get("link", ""),
                source=self.name,
                posted_at=(j.get("updated") or "")[:10],
            )
            for j in resp.json().get("jobs", [])[:25]
        ]


def jsearch_salary(job_title: str, location: str) -> dict | None:
    """Estimated salary range from JSearch (counts against the monthly budget)."""
    settings = get_settings()
    if not settings.rapidapi_key or not _jsearch_consume():
        return None
    headers = {
        "X-RapidAPI-Key": settings.rapidapi_key,
        "X-RapidAPI-Host": "jsearch.p.rapidapi.com",
    }
    for path in ("/estimated-salary", "/job-salary", "/estimated-salary-v2"):
        try:
            resp = httpx.get(
                f"https://jsearch.p.rapidapi.com{path}",
                params={"job_title": job_title, "location": location or "India",
                        "location_type": "ANY"},
                headers=headers, timeout=20,
            )
            if resp.status_code == 404:
                continue
            resp.raise_for_status()
            data = resp.json().get("data")
            items = data.get("salaries", data) if isinstance(data, dict) else data
            if not items:
                return None
            item = items[0]
            return {
                "min": item.get("min_salary") or item.get("min_base_salary"),
                "max": item.get("max_salary") or item.get("max_base_salary"),
                "median": item.get("median_salary") or item.get("median_base_salary"),
                "currency": item.get("salary_currency") or "",
                "period": (item.get("salary_period") or "YEAR").lower(),
                "source": f"jsearch ({item.get('publisher_name', 'estimate')})",
            }
        except httpx.HTTPError as exc:
            logger.warning("jsearch salary %s failed: %s", path, exc)
            return None
    return None


def all_sources() -> list[JobSource]:
    return [
        RemotiveSource(), ArbeitnowSource(), RemoteOKSource(), TheMuseSource(),
        AdzunaSource(), JSearchSource(), JoobleSource(),
    ]
