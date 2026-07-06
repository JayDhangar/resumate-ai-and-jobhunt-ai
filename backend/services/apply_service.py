"""Job-application intelligence: resume↔job fit analysis and email drafting.

LLM-powered when a provider is configured; both features degrade to useful
deterministic fallbacks offline.
"""
from __future__ import annotations

import re
from typing import Any

from core.logging_config import get_logger
from models.schemas import JobPosting, ResumeData
from services.llm_service import get_llm
from services.scoring_service import keyword_suggestions

logger = get_logger("apply")

FIT_SYSTEM_PROMPT = """You are a career coach. Compare a candidate's resume with a job posting and return JSON:
{
  "fit_score": 0-100,
  "matched_skills": ["skills the candidate has that the job wants"],
  "missing_skills": ["important job requirements the resume lacks"],
  "suggestions": {
    "summary": "1-2 sentence rewrite advice to align the professional summary with this role",
    "skills": ["specific skills to add or emphasise"],
    "experience": ["how to reframe existing experience bullets for this role"],
    "projects": ["project ideas or existing projects to highlight"]
  }
}
Be honest about gaps. Never invent things the candidate doesn't have. Return ONLY JSON."""

EMAIL_SYSTEM_PROMPT = """You write job-application emails to recruiters/HR. Using the candidate's resume and the job posting, return JSON:
{"subject": "...", "body": "..."}
Rules:
- Body is plain text, 120-180 words, ready to send.
- Reference the specific role and company; highlight the candidate's 2-3 most relevant strengths with one concrete achievement.
- End with a clear call to action and the candidate's name and contact line.
- Never invent qualifications. Return ONLY JSON."""

TONES = {
    "professional": "polished, formal-but-warm business tone",
    "concise": "very short and direct (max 90 words), respectful of the reader's time",
    "enthusiastic": "energetic and passionate while staying credible",
    "formal": "traditional formal tone suitable for conservative industries",
}

HR_EMAIL_TIPS = [
    "Subject line: role + your headline, e.g. “Application: AI Engineer — 3y Python/ML”. Recruiters scan subjects first.",
    "Send Tuesday–Thursday, 9–11 AM in the company's timezone for the best open rates.",
    "Attach your resume as PDF named Firstname_Lastname_Resume.pdf — never DOCX for a first contact.",
    "Keep it under 200 words — the email is the hook, the resume is the substance.",
    "Mention 1 specific thing about the company/role so it doesn't read as a mass email.",
    "If you found the job on a portal, still apply there too — some ATS systems only count portal applications.",
    "Follow up once after 5–7 business days if you get no reply; more than once looks pushy.",
]


def _job_context(job: JobPosting) -> str:
    return (
        f"Title: {job.title}\nCompany: {job.company}\nLocation: {job.location}\n"
        f"Description: {job.description[:2500]}"
    )


def _resume_context(resume: ResumeData) -> str:
    parts = [
        f"Name: {resume.name}", f"Headline: {resume.headline}",
        f"Email: {resume.email}", f"Phone: {resume.phone}",
        f"Summary: {resume.summary}",
        "Skills: " + ", ".join(resume.flat_skills()),
    ]
    for exp in resume.experience[:4]:
        parts.append(f"Experience: {exp.title} at {exp.company} ({exp.start_date}–{exp.end_date}): "
                     + "; ".join(exp.bullets[:3]))
    for proj in resume.projects[:3]:
        parts.append(f"Project: {proj.name} — {proj.description} [{', '.join(proj.technologies)}]")
    return "\n".join(p for p in parts if p and not p.endswith(": "))


# ------------------------------------------------------------------ fit

def analyze_fit(resume: ResumeData, job: JobPosting) -> dict[str, Any]:
    llm = get_llm()
    if llm.available:
        try:
            payload = llm.complete_json(
                FIT_SYSTEM_PROMPT,
                f"RESUME:\n{_resume_context(resume)}\n\nJOB POSTING:\n{_job_context(job)}",
                max_tokens=1500,
                op="job_fit_analysis",
            )
            payload["fit_score"] = max(0, min(100, int(payload.get("fit_score", 50))))
            payload.setdefault("suggestions", {})
            payload["source"] = "ai"
            return payload
        except Exception as exc:  # noqa: BLE001
            logger.warning("LLM fit analysis failed (%s); using heuristics", exc)
    return _heuristic_fit(resume, job)


def _heuristic_fit(resume: ResumeData, job: JobPosting) -> dict[str, Any]:
    job_text = f"{job.title} {job.description}".lower()
    skills = resume.flat_skills()
    matched = [s for s in skills
               if re.search(rf"(?<![a-z0-9]){re.escape(s.lower())}(?![a-z0-9])", job_text)]
    missing, _ = keyword_suggestions(resume, job.description)
    denominator = len(matched) + len(missing) or 1
    fit = int(30 + 65 * len(matched) / denominator)
    return {
        "fit_score": min(fit, 95),
        "matched_skills": matched[:10],
        "missing_skills": missing[:8],
        "suggestions": {
            "summary": f"Mention '{job.title}' focus and your strongest matching skills "
                       f"({', '.join(matched[:3]) or 'core strengths'}) in the first line of your summary.",
            "skills": missing[:5],
            "experience": ["Quantify achievements with numbers/percentages that echo the job's responsibilities."],
            "projects": [f"Highlight any project using {', '.join(missing[:2])}" if missing
                         else "Highlight your most relevant project at the top."],
        },
        "source": "heuristic",
    }


# ------------------------------------------------------------------ email

def draft_email(resume: ResumeData, job: JobPosting, tone: str = "professional",
                previous_subject: str = "") -> dict[str, Any]:
    llm = get_llm()
    tone_note = TONES.get(tone, TONES["professional"])
    if llm.available:
        try:
            vary = (f"\nWrite a NEW, noticeably different version than one titled "
                    f"'{previous_subject}'." if previous_subject else "")
            payload = llm.complete_json(
                EMAIL_SYSTEM_PROMPT + f"\nTone: {tone_note}.{vary}",
                f"RESUME:\n{_resume_context(resume)}\n\nJOB POSTING:\n{_job_context(job)}",
                max_tokens=800,
                op="draft_email",
            )
            return {
                "subject": str(payload.get("subject", "")).strip(),
                "body": str(payload.get("body", "")).strip(),
                "tone": tone,
                "tips": HR_EMAIL_TIPS,
                "source": "ai",
            }
        except Exception as exc:  # noqa: BLE001
            logger.warning("LLM email draft failed (%s); using template", exc)
    return _template_email(resume, job, tone)


COVER_LETTER_SYSTEM_PROMPT = """You write compelling one-page cover letters. Using the candidate's resume and the job posting, return JSON:
{"title": "Cover Letter — <Role> at <Company>", "body": "..."}
Rules:
- Body is plain text, 250-350 words, 3-4 paragraphs: hook + why-me (with 2 concrete achievements) + why-this-company + close.
- Address "Dear Hiring Manager," unless a name is known.
- End with "Sincerely," and the candidate's name.
- Never invent qualifications, employers or dates. Return ONLY JSON."""


def draft_cover_letter(resume: ResumeData, job: JobPosting, tone: str = "professional",
                       previous_body: str = "") -> dict[str, Any]:
    llm = get_llm()
    tone_note = TONES.get(tone, TONES["professional"])
    if llm.available:
        try:
            vary = "\nWrite a NEW, noticeably different version." if previous_body else ""
            payload = llm.complete_json(
                COVER_LETTER_SYSTEM_PROMPT + f"\nTone: {tone_note}.{vary}",
                f"RESUME:\n{_resume_context(resume)}\n\nJOB POSTING:\n{_job_context(job)}",
                max_tokens=1200,
                op="cover_letter",
            )
            return {
                "title": str(payload.get("title", "")).strip() or f"Cover Letter — {job.title}",
                "body": str(payload.get("body", "")).strip(),
                "tone": tone,
                "source": "ai",
            }
        except Exception as exc:  # noqa: BLE001
            logger.warning("LLM cover letter failed (%s); using template", exc)
    return _template_cover_letter(resume, job, tone)


def _template_cover_letter(resume: ResumeData, job: JobPosting, tone: str) -> dict[str, Any]:
    skills = ", ".join(resume.flat_skills()[:5]) or "relevant technologies"
    top = resume.experience[0] if resume.experience else None
    achievement = top.bullets[0] if top and top.bullets else "consistently delivering measurable results"
    body = (
        f"Dear Hiring Manager,\n\n"
        f"I am excited to apply for the {job.title or 'open'} position at {job.company or 'your company'}. "
        f"As {resume.headline or 'a dedicated professional'}, I bring hands-on expertise in {skills} and a "
        f"track record of turning requirements into shipped, reliable software.\n\n"
        f"In my most recent role{f' as {top.title} at {top.company}' if top else ''}, "
        f"{achievement[:220].rstrip('.')}. I approach every project with ownership, clear communication "
        f"and a focus on outcomes that matter to the business.\n\n"
        f"{job.company or 'Your company'}'s work stood out to me, and I believe my background aligns "
        f"closely with what this role needs. I would welcome the opportunity to discuss how I can contribute.\n\n"
        f"Sincerely,\n{resume.name or 'Your Name'}\n"
        f"{resume.email}{' · ' + resume.phone if resume.phone else ''}"
    )
    return {"title": f"Cover Letter — {job.title or 'Application'}", "body": body,
            "tone": tone, "source": "template"}


def cover_letter_html(title: str, body: str, name: str) -> str:
    """Simple print-ready letter HTML for PDF export."""
    import html as html_mod

    paragraphs = "".join(
        f"<p>{html_mod.escape(p).replace(chr(10), '<br/>')}</p>"
        for p in body.split("\n\n") if p.strip()
    )
    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'/><style>"
        "@page { size: A4; margin: 2.2cm 2.4cm; }"
        "body { font-family: Georgia, serif; font-size: 11.5pt; color: #222; line-height: 1.55; }"
        "h1 { font-size: 15pt; color: #1a1a2e; border-bottom: 2px solid #1a1a2e; padding-bottom: 6px; }"
        "p { margin: 0 0 12px; }"
        "</style></head><body>"
        f"<h1>{html_mod.escape(name)}</h1>{paragraphs}</body></html>"
    )


def _template_email(resume: ResumeData, job: JobPosting, tone: str) -> dict[str, Any]:
    skills = ", ".join(resume.flat_skills()[:4]) or "relevant technologies"
    top = resume.experience[0] if resume.experience else None
    achievement = (top.bullets[0] if top and top.bullets else "delivering measurable results")
    body = (
        f"Dear Hiring Team at {job.company or 'your company'},\n\n"
        f"I'm writing to apply for the {job.title or 'open'} position. "
        f"As {resume.headline or 'a dedicated professional'} with hands-on experience in {skills}, "
        f"I believe I can contribute from day one — for example, {achievement[:140].rstrip('.')}.\n\n"
        f"My resume is attached with full details. I'd welcome the chance to discuss how my "
        f"background fits your team's goals.\n\n"
        f"Best regards,\n{resume.name or 'Your Name'}\n"
        f"{resume.email}{' · ' + resume.phone if resume.phone else ''}"
    )
    return {
        "subject": f"Application: {job.title or 'Open role'} — {resume.name or 'Candidate'}",
        "body": body,
        "tone": tone,
        "tips": HR_EMAIL_TIPS,
        "source": "template",
    }
