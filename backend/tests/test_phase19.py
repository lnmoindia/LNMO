"""Phase 19 — principal read-only governance access + personal_email OTP delivery.

- Principal may GET /res/academic_units & /res/academic_years (the Class Hub/Timetable/Exams data)
  but POST/PUT/DELETE still 403.
- OTP delivery: request with delivery_email saves personal_email + sends the code THERE (provider
  called with that address); confirm marks personal_email_verified; subsequent request defaults to
  the saved personal_email; invalid email -> 422; the LOGIN email never changes.
"""
import os, sys
import pytest

os.environ["OTP_TEST_MODE"] = "1"
sys.path.insert(0, "/app/backend")
import server  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from pymongo import MongoClient  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

TEST_DB = "lnmo_phase19_test"
PA_EMAIL = server.os.environ["PLATFORM_ADMIN_EMAIL"].lower()
PA_PW = server.os.environ["PLATFORM_ADMIN_PASSWORD"]
BASE = "https://testserver"
SENT = []  # (to, subject) capture


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
    server.OTP_TEST_MODE = True

    async def _init():
        server.client = AsyncIOMotorClient(server.mongo_url)
        server.db = server.client[TEST_DB]
    server.app.router.on_startup.insert(0, _init)
    MongoClient(server.mongo_url).drop_database(TEST_DB)
    mon = MongoClient(server.mongo_url)[TEST_DB]

    async def _fake_send(*, to, subject, html):
        SENT.append((to, subject))
        return "test-id"
    server.send_email = _fake_send

    with _client() as C:
        def login(email, pw):
            r = C.post("/api/auth/login", json={"email": email, "password": pw})
            assert r.status_code == 200, r.text
            tok = r.cookies.get("access_token"); C.cookies.clear()
            return Sess(C, tok)

        platform = login(PA_EMAIL, PA_PW)
        platform.post("/api/res/institutions", json={"name": "S19", "slug": "s19", "admin_email": "a@s19.test", "admin_password": "Admin@123"})
        admin = login("a@s19.test", "Admin@123")
        hs = admin.post("/api/res/academic_units", json={"name": "HS", "code": "HS", "status": "active"}).json()
        admin.post("/api/res/academic_years", json={"name": "2026-27", "status": "active"})
        admin.post("/api/res/classes", json={"name": "Grade 8", "academic_unit_id": hs["id"], "status": "active"})
        head = admin.post("/api/teachers", json={"name": "Head", "email": "head@s19.test", "password": "Teach@123", "status": "active"}).json()
        admin.post("/api/principals", json={"teacher_id": head["id"], "scope_type": "units", "unit_ids": [hs["id"]], "designation": "principal"})
        yield {"admin": admin, "login": login, "db": mon, "hs": hs["id"]}
    MongoClient(server.mongo_url).drop_database(TEST_DB)


def test_principal_can_read_governance_but_not_mutate(ctx):
    head = ctx["login"]("head@s19.test", "Teach@123")
    assert head.get("/api/res/academic_units", params={"limit": 200}).status_code == 200   # was 403 (the bug)
    assert head.get("/api/res/academic_years", params={"limit": 100}).status_code == 200
    # writes still blocked
    assert head.post("/api/res/academic_units", json={"name": "X", "code": "X"}).status_code == 403


def test_otp_delivery_to_personal_email(ctx):
    head = ctx["login"]("head@s19.test", "Teach@123")
    head.post("/api/profile/phone", json={"phone": "9112223334"})
    SENT.clear()
    r = head.post("/api/verify/request", json={"purpose": "phone_verify", "delivery_email": "head.personal@gmail.com"})
    assert r.status_code == 200
    assert r.json()["sent_to"] == "head.personal@gmail.com"
    assert SENT and SENT[-1][0] == "head.personal@gmail.com"      # provider called with personal email
    # personal_email saved (unverified) but LOGIN email unchanged
    u = ctx["db"].users.find_one({"email": "head@s19.test"})
    assert u["personal_email"] == "head.personal@gmail.com"
    assert u.get("personal_email_verified") in (False, None)
    assert u["email"] == "head@s19.test"                          # login never changes
    # confirm -> personal email verified
    code = r.json()["dev_code"]
    ok = head.post("/api/verify/confirm", json={"purpose": "phone_verify", "code": code})
    assert ok.status_code == 200
    u2 = ctx["db"].users.find_one({"email": "head@s19.test"})
    assert u2["personal_email_verified"] is True


def test_subsequent_request_defaults_to_saved_personal_email(ctx):
    head = ctx["login"]("head@s19.test", "Teach@123")
    head.post("/api/profile/phone", json={"phone": "9112229999"})
    SENT.clear()
    r = head.post("/api/verify/request", json={"purpose": "phone_verify"})   # no delivery_email
    assert r.status_code == 200
    assert r.json()["sent_to"] == "head.personal@gmail.com"                  # defaults to saved personal
    assert SENT[-1][0] == "head.personal@gmail.com"


def test_invalid_delivery_email_422(ctx):
    head = ctx["login"]("head@s19.test", "Teach@123")
    r = head.post("/api/verify/request", json={"purpose": "phone_verify", "delivery_email": "not-an-email"})
    assert r.status_code == 422


def test_provider_failure_returns_structured_non_5xx(ctx):
    # Simulate Resend rejecting the address: must NOT be a 5xx (Cloudflare would rewrap it).
    async def _boom(*, to, subject, html):
        raise server.EmailSendError("undeliverable")
    orig = server.send_email
    server.send_email = _boom
    try:
        head = ctx["login"]("head@s19.test", "Teach@123")
        head.post("/api/profile/phone", json={"phone": "9112220000"})
        r = head.post("/api/verify/request", json={"purpose": "phone_verify"})
        assert r.status_code == 200          # structured success envelope, never 5xx
        body = r.json()
        assert body["ok"] is False and body["sent"] is False
        assert body["reason"] == "undeliverable"
        assert "different email" in body["message"].lower()
    finally:
        server.send_email = orig
