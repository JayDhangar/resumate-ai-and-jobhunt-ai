"""Portfolio generator: all five designs render with resume data, self-contained."""
import pytest

from core.exceptions import ResumeBuilderError
from services.portfolio_service import DESIGNS, build_portfolio


@pytest.mark.parametrize("design", list(DESIGNS.keys()))
def test_every_design_renders(sample_resume, design):
    html = build_portfolio(sample_resume, design)
    assert html.startswith("<!DOCTYPE html>")
    assert "Alex Morgan" in html
    assert sample_resume.email in html
    assert "Nimbus Labs" in html          # experience present
    assert "OpenMetrics" in html          # project present
    assert "Python" in html               # skills present
    # self-contained: no external network dependencies
    for banned in ("http://cdn.", "https://cdn.", "googleapis.com", "unpkg.com", "jsdelivr"):
        assert banned not in html
    # accessibility: reduced-motion handled
    assert "prefers-reduced-motion" in html


def test_accent_is_applied_and_sanitized(sample_resume):
    html = build_portfolio(sample_resume, "bento", "#2a9d8f")
    assert "#2a9d8f" in html
    # invalid accent falls back safely instead of injecting junk
    html = build_portfolio(sample_resume, "bento", "javascript:alert(1)")
    assert "javascript:alert" not in html


def test_unknown_design_rejected(sample_resume):
    with pytest.raises(ResumeBuilderError):
        build_portfolio(sample_resume, "vaporwave")


def test_portfolio_api(client):
    resume = client.post("/api/resumes", json={"title": "Port Folio"}).json()
    data = resume["data"]
    data["name"] = "Port Folio"
    data["summary"] = "Builder of things."
    client.put(f"/api/resumes/{resume['id']}", json={"data": data})

    designs = client.get("/api/portfolio/designs").json()
    assert len(designs) == 5

    page = client.get(f"/api/resumes/{resume['id']}/portfolio/preview?design=terminal")
    assert page.status_code == 200
    assert "Port Folio" in page.text

    download = client.get(f"/api/resumes/{resume['id']}/portfolio/download?design=brutalist&accent=%23ffe600")
    assert download.status_code == 200
    assert "text/html" in download.headers["content-type"]
