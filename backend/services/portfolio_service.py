"""Portfolio website generator.

Renders the user's resume into one of five self-contained, animated portfolio
websites (single HTML file, zero dependencies, works offline by double-click).
Each design is a Jinja2 template under templates/portfolio/.
"""
from __future__ import annotations

import re
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from core.config import get_settings
from core.exceptions import ResumeBuilderError
from models.schemas import ResumeData

DESIGNS: dict[str, dict] = {
    "terminal": {
        "name": "Neon Terminal",
        "emoji": "🖥",
        "tagline": "Your portfolio as a live terminal session — typing commands, phosphor glow, and a real prompt recruiters can type into.",
        "default_accent": "#33ff66",
    },
    "bento": {
        "name": "Bento Studio",
        "emoji": "🍱",
        "tagline": "Apple/Linear-style glass bento grid — 3D tilt tiles, magnetic buttons, count-up stats.",
        "default_accent": "#7c5fe8",
    },
    "kinetic": {
        "name": "Kinetic Ink",
        "emoji": "✒️",
        "tagline": "Editorial typography in motion — letters assemble, words rotate, projects scroll sideways.",
        "default_accent": "#e8505b",
    },
    "aurora": {
        "name": "Aurora Glass",
        "emoji": "🌌",
        "tagline": "Cinematic dark glassmorphism — drifting aurora, self-drawing timeline, particle sky.",
        "default_accent": "#6d87ff",
    },
    "brutalist": {
        "name": "Brutalist Grid",
        "emoji": "🧱",
        "tagline": "Raw, loud, unforgettable — hard shadows, slamming sections, colors that invert on click.",
        "default_accent": "#ffe600",
    },
}

_env = Environment(
    loader=FileSystemLoader(str(Path(__file__).resolve().parent.parent / "templates" / "portfolio")),
    autoescape=select_autoescape(["html", "j2"]),
)


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = (value or "#7c5fe8").lstrip("#")
    if len(value) == 3:
        value = "".join(c * 2 for c in value)
    if not re.fullmatch(r"[0-9a-fA-F]{6}", value):
        value = "7c5fe8"
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def _shade(rgb: tuple[int, int, int], factor: float) -> str:
    if factor >= 1:  # lighten toward white
        return "#{:02x}{:02x}{:02x}".format(
            *(min(255, int(c + (255 - c) * (factor - 1))) for c in rgb))
    return "#{:02x}{:02x}{:02x}".format(*(max(0, int(c * factor)) for c in rgb))


def build_portfolio(resume: ResumeData, design: str, accent: str = "") -> str:
    if design not in DESIGNS:
        raise ResumeBuilderError(
            f"Unknown design '{design}'. Available: {', '.join(DESIGNS)}", status_code=422)
    accent = accent or DESIGNS[design]["default_accent"]
    rgb = _hex_to_rgb(accent)
    accent = "#{:02x}{:02x}{:02x}".format(*rgb)

    first_name = (resume.name or "Me").split()[0]
    roles = [w.strip() for w in re.split(r"[|•·,/–—-]+", resume.headline) if w.strip()][:4]
    ctx = {
        "r": resume,
        "accent": accent,
        "accent_rgb": f"{rgb[0]}, {rgb[1]}, {rgb[2]}",
        "accent_dark": _shade(rgb, 0.55),
        "accent_light": _shade(rgb, 1.45),
        "first_name": first_name,
        "initials": "".join(w[0] for w in (resume.name or "Me").split()[:2]).upper(),
        "slug": re.sub(r"[^a-z0-9]+", "-", (resume.name or "portfolio").lower()).strip("-"),
        "roles": roles or ["Engineer"],
        "flat_skills": resume.flat_skills()[:24],
        "n_projects": len(resume.projects),
        "n_skills": len(resume.flat_skills()),
        "github": resume.links.github,
        "linkedin": resume.links.linkedin,
        "website": resume.links.website,
    }
    return _env.get_template(f"{design}.html.j2").render(**ctx)


def save_portfolio(resume: ResumeData, design: str, accent: str = "") -> Path:
    html = build_portfolio(resume, design, accent)
    out_dir = Path(get_settings().generated_dir) / "portfolios"
    out_dir.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "-", (resume.name or "portfolio").lower()).strip("-") or "portfolio"
    path = out_dir / f"{slug}-{design}.html"
    path.write_text(html, encoding="utf-8")
    return path
