"""Phase 13 — Exam Timetable. Throwaway DB, API-driven (phase11/12 harness).

Covers: per-division configs persisted + validated; generator schedules all offered subjects with
no class slot-clash + spacing best-effort + unplaced reporting; per-section differing offerings;
postpone keeps original + conflict dialog data; mark-register auto-create idempotent; publish
visibility on the student portal; unit-principal scope + cross-division read-only.
"""
import sys
import pytest

sys.path.insert(0, "/app/backend")
import server  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from pymongo import MongoClient  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

TEST_DB = "lnmo_phase13_test"
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
    def delete(self, p, **k): return self._call("delete", p, **k)


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
            "name": "S13", "slug": "s13", "admin_email": "a@s13.test", "admin_password": "Admin@123"})
        admin = login("a@s13.test", "Admin@123")
        admin.post("/api/res/academic_years", json={"name": AY, "status": "active"})
        hs = admin.post("/api/res/academic_units", json={"name": "HS", "code": "HS", "status": "active"}).json()
        lp = admin.post("/api/res/academic_units", json={"name": "LP", "code": "LP", "status": "active"}).json()

        # Grade 8 (HS): sections A,B; subjects Maths, Science, Art (Art only in A -> per-section)
        admin.post("/api/res/classes", json={"name": "Grade 8", "academic_unit_id": hs["id"], "status": "active"})
        admin.post("/api/res/sections", json={"name": "A", "class_name": "Grade 8", "status": "active"})
        admin.post("/api/res/sections", json={"name": "B", "class_name": "Grade 8", "status": "active"})
        for s in ("Maths", "Science", "Art Education"):
            admin.post("/api/res/subjects", json={"name": s, "status": "active"})
        admin.post("/api/res/subject_offerings", json={"subject": "Maths", "class_name": "Grade 8", "section": "A", "max_marks": 80, "status": "active"})
        admin.post("/api/res/subject_offerings", json={"subject": "Maths", "class_name": "Grade 8", "section": "B", "max_marks": 80, "status": "active"})
        admin.post("/api/res/subject_offerings", json={"subject": "Science", "class_name": "Grade 8", "section": "A", "max_marks": 80, "status": "active"})
        admin.post("/api/res/subject_offerings", json={"subject": "Science", "class_name": "Grade 8", "section": "B", "max_marks": 80, "status": "active"})
        admin.post("/api/res/subject_offerings", json={"subject": "Art Education", "class_name": "Grade 8", "section": "A", "max_marks": 50, "status": "active"})

        # Grade 3 (LP): section A; subject EVS
        admin.post("/api/res/classes", json={"name": "Grade 3", "academic_unit_id": lp["id"], "status": "active"})
        admin.post("/api/res/sections", json={"name": "A", "class_name": "Grade 3", "status": "active"})
        admin.post("/api/res/subjects", json={"name": "EVS", "status": "active"})
        admin.post("/api/res/subject_offerings", json={"subject": "EVS", "class_name": "Grade 3", "section": "A", "max_marks": 100, "status": "active"})

        # A student in Grade 8 A for portal visibility
        st = admin.post("/api/res/students", json={"first_name": "Riya", "last_name": "K", "admission_no": "G8A1",
                                                   "class_name": "Grade 8", "section": "A", "status": "active"}).json()
        admin.post(f"/api/students/{st['id']}/portal-user", json={"email": "g8student@s13.test", "password": "Stud@123"})

        # Unit principal over LP only
        princ = admin.post("/api/teachers", json={"name": "LPHead", "email": "lphead@s13.test", "password": "Teach@123", "status": "active"}).json()
        admin.post("/api/principals", json={"teacher_id": princ["id"], "scope_type": "units", "unit_ids": [lp["id"]], "designation": "principal"})

        yield {"admin": admin, "login": login, "db": mon, "hs": hs["id"], "lp": lp["id"], "student_id": st["id"]}
    MongoClient(server.mongo_url).drop_database(TEST_DB)


def _hs_cfg(ctx):
    return {"academic_unit_id": ctx["hs"], "date_start": "2026-03-02", "date_end": "2026-03-06",
            "slots_per_day": [{"start": "09:30", "end": "11:00", "label": "AM"}, {"start": "12:00", "end": "13:30", "label": "PM"}]}


def _lp_cfg(ctx):
    return {"academic_unit_id": ctx["lp"], "date_start": "2026-03-10", "date_end": "2026-03-12",
            "slots_per_day": [{"start": "10:00", "end": "11:00"}]}


def test_create_validates_and_persists_configs(ctx):
    admin = ctx["admin"]
    # end before start -> 400
    bad = admin.post("/api/exams", json={"name": "Bad", "type": "model",
                                         "division_configs": [{"academic_unit_id": ctx["hs"], "date_start": "2026-03-06", "date_end": "2026-03-02", "slots_per_day": [{"start": "09:00", "end": "10:00"}]}]})
    assert bad.status_code == 400
    # slot end<=start -> 400
    bad2 = admin.post("/api/exams", json={"name": "Bad2", "type": "model",
                                          "division_configs": [{"academic_unit_id": ctx["hs"], "date_start": "2026-03-02", "date_end": "2026-03-06", "slots_per_day": [{"start": "11:00", "end": "11:00"}]}]})
    assert bad2.status_code == 400
    # no divisions -> 400
    assert admin.post("/api/exams", json={"name": "Bad3", "type": "model", "division_configs": []}).status_code == 400
    # good two-division create
    r = admin.post("/api/exams", json={"name": "Model Exam 2026", "type": "model", "division_configs": [_hs_cfg(ctx), _lp_cfg(ctx)]})
    assert r.status_code == 200, r.text
    exam = r.json()["exam"]
    assert exam["status"] == "draft" and len(exam["division_configs"]) == 2
    ctx["exam_id"] = exam["id"]


def test_generate_schedules_all_offered_no_clash(ctx):
    admin = ctx["admin"]
    r = admin.post(f"/api/exams/{ctx['exam_id']}/generate", json={"create_registers": True})
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["unplaced"] == [], res["unplaced"]
    entries = admin.get(f"/api/exams/{ctx['exam_id']}").json()["entries"]
    # Grade 8: Maths & Science offered to all sections -> whole-class (section ""); Art only A -> per-section A
    g8 = [e for e in entries if e["class_name"] == "Grade 8"]
    subj_scope = {(e["subject"], e["section"]) for e in g8}
    assert ("Maths", "") in subj_scope and ("Science", "") in subj_scope and ("Art Education", "A") in subj_scope
    # Grade 3 EVS scheduled within LP window
    g3 = [e for e in entries if e["class_name"] == "Grade 3"]
    assert len(g3) == 1 and g3[0]["subject"] == "EVS"
    assert "2026-03-10" <= g3[0]["date"] <= "2026-03-12"
    # no (section, date, slot) clash for Grade 8 section A (expand whole-class to A)
    seen = set()
    for e in g8:
        secs = ["A", "B"] if e["section"] == "" else [e["section"]]
        for s in secs:
            key = (s, e["date"], e["slot_index"])
            assert key not in seen, f"clash at {key}"
            seen.add(key)
    # HS entries within HS window
    for e in g8:
        assert "2026-03-02" <= e["date"] <= "2026-03-06"


def test_mark_registers_idempotent(ctx):
    admin, db = ctx["admin"], ctx["db"]
    n1 = db.assessments.count_documents({"exam_id": ctx["exam_id"]})
    assert n1 >= 4  # Maths, Science, Art(A), EVS
    # names link the exam
    a = db.assessments.find_one({"exam_id": ctx["exam_id"], "subject": "Maths"})
    assert a and a["name"].startswith("Model Exam 2026 —") and a["status"] == "draft"
    # on-demand re-create is a no-op (idempotent)
    r = admin.post(f"/api/exams/{ctx['exam_id']}/registers")
    assert r.json()["registers_created"] == 0
    assert db.assessments.count_documents({"exam_id": ctx["exam_id"]}) == n1


def test_postpone_keeps_original_and_conflict_data(ctx):
    admin = ctx["admin"]
    entries = admin.get(f"/api/exams/{ctx['exam_id']}").json()["entries"]
    maths = next(e for e in entries if e["class_name"] == "Grade 8" and e["subject"] == "Maths")
    science = next(e for e in entries if e["class_name"] == "Grade 8" and e["subject"] == "Science")
    # move Maths onto Science's slot -> class double-booked conflict (no override)
    clash = admin.post(f"/api/exam-entries/{maths['id']}/move", json={"date": science["date"], "slot_index": science["slot_index"]})
    assert clash.json()["ok"] is False
    assert any(c["type"] == "class_double_booked" for c in clash.json()["conflicts"])
    # date outside HS window -> conflict
    out = admin.post(f"/api/exam-entries/{maths['id']}/move", json={"date": "2026-03-20", "slot_index": 0})
    assert any(c["type"] == "date_out_of_range" for c in out.json()["conflicts"])
    # valid free move -> postponed + original kept
    ok = admin.post(f"/api/exam-entries/{maths['id']}/move", json={"date": "2026-03-05", "slot_index": 1})
    assert ok.json()["ok"] is True
    moved = next(e for e in admin.get(f"/api/exams/{ctx['exam_id']}").json()["entries"] if e["id"] == maths["id"])
    assert moved["status"] == "postponed" and moved["original_date"] == maths["date"] and moved["date"] == "2026-03-05"


def test_publish_visibility_on_portal(ctx):
    admin = ctx["admin"]
    student = ctx["login"]("g8student@s13.test", "Stud@123")
    assert student.get("/api/portal/exams").json()["exams"] == []  # draft hidden
    assert admin.post(f"/api/exams/{ctx['exam_id']}/publish").status_code == 200
    rows = student.get("/api/portal/exams").json()["exams"]
    assert len(rows) >= 2  # Grade 8 A sees Maths, Science, Art
    subs = {r["subject"] for r in rows}
    assert "Maths" in subs and "Art Education" in subs
    # sorted by date
    dates = [r["date"] for r in rows]
    assert dates == sorted(dates)


def test_unit_principal_scope(ctx):
    admin = ctx["admin"]
    lphead = ctx["login"]("lphead@s13.test", "Teach@123")
    # LP principal can create an LP-only exam
    good = lphead.post("/api/exams", json={"name": "LP Unit Test", "type": "unit", "division_configs": [_lp_cfg(ctx)]})
    assert good.status_code == 200, good.text
    # LP principal CANNOT create an HS exam (out of scope)
    bad = lphead.post("/api/exams", json={"name": "HS Sneak", "type": "unit", "division_configs": [_hs_cfg(ctx)]})
    assert bad.status_code == 403
    # The cross-division Model Exam is visible but read-only (editable False); editing it is blocked
    listing = {e["name"]: e for e in lphead.get("/api/exams").json()["exams"]}
    assert "Model Exam 2026" in listing and listing["Model Exam 2026"]["editable"] is False
    assert lphead.post(f"/api/exams/{ctx['exam_id']}/generate", json={"create_registers": False}).status_code == 403
