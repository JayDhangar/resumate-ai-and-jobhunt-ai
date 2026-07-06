"""Resume↔job matching: TF-IDF fallback similarity and skill overlap."""
from agents.job_search_agent import JobSearchAgent
from services.embedding_service import tfidf_similarities


def test_tfidf_ranks_related_doc_higher():
    profile = "Machine learning engineer skilled in Python, TensorFlow and NLP pipelines"
    docs = [
        "We need a machine learning engineer with Python and TensorFlow experience for NLP work",
        "Hiring a plumber for residential pipe repair and maintenance",
    ]
    sims = tfidf_similarities(profile, docs)
    assert sims[0] > sims[1]


def test_matching_skills_word_boundaries():
    skills = ["Python", "C++", "Go", "SQL"]
    text = "Looking for Python and C++ developers. Golang welcome. MySQL a plus."
    found = JobSearchAgent._matching_skills(skills, text)
    assert "Python" in found and "C++" in found
    assert "Go" not in found      # 'Golang' must not match bare 'Go'
    assert "SQL" not in found     # 'MySQL' must not match bare 'SQL'


def test_location_filter():
    from models.schemas import JobPosting

    match = JobSearchAgent._location_matches
    assert match(JobPosting(title="x", location="Pune, India"), "india")
    assert match(JobPosting(title="x", location="Anywhere (Remote)"), "india")
    assert match(JobPosting(title="x", location="", remote=True), "india")
    assert not match(JobPosting(title="x", location="Brazil", remote=True), "india")
    assert not match(JobPosting(title="x", location="Berlin, Germany"), "india")
    assert match(JobPosting(title="x", location="Bengaluru, India"), "Bengaluru, India")


def test_experience_parsing_and_buckets():
    from agents.job_search_agent import matches_experience, required_experience
    from models.schemas import JobPosting

    assert required_experience(JobPosting(title="x", description="3-5 years of experience")) == (3, 5)
    assert required_experience(JobPosting(title="x", description="5+ years in Python")) == (5, 99)
    assert required_experience(JobPosting(title="x", description="at least 2 years required")) == (2, 99)
    assert required_experience(JobPosting(title="x", description="Freshers welcome")) == (0, 1)
    assert required_experience(JobPosting(title="x", description="no mention here")) is None

    senior = JobPosting(title="Senior", description="7+ years experience")
    fresher = JobPosting(title="Junior", description="freshers welcome")
    unknown = JobPosting(title="Any", description="great team")
    assert matches_experience(senior, "0-1") is False
    assert matches_experience(fresher, "0-1") is True
    assert matches_experience(unknown, "0-1") is True   # unknown stays visible
    assert matches_experience(senior, "5+") is True
    assert matches_experience(fresher, "5+") is False
    assert matches_experience(senior, "") is True


def test_multi_query_merges_and_dedupes(monkeypatch):
    from models.schemas import JobPosting

    def fake_search(self, q, loc="", remote=False, source="", limit=60):
        from models.schemas import JobSearchResponse
        jobs = {
            "ai engineer": [JobPosting(title="AI Engineer", company="Acme", description="ai engineer"),
                            JobPosting(title="Shared Role Engineer", company="Both", description="ai engineer")],
            "data scientist": [JobPosting(title="Data Scientist", company="Beta", description="data scientist"),
                               JobPosting(title="Shared Role Engineer", company="Both", description="data scientist")],
        }[q]
        return JobSearchResponse(query=q, total=len(jobs), jobs=jobs, sources_used=["fake"], sources_available=["fake"])

    monkeypatch.setattr(JobSearchAgent, "search", fake_search)
    agent = JobSearchAgent()
    result = agent.search_multi(["ai engineer", "data scientist"])
    titles = [j.title for j in result.jobs]
    assert "AI Engineer" in titles and "Data Scientist" in titles
    assert titles.count("Shared Role Engineer") == 1  # deduped across queries
    assert result.query == "ai engineer | data scientist"


def test_profile_text_includes_key_sections(sample_resume):
    agent = JobSearchAgent()
    profile = agent._profile_text(sample_resume)
    assert "Senior Software Engineer" in profile
    assert "Python" in profile
    assert "Nimbus Labs" in profile
