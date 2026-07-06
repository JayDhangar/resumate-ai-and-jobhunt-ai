"""Agent 5 — Resume Editor.

The intelligent editing agent. Receives the resume JSON, the selected
template, and free-form user instructions ("Replace C++ with Rust", "Remove
internship", "Rewrite professionally", "Increase ATS score", ...) and returns
an updated resume. Information is never lost destructively: callers snapshot a
version before applying the edit, and the LLM is instructed to preserve
content it wasn't asked to change. Works without an LLM via rule-based edits.
"""
from __future__ import annotations

import json
import re

from core.exceptions import LLMUnavailableError
from models.schemas import AgentResult, ResumeData, TemplateMeta
from services.scoring_service import ACTION_VERB_UPGRADES, WEAK_PHRASES, score_resume
from .base_agent import BaseAgent

EDITOR_SYSTEM_PROMPT = """You are an expert resume editor. You receive a resume as JSON and user instructions.
Apply ONLY the requested changes and return the FULL updated resume as JSON with the identical schema.

Hard rules:
- NEVER drop or truncate sections, entries or fields the user did not ask you to change. Copy them verbatim.
- Never invent employers, dates, degrees or facts.
- Keep the same JSON structure and key names. "section_titles" maps canonical section keys (e.g. "projects") to custom display names.
- If asked to improve ATS score: strengthen action verbs, add measurable impact phrasing where content supports it, and align wording with common recruiter keywords — without fabricating facts.
- If asked to fix grammar or rewrite professionally: improve wording while preserving meaning and all facts.
Return ONLY the JSON object."""


class ResumeEditorAgent(BaseAgent):
    name = "resume_editor"

    # ------------------------------------------------------------------ LLM

    def _edit_with_llm(
        self, resume: ResumeData, instructions: str, template: TemplateMeta | None
    ) -> ResumeData:
        context = ""
        if template is not None:
            context = (
                f"\nSelected template: {template.name} (style: {template.style}, "
                f"ats_score: {template.ats_score})."
            )
        payload = self.llm.complete_json(
            EDITOR_SYSTEM_PROMPT,
            f"Instructions: {instructions}{context}\n\nResume JSON:\n"
            + json.dumps(resume.model_dump(mode="json"), ensure_ascii=False),
            max_tokens=8000,
            op="edit_resume",
        )
        updated = ResumeData.model_validate(payload)
        return self._guard_against_loss(resume, updated, instructions)

    def _guard_against_loss(
        self, before: ResumeData, after: ResumeData, instructions: str
    ) -> ResumeData:
        """Restore sections the model silently dropped without being asked to."""
        wants_removal = bool(re.search(r"\b(remove|delete|drop|cut)\b", instructions, re.I))
        for field in ("experience", "education", "projects", "skills",
                      "certifications", "languages", "awards"):
            before_items = getattr(before, field)
            after_items = getattr(after, field)
            if before_items and not after_items and not wants_removal:
                self.logger.warning("LLM dropped '%s' unrequested — restoring", field)
                setattr(after, field, before_items)
        if before.summary and not after.summary and not wants_removal:
            after.summary = before.summary
        return after

    # ------------------------------------------------------------ rule-based

    def _edit_with_rules(self, resume: ResumeData, instructions: str) -> tuple[ResumeData, list[str]]:
        """Deterministic fallback covering the most common edit commands."""
        applied: list[str] = []
        data = resume.model_copy(deep=True)

        for instruction in re.split(r"[\n;]+", instructions):
            instruction = instruction.strip()
            if not instruction:
                continue
            low = instruction.lower()

            if match := re.search(r"replace\s+(.+?)\s+with\s+(.+)", instruction, re.I):
                old, new = match.group(1).strip(" '\""), match.group(2).strip(" '\".")
                data = self._replace_everywhere(data, old, new)
                applied.append(f"Replaced '{old}' with '{new}'")
            elif match := re.search(r"rename\s+['\"]?(.+?)['\"]?\s+(?:to|as)\s+['\"]?(.+?)['\"]?$", instruction, re.I):
                old, new = match.group(1).strip(), match.group(2).strip(" '\".")
                key = old.lower().strip()
                data.section_titles[key] = new
                applied.append(f"Renamed section '{old}' to '{new}'")
            elif match := re.search(r"(?:remove|delete|drop)\s+(?:my\s+|the\s+)?(.+)", instruction, re.I):
                target = match.group(1).strip(" '\".").lower()
                removed = self._remove_matching(data, target)
                applied.append(
                    f"Removed {removed} item(s) matching '{target}'" if removed
                    else f"Nothing matched '{target}' to remove"
                )
            elif "grammar" in low or "professional" in low or "improve" in low or "ats" in low:
                count = self._polish_wording(data)
                applied.append(f"Strengthened wording in {count} place(s)")
            elif match := re.search(r"(?:change|update|set)\s+(?:my\s+)?summary\s*(?:to|:)\s*(.+)", instruction, re.I | re.S):
                data.summary = match.group(1).strip(" :")
                applied.append("Summary updated")
            elif "shorten" in low:
                for exp in data.experience:
                    exp.bullets = exp.bullets[:3]
                applied.append("Shortened experience to 3 bullets per role")
            else:
                applied.append(f"Skipped (needs AI provider): '{instruction[:60]}'")
        return data, applied

    def _replace_everywhere(self, data: ResumeData, old: str, new: str) -> ResumeData:
        pattern = re.compile(re.escape(old), re.IGNORECASE)

        def sub(text: str) -> str:
            return pattern.sub(new, text) if text else text

        raw = data.model_dump()

        def walk(node):
            if isinstance(node, str):
                return sub(node)
            if isinstance(node, list):
                return [walk(x) for x in node]
            if isinstance(node, dict):
                return {k: walk(v) for k, v in node.items()}
            return node

        return ResumeData.model_validate(walk(raw))

    def _remove_matching(self, data: ResumeData, target: str) -> int:
        removed = 0
        canonical = {"summary", "skills", "experience", "education", "projects",
                     "certifications", "languages", "awards"}
        if target in canonical:
            field = getattr(data, target, None)
            if isinstance(field, list) and field:
                removed = len(field)
                setattr(data, target, [])
            elif target == "summary" and data.summary:
                data.summary = ""
                removed = 1
            return removed

        for exp in list(data.experience):
            haystack = f"{exp.title} {exp.company} {' '.join(exp.bullets)}".lower()
            if target in haystack:
                data.experience.remove(exp)
                removed += 1
        for group in data.skills:
            before = len(group.skills)
            group.skills = [s for s in group.skills if target not in s.lower()]
            removed += before - len(group.skills)
        for proj in list(data.projects):
            if target in f"{proj.name} {proj.description}".lower():
                data.projects.remove(proj)
                removed += 1
        return removed

    def _polish_wording(self, data: ResumeData) -> int:
        count = 0
        for exp in data.experience:
            new_bullets = []
            for bullet in exp.bullets:
                original = bullet
                low = bullet.lower()
                for weak in WEAK_PHRASES:
                    if low.startswith(weak):
                        rest = bullet[len(weak):].lstrip(" :,-")
                        bullet = ("Led " + rest) if rest else bullet
                        break
                for weak, strong in ACTION_VERB_UPGRADES.items():
                    bullet = re.sub(rf"^(?i:{re.escape(weak)})\b", strong.capitalize(), bullet)
                if bullet != original:
                    count += 1
                new_bullets.append(bullet)
            exp.bullets = new_bullets
        return count

    # ------------------------------------------------------------------ run

    def run(
        self,
        resume: ResumeData,
        instructions: str,
        template: TemplateMeta | None = None,
    ) -> AgentResult:
        if not instructions.strip():
            return self.fail("No editing instructions provided")
        if self.llm.available:
            try:
                updated = self._edit_with_llm(resume, instructions, template)
                report = score_resume(updated)
                return self.ok(
                    "Edits applied with AI",
                    resume=updated.model_dump(mode="json"),
                    applied=[instructions],
                    scores=report.model_dump(),
                )
            except (LLMUnavailableError, Exception) as exc:  # noqa: BLE001
                self.logger.warning("LLM edit failed (%s); using rule-based editor", exc)
        updated, applied = self._edit_with_rules(resume, instructions)
        report = score_resume(updated)
        return self.ok(
            "Edits applied with rule-based editor",
            resume=updated.model_dump(mode="json"),
            applied=applied,
            scores=report.model_dump(),
        )
