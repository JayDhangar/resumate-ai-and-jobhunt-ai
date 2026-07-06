"""Pydantic schemas: the shared data contracts between agents, API and frontend."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


def _now() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return uuid.uuid4().hex


# ---------------------------------------------------------------------------
# Resume content
# ---------------------------------------------------------------------------

class ContactLinks(BaseModel):
    model_config = ConfigDict(extra="allow")

    linkedin: str = ""
    github: str = ""
    website: str = ""
    other: list[str] = Field(default_factory=list)


class ExperienceItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    title: str = ""
    company: str = ""
    location: str = ""
    start_date: str = ""
    end_date: str = ""
    current: bool = False
    bullets: list[str] = Field(default_factory=list)


class EducationItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    degree: str = ""
    institution: str = ""
    location: str = ""
    start_date: str = ""
    end_date: str = ""
    gpa: str = ""
    details: list[str] = Field(default_factory=list)


class ProjectItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str = ""
    description: str = ""
    technologies: list[str] = Field(default_factory=list)
    link: str = ""
    bullets: list[str] = Field(default_factory=list)


class CertificationItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str = ""
    issuer: str = ""
    date: str = ""
    link: str = ""


class LanguageItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str = ""
    proficiency: str = ""


class AwardItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    title: str = ""
    issuer: str = ""
    date: str = ""
    description: str = ""


class SkillGroup(BaseModel):
    model_config = ConfigDict(extra="allow")

    category: str = ""
    skills: list[str] = Field(default_factory=list)


class ResumeData(BaseModel):
    """Canonical structured resume. Every agent reads/writes this shape."""

    model_config = ConfigDict(extra="allow")

    name: str = ""
    headline: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""
    summary: str = ""
    links: ContactLinks = Field(default_factory=ContactLinks)
    skills: list[SkillGroup] = Field(default_factory=list)
    experience: list[ExperienceItem] = Field(default_factory=list)
    education: list[EducationItem] = Field(default_factory=list)
    projects: list[ProjectItem] = Field(default_factory=list)
    certifications: list[CertificationItem] = Field(default_factory=list)
    languages: list[LanguageItem] = Field(default_factory=list)
    awards: list[AwardItem] = Field(default_factory=list)
    section_order: list[str] = Field(
        default_factory=lambda: [
            "summary", "skills", "experience", "projects",
            "education", "certifications", "awards", "languages",
        ]
    )
    section_titles: dict[str, str] = Field(default_factory=dict)
    extra_sections: dict[str, list[str]] = Field(default_factory=dict)

    def flat_skills(self) -> list[str]:
        out: list[str] = []
        for group in self.skills:
            out.extend(group.skills)
        return out


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

class TemplateSource(str, Enum):
    BUILTIN = "builtin"
    WEB = "web"
    UPLOADED = "uploaded"


class TemplateLayout(BaseModel):
    model_config = ConfigDict(extra="allow")

    columns: int = 1
    header_style: str = "centered"  # centered | left | banner | split
    sidebar: str = "none"           # none | left | right
    spacing: str = "normal"         # compact | normal | relaxed
    uses_icons: bool = False
    section_divider: str = "line"   # line | none | dots | block
    skill_style: str = "lines"      # lines | chips
    experience_style: str = "plain" # plain | timeline
    monogram: bool = False          # initial badge next to the name


class TemplateColors(BaseModel):
    model_config = ConfigDict(extra="allow")

    primary: str = "#1a1a2e"
    accent: str = "#0f4c81"
    text: str = "#222222"
    background: str = "#ffffff"
    sidebar_bg: str = ""
    sidebar_text: str = "#ffffff"


class TemplateFonts(BaseModel):
    model_config = ConfigDict(extra="allow")

    heading: str = "Georgia, serif"
    body: str = "Helvetica, Arial, sans-serif"
    base_size_pt: float = 10.5
    name_size_pt: float = 24.0
    section_size_pt: float = 13.0


class TemplateMeta(BaseModel):
    """Metadata describing a resume template (builtin, web-sourced or uploaded)."""

    model_config = ConfigDict(extra="allow")

    id: str = Field(default_factory=new_id)
    name: str = ""
    source: TemplateSource = TemplateSource.BUILTIN
    style: str = "modern"  # modern | ats | minimal | creative | corporate | executive | professional
    author: str = "Resume Builder AI"
    license: str = "CC0 / original work"
    origin_url: str = ""
    ats_score: int = 80
    popularity: int = 0
    layout: TemplateLayout = Field(default_factory=TemplateLayout)
    colors: TemplateColors = Field(default_factory=TemplateColors)
    fonts: TemplateFonts = Field(default_factory=TemplateFonts)
    sections: list[str] = Field(default_factory=list)
    saved: bool = False          # saved templates persist across web refreshes
    preview_path: str = ""
    html_template: str = ""      # jinja2 template file name for renderable templates
    source_file: str = ""        # original uploaded/downloaded file path
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_now)


class TemplateAdjustments(BaseModel):
    """Free-form user instructions applied to a template at generation time."""

    model_config = ConfigDict(extra="allow")

    instructions: str = ""
    colors: TemplateColors | None = None
    layout: TemplateLayout | None = None
    fonts: TemplateFonts | None = None


# ---------------------------------------------------------------------------
# Resume records, versions, generation
# ---------------------------------------------------------------------------

class ResumeVersion(BaseModel):
    version: int = 1
    label: str = ""
    data: ResumeData = Field(default_factory=ResumeData)
    created_at: datetime = Field(default_factory=_now)
    change_note: str = ""


class PromptHistoryEntry(BaseModel):
    prompt: str
    kind: str = "resume"  # resume | template
    created_at: datetime = Field(default_factory=_now)


class ResumeRecord(BaseModel):
    """Persisted resume document with full history and generation metadata."""

    id: str = Field(default_factory=new_id)
    title: str = "My Resume"
    data: ResumeData = Field(default_factory=ResumeData)
    original_file: str = ""
    original_filename: str = ""
    raw_text: str = ""
    selected_template_id: str = ""
    versions: list[ResumeVersion] = Field(default_factory=list)
    prompt_history: list[PromptHistoryEntry] = Field(default_factory=list)
    generated_files: dict[str, str] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


class ScoreReport(BaseModel):
    resume_score: int = 0
    ats_score: int = 0
    grammar_score: int = 0
    missing_skills: list[str] = Field(default_factory=list)
    keyword_suggestions: list[str] = Field(default_factory=list)
    weak_wording: list[str] = Field(default_factory=list)
    action_verb_suggestions: dict[str, str] = Field(default_factory=dict)
    duplicates: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# API request / response payloads
# ---------------------------------------------------------------------------

class EditRequest(BaseModel):
    instructions: str
    save_version: bool = True


class UpdateResumeRequest(BaseModel):
    data: ResumeData
    save_version: bool = False
    change_note: str = ""


class GenerateRequest(BaseModel):
    template_id: str = ""
    template_instructions: str = ""
    resume_instructions: str = ""
    formats: list[str] = Field(default_factory=lambda: ["html"])


class SelectTemplateRequest(BaseModel):
    template_id: str


class OptimizeRequest(BaseModel):
    job_description: str = ""
    target: str = "job"  # job | linkedin | ats


class JobTrust(BaseModel):
    score: int = 50            # 0-100 genuineness / quality estimate
    verdict: str = "unknown"   # trusted | likely_genuine | unverified | suspicious
    reasons: list[str] = Field(default_factory=list)


class JobPosting(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str = Field(default_factory=new_id)
    title: str = ""
    company: str = ""
    location: str = ""
    remote: bool = False
    salary: str = ""
    description: str = ""
    url: str = ""              # direct apply / posting link
    source: str = ""           # which provider found it
    via: str = ""              # original board when aggregated (e.g. linkedin, naukri)
    posted_at: str = ""
    tags: list[str] = Field(default_factory=list)
    trust: JobTrust = Field(default_factory=JobTrust)
    match_score: int | None = None          # 0-100 resume similarity (match mode only)
    matching_skills: list[str] = Field(default_factory=list)


class JobSearchResponse(BaseModel):
    query: str
    location: str = ""
    total: int = 0
    sources_used: list[str] = Field(default_factory=list)
    sources_available: list[str] = Field(default_factory=list)
    jobs: list[JobPosting] = Field(default_factory=list)


class SavedSearch(BaseModel):
    """A job-alert subscription: runs on scheduled days, digests NEW jobs only."""

    model_config = ConfigDict(extra="allow")

    id: str = Field(default_factory=new_id)
    name: str = ""
    query: str = ""
    location: str = ""
    remote_only: bool = False
    resume_id: str = ""                 # when set, new jobs are match-scored
    days: list[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4, 5, 6])  # 0=Mon .. 6=Sun
    enabled: bool = True
    email_digest: bool = False          # send digest via SMTP when configured
    seen_urls: list[str] = Field(default_factory=list)
    last_run: datetime | None = None
    last_new_jobs: list[JobPosting] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_now)


class ApplicationRecord(BaseModel):
    """A tracked job application (auto-logged on email send or saved manually)."""

    model_config = ConfigDict(extra="allow")

    id: str = Field(default_factory=new_id)
    job_title: str = ""
    company: str = ""
    location: str = ""
    url: str = ""
    source: str = ""
    status: str = "saved"  # saved | applied | interviewing | offer | rejected
    resume_id: str = ""
    resume_title: str = ""
    email_to: str = ""
    email_subject: str = ""
    notes: str = ""
    applied_at: datetime | None = None
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


class AgentResult(BaseModel):
    """Uniform envelope returned by every agent through the coordinator."""

    agent: str
    ok: bool = True
    detail: str = ""
    data: dict[str, Any] = Field(default_factory=dict)
