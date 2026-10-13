"""Iteration 13 backend tests: teacher homeroom (My Class), teacher achievements,
homeroom-scoped report cards, ensure_class_access grants, teacher assessments +
marks entry authz, student portal subjects + attendance history.

Run serially: pytest /app/backend/tests/test_iteration13.py -v -n 0
Creates and cleans up: throwaway class/section/student (unrelated class), draft
assessment for Grade 6/A Mathematics, teacher achievements, Aarav portal user.
"""
import os

import pytest
import requests
from dotenv import dotenv_values

fe = dotenv_values("/app/frontend/.env")
_base = os.environ.get("REACT_APP_BACKEND_URL") or fe.get("REACT_APP_BACKEND_URL")
if not _base:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
API = _base.rstrip("/") + "/api"

ADMIN = {"email": "admin@greenwood.edu", "password": "Green@2026!"}
TEACHER = {"email": "meera@greenwood.edu", "password": "Teach@2026!"}
AARAV_ID = "9fa05e4b-3ec9-4e53-8fb2-8a69b517a4dc"
SECTION_A_ID = "c3e28765-c942-4a93-9ea5-5ab880292061"
MEERA_ID = "6d90ce95-7c16-4401-a98d-d4c0e2d47914"
PORTAL_LOGIN = {"email": "test_iter13_portal@qa.test", "password": "Portal@2026!"}


@pytest.fixture(scope="module")
def admin():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=ADMIN, timeout=30)
    if r.status_code != 200:
        pytest.fail(f"Admin login failed {r.status_code}: {r.text[:300]}")
    return s


@pytest.fixture(scope="module")
def teacher():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=TEACHER, timeout=30)
    if r.status_code != 200:
        pytest.fail(f"Teacher login failed {r.status_code}: {r.text[:300]}")
    return s


@pytest.fixture(scope="module")
def foreign(admin):
    """Unrelated class + section + student that Meera has no access to."""
    created = {}
    units = admin.get(f"{API}/res/academic_units?limit=50", timeout=30).json()["items"]
    r = admin.post(f"{API}/res/classes", json={"name": "TEST_Grade 13X", "grade_level": "13",
                                               "academic_unit_id": units[0]["id"], "status": "active"}, timeout=30)
    assert r.status_code == 200, r.text
    created["class_id"] = r.json()["id"]
    created["class_name"] = r.json()["name"]
    r = admin.post(f"{API}/res/sections", json={"name": "X", "class_name": created["class_name"],
                                                "status": "active"}, timeout=30)
    assert r.status_code == 200, r.text
    created["section_id"] = r.json()["id"]
    r = admin.post(f"{API}/res/students", json={"first_name": "TEST_Foreign", "last_name": "Student",
                                                "class_name": created["class_name"], "section": "X",
                                                "admission_no": "TEST13X", "status": "active"}, timeout=30)
    assert r.status_code == 200, r.text
    created["student_id"] = r.json()["id"]
    yield created
    admin.delete(f"{API}/res/students/{created['student_id']}", timeout=30)
    admin.delete(f"{API}/res/sections/{created['section_id']}", timeout=30)
    admin.delete(f"{API}/res/classes/{created['class_id']}", timeout=30)


@pytest.fixture(scope="module")
def draft_assessment(admin):
    r = admin.post(f"{API}/res/assessments", json={"name": "TEST_Draft Iter13", "class_name": "Grade 6",
                                                   "section": "A", "subject": "Mathematics",
                                                   "max_marks": 50, "status": "draft",
                                                   "date": "2026-07-01"}, timeout=30)
    assert r.status_code == 200, r.text
    aid = r.json()["id"]
    assert r.json().get("status") == "draft", r.json()
    yield r.json()
    admin.delete(f"{API}/res/assessments/{aid}", timeout=30)


# ---------------- My Class (homeroom) ----------------

class TestMyClass:
    def test_my_class_list(self, teacher):
        r = teacher.get(f"{API}/teacher/my-class", timeout=30)
        assert r.status_code == 200, r.text
        homerooms = r.json()["homerooms"]
        assert homerooms, "Meera should be class teacher of Grade 6 A"
        target = [h for h in homerooms if h["id"] == SECTION_A_ID]
        assert target, [h.get("name") for h in homerooms]
        assert target[0]["class_name"] == "Grade 6"
        assert target[0]["name"] == "A"
        assert "_id" not in target[0]

    def test_my_class_detail(self, teacher):
        r = teacher.get(f"{API}/teacher/my-class/{SECTION_A_ID}", timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["section"]["class_leader_id"] == AARAV_ID
        aarav = next((s for s in body["students"] if s["id"] == AARAV_ID), None)
        assert aarav, "Aarav missing from roster"
        assert aarav["attendance_total"] >= 1
        assert aarav["attendance_pct"] == round(aarav["attendance_present"] / aarav["attendance_total"] * 100)
        assert isinstance(aarav["achievements_count"], int)
        assert isinstance(body["achievements"], list)
        for s in body["students"]:
            assert "_id" not in s

    def test_my_class_detail_foreign_section_403(self, teacher, foreign):
        r = teacher.get(f"{API}/teacher/my-class/{foreign['section_id']}", timeout=30)
        assert r.status_code == 403, r.status_code

    def test_my_class_requires_teacher_role(self, admin):
        r = admin.get(f"{API}/teacher/my-class", timeout=30)
        assert r.status_code == 403, r.status_code


# ---------------- Teacher achievements ----------------

class TestTeacherAchievements:
    def test_add_list_and_delete(self, teacher):
        payload = {"student_id": AARAV_ID, "title": "TEST_Iter13 Award",
                   "description": "Quiz winner", "date": "2026-07-02"}
        r = teacher.post(f"{API}/teacher/achievements", json=payload, timeout=30)
        assert r.status_code == 200, r.text
        doc = r.json()
        assert doc["title"] == "TEST_Iter13 Award"
        assert doc["awarded_by"] == "Meera Iyer", doc.get("awarded_by")
        assert doc["student_name"].startswith("Aarav")
        assert doc["class_name"] == "Grade 6" and doc["section"] == "A"
        assert "_id" not in doc
        aid = doc["id"]

        detail = teacher.get(f"{API}/teacher/my-class/{SECTION_A_ID}", timeout=30).json()
        assert any(a["id"] == aid for a in detail["achievements"]), "achievement not in my-class detail"

        d = teacher.delete(f"{API}/teacher/achievements/{aid}", timeout=30)
        assert d.status_code == 200, d.text
        detail = teacher.get(f"{API}/teacher/my-class/{SECTION_A_ID}", timeout=30).json()
        assert not any(a["id"] == aid for a in detail["achievements"]), "achievement still present after delete"
        assert teacher.delete(f"{API}/teacher/achievements/{aid}", timeout=30).status_code == 404

    def test_missing_title_400(self, teacher):
        r = teacher.post(f"{API}/teacher/achievements", json={"student_id": AARAV_ID, "title": "  "}, timeout=30)
        assert r.status_code == 400, r.status_code

    def test_non_homeroom_student_403(self, teacher, foreign):
        r = teacher.post(f"{API}/teacher/achievements",
                         json={"student_id": foreign["student_id"], "title": "TEST_Nope"}, timeout=30)
        assert r.status_code == 403, f"{r.status_code} {r.text[:200]}"
        assert "homeroom" in r.json().get("detail", "").lower()

    def test_unknown_student_400(self, teacher):
        r = teacher.post(f"{API}/teacher/achievements",
                         json={"student_id": "no-such-id", "title": "TEST_Nope"}, timeout=30)
        assert r.status_code == 400, r.status_code


# ---------------- Report card scoping ----------------

class TestReportCardScoping:
    def test_teacher_homeroom_student_allowed(self, teacher):
        r = teacher.get(f"{API}/students/{AARAV_ID}/report-card", timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["student"]["id"] == AARAV_ID
        assert isinstance(body.get("subjects"), list) or isinstance(body.get("rows"), list), list(body)

    def test_teacher_foreign_student_403(self, teacher, foreign):
        r = teacher.get(f"{API}/students/{foreign['student_id']}/report-card", timeout=30)
        assert r.status_code == 403, f"{r.status_code} {r.text[:200]}"

    def test_admin_any_student_allowed(self, admin, foreign):
        r = admin.get(f"{API}/students/{foreign['student_id']}/report-card", timeout=30)
        assert r.status_code == 200, r.text

    def test_unknown_student_404(self, admin):
        r = admin.get(f"{API}/students/no-such-id/report-card", timeout=30)
        assert r.status_code == 404, r.status_code


# ---------------- ensure_class_access grants ----------------

class TestClassAccessGrants:
    def test_attendance_sheet_get_for_homeroom_section(self, teacher):
        r = teacher.get(f"{API}/attendance/sheet",
                        params={"class_name": "Grade 6", "section": "A", "date": "2026-07-03"}, timeout=30)
        assert r.status_code == 200, r.text
        assert any(s["id"] == AARAV_ID for s in r.json()["students"])

    def test_attendance_sheet_post_for_homeroom_section(self, teacher, admin):
        date = "2026-07-03"
        r = teacher.post(f"{API}/attendance/sheet",
                         json={"class_name": "Grade 6", "section": "A", "date": date,
                               "entries": {AARAV_ID: "present"}}, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["entries"][AARAV_ID] == "present"
        # verify persisted
        g = teacher.get(f"{API}/attendance/sheet",
                        params={"class_name": "Grade 6", "section": "A", "date": date}, timeout=30).json()
        assert g["record"]["entries"][AARAV_ID] == "present"

    def test_attendance_sheet_foreign_class_403(self, teacher, foreign):
        r = teacher.get(f"{API}/attendance/sheet",
                        params={"class_name": foreign["class_name"], "section": "X", "date": "2026-07-03"},
                        timeout=30)
        assert r.status_code == 403, r.status_code

    def test_class_teacher_grant_without_subject_assignment(self, admin, teacher):
        """Temporarily remove Meera's Grade 6/A Math assignment; access must persist via homeroom."""
        assigns = admin.get(f"{API}/res/teacher_assignments?limit=100", timeout=30).json()["items"]
        mine = [a for a in assigns if a.get("class_name") == "Grade 6"
                and (a.get("teacher_id") == MEERA_ID or a.get("teacher_email") == TEACHER["email"])]
        assert mine, "Meera has no Grade 6 assignment to temporarily remove"
        backups = [dict(a) for a in mine]
        try:
            for a in mine:
                assert admin.delete(f"{API}/res/teacher_assignments/{a['id']}", timeout=30).status_code == 200
            r = teacher.get(f"{API}/attendance/sheet",
                            params={"class_name": "Grade 6", "section": "A", "date": "2026-07-03"}, timeout=30)
            assert r.status_code == 200, f"class-teacher grant failed: {r.status_code} {r.text[:200]}"
        finally:
            for a in backups:
                payload = {k: v for k, v in a.items()
                           if k not in ("id", "_id", "created_at", "institution_id", "updated_at")}
                rr = admin.post(f"{API}/res/teacher_assignments", json=payload, timeout=30)
                assert rr.status_code == 200, f"RESTORE FAILED: {rr.text[:300]}"
        # sanity: assignment restored
        assigns = admin.get(f"{API}/res/teacher_assignments?limit=100", timeout=30).json()["items"]
        assert any(a.get("class_name") == "Grade 6" and a.get("subject") == "Mathematics"
                   and a.get("section") == "A" for a in assigns), "Grade 6 A Math assignment not restored"


# ---------------- Teacher assessments + marks ----------------

class TestTeacherAssessments:
    def test_list_only_assigned_pairs(self, teacher, draft_assessment, foreign, admin):
        r = teacher.get(f"{API}/teacher/assessments", timeout=30)
        assert r.status_code == 200, r.text
        rows = r.json()["assessments"]
        names = [a["name"] for a in rows]
        assert "Unit Test 1" in names, names
        assert draft_assessment["name"] in names, names
        for a in rows:
            assert a["class_name"] == "Grade 6", f"unassigned class leaked: {a}"
            assert "_id" not in a

    def test_teacher_can_save_marks_on_draft(self, teacher, draft_assessment):
        aid = draft_assessment["id"]
        g = teacher.get(f"{API}/assessments/{aid}/marks", timeout=30)
        assert g.status_code == 200, g.text
        assert g.json()["assessment"]["status"] == "draft"
        r = teacher.post(f"{API}/assessments/{aid}/marks",
                         json={"entries": [{"student_id": AARAV_ID, "score": 44, "status": "present"}]}, timeout=30)
        assert r.status_code == 200, r.text
        g2 = teacher.get(f"{API}/assessments/{aid}/marks", timeout=30).json()
        mk = next((m for m in g2["marks"] if m["student_id"] == AARAV_ID), None)
        assert mk and float(mk["score"]) == 44.0, g2["marks"]

    def test_marks_score_above_max_400(self, teacher, draft_assessment):
        r = teacher.post(f"{API}/assessments/{draft_assessment['id']}/marks",
                         json={"entries": [{"student_id": AARAV_ID, "score": 999, "status": "present"}]}, timeout=30)
        assert r.status_code == 400, r.status_code

    def test_published_assessment_marks_readonly(self, teacher, admin):
        rows = admin.get(f"{API}/res/assessments?search=Unit Test 1&limit=10", timeout=30).json()["items"]
        pub = next((a for a in rows if a.get("status") == "published"), None)
        assert pub, "no published Unit Test 1 found"
        r = teacher.post(f"{API}/assessments/{pub['id']}/marks",
                         json={"entries": [{"student_id": AARAV_ID, "score": 10, "status": "present"}]}, timeout=30)
        assert r.status_code == 400, f"{r.status_code} {r.text[:200]}"

    def test_publish_forbidden_for_teacher(self, teacher, draft_assessment):
        r = teacher.post(f"{API}/assessments/{draft_assessment['id']}/publish",
                         json={"publish": True}, timeout=30)
        assert r.status_code == 403, f"{r.status_code} {r.text[:200]}"

    def test_marks_foreign_assessment_403(self, teacher, admin, foreign):
        r = admin.post(f"{API}/res/assessments", json={"name": "TEST_Foreign Assess", "class_name": foreign["class_name"],
                                                       "section": "X", "subject": "Mathematics",
                                                       "max_marks": 20, "status": "draft"}, timeout=30)
        assert r.status_code == 200, r.text
        aid = r.json()["id"]
        try:
            g = teacher.get(f"{API}/assessments/{aid}/marks", timeout=30)
            assert g.status_code == 403, g.status_code
        finally:
            admin.delete(f"{API}/res/assessments/{aid}", timeout=30)


# ---------------- Student portal ----------------

class TestStudentPortal:
    @pytest.fixture(scope="class")
    def portal(self, admin, teacher):
        r = admin.post(f"{API}/students/{AARAV_ID}/portal-user", json=PORTAL_LOGIN, timeout=30)
        if r.status_code != 200:
            admin.delete(f"{API}/students/{AARAV_ID}/portal-user", timeout=30)
            r = admin.post(f"{API}/students/{AARAV_ID}/portal-user", json=PORTAL_LOGIN, timeout=30)
        assert r.status_code == 200, r.text
        s = requests.Session()
        lr = s.post(f"{API}/auth/login", json=PORTAL_LOGIN, timeout=30)
        assert lr.status_code == 200, lr.text
        yield s
        admin.delete(f"{API}/students/{AARAV_ID}/portal-user", timeout=30)

    def test_portal_me_subjects_and_history(self, portal):
        r = portal.get(f"{API}/portal/me", timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["student"]["id"] == AARAV_ID
        assert body["leader_role"] == "class_leader"
        subs = body["subjects"]
        math = next((s for s in subs if s["subject"] == "Mathematics"), None)
        assert math, subs
        assert math["teacher_name"] == "Meera Iyer", math
        assert math["max_marks"], math
        hist = body["attendance_history"]
        assert hist, "attendance_history empty"
        assert len(hist) <= 30
        dates = [h["date"] for h in hist]
        assert dates == sorted(dates, reverse=True), dates
        assert all(h["status"] for h in hist)
        assert body["attendance"]["total"] == len([h for h in hist]) or body["attendance"]["total"] >= len(hist)

    def test_portal_achievement_from_teacher_visible(self, portal, teacher):
        r = teacher.post(f"{API}/teacher/achievements",
                         json={"student_id": AARAV_ID, "title": "TEST_Portal Visible", "date": "2026-07-02"},
                         timeout=30)
        assert r.status_code == 200, r.text
        aid = r.json()["id"]
        try:
            body = portal.get(f"{API}/portal/me", timeout=30).json()
            assert any(a["id"] == aid for a in body["achievements"]), "teacher achievement not on portal"
        finally:
            teacher.delete(f"{API}/teacher/achievements/{aid}", timeout=30)

    def test_portal_role_cannot_access_teacher_endpoints(self, portal):
        assert portal.get(f"{API}/teacher/my-class", timeout=30).status_code == 403
