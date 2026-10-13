"""Phase 9 — best-effort generation + review→approve→publish. Throwaway DB."""
import sys
import pytest

sys.path.insert(0, "/app/backend")
import server  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from pymongo import MongoClient  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

TEST_DB = "lnmo_phase9_test"
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
                "name": f"S{i}", "slug": f"s9-{i}", "admin_email": f"a{i}@s9.test", "admin_password": "Admin@123"})
            return login(f"a{i}@s9.test", "Admin@123"), i

        yield {"login": login, "new_school": new_school, "C": C}
    MongoClient(server.mongo_url).drop_database(TEST_DB)


def _teacher(admin, i, name):
    return admin.post("/api/teachers", json={"name": name, "email": f"{name.lower()}{i}@s9.test",
                                             "password": "Teach@123", "status": "active"}).json()


def _grade(admin, grade, unit_id, subjects=("Mathematics", "Physics")):
    admin.post("/api/res/classes", json={"name": grade, "academic_unit_id": unit_id, "status": "active"})
    admin.post("/api/res/sections", json={"name": "A", "class_name": grade, "status": "active"})
    for s in subjects:
        admin.post("/api/res/subjects", json={"name": s, "status": "active"})
        admin.post("/api/res/subject_offerings", json={"subject": s, "class_name": grade, "max_marks": 100, "status": "active"})


def _reqs(admin, grade, items):
    return admin.put("/api/timetable/requirements", json={"academic_year": "2026-27", "class_name": grade, "items": items})


def test_generation_counts_consecutive_no_hard_conflicts(ctx):
    admin, i = ctx["new_school"]()
    u = admin.post("/api/res/academic_units", json={"name": "HS", "code": "HS", "status": "active"}).json()
    admin.post("/api/res/academic_years", json={"name": "2026-27", "status": "active"})
    t = _teacher(admin, i, "Mara")
    _grade(admin, "Grade 8", u["id"])
    _grade(admin, "Grade 9", u["id"])
    # shared teacher across both grades' Maths, so generator must avoid double-booking
    _reqs(admin, "Grade 8", [{"subject": "Mathematics", "periods_per_week": 6, "consecutive_periods": 2,
                              "must_be_consecutive": True, "teacher_ids": [t["id"]]},
                             {"subject": "Physics", "periods_per_week": 5, "teacher_ids": [t["id"]]}])
    _reqs(admin, "Grade 9", [{"subject": "Mathematics", "periods_per_week": 4, "teacher_ids": [t["id"]]}])
    g8 = admin.post("/api/timetable/generate", json={"academic_year": "2026-27", "class_name": "Grade 8"}).json()
    assert g8["per_section_summary"]["A"]["placed"] == 11 and g8["unplaced"] == []
    # verify weekly counts + consecutive blocks on the DRAFT
    grid = admin.get("/api/timetable/grid", params={"academic_year": "2026-27", "class_name": "Grade 8", "section": "A", "mode": "draft"}).json()
    ents = grid["entries"]
    assert sum(1 for e in ents if e["subject"] == "Mathematics") == 6
    assert sum(1 for e in ents if e["subject"] == "Physics") == 5
    # Maths appears as adjacent pairs on some day (consecutive-2)
    maths_by_day = {}
    for e in ents:
        if e["subject"] == "Mathematics":
            maths_by_day.setdefault(e["day"], []).append(e["period_no"])
    assert any(len(ps) >= 2 and any(abs(a - b) == 1 for a in ps for b in ps if a != b) for ps in maths_by_day.values())
    # publish Grade 8, then generate Grade 9 → no slot where the shared teacher is double-booked
    g8b = admin.get("/api/timetable/grid", params={"academic_year": "2026-27", "class_name": "Grade 8", "section": "A", "mode": "draft"}).json()
    admin.post("/api/timetable/publish", json={"batch_id": g8b["draft_batch"]["id"]})
    admin.post("/api/timetable/generate", json={"academic_year": "2026-27", "class_name": "Grade 9"})
    g9 = admin.get("/api/timetable/grid", params={"academic_year": "2026-27", "class_name": "Grade 9", "section": "A", "mode": "draft"}).json()
    busy8 = {(e["day"], e["period_no"]) for e in g8b["entries"] if e["teacher_id"] == t["id"]}
    for e in g9["entries"]:
        if e["teacher_id"] == t["id"]:
            assert (e["day"], e["period_no"]) not in busy8, "generator double-booked the shared teacher"


def test_unplaced_reporting_when_insufficient(ctx):
    admin, i = ctx["new_school"]()
    u = admin.post("/api/res/academic_units", json={"name": "HS", "code": "HS", "status": "active"}).json()
    admin.post("/api/res/academic_years", json={"name": "2026-27", "status": "active"})
    _grade(admin, "Grade 8", u["id"], subjects=("Alpha", "Beta", "Gamma"))
    # three must-be-consecutive-3 subjects need 11 blocks of 3, but a 7-period day fits only 2 such
    # blocks/day → 10 block-slots across 5 days; the 11th block (3 periods) cannot be placed.
    _reqs(admin, "Grade 8", [
        {"subject": "Alpha", "periods_per_week": 15, "consecutive_periods": 3, "must_be_consecutive": True},
        {"subject": "Beta", "periods_per_week": 15, "consecutive_periods": 3, "must_be_consecutive": True},
        {"subject": "Gamma", "periods_per_week": 3, "consecutive_periods": 3, "must_be_consecutive": True},
    ])
    g = admin.post("/api/timetable/generate", json={"academic_year": "2026-27", "class_name": "Grade 8"}).json()
    total_short = sum(u["periods_short"] for u in g["unplaced"])
    assert g["unplaced"], "expected an unplaced report"
    assert any("consecutive" in u["reason"] for u in g["unplaced"])
    assert total_short >= 3 and total_short % 3 == 0            # unmet whole consecutive blocks only
    assert g["placed_count"] + total_short == 33                # nothing silently lost
    assert all(u["periods_short"] % 3 == 0 for u in g["unplaced"])  # never placed as violating singles


def test_draft_isolation_until_publish(ctx):
    admin, i = ctx["new_school"]()
    u = admin.post("/api/res/academic_units", json={"name": "HS", "code": "HS", "status": "active"}).json()
    admin.post("/api/res/academic_years", json={"name": "2026-27", "status": "active"})
    _grade(admin, "Grade 8", u["id"])
    _reqs(admin, "Grade 8", [{"subject": "Mathematics", "periods_per_week": 5}])
    admin.post("/api/timetable/generate", json={"academic_year": "2026-27", "class_name": "Grade 8"})
    pub = admin.get("/api/timetable/grid", params={"academic_year": "2026-27", "class_name": "Grade 8", "section": "A", "mode": "published"}).json()
    assert pub["entries"] == []  # nothing published yet
    draft = admin.get("/api/timetable/grid", params={"academic_year": "2026-27", "class_name": "Grade 8", "section": "A", "mode": "draft"}).json()
    assert len(draft["entries"]) == 5 and draft["mode"] == "draft"


def test_publish_swap_atomic_old_removed(ctx):
    admin, i = ctx["new_school"]()
    u = admin.post("/api/res/academic_units", json={"name": "HS", "code": "HS", "status": "active"}).json()
    admin.post("/api/res/academic_years", json={"name": "2026-27", "status": "active"})
    _grade(admin, "Grade 8", u["id"])
    _reqs(admin, "Grade 8", [{"subject": "Mathematics", "periods_per_week": 3}])
    b1 = admin.post("/api/timetable/generate", json={"academic_year": "2026-27", "class_name": "Grade 8"}).json()
    admin.post("/api/timetable/publish", json={"batch_id": b1["batch_id"]})
    pub1 = admin.get("/api/timetable/grid", params={"academic_year": "2026-27", "class_name": "Grade 8", "section": "A", "mode": "published"}).json()
    assert len(pub1["entries"]) == 3
    old_ids = {e["id"] for e in pub1["entries"]}
    # regenerate with different count and republish → old published entries replaced
    _reqs(admin, "Grade 8", [{"subject": "Mathematics", "periods_per_week": 5}])
    b2 = admin.post("/api/timetable/generate", json={"academic_year": "2026-27", "class_name": "Grade 8"}).json()
    admin.post("/api/timetable/publish", json={"batch_id": b2["batch_id"]})
    pub2 = admin.get("/api/timetable/grid", params={"academic_year": "2026-27", "class_name": "Grade 8", "section": "A", "mode": "published"}).json()
    assert len(pub2["entries"]) == 5
    assert old_ids.isdisjoint({e["id"] for e in pub2["entries"]})  # old ones gone


def test_student_portal_visibility(ctx):
    admin, i = ctx["new_school"]()
    u = admin.post("/api/res/academic_units", json={"name": "HS", "code": "HS", "status": "active"}).json()
    admin.post("/api/res/academic_years", json={"name": "2026-27", "status": "active"})
    _grade(admin, "Grade 8", u["id"])
    admin.post("/api/res/sections", json={"name": "A", "class_name": "Grade 8", "status": "active"})
    stu = admin.post("/api/res/students", json={"first_name": "Aarav", "last_name": "M", "class_name": "Grade 8",
                     "section": "A", "admission_no": f"ST{i}", "status": "active"}).json()
    admin.post(f"/api/students/{stu['id']}/portal-user", json={"email": f"aarav{i}@s9.test", "password": "Student@123"})
    _reqs(admin, "Grade 8", [{"subject": "Mathematics", "periods_per_week": 4}])
    b = admin.post("/api/timetable/generate", json={"academic_year": "2026-27", "class_name": "Grade 8"}).json()
    sess = ctx["login"](f"aarav{i}@s9.test", "Student@123")
    assert sess.get("/api/portal/timetable").json()["entries"] == []  # pre-publish: nothing
    admin.post("/api/timetable/publish", json={"batch_id": b["batch_id"]})
    assert len(sess.get("/api/portal/timetable").json()["entries"]) == 4  # post-publish: visible
    admin.post("/api/timetable/unpublish", json={"class_name": "Grade 8", "academic_year": "2026-27"})
    assert sess.get("/api/portal/timetable").json()["entries"] == []  # unpublished: gone


def test_unit_principal_scope_generate_publish(ctx):
    admin, i = ctx["new_school"]()
    ua = admin.post("/api/res/academic_units", json={"name": "LP", "code": "LP", "status": "active"}).json()
    ub = admin.post("/api/res/academic_units", json={"name": "UP", "code": "UP", "status": "active"}).json()
    admin.post("/api/res/academic_years", json={"name": "2026-27", "status": "active"})
    _grade(admin, "Grade 1", ua["id"])
    _grade(admin, "Grade 6", ub["id"])
    _reqs(admin, "Grade 1", [{"subject": "Mathematics", "periods_per_week": 3}])
    _reqs(admin, "Grade 6", [{"subject": "Mathematics", "periods_per_week": 3}])
    t = _teacher(admin, i, "Pscope")
    admin.post("/api/principals", json={"teacher_id": t["id"], "scope_type": "units", "unit_ids": [ua["id"]]})
    prin = ctx["login"](f"pscope{i}@s9.test", "Teach@123")
    assert prin.post("/api/timetable/generate", json={"academic_year": "2026-27", "class_name": "Grade 1"}).status_code == 200
    assert prin.post("/api/timetable/generate", json={"academic_year": "2026-27", "class_name": "Grade 6"}).status_code == 403
    # publish in-scope OK, out-of-scope blocked (admin generates Grade 6 draft first)
    b6 = admin.post("/api/timetable/generate", json={"academic_year": "2026-27", "class_name": "Grade 6"}).json()
    assert prin.post("/api/timetable/publish", json={"batch_id": b6["batch_id"]}).status_code == 403


def test_phase8_place_on_published_still_works(ctx):
    admin, i = ctx["new_school"]()
    u = admin.post("/api/res/academic_units", json={"name": "HS", "code": "HS", "status": "active"}).json()
    admin.post("/api/res/academic_years", json={"name": "2026-27", "status": "active"})
    _grade(admin, "Grade 8", u["id"])
    r = admin.post("/api/timetable/place", json={"academic_year": "2026-27", "class_name": "Grade 8",
        "section": "A", "day": "mon", "period_no": 1, "subject": "Mathematics"})
    assert r.json()["ok"] is True
    assert r.json()["entry"]["publish_state"] == "published"
    pub = admin.get("/api/timetable/grid", params={"academic_year": "2026-27", "class_name": "Grade 8", "section": "A"}).json()
    assert len(pub["entries"]) == 1  # visible in default (published) mode immediately


# ---------------- Enhancement: actionable unplaced suggestions ----------------

def test_no_teacher_cause_and_suggestion(ctx):
    admin, i = ctx["new_school"]()
    u = admin.post("/api/res/academic_units", json={"name": "HS", "code": "HS", "status": "active"}).json()
    admin.post("/api/res/academic_years", json={"name": "2026-27", "status": "active"})
    _grade(admin, "Grade 8", u["id"], subjects=("Solo",))
    _reqs(admin, "Grade 8", [{"subject": "Solo", "periods_per_week": 3, "teacher_ids": []}])
    g = admin.post("/api/timetable/generate", json={"academic_year": "2026-27", "class_name": "Grade 8"}).json()
    nt = [x for x in g["unplaced"] if x["cause"] == "no_teacher"]
    assert nt, "expected a no_teacher advisory"
    assert nt[0]["suggestions"] and "class-hub" in nt[0]["suggestions"][0]["href"]
    assert "tab=subjects" in nt[0]["suggestions"][0]["href"]


def test_pool_exhausted_cause_and_suggestion(ctx):
    admin, i = ctx["new_school"]()
    u = admin.post("/api/res/academic_units", json={"name": "HS", "code": "HS", "status": "active"}).json()
    admin.post("/api/res/academic_years", json={"name": "2026-27", "status": "active"})
    t = _teacher(admin, i, "Solo")
    # make the only Maths teacher globally busy at P1 every working day (published elsewhere).
    # The single-slot placement tries each day's first free period, so blocking P1 everywhere
    # exhausts the pool while the section's week still has free slots → pool_exhausted.
    _grade(admin, "Grade Y", u["id"], subjects=("Filler",))
    for d in ("mon", "tue", "wed", "thu", "fri", "sat"):
        admin.post("/api/timetable/place", json={"academic_year": "2026-27", "class_name": "Grade Y",
                   "section": "A", "day": d, "period_no": 1, "subject": "Filler", "teacher_id": t["id"], "override": True})
    # Grade X: Maths by the SAME (now P1-busy) teacher → pool exhausted, section slots free
    _grade(admin, "Grade X", u["id"], subjects=("Maths",))
    _reqs(admin, "Grade X", [{"subject": "Maths", "periods_per_week": 2, "teacher_ids": [t["id"]]}])
    g = admin.post("/api/timetable/generate", json={"academic_year": "2026-27", "class_name": "Grade X"}).json()
    pe = [x for x in g["unplaced"] if x["cause"] == "pool_exhausted"]
    assert pe, f"expected pool_exhausted, got {[x.get('cause') for x in g['unplaced']]}"
    labels = " ".join(s["label"] for s in pe[0]["suggestions"])
    assert "Add another" in labels and "periods/week" in labels


def test_consecutive_unplaceable_cause_and_suggestion(ctx):
    admin, i = ctx["new_school"]()
    u = admin.post("/api/res/academic_units", json={"name": "HS", "code": "HS", "status": "active"}).json()
    admin.post("/api/res/academic_years", json={"name": "2026-27", "status": "active"})
    t = _teacher(admin, i, "Mara")
    _grade(admin, "Grade 8", u["id"], subjects=("Alpha", "Beta", "Gamma"))
    _reqs(admin, "Grade 8", [
        {"subject": "Alpha", "periods_per_week": 15, "consecutive_periods": 3, "must_be_consecutive": True, "teacher_ids": [t["id"]]},
        {"subject": "Beta", "periods_per_week": 15, "consecutive_periods": 3, "must_be_consecutive": True, "teacher_ids": [t["id"]]},
        {"subject": "Gamma", "periods_per_week": 3, "consecutive_periods": 3, "must_be_consecutive": True, "teacher_ids": [t["id"]]},
    ])
    g = admin.post("/api/timetable/generate", json={"academic_year": "2026-27", "class_name": "Grade 8"}).json()
    cu = [x for x in g["unplaced"] if x["cause"] == "consecutive_unplaceable"]
    assert cu, "expected consecutive_unplaceable"
    labels = " ".join(s["label"] for s in cu[0]["suggestions"])
    assert "must-be-consecutive" in labels and "Reduce consecutive" in labels
