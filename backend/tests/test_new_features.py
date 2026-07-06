"""JD coverage, public share links, page/photo layout keywords, research fallback."""
from agents.resume_generator_agent import ResumeGeneratorAgent
from models.schemas import JobPosting, TemplateMeta
from services.scoring_service import jd_coverage


def test_jd_coverage_counts_keywords(sample_resume):
    jd = ("We need strong Python and TensorFlow experience. Python is essential. "
          "Kubernetes and Docker required. Kubernetes clusters at scale. "
          "Blockchain and Solidity are required. Blockchain experience preferred.")
    coverage = jd_coverage(sample_resume, jd)
    assert coverage["total"] > 0
    assert "python" in coverage["covered"]
    assert "kubernetes" in coverage["covered"]
    assert "blockchain" in coverage["missing"]
    assert 0 < coverage["coverage_pct"] < 100


def test_optimize_returns_coverage(client):
    resume = client.post("/api/resumes", json={"title": "Cov"}).json()
    data = resume["data"]
    data["skills"] = [{"category": "", "skills": ["Python", "FastAPI"]}]
    client.put(f"/api/resumes/{resume['id']}", json={"data": data})
    body = client.post(f"/api/resumes/{resume['id']}/optimize",
                       json={"job_description": "Python developer with FastAPI and GraphQL. "
                                                 "GraphQL and Python daily. FastAPI services."}).json()
    assert "jd_coverage" in body
    assert "python" in body["jd_coverage"]["covered"]


def test_publish_and_public_page(client):
    resume = client.post("/api/resumes", json={"title": "Pub Test"}).json()
    data = resume["data"]
    data["name"] = "Pub Lisher"
    data["summary"] = "Test summary for the public page."
    client.put(f"/api/resumes/{resume['id']}", json={"data": data})

    pub = client.post(f"/api/resumes/{resume['id']}/publish").json()
    assert pub["published"] is True
    assert pub["slug"] == "pub-lisher"

    page = client.get(f"/r/{pub['slug']}")
    assert page.status_code == 200
    assert "Pub Lisher" in page.text
    assert "ResuMate AI" in page.text  # footer credit

    # publishing again keeps the same slug
    again = client.post(f"/api/resumes/{resume['id']}/publish").json()
    assert again["slug"] == pub["slug"]

    client.post(f"/api/resumes/{resume['id']}/unpublish")
    assert client.get(f"/r/{pub['slug']}").status_code == 404


def test_page_and_photo_keywords():
    generator = ResumeGeneratorAgent()
    template = TemplateMeta(name="T", html_template="master.html.j2")
    one = generator.parse_adjustments(template, "one page layout")
    assert one.layout.page_mode == "one"
    two = generator.parse_adjustments(template, "two page layout")
    assert two.layout.page_mode == "two"
    show = generator.parse_adjustments(template, "show my photo")
    assert show.layout.show_photo is True
    hide = generator.parse_adjustments(show, "hide the photo")
    assert hide.layout.show_photo is False
    # "two columns" must NOT trigger two-page mode
    cols = generator.parse_adjustments(template, "use two columns")
    assert cols.layout.page_mode == "auto"
    assert cols.layout.columns == 2


def test_photo_renders_in_html(sample_resume):
    generator = ResumeGeneratorAgent()
    template = TemplateMeta(name="T", html_template="master.html.j2")
    template.layout.show_photo = True
    resume = sample_resume.model_copy(deep=True)
    resume.photo = "data:image/jpeg;base64,dGVzdA=="
    html = generator.render_html(resume, template)
    assert "data:image/jpeg;base64" in html
    # without photo data, no broken img tag
    resume.photo = ""
    html = generator.render_html(resume, template)
    assert 'class="photo"' not in html


def test_company_research_heuristic_fallback():
    from services.apply_service import research_company

    job = JobPosting(title="Engineer", company="Acme",
                     description="Pay a registration fee to apply via WhatsApp +911234",
                     url="http://sketchy.example")
    result = research_company(job)  # no LLM in tests
    assert result["source"] == "heuristic"
    assert any("fee" in f for f in result["red_flags"])
    assert result["trust_score"] < 60
