"""REST endpoints for resumes: upload, CRUD, AI edit, versions, scores."""
from __future__ import annotations

from fastapi import APIRouter, Body, File, UploadFile

from agents.coordinator import get_coordinator
from models.schemas import (
    EditRequest,
    OptimizeRequest,
    SelectTemplateRequest,
    UpdateResumeRequest,
)

router = APIRouter(prefix="/api/resumes", tags=["resumes"])


@router.post("/upload")
async def upload_resume(file: UploadFile = File(...)):
    content = await file.read()
    record = get_coordinator().upload_resume(content, file.filename or "resume.pdf")
    return record.model_dump(mode="json")


@router.post("")
def create_resume(title: str = Body("New Resume", embed=True)):
    return get_coordinator().create_blank_resume(title).model_dump(mode="json")


@router.get("")
def list_resumes():
    return [r.model_dump(mode="json") for r in get_coordinator().list_resumes()]


@router.get("/{resume_id}")
def get_resume(resume_id: str):
    return get_coordinator().get_resume(resume_id).model_dump(mode="json")


@router.put("/{resume_id}")
def update_resume(resume_id: str, payload: UpdateResumeRequest):
    record = get_coordinator().update_resume(
        resume_id, payload.data, payload.save_version, payload.change_note
    )
    return record.model_dump(mode="json")


@router.delete("/{resume_id}")
def delete_resume(resume_id: str):
    deleted = get_coordinator().delete_resume(resume_id)
    return {"deleted": deleted}


@router.post("/{resume_id}/edit")
def edit_resume(resume_id: str, payload: EditRequest):
    record, extra = get_coordinator().edit_resume(
        resume_id, payload.instructions, payload.save_version
    )
    return {"resume": record.model_dump(mode="json"), **extra}


@router.post("/{resume_id}/select-template")
def select_template(resume_id: str, payload: SelectTemplateRequest):
    record = get_coordinator().select_template(resume_id, payload.template_id)
    return record.model_dump(mode="json")


@router.get("/{resume_id}/versions")
def list_versions(resume_id: str):
    record = get_coordinator().get_resume(resume_id)
    return [v.model_dump(mode="json") for v in record.versions]


@router.post("/{resume_id}/versions/{version}/restore")
def restore_version(resume_id: str, version: int):
    return get_coordinator().restore_version(resume_id, version).model_dump(mode="json")


@router.get("/{resume_id}/scores")
def get_scores(resume_id: str, job_description: str = ""):
    return get_coordinator().scores(resume_id, job_description).model_dump()


@router.post("/{resume_id}/optimize")
def optimize(resume_id: str, payload: OptimizeRequest):
    """Job-specific / LinkedIn / ATS optimization suggestions + JD keyword coverage."""
    from services.scoring_service import jd_coverage

    coordinator = get_coordinator()
    record = coordinator.get_resume(resume_id)
    report = coordinator.scores(resume_id, payload.job_description).model_dump()
    if payload.job_description.strip():
        report["jd_coverage"] = jd_coverage(record.data, payload.job_description)
    return report


@router.post("/{resume_id}/publish")
def publish_resume(resume_id: str):
    """Make the resume public at /r/{slug}."""
    import re as _re

    coordinator = get_coordinator()
    record = coordinator.get_resume(resume_id)
    if not record.public_slug:
        base = _re.sub(r"[^a-z0-9]+", "-", (record.data.name or record.title).lower()).strip("-") or "resume"
        slug = base
        existing = {r.public_slug for r in coordinator.list_resumes() if r.public_slug}
        suffix = 1
        while slug in existing:
            suffix += 1
            slug = f"{base}-{suffix}"
        record.public_slug = slug
        coordinator._save(record)
    return {"published": True, "slug": record.public_slug, "url": f"/r/{record.public_slug}"}


@router.post("/{resume_id}/unpublish")
def unpublish_resume(resume_id: str):
    coordinator = get_coordinator()
    record = coordinator.get_resume(resume_id)
    record.public_slug = ""
    coordinator._save(record)
    return {"published": False}


@router.get("/{resume_id}/prompt-history")
def prompt_history(resume_id: str):
    record = get_coordinator().get_resume(resume_id)
    return [p.model_dump(mode="json") for p in record.prompt_history]
