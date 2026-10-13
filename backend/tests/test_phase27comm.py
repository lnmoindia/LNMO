"""Phase 27 — Communication part 3: inbound + media + secure document links. Throwaway DB.

Covers: secure-link sign/verify/expiry/tamper + file serving via /api/comm/dl; inbound webhook
school+contact routing (LNMO-managed vs own sender) + unknown-number parking; report-card send
flow (stub) stores PDF + mints secure link + writes message row; SMS uses link (no media) vs
WhatsApp uses media; history direction filter.
"""
import sys
import time
import uuid
import pytest

sys.path.insert(0, "/app/backend")
import server  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from pymongo import MongoClient  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

TEST_DB = "lnmo_phase27comm_test"
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
            tok = r.cookies.get("access_token"); C.cookies.clear()
            return Sess(C, tok)

        platform = login(PA_EMAIL, PA_PW)
        a = platform.post("/api/res/institutions", json={"name": "SchoolA", "slug": "p27a", "admin_email": "a@p27a.test", "admin_password": "Admin@123"}).json()
        b = platform.post("/api/res/institutions", json={"name": "SchoolB", "slug": "p27b", "admin_email": "a@p27b.test", "admin_password": "Admin@123"}).json()
        A, B = a["id"], b["id"]
        adminA = login("a@p27a.test", "Admin@123")

        mon.classes.insert_one({"id": "cl-g8", "institution_id": A, "name": "Grade 8", "academic_unit_id": "u1", "academic_unit_name": "HS"})
        mon.students.insert_many([
            {"id": "st1", "institution_id": A, "first_name": "Riya", "last_name": "K", "class_name": "Grade 8", "section": "A", "enrollment_status": "enrolled", "guardian_name": "Mr K", "guardian_phone": "9000000001"},
            {"id": "st2", "institution_id": A, "first_name": "No", "last_name": "Phone", "class_name": "Grade 8", "section": "A", "enrollment_status": "enrolled", "guardian_name": "Mr NP"},
        ])
        # SchoolB uses its OWN Twilio sender number (for inbound routing test)
        mon.institutions.update_one({"id": B}, {"$set": {"comm.own_twilio.whatsapp_sender": "+1555000999"}})
        mon.students.insert_one({"id": "stB", "institution_id": B, "first_name": "Bina", "last_name": "B", "class_name": "Grade 1", "section": "A", "enrollment_status": "enrolled", "guardian_name": "Mrs B", "guardian_phone": "9000000777"})
        # LNMO-managed sender number on platform config
        mon.platform_config.update_one({"id": "singleton"}, {"$set": {"twilio.whatsapp_sender": "+1555000111"}}, upsert=True)

        yield {"platform": platform, "adminA": adminA, "A": A, "B": B, "db": mon, "C": C}
    MongoClient(server.mongo_url).drop_database(TEST_DB)


def test_secure_link_sign_verify_expiry_tamper():
    tok = server._make_secure_link("iid1", "ref1", ttl_hours=72, path="lnmo/x/y.pdf", ct="application/pdf")
    data = server._verify_secure_link(tok)
    assert data["iid"] == "iid1" and data["path"] == "lnmo/x/y.pdf" and data["ct"] == "application/pdf"
    assert server._verify_secure_link(tok + "z") is None               # tampered
    expired = server._make_secure_link("iid1", "ref1", ttl_hours=-1)    # already expired
    assert server._verify_secure_link(expired) is None


def test_dl_serves_stored_file(ctx):
    # store a file via the real object storage, mint a token, fetch through dl (no auth header)
    path = f"lnmo/test/{uuid.uuid4()}.txt"
    server._put_object(path, b"hello-secure-doc", "text/plain")
    tok = server._make_secure_link(ctx["A"], "t", 72, path, "text/plain")
    r = ctx["C"].get(f"/api/comm/dl/{tok}")
    assert r.status_code == 200 and r.content == b"hello-secure-doc"
    # tampered token → 410
    assert ctx["C"].get(f"/api/comm/dl/{tok}x").status_code == 410


def test_inbound_lnmo_managed_routes_by_contact(ctx):
    # LNMO-managed sender (+1555000111) → school inferred from the matched guardian contact
    r = ctx["C"].post("/api/comm/webhook/inbound", json={
        "From": "whatsapp:9000000001", "To": "whatsapp:+1555000111", "Body": "Thanks!"})
    assert r.status_code == 200
    d = r.json()
    assert d["matched"] is True and d["institution_id"] == ctx["A"]
    assert d["contact"]["type"] == "guardian" and d["contact"]["student_id"] == "st1"
    row = ctx["db"].messages.find_one({"institution_id": ctx["A"], "direction": "inbound", "from_phone": "9000000001"})
    assert row and row["body"] == "Thanks!"


def test_inbound_own_sender_routes_to_that_school(ctx):
    r = ctx["C"].post("/api/comm/webhook/inbound", json={
        "From": "whatsapp:9000000777", "To": "whatsapp:+1555000999", "Body": "Hi from B"})
    assert r.status_code == 200 and r.json()["institution_id"] == ctx["B"]


def test_inbound_unknown_number_parked(ctx):
    r = ctx["C"].post("/api/comm/webhook/inbound", json={
        "From": "whatsapp:9111111111", "To": "whatsapp:+1555000111", "Body": "who?"})
    assert r.status_code == 200
    d = r.json()
    assert d["matched"] is False and d["institution_id"] is None
    assert ctx["db"].messages.find_one({"institution_id": None, "from_phone": "9111111111"}) is not None


def test_history_direction_filter(ctx):
    inbound = ctx["adminA"].get("/api/comm/history?direction=inbound").json()["messages"]
    assert len(inbound) >= 1 and all(m["direction"] == "inbound" for m in inbound)
    outbound = ctx["adminA"].get("/api/comm/history?direction=outbound").json()["messages"]
    assert all(m["direction"] == "outbound" for m in outbound)


def test_report_card_whatsapp_media(ctx):
    r = ctx["adminA"].post("/api/comm/send-report-card", json={"student_id": "st1", "channel": "whatsapp"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["sent"] == 1 and "/api/comm/dl/" in d["secure_link"]
    msg = ctx["db"].messages.find_one({"institution_id": ctx["A"], "module": "report_card",
                                       "recipient_student_id": "st1", "channel": "whatsapp"})
    assert msg and msg["has_media"] is True and msg["media_url"] == d["secure_link"]
    # the minted link actually serves a PDF
    tok = d["secure_link"].split("/api/comm/dl/")[1]
    served = ctx["C"].get(f"/api/comm/dl/{tok}")
    assert served.status_code == 200 and served.content[:5] == b"%PDF-"


def test_report_card_sms_uses_link_not_media(ctx):
    r = ctx["adminA"].post("/api/comm/send-report-card", json={"student_id": "st1", "channel": "sms"})
    assert r.status_code == 200
    msg = ctx["db"].messages.find_one({"institution_id": ctx["A"], "module": "report_card",
                                       "recipient_student_id": "st1", "channel": "sms"})
    assert msg["has_media"] is False and msg["media_url"] is None
    assert "/api/comm/dl/" in (msg["body"] or "")  # secure link embedded in the SMS text


def test_report_card_no_guardian_phone_400(ctx):
    r = ctx["adminA"].post("/api/comm/send-report-card", json={"student_id": "st2", "channel": "whatsapp"})
    assert r.status_code == 400 and "guardian phone" in r.json()["detail"].lower()
