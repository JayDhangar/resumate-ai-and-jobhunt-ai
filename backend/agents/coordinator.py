"""Coordinator — orchestrates the multi-agent workflow.

The API layer talks only to this class. It wires together:
Reader -> (storage) -> Editor -> Generator -> Export, plus the template
search / parser / manual-upload agents, version history and prompt history.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from core.config import get_settings
from core.exceptions import NotFoundError, ResumeBuilderError
from core.logging_config import get_logger
from models.schemas import (
    PromptHistoryEntry,
    ResumeData,
    ResumeRecord,
    ResumeVersion,
    ScoreReport,
    TemplateMeta,
)
from services.file_service import save_upload
from services.scoring_service import score_resume
from services.storage import get_store
from .export_agent import ExportAgent
from .manual_template_agent import ManualTemplateAgent
from .resume_editor_agent import ResumeEditorAgent
from .resume_generator_agent import ResumeGeneratorAgent
from .resume_reader_agent import ResumeReaderAgent
from .template_parser_agent import TemplateParserAgent
from .template_search_agent import TEMPLATES_COLLECTION, TemplateSearchAgent

RESUMES_COLLECTION = "resumes"
logger = get_logger("coordinator")


class Coordinator:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.store = get_store()
        self.reader = ResumeReaderAgent()
        self.searcher = TemplateSearchAgent()
        self.parser = TemplateParserAgent()
        self.manual = ManualTemplateAgent(parser=self.parser)
        self.editor = ResumeEditorAgent()
        self.generator = ResumeGeneratorAgent()
        self.exporter = ExportAgent()

    # ----------------------------------------------------------- resumes

    def upload_resume(self, content: bytes, filename: str) -> ResumeRecord:
        path = save_upload(
            content, filename,
            self.settings.uploads_dir,
            self.settings.allowed_resume_extensions,
        )
        data, raw_text = self.reader.run(path)
        record = ResumeRecord(
            title=data.name or Path(filename).stem,
            data=data,
            original_file=str(path),
            original_filename=filename,
            raw_text=raw_text[:50000],
        )
        record.versions.append(ResumeVersion(version=1, label="Original upload", data=data))
        self._save(record)
        logger.info("Resume %s created from %s", record.id, filename)
        return record

    def create_blank_resume(self, title: str = "New Resume") -> ResumeRecord:
        record = ResumeRecord(title=title)
        record.versions.append(ResumeVersion(version=1, label="Created from scratch", data=record.data))
        self._save(record)
        return record

    def get_resume(self, resume_id: str) -> ResumeRecord:
        doc = self.store.get(RESUMES_COLLECTION, resume_id)
        if doc is None:
            raise NotFoundError(f"Resume '{resume_id}' not found")
        return ResumeRecord.model_validate(doc)

    def list_resumes(self) -> list[ResumeRecord]:
        records = [ResumeRecord.model_validate(d) for d in self.store.list(RESUMES_COLLECTION)]
        return sorted(records, key=lambda r: str(r.updated_at), reverse=True)

    def delete_resume(self, resume_id: str) -> bool:
        return self.store.delete(RESUMES_COLLECTION, resume_id)

    def update_resume(
        self, resume_id: str, data: ResumeData,
        save_version: bool = False, change_note: str = "",
    ) -> ResumeRecord:
        record = self.get_resume(resume_id)
        record.data = data
        if save_version:
            self._snapshot(record, label=change_note or "Manual save")
        self._save(record)
        return record

    def save_tweaks(self, resume_id: str, tweaks: dict) -> ResumeRecord:
        """Persist the customize-panel state on the record so layout choices
        (like a 1-page PDF) follow the resume across sessions and browsers."""
        record = self.get_resume(resume_id)
        record.ui_tweaks = {str(k): str(v) for k, v in tweaks.items() if v}
        self._save(record)
        return record

    def edit_resume(self, resume_id: str, instructions: str, save_version: bool = True) -> tuple[ResumeRecord, dict]:
        record = self.get_resume(resume_id)
        template = self._maybe_template(record.selected_template_id)
        result = self.editor.run(record.data, instructions, template)
        if not result.ok:
            raise ResumeBuilderError(result.detail, status_code=422)
        updated = ResumeData.model_validate(result.data["resume"])
        record.data = updated
        record.prompt_history.append(PromptHistoryEntry(prompt=instructions, kind="resume"))
        if save_version:
            self._snapshot(record, label=instructions[:80])
        self._save(record)
        return record, {"applied": result.data.get("applied", []), "scores": result.data.get("scores", {})}

    # ----------------------------------------------------------- versions

    def _snapshot(self, record: ResumeRecord, label: str = "") -> None:
        next_version = (record.versions[-1].version + 1) if record.versions else 1
        record.versions.append(
            ResumeVersion(version=next_version, label=label or f"Version {next_version}", data=record.data)
        )
        # keep history bounded
        if len(record.versions) > 50:
            record.versions = record.versions[-50:]

    def restore_version(self, resume_id: str, version: int) -> ResumeRecord:
        record = self.get_resume(resume_id)
        match = next((v for v in record.versions if v.version == version), None)
        if match is None:
            raise NotFoundError(f"Version {version} not found for resume '{resume_id}'")
        record.data = match.data.model_copy(deep=True)
        self._snapshot(record, label=f"Restored from version {version}")
        self._save(record)
        return record

    # ---------------------------------------------------------- templates

    def refresh_templates(self, include_web: bool = True) -> dict:
        return self.searcher.run(include_web=include_web).model_dump()

    def list_templates(self) -> list[TemplateMeta]:
        templates = [TemplateMeta.model_validate(d) for d in self.store.list(TEMPLATES_COLLECTION)]
        if not templates:
            self.searcher.seed_catalog()
            templates = [TemplateMeta.model_validate(d) for d in self.store.list(TEMPLATES_COLLECTION)]
        return sorted(templates, key=lambda t: (-t.popularity, t.name))

    def get_template(self, template_id: str) -> TemplateMeta:
        doc = self.store.get(TEMPLATES_COLLECTION, template_id)
        if doc is None:
            raise NotFoundError(f"Template '{template_id}' not found")
        return TemplateMeta.model_validate(doc)

    def _maybe_template(self, template_id: str) -> TemplateMeta | None:
        if not template_id:
            return None
        try:
            return self.get_template(template_id)
        except NotFoundError:
            return None

    def upload_template(self, content: bytes, filename: str, display_name: str = "") -> TemplateMeta:
        result = self.manual.run(content, filename, display_name)
        if not result.ok:
            raise ResumeBuilderError(result.detail, status_code=422)
        return TemplateMeta.model_validate(result.data["template"])

    def delete_template(self, template_id: str) -> bool:
        return self.store.delete(TEMPLATES_COLLECTION, template_id)

    def select_template(self, resume_id: str, template_id: str) -> ResumeRecord:
        record = self.get_resume(resume_id)
        self.get_template(template_id)  # validate existence
        record.selected_template_id = template_id
        self._save(record)
        return record

    # --------------------------------------------------------- generation

    def generate(
        self,
        resume_id: str,
        template_id: str = "",
        template_instructions: str | None = None,
        resume_instructions: str = "",
        formats: list[str] | None = None,
    ) -> dict:
        record = self.get_resume(resume_id)

        if resume_instructions.strip():
            record, _ = self.edit_resume(resume_id, resume_instructions, save_version=True)

        # None means "reuse what this resume last generated with", so on-demand
        # exports (like the download route) keep the user's layout choices
        if template_instructions is None:
            template_instructions = record.template_instructions
        else:
            record.template_instructions = template_instructions

        tid = template_id or record.selected_template_id
        template = self._maybe_template(tid)
        if template is None:
            templates = self.list_templates()
            template = templates[0]
        if template_instructions.strip():
            record.prompt_history.append(
                PromptHistoryEntry(prompt=template_instructions, kind="template")
            )
        record.selected_template_id = template.id

        gen = self.generator.run(
            record.data, template, template_instructions, output_name=f"resume_{record.id[:8]}"
        )
        if not gen.ok:
            raise ResumeBuilderError(gen.detail, status_code=422)
        html = gen.data["html"]
        adjusted = TemplateMeta.model_validate(gen.data["template"])

        export = self.exporter.run(
            record.data, adjusted, html,
            formats or ["html"], output_name=f"resume_{record.id[:8]}",
        )
        record.generated_files.update(export.data.get("files", {}))
        self._save(record)
        return {
            "resume_id": record.id,
            "template": adjusted.model_dump(mode="json"),
            "html": html,
            "files": export.data.get("files", {}),
            "errors": export.data.get("errors", {}),
        }

    def scores(self, resume_id: str, job_description: str = "") -> ScoreReport:
        record = self.get_resume(resume_id)
        return score_resume(record.data, job_description)

    # ------------------------------------------------------------- utils

    def _save(self, record: ResumeRecord) -> None:
        record.updated_at = datetime.now(timezone.utc)
        self.store.put(RESUMES_COLLECTION, record.model_dump(mode="json"))


_coordinator: Coordinator | None = None


def get_coordinator() -> Coordinator:
    global _coordinator
    if _coordinator is None:
        _coordinator = Coordinator()
    return _coordinator


def reset_coordinator() -> None:
    global _coordinator
    _coordinator = None
