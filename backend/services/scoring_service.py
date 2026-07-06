"""Resume quality scoring: ATS, grammar and overall scores plus suggestions.

Deterministic heuristics that work offline; the editing agent layers LLM
recommendations on top when a provider is configured.
"""
from __future__ import annotations

import re
from collections import Counter

from models.schemas import ResumeData, ScoreReport

WEAK_PHRASES = [
    "responsible for", "worked on", "helped with", "duties included",
    "involved in", "participated in", "assisted with", "was tasked with",
    "in charge of", "familiar with",
]

ACTION_VERB_UPGRADES = {
    "made": "built",
    "did": "executed",
    "worked on": "engineered",
    "helped": "drove",
    "used": "leveraged",
    "handled": "managed",
    "responsible for": "led",
    "created": "designed",
    "fixed": "resolved",
    "improved": "optimized",
}

COMMON_TECH_KEYWORDS = [
    "python", "java", "javascript", "typescript", "react", "node", "sql",
    "aws", "docker", "kubernetes", "git", "ci/cd", "rest", "api", "agile",
    "machine learning", "cloud", "linux", "testing", "microservices",
]

_METRIC_RE = re.compile(r"\d+\s*%|\$\s*\d|\d+[kKmM]\b|\b\d{2,}\b")


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"[.!?\n]+", text) if s.strip()]


def grammar_score(resume: ResumeData) -> tuple[int, list[str]]:
    """Cheap grammar/style lint: double spaces, casing, trailing punctuation."""
    issues: list[str] = []
    texts: list[str] = [resume.summary]
    for exp in resume.experience:
        texts.extend(exp.bullets)
    for proj in resume.projects:
        texts.append(proj.description)
        texts.extend(proj.bullets)
    checked = 0
    problems = 0
    for text in texts:
        if not text:
            continue
        checked += 1
        if "  " in text:
            problems += 1
            issues.append(f"Double spaces in: “{text[:60]}…”")
        stripped = text.strip()
        if stripped and stripped[0].islower():
            problems += 1
            issues.append(f"Starts lowercase: “{stripped[:60]}…”")
        if re.search(r"\b(i)\b", text):
            problems += 1
            issues.append(f"First-person pronoun in: “{stripped[:60]}…”")
    if checked == 0:
        return 50, ["Resume has no written content to check"]
    score = max(0, 100 - int(problems / max(checked, 1) * 100))
    return score, issues[:10]


def ats_score(resume: ResumeData) -> tuple[int, list[str]]:
    """ATS-readiness: contact info, standard sections, keywords, bullet metrics."""
    tips: list[str] = []
    score = 0
    if resume.email:
        score += 15
    else:
        tips.append("Add an email address — ATS systems key on it")
    if resume.phone:
        score += 10
    else:
        tips.append("Add a phone number")
    if resume.name:
        score += 10
    if resume.summary:
        score += 10
    else:
        tips.append("Add a professional summary with role keywords")
    if resume.flat_skills():
        score += 15
    else:
        tips.append("Add a dedicated skills section")
    if resume.experience:
        score += 15
        dated = all(e.start_date for e in resume.experience)
        if dated:
            score += 5
        else:
            tips.append("Every experience entry should have dates")
    else:
        tips.append("Add work experience entries")
    if resume.education:
        score += 10
    bullets = [b for e in resume.experience for b in e.bullets]
    if bullets:
        with_metrics = sum(1 for b in bullets if _METRIC_RE.search(b))
        if with_metrics >= max(1, len(bullets) // 3):
            score += 10
        else:
            tips.append("Quantify achievements — add numbers, %, or $ impact to bullets")
    return min(score, 100), tips


def find_weak_wording(resume: ResumeData) -> list[str]:
    found: list[str] = []
    texts = [resume.summary] + [b for e in resume.experience for b in e.bullets]
    for text in texts:
        lower = text.lower()
        for phrase in WEAK_PHRASES:
            if phrase in lower:
                found.append(f"“{phrase}” in: “{text[:70]}…”")
    return found[:10]


def action_verb_suggestions(resume: ResumeData) -> dict[str, str]:
    suggestions: dict[str, str] = {}
    texts = [b for e in resume.experience for b in e.bullets]
    for text in texts:
        lower = text.lower()
        for weak, strong in ACTION_VERB_UPGRADES.items():
            if re.search(rf"\b{re.escape(weak)}\b", lower):
                suggestions[weak] = strong
    return suggestions


def find_duplicates(resume: ResumeData) -> list[str]:
    bullets = [b.strip().lower() for e in resume.experience for b in e.bullets if b.strip()]
    skills = [s.strip().lower() for s in resume.flat_skills() if s.strip()]
    dupes = [item for item, count in Counter(bullets + skills).items() if count > 1]
    return dupes[:10]


def keyword_suggestions(resume: ResumeData, job_description: str = "") -> tuple[list[str], list[str]]:
    """Return (missing_skills, keyword_suggestions)."""
    have = {s.lower() for s in resume.flat_skills()}
    body = (resume.summary + " " + " ".join(
        b for e in resume.experience for b in e.bullets
    )).lower()
    pool = COMMON_TECH_KEYWORDS
    if job_description:
        words = re.findall(r"[A-Za-z][A-Za-z+#./-]{2,}", job_description.lower())
        pool = [w for w, c in Counter(words).most_common(40) if len(w) > 3] or pool
    missing = [k for k in pool if k not in have and k not in body][:10]
    suggested = [k for k in pool if k in body and k not in have][:10]
    return missing, suggested


def jd_coverage(resume: ResumeData, job_description: str) -> dict:
    """Keyword coverage of a job description: which JD terms the resume hits."""
    words = re.findall(r"[A-Za-z][A-Za-z+#./-]{2,}", job_description.lower())
    stop = {"the", "and", "for", "with", "you", "will", "our", "are", "have", "this",
            "that", "your", "who", "can", "all", "job", "work", "team", "role", "years",
            "experience", "skills", "strong", "ability", "including", "required",
            "preferred", "candidate", "responsibilities", "requirements", "about"}
    counts = Counter(w for w in words if w not in stop and len(w) > 2)
    pool = [w for w, c in counts.most_common(30) if c >= 2 or len(w) > 5][:20]
    resume_text = (
        " ".join(resume.flat_skills()) + " " + resume.summary + " " + resume.headline + " "
        + " ".join(b for e in resume.experience for b in e.bullets)
        + " " + " ".join(f"{p.name} {p.description} {' '.join(p.technologies)}" for p in resume.projects)
    ).lower()
    covered = [w for w in pool if re.search(rf"(?<![a-z0-9]){re.escape(w)}(?![a-z0-9])", resume_text)]
    missing = [w for w in pool if w not in covered]
    return {
        "total": len(pool),
        "covered": covered,
        "missing": missing,
        "coverage_pct": int(100 * len(covered) / len(pool)) if pool else 0,
    }


def score_resume(resume: ResumeData, job_description: str = "") -> ScoreReport:
    ats, ats_tips = ats_score(resume)
    grammar, grammar_issues = grammar_score(resume)
    weak = find_weak_wording(resume)
    verbs = action_verb_suggestions(resume)
    dupes = find_duplicates(resume)
    missing, keywords = keyword_suggestions(resume, job_description)

    completeness = sum(
        bool(x) for x in (
            resume.name, resume.email, resume.summary, resume.experience,
            resume.education, resume.flat_skills(), resume.projects,
        )
    ) / 7 * 100
    overall = int(0.4 * ats + 0.25 * grammar + 0.35 * completeness)

    recommendations = ats_tips[:5]
    if weak:
        recommendations.append("Replace weak phrases with strong action verbs")
    if dupes:
        recommendations.append("Remove duplicated bullets/skills")
    if missing:
        recommendations.append(f"Consider adding relevant skills: {', '.join(missing[:5])}")

    return ScoreReport(
        resume_score=overall,
        ats_score=ats,
        grammar_score=grammar,
        missing_skills=missing,
        keyword_suggestions=keywords,
        weak_wording=weak,
        action_verb_suggestions=verbs,
        duplicates=dupes,
        recommendations=recommendations,
    )
