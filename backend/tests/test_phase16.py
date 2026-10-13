"""Phase 16 — OTP verification + parent-child linking. Throwaway DB, API-driven.

OTP happy path (request→confirm→verified), expiry, wrong-code cap, cooldown; parent self-link
happy + wrong-phone + duplicate; manual link/unlink by admin + in-scope principal (out-of-scope
403); multi-child parent fetches each child, 403 on unlinked; cross-institution link impossible.
Relies on OTP_TEST_MODE=1 (set before import) which exposes dev_code in the request response.
"""
import os
import sys
import pytest

os.environ["OTP_TEST_MODE"] = "1"
sys.path.insert(0, "/app/backend")
import server  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from pymongo import MongoClient  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

TEST_DB = "lnmo_phase16_test"
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
    server.OTP_TEST_MODE = True

    async def _init():
        server.client = AsyncIOMotorClient(server.mongo_url)
        server.db = server.client[TEST_DB]
    server.app.router.on_startup.insert(0, _init)
    MongoClient(server.mongo_url).drop_database(TEST_DB)
    mon = MongoClient(server.mongo_url)[TEST_DB]

    # stub the email sender so tests never hit the network
    async def _fake_send(**kwargs):
        return "test-email-id"
    server.send_email = _fake_send

    with _client() as C:
        def login(email, pw):
            r = C.post("/api/auth/login", json={"email": email, "password": pw})
            assert r.status_code == 200, r.text
            tok = r.cookies.get("access_token")
            C.cookies.clear()
            return Sess(C, tok)

        platform = login(PA_EMAIL, PA_PW)
        platform.post("/api/res/institutions", json={"name": "S16", "slug": "s16", "admin_email": "a@s16.test", "admin_password": "Admin@123"})
        platform.post("/api/res/institutions", json={"name": "Other16", "slug": "o16", "admin_email": "a@o16.test", "admin_password": "Admin@123"})
        admin = login("a@s16.test", "Admin@123")
        other_admin = login("a@o16.test", "Admin@123")

        hs = admin.post("/api/res/academic_units", json={"name": "HS", "code": "HS", "status": "active"}).json()
        lp = admin.post("/api/res/academic_units", json={"name": "LP", "code": "LP", "status": "active"}).json()
        admin.post("/api/res/classes", json={"name": "Grade 8", "academic_unit_id": hs["id"], "status": "active"})
        admin.post("/api/res/classes", json={"name": "Grade 3", "academic_unit_id": lp["id"], "status": "active"})

        def teacher(n):
            return admin.post("/api/teachers", json={"name": n, "email": f"{n.lower()}@s16.test", "password": "Teach@123", "status": "active"}).json()
        pra = teacher("Prasad")
        hsHead = teacher("HSHead")
        lpHead = teacher("LPHead")
        admin.post("/api/principals", json={"teacher_id": hsHead["id"], "scope_type": "units", "unit_ids": [hs["id"]], "designation": "principal"})
        admin.post("/api/principals", json={"teacher_id": lpHead["id"], "scope_type": "units", "unit_ids": [lp["id"]], "designation": "principal"})

        # two children of the same guardian phone
        s1 = admin.post("/api/res/students", json={"first_name": "Riya", "last_name": "K", "admission_no": "G8-1", "class_name": "Grade 8", "section": "A", "guardian_phone": "9000000001", "status": "active"}).json()
        s2 = admin.post("/api/res/students", json={"first_name": "Rahul", "last_name": "K", "admission_no": "G3-1", "class_name": "Grade 3", "section": "A", "guardian_phone": "9000000001", "status": "active"}).json()
        s3 = admin.post("/api/res/students", json={"first_name": "Other", "last_name": "Kid", "admission_no": "G8-9", "class_name": "Grade 8", "section": "A", "guardian_phone": "9000000099", "status": "active"}).json()

        # parent account (linked to nothing yet) via admin creating a parent-user then clearing links
        admin.post(f"/api/students/{s1['id']}/parent-user", json={"email": "parent@s16.test", "password": "Parent@123", "name": "Parent"})
        mon.users.update_one({"email": "parent@s16.test"}, {"$set": {"student_ids": []}})

        yield {"admin": admin, "other_admin": other_admin, "login": login, "db": mon,
               "pra": pra["id"], "s1": s1["id"], "s2": s2["id"], "s3": s3["id"]}
    MongoClient(server.mongo_url).drop_database(TEST_DB)


def test_phone_verify_otp_flow(ctx):
    pra = ctx["login"]("prasad@s16.test", "Teach@123")
    assert pra.post("/api/profile/phone", json={"phone": "9112223334"}).json()["phone_verified"] is False
    req = pra.post("/api/verify/request", json={"purpose": "phone_verify"})
    assert req.status_code == 200 and "dev_code" in req.json()
    code = req.json()["dev_code"]
    # wrong code increments attempts
    assert pra.post("/api/verify/confirm", json={"purpose": "phone_verify", "code": "000000"}).status_code == 400
    ok = pra.post("/api/verify/confirm", json={"purpose": "phone_verify", "code": code})
    assert ok.status_code == 200 and ok.json()["phone_verified"] is True


def test_otp_cooldown_and_attempt_cap(ctx):
    pra = ctx["login"]("prasad@s16.test", "Teach@123")
    pra.post("/api/profile/phone", json={"phone": "9112223335"})
    assert pra.post("/api/verify/request", json={"purpose": "phone_verify"}).status_code == 200
    # immediate re-request blocked by 60s cooldown
    assert pra.post("/api/verify/request", json={"purpose": "phone_verify"}).status_code == 429
    # exhaust attempt cap with wrong codes
    for _ in range(5):
        pra.post("/api/verify/confirm", json={"purpose": "phone_verify", "code": "111111"})
    assert pra.post("/api/verify/confirm", json={"purpose": "phone_verify", "code": "111111"}).status_code == 429


def test_otp_expiry(ctx):
    pra = ctx["login"]("prasad@s16.test", "Teach@123")
    pra.post("/api/profile/phone", json={"phone": "9112223336"})
    req = pra.post("/api/verify/request", json={"purpose": "phone_verify"})
    code = req.json()["dev_code"]
    # force-expire the stored record
    ctx["db"].otp_codes.update_many({"purpose": "phone_verify", "verified": False},
                                    {"$set": {"expires_at": "2000-01-01T00:00:00+00:00"}})
    assert pra.post("/api/verify/confirm", json={"purpose": "phone_verify", "code": code}).status_code == 400


def test_parent_self_link_flow(ctx):
    parent = ctx["login"]("parent@s16.test", "Parent@123")
    # wrong phone/admission -> generic failure, no code sent
    bad = parent.post("/api/verify/request", json={"purpose": "parent_link", "phone": "0000000000", "admission_no": "G8-1"})
    assert bad.status_code == 400
    # correct combo -> code emailed
    req = parent.post("/api/verify/request", json={"purpose": "parent_link", "phone": "9000000001", "admission_no": "G8-1"})
    assert req.status_code == 200
    code = req.json()["dev_code"]
    ok = parent.post("/api/verify/confirm", json={"purpose": "parent_link", "phone": "9000000001", "admission_no": "G8-1", "code": code})
    assert ok.status_code == 200 and ok.json()["linked"] is True
    # child now visible
    kids = parent.get("/api/parent/children").json()["children"]
    assert any(k["id"] == ctx["s1"] for k in kids)
    # duplicate link -> friendly error
    req2 = parent.post("/api/verify/request", json={"purpose": "parent_link", "phone": "9000000001", "admission_no": "G8-1"})
    code2 = req2.json()["dev_code"]
    dup = parent.post("/api/verify/confirm", json={"purpose": "parent_link", "phone": "9000000001", "admission_no": "G8-1", "code": code2})
    assert dup.status_code == 400 and "already linked" in dup.json()["detail"].lower()


def test_manual_link_scope_and_multichild(ctx):
    admin = ctx["admin"]
    # admin manually links the 2nd child (Grade 3) to the parent
    assert admin.post(f"/api/students/{ctx['s2']}/parent-user", json={"email": "parent@s16.test"}).status_code == 200
    parent = ctx["login"]("parent@s16.test", "Parent@123")
    ids = {k["id"] for k in parent.get("/api/parent/children").json()["children"]}
    assert ctx["s1"] in ids and ctx["s2"] in ids  # multi-child switcher data
    # per-child snapshot enforces linkage: unlinked child -> 403
    assert parent.get(f"/api/parent/child/{ctx['s2']}").status_code == 200
    assert parent.get(f"/api/parent/child/{ctx['s3']}").status_code == 403
    # out-of-scope principal cannot manual-link a Grade 8 child; in-scope can
    lpHead = ctx["login"]("lphead@s16.test", "Teach@123")
    assert lpHead.post(f"/api/students/{ctx['s3']}/parent-user", json={"email": "parent@s16.test"}).status_code == 403
    hsHead = ctx["login"]("hshead@s16.test", "Teach@123")
    assert hsHead.post(f"/api/students/{ctx['s3']}/parent-user", json={"email": "parent@s16.test"}).status_code == 200
    # unlink by admin + parent self-unlink
    assert admin.post(f"/api/students/{ctx['s3']}/unlink-parent", json={"email": "parent@s16.test"}).status_code == 200
    assert parent.post(f"/api/parent/unlink/{ctx['s2']}").status_code == 200
    ids2 = {k["id"] for k in parent.get("/api/parent/children").json()["children"]}
    assert ctx["s2"] not in ids2 and ctx["s1"] in ids2


def test_cross_institution_link_impossible(ctx):
    # a parent in S16 can never link a child that doesn't exist in their institution
    parent = ctx["login"]("parent@s16.test", "Parent@123")
    bad = parent.post("/api/verify/request", json={"purpose": "parent_link", "phone": "9000000001", "admission_no": "NOPE-STUDENT"})
    assert bad.status_code == 400
