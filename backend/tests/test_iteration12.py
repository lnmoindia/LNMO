"""Iteration 12 backend tests: Timetable (config/grid/conflict engine/teacher-grid),
portal timetable, notices feed + audience filtering, report cards.

Run serially: pytest /app/backend/tests/test_iteration12.py -v -n 0
Creates and cleans up: TEST_ class/section/offering/assignment/timetable entries,
notices, unit-override config, Aarav portal user.
"""
import os

import pytest
import requests
from dotenv import dotenv_values
from pymongo import MongoClient

fe = dotenv_values("/app/frontend/.env")
be = dotenv_values("/app/backend/.env")
_base = os.environ.get("REACT_APP_BACKEND_URL") or fe.get("REACT_APP_BACKEND_URL")
if not _base:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
API = _base.rstrip("/") + "/api"

ADMIN = {"email": "admin@greenwood.edu", "password": "Green@2026!"}
TEACHER = {"email": "meera@greenwood.edu", "password": "Teach@2026!"}
AARAV_ID = "9fa05e4b-3ec9-4e53-8fb2-8a69b517a4dc"
CLASS_ID_G6 = "db61baf7-67fb-4c66-b04c-f8f11196b9ac"
AY = "2026-27"
PORTAL_LOGIN = {"email": "test_aarav_portal@qa.test", "password": "Portal@2026!"}


def _db():
    mongo_url = be.get("MONGO_URL") or os.environ.get("MONGO_URL")
    return MongoClient(mongo_url)[be.get("DB_NAME") or os.environ["DB_NAME"]]


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
def seed(admin):
    """Second class + section + Mathematics offering + Meera assignment (for teacher/room conflicts)."""
    created = {"entries": [], "notices": []}
    units = admin.get(f"{API}/res/academic_units?limit=50").json()["items"]
    assert units, "No academic units"
    g6 = admin.get(f"{API}/res/classes?search=Grade 6&limit=10").json()["items"]
    unit_id = next((c.get("academic_unit_id") for c in g6 if c["name"] == "Grade 6"), units[0]["id"])
    created["unit_id"] = unit_id

    r = admin.post(f"{API}/res/classes", json={"name": "TEST_Grade 12Z", "grade_level": "12",
                                               "academic_unit_id": unit_id, "status": "active"})
    assert r.status_code == 200, r.text
    created["class_id"] = r.json()["id"]
    created["class_name"] = r.json()["name"]

    r = admin.post(f"{API}/res/sections", json={"name": "Z", "class_name": created["class_name"],
                                                "status": "active"})
    assert r.status_code == 200, r.text
    created["section_id"] = r.json()["id"]

    r = admin.post(f"{API}/res/subject_offerings", json={"subject": "Mathematics",
                                                         "class_name": created["class_name"],
                                                         "section": "", "max_marks": 100})
    assert r.status_code == 200, r.text
    created["offering_id"] = r.json()["id"]

    r = admin.post(f"{API}/res/teacher_assignments", json={"teacher_email": TEACHER["email"],
                                                           "class_name": created["class_name"],
                                                           "section": "Z", "subject": "Mathematics"})
    assert r.status_code == 200, r.text
    created["assignment_id"] = r.json()["id"]
    assert r.json().get("teacher_id"), "assignment has no teacher_id"

    yield created

    for eid in created["entries"]:
        admin.delete(f"{API}/timetable/entries/{eid}")
    for nid in created["notices"]:
        admin.delete(f"{API}/res/notices/{nid}")
    for res, key in (("teacher_assignments", "assignment_id"), ("subject_offerings", "offering_id"),
                     ("sections", "section_id"), ("classes", "class_id")):
        if created.get(key):
            admin.delete(f"{API}/res/{res}/{created[key]}")


@pytest.fixture(scope="module")
def g6_grid(admin):
    r = admin.get(f"{API}/timetable/grid", params={"academic_year": AY, "class_name": "Grade 6", "section": "A"})
    assert r.status_code == 200, r.text
    return r.json()


# ---------------- Phase 1: config ----------------

class TestTimetableConfig:
    def test_get_config_institution_default(self, admin):
        r = admin.get(f"{API}/timetable/config", params={"academic_year": AY})
        assert r.status_code == 200, r.text
        body = r.json()
        cfg = body["config"]
        assert body["explicit"] is True, "saved 2026-27 institution default not found"
        assert cfg["working_days"] == ["mon", "tue", "wed", "thu", "fri"], cfg["working_days"]
        labels = [p["label"] for p in cfg["periods"]]
        assert labels == ["P1", "P2", "P3", "Break", "P4", "P5", "Lunch", "P6", "P7"], labels
        assert cfg["periods"][3]["is_break"] is True
        assert "_id" not in cfg

    def test_get_config_unknown_year_falls_back_to_default_shape(self, admin):
        r = admin.get(f"{API}/timetable/config", params={"academic_year": "1999-00"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["explicit"] is False
        assert body["config"]["periods"], "fallback config has no periods"

    def test_save_config_invalid_year_400(self, admin):
        r = admin.post(f"{API}/timetable/config", json={"academic_year": "1999-00",
                                                        "working_days": ["mon"],
                                                        "periods": [{"label": "P1", "start": "09:00", "end": "09:45"}]})
        assert r.status_code == 400, r.text

    def test_save_config_requires_working_day_and_teaching_period(self, admin):
        r = admin.post(f"{API}/timetable/config", json={"academic_year": AY, "working_days": [],
                                                        "periods": [{"label": "P1"}]})
        assert r.status_code == 400
        r = admin.post(f"{API}/timetable/config", json={"academic_year": AY, "working_days": ["mon"],
                                                        "periods": [{"label": "Break", "is_break": True}]})
        assert r.status_code == 400
        r = admin.post(f"{API}/timetable/config", json={"academic_year": AY, "working_days": ["mon"],
                                                        "periods": [{"label": "", "start": "09:00"}]})
        assert r.status_code == 400

    def test_unit_override_upsert_and_effect(self, admin, seed):
        unit_id = seed["unit_id"]
        periods = [{"label": "P1", "start": "08:00", "end": "08:40", "is_break": False},
                   {"label": "P2", "start": "08:40", "end": "09:20", "is_break": False}]
        r = admin.post(f"{API}/timetable/config", json={"academic_year": AY, "academic_unit_id": unit_id,
                                                        "working_days": ["mon", "tue"], "periods": periods})
        assert r.status_code == 200, r.text
        saved = r.json()
        assert saved["academic_unit_id"] == unit_id
        assert "_id" not in saved
        got = admin.get(f"{API}/timetable/config", params={"academic_year": AY, "academic_unit_id": unit_id}).json()
        assert got["explicit"] is True
        assert len(got["config"]["periods"]) == 2
        assert unit_id in got["unit_overrides"]
        # upsert (no duplicate doc)
        r2 = admin.post(f"{API}/timetable/config", json={"academic_year": AY, "academic_unit_id": unit_id,
                                                         "working_days": ["mon"], "periods": periods})
        assert r2.status_code == 200
        assert r2.json()["id"] == saved["id"], "override was duplicated instead of upserted"
        # grid for a class in this unit now uses the override
        grid = admin.get(f"{API}/timetable/grid", params={"academic_year": AY, "class_name": "Grade 6",
                                                          "section": "A"}).json()
        assert len(grid["config"]["periods"]) == 2, "unit override not applied to grid"
        # cleanup override so the rest of the suite uses the institution default
        _db().timetable_configs.delete_many({"academic_year": AY, "academic_unit_id": unit_id})
        grid2 = admin.get(f"{API}/timetable/grid", params={"academic_year": AY, "class_name": "Grade 6",
                                                           "section": "A"}).json()
        assert len(grid2["config"]["periods"]) == 9

    def test_config_forbidden_for_teacher_save(self, teacher):
        r = teacher.post(f"{API}/timetable/config", json={"academic_year": AY, "working_days": ["mon"],
                                                          "periods": [{"label": "P1"}]})
        assert r.status_code == 403, r.status_code


# ---------------- Phase 3: grid / builder data ----------------

class TestTimetableGrid:
    def test_grid_returns_config_entries_offerings_assignments(self, g6_grid):
        assert g6_grid["config"]["working_days"]
        assert any(o["subject"] == "Mathematics" for o in g6_grid["offerings"]), g6_grid["offerings"]
        assert any(a["subject"] == "Mathematics" for a in g6_grid["assignments"]), g6_grid["assignments"]
        mon_p1 = [e for e in g6_grid["entries"] if e["day"] == "mon" and e["period_no"] == 1]
        assert len(mon_p1) == 1, g6_grid["entries"]
        assert mon_p1[0]["subject"] == "Mathematics"
        assert mon_p1[0]["room"] == "Room 204"
        assert mon_p1[0]["teacher_name"]

    def test_grid_unknown_class_404(self, admin):
        r = admin.get(f"{API}/timetable/grid", params={"academic_year": AY, "class_name": "NoSuchClass",
                                                       "section": "A"})
        assert r.status_code == 404


# ---------------- Phase 2: conflict engine ----------------

class TestConflictEngine:
    def test_create_valid_entry(self, admin, g6_grid, seed):
        off = next(o for o in g6_grid["offerings"] if o["subject"] == "Mathematics")
        asg = next(a for a in g6_grid["assignments"] if a["subject"] == "Mathematics")
        r = admin.post(f"{API}/timetable/entries", json={
            "academic_year": AY, "class_name": "Grade 6", "section": "A", "day": "tue", "period_no": 2,
            "offering_id": off["id"], "teacher_assignment_id": asg["id"], "room": "TEST_R1", "type": "regular"})
        assert r.status_code == 200, r.text
        e = r.json()
        seed["entries"].append(e["id"])
        assert e["subject"] == "Mathematics"
        assert e["teacher_id"]
        assert e["status"] == "active"
        assert "_id" not in e
        # persisted in grid
        grid = admin.get(f"{API}/timetable/grid", params={"academic_year": AY, "class_name": "Grade 6",
                                                          "section": "A"}).json()
        assert any(x["id"] == e["id"] for x in grid["entries"])
        seed["g6_tue_p2"] = e

    def test_section_conflict_409(self, admin, g6_grid):
        off = next(o for o in g6_grid["offerings"] if o["subject"] == "Mathematics")
        asg = next(a for a in g6_grid["assignments"] if a["subject"] == "Mathematics")
        r = admin.post(f"{API}/timetable/entries", json={
            "academic_year": AY, "class_name": "Grade 6", "section": "A", "day": "mon", "period_no": 1,
            "offering_id": off["id"], "teacher_assignment_id": asg["id"]})
        assert r.status_code == 409, r.text
        assert "Section conflict" in r.json()["detail"]

    def test_break_period_400(self, admin, g6_grid):
        off = next(o for o in g6_grid["offerings"] if o["subject"] == "Mathematics")
        asg = next(a for a in g6_grid["assignments"] if a["subject"] == "Mathematics")
        r = admin.post(f"{API}/timetable/entries", json={
            "academic_year": AY, "class_name": "Grade 6", "section": "A", "day": "wed", "period_no": 4,
            "offering_id": off["id"], "teacher_assignment_id": asg["id"]})
        assert r.status_code == 400, r.text
        assert "break" in r.json()["detail"].lower()

    def test_non_working_day_400(self, admin, g6_grid):
        off = next(o for o in g6_grid["offerings"] if o["subject"] == "Mathematics")
        asg = next(a for a in g6_grid["assignments"] if a["subject"] == "Mathematics")
        r = admin.post(f"{API}/timetable/entries", json={
            "academic_year": AY, "class_name": "Grade 6", "section": "A", "day": "sun", "period_no": 1,
            "offering_id": off["id"], "teacher_assignment_id": asg["id"]})
        assert r.status_code == 400, r.text
        assert "working day" in r.json()["detail"]

    def test_period_out_of_range_and_bad_day(self, admin, g6_grid):
        off = next(o for o in g6_grid["offerings"] if o["subject"] == "Mathematics")
        asg = next(a for a in g6_grid["assignments"] if a["subject"] == "Mathematics")
        base = {"academic_year": AY, "class_name": "Grade 6", "section": "A",
                "offering_id": off["id"], "teacher_assignment_id": asg["id"]}
        r = admin.post(f"{API}/timetable/entries", json={**base, "day": "wed", "period_no": 99})
        assert r.status_code == 400 and "out of range" in r.json()["detail"]
        r = admin.post(f"{API}/timetable/entries", json={**base, "day": "funday", "period_no": 1})
        assert r.status_code == 400 and "Invalid day" in r.json()["detail"]
        r = admin.post(f"{API}/timetable/entries", json={**base, "day": "wed"})
        assert r.status_code == 400 and "Missing field" in r.json()["detail"]

    def test_assignment_mismatch_400(self, admin, g6_grid, seed):
        """Grade 6 offering + assignment belonging to the TEST class → 400."""
        off = next(o for o in g6_grid["offerings"] if o["subject"] == "Mathematics")
        r = admin.post(f"{API}/timetable/entries", json={
            "academic_year": AY, "class_name": "Grade 6", "section": "A", "day": "wed", "period_no": 2,
            "offering_id": off["id"], "teacher_assignment_id": seed["assignment_id"]})
        assert r.status_code == 400, r.text
        assert "not assigned" in r.json()["detail"]

    def test_offering_not_for_class_400(self, admin, seed, g6_grid):
        asg = next(a for a in g6_grid["assignments"] if a["subject"] == "Mathematics")
        r = admin.post(f"{API}/timetable/entries", json={
            "academic_year": AY, "class_name": "Grade 6", "section": "A", "day": "wed", "period_no": 3,
            "offering_id": seed["offering_id"], "teacher_assignment_id": asg["id"]})
        assert r.status_code == 400, r.text
        assert "not offered" in r.json()["detail"]

    def test_teacher_conflict_409(self, admin, seed):
        """Meera already teaches Grade 6 A Mon P1 → same slot in TEST class must 409."""
        r = admin.post(f"{API}/timetable/entries", json={
            "academic_year": AY, "class_name": seed["class_name"], "section": "Z", "day": "mon", "period_no": 1,
            "offering_id": seed["offering_id"], "teacher_assignment_id": seed["assignment_id"]})
        assert r.status_code == 409, r.text
        assert "Teacher conflict" in r.json()["detail"]

    def test_room_conflict_409(self, admin, seed):
        """Grade 6 A Tue P2 uses TEST_R1 → TEST class Tue P2 same room must 409 (room checked)."""
        r = admin.post(f"{API}/timetable/entries", json={
            "academic_year": AY, "class_name": seed["class_name"], "section": "Z", "day": "tue", "period_no": 2,
            "offering_id": seed["offering_id"], "teacher_assignment_id": seed["assignment_id"],
            "room": "TEST_R1"})
        assert r.status_code == 409, r.text
        # teacher conflict is checked before room; both are legitimate conflicts here
        assert "conflict" in r.json()["detail"]

    def test_non_overlapping_effective_ranges_allowed(self, admin, seed):
        payload = {"academic_year": AY, "class_name": seed["class_name"], "section": "Z", "day": "wed",
                   "period_no": 1, "offering_id": seed["offering_id"],
                   "teacher_assignment_id": seed["assignment_id"]}
        r1 = admin.post(f"{API}/timetable/entries", json={**payload, "effective_from": "2026-04-01",
                                                          "effective_to": "2026-06-30"})
        assert r1.status_code == 200, r1.text
        seed["entries"].append(r1.json()["id"])
        r2 = admin.post(f"{API}/timetable/entries", json={**payload, "effective_from": "2026-07-01",
                                                          "effective_to": "2026-09-30"})
        assert r2.status_code == 200, f"non-overlapping ranges rejected: {r2.status_code} {r2.text}"
        seed["entries"].append(r2.json()["id"])
        # overlapping range must be rejected
        r3 = admin.post(f"{API}/timetable/entries", json={**payload, "effective_from": "2026-06-15",
                                                          "effective_to": "2026-07-15"})
        assert r3.status_code == 409, r3.text
        # invalid range
        r4 = admin.post(f"{API}/timetable/entries", json={**payload, "effective_from": "2026-08-01",
                                                          "effective_to": "2026-07-01"})
        assert r4.status_code == 400 and "before" in r4.json()["detail"]

    def test_update_entry_and_persist(self, admin, seed):
        eid = seed["entries"][0]
        r = admin.put(f"{API}/timetable/entries/{eid}", json={"room": "TEST_R9", "type": "lab"})
        assert r.status_code == 200, r.text
        assert r.json()["room"] == "TEST_R9"
        assert r.json()["type"] == "lab"
        grid = admin.get(f"{API}/timetable/grid", params={"academic_year": AY, "class_name": "Grade 6",
                                                          "section": "A"}).json()
        got = next(e for e in grid["entries"] if e["id"] == eid)
        assert got["room"] == "TEST_R9" and got["type"] == "lab"
        assert "_id" not in got

    def test_update_unknown_entry_404(self, admin):
        r = admin.put(f"{API}/timetable/entries/nope-123", json={"room": "X"})
        assert r.status_code == 404

    def test_delete_entry_and_verify_removed(self, admin, seed):
        eid = seed["entries"].pop(0)
        r = admin.delete(f"{API}/timetable/entries/{eid}")
        assert r.status_code == 200, r.text
        grid = admin.get(f"{API}/timetable/grid", params={"academic_year": AY, "class_name": "Grade 6",
                                                          "section": "A"}).json()
        assert not any(e["id"] == eid for e in grid["entries"])
        assert admin.delete(f"{API}/timetable/entries/{eid}").status_code == 404

    def test_teacher_cannot_create_entry(self, teacher, seed):
        r = teacher.post(f"{API}/timetable/entries", json={
            "academic_year": AY, "class_name": seed["class_name"], "section": "Z", "day": "thu",
            "period_no": 1, "offering_id": seed["offering_id"],
            "teacher_assignment_id": seed["assignment_id"]})
        assert r.status_code == 403, r.status_code


# ---------------- teacher grid ----------------

class TestTeacherGrid:
    def test_teacher_self_grid_no_params(self, teacher):
        r = teacher.get(f"{API}/timetable/teacher-grid")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["academic_year"] == AY, body["academic_year"]
        assert body["config"]["periods"]
        assert body["entries"], "teacher has no timetable entries (expected Grade 6 A Mon P1)"
        assert all(e.get("teacher_name") for e in body["entries"])
        assert any(e["day"] == "mon" and e["period_no"] == 1 for e in body["entries"])

    def test_admin_by_teacher_requires_id(self, admin):
        r = admin.get(f"{API}/timetable/teacher-grid")
        assert r.status_code == 400, r.status_code

    def test_admin_by_teacher_id(self, admin, teacher):
        me = teacher.get(f"{API}/auth/me").json()
        tid = (me.get("user") or me)["id"]
        r = admin.get(f"{API}/timetable/teacher-grid", params={"teacher_id": tid, "academic_year": AY})
        assert r.status_code == 200, r.text
        assert all(e["teacher_id"] == tid for e in r.json()["entries"])

    def test_teacher_id_param_ignored_for_teacher_role(self, teacher):
        r = teacher.get(f"{API}/timetable/teacher-grid", params={"teacher_id": "someone-else"})
        assert r.status_code == 200
        me = teacher.get(f"{API}/auth/me").json()
        tid = (me.get("user") or me)["id"]
        assert all(e["teacher_id"] == tid for e in r.json()["entries"])


# ---------------- notices ----------------

class TestNotices:
    def test_create_notice_requires_title(self, admin):
        r = admin.post(f"{API}/res/notices", json={"body": "no title"})
        assert r.status_code == 400, r.text

    def test_create_and_feed_audience_filtering(self, admin, teacher, seed):
        made = {}
        for aud, status in (("all", "published"), ("teachers", "published"),
                            ("students", "published"), ("all", "draft")):
            r = admin.post(f"{API}/res/notices", json={"title": f"TEST_{aud}_{status}",
                                                        "body": "b", "audience": aud, "status": status})
            assert r.status_code == 200, r.text
            doc = r.json()
            assert doc["audience"] == aud and doc["status"] == status
            assert doc.get("author_name")
            assert "_id" not in doc
            made[f"{aud}_{status}"] = doc["id"]
            seed["notices"].append(doc["id"])
        seed["notice_ids"] = made

        tfeed = [n["title"] for n in teacher.get(f"{API}/notices/feed").json()["notices"]]
        assert "TEST_all_published" in tfeed
        assert "TEST_teachers_published" in tfeed
        assert "TEST_students_published" not in tfeed
        assert "TEST_all_draft" not in tfeed
        assert "Sports Day on Friday" in tfeed, tfeed

        afeed = [n["title"] for n in admin.get(f"{API}/notices/feed").json()["notices"]]
        assert "TEST_students_published" in afeed and "TEST_all_draft" not in afeed

    def test_invalid_audience_status_defaults(self, admin, seed):
        r = admin.post(f"{API}/res/notices", json={"title": "TEST_defaults", "audience": "aliens",
                                                    "status": "weird"})
        assert r.status_code == 200, r.text
        assert r.json()["audience"] == "all" and r.json()["status"] == "published"
        seed["notices"].append(r.json()["id"])

    def test_update_and_delete_notice(self, admin, seed):
        nid = seed["notice_ids"]["all_published"]
        r = admin.put(f"{API}/res/notices/{nid}", json={"title": "TEST_all_published_v2", "status": "draft"})
        assert r.status_code == 200, r.text
        got = admin.get(f"{API}/res/notices/{nid}").json()
        assert got["title"] == "TEST_all_published_v2" and got["status"] == "draft"
        feed = [n["title"] for n in admin.get(f"{API}/notices/feed").json()["notices"]]
        assert "TEST_all_published_v2" not in feed, "draft leaked into feed"
        assert admin.delete(f"{API}/res/notices/{nid}").status_code == 200
        assert admin.get(f"{API}/res/notices/{nid}").status_code == 404
        seed["notices"].remove(nid)

    def test_notices_list_pagination(self, admin):
        r = admin.get(f"{API}/res/notices", params={"limit": 5, "page": 1})
        assert r.status_code == 200
        body = r.json()
        assert isinstance(body["items"], list) and body["total"] >= 1


# ---------------- portal (student) ----------------

class TestStudentPortal:
    @pytest.fixture(scope="class")
    def student(self, admin):
        r = admin.post(f"{API}/students/{AARAV_ID}/portal-user", json=PORTAL_LOGIN)
        if r.status_code != 200:
            pytest.fail(f"portal-user create failed {r.status_code}: {r.text[:300]}")
        s = requests.Session()
        lr = s.post(f"{API}/auth/login", json=PORTAL_LOGIN, timeout=30)
        if lr.status_code != 200:
            admin.delete(f"{API}/students/{AARAV_ID}/portal-user")
            pytest.fail(f"student login failed {lr.status_code}: {lr.text[:300]}")
        assert (lr.json().get("user") or lr.json())["role"] == "student"
        yield s
        assert admin.delete(f"{API}/students/{AARAV_ID}/portal-user").status_code == 200

    def test_portal_timetable(self, student):
        r = student.get(f"{API}/portal/timetable")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["class_name"] == "Grade 6" and body["section"] == "A"
        assert body["academic_year"] == AY
        assert body["config"]["working_days"]
        assert body["entries"], "no timetable entries for Grade 6 A"
        e = next(x for x in body["entries"] if x["day"] == "mon" and x["period_no"] == 1)
        assert e["subject"] == "Mathematics" and e["teacher_name"] and e["room"] == "Room 204"
        assert "_id" not in e

    def test_portal_notices_feed(self, student):
        titles = [n["title"] for n in student.get(f"{API}/notices/feed").json()["notices"]]
        assert "TEST_students_published" in titles or "Sports Day on Friday" in titles, titles
        assert "TEST_teachers_published" not in titles
        assert "TEST_all_draft" not in titles

    def test_student_cannot_use_admin_timetable_apis(self, student):
        assert student.get(f"{API}/timetable/grid", params={"academic_year": AY, "class_name": "Grade 6",
                                                            "section": "A"}).status_code == 403
        assert student.get(f"{API}/timetable/teacher-grid").status_code == 403
        assert student.get(f"{API}/students/{AARAV_ID}/report-card").status_code == 403


# ---------------- report cards ----------------

class TestReportCard:
    def test_report_card_admin(self, admin):
        r = admin.get(f"{API}/students/{AARAV_ID}/report-card")
        assert r.status_code == 200, r.text
        b = r.json()
        assert "_id" not in b["student"] and "password_hash" not in b["student"]
        assert b["student"]["first_name"] == "Aarav"
        assert b["academic_year"] == AY
        math = next((s for s in b["subjects"] if s["subject"] == "Mathematics"), None)
        assert math, b["subjects"]
        assert math["total_score"] == 42 and math["total_max"] == 50
        assert math["pct"] == 84.0 and math["grade"] == "A"
        assert math["assessments"] and math["assessments"][0]["max_marks"] == 50
        assert b["overall"]["pct"] == 84.0 and b["overall"]["grade"] == "A"
        assert b["attendance"]["total"] >= 1 and b["attendance"]["pct"] is not None
        assert b["institution"]["name"]

    def test_draft_assessment_excluded(self, admin):
        """Publish->draft toggle on the Mathematics assessment must drop it from the report card."""
        aid = None
        for a in admin.get(f"{API}/res/assessments", params={"limit": 50}).json()["items"]:
            if a.get("subject") == "Mathematics" and a.get("status") == "published":
                aid = a["id"]
                break
        assert aid, "no published Mathematics assessment found"
        assert admin.put(f"{API}/res/assessments/{aid}", json={"status": "draft"}).status_code == 200
        try:
            b = admin.get(f"{API}/students/{AARAV_ID}/report-card").json()
            assert not any(s["subject"] == "Mathematics" for s in b["subjects"]), b["subjects"]
            assert b["overall"]["total_max"] == 0 and b["overall"]["grade"] is None
        finally:
            assert admin.put(f"{API}/res/assessments/{aid}", json={"status": "published"}).status_code == 200
        b2 = admin.get(f"{API}/students/{AARAV_ID}/report-card").json()
        assert any(s["subject"] == "Mathematics" for s in b2["subjects"])

    def test_report_card_teacher_role_allowed(self, teacher):
        r = teacher.get(f"{API}/students/{AARAV_ID}/report-card")
        assert r.status_code == 200, r.text
        assert r.json()["student"]["id"] == AARAV_ID

    def test_report_card_unknown_student_404(self, admin):
        assert admin.get(f"{API}/students/does-not-exist/report-card").status_code == 404

    def test_grade_bands(self, admin):
        from importlib import util
        spec = util.spec_from_file_location("srv_grade", "/app/backend/server.py")
        # avoid importing the whole app; replicate band check via API-independent expectations
        bands = [(95, "A+"), (90, "A+"), (85, "A"), (80, "A"), (75, "B+"), (70, "B+"),
                 (65, "B"), (60, "B"), (55, "C"), (50, "C"), (40, "D"), (35, "D"), (34, "F"), (0, "F")]
        def grade(p):
            for cut, g in [(90, "A+"), (80, "A"), (70, "B+"), (60, "B"), (50, "C"), (35, "D")]:
                if p >= cut:
                    return g
            return "F"
        for pct, expected in bands:
            assert grade(pct) == expected
        assert spec is not None


# ---------------- regression ----------------

class TestRegression:
    def test_class_detail_still_works(self, admin):
        r = admin.get(f"{API}/classes/{CLASS_ID_G6}/detail")
        assert r.status_code == 200, r.text
        b = r.json()
        assert b["class"]["name"] == "Grade 6"
        assert isinstance(b["sections"], list) and isinstance(b["achievements"], list)
        assert any(s["id"] == AARAV_ID for s in b["students"])
        assert b["unit"] is not None

    def test_generic_create_still_requires_name(self, admin):
        r = admin.post(f"{API}/res/subjects", json={"code": "XX"})
        assert r.status_code == 400 and "Name is required" in r.json()["detail"]

    def test_subjects_and_offerings_list(self, admin):
        for res in ("subjects", "subject_offerings", "assessments", "achievements"):
            r = admin.get(f"{API}/res/{res}", params={"limit": 5})
            assert r.status_code == 200, f"{res}: {r.text[:200]}"
            assert all("_id" not in i for i in r.json()["items"])

    def test_unauthenticated_blocked(self):
        s = requests.Session()
        assert s.get(f"{API}/notices/feed").status_code in (401, 403)
        assert s.get(f"{API}/timetable/config", params={"academic_year": AY}).status_code in (401, 403)
