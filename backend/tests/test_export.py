"""Export agent format conversions (offline)."""
from pathlib import Path

from agents.export_agent import ExportAgent
from agents.resume_generator_agent import ResumeGeneratorAgent
from models.schemas import TemplateMeta


def _template() -> TemplateMeta:
    return TemplateMeta(name="Test Template", html_template="master.html.j2")


def test_markdown_contains_all_sections(sample_resume):
    md = ExportAgent().to_markdown(sample_resume)
    for expected in ("# Alex Morgan", "## Summary", "## Skills", "## Experience",
                     "## Education", "Nimbus Labs"):
        assert expected in md


def test_full_export_pipeline(sample_resume, tmp_path):
    generator = ResumeGeneratorAgent()
    html = generator.render_html(sample_resume, _template())
    assert "Alex Morgan" in html and "<html>" in html

    agent = ExportAgent()
    result = agent.run(sample_resume, _template(), html,
                       ["html", "pdf", "docx", "png", "md", "json"], output_name="test_export")
    assert result.ok, result.detail
    files = result.data["files"]
    assert set(files) == {"html", "pdf", "docx", "png", "md", "json"}
    for path in files.values():
        assert Path(path).is_file() and Path(path).stat().st_size > 0
    assert result.data["errors"] == {}


def test_unknown_format_reported(sample_resume):
    generator = ResumeGeneratorAgent()
    html = generator.render_html(sample_resume, _template())
    result = ExportAgent().run(sample_resume, _template(), html, ["html", "xyz"])
    assert result.ok
    assert "xyz" in result.data["errors"]
    assert "html" in result.data["files"]


def test_generator_keyword_adjustments(sample_resume):
    generator = ResumeGeneratorAgent()
    adjusted = generator.parse_adjustments(
        _template(), "make colors blue, use two columns, compact"
    )
    assert adjusted.colors.primary == "#14508c"
    assert adjusted.layout.columns == 2
    assert adjusted.layout.spacing == "compact"


def test_generator_hex_color_adjustment(sample_resume):
    generator = ResumeGeneratorAgent()
    adjusted = generator.parse_adjustments(_template(), "make colors #2a9d8f")
    assert adjusted.colors.accent == "#2a9d8f"
    assert adjusted.colors.primary == "#1e7166"  # darker shade for headings


def test_generator_contradictions_last_wins(sample_resume):
    generator = ResumeGeneratorAgent()
    adjusted = generator.parse_adjustments(
        _template(), "make colors blue\nmake colors green\nmake it serif\nmake it sans"
    )
    assert adjusted.colors.primary == "#1d6b3a"  # green won
    assert "sans" in adjusted.fonts.body
