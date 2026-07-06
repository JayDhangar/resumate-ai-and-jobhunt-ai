"""Portfolio generator: all five designs render with resume data, self-contained."""
import pytest

from core.exceptions import ResumeBuilderError
from models.schemas import ResumeData
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


@pytest.mark.parametrize("design", list(DESIGNS.keys()))
def test_sparse_resume_adapts(design):
    """Layouts are dynamic: empty sections collapse instead of rendering bare headings."""
    sparse = ResumeData(name="Sam Sparse", email="sam@example.com", headline="Developer")
    html = build_portfolio(sparse, design)
    assert "Sam Sparse" in html
    # section headings for absent data must not appear (as rendered elements)
    for heading in ("Projects", "Journey", "Experience", "Track record",
                    "Skill constellation", "The toolbox", "Arsenal", "Manifesto"):
        assert f">{heading}<" not in html, f"{design}: '{heading}' rendered without data"
    # em-dash-free microcopy
    assert " — " not in html


@pytest.mark.parametrize("design", list(DESIGNS.keys()))
def test_copy_has_no_spaced_em_dashes(sample_resume, design):
    html = build_portfolio(sample_resume, design)
    assert " — " not in html


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
