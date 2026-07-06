"""End-to-end API flow through the FastAPI test client (offline)."""


def test_health(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["llm_available"] is False


def test_templates_seeded_and_filterable(client):
    templates = client.get("/api/templates").json()
    assert len(templates) >= 8
    ats = client.get("/api/templates", params={"style": "ats"}).json()
    assert ats and all(t["style"] == "ats" for t in ats)
    searched = client.get("/api/templates", params={"q": "minimal"}).json()
    assert any("minimal" in t["name"].lower() or "minimal" in t["tags"] for t in searched)


def test_full_resume_lifecycle(client):
    # create
    resume = client.post("/api/resumes", json={"title": "API Test"}).json()
    rid = resume["id"]

    # update
    resume["data"].update({
        "name": "Api Tester", "email": "api@test.dev",
        "summary": "Engineer with impact.",
        "skills": [{"category": "", "skills": ["Python", "SQL"]}],
        "experience": [{"title": "Dev", "company": "TestCo", "start_date": "2020",
                        "end_date": "Present", "current": True, "location": "",
                        "bullets": ["Did things"]}],
    })
    r = client.put(f"/api/resumes/{rid}", json={"data": resume["data"], "save_version": True})
    assert r.status_code == 200

    # edit (rule-based)
    r = client.post(f"/api/resumes/{rid}/edit", json={"instructions": "Replace SQL with PostgreSQL"})
    assert r.status_code == 200
    assert "PostgreSQL" in r.json()["resume"]["data"]["skills"][0]["skills"]

    # select template + generate
    templates = client.get("/api/templates").json()
    tid = templates[0]["id"]
    assert client.post(f"/api/resumes/{rid}/select-template", json={"template_id": tid}).status_code == 200
    r = client.post(f"/api/resumes/{rid}/generate", json={"formats": ["html", "pdf"]})
    assert r.status_code == 200
    assert set(r.json()["files"]) >= {"html", "pdf"}

    # preview + download
    assert client.get(f"/api/resumes/{rid}/preview").status_code == 200
    assert client.get(f"/api/resumes/{rid}/download/pdf").status_code == 200

    # scores (while the resume still has content)
    scores = client.get(f"/api/resumes/{rid}/scores").json()
    assert 0 < scores["ats_score"] <= 100

    # versions + restore (v1 is the blank creation snapshot)
    versions = client.get(f"/api/resumes/{rid}/versions").json()
    assert len(versions) >= 2
    assert client.post(f"/api/resumes/{rid}/versions/1/restore").status_code == 200
    restored = client.get(f"/api/resumes/{rid}").json()
    assert restored["data"]["name"] == ""

    # delete
    assert client.delete(f"/api/resumes/{rid}").json()["deleted"] is True
    assert client.get(f"/api/resumes/{rid}").status_code == 404


def test_upload_rejects_bad_extension(client):
    r = client.post("/api/resumes/upload", files={"file": ("evil.exe", b"MZ", "application/octet-stream")})
    assert r.status_code == 415


def test_unknown_resume_404(client):
    assert client.get("/api/resumes/does-not-exist").status_code == 404
