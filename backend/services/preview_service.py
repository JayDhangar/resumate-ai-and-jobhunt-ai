"""Template preview generation.

Renderable (builtin/web) templates get a vector SVG thumbnail drawn from their
layout descriptor; uploaded files get a raster thumbnail via PyMuPDF / Pillow.
"""
from __future__ import annotations

import html
from pathlib import Path

from models.schemas import TemplateMeta

PREVIEW_W, PREVIEW_H = 320, 414  # A4-ish aspect


def _bar(x: float, y: float, w: float, h: float, fill: str, rx: float = 2) -> str:
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}"/>'


def generate_svg_preview(meta: TemplateMeta, dest: Path) -> Path:
    """Draw a stylised thumbnail of the template layout as an SVG file."""
    colors = meta.colors
    layout = meta.layout
    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{PREVIEW_W}" height="{PREVIEW_H}" '
        f'viewBox="0 0 {PREVIEW_W} {PREVIEW_H}">',
        f'<rect width="{PREVIEW_W}" height="{PREVIEW_H}" fill="{colors.background}"/>',
    ]
    pad = 22
    y = pad

    sidebar_w = 100 if layout.sidebar in ("left", "right") else 0
    sidebar_x = 0 if layout.sidebar == "left" else PREVIEW_W - sidebar_w
    main_x = pad + (sidebar_w if layout.sidebar == "left" else 0)
    main_w = PREVIEW_W - 2 * pad - sidebar_w

    if sidebar_w:
        sb_color = colors.sidebar_bg or colors.primary
        sb_text = (colors.sidebar_text or "#ffffff") + "88"
        parts.append(_bar(sidebar_x, 0, sidebar_w, PREVIEW_H, sb_color, 0))
        sy = 30
        for _ in range(6):
            parts.append(_bar(sidebar_x + 14, sy, sidebar_w - 28, 7, sb_text))
            sy += 18

    # header
    if layout.header_style == "banner":
        parts.append(_bar(0 if not sidebar_w else main_x - pad, 0, PREVIEW_W, 64, colors.primary, 0))
        parts.append(_bar(main_x, 20, main_w * 0.55, 12, "#ffffffcc"))
        parts.append(_bar(main_x, 40, main_w * 0.35, 7, "#ffffff88"))
        y = 84
    elif layout.header_style == "split":
        name_x = main_x + (26 if layout.monogram else 0)
        if layout.monogram:
            parts.append(f'<circle cx="{main_x + 10}" cy="{y + 7}" r="10" fill="{colors.accent}"/>')
        parts.append(_bar(name_x, y, main_w * 0.4, 13, colors.primary))
        parts.append(_bar(main_x + main_w * 0.72, y, main_w * 0.28, 5, colors.text + "55"))
        parts.append(_bar(main_x + main_w * 0.72, y + 9, main_w * 0.28, 5, colors.text + "55"))
        parts.append(_bar(main_x, y + 24, main_w, 2.5, colors.accent, 0))
        y += 40
    else:
        name_w = main_w * 0.5
        name_x = main_x + (main_w - name_w) / 2 if layout.header_style == "centered" else main_x
        if layout.monogram:
            parts.append(f'<circle cx="{name_x - 14}" cy="{y + 7}" r="10" fill="{colors.accent}"/>')
        parts.append(_bar(name_x, y, name_w, 13, colors.primary))
        parts.append(_bar(name_x, y + 20, name_w * 0.7, 6, colors.accent))
        y += 44

    # body sections
    section_gap = {"compact": 10, "normal": 14, "relaxed": 20}.get(layout.spacing, 14)
    cols = max(1, min(layout.columns, 2)) if not sidebar_w else 1
    col_w = (main_w - (cols - 1) * 14) / cols
    timeline = layout.experience_style == "timeline"
    chips = layout.skill_style == "chips"
    for col in range(cols):
        cx = main_x + col * (col_w + 14)
        cy = y
        for section_i in range(4):
            parts.append(_bar(cx, cy, col_w * 0.45, 8, colors.accent))
            cy += 14
            if layout.section_divider == "line":
                parts.append(_bar(cx, cy - 3, col_w, 1.5, colors.accent + "66", 0))
            if chips and section_i == 0:
                chip_x = cx
                for chip_w in (col_w * 0.2, col_w * 0.26, col_w * 0.18, col_w * 0.24):
                    parts.append(
                        f'<rect x="{chip_x}" y="{cy}" width="{chip_w}" height="9" rx="4.5" '
                        f'fill="none" stroke="{colors.accent}" stroke-width="1.2"/>'
                    )
                    chip_x += chip_w + 5
                cy += 16
                for _ in range(2):
                    parts.append(_bar(cx, cy, col_w * 0.95, 5, colors.text + "33"))
                    cy += 10
            elif timeline and section_i == 1:
                parts.append(_bar(cx + 1, cy, 2.5, 30, colors.accent, 0))
                for _ in range(3):
                    parts.append(_bar(cx + 10, cy, col_w * 0.85, 5, colors.text + "33"))
                    cy += 10
            else:
                for _ in range(3):
                    parts.append(_bar(cx, cy, col_w * 0.95, 5, colors.text + "33"))
                    cy += 10
            cy += section_gap

    label = html.escape(meta.style.upper())
    parts.append(
        f'<text x="{PREVIEW_W - 8}" y="{PREVIEW_H - 8}" text-anchor="end" '
        f'font-family="Arial" font-size="9" fill="{colors.accent}99">{label}</text>'
    )
    parts.append("</svg>")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("".join(parts), encoding="utf-8")
    return dest


def generate_file_preview(source: Path, dest: Path) -> Path | None:
    """Raster thumbnail for an uploaded/downloaded file (PDF or image)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    ext = source.suffix.lower()
    try:
        if ext == ".pdf":
            import fitz

            with fitz.open(source) as doc:
                if doc.page_count == 0:
                    return None
                pix = doc[0].get_pixmap(dpi=72)
                pix.save(str(dest))
                return dest
        if ext in (".png", ".jpg", ".jpeg"):
            from PIL import Image

            with Image.open(source) as img:
                img.thumbnail((PREVIEW_W * 2, PREVIEW_H * 2))
                img.convert("RGB").save(str(dest))
                return dest
    except Exception:  # noqa: BLE001 - previews are best-effort
        return None
    return None
