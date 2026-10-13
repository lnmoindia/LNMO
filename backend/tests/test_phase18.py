"""Phase 18 — student profile aggregation endpoint. Throwaway DB, API-driven.

Full payload for admin; 403 for out-of-scope principal; 403 for teacher/student/parent roles;
linked-parents data present; in-scope principal allowed. Teacher profile full-view permissions
reuse Phase 15 (not re-tested here)."""
import os, sys
import pytest

sys.path.insert(0, "/app/backend")
import server  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from pymongo import MongoClient  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

TEST_DB = "lnmo_phase18_test"
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
        platform.post("/api/res/institutions", json={"name": "S18", "slug": "s18", "admin_email": "a@s18.test", "admin_password": "Admin@123"})
        admin = login("a@s18.test", "Admin@123")

        hs = admin.post("/api/res/academic_units", json={"name": "HS", "code": "HS", "status": "active"}).json()
        lp = admin.post("/api/res/academic_units", json={"name": "LP", "code": "LP", "status": "active"}).json()
        admin.post("/api/res/classes", json={"name": "Grade 8", "academic_unit_id": hs["id"], "status": "active"})
        admin.post("/api/res/classes", json={"name": "Grade 3", "academic_unit_id": lp["id"], "status": "active"})

        hsHead = admin.post("/api/teachers", json={"name": "HSHead", "email": "hshead@s18.test", "password": "Teach@123", "status": "active"}).json()
        stranger = admin.post("/api/teachers", json={"name": "Stranger", "email": "stranger@s18.test", "password": "Teach@123", "status": "active"}).json()
        admin.post("/api/principals", json={"teacher_id": hsHead["id"], "scope_type": "units", "unit_ids": [hs["id"]], "designation": "principal"})

        g8 = admin.post("/api/res/students", json={"first_name": "Riya", "last_name": "K", "admission_no": "G8-1", "class_name": "Grade 8", "section": "A", "guardian_name": "Mr K", "guardian_phone": "9000000001", "status": "active"}).json()
        g3 = admin.post("/api/res/students", json={"first_name": "Rahul", "last_name": "P", "admission_no": "G3-1", "class_name": "Grade 3", "section": "A", "status": "active"}).json()

        # link a parent to the G8 student
        admin.post(f"/api/students/{g8['id']}/parent-user", json={"email": "rparent@s18.test", "password": "Parent@123", "name": "RP"})

        # student portal login for role test
        admin.post(f"/api/students/{g8['id']}/portal-user", json={"email": "riya@s18.test", "password": "Stud@123"})

        yield {"admin": admin, "login": login, "g8": g8["id"], "g3": g3["id"], "stranger": stranger}
    MongoClient(server.mongo_url).drop_database(TEST_DB)


def test_admin_full_payload_with_parents(ctx):
    r = ctx["admin"].get(f"/api/students/{ctx['g8']}/profile")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["student"]["admission_no"] == "G8-1"
    assert "attendance" in d and "results" in d and "upcoming_exams" in d
    assert any(p["email"] == "rparent@s18.test" for p in d["parents"])  # linked parents present


def test_in_scope_principal_allowed_out_of_scope_403(ctx):
    hs = ctx["login"]("hshead@s18.test", "Teach@123")
    assert hs.get(f"/api/students/{ctx['g8']}/profile").status_code == 200   # HS → Grade 8 ok
    assert hs.get(f"/api/students/{ctx['g3']}/profile").status_code == 403   # Grade 3 (LP) blocked


def test_unrelated_teacher_403(ctx):
    stranger = ctx["login"]("stranger@s18.test", "Teach@123")
    assert stranger.get(f"/api/students/{ctx['g8']}/profile").status_code == 403


def test_student_and_parent_roles_403(ctx):
    student = ctx["login"]("riya@s18.test", "Stud@123")
    assert student.get(f"/api/students/{ctx['g8']}/profile").status_code == 403
    parent = ctx["login"]("rparent@s18.test", "Parent@123")
    assert parent.get(f"/api/students/{ctx['g8']}/profile").status_code == 403


def test_no_storage_path_leak(ctx):
    import json
    raw = json.dumps(ctx["admin"].get(f"/api/students/{ctx['g8']}/profile").json())
    assert "lnmo/signatures" not in raw and "lnmo/seals" not in raw


def test_teacher_profile_includes_principal_scope(ctx):
    admin = ctx["admin"]
    teachers = admin.get("/api/teachers", params={"limit": 50}).json()["items"]
    hs = next(t for t in teachers if t["email"] == "hshead@s18.test")
    prof = admin.get(f"/api/teachers/{hs['id']}/profile").json()["profile"]
    assert prof["is_principal"] is True
    assert prof["principal"]["scope_type"] == "units"
    assert "HS" in prof["principal"]["unit_names"]           # resolved unit NAME, not id
    # a non-principal teacher reports is_principal false, principal null
    p2 = admin.get(f"/api/teachers/{ctx['stranger']['id']}/profile").json()["profile"]
    assert p2["is_principal"] is False
    assert p2["principal"] is None
