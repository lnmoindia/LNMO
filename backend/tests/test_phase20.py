"""Phase 20 — exam list scoping for unit principals.

Matrix: institution_admin & whole-school principal → all exams editable. Unit principal → sees
ALL institution exams; editable=true only when EVERY division of the exam is within their units,
else editable=false (read-only, still visible). Empty-scope → 200 with exams listed read-only.
"""
import os, sys
import pytest

sys.path.insert(0, "/app/backend")
import server  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from pymongo import MongoClient  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

TEST_DB = "lnmo_phase20_test"
PA_EMAIL = server.os.environ["PLATFORM_ADMIN_EMAIL"].lower()
PA_PW = server.os.environ["PLATFORM_ADMIN_PASSWORD"]
BASE = "https://testserver"


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
            tok = r.cookies.get("access_token"); C.cookies.clear()
            return Sess(C, tok)

        platform = login(PA_EMAIL, PA_PW)
        platform.post("/api/res/institutions", json={"name": "S20", "slug": "s20", "admin_email": "a@s20.test", "admin_password": "Admin@123"})
        admin = login("a@s20.test", "Admin@123")
        hs = admin.post("/api/res/academic_units", json={"name": "HS", "code": "HS", "status": "active"}).json()
        lp = admin.post("/api/res/academic_units", json={"name": "LP", "code": "LP", "status": "active"}).json()
        up = admin.post("/api/res/academic_units", json={"name": "UP", "code": "UP", "status": "active"}).json()
        admin.post("/api/res/academic_years", json={"name": "2026-27", "status": "active"})
        admin.post("/api/res/classes", json={"name": "Grade 8", "academic_unit_id": hs["id"], "status": "active"})
        admin.post("/api/res/classes", json={"name": "Grade 3", "academic_unit_id": lp["id"], "status": "active"})

        def principal(name, units):
            t = admin.post("/api/teachers", json={"name": name, "email": f"{name.lower()}@s20.test", "password": "Teach@123", "status": "active"}).json()
            admin.post("/api/principals", json={"teacher_id": t["id"], "scope_type": "units", "unit_ids": units, "designation": "principal"})
        principal("HSHead", [hs["id"]])
        principal("UPHead", [up["id"]])

        def mk_exam(nm, unit_ids):
            cfgs = [{"academic_unit_id": u, "date_start": "2026-11-01", "date_end": "2026-11-05",
                     "slots_per_day": [{"start": "09:30", "end": "11:00", "label": ""}]} for u in unit_ids]
            return admin.post("/api/exams", json={"name": nm, "type": "model", "division_configs": cfgs}).json()["exam"]
        model = mk_exam("Model Exam 2026", [hs["id"], lp["id"]])  # HS + LP (cross-division)
        hs_only = mk_exam("HS Unit Test", [hs["id"]])

        yield {"admin": admin, "login": login, "model": model["id"], "hs_only": hs_only["id"]}
    MongoClient(server.mongo_url).drop_database(TEST_DB)


def _by_id(exams):
    return {e["id"]: e for e in exams}


def test_admin_sees_all_editable(ctx):
    exams = _by_id(ctx["admin"].get("/api/exams").json()["exams"])
    assert len(exams) == 2
    assert exams[ctx["model"]]["editable"] is True
    assert exams[ctx["hs_only"]]["editable"] is True


def test_hs_principal_editable_in_scope_readonly_cross(ctx):
    hs = ctx["login"]("hshead@s20.test", "Teach@123")
    exams = _by_id(hs.get("/api/exams").json()["exams"])
    assert len(exams) == 2                                   # sees BOTH, none hidden
    assert exams[ctx["hs_only"]]["editable"] is True         # fully in HS → editable
    assert exams[ctx["model"]]["editable"] is False          # HS+LP → cross-division → read-only


def test_up_principal_sees_all_readonly(ctx):
    up = ctx["login"]("uphead@s20.test", "Teach@123")
    r = up.get("/api/exams")
    assert r.status_code == 200
    exams = _by_id(r.json()["exams"])
    assert len(exams) == 2                                   # UP has NO exams in scope, but still SEES them
    assert exams[ctx["model"]]["editable"] is False
    assert exams[ctx["hs_only"]]["editable"] is False
