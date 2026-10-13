"""Phase 25 — Communication foundation. Throwaway DB.

stub send logs + simulated statuses; quota decrement + exhaustion block; credit request →
approve → limit increased; cross-tenant isolation; secrets masked everywhere; platform-only 403.
"""
import sys
import pytest

sys.path.insert(0, "/app/backend")
import server  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from pymongo import MongoClient  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

TEST_DB = "lnmo_phase25comm_test"
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


def _run(coro):
    import asyncio
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    old = server.db
    server.db = AsyncIOMotorClient(server.mongo_url)[TEST_DB]
    try:
        return loop.run_until_complete(coro)
    finally:
        server.db = old
        loop.close()


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
        a = platform.post("/api/res/institutions", json={"name": "SchoolA", "slug": "schoola", "admin_email": "a@a.test", "admin_password": "Admin@123"}).json()
        b = platform.post("/api/res/institutions", json={"name": "SchoolB", "slug": "schoolb", "admin_email": "a@b.test", "admin_password": "Admin@123"}).json()
        adminA = login("a@a.test", "Admin@123")
        adminB = login("a@b.test", "Admin@123")
        yield {"platform": platform, "adminA": adminA, "adminB": adminB,
               "A": a["id"], "B": b["id"], "db": mon}
    MongoClient(server.mongo_url).drop_database(TEST_DB)


def test_platform_config_masked_and_roundtrip(ctx):
    p = ctx["platform"]
    p.put("/api/platform/comm-config", json={"account_sid": "AC123456789", "auth_token": "secrettoken99", "whatsapp_sender": "+14155550123", "active_provider": "stub"})
    cfg = p.get("/api/platform/comm-config").json()
    assert cfg["twilio"]["account_sid"].endswith("6789") and "•" in cfg["twilio"]["account_sid"]
    assert cfg["twilio"]["auth_token"].endswith("n99") and "•" in cfg["twilio"]["auth_token"]
    assert "secrettoken99" not in str(cfg)  # raw secret never leaks
    assert cfg["twilio"]["whatsapp_sender"] == "+14155550123"


def test_platform_only_endpoints_403_for_admin(ctx):
    assert ctx["adminA"].get("/api/platform/comm-config").status_code == 403
    assert ctx["adminA"].get("/api/platform/comm/schools").status_code == 403


def test_stub_send_logs_and_simulated_delivered(ctx):
    res = _run(server.send_message(ctx["A"], "whatsapp",
               [{"name": "Riya", "phone": "+100"}, {"name": "Sam", "phone": "+101"}],
               body="Hello", module="test"))
    assert res["ok"] and res["sent"] == 2
    msgs = list(ctx["db"].messages.find({"institution_id": ctx["A"]}))
    assert len(msgs) == 2
    assert all(m["status"] == "delivered" for m in msgs)
    assert all([h["status"] for h in m["status_history"]] == ["queued", "sent", "delivered"] for m in msgs)


def test_quota_decrement_and_exhaustion(ctx):
    ctx["platform"].put(f"/api/platform/comm/schools/{ctx['A']}", json={"sms_limit": 1})
    res = _run(server.send_message(ctx["A"], "sms",
               [{"name": "X", "phone": "+1"}, {"name": "Y", "phone": "+2"}], body="hi", module="test"))
    assert res["sent"] == 1
    codes = [r.get("code") for r in res["results"]]
    assert "quota_exceeded" in codes
    st = ctx["adminA"].get("/api/comm/status").json()
    assert st["sms"]["used"] == 1 and st["sms"]["remaining"] == 0


def test_channel_disabled_blocks_send(ctx):
    ctx["platform"].put("/api/platform/comm-config", json={"whatsapp_enabled": False})
    res = _run(server.send_message(ctx["B"], "whatsapp", [{"name": "Z", "phone": "+9"}], body="x", module="test"))
    assert res["ok"] is False and res["code"] == "channel_disabled"
    ctx["platform"].put("/api/platform/comm-config", json={"whatsapp_enabled": True})


def test_credit_request_approve_increases_limit(ctx):
    before = ctx["adminA"].get("/api/comm/status").json()["whatsapp"]["limit"]
    req = ctx["adminA"].post("/api/comm/request-credit", json={"channel": "whatsapp", "amount": 100, "note": "event"}).json()
    assert req["status"] == "pending"
    pend = ctx["platform"].get("/api/platform/comm/requests").json()["requests"]
    assert any(r["id"] == req["id"] for r in pend)
    ap = ctx["platform"].post(f"/api/platform/comm/requests/{req['id']}/approve").json()
    assert ap["status"] == "approved" and ap["new_limit"] == before + 100
    after = ctx["adminA"].get("/api/comm/status").json()["whatsapp"]["limit"]
    assert after == before + 100


def test_cross_tenant_history_isolation(ctx):
    histA = ctx["adminA"].get("/api/comm/history").json()["messages"]
    histB = ctx["adminB"].get("/api/comm/history").json()["messages"]
    assert all(m["institution_id"] == ctx["A"] for m in histA)
    assert all(m["institution_id"] == ctx["B"] for m in histB)
    assert len(histA) >= 1


def test_sender_mode_own_masks_secret(ctx):
    st = ctx["adminB"].put("/api/comm/sender-mode", json={"sender_mode": "own", "account_sid": "ACownsecret12345", "auth_token": "ownauth9999", "whatsapp_sender": "+1999"}).json()
    assert st["connection"]["mode"] == "own"
    assert "ownauth9999" not in str(st) and "ACownsecret12345" not in str(st)
    assert st["connection"]["own_twilio"]["account_sid"].endswith("2345")
    ctx["adminB"].put("/api/comm/sender-mode", json={"sender_mode": "lnmo"})
