"""Sample resume used for template gallery previews and tests."""
from __future__ import annotations

from models.schemas import (
    ContactLinks,
    EducationItem,
    ExperienceItem,
    ProjectItem,
    ResumeData,
    SkillGroup,
)

SAMPLE_RESUME = ResumeData(
    name="Alex Morgan",
    headline="Senior Software Engineer",
    email="alex.morgan@example.com",
    phone="+1 (555) 010-2030",
    location="Austin, TX",
    summary=(
        "Senior software engineer with 8 years of experience building scalable web "
        "platforms. Led teams of up to 6 engineers and cut infrastructure costs by 35%."
    ),
    links=ContactLinks(linkedin="linkedin.com/in/alexmorgan", github="github.com/alexmorgan"),
    skills=[
        SkillGroup(category="Languages", skills=["Python", "TypeScript", "Go"]),
        SkillGroup(category="Cloud", skills=["AWS", "Docker", "Kubernetes", "Terraform"]),
    ],
    experience=[
        ExperienceItem(
            title="Senior Software Engineer",
            company="Nimbus Labs",
            location="Austin, TX",
            start_date="Mar 2021",
            end_date="Present",
            current=True,
            bullets=[
                "Designed a distributed job platform processing 40M tasks/day",
                "Reduced p99 API latency by 62% through query and cache optimization",
                "Mentored 4 engineers; led migration to Kubernetes",
            ],
        ),
        ExperienceItem(
            title="Software Engineer",
            company="Brightpath",
            location="Remote",
            start_date="Jun 2017",
            end_date="Feb 2021",
            bullets=[
                "Built customer analytics dashboard used by 300+ enterprise clients",
                "Introduced CI/CD pipeline cutting release time from days to hours",
            ],
        ),
    ],
    education=[
        EducationItem(
            degree="B.S. Computer Science",
            institution="University of Texas at Austin",
            start_date="2013",
            end_date="2017",
            gpa="3.8",
        )
    ],
    projects=[
        ProjectItem(
            name="OpenMetrics",
            description="Open-source metrics aggregation library (2.1k GitHub stars)",
            technologies=["Go", "Prometheus"],
        )
    ],
)
