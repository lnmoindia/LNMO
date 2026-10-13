"""Phase 14 — Marks scope + result publishing. Throwaway DB, API-driven (phase11-13 harness).

Covers: subject-teacher allowed / unrelated teacher 403 / class-teacher allowed; post-publish
teacher edit locked; principal correction writes old→new audit shown in change history; unit
principal publishes in-scope exam results (403 out-of-scope); teacher publish 403; student portal
shows result only after publish; report card excludes unpublished; move-back status reset.
"""
import sys
import pytest

sys.path.insert(0, "/app/backend")
import server  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from pymongo import MongoClient  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

TEST_DB = "lnmo_phase14_test"
PA_EMAIL = server.os.environ["PLATFORM_ADMIN_EMAIL"].lower()
PA_PW = server.os.environ["PLATFORM_ADMIN_PASSWORD"]
BASE = "https://testserver"
AY = "2026-27"


def _client():
    return TestClient(server.app, base_url=BASE)


class Sess:
    def __init__(self, c, tok):
        self._c, self._h = c, {"Authorization": f"Bearer {tok}"}

    def _call(self, m, p, **k):
        self._c.cookies.clear()
        return getattr(self._c, m)(p, headers={**self._h, **k.pop("headers", {})}, **k)

    def get(self, p, **k): return self._call("get", p, **k)
    def post(self, p, **k): return self._call("post", p, **k)
    def put(self, p, **k): return self._call("put", p, **k)


@pytest.fixture(scope="module")
def ctx():
    async def _init():
        server.client = AsyncIOMotorClient(server.mongo_url)
        server.db = server.client[TEST_DB]
    server.app.router.on_startup.insert(0, _init)
    MongoClient(server.mongo_url).drop_database(TEST_DB)
    mon = MongoClient(server.mongo_url)[TEST_DB]
    with _client() as C:
        def login(email, pw):
            r = C.post("/api/auth/login", json={"email": email, "password": pw})
            assert r.status_code == 200, r.text
            tok = r.cookies.get("access_token")
            C.cookies.clear()
            return Sess(C, tok)

        platform = login(PA_EMAIL, PA_PW)
        platform.post("/api/res/institutions", json={
            "name": "S14", "slug": "s14", "admin_email": "a@s14.test", "admin_password": "Admin@123"})
        admin = login("a@s14.test", "Admin@123")
        admin.post("/api/res/academic_years", json={"name": AY, "status": "active"})
        hs = admin.post("/api/res/academic_units", json={"name": "HS", "code": "HS", "status": "active"}).json()
        lp = admin.post("/api/res/academic_units", json={"name": "LP", "code": "LP", "status": "active"}).json()

        def teacher(n):
            return admin.post("/api/teachers", json={"name": n, "email": f"{n.lower()}@s14.test", "password": "Teach@123", "status": "active"}).json()
        tt = {n: teacher(n) for n in ("Manoj", "Random", "ClassT", "LPHead")}

        # Grade 8 (HS) section A. Maths taught by Manoj; ClassT is class teacher of A.
        admin.post("/api/res/classes", json={"name": "Grade 8", "academic_unit_id": hs["id"], "status": "active"})
        secA = admin.post("/api/res/sections", json={"name": "A", "class_name": "Grade 8", "status": "active"}).json()
        admin.post("/api/res/subjects", json={"name": "Maths", "status": "active"})
        admin.post("/api/res/subjects", json={"name": "Science", "status": "active"})
        admin.post("/api/res/subject_offerings", json={"subject": "Maths", "class_name": "Grade 8", "section": "A", "max_marks": 100, "status": "active"})
        admin.post("/api/res/subject_offerings", json={"subject": "Science", "class_name": "Grade 8", "section": "A", "max_marks": 100, "status": "active"})
        admin.post("/api/res/teacher_assignments", json={"teacher_email": "manoj@s14.test", "class_name": "Grade 8", "section": "A", "subject": "Maths", "status": "active"})
        admin.post("/api/res/teacher_assignments", json={"teacher_email": "random@s14.test", "class_name": "Grade 8", "section": "A", "subject": "Science", "status": "active"})
        admin.put(f"/api/sections/{secA['id']}", json={})
        mon.sections.update_one({"id": secA["id"]}, {"$set": {"class_teacher_id": tt["ClassT"]["id"], "class_teacher": "ClassT"}})

        # students
        s1 = admin.post("/api/res/students", json={"first_name": "Riya", "last_name": "K", "admission_no": "G8A1", "class_name": "Grade 8", "section": "A", "status": "active"}).json()
        admin.post("/api/res/students", json={"first_name": "Sam", "last_name": "P", "admission_no": "G8A2", "class_name": "Grade 8", "section": "A", "status": "active"})
        admin.post(f"/api/students/{s1['id']}/portal-user", json={"email": "g8student@s14.test", "password": "Stud@123"})

        # LP principal
        admin.post("/api/principals", json={"teacher_id": tt["LPHead"]["id"], "scope_type": "units", "unit_ids": [lp["id"]], "designation": "principal"})

        # A Maths assessment for Grade 8 A
        asmt = admin.post("/api/res/assessments", json={"name": "Maths Test", "subject": "Maths", "class_name": "Grade 8", "section": "A", "max_marks": 100, "status": "draft"}).json()

        yield {"admin": admin, "login": login, "db": mon, "tt": tt, "hs": hs["id"], "lp": lp["id"],
               "student_id": s1["id"], "asmt_id": asmt["id"]}
    MongoClient(server.mongo_url).drop_database(TEST_DB)


def test_marks_entry_scope(ctx):
    aid = ctx["asmt_id"]
    manoj = ctx["login"]("manoj@s14.test", "Teach@123")       # subject teacher for Maths
    random_t = ctx["login"]("random@s14.test", "Teach@123")   # Science teacher, unrelated to Maths
    classt = ctx["login"]("classt@s14.test", "Teach@123")     # class teacher of A
    assert manoj.get(f"/api/assessments/{aid}/marks").status_code == 200
    assert random_t.get(f"/api/assessments/{aid}/marks").status_code == 403
    assert classt.get(f"/api/assessments/{aid}/marks").status_code == 200
    # subject teacher can save
    r = manoj.post(f"/api/assessments/{aid}/marks", json={"entries": [{"student_id": ctx["student_id"], "score": 55, "status": "present"}]})
    assert r.status_code == 200, r.text
    # unrelated teacher cannot save
    assert random_t.post(f"/api/assessments/{aid}/marks", json={"entries": []}).status_code == 403


def test_post_publish_teacher_locked_principal_corrects(ctx):
    aid, admin = ctx["asmt_id"], ctx["admin"]
    manoj = ctx["login"]("manoj@s14.test", "Teach@123")
    # publish (admin)
    assert admin.post(f"/api/assessments/{aid}/publish", json={"publish": True}).status_code == 200
    # teacher locked out of saving after publish
    locked = manoj.post(f"/api/assessments/{aid}/marks", json={"entries": [{"student_id": ctx["student_id"], "score": 60, "status": "present"}]})
    assert locked.status_code == 403
    assert manoj.get(f"/api/assessments/{aid}/marks").json()["locked"] is True
    # admin corrects the published mark 55 -> 88
    corr = admin.post(f"/api/assessments/{aid}/marks", json={"entries": [{"student_id": ctx["student_id"], "score": 88, "status": "present"}]})
    assert corr.status_code == 200 and corr.json()["changes"] == 1
    # change history shows old->new correction
    hist = admin.get(f"/api/assessments/{aid}/history").json()["history"]
    corr_rows = [h for h in hist if h["is_correction"] and h["new_score"] == 88]
    assert corr_rows and corr_rows[0]["old_score"] == 55 and corr_rows[0]["editor_role"] == "institution_admin"
    # audit trail recorded a correction
    assert ctx["db"].audit_logs.find_one({"action": "correct", "resource": "marks", "entity_id": aid})


def test_teacher_cannot_publish(ctx):
    manoj = ctx["login"]("manoj@s14.test", "Teach@123")
    r = manoj.post(f"/api/assessments/{ctx['asmt_id']}/publish", json={"publish": True})
    assert r.status_code == 403


def test_unit_principal_publish_scope(ctx):
    admin, db = ctx["admin"], ctx["db"]
    lphead = ctx["login"]("lphead@s14.test", "Teach@123")
    # build a cross-division exam-linked register set: an LP assessment + the HS Maths one
    admin.post("/api/res/classes", json={"name": "Grade 3", "academic_unit_id": ctx["lp"], "status": "active"})
    admin.post("/api/res/sections", json={"name": "A", "class_name": "Grade 3", "status": "active"})
    admin.post("/api/res/subjects", json={"name": "EVS", "status": "active"})
    exam = admin.post("/api/exams", json={"name": "Term 1", "type": "term", "division_configs": [
        {"academic_unit_id": ctx["hs"], "date_start": "2026-04-01", "date_end": "2026-04-03", "slots_per_day": [{"start": "09:00", "end": "10:00"}]},
        {"academic_unit_id": ctx["lp"], "date_start": "2026-04-01", "date_end": "2026-04-03", "slots_per_day": [{"start": "09:00", "end": "10:00"}]},
    ]}).json()["exam"]
    # manually link two assessments to this exam (one HS, one LP)
    import uuid
    iid = exam["institution_id"]
    for cn, subj in [("Grade 8", "Maths"), ("Grade 3", "EVS")]:
        db.assessments.insert_one({"id": str(uuid.uuid4()), "institution_id": iid,
                                   "exam_id": exam["id"], "name": f"Term 1 — {subj}", "subject": subj,
                                   "class_name": cn, "section": "A", "max_marks": 100, "status": "draft", "created_at": "2026-01-01T00:00:00+00:00"})
    # LP principal bulk-publishes exam results: only the LP (Grade 3) register flips, HS skipped
    res = lphead.post(f"/api/exams/{exam['id']}/publish-results", json={"publish": True})
    assert res.status_code == 200, res.text
    assert res.json()["updated"] == 1 and res.json()["skipped"] == 1
    assert db.assessments.find_one({"exam_id": exam["id"], "class_name": "Grade 3"})["status"] == "published"
    assert db.assessments.find_one({"exam_id": exam["id"], "class_name": "Grade 8"})["status"] == "draft"
    # naming an out-of-scope class explicitly -> 403
    assert lphead.post(f"/api/exams/{exam['id']}/publish-results", json={"publish": True, "class_name": "Grade 8"}).status_code == 403


def test_student_portal_only_after_publish(ctx):
    # Maths Test was published in an earlier test; student should now see the Maths result
    student = ctx["login"]("g8student@s14.test", "Stud@123")
    me = student.get("/api/portal/me").json()
    subs = {r["subject"] for r in me.get("results", [])}
    assert "Maths" in subs
    # report card includes only published assessments
    rc = ctx["admin"].get(f"/api/students/{ctx['student_id']}/report-card").json()
    rc_subs = {s["subject"] for s in rc["subjects"]}
    assert "Maths" in rc_subs and "Science" not in rc_subs  # Science never published


def test_move_back_resets_status(ctx):
    admin = ctx["admin"]
    exam = admin.post("/api/exams", json={"name": "Move Test", "type": "unit", "division_configs": [
        {"academic_unit_id": ctx["hs"], "date_start": "2026-05-04", "date_end": "2026-05-08", "slots_per_day": [{"start": "09:00", "end": "10:00"}, {"start": "11:00", "end": "12:00"}]},
    ]}).json()["exam"]
    admin.post(f"/api/exams/{exam['id']}/generate", json={"create_registers": False})
    e = admin.get(f"/api/exams/{exam['id']}").json()["entries"][0]
    orig_date, orig_slot = e["date"], e["slot_index"]
    # move away -> postponed + original kept
    admin.post(f"/api/exam-entries/{e['id']}/move", json={"date": "2026-05-08", "slot_index": 1, "override": True})
    moved = next(x for x in admin.get(f"/api/exams/{exam['id']}").json()["entries"] if x["id"] == e["id"])
    assert moved["status"] == "postponed" and moved["original_date"] == orig_date
    # move BACK to original -> status reset to scheduled, trail cleared
    admin.post(f"/api/exam-entries/{e['id']}/move", json={"date": orig_date, "slot_index": orig_slot, "override": True})
    back = next(x for x in admin.get(f"/api/exams/{exam['id']}").json()["entries"] if x["id"] == e["id"])
    assert back["status"] == "scheduled" and back["original_date"] is None and back["original_slot"] is None
