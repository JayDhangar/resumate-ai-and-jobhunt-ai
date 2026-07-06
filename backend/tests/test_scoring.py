"""Scoring service heuristics."""
from models.schemas import ExperienceItem, ResumeData
from services.scoring_service import (
    find_duplicates,
    find_weak_wording,
    score_resume,
)


def test_full_resume_scores_high(sample_resume):
    report = score_resume(sample_resume)
    assert report.ats_score >= 80
    assert report.resume_score >= 70
    assert report.grammar_score >= 80


def test_empty_resume_scores_low():
    report = score_resume(ResumeData())
    assert report.ats_score < 40
    assert any("email" in tip.lower() for tip in report.recommendations)


def test_weak_wording_detected():
    resume = ResumeData(experience=[
        ExperienceItem(title="Dev", bullets=["Responsible for maintaining servers"])
    ])
    weak = find_weak_wording(resume)
    assert weak and "responsible for" in weak[0]


def test_duplicates_detected():
    resume = ResumeData(experience=[
        ExperienceItem(title="Dev", bullets=["Shipped features", "Shipped features"])
    ])
    assert find_duplicates(resume) == ["shipped features"]
