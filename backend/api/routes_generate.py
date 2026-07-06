"""REST endpoints for generation, preview and downloads."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse, Response

from agents.coordinator import get_coordinator
from core.exceptions import NotFoundError
from models.schemas import GenerateRequest

router = APIRouter(prefix="/api/resumes", tags=["generate"])

MEDIA_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".html": "text/html",
    ".png": "image/png",
    ".md": "text/markdown",
    ".json": "application/json",
}


@router.post("/{resume_id}/generate")
def generate_resume(resume_id: str, payload: GenerateRequest):
    return get_coordinator().generate(
        resume_id,
        template_id=payload.template_id,
        template_instructions=payload.template_instructions,
        resume_instructions=payload.resume_instructions,
        formats=payload.formats,
    )


@router.get("/{resume_id}/preview")
def preview_resume(resume_id: str, template_id: str = "", template_instructions: str = ""):
    """Render (without persisting exports) and return the HTML preview."""
    coordinator = get_coordinator()
    record = coordinator.get_resume(resume_id)
    tid = template_id or record.selected_template_id
    template = coordinator._maybe_template(tid) or coordinator.list_templates()[0]
    adjusted = coordinator.generator.parse_adjustments(template, template_instructions)
    html = coordinator.generator.render_html(record.data, adjusted)
    return Response(content=html, media_type="text/html")


@router.get("/{resume_id}/download/{fmt}")
def download_resume(resume_id: str, fmt: str):
    coordinator = get_coordinator()
    record = coordinator.get_resume(resume_id)
    fmt = fmt.lower().lstrip(".")
    if fmt in ("image", "jpg", "jpeg"):
        fmt = "png"
    path_str = record.generated_files.get(fmt, "")
    if not path_str or not Path(path_str).is_file():
        # generate on demand
        result = coordinator.generate(resume_id, formats=[fmt])
        path_str = result["files"].get(fmt, "")
        if not path_str:
            raise NotFoundError(
                f"Could not produce {fmt.upper()} export: {result['errors'].get(fmt, 'unknown error')}"
            )
    path = Path(path_str)
    safe_title = "".join(c for c in record.title if c.isalnum() or c in " -_").strip() or "resume"
    return FileResponse(
        str(path),
        media_type=MEDIA_TYPES.get(path.suffix, "application/octet-stream"),
        filename=f"{safe_title}{path.suffix}",
    )
