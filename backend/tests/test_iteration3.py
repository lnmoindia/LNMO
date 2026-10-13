"""Iteration 3: Institution Setup Wizard backend — academic config, academic units,
subject offerings, setup-status, enforcement gates, lookups."""
import os
import uuid

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE_URL = base_url.rstrip("/")
API = f"{BASE_URL}/api"

PLATFORM = {"email": "lnmopvt@gmail.com", "password": "Lnmo@2026!"}
GREENWOOD = {"email": "admin@greenwood.edu", "password": "Green@2026!"}
TEACHER = {"email": "meera@greenwood.edu", "password": "Teach@2026!"}


def client(creds):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=creds, timeout=30)
    if r.status_code != 200:
        pytest.fail(f"login failed for {creds['email']}: {r.status_code} {r.text[:300]}")
    return s


@pytest.fixture(scope="session")
def platform_client():
    return client(PLATFORM)


@pytest.fixture(scope="session")
def green_client():
    return client(GREENWOOD)


@pytest.fixture(scope="class")
def fresh_institution(platform_client):
    """Create a brand-new institution + its admin; yields (session, inst_id, admin_email).

    Class-scoped so each test class gets a clean blank-slate tenant (pytest-xdist
    loadscope pins a class to one worker).
    """
    suffix = uuid.uuid4().hex[:8]
    admin_email = f"TEST_admin_{suffix}@qa.test".lower()
    payload = {
        "name": f"TEST_Fresh School {suffix}",
        "code": f"TSF{suffix[:4].upper()}",
        "admin_name": "TEST Fresh Admin",
        "admin_email": admin_email,
        "admin_password": "Fresh@2026!",
    }
    r = platform_client.post(f"{API}/res/institutions", json=payload, timeout=30)
    assert r.status_code == 200, r.text
    inst = r.json()
    assert "_id" not in inst
    sess = client({"email": admin_email, "password": "Fresh@2026!"})
    yield sess, inst["id"], admin_email
    d = platform_client.delete(f"{API}/res/institutions/{inst['id']}", timeout=30)
    assert d.status_code in (200, 204, 404)


# ---------------- auth / playbook basics ----------------

class TestAuthBasics:
    def test_login_sets_httponly_cookies(self):
        s = requests.Session()
        r = s.post(f"{API}/auth/login", json=GREENWOOD, timeout=30)
        assert r.status_code == 200
        raw = r.headers.get("set-cookie", "")
        assert "access_token" in raw and "HttpOnly" in raw
        body = r.json()
        assert body["email"] == GREENWOOD["email"]
        assert "password_hash" not in body

    def test_me_requires_auth(self):
        r = requests.get(f"{API}/auth/me", timeout=30)
        assert r.status_code == 401

    def test_teacher_login_and_role(self):
        s = client(TEACHER)
        me = s.get(f"{API}/auth/me", timeout=30)
        assert me.status_code == 200
        assert me.json()["role"] == "teacher"


# ---------------- setup-status ----------------

class TestSetupStatus:
    def test_greenwood_setup_status_shape(self, green_client):
        r = green_client.get(f"{API}/institution/setup-status", timeout=30)
        assert r.status_code == 200
        d = r.json()
        for k in ("steps", "setup_complete", "operationally_ready", "migrated_general_unit", "counts"):
            assert k in d
        for k in ("profile", "academic_config", "academic_year", "academic_units",
                  "classes", "sections", "subjects", "teachers", "teacher_assignments"):
            assert k in d["steps"] and isinstance(d["steps"][k], bool)
        assert d["migrated_general_unit"] is True
        assert d["counts"]["academic_units"] >= 1

    def test_fresh_institution_setup_incomplete(self, fresh_institution):
        sess, _, _ = fresh_institution
        d = sess.get(f"{API}/institution/setup-status", timeout=30).json()
        assert d["setup_complete"] is False
        assert d["operationally_ready"] is False
        assert d["migrated_general_unit"] is False
        assert d["counts"]["classes"] == 0

    def test_setup_status_forbidden_for_teacher(self):
        s = client(TEACHER)
        r = s.get(f"{API}/institution/setup-status", timeout=30)
        assert r.status_code == 403


# ---------------- academic config + presets ----------------

class TestAcademicConfig:
    def test_presets_created_then_idempotent(self, fresh_institution):
        sess, _, _ = fresh_institution
        body = {"institution_type": "school", "school_model": "k12", "apply_presets": True}
        r = sess.put(f"{API}/institution/academic-config", json=body, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["units_created"] == 4
        assert d["config"]["school_model"] == "k12"
        assert "_id" not in d["config"]

        units = sess.get(f"{API}/res/academic_units", params={"limit": 50}, timeout=30).json()
        codes = {u["code"] for u in units["items"]}
        assert {"LP", "UP", "HS", "HSS"} <= codes

        r2 = sess.put(f"{API}/institution/academic-config", json=body, timeout=30)
        assert r2.status_code == 200
        assert r2.json()["units_created"] == 0

        g = sess.get(f"{API}/institution/academic-config", timeout=30)
        assert g.status_code == 200
        assert g.json()["institution_type"] == "school"
        assert "_id" not in g.json()

    def test_config_marks_step_done(self, fresh_institution):
        sess, _, _ = fresh_institution
        d = sess.get(f"{API}/institution/setup-status", timeout=30).json()
        assert d["steps"]["academic_config"] is True
        assert d["steps"]["academic_units"] is True

    def test_config_requires_institution_admin(self, platform_client):
        r = platform_client.get(f"{API}/institution/academic-config", timeout=30)
        assert r.status_code == 403


# ---------------- academic_units CRUD + lookup ----------------

def apply_presets(sess):
    r = sess.put(f"{API}/institution/academic-config",
                 json={"institution_type": "school", "school_model": "k12", "apply_presets": True}, timeout=30)
    assert r.status_code == 200, r.text


class TestAcademicUnits:
    @pytest.fixture(autouse=True, scope="class")
    def _presets(self, fresh_institution):
        apply_presets(fresh_institution[0])

    def test_crud_and_coercion(self, fresh_institution):
        sess, _, _ = fresh_institution
        r = sess.post(f"{API}/res/academic_units", json={
            "name": "TEST_Pre Primary", "code": "PP", "attendance_model": "daily",
            "subject_model": "fixed", "assessment_model": "grades", "grading_model": "letter",
            "timetable_required": "true", "has_lab": False}, timeout=30)
        assert r.status_code == 200, r.text
        u = r.json()
        assert u["timetable_required"] is True
        assert u["has_lab"] is False
        assert isinstance(u["sort_order"], int)
        assert "_id" not in u

        lst = sess.get(f"{API}/res/academic_units", params={"search": "TEST_Pre"}, timeout=30).json()
        assert any(i["id"] == u["id"] for i in lst["items"])

        upd = sess.put(f"{API}/res/academic_units/{u['id']}", json={"name": "TEST_Pre Primary Renamed"}, timeout=30)
        assert upd.status_code == 200
        assert upd.json()["name"] == "TEST_Pre Primary Renamed"

        dele = sess.delete(f"{API}/res/academic_units/{u['id']}", timeout=30)
        assert dele.status_code == 200
        assert sess.delete(f"{API}/res/academic_units/{u['id']}", timeout=30).status_code == 404

    def test_unit_requires_name(self, fresh_institution):
        sess, _, _ = fresh_institution
        r = sess.post(f"{API}/res/academic_units", json={"code": "NX"}, timeout=30)
        assert r.status_code == 400

    def test_lookup_academic_units(self, fresh_institution):
        sess, _, _ = fresh_institution
        r = sess.get(f"{API}/lookup/academic_units", timeout=30)
        assert r.status_code == 200
        rows = r.json()
        assert len(rows) >= 4
        assert set(rows[0].keys()) == {"value", "label"}

    def test_units_tenant_isolated(self, fresh_institution, green_client):
        sess, _, _ = fresh_institution
        mine = {u["id"] for u in sess.get(f"{API}/res/academic_units", params={"limit": 50}, timeout=30).json()["items"]}
        theirs = {u["id"] for u in green_client.get(f"{API}/res/academic_units", params={"limit": 50}, timeout=30).json()["items"]}
        assert mine and theirs
        assert mine.isdisjoint(theirs)


# ---------------- gates: enrollments / teacher_assignments before classes ----------------

class TestEnforcementGatesNoClasses:
    def test_enrollment_blocked_without_classes(self, fresh_institution):
        sess, _, _ = fresh_institution
        st = sess.post(f"{API}/res/students", json={"first_name": "TEST", "last_name": "Gate",
                                                    "admission_no": f"T{uuid.uuid4().hex[:5]}"}, timeout=30)
        assert st.status_code == 200, st.text
        sid = st.json()["id"]
        r = sess.post(f"{API}/res/enrollments", json={"student_id": sid, "academic_year": "2026-27"}, timeout=30)
        assert r.status_code == 400, r.text
        assert "class" in r.json()["detail"].lower()
        sess.delete(f"{API}/res/students/{sid}", timeout=30)

    def test_teacher_assignment_blocked_without_classes(self, fresh_institution):
        sess, _, _ = fresh_institution
        r = sess.post(f"{API}/res/teacher_assignments",
                      json={"teacher_email": "nobody@qa.test", "class_name": "Grade 1"}, timeout=30)
        assert r.status_code == 400
        assert "class" in r.json()["detail"].lower()


# ---------------- classes with academic unit, subject offerings ----------------

class TestClassesAndOfferings:
    @pytest.fixture(scope="class")
    def seeded(self, fresh_institution):
        sess, _, _ = fresh_institution
        apply_presets(sess)
        unit_id = sess.get(f"{API}/lookup/academic_units", timeout=30).json()[0]["value"]
        cls = sess.post(f"{API}/res/classes", json={"name": "TEST_Grade 1", "academic_unit_id": unit_id,
                                                    "grade_level": "1"}, timeout=30)
        assert cls.status_code == 200, cls.text
        subj = sess.post(f"{API}/res/subjects", json={"name": "TEST_Maths", "code": "TM"}, timeout=30)
        assert subj.status_code == 200
        yield sess, cls.json(), subj.json()
        sess.delete(f"{API}/res/classes/{cls.json()['id']}", timeout=30)
        sess.delete(f"{API}/res/subjects/{subj.json()['id']}", timeout=30)

    def test_class_stores_academic_unit_name(self, seeded):
        sess, cls, _ = seeded
        assert cls.get("academic_unit_name")
        got = sess.get(f"{API}/res/classes", params={"search": "TEST_Grade 1"}, timeout=30).json()["items"]
        assert got and got[0]["academic_unit_name"] == cls["academic_unit_name"]

    def test_offering_crud_and_validation(self, seeded):
        sess, cls, subj = seeded
        r = sess.post(f"{API}/res/subject_offerings",
                      json={"subject": subj["name"], "class_name": cls["name"], "section": "A"}, timeout=30)
        assert r.status_code == 200, r.text
        off = r.json()
        assert off["subject"] == subj["name"]
        assert "_id" not in off

        dup = sess.post(f"{API}/res/subject_offerings",
                        json={"subject": subj["name"], "class_name": cls["name"], "section": "A"}, timeout=30)
        assert dup.status_code == 400
        assert "already offered" in dup.json()["detail"].lower()

        bad = sess.post(f"{API}/res/subject_offerings",
                        json={"subject": subj["name"], "class_name": "TEST_Nope"}, timeout=30)
        assert bad.status_code == 400
        assert "does not exist" in bad.json()["detail"].lower()

        missing = sess.post(f"{API}/res/subject_offerings", json={"subject": subj["name"]}, timeout=30)
        assert missing.status_code == 400

        assert sess.delete(f"{API}/res/subject_offerings/{off['id']}", timeout=30).status_code == 200

    def test_gate_rejects_unknown_class_name(self, seeded):
        sess, _, _ = seeded
        st = sess.post(f"{API}/res/students", json={"first_name": "TEST", "last_name": "Bad",
                                                    "admission_no": f"T{uuid.uuid4().hex[:5]}"}, timeout=30)
        sid = st.json()["id"]
        r = sess.post(f"{API}/res/enrollments",
                      json={"student_id": sid, "class_name": "TEST_Ghost", "academic_year": "2026-27"}, timeout=30)
        assert r.status_code == 400
        assert "does not exist" in r.json()["detail"].lower()
        ta = sess.post(f"{API}/res/teacher_assignments",
                       json={"teacher_email": "nobody@qa.test", "class_name": "TEST_Ghost"}, timeout=30)
        assert ta.status_code == 400
        assert "does not exist" in ta.json()["detail"].lower()
        sess.delete(f"{API}/res/students/{sid}", timeout=30)

    def test_valid_enrollment_and_assignment_pass(self, seeded):
        sess, cls, subj = seeded
        st = sess.post(f"{API}/res/students", json={"first_name": "TEST", "last_name": "Ok",
                                                    "admission_no": f"T{uuid.uuid4().hex[:5]}"}, timeout=30)
        sid = st.json()["id"]
        en = sess.post(f"{API}/res/enrollments", json={"student_id": sid, "class_name": cls["name"],
                                                       "section": "A", "academic_year": "2026-27"}, timeout=30)
        assert en.status_code == 200, en.text
        assert en.json()["student_name"] == "TEST Ok"
        ta = sess.post(f"{API}/res/teacher_assignments",
                       json={"teacher_email": "nobody@qa.test", "class_name": cls["name"],
                             "section": "A", "subject": subj["name"]}, timeout=30)
        assert ta.status_code == 200, ta.text
        sess.delete(f"{API}/res/enrollments/{en.json()['id']}", timeout=30)
        sess.delete(f"{API}/res/teacher_assignments/{ta.json()['id']}", timeout=30)
        sess.delete(f"{API}/res/students/{sid}", timeout=30)


# ---------------- full setup completion for fresh institution ----------------

class TestCompleteSetupFlow:
    def test_walk_all_steps_to_complete(self, fresh_institution):
        sess, iid, _ = fresh_institution
        apply_presets(sess)
        assert sess.put(f"{API}/institution/profile",
                        json={"contact_email": "TEST_office@qa.test", "phone": "9998887776"},
                        timeout=30).status_code == 200
        created = []
        for ep, body in [
            ("res/academic_years", {"name": "TEST_2026-27"}),
            ("res/subjects", {"name": "TEST_Science"}),
        ]:
            r = sess.post(f"{API}/{ep}", json=body, timeout=30)
            assert r.status_code == 200, r.text
            created.append((ep, r.json()["id"]))
        unit_id = sess.get(f"{API}/lookup/academic_units", timeout=30).json()[0]["value"]
        c = sess.post(f"{API}/res/classes", json={"name": "TEST_Class X", "academic_unit_id": unit_id}, timeout=30)
        assert c.status_code == 200
        created.append(("res/classes", c.json()["id"]))
        sec = sess.post(f"{API}/res/sections", json={"name": "TEST_A", "class_name": "TEST_Class X"}, timeout=30)
        assert sec.status_code == 200
        created.append(("res/sections", sec.json()["id"]))

        d = sess.get(f"{API}/institution/setup-status", timeout=30).json()
        assert d["setup_complete"] is True, d
        assert d["operationally_ready"] is False

        tu = sess.post(f"{API}/users", json={"name": "TEST Teacher", "email": f"TEST_t_{uuid.uuid4().hex[:6]}@qa.test",
                                             "password": "Teach@2026!", "role": "teacher"}, timeout=30)
        assert tu.status_code == 200, tu.text
        ta = sess.post(f"{API}/res/teacher_assignments",
                       json={"teacher_email": tu.json()["email"], "class_name": "TEST_Class X",
                             "section": "TEST_A", "subject": "TEST_Science"}, timeout=30)
        assert ta.status_code == 200, ta.text
        d2 = sess.get(f"{API}/institution/setup-status", timeout=30).json()
        assert d2["setup_complete"] is True
        assert d2["operationally_ready"] is True
