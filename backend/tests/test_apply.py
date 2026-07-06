"""Fit analysis and email drafting fallbacks + SMTP guard."""
import pytest

from core.exceptions import ResumeBuilderError
from models.schemas import JobPosting
from services.apply_service import analyze_fit, draft_email
from services.email_service import email_configured, send_email

JOB = JobPosting(
    title="Senior Python Engineer",
    company="Acme Corp",
    description="We need strong Python and AWS experience. Docker and Kubernetes required. "
                "You will build scalable APIs and mentor engineers.",
    url="https://boards.greenhouse.io/acme/jobs/1",
)


def test_heuristic_fit_finds_overlap(sample_resume):
    fit = analyze_fit(sample_resume, JOB)  # LLM disabled in tests -> heuristic
    assert fit["source"] == "heuristic"
    assert 0 <= fit["fit_score"] <= 100
    assert "Python" in fit["matched_skills"]
    assert fit["suggestions"]["summary"]


def test_template_email_contains_essentials(sample_resume):
    draft = draft_email(sample_resume, JOB, tone="professional")
    assert draft["source"] == "template"
    assert "Senior Python Engineer" in draft["body"]
    assert "Acme Corp" in draft["body"]
    assert sample_resume.name in draft["body"]
    assert draft["subject"]
    assert len(draft["tips"]) >= 5


def test_send_email_requires_configuration():
    assert email_configured() is False  # tests run without SMTP env
    with pytest.raises(ResumeBuilderError) as excinfo:
        send_email("hr@example.com", "Hi", "Body")
    assert excinfo.value.status_code == 503
