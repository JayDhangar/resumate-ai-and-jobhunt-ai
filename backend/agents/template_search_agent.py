"""Agent 2 — Template Search.

Discovers resume templates and keeps a deduplicated, cached library:

* Seeds a curated catalog of **original, freely-licensed designs** (rendered by
  our own Jinja2 engine) covering every requested style — modern, ATS,
  software engineer, designer, executive, minimal, creative, corporate.
* Optionally queries the public npm registry for open-source ``jsonresume-theme``
  packages and stores their **metadata only** (name, author, license, link) —
  no copyrighted assets are downloaded.
* Generates a preview image for every template and caches everything in the
  document store; refreshes periodically without creating duplicates.
"""
from __future__ import annotations

import re
from pathlib import Path

import httpx

from core.config import get_settings
from models.schemas import (
    AgentResult,
    TemplateColors,
    TemplateFonts,
    TemplateLayout,
    TemplateMeta,
    TemplateSource,
)
from services.preview_service import generate_svg_preview
from services.storage import get_store
from .base_agent import BaseAgent

TEMPLATES_COLLECTION = "templates"

NPM_SEARCH_URL = "https://registry.npmjs.org/-/v1/search"
SEARCH_QUERIES = [
    "modern resume template",
    "ats resume template",
    "software engineer resume",
    "designer resume",
    "executive resume",
    "minimal resume",
    "creative resume",
]


def _catalog() -> list[TemplateMeta]:
    """Curated original designs, all rendered by the built-in engine."""
    def meta(name: str, style: str, ats: int, desc: str, tags: list[str],
             layout: TemplateLayout, colors: TemplateColors,
             fonts: TemplateFonts | None = None, popularity: int = 50) -> TemplateMeta:
        return TemplateMeta(
            id=f"builtin-{name.lower().replace(' ', '-')}",
            name=name,
            source=TemplateSource.BUILTIN,
            style=style,
            ats_score=ats,
            description=desc,
            tags=tags,
            layout=layout,
            colors=colors,
            fonts=fonts or TemplateFonts(),
            html_template="master.html.j2",
            sections=["summary", "skills", "experience", "projects",
                      "education", "certifications", "awards", "languages"],
            popularity=popularity,
        )

    return [
        # ---- Featured defaults (modelled on the four reference designs) ----
        meta("Coral Timeline", "professional", 92,
             "Single-column professional layout with coral section accents, expertise tag chips "
             "and a clean timeline feel — great for project managers.",
             ["featured", "default", "project-manager", "chips", "timeline"],
             TemplateLayout(columns=1, header_style="left", spacing="normal",
                            section_divider="line", skill_style="chips"),
             TemplateColors(primary="#3a3a3a", accent="#e8505b", text="#3d3d3d"),
             TemplateFonts(heading="Helvetica, Arial, sans-serif",
                           body="Helvetica, Arial, sans-serif", name_size_pt=25),
             popularity=99),
        meta("Azure Duo", "modern", 88,
             "Two-column layout with a light right rail for skills, projects and certificates; "
             "blue pill skills — ideal for retail and business roles.",
             ["featured", "default", "two-column", "chips", "business"],
             TemplateLayout(columns=2, header_style="left", sidebar="right",
                            spacing="normal", skill_style="chips"),
             TemplateColors(primary="#26364a", accent="#1d6fc4", text="#2b2b2b",
                            sidebar_bg="#eef4fb", sidebar_text="#26364a"),
             TemplateFonts(heading="Helvetica, Arial, sans-serif",
                           body="Helvetica, Arial, sans-serif"),
             popularity=98),
        meta("Violet Scholar", "modern", 84,
             "Left sidebar for contact, soft skills and languages with a bold violet header — "
             "made for students and early-career profiles.",
             ["featured", "default", "student", "sidebar", "violet"],
             TemplateLayout(columns=2, header_style="left", sidebar="left",
                            spacing="normal", section_divider="line"),
             TemplateColors(primary="#4b3a8f", accent="#5b2a86", text="#333333",
                            sidebar_bg="#f4f2fa", sidebar_text="#3a3060"),
             TemplateFonts(heading="Trebuchet MS, sans-serif", body="Verdana, sans-serif"),
             popularity=97),
        meta("Teal Studio", "creative", 86,
             "Portfolio-friendly two-column design with a soft teal rail and chip-style hard/soft "
             "skills — built for photographers, designers and creatives.",
             ["featured", "default", "creative", "portfolio", "chips", "teal"],
             TemplateLayout(columns=2, header_style="left", sidebar="right",
                            spacing="compact", skill_style="chips"),
             TemplateColors(primary="#14332e", accent="#2a9d8f", text="#243430",
                            sidebar_bg="#eef8f5", sidebar_text="#14332e"),
             TemplateFonts(heading="Helvetica, Arial, sans-serif",
                           body="Helvetica, Arial, sans-serif"),
             popularity=96),
        # ---- New layout showcases ----
        meta("Timeline Noir", "modern", 88,
             "Split header with a bold rule, chip skills and a vertical timeline running "
             "down the experience section — distinctive but still ATS-friendly.",
             ["featured", "timeline", "split-header", "chips"],
             TemplateLayout(columns=1, header_style="split", spacing="normal",
                            experience_style="timeline", skill_style="chips",
                            section_divider="none"),
             TemplateColors(primary="#1b1b1b", accent="#4a4a4a", text="#2a2a2a"),
             TemplateFonts(heading="Helvetica, Arial, sans-serif",
                           body="Helvetica, Arial, sans-serif", name_size_pt=23),
             popularity=94),
        meta("Monogram Ivory", "executive", 84,
             "Warm ivory page with a monogram badge, centered serif header and relaxed "
             "spacing — an elegant executive look.",
             ["monogram", "serif", "elegant", "executive"],
             TemplateLayout(columns=1, header_style="centered", spacing="relaxed",
                            monogram=True, section_divider="line"),
             TemplateColors(primary="#3d3428", accent="#8a6d3b", text="#3d3428",
                            background="#fbfaf6"),
             TemplateFonts(heading="Garamond, Georgia, serif", body="Georgia, serif",
                           name_size_pt=25),
             popularity=93),
        meta("Split Cobalt", "professional", 90,
             "Name left, contact right over a cobalt rule; timeline experience with a "
             "light sidebar for skills — a fresh two-column take.",
             ["split-header", "two-column", "timeline"],
             TemplateLayout(columns=2, header_style="left", sidebar="left",
                            spacing="relaxed", experience_style="timeline"),
             TemplateColors(primary="#1d3557", accent="#3a6ea5", text="#26313d",
                            sidebar_bg="#eef3fa", sidebar_text="#1d3557"),
             popularity=92),
        # ---- Original catalog ----
        meta("Crisp ATS", "ats", 98,
             "Single-column, zero-frills layout engineered to sail through applicant tracking systems.",
             ["ats", "simple", "single-column"],
             TemplateLayout(columns=1, header_style="left", spacing="normal", section_divider="line"),
             TemplateColors(primary="#111111", accent="#333333", text="#222222"),
             TemplateFonts(heading="Arial, sans-serif", body="Arial, sans-serif", base_size_pt=10.5),
             popularity=95),
        meta("Metro Modern", "modern", 90,
             "Clean modern look with a bold accent color and generous whitespace.",
             ["modern", "clean", "professional"],
             TemplateLayout(columns=1, header_style="left", spacing="relaxed", section_divider="line"),
             TemplateColors(primary="#0f4c81", accent="#0f4c81", text="#2b2b2b"),
             TemplateFonts(heading="Helvetica, Arial, sans-serif", body="Helvetica, Arial, sans-serif"),
             popularity=88),
        meta("Sidebar Slate", "professional", 78,
             "Two-column layout with a slate sidebar for skills, links and languages.",
             ["two-column", "sidebar", "software-engineer"],
             TemplateLayout(columns=2, header_style="left", sidebar="left", spacing="normal"),
             TemplateColors(primary="#1f2a3d", accent="#3f6fb5", text="#2b2b2b", sidebar_bg="#1f2a3d"),
             popularity=82),
        meta("Minimal Ink", "minimal", 92,
             "Ultra-minimal typographic resume — just beautiful hierarchy and space.",
             ["minimal", "typographic", "elegant"],
             TemplateLayout(columns=1, header_style="centered", spacing="relaxed", section_divider="none"),
             TemplateColors(primary="#000000", accent="#666666", text="#333333"),
             TemplateFonts(heading="Georgia, serif", body="Georgia, serif", base_size_pt=10.5),
             popularity=74),
        meta("Creative Coral", "creative", 68,
             "Banner header with vibrant coral accents — great for designers and creatives.",
             ["creative", "designer", "colorful", "banner"],
             TemplateLayout(columns=2, header_style="banner", spacing="normal", uses_icons=True),
             TemplateColors(primary="#e8505b", accent="#f9a828", text="#333333"),
             TemplateFonts(heading="Trebuchet MS, sans-serif", body="Verdana, sans-serif"),
             popularity=66),
        meta("Executive Prestige", "executive", 85,
             "Refined serif design with understated gold detailing for senior leaders.",
             ["executive", "leadership", "serif"],
             TemplateLayout(columns=1, header_style="centered", spacing="relaxed", section_divider="line"),
             TemplateColors(primary="#2c2c2c", accent="#a67c00", text="#2c2c2c"),
             TemplateFonts(heading="Garamond, Georgia, serif", body="Georgia, serif", name_size_pt=26),
             popularity=71),
        meta("Corporate Blue", "corporate", 88,
             "Structured corporate style with a navy banner and disciplined sections.",
             ["corporate", "banner", "business"],
             TemplateLayout(columns=1, header_style="banner", spacing="compact", section_divider="line"),
             TemplateColors(primary="#14395d", accent="#14395d", text="#222222"),
             popularity=79),
        meta("Terminal Green", "modern", 80,
             "Developer-flavored theme with monospace headings — built for software engineers.",
             ["software-engineer", "developer", "tech"],
             TemplateLayout(columns=2, header_style="left", sidebar="right", spacing="compact"),
             TemplateColors(primary="#0d1b0f", accent="#1f7a33", text="#1c1c1c", sidebar_bg="#0d1b0f"),
             TemplateFonts(heading="Consolas, monospace", body="Calibri, sans-serif"),
             popularity=64),
    ]


_WEB_PALETTES: list[dict] = [
    {"primary": "#0f4c81", "accent": "#1d6fc4", "style": "modern"},
    {"primary": "#1f6b3a", "accent": "#2f9e57", "style": "modern"},
    {"primary": "#5b2a86", "accent": "#7c4dbd", "style": "creative"},
    {"primary": "#a8262e", "accent": "#d13f47", "style": "creative"},
    {"primary": "#116466", "accent": "#2a9d8f", "style": "minimal"},
    {"primary": "#c85311", "accent": "#e8752a", "style": "creative"},
    {"primary": "#2c2c2c", "accent": "#a67c00", "style": "executive"},
    {"primary": "#14395d", "accent": "#3f6fb5", "style": "corporate"},
    {"primary": "#7a1f4d", "accent": "#b23a67", "style": "creative"},
    {"primary": "#111111", "accent": "#555555", "style": "ats"},
]

_WEB_LAYOUTS: list[TemplateLayout] = [
    TemplateLayout(columns=1, header_style="left", spacing="normal"),
    TemplateLayout(columns=1, header_style="centered", spacing="relaxed", section_divider="none"),
    TemplateLayout(columns=2, header_style="left", sidebar="left", spacing="normal"),
    TemplateLayout(columns=2, header_style="left", sidebar="right", spacing="compact"),
    TemplateLayout(columns=1, header_style="banner", spacing="normal"),
    TemplateLayout(columns=1, header_style="left", spacing="compact", skill_style="chips"),
    TemplateLayout(columns=1, header_style="split", spacing="normal", skill_style="chips"),
    TemplateLayout(columns=1, header_style="split", spacing="compact",
                   experience_style="timeline", section_divider="none"),
    TemplateLayout(columns=1, header_style="left", spacing="normal",
                   experience_style="timeline", skill_style="chips"),
    TemplateLayout(columns=1, header_style="centered", spacing="relaxed", monogram=True),
    TemplateLayout(columns=1, header_style="banner", spacing="compact", skill_style="chips"),
    TemplateLayout(columns=2, header_style="left", sidebar="left", spacing="relaxed",
                   experience_style="timeline"),
]


def _themed_variant(name: str) -> tuple[TemplateColors, TemplateLayout, str]:
    """Deterministically vary colors/layout per template name so gallery
    cards are visually distinct (metadata-only web themes have no assets)."""
    seed = sum(ord(c) for c in name)
    palette = _WEB_PALETTES[seed % len(_WEB_PALETTES)]
    layout = _WEB_LAYOUTS[(seed // 7) % len(_WEB_LAYOUTS)].model_copy(deep=True)
    colors = TemplateColors(primary=palette["primary"], accent=palette["accent"])
    if layout.sidebar != "none":
        if seed % 2 == 0:
            colors.sidebar_bg = palette["primary"]
            colors.sidebar_text = "#ffffff"
        else:
            colors.sidebar_bg = "#f2f4f8"
            colors.sidebar_text = "#333333"
    return colors, layout, palette["style"]


def _normalize_popularity(score: float) -> int:
    """npm registry scores vary in scale (0-1 or 0-100+); clamp to 0-90 so
    curated featured templates (95+) always rank above community metadata."""
    value = score * 100 if score <= 1 else score
    return max(0, min(90, int(value)))


class TemplateSearchAgent(BaseAgent):
    name = "template_search"

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.settings = get_settings()
        self.store = get_store()

    # ----------------------------------------------------------------- seed

    def seed_catalog(self) -> int:
        """Install curated designs (idempotent) and build their previews."""
        added = 0
        preview_dir = Path(self.settings.downloaded_templates_dir) / "previews"
        for meta in _catalog():
            existing = self.store.get(TEMPLATES_COLLECTION, meta.id)
            preview = preview_dir / f"{meta.id}.svg"
            if not preview.exists():
                generate_svg_preview(meta, preview)
            meta.preview_path = str(preview)
            if existing is None:
                added += 1
            self.store.put(TEMPLATES_COLLECTION, meta.model_dump(mode="json"))
        self.logger.info("Catalog seeded (%d new)", added)
        return added

    # ------------------------------------------------------------------ web

    def search_web(self, max_total: int = 80) -> int:
        """Fetch open-source theme metadata from the npm registry (best effort).

        Multiple search queries widen coverage; results are deduped by package
        URL and each is assigned one of 12 distinct layout archetypes.
        """
        added = 0
        existing_urls = {
            t.get("origin_url") for t in self.store.list(TEMPLATES_COLLECTION)
        }
        registry_queries = [
            {"text": "keywords:jsonresume-theme", "size": 60},
            {"text": "keywords:resume-theme", "size": 25},
            {"text": "keywords:resume-template", "size": 25},
            {"text": "keywords:cv-template", "size": 20},
        ]
        packages: list[dict] = []
        seen_names: set[str] = set()
        try:
            with httpx.Client(timeout=15) as client:
                for params in registry_queries:
                    try:
                        resp = client.get(NPM_SEARCH_URL, params=params)
                        resp.raise_for_status()
                        for obj in resp.json().get("objects", []):
                            name = obj.get("package", {}).get("name", "")
                            if name and name not in seen_names:
                                seen_names.add(name)
                                packages.append(obj)
                    except httpx.HTTPError as exc:
                        self.logger.warning("Query %s failed: %s", params["text"], exc)
        except httpx.HTTPError as exc:
            self.logger.warning("Web template search skipped (offline?): %s", exc)
            return 0
        packages = packages[:max_total]

        preview_dir = Path(self.settings.downloaded_templates_dir) / "previews"
        for obj in packages:
            pkg = obj.get("package", {})
            url = pkg.get("links", {}).get("npm", "")
            if not url or url in existing_urls:
                continue
            raw_name = pkg.get("name", "")
            for prefix in ("jsonresume-theme-", "resume-theme-", "resume-template-", "cv-template-"):
                raw_name = raw_name.replace(prefix, "")
            slug = re.sub(r"[^a-z0-9]+", "-", raw_name.lower()).strip("-") or "theme"
            colors, layout, style = _themed_variant(raw_name)
            meta = TemplateMeta(
                id=f"web-{slug}",
                name=slug.replace("-", " ").title(),
                source=TemplateSource.WEB,
                style=style,
                colors=colors,
                layout=layout,
                author=(pkg.get("publisher") or {}).get("username", "community"),
                license=pkg.get("license") or "open source",
                origin_url=url,
                description=pkg.get("description", "")[:200],
                tags=["community", "jsonresume"],
                ats_score=75,
                html_template="master.html.j2",
                popularity=_normalize_popularity(obj.get("score", {}).get("final", 0.4)),
            )
            preview = preview_dir / f"{meta.id}.svg"
            generate_svg_preview(meta, preview)
            meta.preview_path = str(preview)
            self.store.put(TEMPLATES_COLLECTION, meta.model_dump(mode="json"))
            existing_urls.add(url)
            added += 1
        self.logger.info("Web search added %d community templates", added)
        return added

    # ------------------------------------------------------------------ run

    def purge_unsaved_web(self) -> int:
        """Drop web templates the user hasn't saved — they get re-fetched fresh.

        Saved templates (and all builtin/uploaded ones) always persist in the DB.
        """
        removed = 0
        for doc in self.store.list(TEMPLATES_COLLECTION):
            if doc.get("source") == "web" and not doc.get("saved"):
                self.store.delete(TEMPLATES_COLLECTION, doc["id"])
                removed += 1
        if removed:
            self.logger.info("Purged %d unsaved web templates before refresh", removed)
        return removed

    def run(self, include_web: bool = True) -> AgentResult:
        seeded = self.seed_catalog()
        web = 0
        if include_web and self.settings.template_search_enabled:
            self.purge_unsaved_web()
            web = self.search_web()
        total = len(self.store.list(TEMPLATES_COLLECTION))
        return self.ok(
            f"Template library refreshed: {seeded} curated added, {web} web templates fetched",
            seeded=seeded, web_added=web, total=total,
            queries=SEARCH_QUERIES,
        )
