"""Iteration 11 backend tests: per-section leaders + portal achievements/leader_role.

Requires seed_iter11.py to have been run (iter11_ids.json present).
Run serially: pytest /app/backend/tests/test_iteration11.py -v -n 0
"""
import json
import os

import pytest
import requests
from dotenv import dotenv_values

fe = dotenv_values("/app/frontend/.env")
_base = os.environ.get("REACT_APP_BACKEND_URL") or fe.get("REACT_APP_BACKEND_URL")
if not _base:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
API = _base.rstrip("/") + "/api"
IDS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "iter11_ids.json")
ADMIN = {"email": "admin@greenwood.edu", "password": "Green@2026!"}


@pytest.fixture(scope="module")
def ids():
    if not os.path.exists(IDS_FILE):
        pytest.fail("iter11_ids.json missing — run seed_iter11.py first")
    with open(IDS_FILE) as f:
        return json.load(f)


@pytest.fixture(scope="module")
def admin():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=ADMIN, timeout=30)
    if r.status_code != 200:
        pytest.fail(f"Admin login failed {r.status_code}: {r.text[:300]}")
    return s


@pytest.fixture(scope="module")
def student(ids):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=ids["student_login"], timeout=30)
    if r.status_code != 200:
        pytest.fail(f"Student login failed {r.status_code}: {r.text[:300]}")
    body = r.json()
    assert (body.get("user") or body).get("role") == "student", body
    return s


# ---------- sections: per-section leader resolution ----------

class TestSectionLeaders:
    def test_section_b_leader_resolved(self, admin, ids):
        r = admin.get(f"{API}/res/sections/{ids['section_b_id']}")
        assert r.status_code == 200
        sec = r.json()
        assert "_id" not in sec
        assert sec["class_leader_id"] == ids["student_b_id"]
        assert sec["class_leader"] == "TEST_Bhavya Rao"
        assert sec.get("second_leader", "") == ""

    def test_set_second_leader_and_persist(self, admin, ids):
        r = admin.put(f"{API}/res/sections/{ids['section_b_id']}",
                      json={"class_leader_id": ids["student_b_id"], "second_leader_id": ids["student_b_id"]})
        assert r.status_code == 200, r.text
        assert r.json()["second_leader"] == "TEST_Bhavya Rao"
        got = admin.get(f"{API}/res/sections/{ids['section_b_id']}").json()
        assert got["second_leader_id"] == ids["student_b_id"]
        assert got["second_leader"] == "TEST_Bhavya Rao"

    def test_clear_second_leader_clears_name(self, admin, ids):
        r = admin.put(f"{API}/res/sections/{ids['section_b_id']}",
                      json={"class_leader_id": ids["student_b_id"], "second_leader_id": ""})
        assert r.status_code == 200
        assert r.json()["second_leader"] == ""
        got = admin.get(f"{API}/res/sections/{ids['section_b_id']}").json()
        assert got["second_leader"] == ""
        assert got["second_leader_id"] == ""

    def test_bogus_leader_id_rejected_and_not_persisted(self, admin, ids):
        before = admin.get(f"{API}/res/sections/{ids['section_b_id']}").json()
        r = admin.put(f"{API}/res/sections/{ids['section_b_id']}",
                      json={"class_leader_id": "does-not-exist", "second_leader_id": ""})
        assert r.status_code == 400, r.text
        assert "Selected student not found" in r.json()["detail"]
        after = admin.get(f"{API}/res/sections/{ids['section_b_id']}").json()
        assert after["class_leader_id"] == before["class_leader_id"]
        assert after["class_leader"] == before["class_leader"]

    def test_student_from_other_class_rejected(self, admin, ids):
        r = admin.put(f"{API}/res/sections/{ids['section_b_id']}",
                      json={"class_leader_id": ids["other_student_id"]})
        assert r.status_code == 400, r.text
        assert "Student is not in this class" in r.json()["detail"]
        after = admin.get(f"{API}/res/sections/{ids['section_b_id']}").json()
        assert after["class_leader_id"] == ids["student_b_id"]

    def test_section_a_leader_independent(self, admin, ids):
        sec_a = admin.get(f"{API}/res/sections/{ids['section_a_id']}").json()
        assert sec_a["class_leader_id"] == ids["section_a_original_leader"]
        assert sec_a["class_leader"] == "Aarav Shah"


# ---------- class detail aggregation ----------

class TestClassDetail:
    def test_detail_shape(self, admin, ids):
        r = admin.get(f"{API}/classes/{ids['class_id']}/detail")
        assert r.status_code == 200
        d = r.json()
        for k in ("class", "sections", "offerings", "students", "achievements"):
            assert k in d
        names = sorted(s["name"] for s in d["sections"])
        assert "A" in names and "B" in names
        secb = next(s for s in d["sections"] if s["name"] == "B")
        assert secb["class_leader"] == "TEST_Bhavya Rao"
        seca = next(s for s in d["sections"] if s["name"] == "A")
        assert seca["class_leader"] == "Aarav Shah"

    def test_students_carry_sections(self, admin, ids):
        d = admin.get(f"{API}/classes/{ids['class_id']}/detail").json()
        by_id = {s["id"]: s for s in d["students"]}
        assert by_id[ids["student_b_id"]]["section"] == "B"
        assert by_id[ids["section_a_original_leader"]]["section"] == "A"

    def test_achievement_scoped_to_section(self, admin, ids):
        d = admin.get(f"{API}/classes/{ids['class_id']}/detail").json()
        ach = next(a for a in d["achievements"] if a["id"] == ids["achievement_id"])
        assert ach["section"] == "B"
        assert ach["class_name"] == "Grade 6"
        assert ach["student_name"] == "TEST_Bhavya Rao"
        assert ach["title"] == "TEST_1st place Science Fair"
        assert ach["date"] == "2026-02-14"

    def test_class_teacher_is_section_level_now(self, admin, ids):
        d = admin.get(f"{API}/classes/{ids['class_id']}/detail").json()
        assert "class_teacher" not in d["class"] or not d["class"].get("class_teacher")
        sec_a = next(s for s in d["sections"] if s["name"] == "A")
        assert sec_a.get("class_teacher") == "Meera Iyer"


# ---------- achievements CRUD regression ----------

class TestAchievementsRegression:
    def test_add_and_delete_achievement(self, admin, ids):
        r = admin.post(f"{API}/res/achievements", json={
            "student_id": ids["student_b_id"], "title": "TEST_Quiz winner", "description": "x"})
        assert r.status_code == 200, r.text
        a = r.json()
        assert a["student_name"] == "TEST_Bhavya Rao"
        assert a["section"] == "B"
        assert a["date"]  # auto today
        d = admin.get(f"{API}/classes/{ids['class_id']}/detail").json()
        assert any(x["id"] == a["id"] for x in d["achievements"])
        assert admin.delete(f"{API}/res/achievements/{a['id']}").status_code == 200
        d2 = admin.get(f"{API}/classes/{ids['class_id']}/detail").json()
        assert not any(x["id"] == a["id"] for x in d2["achievements"])

    def test_achievement_requires_title(self, admin, ids):
        r = admin.post(f"{API}/res/achievements", json={"student_id": ids["student_b_id"], "title": "  "})
        assert r.status_code == 400

    def test_achievement_bogus_student(self, admin):
        r = admin.post(f"{API}/res/achievements", json={"student_id": "nope", "title": "TEST_x"})
        assert r.status_code == 400


# ---------- portal ----------

class TestPortal:
    def test_portal_me_achievements_and_class_leader(self, student, ids):
        r = student.get(f"{API}/portal/me")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["student"]["id"] == ids["student_b_id"]
        assert "password_hash" not in d["student"]
        titles = [a["title"] for a in d["achievements"]]
        assert "TEST_1st place Science Fair" in titles
        ach = next(a for a in d["achievements"] if a["id"] == ids["achievement_id"])
        assert ach["description"] == "District level model contest"
        assert ach["date"] == "2026-02-14"
        assert d["leader_role"] == "class_leader"

    def test_leader_role_second(self, admin, student, ids):
        admin.put(f"{API}/res/sections/{ids['section_b_id']}",
                  json={"class_leader_id": "", "second_leader_id": ids["student_b_id"]})
        d = student.get(f"{API}/portal/me").json()
        assert d["leader_role"] == "second_leader"

    def test_leader_role_none(self, admin, student, ids):
        admin.put(f"{API}/res/sections/{ids['section_b_id']}",
                  json={"class_leader_id": "", "second_leader_id": ""})
        d = student.get(f"{API}/portal/me").json()
        assert d["leader_role"] is None
        # restore class_leader for UI test
        admin.put(f"{API}/res/sections/{ids['section_b_id']}",
                  json={"class_leader_id": ids["student_b_id"], "second_leader_id": ""})
        assert student.get(f"{API}/portal/me").json()["leader_role"] == "class_leader"

    def test_portal_me_forbidden_for_admin(self, admin):
        r = admin.get(f"{API}/portal/me")
        assert r.status_code == 403
