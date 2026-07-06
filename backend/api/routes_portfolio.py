"""REST endpoints for the portfolio website generator."""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import FileResponse, HTMLResponse

from agents.coordinator import get_coordinator
from services.portfolio_service import DESIGNS, build_portfolio, save_portfolio

router = APIRouter(prefix="/api", tags=["portfolio"])


@router.get("/portfolio/designs")
def list_designs():
    return [
        {"id": key, **meta}
        for key, meta in DESIGNS.items()
    ]


@router.get("/resumes/{resume_id}/portfolio/preview")
def preview_portfolio(resume_id: str, design: str = "bento", accent: str = ""):
    record = get_coordinator().get_resume(resume_id)
    html = build_portfolio(record.data, design, accent)
    return HTMLResponse(html)


@router.get("/resumes/{resume_id}/portfolio/download")
def download_portfolio(resume_id: str, design: str = "bento", accent: str = ""):
    """Generate, save locally (generated/portfolios/) and download the file."""
    record = get_coordinator().get_resume(resume_id)
    path = save_portfolio(record.data, design, accent)
    return FileResponse(str(path), media_type="text/html", filename=path.name)
