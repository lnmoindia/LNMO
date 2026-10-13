"""Phase 3 backend tests: POST /api/students/enroll (create student + optional enrollment)."""
import os
import re
import uuid
from pathlib import Path

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE_URL = base_url.rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@greenwood.edu"
ADMIN_PASS = "Green@2026!"


@pytest.fixture(scope="module")
def admin():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=30)
    if r.status_code != 200:
        pytest.fail(f"admin login failed {r.status_code}: {r.text[:300]}")
    return s


@pytest.fixture(scope="module")
def created(admin):
    ids = []
    yield ids
    for sid in ids:
        admin.delete(f"{API}/res/students/{sid}", timeout=30)


# ---- helpers ----
def _get_student(admin, sid):
    r = admin.get(f"{API}/res/students", params={"limit": 500}, timeout=30)
    assert r.status_code == 200, r.text
    for it in r.json()["items"]:
        if it["id"] == sid:
            return it
    raise AssertionError(f"student {sid} not found in list")


def _has_raw_id(obj):
    if isinstance(obj, dict):
        return "_id" in obj or any(_has_raw_id(v) for v in obj.values())
    if isinstance(obj, list):
        return any(_has_raw_id(v) for v in obj)
    return False


def _first_class(admin):
    r = admin.get(f"{API}/res/classes", params={"limit": 50}, timeout=30)
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert items, "no classes seeded for Greenwood"
    return items[0]


# ---- module: students/enroll happy path ----
class TestCreateAndEnroll:
    def test_create_and_enroll(self, admin, created):
        cls = _first_class(admin)
        secs = admin.get(f"{API}/res/sections", params={"limit": 100}, timeout=30).json()["items"]
        section = next((s["name"] for s in secs if s.get("class_name") == cls["name"]), None)
        tag = uuid.uuid4().hex[:6]
        payload = {"first_name": "TEST_Enrolled", "last_name": tag, "admission_no": f"TEST-{tag}",
                   "guardian_name": "TEST Guardian", "enroll": True,
                   "academic_year": None, "class_name": cls["name"], "section": section}
        r = admin.post(f"{API}/students/enroll", json=payload, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "_id" not in d
        assert d["enrollment_status"] == "enrolled"
        assert d["class_name"] == cls["name"]
        assert d["section"] == section
        sid = d["id"]
        created.append(sid)

        # GET verifies persistence
        gd = _get_student(admin, sid)
        assert "_id" not in gd
        assert gd["enrollment_status"] == "enrolled"
        assert gd["class_name"] == cls["name"]
        assert gd["guardian_name"] == "TEST Guardian"

        # enrollment record created
        e = admin.get(f"{API}/res/enrollments", params={"limit": 200, "search": f"TEST_Enrolled {tag}"}, timeout=30)
        assert e.status_code == 200, e.text
        rows = [x for x in e.json()["items"] if x.get("student_id") == sid]
        assert rows, f"no enrollment record created for {sid}: {e.text[:300]}"
        assert rows[0]["class_name"] == cls["name"]
        assert "_id" not in rows[0]


# ---- module: students/enroll profile-only + validation ----
class TestProfileOnlyAndValidation:
    def test_profile_only(self, admin, created):
        tag = uuid.uuid4().hex[:6]
        r = admin.post(f"{API}/students/enroll", json={
            "first_name": "TEST_ProfileOnly", "last_name": tag, "enroll": False,
            "class_name": "Grade 6", "section": "A"}, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["enrollment_status"] == "not_enrolled"
        assert not d.get("class_name")
        assert not d.get("section")
        created.append(d["id"])
        g = _get_student(admin, d["id"])
        assert g["enrollment_status"] == "not_enrolled"
        assert not g.get("class_name")

    def test_enroll_without_class_400(self, admin):
        r = admin.post(f"{API}/students/enroll", json={"first_name": "TEST_NoClass", "enroll": True}, timeout=30)
        assert r.status_code == 400, r.text
        assert "class" in r.json()["detail"].lower()

    def test_enroll_nonexistent_class_400(self, admin):
        r = admin.post(f"{API}/students/enroll", json={
            "first_name": "TEST_BadClass", "enroll": True, "class_name": "NoSuchClass-XYZ"}, timeout=30)
        assert r.status_code == 400, r.text
        assert "exist" in r.json()["detail"].lower()

    def test_missing_first_name_400(self, admin):
        r = admin.post(f"{API}/students/enroll", json={"enroll": False}, timeout=30)
        assert r.status_code == 400, r.text

    def test_requires_auth(self):
        r = requests.post(f"{API}/students/enroll", json={"first_name": "X", "enroll": False}, timeout=30)
        assert r.status_code in (401, 403), r.status_code

    def test_teacher_forbidden(self):
        s = requests.Session()
        lr = s.post(f"{API}/auth/login", json={"email": "meera@greenwood.edu", "password": "Teach@2026!"}, timeout=30)
        assert lr.status_code == 200, lr.text
        r = s.post(f"{API}/students/enroll", json={"first_name": "TEST_T", "enroll": False}, timeout=30)
        assert r.status_code == 403, f"teacher should not create students: {r.status_code}"


# ---- module: enrollment flips existing student to enrolled ----
class TestEnrollExisting:
    def test_enroll_existing_student_flips_status(self, admin, created):
        tag = uuid.uuid4().hex[:6]
        r = admin.post(f"{API}/res/students", json={"first_name": "TEST_Existing", "last_name": tag}, timeout=30)
        assert r.status_code in (200, 201), r.text
        sid = r.json()["id"]
        created.append(sid)
        assert r.json()["enrollment_status"] == "not_enrolled"

        cls = _first_class(admin)
        er = admin.post(f"{API}/res/enrollments", json={
            "student_id": sid, "academic_year": "", "class_name": cls["name"], "section": ""}, timeout=30)
        assert er.status_code in (200, 201), er.text
        g = _get_student(admin, sid)
        assert g["enrollment_status"] == "enrolled"
        assert g["class_name"] == cls["name"]


# ---- module: seeded data sanity + regression list endpoints ----
class TestRegression:
    def test_seeded_student_enrolled(self, admin):
        r = admin.get(f"{API}/res/students", params={"search": "Aarav", "limit": 10}, timeout=30)
        assert r.status_code == 200, r.text
        items = r.json()["items"]
        assert items, "seeded student Aarav Shah missing"
        assert items[0]["enrollment_status"] == "enrolled"

    @pytest.mark.parametrize("path", [
        "/res/classes", "/res/sections", "/res/subjects", "/res/academic_units",
        "/res/teachers", "/users", "/res/enrollments", "/res/assessments",
        "/lookup/academic_years", "/lookup/classes", "/lookup/students",
    ])
    def test_list_endpoints(self, admin, path):
        r = admin.get(f"{API}{path}", timeout=30)
        assert r.status_code == 200, f"{path} -> {r.status_code} {r.text[:200]}"
        assert not _has_raw_id(r.json()), f"{path} leaks raw _id"
