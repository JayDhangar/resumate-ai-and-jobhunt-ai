"""Heuristic (offline) resume text structuring."""
from agents.resume_reader_agent import ResumeReaderAgent

SAMPLE_TEXT = """Jane Doe
jane.doe@example.com | +1 555-123-4567 | Austin, TX
https://linkedin.com/in/janedoe | https://github.com/janedoe

Summary
Senior engineer focused on distributed systems and developer tooling.

Skills
Languages: Python, Go, SQL
Cloud: AWS, Docker

Experience
Senior Engineer - CloudCo Jan 2021 - Present
• Built event pipeline handling 10M events/day
• Cut costs by 30%
Engineer - StartupX 2018 - 2020
• Shipped the mobile API

Education
B.S. Computer Science 2014 - 2018
State University
"""


def test_heuristic_structure_extracts_contact():
    resume = ResumeReaderAgent().heuristic_structure(SAMPLE_TEXT)
    assert resume.name == "Jane Doe"
    assert resume.email == "jane.doe@example.com"
    assert "555" in resume.phone
    assert "linkedin" in resume.links.linkedin
    assert "github" in resume.links.github


def test_heuristic_structure_sections():
    resume = ResumeReaderAgent().heuristic_structure(SAMPLE_TEXT)
    assert "distributed systems" in resume.summary
    assert resume.skills and resume.skills[0].category == "Languages"
    assert "Python" in resume.flat_skills()
    assert len(resume.experience) == 2
    assert resume.experience[0].bullets
    assert resume.experience[0].current
    assert resume.education and "Computer Science" in resume.education[0].degree
