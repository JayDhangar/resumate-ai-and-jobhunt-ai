"""REST endpoints for the JobHunt AI platform."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from agents.coordinator import get_coordinator
from agents.job_search_agent import get_job_search_agent

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


class MatchRequest(BaseModel):
    resume_id: str
    query: str = ""
    location: str = ""
    remote_only: bool = False
    limit: int = 40


class JobPayload(BaseModel):
    title: str = ""
    company: str = ""
    location: str = ""
    description: str = ""
    url: str = ""


class FitRequest(BaseModel):
    resume_id: str
    job: JobPayload


class EmailDraftRequest(BaseModel):
    resume_id: str
    job: JobPayload
    tone: str = "professional"
    previous_subject: str = ""


class SendEmailRequest(BaseModel):
    to: str
    subject: str
    body: str
    resume_id: str = ""            # set with attach_resume to attach the PDF
    attach_resume: bool = False
    job: JobPayload | None = None  # when present, the application is auto-logged


class TailorRequest(BaseModel):
    resume_id: str
    job: JobPayload


class SaveApplicationRequest(BaseModel):
    job: JobPayload
    source: str = ""
    resume_id: str = ""
    status: str = "saved"


class UpdateApplicationRequest(BaseModel):
    status: str = ""
    notes: str | None = None


@router.get("/search")
def search_jobs(
    q: str,
    location: str = "",
    remote_only: bool = False,
    source: str = "",
    exp: str = "",       # experience bucket: 0-1 | 1-3 | 3-5 | 5+
    limit: int = 60,
):
    """Search one or more roles — separate multiple with '|' (e.g. 'AI Engineer|Data Scientist')."""
    agent = get_job_search_agent()
    queries = [part for part in q.split("|") if part.strip()]
    if len(queries) > 1:
        return agent.search_multi(queries, location, remote_only, exp, min(limit, 100)).model_dump(mode="json")
    response = agent.search(q, location, remote_only, source, min(limit, 100))
    return agent.filter_experience(response, exp, min(limit, 100)).model_dump(mode="json")


@router.post("/match")
def match_jobs(payload: MatchRequest):
    """RAG-style matching: rank live job postings by similarity to a stored resume."""
    record = get_coordinator().get_resume(payload.resume_id)
    response = get_job_search_agent().match(
        record.data,
        query=payload.query,
        location=payload.location,
        remote_only=payload.remote_only,
        limit=min(payload.limit, 60),
    )
    body = response.model_dump(mode="json")
    body["matched_resume"] = {"id": record.id, "title": record.title, "name": record.data.name}
    return body


@router.post("/analyze-fit")
def analyze_fit(payload: FitRequest):
    """Resume-vs-job fit: score, matched/missing skills, alignment suggestions."""
    from models.schemas import JobPosting
    from services.apply_service import analyze_fit as run_fit

    record = get_coordinator().get_resume(payload.resume_id)
    job = JobPosting(**payload.job.model_dump())
    return run_fit(record.data, job)


@router.post("/draft-email")
def draft_application_email(payload: EmailDraftRequest):
    """AI-draft an application email from the stored resume + job posting."""
    from models.schemas import JobPosting
    from services.apply_service import draft_email

    record = get_coordinator().get_resume(payload.resume_id)
    job = JobPosting(**payload.job.model_dump())
    return draft_email(record.data, job, payload.tone, payload.previous_subject)


@router.post("/tailor")
def tailor_resume(payload: TailorRequest):
    """Rewrite the resume to target a specific job posting (saved as a new version)."""
    coordinator = get_coordinator()
    job = payload.job
    instructions = (
        f"Tailor this resume for the following job posting. Rewrite the professional summary to "
        f"target the role, reorder/emphasise skills that match, and reframe experience bullets "
        f"using the posting's keywords where truthful. NEVER invent skills, employers or experience "
        f"the candidate does not have.\n\n"
        f"JOB: {job.title} at {job.company} ({job.location})\n"
        f"DESCRIPTION: {job.description[:2500]}"
    )
    record, extra = coordinator.edit_resume(payload.resume_id, instructions, save_version=True)
    latest = record.versions[-1] if record.versions else None
    if latest is not None:
        latest.label = f"Tailored for {job.title} @ {job.company}"[:80]
        coordinator._save(record)
    return {
        "resume": record.model_dump(mode="json"),
        "version": latest.version if latest else None,
        "scores": extra.get("scores", {}),
    }


class CoverLetterRequest(BaseModel):
    resume_id: str
    job: JobPayload
    tone: str = "professional"
    previous_body: str = ""


class CoverLetterPdfRequest(BaseModel):
    resume_id: str
    title: str
    body: str


@router.post("/cover-letter")
def generate_cover_letter(payload: CoverLetterRequest):
    from models.schemas import JobPosting
    from services.apply_service import draft_cover_letter

    record = get_coordinator().get_resume(payload.resume_id)
    job = JobPosting(**payload.job.model_dump())
    return draft_cover_letter(record.data, job, payload.tone, payload.previous_body)


@router.post("/cover-letter/pdf")
def cover_letter_pdf(payload: CoverLetterPdfRequest):
    from pathlib import Path

    from fastapi.responses import FileResponse

    from core.config import get_settings
    from services.apply_service import cover_letter_html

    coordinator = get_coordinator()
    record = coordinator.get_resume(payload.resume_id)
    html = cover_letter_html(payload.title, payload.body, record.data.name or record.title)
    dest = Path(get_settings().generated_dir) / f"cover_letter_{record.id[:8]}.pdf"
    coordinator.exporter.to_pdf(html, dest)
    safe = "".join(c for c in (record.data.name or "cover_letter") if c.isalnum() or c in " -_").strip()
    return FileResponse(str(dest), media_type="application/pdf",
                        filename=f"{safe.replace(' ', '_')}_Cover_Letter.pdf")


@router.post("/send-email")
def send_application_email(payload: SendEmailRequest):
    from services.email_service import send_email

    attachment_path = ""
    attachment_name = ""
    if payload.attach_resume and payload.resume_id:
        coordinator = get_coordinator()
        record = coordinator.get_resume(payload.resume_id)
        result = coordinator.generate(payload.resume_id, formats=["pdf"])
        attachment_path = result["files"].get("pdf", "")
        safe = "".join(c for c in (record.data.name or record.title) if c.isalnum() or c in " -_").strip()
        attachment_name = f"{safe.replace(' ', '_') or 'Resume'}_Resume.pdf"

    sent = send_email(payload.to, payload.subject, payload.body, attachment_path, attachment_name)

    if payload.job is not None and payload.job.title:
        _log_application(payload, status="applied")
    return sent


def _log_application(payload: SendEmailRequest, status: str) -> None:
    from datetime import datetime, timezone

    from models.schemas import ApplicationRecord

    coordinator = get_coordinator()
    resume_title = ""
    if payload.resume_id:
        try:
            resume_title = coordinator.get_resume(payload.resume_id).title
        except Exception:  # noqa: BLE001
            pass
    record = ApplicationRecord(
        job_title=payload.job.title,
        company=payload.job.company,
        location=payload.job.location,
        url=payload.job.url,
        status=status,
        resume_id=payload.resume_id,
        resume_title=resume_title,
        email_to=payload.to,
        email_subject=payload.subject,
        applied_at=datetime.now(timezone.utc),
    )
    coordinator.store.put("applications", record.model_dump(mode="json"))


# ------------------------------------------------------------- applications

@router.get("/applications")
def list_applications():
    from models.schemas import ApplicationRecord

    records = [ApplicationRecord.model_validate(d)
               for d in get_coordinator().store.list("applications")]
    records.sort(key=lambda r: str(r.updated_at), reverse=True)
    return [r.model_dump(mode="json") for r in records]


@router.post("/applications")
def save_application(payload: SaveApplicationRequest):
    from models.schemas import ApplicationRecord

    coordinator = get_coordinator()
    # avoid duplicate saves of the same posting
    for doc in coordinator.store.list("applications"):
        if doc.get("url") and doc.get("url") == payload.job.url:
            return {"saved": False, "detail": "Already tracked", "id": doc["id"]}
    resume_title = ""
    if payload.resume_id:
        try:
            resume_title = coordinator.get_resume(payload.resume_id).title
        except Exception:  # noqa: BLE001
            pass
    record = ApplicationRecord(
        job_title=payload.job.title, company=payload.job.company,
        location=payload.job.location, url=payload.job.url,
        source=payload.source, status=payload.status,
        resume_id=payload.resume_id, resume_title=resume_title,
    )
    coordinator.store.put("applications", record.model_dump(mode="json"))
    return {"saved": True, "id": record.id}


@router.patch("/applications/{application_id}")
def update_application(application_id: str, payload: UpdateApplicationRequest):
    from datetime import datetime, timezone

    from core.exceptions import NotFoundError
    from models.schemas import ApplicationRecord

    store = get_coordinator().store
    doc = store.get("applications", application_id)
    if doc is None:
        raise NotFoundError(f"Application '{application_id}' not found")
    record = ApplicationRecord.model_validate(doc)
    if payload.status:
        record.status = payload.status
        if payload.status == "applied" and record.applied_at is None:
            record.applied_at = datetime.now(timezone.utc)
    if payload.notes is not None:
        record.notes = payload.notes
    record.updated_at = datetime.now(timezone.utc)
    store.put("applications", record.model_dump(mode="json"))
    return record.model_dump(mode="json")


@router.delete("/applications/{application_id}")
def delete_application(application_id: str):
    return {"deleted": get_coordinator().store.delete("applications", application_id)}


@router.get("/email-status")
def email_status():
    from services.email_service import email_configured, masked_sender

    configured = email_configured()
    return {"configured": configured, "sender": masked_sender() if configured else ""}


# ------------------------------------------------------------- job alerts

class SavedSearchRequest(BaseModel):
    name: str = ""
    query: str
    location: str = ""
    remote_only: bool = False
    resume_id: str = ""
    days: list[int] = [0, 1, 2, 3, 4, 5, 6]
    enabled: bool = True
    email_digest: bool = False


@router.get("/alerts")
def list_alerts():
    from agents.job_alerts_agent import get_job_alerts_agent

    return [s.model_dump(mode="json") for s in get_job_alerts_agent().list()]


@router.post("/alerts")
def create_alert(payload: SavedSearchRequest):
    from agents.job_alerts_agent import get_job_alerts_agent
    from models.schemas import SavedSearch

    search = SavedSearch(**payload.model_dump())
    if not search.name:
        search.name = f"{search.query}{' · ' + search.location if search.location else ''}"
    return get_job_alerts_agent().save(search).model_dump(mode="json")


@router.put("/alerts/{alert_id}")
def update_alert(alert_id: str, payload: SavedSearchRequest):
    from agents.job_alerts_agent import get_job_alerts_agent
    from core.exceptions import NotFoundError

    agent = get_job_alerts_agent()
    existing = agent.get(alert_id)
    if existing is None:
        raise NotFoundError(f"Alert '{alert_id}' not found")
    updated = existing.model_copy(update=payload.model_dump())
    return agent.save(updated).model_dump(mode="json")


@router.delete("/alerts/{alert_id}")
def delete_alert(alert_id: str):
    from agents.job_alerts_agent import get_job_alerts_agent

    return {"deleted": get_job_alerts_agent().delete(alert_id)}


@router.post("/alerts/{alert_id}/run")
def run_alert(alert_id: str, force: bool = False):
    from agents.job_alerts_agent import get_job_alerts_agent
    from core.exceptions import NotFoundError

    agent = get_job_alerts_agent()
    search = agent.get(alert_id)
    if search is None:
        raise NotFoundError(f"Alert '{alert_id}' not found")
    return agent.run_search(search, force=force)


@router.get("/quota")
def quota_status():
    from services.job_sources import jsearch_quota

    return {"jsearch": jsearch_quota()}


@router.get("/sources")
def job_sources():
    """Which job boards are active; key-based ones show how to enable them."""
    return get_job_search_agent().sources_status()
