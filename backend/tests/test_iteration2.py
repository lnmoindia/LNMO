"""LNMO iteration-2 backend tests: lookups, academic years/enrollments/teacher assignments,
attendance sheet + records, marks + publish, teacher workspace, global search."""
import os
import uuid
from datetime import date

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
API = f"{base_url.rstrip('/')}/api"

ADMIN = {"email": "admin@greenwood.edu", "password": "Green@2026!"}
TEACHER = {"email": "meera@greenwood.edu", "password": "Teach@2026!"}
PLATFORM = {"email": "lnmopvt@gmail.com", "password": "Lnmo@2026!"}
SUFFIX = uuid.uuid4().hex[:6]


def _client(creds):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=creds, timeout=30)
    if r.status_code != 200:
        pytest.fail(f"login failed for {creds['email']}: {r.status_code} {r.text[:300]}")
    return s


@pytest.fixture(scope="module")
def admin():
    return _client(ADMIN)


@pytest.fixture(scope="module")
def teacher():
    return _client(TEACHER)


@pytest.fixture(scope="module")
def platform():
    return _client(PLATFORM)


@pytest.fixture(scope="module")
def cleanup():
    trash = []
    yield trash
    s = _client(ADMIN)
    for resource, rid in trash:
        s.delete(f"{API}/res/{resource}/{rid}", timeout=30)


# ---------------- Lookups ----------------
class TestLookups:
    @pytest.mark.parametrize("kind", ["students", "classes", "sections", "subjects",
                                      "academic_years", "teacher_users"])
    def test_lookup_shape(self, admin, kind):
        r = admin.get(f"{API}/lookup/{kind}", timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data, list)
        for row in data:
            assert set(row.keys()) == {"value", "label"}
            assert isinstance(row["value"], str) and row["value"]

    def test_lookup_unknown(self, admin):
        assert admin.get(f"{API}/lookup/bogus", timeout=30).status_code == 404

    def test_lookup_denied_for_platform_admin(self, platform):
        assert platform.get(f"{API}/lookup/students", timeout=30).status_code == 403

    def test_teacher_users_lookup_contains_seeded_teacher(self, admin):
        vals = [r["value"] for r in admin.get(f"{API}/lookup/teacher_users", timeout=30).json()]
        assert TEACHER["email"] in vals

    def test_teacher_can_use_lookups(self, teacher):
        assert teacher.get(f"{API}/lookup/classes", timeout=30).status_code == 200


# ---------------- Academic years ----------------
class TestAcademicYears:
    def test_create_and_persist(self, admin, cleanup):
        name = f"TEST_{SUFFIX}-AY"
        r = admin.post(f"{API}/res/academic_years", json={
            "name": name, "start_date": "2027-04-01", "end_date": "2028-03-31", "status": "active"}, timeout=30)
        assert r.status_code == 200, r.text
        doc = r.json()
        assert "_id" not in doc
        assert doc["name"] == name and doc["status"] == "active"
        cleanup.append(("academic_years", doc["id"]))

        lst = admin.get(f"{API}/res/academic_years", params={"search": name}, timeout=30).json()
        assert lst["total"] >= 1
        found = [i for i in lst["items"] if i["id"] == doc["id"]]
        assert found and found[0]["start_date"] == "2027-04-01"

        # appears in lookup
        assert name in [x["value"] for x in admin.get(f"{API}/lookup/academic_years", timeout=30).json()]

    def test_teacher_cannot_list(self, teacher):
        assert teacher.get(f"{API}/res/academic_years", timeout=30).status_code == 403


# ---------------- Enrollments ----------------
class TestEnrollments:
    def test_enrollment_updates_student(self, admin, cleanup):
        r = admin.post(f"{API}/res/students", json={
            "first_name": "TESTQA_Enroll", "last_name": "Student", "admission_no": "TESTQA-EN1"}, timeout=30)
        assert r.status_code == 200, r.text
        sid = r.json()["id"]
        cleanup.append(("students", sid))
        years = admin.get(f"{API}/lookup/academic_years", timeout=30).json()
        year = years[0]["value"] if years else "2026-27"

        r = admin.post(f"{API}/res/enrollments", json={
            "student_id": sid, "academic_year": year, "class_name": "Grade 6",
            "section": "A", "roll_no": "99"}, timeout=30)
        assert r.status_code == 200, r.text
        doc = r.json()
        cleanup.append(("enrollments", doc["id"]))
        assert doc["student_name"], "student_name not enriched"
        assert "admission_no" in doc

        # duplicate enrollment for the same student + year must be rejected
        r2 = admin.post(f"{API}/res/enrollments", json={
            "student_id": sid, "academic_year": year, "class_name": "Grade 6", "section": "A"}, timeout=30)
        assert r2.status_code == 400, f"duplicate enrollment should be rejected: {r2.text}"

        st = admin.get(f"{API}/res/students", params={"search": doc["admission_no"] or doc["student_name"]},
                       timeout=30).json()["items"]
        target = [s for s in st if s["id"] == sid]
        assert target, "student not found after enrollment"
        assert target[0]["class_name"] == "Grade 6"
        assert target[0]["section"] == "A"
        assert target[0]["academic_year"] == year

    def test_enrollment_requires_student(self, admin):
        r = admin.post(f"{API}/res/enrollments", json={"academic_year": "2026-27", "class_name": "Grade 6"}, timeout=30)
        assert r.status_code == 400, r.text

    def test_enrollment_invalid_student(self, admin):
        r = admin.post(f"{API}/res/enrollments", json={"student_id": str(uuid.uuid4())}, timeout=30)
        assert r.status_code == 400
        assert "Student not found" in r.json()["detail"]


# ---------------- Teacher assignments ----------------
class TestTeacherAssignments:
    def test_create_resolves_teacher_name(self, admin, cleanup):
        r = admin.post(f"{API}/res/teacher_assignments", json={
            "teacher_email": TEACHER["email"], "class_name": "Grade 6", "section": "A",
            "subject": f"TEST_{SUFFIX}"}, timeout=30)
        assert r.status_code == 200, r.text
        doc = r.json()
        cleanup.append(("teacher_assignments", doc["id"]))
        assert doc["teacher_name"] and doc["teacher_name"] != TEACHER["email"], doc

    def test_requires_teacher(self, admin):
        r = admin.post(f"{API}/res/teacher_assignments", json={"class_name": "Grade 6"}, timeout=30)
        assert r.status_code == 400


# ---------------- Attendance ----------------
class TestAttendance:
    DATE = date.today().isoformat()

    def test_admin_sheet_and_draft_save(self, admin):
        r = admin.get(f"{API}/attendance/sheet", params={
            "class_name": "Grade 6", "section": "A", "date": self.DATE}, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data["students"], list) and data["students"], "no students in Grade 6 A"
        sid = data["students"][0]["id"]

        save = admin.post(f"{API}/attendance/sheet", json={
            "class_name": "Grade 6", "section": "A", "date": self.DATE,
            "entries": {sid: "late"}, "finalized": False}, timeout=30)
        assert save.status_code == 200, save.text
        rec = save.json()
        assert rec["finalized"] is False and rec["entries"][sid] == "late"
        assert "_id" not in rec

        again = admin.get(f"{API}/attendance/sheet", params={
            "class_name": "Grade 6", "section": "A", "date": self.DATE}, timeout=30).json()
        assert again["record"]["entries"][sid] == "late"

    def test_invalid_status_filtered(self, admin):
        sheet = admin.get(f"{API}/attendance/sheet", params={
            "class_name": "Grade 6", "section": "A", "date": self.DATE}, timeout=30).json()
        sid = sheet["students"][0]["id"]
        r = admin.post(f"{API}/attendance/sheet", json={
            "class_name": "Grade 6", "section": "A", "date": self.DATE,
            "entries": {sid: "banana"}, "finalized": False}, timeout=30)
        assert r.status_code == 200
        assert sid not in r.json()["entries"]

    def test_missing_class_or_date(self, admin):
        assert admin.post(f"{API}/attendance/sheet", json={"date": self.DATE}, timeout=30).status_code == 400
        assert admin.post(f"{API}/attendance/sheet", json={"class_name": "Grade 6"}, timeout=30).status_code == 400

    def test_teacher_locked_after_finalize(self, admin, teacher):
        import pymongo
        from dotenv import dotenv_values
        benv = dotenv_values("/app/backend/.env")
        db = pymongo.MongoClient(benv["MONGO_URL"])[benv["DB_NAME"]]
        d = "2026-07-02"
        key = {"class_name": "Grade 6", "section": "A", "date": d}
        db.attendance.delete_many(key)
        try:
            sheet = teacher.get(f"{API}/attendance/sheet", params={
                "class_name": "Grade 6", "section": "A", "date": d}, timeout=30)
            assert sheet.status_code == 200, sheet.text
            sid = sheet.json()["students"][0]["id"]

            # teacher can save draft
            r = teacher.post(f"{API}/attendance/sheet", json={
                "class_name": "Grade 6", "section": "A", "date": d,
                "entries": {sid: "present"}, "finalized": False}, timeout=30)
            assert r.status_code == 200, r.text

            # admin finalizes
            r = admin.post(f"{API}/attendance/sheet", json={
                "class_name": "Grade 6", "section": "A", "date": d,
                "entries": {sid: "present"}, "finalized": True}, timeout=30)
            assert r.status_code == 200 and r.json()["finalized"] is True

            # teacher blocked
            r = teacher.post(f"{API}/attendance/sheet", json={
                "class_name": "Grade 6", "section": "A", "date": d,
                "entries": {sid: "absent"}, "finalized": False}, timeout=30)
            assert r.status_code == 403, r.text

            # admin can still correct
            r = admin.post(f"{API}/attendance/sheet", json={
                "class_name": "Grade 6", "section": "A", "date": d,
                "entries": {sid: "present"}, "finalized": True}, timeout=30)
            assert r.status_code == 200
        finally:
            db.attendance.delete_many(key)

    def test_teacher_unassigned_class_denied(self, teacher):
        r = teacher.get(f"{API}/attendance/sheet", params={
            "class_name": "Grade 12", "section": "Z", "date": self.DATE}, timeout=30)
        assert r.status_code == 403, r.text

    def test_records_counts(self, admin):
        r = admin.get(f"{API}/attendance/records", timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert data["total"] >= 1
        it = data["items"][0]
        for k in ("present", "absent", "late", "finalized", "class_name", "date"):
            assert k in it, it
        assert "entries" not in it

    def test_teacher_records_scoped(self, teacher):
        r = teacher.get(f"{API}/attendance/records", timeout=30)
        assert r.status_code == 200
        for it in r.json()["items"]:
            assert it["class_name"] == "Grade 6"

    def test_platform_admin_denied(self, platform):
        assert platform.get(f"{API}/attendance/records", timeout=30).status_code == 403


# ---------------- Marks + publish ----------------
class TestMarks:
    @pytest.fixture(scope="class")
    def assessment(self, admin):
        r = admin.post(f"{API}/res/assessments", json={
            "name": f"TEST_Assessment_{SUFFIX}", "subject": "Mathematics", "class_name": "Grade 6",
            "section": "A", "max_marks": 50, "date": "2026-07-10"}, timeout=30)
        assert r.status_code == 200, r.text
        doc = r.json()
        assert doc["status"] == "draft", "new assessment should default to draft"
        yield doc
        admin.delete(f"{API}/res/assessments/{doc['id']}", timeout=30)

    def test_get_marks_grid(self, admin, assessment):
        r = admin.get(f"{API}/assessments/{assessment['id']}/marks", timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["assessment"]["id"] == assessment["id"]
        assert data["students"], "no students in marks grid"
        assert isinstance(data["marks"], list)

    def test_get_marks_unknown_assessment(self, admin):
        assert admin.get(f"{API}/assessments/{uuid.uuid4()}/marks", timeout=30).status_code == 404

    def test_save_valid_marks_persist(self, admin, assessment):
        students = admin.get(f"{API}/assessments/{assessment['id']}/marks", timeout=30).json()["students"]
        sid = students[0]["id"]
        r = admin.post(f"{API}/assessments/{assessment['id']}/marks",
                       json={"entries": [{"student_id": sid, "score": 42, "status": "present"}]}, timeout=30)
        assert r.status_code == 200, r.text
        marks = admin.get(f"{API}/assessments/{assessment['id']}/marks", timeout=30).json()["marks"]
        row = [m for m in marks if m["student_id"] == sid]
        assert row and row[0]["score"] == 42 and row[0]["status"] == "present"
        assert "_id" not in row[0]

    def test_absent_clears_score(self, admin, assessment):
        students = admin.get(f"{API}/assessments/{assessment['id']}/marks", timeout=30).json()["students"]
        sid = students[0]["id"]
        r = admin.post(f"{API}/assessments/{assessment['id']}/marks",
                       json={"entries": [{"student_id": sid, "score": 30, "status": "absent"}]}, timeout=30)
        assert r.status_code == 200
        marks = admin.get(f"{API}/assessments/{assessment['id']}/marks", timeout=30).json()["marks"]
        row = [m for m in marks if m["student_id"] == sid][0]
        assert row["score"] is None and row["status"] == "absent"

    def test_score_above_max_rejected(self, admin, assessment):
        students = admin.get(f"{API}/assessments/{assessment['id']}/marks", timeout=30).json()["students"]
        sid = students[0]["id"]
        r = admin.post(f"{API}/assessments/{assessment['id']}/marks",
                       json={"entries": [{"student_id": sid, "score": 999, "status": "present"}]}, timeout=30)
        assert r.status_code == 400, r.text
        assert "between 0 and 50" in r.json()["detail"]

    def test_non_numeric_score_rejected(self, admin, assessment):
        students = admin.get(f"{API}/assessments/{assessment['id']}/marks", timeout=30).json()["students"]
        sid = students[0]["id"]
        r = admin.post(f"{API}/assessments/{assessment['id']}/marks",
                       json={"entries": [{"student_id": sid, "score": "abc", "status": "present"}]}, timeout=30)
        assert r.status_code == 400

    def test_publish_locks_then_unpublish(self, admin, assessment):
        aid = assessment["id"]
        students = admin.get(f"{API}/assessments/{aid}/marks", timeout=30).json()["students"]
        sid = students[0]["id"]

        r = admin.post(f"{API}/assessments/{aid}/publish", json={"publish": True}, timeout=30)
        assert r.status_code == 200 and r.json()["status"] == "published"
        assert admin.get(f"{API}/assessments/{aid}/marks", timeout=30).json()["assessment"]["status"] == "published"

        blocked = admin.post(f"{API}/assessments/{aid}/marks",
                             json={"entries": [{"student_id": sid, "score": 10, "status": "present"}]}, timeout=30)
        assert blocked.status_code == 400
        assert "Unpublish" in blocked.json()["detail"]

        r = admin.post(f"{API}/assessments/{aid}/publish", json={"publish": False}, timeout=30)
        assert r.status_code == 200 and r.json()["status"] == "draft"
        ok = admin.post(f"{API}/assessments/{aid}/marks",
                        json={"entries": [{"student_id": sid, "score": 10, "status": "present"}]}, timeout=30)
        assert ok.status_code == 200

    def test_publish_unknown_assessment(self, admin):
        assert admin.post(f"{API}/assessments/{uuid.uuid4()}/publish",
                          json={"publish": True}, timeout=30).status_code == 404

    def test_teacher_cannot_publish(self, teacher, assessment):
        r = teacher.post(f"{API}/assessments/{assessment['id']}/publish", json={"publish": True}, timeout=30)
        assert r.status_code == 403


# ---------------- Teacher workspace ----------------
class TestTeacherWorkspace:
    def test_overview(self, teacher):
        r = teacher.get(f"{API}/teacher/overview", timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["assignments"], "seeded teacher should have assignments"
        assert data["stats"]["classes"] >= 1
        assert data["stats"]["students"] >= 1
        assert data["stats"]["subjects"] >= 1
        for a in data["assignments"]:
            assert "_id" not in a

    def test_overview_denied_for_admin(self, admin):
        assert admin.get(f"{API}/teacher/overview", timeout=30).status_code == 403

    def test_students_of_assigned_class(self, teacher):
        r = teacher.get(f"{API}/teacher/students",
                        params={"class_name": "Grade 6", "section": "A"}, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["students"], "assigned class should have students"

    def test_students_unassigned_denied(self, teacher):
        r = teacher.get(f"{API}/teacher/students",
                        params={"class_name": "Grade 99", "section": "Z"}, timeout=30)
        assert r.status_code == 403

    def test_teacher_cannot_access_institution_resources(self, teacher):
        for res in ("students", "classes", "assessments", "enrollments"):
            assert teacher.get(f"{API}/res/{res}", timeout=30).status_code == 403


# ---------------- Global search ----------------
class TestSearch:
    def test_short_query_returns_empty(self, admin):
        r = admin.get(f"{API}/search", params={"q": "a"}, timeout=30)
        assert r.status_code == 200 and r.json()["groups"] == []

    def test_institution_admin_student_search(self, admin):
        r = admin.get(f"{API}/search", params={"q": "aarav"}, timeout=30)
        assert r.status_code == 200, r.text
        groups = r.json()["groups"]
        labels = [g["label"] for g in groups]
        assert "Students" in labels, groups
        item = [g for g in groups if g["label"] == "Students"][0]["items"][0]
        assert item["path"].startswith("/app/students?q=")
        assert item["label"] and "id" in item

    def test_platform_admin_institution_search(self, platform):
        r = platform.get(f"{API}/search", params={"q": "green"}, timeout=30)
        assert r.status_code == 200
        groups = r.json()["groups"]
        assert any(g["label"] == "Institutions" for g in groups), groups

    def test_teacher_search_scoped_to_own_students(self, teacher):
        r = teacher.get(f"{API}/search", params={"q": "aarav"}, timeout=30)
        assert r.status_code == 200
        groups = r.json()["groups"]
        assert all(g["label"] == "My students" for g in groups), groups

    def test_search_requires_auth(self):
        assert requests.get(f"{API}/search", params={"q": "aarav"}, timeout=30).status_code == 401

    def test_no_password_hash_leak(self, admin):
        r = admin.get(f"{API}/search", params={"q": "admin"}, timeout=30)
        assert "password_hash" not in r.text
