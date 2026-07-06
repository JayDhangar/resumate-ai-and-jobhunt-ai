"""Schema round-trips and helpers."""
from models.schemas import ResumeData, ResumeRecord, SkillGroup, TemplateMeta


def test_resume_data_roundtrip(sample_resume):
    dumped = sample_resume.model_dump(mode="json")
    restored = ResumeData.model_validate(dumped)
    assert restored == sample_resume


def test_flat_skills():
    resume = ResumeData(skills=[
        SkillGroup(category="A", skills=["x", "y"]),
        SkillGroup(category="B", skills=["z"]),
    ])
    assert resume.flat_skills() == ["x", "y", "z"]


def test_resume_record_defaults():
    record = ResumeRecord()
    assert record.id and record.data is not None
    assert record.versions == [] and record.generated_files == {}


def test_template_meta_defaults():
    meta = TemplateMeta(name="Test")
    assert meta.layout.columns == 1
    assert meta.colors.background == "#ffffff"
    assert meta.source.value == "builtin"
