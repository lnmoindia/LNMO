"""Iteration 10 backend tests: offered_subjects lookup, class detail, leadership, achievements, cascades."""
import os
import re
from pathlib import Path

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE = base_url.rstrip("/") + "/api"

CLASS_ID = "db61baf7-67fb-4c66-b04c-f8f11196b9ac"  # Grade 6
STUDENT_ID = "9fa05e4b-3ec9-4e53-8fb2-8a69b517a4dc"  # Aarav Shah
TEACHER_USER_ID = "6d90ce95-7c16-4401-a98d-d4c0e2d47914"  # Meera Iyer


def _creds():
    content = Path("/app/memory/test_credentials.md").read_text()
    m = re.search(r"admin@greenwood\.edu\s*/\s*(\S+)", content)
    return {"email": "admin@greenwood.edu", "password": m.group(1) if m else "Green@2026!"}


@pytest.fixture(scope="session")
def client():
    s = requests.Session()
    c = _creds()
    r = s.post(f"{BASE}/auth/login", json=c, timeout=30)
    if r.status_code != 200:
        pytest.fail(f"login failed {r.status_code}: {r.text[:300]}")
    return s


@pytest.fixture(scope="session")
def created(client):
    bag = {"offerings": [], "achievements": [], "students": [], "classes": []}
    yield bag
    for oid in bag["offerings"]:
        client.delete(f"{BASE}/res/subject_offerings/{oid}", timeout=30)
    for aid in bag["achievements"]:
        client.delete(f"{BASE}/res/achievements/{aid}", timeout=30)
    for sid in bag["students"]:
        client.delete(f"{BASE}/res/students/{sid}", timeout=30)
    for cid in bag["classes"]:
        client.delete(f"{BASE}/res/classes/{cid}", timeout=30)


# ---------------- lookups ----------------
class TestLookups:
    def test_teachers_by_id(self, client):
        r = client.get(f"{BASE}/lookup/teachers_by_id", timeout=30)
        assert r.status_code == 200
        rows = r.json()
        assert isinstance(rows, list) and len(rows) > 0
        ids = [x["value"] for x in rows]
        assert TEACHER_USER_ID in ids
        lbl = next(x["label"] for x in rows if x["value"] == TEACHER_USER_ID)
        assert "Meera" in lbl and "@" in lbl

    def test_offered_subjects_scoped(self, client, created):
        # create an offering for Grade 6 / Mathematics
        payload = {"class_name": "Grade 6", "section": "", "subject": "Mathematics", "max_marks": 100}
        r = client.post(f"{BASE}/res/subject_offerings", json=payload, timeout=30)
        assert r.status_code in (200, 201), r.text
        off = r.json()
        created["offerings"].append(off["id"])

        r = client.get(f"{BASE}/lookup/offered_subjects", params={"class_name": "Grade 6"}, timeout=30)
        assert r.status_code == 200
        assert [x["value"] for x in r.json()] == ["Mathematics"]

        # unknown class => empty
        r = client.get(f"{BASE}/lookup/offered_subjects", params={"class_name": "TEST_NoSuchClass"}, timeout=30)
        assert r.status_code == 200
        assert r.json() == []

        # unscoped includes Mathematics
        r = client.get(f"{BASE}/lookup/offered_subjects", timeout=30)
        assert "Mathematics" in [x["value"] for x in r.json()]

    def test_offered_subjects_distinct_across_sections(self, client, created):
        p = {"class_name": "Grade 6", "section": "A", "subject": "Mathematics", "max_marks": 100}
        r = client.post(f"{BASE}/res/subject_offerings", json=p, timeout=30)
        assert r.status_code in (200, 201), r.text
        created["offerings"].append(r.json()["id"])
        r = client.get(f"{BASE}/lookup/offered_subjects", params={"class_name": "Grade 6"}, timeout=30)
        vals = [x["value"] for x in r.json()]
        assert vals.count("Mathematics") == 1  # distinct


# ---------------- class detail ----------------
class TestClassDetail:
    def test_detail_shape(self, client):
        r = client.get(f"{BASE}/classes/{CLASS_ID}/detail", timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ("class", "unit", "sections", "offerings", "students", "achievements"):
            assert k in d
        assert d["class"]["name"] == "Grade 6"
        assert "_id" not in d["class"]
        assert all("_id" not in s for s in d["sections"])
        assert all("_id" not in s for s in d["students"])
        assert any(s["id"] == STUDENT_ID for s in d["students"])

    def test_detail_404(self, client):
        r = client.get(f"{BASE}/classes/nope-not-real/detail", timeout=30)
        assert r.status_code == 404

    def test_detail_requires_auth(self):
        r = requests.get(f"{BASE}/classes/{CLASS_ID}/detail", timeout=30)
        assert r.status_code in (401, 403)


# ---------------- leadership ----------------
SECTION_A_ID = "c3e28765-c942-4a93-9ea5-5ab880292061"  # Grade 6 / Section A


class TestLeadership:
    """Leadership is per-section now: teacher + leader + second leader live on the section record."""

    def test_set_and_clear_leadership(self, client):
        r = client.put(f"{BASE}/res/sections/{SECTION_A_ID}", json={
            "class_teacher_id": TEACHER_USER_ID,
            "class_leader_id": STUDENT_ID,
            "second_leader_id": STUDENT_ID,
        }, timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["class_teacher"] == "Meera Iyer"
        assert body["class_leader"] == "Aarav Shah"
        assert body["second_leader"] == "Aarav Shah"

        secs = client.get(f"{BASE}/classes/{CLASS_ID}/detail", timeout=30).json()["sections"]
        sec = next(s for s in secs if s["id"] == SECTION_A_ID)
        assert sec["class_teacher"] == "Meera Iyer"
        assert sec["class_leader_id"] == STUDENT_ID
        assert sec["second_leader"] == "Aarav Shah"

        # clear second leader with empty string
        r = client.put(f"{BASE}/res/sections/{SECTION_A_ID}", json={"second_leader_id": ""}, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["second_leader"] == ""
        secs = client.get(f"{BASE}/classes/{CLASS_ID}/detail", timeout=30).json()["sections"]
        sec = next(s for s in secs if s["id"] == SECTION_A_ID)
        assert sec["second_leader"] == ""
        assert sec["class_teacher"] == "Meera Iyer"
        assert sec["class_leader"] == "Aarav Shah"

    def _restore(self, client):
        client.put(f"{BASE}/res/sections/{SECTION_A_ID}", json={
            "class_teacher_id": TEACHER_USER_ID, "class_leader_id": STUDENT_ID, "second_leader_id": ""}, timeout=30)

    def test_bad_teacher_id_rejected(self, client):
        r = client.put(f"{BASE}/res/sections/{SECTION_A_ID}", json={"class_teacher_id": "bogus-id"}, timeout=30)
        assert r.status_code == 400
        assert "teacher not found" in r.json()["detail"].lower()
        stored = client.get(f"{BASE}/res/sections/{SECTION_A_ID}", timeout=30).json()
        self._restore(client)
        assert stored.get("class_teacher_id") == TEACHER_USER_ID, \
            f"invalid class_teacher_id persisted despite 400: {stored.get('class_teacher_id')}"

    def test_bad_student_id_rejected(self, client):
        r = client.put(f"{BASE}/res/sections/{SECTION_A_ID}", json={"class_leader_id": "bogus-id"}, timeout=30)
        assert r.status_code == 400
        assert "student not found" in r.json()["detail"].lower()
        stored = client.get(f"{BASE}/res/sections/{SECTION_A_ID}", timeout=30).json()
        self._restore(client)
        assert stored.get("class_leader_id") == STUDENT_ID, \
            f"invalid class_leader_id persisted despite 400: {stored.get('class_leader_id')}"


# ---------------- achievements ----------------
class TestAchievements:
    def test_create_enrich_list_delete(self, client, created):
        r = client.post(f"{BASE}/res/achievements", json={
            "student_id": STUDENT_ID, "title": "  TEST_Science Fair 1st  ", "description": "TEST desc"}, timeout=30)
        assert r.status_code in (200, 201), r.text
        a = r.json()
        aid = a["id"]
        created["achievements"].append(aid)
        assert a["student_name"] == "Aarav Shah"
        assert a["title"] == "TEST_Science Fair 1st"  # trimmed
        assert a["class_name"] == "Grade 6"
        assert a["date"] and len(a["date"]) == 10  # defaults to today
        assert "_id" not in a

        # appears in class detail
        d = client.get(f"{BASE}/classes/{CLASS_ID}/detail", timeout=30).json()
        assert any(x["id"] == aid for x in d["achievements"])

        # appears in list endpoint
        lr = client.get(f"{BASE}/res/achievements", timeout=30)
        assert lr.status_code == 200
        items = lr.json().get("items", lr.json())
        assert any(x["id"] == aid for x in items)

        # delete
        dr = client.delete(f"{BASE}/res/achievements/{aid}", timeout=30)
        assert dr.status_code in (200, 204)
        d = client.get(f"{BASE}/classes/{CLASS_ID}/detail", timeout=30).json()
        assert not any(x["id"] == aid for x in d["achievements"])
        created["achievements"].remove(aid)

    def test_validation(self, client):
        r = client.post(f"{BASE}/res/achievements", json={"student_id": STUDENT_ID, "title": "   "}, timeout=30)
        assert r.status_code == 400
        r = client.post(f"{BASE}/res/achievements", json={"title": "TEST_x"}, timeout=30)
        assert r.status_code == 400
        r = client.post(f"{BASE}/res/achievements", json={"student_id": "nope", "title": "TEST_x"}, timeout=30)
        assert r.status_code == 400
        assert "student not found" in r.json()["detail"].lower()

    def test_explicit_date_preserved(self, client, created):
        r = client.post(f"{BASE}/res/achievements", json={
            "student_id": STUDENT_ID, "title": "TEST_Quiz", "date": "2026-03-05"}, timeout=30)
        assert r.status_code in (200, 201), r.text
        a = r.json()
        created["achievements"].append(a["id"])
        assert a["date"] == "2026-03-05"


# ---------------- cascade ----------------
class TestCascade:
    def test_student_delete_cascades_achievements(self, client, created):
        sr = client.post(f"{BASE}/res/students", json={
            "first_name": "TEST_Cascade", "last_name": "Kid", "class_name": "Grade 6",
            "section": "A", "admission_no": "TEST_C1"}, timeout=30)
        assert sr.status_code in (200, 201), sr.text
        sid = sr.json()["id"]
        ar = client.post(f"{BASE}/res/achievements", json={"student_id": sid, "title": "TEST_Cascade Award"}, timeout=30)
        assert ar.status_code in (200, 201), ar.text
        aid = ar.json()["id"]

        dr = client.delete(f"{BASE}/res/students/{sid}", timeout=30)
        assert dr.status_code in (200, 204)

        items = client.get(f"{BASE}/res/achievements", params={"search": "TEST_Cascade Award"}, timeout=30).json()
        items = items.get("items", items)
        assert not any(x["id"] == aid for x in items), "achievement not cascaded on student delete"
