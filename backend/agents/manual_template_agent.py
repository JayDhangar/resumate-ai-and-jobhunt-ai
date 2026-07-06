"""Agent 4 — Manual Template.

Handles user-uploaded template files (PDF / DOCX / PNG / JPG): stores them in
``templates/uploaded/``, delegates analysis to the Template Parser Agent, and
registers the result so uploaded templates appear beside web templates in the
gallery under "My Templates".
"""
from __future__ import annotations

from pathlib import Path

from core.config import get_settings
from models.schemas import AgentResult, TemplateMeta, TemplateSource, new_id
from services.file_service import save_upload
from services.storage import get_store
from .base_agent import BaseAgent
from .template_parser_agent import TemplateParserAgent
from .template_search_agent import TEMPLATES_COLLECTION


class ManualTemplateAgent(BaseAgent):
    name = "manual_template"

    def __init__(self, parser: TemplateParserAgent | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.settings = get_settings()
        self.store = get_store()
        self.parser = parser or TemplateParserAgent()

    def run(self, content: bytes, filename: str, display_name: str = "") -> AgentResult:
        try:
            path = save_upload(
                content,
                filename,
                self.settings.uploaded_templates_dir,
                self.settings.allowed_template_extensions,
            )
        except Exception as exc:  # noqa: BLE001
            return self.fail(str(exc))

        meta = TemplateMeta(
            id=f"uploaded-{new_id()[:12]}",
            name=display_name or Path(filename).stem.replace("_", " ").replace("-", " ").title(),
            source=TemplateSource.UPLOADED,
            style="custom",
            author="You",
            license="user-provided",
            source_file=str(path),
            html_template="master.html.j2",
            description=f"Uploaded template ({Path(filename).suffix.upper().lstrip('.')})",
            tags=["uploaded", "custom"],
            ats_score=70,
        )
        parse_result = self.parser.run(path, meta)
        if not parse_result.ok:
            self.logger.warning("Parser degraded for %s: %s", filename, parse_result.detail)

        self.store.put(TEMPLATES_COLLECTION, meta.model_dump(mode="json"))
        return self.ok(
            f"Template '{meta.name}' uploaded and analysed",
            template=meta.model_dump(mode="json"),
        )
