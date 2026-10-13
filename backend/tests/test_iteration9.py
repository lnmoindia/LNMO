"""Iteration 9 targeted tests:
- lookup/sections dedupe + class_name filter (Section dropdown bug fix)
- subjects auto-generated code when blank
- regression: subject_offerings / sections / classes CRUD
"""
import os
import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE = base_url.rstrip("/") + "/api"

ADMIN = {"email": "admin@greenwood.edu", "password": "Green@2026!"}


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    r = s.post(f"{BASE}/auth/login", json=ADMIN)
    if r.status_code != 200:
        pytest.fail(f"login failed {r.status_code}: {r.text[:300]}")
    return s


@pytest.fixture(scope="module")
def created(client):
    ids = {"sections": [], "classes": [], "subjects": [], "subject_offerings": []}
    yield ids
    for res in ("subject_offerings", "sections", "classes", "subjects"):
        for i in ids[res]:
            client.delete(f"{BASE}/res/{res}/{i}")


# ---------- lookup/sections ----------
class TestSectionLookup:
    def test_setup_two_classes_with_section_A(self, client, created):
        units = client.get(f"{BASE}/lookup/academic_units").json()
        assert units, "no academic units available"
        uid = units[0]["value"]
        for cname in ("TEST_ClassX", "TEST_ClassY"):
            r = client.post(f"{BASE}/res/classes", json={"name": cname, "academic_unit_id": uid})
            assert r.status_code in (200, 201), r.text
            created["classes"].append(r.json()["id"])
            rs = client.post(f"{BASE}/res/sections", json={"name": "A", "class_name": cname, "capacity": 30})
            assert rs.status_code in (200, 201), rs.text
            created["sections"].append(rs.json()["id"])

    def test_lookup_sections_dedupes(self, client):
        r = client.get(f"{BASE}/lookup/sections")
        assert r.status_code == 200
        data = r.json()
        values = [d["value"] for d in data]
        assert len(values) == len(set(values)), f"duplicate section values: {values}"
        for d in data:
            assert d["label"] == d["value"], f"label should be plain name, got {d}"
        assert "A" in values

    def test_lookup_sections_class_filter(self, client):
        r = client.get(f"{BASE}/lookup/sections", params={"class_name": "TEST_ClassX"})
        assert r.status_code == 200
        assert r.json() == [{"value": "A", "label": "A"}]

    def test_lookup_sections_unknown_class_empty(self, client):
        r = client.get(f"{BASE}/lookup/sections", params={"class_name": "TEST_NoSuchClass"})
        assert r.status_code == 200
        assert r.json() == []


# ---------- subjects auto code ----------
class TestSubjectAutoCode:
    def test_multiword_initials(self, client, created):
        r = client.post(f"{BASE}/res/subjects", json={"name": "TEST Social Science Studies", "code": ""})
        assert r.status_code in (200, 201), r.text
        body = r.json()
        created["subjects"].append(body["id"])
        assert body["code"] == "TSSS", body
        g = client.get(f"{BASE}/res/subjects/{body['id']}")
        assert g.status_code == 200 and g.json()["code"] == "TSSS"
        assert "_id" not in g.json()

    def test_duplicate_gets_suffix(self, client, created):
        r = client.post(f"{BASE}/res/subjects", json={"name": "TEST Super Sample Set", "code": ""})
        assert r.status_code in (200, 201), r.text
        body = r.json()
        created["subjects"].append(body["id"])
        assert body["code"] == "TSSS2", body

    def test_single_word_first4(self, client, created):
        r = client.post(f"{BASE}/res/subjects", json={"name": "TESTgeography"})
        assert r.status_code in (200, 201), r.text
        body = r.json()
        created["subjects"].append(body["id"])
        assert body["code"] == "TEST", body

    def test_explicit_code_preserved(self, client, created):
        r = client.post(f"{BASE}/res/subjects", json={"name": "TEST Explicit", "code": "TEXPL"})
        assert r.status_code in (200, 201), r.text
        body = r.json()
        created["subjects"].append(body["id"])
        assert body["code"] == "TEXPL"


# ---------- regression ----------
class TestOfferingRegression:
    def test_create_offering_with_practical(self, client, created):
        subs = client.get(f"{BASE}/lookup/subjects").json()
        assert subs
        r = client.post(f"{BASE}/res/subject_offerings", json={
            "subject": subs[0]["value"], "class_name": "TEST_ClassX", "section": "A",
            "has_practical": True, "theory_max_marks": 70, "practical_max_marks": 30})
        assert r.status_code in (200, 201), r.text
        body = r.json()
        created["subject_offerings"].append(body["id"])
        assert body["max_marks"] == 100, body

    def test_offering_bad_class_rejected(self, client):
        r = client.post(f"{BASE}/res/subject_offerings", json={
            "subject": "Mathematics", "class_name": "TEST_Nope", "section": ""})
        assert r.status_code == 400, r.text
