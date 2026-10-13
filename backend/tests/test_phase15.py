"""Phase 15 — Profiles: photos + signature/seal vault. Throwaway DB, API-driven.

Covers: profile photo upload/fetch + role rules; signature VAULT (owner 200, admin 200,
out-of-scope principal 403, student/parent 403); seal upload (admin + principal, teacher 403);
teacher-profile field filtering (student sees no phone/email); no public leak of vault paths.
"""
import io
import sys
import pytest

sys.path.insert(0, "/app/backend")
import server  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from pymongo import MongoClient  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

TEST_DB = "lnmo_phase15_test"
PA_EMAIL = server.os.environ["PLATFORM_ADMIN_EMAIL"].lower()
PA_PW = server.os.environ["PLATFORM_ADMIN_PASSWORD"]
BASE = "https://testserver"

# 1x1 PNG
PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
       b"\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82")


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
    def delete(self, p, **k): return self._call("delete", p, **k)


def _png(name="sig.png"):
    return {"file": (name, io.BytesIO(PNG), "image/png")}


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
        platform.post("/api/res/institutions", json={"name": "S15", "slug": "s15", "admin_email": "a@s15.test", "admin_password": "Admin@123"})
        admin = login("a@s15.test", "Admin@123")
        hs = admin.post("/api/res/academic_units", json={"name": "HS", "code": "HS", "status": "active"}).json()
        lp = admin.post("/api/res/academic_units", json={"name": "LP", "code": "LP", "status": "active"}).json()
        admin.post("/api/res/classes", json={"name": "Grade 8", "academic_unit_id": hs["id"], "status": "active"})
        admin.post("/api/res/classes", json={"name": "Grade 3", "academic_unit_id": lp["id"], "status": "active"})

        def teacher(n):
            return admin.post("/api/teachers", json={"name": n, "email": f"{n.lower()}@s15.test", "password": "Teach@123", "phone": "999000", "status": "active"}).json()
        pra = teacher("Prasad")   # HS Grade 8 subject teacher
        other = teacher("Other")
        hsHead = teacher("HSHead")
        lpHead = teacher("LPHead")
        admin.post("/api/res/subjects", json={"name": "Maths", "status": "active"})
        admin.post("/api/res/teacher_assignments", json={"teacher_email": "prasad@s15.test", "class_name": "Grade 8", "section": "A", "subject": "Maths", "status": "active"})
        admin.post("/api/principals", json={"teacher_id": hsHead["id"], "scope_type": "units", "unit_ids": [hs["id"]], "designation": "principal"})
        admin.post("/api/principals", json={"teacher_id": lpHead["id"], "scope_type": "units", "unit_ids": [lp["id"]], "designation": "principal"})

        st = admin.post("/api/res/students", json={"first_name": "Riya", "last_name": "K", "admission_no": "G8A1", "class_name": "Grade 8", "section": "A", "status": "active"}).json()
        admin.post(f"/api/students/{st['id']}/portal-user", json={"email": "stud@s15.test", "password": "Stud@123"})

        yield {"admin": admin, "login": login, "db": mon, "pra": pra["id"], "other": other["id"]}
    MongoClient(server.mongo_url).drop_database(TEST_DB)


def test_profile_photo_upload_and_rules(ctx):
    pra = ctx["login"]("prasad@s15.test", "Teach@123")
    assert pra.post("/api/profile/photo", files=_png("me.png")).status_code == 200
    # self fetch
    assert pra.get(f"/api/users/{ctx['pra']}/photo").status_code == 200
    # student may view a TEACHER's photo (public-ish face)
    student = ctx["login"]("stud@s15.test", "Stud@123")
    assert student.get(f"/api/users/{ctx['pra']}/photo").status_code == 200
    # bad type rejected
    bad = pra.post("/api/profile/photo", files={"file": ("x.gif", io.BytesIO(b"GIF89a"), "image/gif")})
    assert bad.status_code == 400


def test_signature_vault_access(ctx):
    pra = ctx["login"]("prasad@s15.test", "Teach@123")
    assert pra.post("/api/profile/signature", files=_png()).status_code == 200
    # owner
    assert pra.get("/api/profile/signature").status_code == 200
    assert pra.get(f"/api/users/{ctx['pra']}/signature").status_code == 200
    # admin
    assert ctx["admin"].get(f"/api/users/{ctx['pra']}/signature").status_code == 200
    # in-scope principal (HS) ok; out-of-scope principal (LP) 403
    hsHead = ctx["login"]("hshead@s15.test", "Teach@123")
    lpHead = ctx["login"]("lphead@s15.test", "Teach@123")
    assert hsHead.get(f"/api/users/{ctx['pra']}/signature").status_code == 200
    assert lpHead.get(f"/api/users/{ctx['pra']}/signature").status_code == 403
    # student/parent NEVER
    student = ctx["login"]("stud@s15.test", "Stud@123")
    assert student.get(f"/api/users/{ctx['pra']}/signature").status_code == 403
    # students cannot even upload a signature (role gate)
    assert student.post("/api/profile/signature", files=_png()).status_code == 403


def test_seal_upload_permissions(ctx):
    # admin uploads seal
    assert ctx["admin"].post("/api/institution/seal", files=_png("seal.png")).status_code == 200
    assert ctx["admin"].get("/api/institution/seal").status_code == 200
    # any principal can upload + fetch
    hsHead = ctx["login"]("hshead@s15.test", "Teach@123")
    assert hsHead.post("/api/institution/seal", files=_png("seal2.png")).status_code == 200
    assert hsHead.get("/api/institution/seal").status_code == 200
    # a plain teacher cannot
    other = ctx["login"]("other@s15.test", "Teach@123")
    assert other.post("/api/institution/seal", files=_png()).status_code == 403
    assert other.get("/api/institution/seal").status_code == 403
    # student cannot
    student = ctx["login"]("stud@s15.test", "Stud@123")
    assert student.get("/api/institution/seal").status_code == 403


def test_teacher_profile_field_filtering(ctx):
    # admin → full (email + phone present)
    full = ctx["admin"].get(f"/api/teachers/{ctx['pra']}/profile").json()
    assert full["full"] is True and full["profile"]["email"] and full["profile"]["phone"]
    assert "assignments" in full["profile"]
    # student → limited (no email/phone, but name + subjects)
    student = ctx["login"]("stud@s15.test", "Stud@123")
    lim = student.get(f"/api/teachers/{ctx['pra']}/profile").json()
    assert lim["full"] is False
    assert "email" not in lim["profile"] and "phone" not in lim["profile"]
    assert lim["profile"]["name"] and "Maths" in lim["profile"]["subjects"]
    # out-of-scope principal (LP) → limited for an HS teacher
    lpHead = ctx["login"]("lphead@s15.test", "Teach@123")
    assert lpHead.get(f"/api/teachers/{ctx['pra']}/profile").json()["full"] is False


def test_no_public_vault_leak(ctx):
    # public endpoints must not accept or leak vault paths; auth required
    c = _client()
    assert c.get(f"/api/users/{ctx['pra']}/signature").status_code == 401
    assert c.get("/api/institution/seal").status_code == 401
    assert c.get(f"/api/users/{ctx['pra']}/photo").status_code == 401
    # /auth/me never exposes signature_path
    pra = ctx["login"]("prasad@s15.test", "Teach@123")
    me = pra.get("/api/auth/me").json()
    assert "signature_path" not in me and me.get("has_signature") is True and me.get("has_photo") is True
