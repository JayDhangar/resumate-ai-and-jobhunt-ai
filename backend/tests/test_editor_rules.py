"""Rule-based (offline) resume editor behaviour."""
from agents.resume_editor_agent import ResumeEditorAgent


def test_replace_everywhere(sample_resume):
    agent = ResumeEditorAgent()
    result = agent.run(sample_resume, "Replace Python with Golang")
    assert result.ok
    skills = result.data["resume"]["skills"][0]["skills"]
    assert "Golang" in skills and "Python" not in skills


def test_remove_experience_item(sample_resume):
    agent = ResumeEditorAgent()
    result = agent.run(sample_resume, "Remove Brightpath")
    assert result.ok
    companies = [e["company"] for e in result.data["resume"]["experience"]]
    assert "Brightpath" not in companies and len(companies) == 1


def test_rename_section(sample_resume):
    agent = ResumeEditorAgent()
    result = agent.run(sample_resume, "Rename 'Projects' to 'Portfolio'")
    assert result.ok
    assert result.data["resume"]["section_titles"]["projects"] == "Portfolio"


def test_summary_change(sample_resume):
    agent = ResumeEditorAgent()
    result = agent.run(sample_resume, "Change my summary to: Seasoned platform engineer.")
    assert result.ok
    assert result.data["resume"]["summary"] == "Seasoned platform engineer."


def test_empty_instructions_fail(sample_resume):
    agent = ResumeEditorAgent()
    assert not agent.run(sample_resume, "   ").ok


def test_guard_restores_dropped_sections(sample_resume):
    agent = ResumeEditorAgent()
    broken = sample_resume.model_copy(deep=True)
    broken.experience = []
    broken.summary = ""
    fixed = agent._guard_against_loss(sample_resume, broken, "fix grammar")
    assert fixed.experience == sample_resume.experience
    assert fixed.summary == sample_resume.summary
    # but explicit removals are honoured (fresh copy — the guard mutates in place)
    broken2 = sample_resume.model_copy(deep=True)
    broken2.experience = []
    removed = agent._guard_against_loss(sample_resume, broken2, "remove experience")
    assert removed.experience == []
