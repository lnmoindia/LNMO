"""Phase 7 — weekly subject requirements (timetable config layer). Throwaway DB.

Covers: requirement CRUD + read-back, over-total-slots 400 with numbers, consecutive validation,
multi-teacher + per-section map persistence, invalid teacher/section 400, unit-principal scope
(in-scope 200 / out-of-scope 403), and that existing single-teacher offerings are unaffected.
"""
import sys
import pytest

sys.path.insert(0, "/app/backend")
import server  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from pymongo import MongoClient  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

TEST_DB = "lnmo_phase7_test"
PA_EMAIL = server.os.environ["PLATFORM_ADMIN_EMAIL"].lower()
PA_PW = server.os.environ["PLATFORM_ADMIN_PASSWORD"]
BASE = "https://testserver"
_n = {"i": 0}


def _client():
    return TestClient(server.app, base_url=BASE)


class Sess:
    def __init__(self, c, tok):
        self._c = c
        self._h = {"Authorization": f"Bearer {tok}"}

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
    with _client() as C:
        def login(email, pw):
            r = C.post("/api/auth/login", json={"email": email, "password": pw})
            assert r.status_code == 200, r.text
            tok = r.cookies.get("access_token")
            C.cookies.clear()
            return Sess(C, tok)

        platform = login(PA_EMAIL, PA_PW)

        def new_school():
            _n["i"] += 1
            i = _n["i"]
            platform.post("/api/res/institutions", json={
                "name": f"S{i}", "slug": f"s7-{i}", "admin_email": f"a{i}@s7.test", "admin_password": "Admin@123"})
            return login(f"a{i}@s7.test", "Admin@123"), i

        yield {"login": login, "new_school": new_school, "C": C}
    MongoClient(server.mongo_url).drop_database(TEST_DB)


def _teacher(admin, i, name):
    return admin.post("/api/teachers", json={"name": name, "email": f"{name.lower()}{i}@s7.test",
                                             "password": "Teach@123", "status": "active"}).json()


def _scaffold(admin, grade="Grade 8", sections=("A",), subjects=("Mathematics", "Physics", "English")):
    """unit + class + sections + academic year + subject offerings. Returns (unit_id, class_id)."""
    u = admin.post("/api/res/academic_units", json={"name": "HS", "code": "HS", "status": "active"}).json()
    c = admin.post("/api/res/classes", json={"name": grade, "grade_level": "8", "academic_unit_id": u["id"], "status": "active"}).json()
    for s in sections:
        admin.post("/api/res/sections", json={"name": s, "class_name": grade, "status": "active"})
    admin.post("/api/res/academic_years", json={"name": "2026-27", "status": "active"})
    for subj in subjects:
        admin.post("/api/res/subjects", json={"name": subj, "status": "active"})
        admin.post("/api/res/subject_offerings", json={"subject": subj, "class_name": grade, "max_marks": 100, "status": "active"})
    return u["id"], c["id"]


def test_requirement_crud_and_readback(ctx):
    admin, i = ctx["new_school"]()
    _scaffold(admin)
    body = {"academic_year": "2026-27", "class_name": "Grade 8", "items": [
        {"subject": "Mathematics", "periods_per_week": 6, "consecutive_periods": 2, "must_be_consecutive": True},
        {"subject": "English", "periods_per_week": 4},
    ]}
    r = admin.put("/api/timetable/requirements", json=body)
    assert r.status_code == 200, r.text
    assert r.json()["total_required"] == 10
    # read back
    g = admin.get("/api/timetable/requirements", params={"academic_year": "2026-27", "class_name": "Grade 8"}).json()
    by = {it["subject"]: it for it in g["items"]}
    assert by["Mathematics"]["periods_per_week"] == 6 and by["Mathematics"]["consecutive_periods"] == 2
    assert by["Mathematics"]["must_be_consecutive"] is True and by["Mathematics"]["configured"]
    assert by["English"]["periods_per_week"] == 4 and by["Physics"]["configured"] is False
    assert g["slots"]["total"] == 35  # default 5 days x 7 teaching periods
    # update: drop English (ppw 0 omitted) → requirement removed
    admin.put("/api/timetable/requirements", json={"academic_year": "2026-27", "class_name": "Grade 8",
              "items": [{"subject": "Mathematics", "periods_per_week": 5, "consecutive_periods": 1}]})
    g2 = admin.get("/api/timetable/requirements", params={"academic_year": "2026-27", "class_name": "Grade 8"}).json()
    by2 = {it["subject"]: it for it in g2["items"]}
    assert by2["Mathematics"]["periods_per_week"] == 5 and by2["English"]["configured"] is False


def test_over_total_slots_400_with_numbers(ctx):
    admin, _ = ctx["new_school"]()
    _scaffold(admin)
    r = admin.put("/api/timetable/requirements", json={"academic_year": "2026-27", "class_name": "Grade 8",
                  "items": [{"subject": "Mathematics", "periods_per_week": 40, "consecutive_periods": 1}]})
    assert r.status_code == 400
    d = r.json()["detail"]
    assert "40" in d and "35" in d and "Reduce by 5" in d, d


def test_consecutive_validation(ctx):
    admin, _ = ctx["new_school"]()
    _scaffold(admin)
    base = {"academic_year": "2026-27", "class_name": "Grade 8"}
    # consecutive > periods_per_week
    r = admin.put("/api/timetable/requirements", json={**base, "items": [
        {"subject": "Mathematics", "periods_per_week": 2, "consecutive_periods": 3}]})
    assert r.status_code == 400 and "cannot exceed" in r.json()["detail"]
    # must_be_consecutive with consecutive == 1
    r = admin.put("/api/timetable/requirements", json={**base, "items": [
        {"subject": "Mathematics", "periods_per_week": 4, "consecutive_periods": 1, "must_be_consecutive": True}]})
    assert r.status_code == 400 and "must be consecutive" in r.json()["detail"].lower()
    # consecutive out of 1..3
    r = admin.put("/api/timetable/requirements", json={**base, "items": [
        {"subject": "Mathematics", "periods_per_week": 6, "consecutive_periods": 4}]})
    assert r.status_code == 400 and "1, 2 or 3" in r.json()["detail"]
    # periods_per_week < 1
    r = admin.put("/api/timetable/requirements", json={**base, "items": [
        {"subject": "Mathematics", "periods_per_week": 0}]})
    # ppw 0 is simply dropped client-side; server rejects if explicitly sent
    assert r.status_code == 400 and "at least 1" in r.json()["detail"]


def test_multi_teacher_and_section_map_persist(ctx):
    admin, i = ctx["new_school"]()
    _scaffold(admin, sections=("A", "B"))
    t1 = _teacher(admin, i, "Alpha")
    t2 = _teacher(admin, i, "Beta")
    t3 = _teacher(admin, i, "Gamma")
    body = {"academic_year": "2026-27", "class_name": "Grade 8", "items": [{
        "subject": "Mathematics", "periods_per_week": 6, "consecutive_periods": 2, "must_be_consecutive": True,
        "teacher_ids": [t1["id"], t2["id"], t3["id"]],
        "section_teachers": {"A": t1["id"], "B": t2["id"]},
    }]}
    r = admin.put("/api/timetable/requirements", json=body)
    assert r.status_code == 200, r.text
    m = {it["subject"]: it for it in r.json()["items"]}["Mathematics"]
    assert set(m["teacher_ids"]) == {t1["id"], t2["id"], t3["id"]}
    assert m["section_teachers"] == {"A": t1["id"], "B": t2["id"]}


def test_invalid_teacher_and_section_rejected(ctx):
    admin, i = ctx["new_school"]()
    _scaffold(admin, sections=("A",))
    t1 = _teacher(admin, i, "Dee")
    base = {"academic_year": "2026-27", "class_name": "Grade 8"}
    # non-existent teacher id in pool
    r = admin.put("/api/timetable/requirements", json={**base, "items": [
        {"subject": "Mathematics", "periods_per_week": 3, "teacher_ids": ["nope"]}]})
    assert r.status_code == 400 and "not an active teacher" in r.json()["detail"]
    # section that doesn't exist
    r = admin.put("/api/timetable/requirements", json={**base, "items": [
        {"subject": "Mathematics", "periods_per_week": 3, "teacher_ids": [t1["id"]],
         "section_teachers": {"Z": t1["id"]}}]})
    assert r.status_code == 400 and "section 'Z'" in r.json()["detail"]
    # section teacher not in the selected pool
    t2 = _teacher(admin, i, "Eff")
    r = admin.put("/api/timetable/requirements", json={**base, "items": [
        {"subject": "Mathematics", "periods_per_week": 3, "teacher_ids": [t1["id"]],
         "section_teachers": {"A": t2["id"]}}]})
    assert r.status_code == 400 and "must be one of" in r.json()["detail"]


def test_subject_not_offered_rejected(ctx):
    admin, _ = ctx["new_school"]()
    _scaffold(admin, subjects=("Mathematics",))
    r = admin.put("/api/timetable/requirements", json={"academic_year": "2026-27", "class_name": "Grade 8",
                  "items": [{"subject": "Biology", "periods_per_week": 3}]})
    assert r.status_code == 400 and "not offered" in r.json()["detail"]


def test_unit_principal_scope(ctx):
    admin, i = ctx["new_school"]()
    # two units, a class + offering in each
    ua = admin.post("/api/res/academic_units", json={"name": "LP", "code": "LP", "status": "active"}).json()
    ub = admin.post("/api/res/academic_units", json={"name": "HS", "code": "HS", "status": "active"}).json()
    admin.post("/api/res/academic_years", json={"name": "2026-27", "status": "active"})
    admin.post("/api/res/classes", json={"name": "Grade 1", "academic_unit_id": ua["id"], "status": "active"})
    admin.post("/api/res/classes", json={"name": "Grade 9", "academic_unit_id": ub["id"], "status": "active"})
    for grade in ("Grade 1", "Grade 9"):
        admin.post("/api/res/subjects", json={"name": "Mathematics", "status": "active"})
        admin.post("/api/res/subject_offerings", json={"subject": "Mathematics", "class_name": grade, "max_marks": 100, "status": "active"})
    t = _teacher(admin, i, "Prin")
    admin.post("/api/principals", json={"teacher_id": t["id"], "scope_type": "units", "unit_ids": [ua["id"]]})
    prin = ctx["login"](f"prin{i}@s7.test", "Teach@123")
    # in-scope read + write OK
    assert prin.get("/api/timetable/requirements", params={"academic_year": "2026-27", "class_name": "Grade 1"}).status_code == 200
    assert prin.put("/api/timetable/requirements", json={"academic_year": "2026-27", "class_name": "Grade 1",
                    "items": [{"subject": "Mathematics", "periods_per_week": 5}]}).status_code == 200
    # out-of-scope read + write blocked
    assert prin.get("/api/timetable/requirements", params={"academic_year": "2026-27", "class_name": "Grade 9"}).status_code == 403
    assert prin.put("/api/timetable/requirements", json={"academic_year": "2026-27", "class_name": "Grade 9",
                    "items": [{"subject": "Mathematics", "periods_per_week": 5}]}).status_code == 403
    # all-classes GET only returns in-scope classes
    allc = prin.get("/api/timetable/requirements", params={"academic_year": "2026-27"}).json()
    names = {c["class_name"] for c in allc["classes"]}
    assert names == {"Grade 1"}


def test_existing_single_teacher_offerings_unaffected(ctx):
    admin, i = ctx["new_school"]()
    _scaffold(admin)
    # a classic single teacher_assignment still works exactly as before
    t = _teacher(admin, i, "Solo")
    r = admin.post("/api/res/teacher_assignments", json={"teacher_email": t["email"],
                   "class_name": "Grade 8", "section": "A", "subject": "Mathematics", "status": "active"})
    assert r.status_code == 200, r.text
    rows = admin.get("/api/res/teacher_assignments", params={"limit": 50}).json()["items"]
    assert any(a["teacher_email"] == t["email"] and a["subject"] == "Mathematics" for a in rows)
    # and subject_offerings are untouched by requirements
    offs = admin.get("/api/res/subject_offerings", params={"limit": 50}).json()["items"]
    assert any(o["subject"] == "Mathematics" and o["class_name"] == "Grade 8" for o in offs)
