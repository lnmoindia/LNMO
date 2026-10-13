"""Phase 5 — academic configuration PRESETS (apply-preset) backend tests. Throwaway DB."""
import sys
import pytest

sys.path.insert(0, "/app/backend")
import server  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from pymongo import MongoClient  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

TEST_DB = "lnmo_phase5_test"
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
            r = platform.post("/api/res/institutions", json={
                "name": f"School {i}", "slug": f"school-{i}",
                "admin_email": f"admin{i}@school.test", "admin_password": "Admin@123"})
            assert r.status_code == 200, r.text
            return login(f"admin{i}@school.test", "Admin@123")

        yield {"login": login, "new_school": new_school, "C": C}
    MongoClient(server.mongo_url).drop_database(TEST_DB)


def _counts(admin):
    u = admin.get("/api/res/academic_units", params={"limit": 100}).json()["total"]
    c = admin.get("/api/res/classes", params={"limit": 100}).json()["total"]
    s = admin.get("/api/res/sections", params={"limit": 100}).json()["total"]
    return u, c, s


def test_lp_up_hs_hss_from_empty(ctx):
    admin = ctx["new_school"]()
    r = admin.post("/api/institution/apply-preset", json={"preset": "lp_up_hs_hss"})
    assert r.status_code == 200, r.text
    s = r.json()["summary"]
    assert s == {"units_created": 4, "units_skipped": 0, "classes_created": 12,
                 "classes_skipped": 0, "sections_created": 12}, s
    assert _counts(admin) == (4, 12, 12)
    names = {u["name"] for u in admin.get("/api/res/academic_units", params={"limit": 100}).json()["items"]}
    assert names == {"LP", "UP", "HS", "HSS"}


def test_k12_from_empty(ctx):
    admin = ctx["new_school"]()
    r = admin.post("/api/institution/apply-preset", json={"preset": "k12"})
    s = r.json()["summary"]
    assert s == {"units_created": 1, "units_skipped": 0, "classes_created": 12,
                 "classes_skipped": 0, "sections_created": 12}, s
    assert _counts(admin) == (1, 12, 12)
    assert admin.get("/api/res/academic_units", params={"limit": 100}).json()["items"][0]["name"] == "K-12"


def test_merge_over_partial_setup(ctx):
    admin = ctx["new_school"]()
    # pre-create unit "LP" + class "Grade 1" manually (no section)
    unit = admin.post("/api/res/academic_units", json={"name": "LP", "code": "LP", "status": "active"}).json()
    admin.post("/api/res/classes", json={"name": "Grade 1", "grade_level": "1",
                                         "academic_unit_id": unit["id"], "status": "active"})
    r = admin.post("/api/institution/apply-preset", json={"preset": "lp_up_hs_hss"})
    s = r.json()["summary"]
    # LP + Grade 1 already existed → skipped; everything else created; Grade 1 still gets its section
    assert s["units_skipped"] == 1 and s["units_created"] == 3, s
    assert s["classes_skipped"] == 1 and s["classes_created"] == 11, s
    assert s["sections_created"] == 12, s
    assert _counts(admin) == (4, 12, 12)  # no duplicates


def test_idempotent_double_apply(ctx):
    admin = ctx["new_school"]()
    admin.post("/api/institution/apply-preset", json={"preset": "k12"})
    r2 = admin.post("/api/institution/apply-preset", json={"preset": "k12"})
    s = r2.json()["summary"]
    assert s == {"units_created": 0, "units_skipped": 1, "classes_created": 0,
                 "classes_skipped": 12, "sections_created": 0}, s
    assert _counts(admin) == (1, 12, 12)


def test_invalid_preset_422(ctx):
    admin = ctx["new_school"]()
    assert admin.post("/api/institution/apply-preset", json={"preset": "nope"}).status_code == 422


def test_principal_and_teacher_get_403(ctx):
    admin = ctx["new_school"]()
    # create a teacher, elevate to principal, and confirm 403 either way (academic config is excluded)
    t = admin.post("/api/teachers", json={"name": "T", "email": f"t{_n['i']}@school.test",
                                          "password": "Teach@123", "status": "active"}).json()
    admin.post("/api/principals", json={"teacher_id": t["id"], "scope_type": "whole_school"})
    server_db_mark = None  # noqa
    teacher = ctx["login"](f"t{_n['i']}@school.test", "Teach@123")
    assert teacher.post("/api/institution/apply-preset", json={"preset": "k12"}).status_code == 403
