"""Job-posting genuineness scoring.

Deterministic heuristics that estimate how trustworthy a posting is:
apply-link domain reputation, HTTPS, scam-keyword detection, description
quality, company presence and posting freshness. Returns a 0-100 score,
a verdict and human-readable reasons.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from urllib.parse import urlparse

from models.schemas import JobPosting, JobTrust

# Domains belonging to reputable job boards / applicant tracking systems.
TRUSTED_DOMAINS = {
    "linkedin.com": "LinkedIn", "indeed.com": "Indeed", "naukri.com": "Naukri",
    "monster.com": "Monster", "monsterindia.com": "Monster India",
    "glassdoor.com": "Glassdoor", "ziprecruiter.com": "ZipRecruiter",
    "greenhouse.io": "Greenhouse ATS", "lever.co": "Lever ATS",
    "workday.com": "Workday ATS", "myworkdayjobs.com": "Workday ATS",
    "ashbyhq.com": "Ashby ATS", "smartrecruiters.com": "SmartRecruiters",
    "jobvite.com": "Jobvite", "icims.com": "iCIMS ATS",
    "bamboohr.com": "BambooHR", "workable.com": "Workable",
    "remotive.com": "Remotive", "remoteok.com": "RemoteOK",
    "themuse.com": "The Muse", "arbeitnow.com": "Arbeitnow",
    "adzuna.com": "Adzuna", "adzuna.in": "Adzuna", "jooble.org": "Jooble",
    "wellfound.com": "Wellfound", "instahyre.com": "Instahyre",
    "foundit.in": "Foundit (Monster)",
}

SCAM_PATTERNS = [
    (r"registration fee|processing fee|security deposit|pay.{0,20}(fee|deposit)", "asks for an upfront fee"),
    (r"earn \$?\d+.{0,15}(per day|daily|per week)", "unrealistic quick-earnings claim"),
    (r"no experience.{0,20}(high|huge|big) (salary|pay)", "no-experience high-pay claim"),
    (r"whatsapp.{0,20}(\+?\d{7,})", "recruiting via WhatsApp number"),
    (r"telegram", "recruiting via Telegram"),
    (r"@gmail\.com|@yahoo\.com|@hotmail\.com", "free personal email as contact"),
    (r"crypto( |-)?(investment|trading)|forex trading", "crypto/forex recruitment bait"),
    (r"work from home.{0,25}(data entry|copy paste|form filling)", "classic WFH data-entry scam wording"),
]


def score_job(job: JobPosting) -> JobTrust:
    score = 50
    reasons: list[str] = []
    text = f"{job.title} {job.description}".lower()

    # --- apply link ---
    parsed = urlparse(job.url or "")
    host = (parsed.netloc or "").lower().removeprefix("www.")
    if not job.url:
        score -= 25
        reasons.append("✗ no apply link provided")
    else:
        if parsed.scheme == "https":
            score += 5
        else:
            score -= 15
            reasons.append("✗ apply link is not HTTPS")
        matched = next((label for domain, label in TRUSTED_DOMAINS.items()
                        if host == domain or host.endswith("." + domain)), None)
        if matched:
            score += 25
            reasons.append(f"✓ apply link on a recognised platform ({matched})")
        elif host:
            reasons.append(f"• apply link on {host} (unrecognised domain — verify before sharing personal data)")

    # --- scam wording ---
    flagged = False
    for pattern, why in SCAM_PATTERNS:
        if re.search(pattern, text):
            score -= 30
            flagged = True
            reasons.append(f"⚠ {why}")
    if not flagged:
        score += 5

    # --- content quality ---
    if job.company:
        score += 8
    else:
        score -= 10
        reasons.append("✗ no company name listed")
    if len(job.description) > 400:
        score += 8
        reasons.append("✓ detailed job description")
    elif len(job.description) < 80:
        score -= 8
        reasons.append("• very short description")
    if job.salary:
        digits = [int(x.replace(",", "")) for x in re.findall(r"\d[\d,]*", job.salary)]
        if digits and max(digits) > 20_000_000:
            score -= 10
            reasons.append("⚠ implausible salary figure")
        else:
            score += 4
            reasons.append("✓ salary disclosed")

    # --- freshness ---
    if job.posted_at:
        try:
            posted = datetime.fromisoformat(job.posted_at).replace(tzinfo=timezone.utc)
            age_days = (datetime.now(timezone.utc) - posted).days
            if age_days <= 14:
                score += 5
                reasons.append("✓ posted recently")
            elif age_days > 90:
                score -= 8
                reasons.append("• posting is over 3 months old")
        except ValueError:
            pass

    score = max(0, min(100, score))
    if score >= 80:
        verdict = "trusted"
    elif score >= 60:
        verdict = "likely_genuine"
    elif score >= 40:
        verdict = "unverified"
    else:
        verdict = "suspicious"
    return JobTrust(score=score, verdict=verdict, reasons=reasons[:6])
