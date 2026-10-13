"""Phase 12 — Auto-Balance Generator. Throwaway DB, API-driven (mirrors phase11 harness).

Covers: default flexible flags, trim-flexible-first when over budget, consecutive relaxation for
flexible subjects only (reported), empty-slot top-up to max, auto_adjustments[] report, that
subject_requirements is NEVER mutated by balancing, and honest staffing-shortfall reporting.

Capacity = 5 working days x 7 teaching periods (P1..P7) = 35 slots. The only valid 3-in-a-row
window per day is P1-P3, so a 3-consecutive subject can place at most 5 blocks (one per day).
"""
import sys
import pytest

sys.path.insert(0, "/app/backend")
import server  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from pymongo import MongoClient  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

TEST_DB = "lnmo_phase12_test"
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
            "name": "S12", "slug": "s12", "admin_email": "a@s12.test", "admin_password": "Admin@123"})
        admin = login("a@s12.test", "Admin@123")
        admin.post("/api/res/academic_years", json={"name": AY, "status": "active"})
        lp = admin.post("/api/res/academic_units", json={"name": "LP", "code": "LP", "status": "active"}).json()

        def teacher(n):
            return admin.post("/api/teachers", json={"name": n, "email": f"{n.lower()}@s12.test", "password": "Teach@123", "status": "active"}).json()
        tt = {n: teacher(n) for n in ("Core", "Flex")}

        admin.post("/api/res/classes", json={"name": "Grade 1", "academic_unit_id": lp["id"], "status": "active"})
        admin.post("/api/res/sections", json={"name": "A", "class_name": "Grade 1", "status": "active"})
        for s in ("Mathematics", "Art Education", "Music", "Library"):
            admin.post("/api/res/subjects", json={"name": s, "status": "active"})
            admin.post("/api/res/subject_offerings", json={"subject": s, "class_name": "Grade 1", "section": "A", "max_marks": 100, "status": "active"})

        yield {"admin": admin, "t": tt, "db": mon}
    MongoClient(server.mongo_url).drop_database(TEST_DB)


def _staff(admin, items):
    r = admin.put("/api/class-hub/Grade 1/subject-staff", json={"academic_year": AY, "items": items})
    assert r.status_code == 200, r.text
    return r.json()


def _reset(db):
    db.subject_requirements.delete_many({})
    db.timetable_entries.delete_many({})
    db.timetable_batches.delete_many({})


def _gen(admin, auto_balance):
    r = admin.post("/api/timetable/generate", json={"academic_year": AY, "class_name": "Grade 1", "auto_balance": auto_balance})
    assert r.status_code == 200, r.text
    return r.json()


def test_default_flexible_flag_exposed(ctx):
    admin = ctx["admin"]
    items = {i["subject"]: i for i in admin.get("/api/class-hub/Grade 1/subject-staff", params={"academic_year": AY}).json()["items"]}
    assert items["Art Education"]["flexible"] is True     # default-flexible catalog subject
    assert items["Mathematics"]["flexible"] is False      # core subject
    assert items["Music"]["flexible"] is True
    assert items["Mathematics"]["min_periods"] == 1


def test_overbudget_trims_flexible_only(ctx):
    admin, t, db = ctx["admin"], ctx["t"], ctx["db"]
    _reset(db)
    # Capacity 35. Core 33 + flexible Art 10 = 43 > 35 -> trim Art by 8 (floor min 1).
    _staff(admin, [
        {"subject": "Mathematics", "section_teachers": {"A": t["Core"]["id"]}, "periods_per_week": 33, "flexible": False},
        {"subject": "Art Education", "section_teachers": {"A": t["Flex"]["id"]}, "periods_per_week": 10, "flexible": True, "min_periods": 1, "max_periods": 10},
    ])
    res = _gen(admin, True)
    trims = [a for a in res["auto_adjustments"] if a["type"] == "trim"]
    assert any(a["subject"] == "Art Education" and a["to"] == 2 for a in trims), res["auto_adjustments"]
    assert all(a["subject"] != "Mathematics" for a in trims)  # core never trimmed
    # requirements doc is NOT mutated by balancing
    assert db.subject_requirements.find_one({"subject": "Art Education"})["periods_per_week"] == 10


def test_topup_fills_empty_slots_to_max(ctx):
    admin, t, db = ctx["admin"], ctx["t"], ctx["db"]
    _reset(db)
    _staff(admin, [
        {"subject": "Mathematics", "section_teachers": {"A": t["Core"]["id"]}, "periods_per_week": 5, "flexible": False},
        {"subject": "Music", "section_teachers": {"A": t["Flex"]["id"]}, "periods_per_week": 2, "flexible": True, "min_periods": 1, "max_periods": 5},
    ])
    res = _gen(admin, True)
    topups = [a for a in res["auto_adjustments"] if a["type"] == "topup" and a["subject"] == "Music"]
    assert topups and topups[0]["to"] == 5, res["auto_adjustments"]
    assert db.timetable_entries.count_documents({"subject": "Music", "publish_state": "draft"}) == 5


def test_no_adjustments_when_balance_off(ctx):
    admin, t, db = ctx["admin"], ctx["t"], ctx["db"]
    _reset(db)
    _staff(admin, [
        {"subject": "Mathematics", "section_teachers": {"A": t["Core"]["id"]}, "periods_per_week": 5, "flexible": False},
        {"subject": "Music", "section_teachers": {"A": t["Flex"]["id"]}, "periods_per_week": 2, "flexible": True, "max_periods": 5},
    ])
    res = _gen(admin, False)
    assert res["auto_adjustments"] == []
    assert db.timetable_entries.count_documents({"subject": "Music", "publish_state": "draft"}) == 2  # no top-up


def test_consecutive_relaxed_for_flexible_only(ctx):
    admin, t, db = ctx["admin"], ctx["t"], ctx["db"]
    _reset(db)
    # Library flexible, 18 periods in 3-consecutive blocks. Only P1-P3 per day is valid -> max 5
    # blocks (15 periods) fit as blocks; the 6th block can't -> relaxed to singles (not trimmed:
    # demand 18+5=23 < 35). max 18 so no top-up.
    _staff(admin, [
        {"subject": "Mathematics", "section_teachers": {"A": t["Core"]["id"]}, "periods_per_week": 5, "flexible": False},
        {"subject": "Library", "section_teachers": {"A": t["Flex"]["id"]}, "periods_per_week": 18,
         "consecutive_periods": 3, "must_be_consecutive": True, "flexible": True, "min_periods": 18, "max_periods": 18},
    ])
    res = _gen(admin, True)
    relax = [a for a in res["auto_adjustments"] if a["type"] == "relax_consecutive" and a["subject"] == "Library"]
    assert relax, res["auto_adjustments"]
    # all 18 Library periods still land (5 blocks of 3 + 3 relaxed singles)
    assert db.timetable_entries.count_documents({"subject": "Library", "publish_state": "draft"}) == 18


def test_staffing_shortfall_still_reported(ctx):
    admin, t, db = ctx["admin"], ctx["t"], ctx["db"]
    _reset(db)
    # Flexible subject with NO teacher: honest no_teacher report, and never topped up.
    _staff(admin, [
        {"subject": "Mathematics", "section_teachers": {"A": t["Core"]["id"]}, "periods_per_week": 5, "flexible": False},
        {"subject": "Music", "section_teachers": {}, "periods_per_week": 3, "flexible": True, "max_periods": 6},
    ])
    res = _gen(admin, True)
    assert any(u["cause"] == "no_teacher" and u["subject"] == "Music" for u in res["unplaced"]), res["unplaced"]
    assert all(not (a["type"] == "topup" and a["subject"] == "Music") for a in res["auto_adjustments"])
