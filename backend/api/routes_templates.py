"""REST endpoints for the template library: search/refresh, upload, CRUD, previews."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import FileResponse, Response

from agents.coordinator import get_coordinator
from core.exceptions import NotFoundError
from models.schemas import TemplateMeta

router = APIRouter(prefix="/api/templates", tags=["templates"])


@router.get("")
def list_templates(source: str = "", style: str = "", q: str = "", sort: str = "popularity"):
    templates = get_coordinator().list_templates()
    if source:
        templates = [t for t in templates if t.source.value == source]
    if style:
        templates = [t for t in templates if t.style == style]
    if q:
        needle = q.lower()
        templates = [
            t for t in templates
            if needle in t.name.lower()
            or needle in t.description.lower()
            or any(needle in tag for tag in t.tags)
        ]
    if sort == "name":
        templates.sort(key=lambda t: t.name.lower())
    elif sort == "ats":
        templates.sort(key=lambda t: -t.ats_score)
    else:
        templates.sort(key=lambda t: -t.popularity)
    return [t.model_dump(mode="json") for t in templates]


@router.post("/refresh")
def refresh_templates(include_web: bool = True):
    return get_coordinator().refresh_templates(include_web=include_web)


@router.post("/upload")
async def upload_template(file: UploadFile = File(...), name: str = Form("")):
    content = await file.read()
    meta = get_coordinator().upload_template(content, file.filename or "template.pdf", name)
    return meta.model_dump(mode="json")


@router.get("/{template_id}")
def get_template(template_id: str):
    return get_coordinator().get_template(template_id).model_dump(mode="json")


@router.put("/{template_id}")
def update_template(template_id: str, payload: TemplateMeta):
    coordinator = get_coordinator()
    existing = coordinator.get_template(template_id)
    payload.id = existing.id  # id is immutable
    coordinator.store.put("templates", payload.model_dump(mode="json"))
    return payload.model_dump(mode="json")


@router.post("/{template_id}/save")
def toggle_save_template(template_id: str):
    """Toggle 'saved' — saved templates persist across web refreshes."""
    coordinator = get_coordinator()
    meta = coordinator.get_template(template_id)
    meta.saved = not meta.saved
    coordinator.store.put("templates", meta.model_dump(mode="json"))
    return {"id": meta.id, "saved": meta.saved}


@router.delete("/{template_id}")
def delete_template(template_id: str):
    return {"deleted": get_coordinator().delete_template(template_id)}


@router.get("/{template_id}/preview")
def template_preview(template_id: str):
    meta = get_coordinator().get_template(template_id)
    path = Path(meta.preview_path)
    if not meta.preview_path or not path.is_file():
        raise NotFoundError("Preview not available for this template")
    media = "image/svg+xml" if path.suffix == ".svg" else "image/png"
    return FileResponse(str(path), media_type=media)


@router.get("/{template_id}/render-sample")
def render_sample(template_id: str):
    """Render the template with sample data — used for large gallery previews."""
    from services.sample_data import SAMPLE_RESUME

    coordinator = get_coordinator()
    meta = coordinator.get_template(template_id)
    html = coordinator.generator.render_html(SAMPLE_RESUME, meta)
    return Response(content=html, media_type="text/html")
