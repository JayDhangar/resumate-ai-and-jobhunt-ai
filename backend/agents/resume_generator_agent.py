"""Agent 6 — Resume Generator.

Renders a resume + selected template into a polished HTML document via the
built-in Jinja2 engine. Free-form template instructions ("make colors blue",
"use two columns", "make compact", ...) are interpreted with the LLM when
available, or a keyword parser otherwise, and applied as adjustments on top of
the template's metadata. Supports ATS / modern / professional / creative /
corporate styles.
"""
from __future__ import annotations

import re
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from core.config import get_settings
from core.exceptions import LLMUnavailableError, TemplateError
from models.schemas import AgentResult, ResumeData, TemplateMeta
from .base_agent import BaseAgent

ADJUSTMENT_SYSTEM_PROMPT = """You translate template styling instructions into JSON adjustments.
Given a resume template's current settings and user instructions, return JSON:
{
  "colors": {"primary": "#hex", "accent": "#hex", "text": "#hex", "background": "#hex", "sidebar_bg": "#hex"},
  "layout": {"columns": 1|2, "header_style": "centered|left|banner", "sidebar": "none|left|right",
             "spacing": "compact|normal|relaxed", "uses_icons": bool, "section_divider": "line|none|dots|block"},
  "fonts": {"heading": "css font stack", "body": "css font stack", "base_size_pt": number,
            "name_size_pt": number, "section_size_pt": number},
  "hide_photo": bool
}
Only include keys the user asked to change. Return ONLY JSON.
Color taste rules: resumes are professional documents — always choose muted, desaturated,
print-friendly tones (e.g. green -> #2f7d4f, never #00ff00). Never change "background" or
"text" unless the user explicitly mentions the page background or body text color."""

COLOR_WORDS = {
    "blue": ("#14508c", "#1d6fc4"), "navy": ("#122c4f", "#1d4e89"),
    "green": ("#1d6b3a", "#2f9e57"), "red": ("#a8262e", "#d13f47"),
    "purple": ("#5b2a86", "#7c4dbd"), "teal": ("#116466", "#2a9d8f"),
    "orange": ("#c85311", "#e8752a"), "black": ("#111111", "#333333"),
    "gray": ("#444444", "#6b6b6b"), "grey": ("#444444", "#6b6b6b"),
    "gold": ("#8a6d1a", "#a67c00"), "pink": ("#b23a67", "#d6538c"),
}

def _darken(hex_color: str, factor: float) -> str:
    """Return hex_color with each channel multiplied by factor (0..1)."""
    value = hex_color.lstrip("#")
    rgb = tuple(max(0, min(255, int(int(value[i:i + 2], 16) * factor))) for i in (0, 2, 4))
    return "#{:02x}{:02x}{:02x}".format(*rgb)


SECTION_TITLE_DEFAULTS = {
    "summary": "Summary", "skills": "Skills", "experience": "Experience",
    "projects": "Projects", "education": "Education",
    "certifications": "Certifications", "awards": "Awards", "languages": "Languages",
}


INSTRUCTION_CATEGORIES: list[tuple[str, re.Pattern]] = [
    ("font", re.compile(r"\b(serif|sans)\b", re.I)),
    ("color", re.compile(r"\bcolors?\b", re.I)),
    ("spacing", re.compile(r"\b(compact|spacing|airy|relaxed|tight)\b", re.I)),
    ("columns", re.compile(r"\bcolumns?\b", re.I)),
    ("header", re.compile(r"\b(centered|banner|header)\b", re.I)),
    ("size", re.compile(r"\b(font size|bigger text|larger text|smaller text)\b", re.I)),
    ("pages", re.compile(r"\b(one|two|1|2|single)[ -]?pages?\b", re.I)),
    ("photo", re.compile(r"\bphoto\b|\bpicture\b|\bheadshot\b", re.I)),
]


def dedupe_instructions(instructions: str) -> str:
    """Keep only the LAST instruction per styling category.

    UI tweak controls and repeated prompts can stack contradictory lines
    ("make it serif" then "make it sans"); the latest intent wins.
    """
    lines = [ln.strip() for ln in re.split(r"[\n;]+", instructions) if ln.strip()]
    kept: list[str] = []
    seen_categories: set[str] = set()
    for line in reversed(lines):
        category = next((name for name, pat in INSTRUCTION_CATEGORIES if pat.search(line)), None)
        if category is None:
            kept.append(line)
        elif category not in seen_categories:
            seen_categories.add(category)
            kept.append(line)
    return "\n".join(reversed(kept))


class ResumeGeneratorAgent(BaseAgent):
    name = "resume_generator"

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.settings = get_settings()
        self._env = Environment(
            loader=FileSystemLoader(self.settings.builtin_templates_dir),
            autoescape=select_autoescape(["html", "j2"]),
        )

    # ----------------------------------------------------- adjustments

    def parse_adjustments(self, template: TemplateMeta, instructions: str) -> TemplateMeta:
        """Return a copy of the template with user styling instructions applied."""
        adjusted = template.model_copy(deep=True)
        if not instructions.strip():
            return adjusted
        instructions = dedupe_instructions(instructions)
        # deterministic keyword rules first (curated palette, no LLM color taste issues);
        # only lines the rules don't understand go to the LLM
        adjusted, unhandled = self._keyword_adjustments(adjusted, instructions)
        if unhandled and self.llm.available:
            remaining = "\n".join(unhandled)
            low = remaining.lower()
            try:
                payload = self.llm.complete_json(
                    ADJUSTMENT_SYSTEM_PROMPT,
                    "Current settings:\n"
                    f"colors={adjusted.colors.model_dump()}\n"
                    f"layout={adjusted.layout.model_dump()}\n"
                    f"fonts={adjusted.fonts.model_dump()}\n\n"
                    f"Instructions: {remaining}",
                    max_tokens=1000,
                    op="style_template",
                )
                # never let the model repaint the page/text unless explicitly asked —
                # accent recolors that also change background made previews unreadable
                if isinstance(payload.get("colors"), dict):
                    if "background" not in low:
                        payload["colors"].pop("background", None)
                    if "text color" not in low and "text colour" not in low:
                        payload["colors"].pop("text", None)
                for key in ("colors", "layout", "fonts"):
                    if isinstance(payload.get(key), dict):
                        current = getattr(adjusted, key).model_dump()
                        current.update({k: v for k, v in payload[key].items() if v not in (None, "")})
                        setattr(adjusted, key, type(getattr(adjusted, key)).model_validate(current))
            except (LLMUnavailableError, Exception) as exc:  # noqa: BLE001
                self.logger.warning("LLM adjustment parse failed (%s); keyword result kept", exc)
        return adjusted

    def _keyword_adjustments(self, adjusted: TemplateMeta, instructions: str) -> tuple[TemplateMeta, list[str]]:
        """Apply deterministic styling rules line by line.

        Returns the adjusted template plus the lines no rule understood
        (those are forwarded to the LLM by the caller).
        """
        unhandled: list[str] = []
        for line in re.split(r"[\n;]+", instructions):
            line = line.strip()
            if not line:
                continue
            if not self._apply_keyword_line(adjusted, line.lower()):
                unhandled.append(line)
        return adjusted, unhandled

    def _apply_keyword_line(self, adjusted: TemplateMeta, low: str) -> bool:
        handled = False
        # explicit hex color (from the UI color picker): accent = picked color,
        # primary = a darker shade of it for headings
        if match := re.search(r"colou?rs?\b[^#]*#([0-9a-f]{6}|[0-9a-f]{3})\b", low):
            hex_value = match.group(1)
            if len(hex_value) == 3:
                hex_value = "".join(c * 2 for c in hex_value)
            accent = f"#{hex_value}"
            adjusted.colors.accent = accent
            adjusted.colors.primary = _darken(accent, 0.72)
            if adjusted.layout.sidebar != "none" and adjusted.colors.sidebar_text == "#ffffff":
                adjusted.colors.sidebar_bg = adjusted.colors.primary
            handled = True
        for word, (primary, accent) in COLOR_WORDS.items():
            if handled:
                break  # explicit hex wins over color words in the same line
            if re.search(rf"\bcolou?rs?\b.*\b{word}\b|\b{word}\b.*\bcolou?rs?\b", low):
                adjusted.colors.primary = primary
                adjusted.colors.accent = accent
                if adjusted.layout.sidebar != "none" and adjusted.colors.sidebar_text == "#ffffff":
                    adjusted.colors.sidebar_bg = primary
                handled = True
                break
        if re.search(r"\btwo columns?\b|\b2 columns?\b", low):
            adjusted.layout.columns = 2
            if adjusted.layout.sidebar == "none":
                adjusted.layout.sidebar = "left"
            handled = True
        if re.search(r"\bone column\b|\bsingle column\b", low):
            adjusted.layout.columns = 1
            adjusted.layout.sidebar = "none"
            handled = True
        if re.search(r"\bcompact\b|\btight\b|less spacing|reduce spacing", low):
            adjusted.layout.spacing = "compact"
            handled = True
        if re.search(r"increase spacing|more spacing|\bairy\b|\brelaxed\b", low):
            adjusted.layout.spacing = "relaxed"
            handled = True
        if "centered" in low:
            adjusted.layout.header_style = "centered"
            handled = True
        if "banner" in low:
            adjusted.layout.header_style = "banner"
            handled = True
        if "split header" in low or "contact on the right" in low:
            adjusted.layout.header_style = "split"
            handled = True
        if "timeline" in low:
            adjusted.layout.experience_style = "plain" if re.search(r"\b(no|remove|without)\b.*timeline", low) else "timeline"
            handled = True
        if "monogram" in low or "initial badge" in low:
            adjusted.layout.monogram = not re.search(r"\b(no|remove|without)\b.*(monogram|badge)", low)
            handled = True
        if re.search(r"\bchips?\b|\bpills?\b|\btags?\b", low) and "skill" in low:
            adjusted.layout.skill_style = "chips"
            handled = True
        if re.search(r"\b(one|1|single)[ -]?page\b", low):
            adjusted.layout.page_mode = "one"
            handled = True
        if re.search(r"\b(two|2)[ -]?pages?\b", low):
            adjusted.layout.page_mode = "two"
            handled = True
        if re.search(r"\bauto\b.*\bpages?\b|\bpages?\b.*\bauto\b", low):
            adjusted.layout.page_mode = "auto"
            handled = True
        if re.search(r"\b(show|add|with|include)\b.*\b(photo|picture|headshot)\b", low):
            adjusted.layout.show_photo = True
            handled = True
        if re.search(r"\b(hide|remove|no|without)\b.*\b(photo|picture|headshot)\b", low):
            adjusted.layout.show_photo = False
            handled = True
        if "serif" in low and "sans" not in low:
            adjusted.fonts.heading = "Georgia, serif"
            adjusted.fonts.body = "Georgia, serif"
            handled = True
        if "sans" in low:
            adjusted.fonts.heading = "Helvetica, Arial, sans-serif"
            adjusted.fonts.body = "Helvetica, Arial, sans-serif"
            handled = True
        if match := re.search(r"font size\s*(\d{1,2})", low):
            adjusted.fonts.base_size_pt = float(match.group(1))
            handled = True
        if "bigger text" in low or "larger text" in low:
            adjusted.fonts.base_size_pt += 1
            handled = True
        if "smaller text" in low:
            adjusted.fonts.base_size_pt = max(8.0, adjusted.fonts.base_size_pt - 1)
            handled = True
        return handled

    # ----------------------------------------------------------- rendering

    def render_html(self, resume: ResumeData, template: TemplateMeta) -> str:
        if template.layout.page_mode == "one":
            # harder compaction: smaller type so more content fits before shrink-to-fit kicks in
            template = template.model_copy(deep=True)
            template.fonts.base_size_pt = max(8.5, template.fonts.base_size_pt - 0.5)
            template.fonts.name_size_pt = max(16.0, template.fonts.name_size_pt - 4)
            template.fonts.section_size_pt = max(10.0, template.fonts.section_size_pt - 1)
        template_file = template.html_template or "master.html.j2"
        try:
            jinja_template = self._env.get_template(template_file)
        except Exception as exc:  # noqa: BLE001
            raise TemplateError(f"Template file '{template_file}' cannot be loaded: {exc}") from exc
        titles = dict(SECTION_TITLE_DEFAULTS)
        titles.update({k.lower(): v for k, v in resume.section_titles.items()})
        return jinja_template.render(
            resume=resume,
            t=template,
            layout=template.layout,
            colors=template.colors,
            fonts=template.fonts,
            titles=titles,
            section_order=resume.section_order or list(SECTION_TITLE_DEFAULTS),
        )

    # ------------------------------------------------------------------ run

    def run(
        self,
        resume: ResumeData,
        template: TemplateMeta,
        template_instructions: str = "",
        output_name: str = "resume",
    ) -> AgentResult:
        try:
            adjusted = self.parse_adjustments(template, template_instructions)
            html = self.render_html(resume, adjusted)
        except TemplateError as exc:
            return self.fail(exc.message)
        out_dir = Path(self.settings.generated_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        html_path = out_dir / f"{output_name}.html"
        html_path.write_text(html, encoding="utf-8")
        return self.ok(
            f"Resume rendered with template '{adjusted.name}'",
            html=html,
            html_path=str(html_path),
            template=adjusted.model_dump(mode="json"),
        )
