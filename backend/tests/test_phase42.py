"""Phase 42 — Bulk recommend on the promotion module.
Rule under test: bulk applies to one section only; rows that already carry an individual
recommendation are SKIPPED unless override=true; bulk recommendations never become decisions
on their own; out-of-scope callers get 403.
"""
import sys
import uuid
import pytest

sys.path.insert(0, "/app/backend")
import server  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from pymongo import MongoClient  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

TEST_DB = "lnmo_phase42_test"
PA_EMAIL = server.os.environ["PLATFORM_ADMIN_EMAIL"].lower()
PA_PW = server.os.environ["PLATFORM_ADMIN_PASSWORD"]
BASE = "https://testserver"
FROM_Y = "2026-27"
TO_Y = "2027-28"


def _client():
    return TestClient(server.app, base_url=BASE)


class Sess:
    def __init__(self, c, tok):
        self._c, self._h = c, {"Authorization": f"Bearer {tok}"}

    def _call(self, m, p, **k):
        self._c.cookies.clear()
        return self._c.request(m, p, headers={**self._h, **k.pop("headers", {})}, **k)

    def get(self, p, **k): return self._call("get", p, **k)
    def post(self, p, **k): return self._call("post", p, **k)
    def put(self, p, **k): return self._call("put", p, **k)


def _seed_student(mon, iid, name, grade, section, year):
    sid = str(uuid.uuid4())
    mon.students.insert_one({"id": sid, "institution_id": iid, "first_name": name, "last_name": "X",
                             "admission_no": name.upper(), "enrollment_status": "enrolled",
                             "class_name": f"Grade {grade}", "section": section, "academic_year": year})
    mon.enrollments.insert_one({"id": str(uuid.uuid4()), "institution_id": iid, "student_id": sid,
                                "student_name": f"{name} X", "admission_no": name.upper(),
                                "academic_year": year, "class_name": f"Grade {grade}", "section": section})
    return sid


@pytest.fixture(scope="module")
def ctx(monkeymodule):
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
            tok = r.cookies.get("access_token"); C.cookies.clear()
            return tok

        platform = Sess(C, login(PA_EMAIL, PA_PW))
        A = platform.post("/api/res/institutions", json={"name": "Bulk", "slug": "p42",
                          "admin_email": "a@p42.test", "admin_password": "Admin@123"}).json()["id"]
        admin = Sess(C, login("a@p42.test", "Admin@123"))

        mon.academic_units.insert_many([
            {"id": "uHS", "institution_id": A, "name": "HS", "code": "HS"},
            {"id": "uUP", "institution_id": A, "name": "UP", "code": "UP"},
        ])
        for g, unit in [(7, "uUP"), (8, "uHS"), (9, "uHS")]:
            uname = "UP" if unit == "uUP" else "HS"
            mon.classes.insert_one({"id": f"c{g}", "institution_id": A, "name": f"Grade {g}",
                                    "grade_level": str(g), "academic_unit_id": unit, "academic_unit_name": uname})
            mon.sections.insert_one({"id": f"s{g}A", "institution_id": A, "name": "A", "class_name": f"Grade {g}", "status": "active"})
        mon.academic_years.insert_one({"id": str(uuid.uuid4()), "institution_id": A, "name": FROM_Y, "status": "active"})

        ctid = str(uuid.uuid4())
        mon.users.insert_one({"id": ctid, "name": "CT8", "email": "ct8@p42.test",
                              "password_hash": server.hash_password("Teach@123"), "role": "teacher",
                              "institution_id": A, "status": "active", "must_change_password": False,
                              "created_at": server.now_iso()})
        mon.sections.update_one({"id": "s8A"}, {"$set": {"class_teacher_id": ctid, "class_teacher": "CT8"}})
        CT8 = Sess(C, login("ct8@p42.test", "Teach@123"))

        # a teacher who is NOT the Grade-8 class teacher (class teacher of Grade 7)
        otid = str(uuid.uuid4())
        mon.users.insert_one({"id": otid, "name": "CT7", "email": "ct7@p42.test",
                              "password_hash": server.hash_password("Teach@123"), "role": "teacher",
                              "institution_id": A, "status": "active", "must_change_password": False,
                              "created_at": server.now_iso()})
        mon.sections.update_one({"id": "s7A"}, {"$set": {"class_teacher_id": otid, "class_teacher": "CT7"}})
        CT7 = Sess(C, login("ct7@p42.test", "Teach@123"))

        g8 = [_seed_student(mon, A, f"a{i}", 8, "A", FROM_Y) for i in range(4)]
        g9 = [_seed_student(mon, A, f"b{i}", 9, "A", FROM_Y) for i in range(2)]
        yield {"admin": admin, "CT8": CT8, "CT7": CT7, "A": A, "db": mon, "g8": g8, "g9": g9}
    MongoClient(server.mongo_url).drop_database(TEST_DB)


def _fresh_run(admin):
    admin.post("/api/promotion/preview", json={"from_year": FROM_Y, "to_year": TO_Y})
    return admin.get("/api/promotion/runs").json()["runs"][0]["id"]


def test_bulk_applies_to_section_only(ctx):
    admin, db = ctx["admin"], ctx["db"]
    rid = _fresh_run(admin)
    r = ctx["CT8"].put(f"/api/promotion/{rid}/recommend-bulk",
                       json={"class_name": "Grade 8", "section": "A", "recommendation": "detain", "note": "revise"})
    assert r.status_code == 200, r.text
    assert r.json()["applied"] == 4 and r.json()["skipped"] == 0
    for sid in ctx["g8"]:
        d = db.promotion_decisions.find_one({"run_id": rid, "student_id": sid})
        assert d["teacher_recommendation"] == "detain" and d["recommendation_note"] == "revise"
        assert d["decision"] == "promote"  # recommendation alone never detains
    for sid in ctx["g9"]:  # other section untouched
        assert db.promotion_decisions.find_one({"run_id": rid, "student_id": sid})["teacher_recommendation"] is None


def test_bulk_skips_edited_unless_override(ctx):
    admin, db = ctx["admin"], ctx["db"]
    rid = _fresh_run(admin)
    # individually recommend one Grade-8 student first
    first = db.promotion_decisions.find_one({"run_id": rid, "student_id": ctx["g8"][0]})
    ctx["CT8"].put(f"/api/promotion/decisions/{first['id']}/recommend", json={"recommendation": "promote", "note": "star"})
    # bulk without override skips that row
    r = ctx["CT8"].put(f"/api/promotion/{rid}/recommend-bulk",
                       json={"class_name": "Grade 8", "section": "A", "recommendation": "detain"})
    assert r.json()["applied"] == 3 and r.json()["skipped"] == 1
    assert db.promotion_decisions.find_one({"id": first["id"]})["teacher_recommendation"] == "promote"  # preserved
    # bulk WITH override replaces it
    r2 = ctx["CT8"].put(f"/api/promotion/{rid}/recommend-bulk",
                        json={"class_name": "Grade 8", "section": "A", "recommendation": "detain", "override": True})
    assert r2.json()["applied"] == 4 and r2.json()["skipped"] == 0
    assert db.promotion_decisions.find_one({"id": first["id"]})["teacher_recommendation"] == "detain"


def test_bulk_scope_403(ctx):
    admin = ctx["admin"]
    rid = _fresh_run(admin)
    # the Grade-7 class teacher cannot bulk-recommend Grade 8
    r = ctx["CT7"].put(f"/api/promotion/{rid}/recommend-bulk",
                       json={"class_name": "Grade 8", "section": "A", "recommendation": "detain"})
    assert r.status_code == 403, r.text


def test_bulk_requires_preview_run(ctx):
    admin, db = ctx["admin"], ctx["db"]
    rid = _fresh_run(admin)
    db.promotion_runs.update_one({"id": rid}, {"$set": {"status": "executed"}})
    r = ctx["admin"].put(f"/api/promotion/{rid}/recommend-bulk",
                         json={"class_name": "Grade 8", "section": "A", "recommendation": "promote"})
    assert r.status_code == 409
    db.promotion_runs.update_one({"id": rid}, {"$set": {"status": "preview"}})
