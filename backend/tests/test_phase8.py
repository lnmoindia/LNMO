"""Phase 8 — grade-grid views + manual editing with multi-conflict warnings. Throwaway DB."""
import sys
import pytest

sys.path.insert(0, "/app/backend")
import server  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from pymongo import MongoClient  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

TEST_DB = "lnmo_phase8_test"
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
                "name": f"S{i}", "slug": f"s8-{i}", "admin_email": f"a{i}@s8.test", "admin_password": "Admin@123"})
            return login(f"a{i}@s8.test", "Admin@123"), i

        yield {"login": login, "new_school": new_school, "C": C}
    MongoClient(server.mongo_url).drop_database(TEST_DB)


def _teacher(admin, i, name):
    return admin.post("/api/teachers", json={"name": name, "email": f"{name.lower()}{i}@s8.test",
                                             "password": "Teach@123", "status": "active"}).json()


def _grade(admin, grade, unit_id, subjects=("Mathematics", "Physics")):
    admin.post("/api/res/classes", json={"name": grade, "academic_unit_id": unit_id, "status": "active"})
    admin.post("/api/res/sections", json={"name": "A", "class_name": grade, "status": "active"})
    for s in subjects:
        admin.post("/api/res/subjects", json={"name": s, "status": "active"})
        admin.post("/api/res/subject_offerings", json={"subject": s, "class_name": grade, "max_marks": 100, "status": "active"})


def _setup(admin):
    u = admin.post("/api/res/academic_units", json={"name": "HS", "code": "HS", "status": "active"}).json()
    admin.post("/api/res/academic_years", json={"name": "2026-27", "status": "active"})
    _grade(admin, "Grade 8", u["id"])
    _grade(admin, "Grade 9", u["id"])
    return u["id"]


def _place(admin, grade, day, pno, subject, teacher_id="", override=False, section="A"):
    return admin.post("/api/timetable/place", json={
        "academic_year": "2026-27", "class_name": grade, "section": section, "day": day,
        "period_no": pno, "subject": subject, "teacher_id": teacher_id, "override": override})


def test_conflict_check_lists_all(ctx):
    admin, i = ctx["new_school"]()
    _setup(admin)
    t = _teacher(admin, i, "Tee")
    # Grade 8 Maths Mon P1 with Tee (Tee isn't in a pool yet → soft warning, save anyway)
    r = _place(admin, "Grade 8", "mon", 1, "Mathematics", t["id"], override=True)
    assert r.json()["ok"] is True, r.text
    # Now propose Grade 9 Physics Mon P1 with the SAME teacher (double-book) who is also not in Physics pool
    chk = admin.post("/api/timetable/entries/check", json={
        "academic_year": "2026-27", "class_name": "Grade 9", "section": "A", "day": "mon",
        "period_no": 1, "subject": "Physics", "teacher_id": t["id"]}).json()
    types = {c["type"] for c in chk["conflicts"]}
    assert "teacher" in types and "pool" in types, chk
    # occupy Grade 9 A Mon P1 with Maths first, then a section conflict appears for a different entry
    _place(admin, "Grade 9", "mon", 1, "Mathematics")
    chk2 = admin.post("/api/timetable/entries/check", json={
        "academic_year": "2026-27", "class_name": "Grade 9", "section": "A", "day": "mon",
        "period_no": 1, "subject": "Physics", "teacher_id": t["id"]}).json()
    # placing a NEW subject in an occupied slot (entry_id omitted) → section conflict also listed
    assert "section" in {c["type"] for c in chk2["conflicts"]}, chk2


def test_consecutive_conflict(ctx):
    admin, i = ctx["new_school"]()
    _setup(admin)
    # Maths must_be_consecutive 2
    admin.put("/api/timetable/requirements", json={"academic_year": "2026-27", "class_name": "Grade 8",
              "items": [{"subject": "Mathematics", "periods_per_week": 4, "consecutive_periods": 2, "must_be_consecutive": True}]})
    r = _place(admin, "Grade 8", "mon", 1, "Mathematics")  # isolated → consecutive conflict
    assert r.json()["ok"] is False
    assert "consecutive" in {c["type"] for c in r.json()["conflicts"]}
    # override to persist, then P2 adjacent is clean
    assert _place(admin, "Grade 8", "mon", 1, "Mathematics", override=True).json()["ok"] is True
    r2 = _place(admin, "Grade 8", "mon", 2, "Mathematics")
    assert r2.json()["ok"] is True and r2.json()["conflicts"] == []


def test_save_anyway_override_persists_and_audits(ctx):
    admin, i = ctx["new_school"]()
    _setup(admin)
    t = _teacher(admin, i, "Dub")
    _place(admin, "Grade 8", "tue", 2, "Mathematics", t["id"], override=True)
    # double-book same teacher on Grade 9 tue P2 → blocked, then override
    blocked = _place(admin, "Grade 9", "tue", 2, "Physics", t["id"])
    assert blocked.json()["ok"] is False and "teacher" in {c["type"] for c in blocked.json()["conflicts"]}
    ok = _place(admin, "Grade 9", "tue", 2, "Physics", t["id"], override=True)
    assert ok.json()["ok"] is True
    assert len(ok.json()["entry"]["conflict_flags"]) >= 1  # flagged
    iid = admin.get("/api/auth/me").json()["institution_id"]
    tdb = MongoClient(server.mongo_url)[TEST_DB]
    assert tdb.audit_logs.count_documents({"institution_id": iid, "action": "override", "resource": "timetable_entries"}) >= 1


def test_move_and_swap(ctx):
    admin, i = ctx["new_school"]()
    _setup(admin)
    e1 = _place(admin, "Grade 8", "wed", 1, "Mathematics").json()["entry"]
    # move to empty wed P3
    mv = admin.post("/api/timetable/move", json={"entry_id": e1["id"], "to_day": "wed", "to_period_no": 3})
    assert mv.json()["ok"] is True and mv.json()["swap"] is False
    # place another at wed P5, then swap P3<->P5
    e2 = _place(admin, "Grade 8", "wed", 5, "Physics").json()["entry"]
    sw = admin.post("/api/timetable/move", json={"entry_id": e1["id"], "to_day": "wed", "to_period_no": 5})
    assert sw.json()["ok"] is True and sw.json()["swap"] is True
    grid = admin.get("/api/timetable/grid", params={"academic_year": "2026-27", "class_name": "Grade 8", "section": "A"}).json()
    at = {(x["day"], x["period_no"]): x["subject"] for x in grid["entries"]}
    assert at[("wed", 5)] == "Mathematics" and at[("wed", 3)] == "Physics"


def test_teacher_view_free_periods(ctx):
    admin, i = ctx["new_school"]()
    _setup(admin)
    t = _teacher(admin, i, "Viewy")
    _place(admin, "Grade 8", "mon", 1, "Mathematics", t["id"], override=True)
    tv = admin.get(f"/api/timetable/teacher/{t['id']}", params={"academic_year": "2026-27"}).json()
    mon = next(d for d in tv["schedule"] if d["day"] == "mon")
    p1 = next(p for p in mon["periods"] if p["period_no"] == 1)
    p2 = next(p for p in mon["periods"] if p["period_no"] == 2)
    assert p1["entry"] and p1["free"] is False
    assert p2["entry"] is None and p2["free"] is True
    # teacher can view own, not others
    teacher_sess = ctx["login"](t["email"], "Teach@123")
    assert teacher_sess.get(f"/api/timetable/teacher/{t['id']}").status_code == 200
    other = _teacher(admin, i, "Zed")
    assert teacher_sess.get(f"/api/timetable/teacher/{other['id']}").status_code == 403


def test_unit_principal_scope_on_views_and_edit(ctx):
    admin, i = ctx["new_school"]()
    ua = admin.post("/api/res/academic_units", json={"name": "LP", "code": "LP", "status": "active"}).json()
    ub = admin.post("/api/res/academic_units", json={"name": "UP", "code": "UP", "status": "active"}).json()
    admin.post("/api/res/academic_years", json={"name": "2026-27", "status": "active"})
    _grade(admin, "Grade 1", ua["id"])
    _grade(admin, "Grade 6", ub["id"])
    t = _teacher(admin, i, "Prin")
    admin.post("/api/principals", json={"teacher_id": t["id"], "scope_type": "units", "unit_ids": [ua["id"]]})
    prin = ctx["login"](f"prin{i}@s8.test", "Teach@123")
    # in-scope place OK
    assert prin.post("/api/timetable/place", json={"academic_year": "2026-27", "class_name": "Grade 1",
           "section": "A", "day": "mon", "period_no": 1, "subject": "Mathematics"}).status_code == 200
    # out-of-scope place blocked (403)
    assert prin.post("/api/timetable/place", json={"academic_year": "2026-27", "class_name": "Grade 6",
           "section": "A", "day": "mon", "period_no": 1, "subject": "Mathematics"}).status_code == 403
    # day view only shows in-scope rows
    day = prin.get("/api/timetable/day", params={"day": "mon", "academic_year": "2026-27"}).json()
    assert {r["class_name"] for r in day["rows"]} == {"Grade 1"}
    # subject view scoped too
    admin.post("/api/timetable/place", json={"academic_year": "2026-27", "class_name": "Grade 6",
               "section": "A", "day": "tue", "period_no": 1, "subject": "Mathematics"})
    subj = prin.get("/api/timetable/subject", params={"subject": "Mathematics", "academic_year": "2026-27"}).json()
    assert {e["class_name"] for e in subj["entries"]} == {"Grade 1"}


def test_existing_builder_entry_path_still_works(ctx):
    admin, i = ctx["new_school"]()
    _setup(admin)
    t = _teacher(admin, i, "Builder")
    # the strict manual builder requires offering_id + teacher_assignment_id
    off = admin.get("/api/res/subject_offerings", params={"limit": 50}).json()["items"]
    moff = next(o for o in off if o["class_name"] == "Grade 8" and o["subject"] == "Mathematics")
    asg = admin.post("/api/res/teacher_assignments", json={"teacher_email": t["email"],
          "class_name": "Grade 8", "section": "A", "subject": "Mathematics", "status": "active"}).json()
    r = admin.post("/api/timetable/entries", json={"academic_year": "2026-27", "class_name": "Grade 8",
        "section": "A", "day": "fri", "period_no": 1, "offering_id": moff["id"], "teacher_assignment_id": asg["id"]})
    assert r.status_code == 200, r.text
    assert r.json()["subject"] == "Mathematics" and r.json()["teacher_name"] == t["name"]
