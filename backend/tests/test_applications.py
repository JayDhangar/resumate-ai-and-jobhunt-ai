"""Application tracker CRUD and tailor endpoint (offline rule-based path)."""


def _make_resume(client):
    resume = client.post("/api/resumes", json={"title": "Tracker Test"}).json()
    data = resume["data"]
    data.update({
        "name": "Track Er", "email": "track@test.dev",
        "summary": "Engineer focused on Python systems.",
        "skills": [{"category": "", "skills": ["Python", "SQL"]}],
        "experience": [{"title": "Dev", "company": "TestCo", "start_date": "2020",
                        "end_date": "Present", "current": True, "location": "", "bullets": ["Built stuff"]}],
    })
    client.put(f"/api/resumes/{resume['id']}", json={"data": data})
    return resume["id"]


JOB = {"title": "Python Engineer", "company": "Acme", "location": "Pune, India",
       "description": "Python and SQL heavy role.", "url": "https://boards.greenhouse.io/acme/1"}


def test_application_lifecycle(client):
    rid = _make_resume(client)

    # save a job
    r = client.post("/api/jobs/applications", json={"job": JOB, "source": "linkedin", "resume_id": rid})
    assert r.status_code == 200 and r.json()["saved"] is True
    app_id = r.json()["id"]

    # duplicate save is rejected gracefully
    r = client.post("/api/jobs/applications", json={"job": JOB})
    assert r.json()["saved"] is False

    # list
    apps = client.get("/api/jobs/applications").json()
    assert len(apps) == 1
    assert apps[0]["job_title"] == "Python Engineer"
    assert apps[0]["status"] == "saved"
    assert apps[0]["resume_title"] == "Tracker Test"

    # update status + notes
    r = client.patch(f"/api/jobs/applications/{app_id}", json={"status": "interviewing", "notes": "call Friday"})
    assert r.status_code == 200
    assert r.json()["status"] == "interviewing"
    assert r.json()["notes"] == "call Friday"

    # applied sets applied_at
    r = client.patch(f"/api/jobs/applications/{app_id}", json={"status": "applied"})
    assert r.json()["applied_at"] is not None

    # delete
    assert client.delete(f"/api/jobs/applications/{app_id}").json()["deleted"] is True
    assert client.get("/api/jobs/applications").json() == []


def test_unknown_application_404(client):
    assert client.patch("/api/jobs/applications/nope", json={"status": "applied"}).status_code == 404


def test_tailor_saves_version(client):
    rid = _make_resume(client)
    r = client.post("/api/jobs/tailor", json={"resume_id": rid, "job": JOB})
    assert r.status_code == 200
    body = r.json()
    assert body["version"] is not None
    versions = client.get(f"/api/resumes/{rid}/versions").json()
    assert any("Tailored for Python Engineer" in v["label"] for v in versions)