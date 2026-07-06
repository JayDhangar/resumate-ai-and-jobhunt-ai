"""Job search: trust scoring heuristics and dedupe logic."""
from agents.job_search_agent import JobSearchAgent
from models.schemas import JobPosting
from services.trust_service import score_job


def test_trusted_platform_scores_high():
    job = JobPosting(
        title="AI Engineer",
        company="Acme Corp",
        url="https://boards.greenhouse.io/acme/jobs/123",
        description="We are hiring an AI engineer. " * 30,
        salary="1,500,000 – 2,500,000",
        posted_at="2026-07-01",
    )
    trust = score_job(job)
    assert trust.score >= 80
    assert trust.verdict == "trusted"
    assert any("recognised platform" in r for r in trust.reasons)


def test_scam_posting_scores_low():
    job = JobPosting(
        title="Work from home data entry — earn $500 per day",
        company="",
        url="http://quick-money-jobs.xyz/apply",
        description="No experience needed, huge salary! Pay a small registration fee "
                    "and contact us on WhatsApp +911234567890 at winner@gmail.com",
    )
    trust = score_job(job)
    assert trust.score < 40
    assert trust.verdict == "suspicious"
    assert any("fee" in r for r in trust.reasons)


def test_missing_link_penalised():
    trust = score_job(JobPosting(title="Engineer", company="X", url=""))
    assert any("no apply link" in r for r in trust.reasons)


def test_dedupe_same_job_across_sources():
    agent = JobSearchAgent()
    jobs = [
        JobPosting(title="AI Engineer", company="Acme Corp", source="remotive"),
        JobPosting(title="AI  engineer!", company="ACME CORP", source="adzuna"),
        JobPosting(title="Data Scientist", company="Acme Corp", source="adzuna"),
    ]
    deduped = agent._dedupe(jobs)
    assert len(deduped) == 2
