"""Phase 26 — Communication part 2: templates, send flows, delivery webhooks. Throwaway DB.

Covers: template substitution + variable whitelist (injection-safe); WhatsApp free-text blocked /
SMS free-text ok; pending template blocked on WhatsApp; recipient resolution + skipped count;
unit-principal out-of-scope target → 403; quota pre-check + insufficient block; webhook status
transitions (queued→delivered→read) + idempotent repeat; secure-link roundtrip.
"""
import sys
import uuid
import pytest

sys.path.insert(0, "/app/backend")
import server  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from pymongo import MongoClient  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

TEST_DB = "lnmo_phase26comm_test"
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
        a = platform.post("/api/res/institutions", json={"name": "SchoolA", "slug": "p26a", "admin_email": "a@p26a.test", "admin_password": "Admin@123"}).json()
        A = a["id"]
        adminA = login("a@p26a.test", "Admin@123")

        mon.classes.insert_many([
            {"id": "cl-g8", "institution_id": A, "name": "Grade 8", "academic_unit_id": "unitHS", "academic_unit_name": "HS"},
            {"id": "cl-g1", "institution_id": A, "name": "Grade 1", "academic_unit_id": "unitLP", "academic_unit_name": "LP"},
        ])
        mon.students.insert_many([
            {"id": "st1", "institution_id": A, "first_name": "Riya", "last_name": "K", "class_name": "Grade 8", "section": "A", "enrollment_status": "enrolled", "guardian_name": "Mr K", "guardian_phone": "9847000001"},
            {"id": "st2", "institution_id": A, "first_name": "Sam", "last_name": "P", "class_name": "Grade 8", "section": "A", "enrollment_status": "enrolled", "guardian_name": "Mrs P", "guardian_phone": "9847000002"},
            {"id": "st3", "institution_id": A, "first_name": "No", "last_name": "Phone", "class_name": "Grade 8", "section": "A", "enrollment_status": "enrolled", "guardian_name": "Mr NP"},
        ])
        puid = str(uuid.uuid4())
        mon.users.insert_one({"id": puid, "name": "LP Principal", "email": "lpprin@p26a.test",
                              "password_hash": server.hash_password("Prin@123"), "role": "teacher",
                              "institution_id": A, "status": "active", "must_change_password": False,
                              "created_at": server.now_iso()})
        mon.principal_assignments.insert_one({"id": str(uuid.uuid4()), "user_id": puid, "institution_id": A,
                                              "scope_type": "units", "unit_ids": ["unitLP"], "status": "active",
                                              "designation": "principal", "created_at": server.now_iso()})
        principal = login("lpprin@p26a.test", "Prin@123")

        yield {"platform": platform, "adminA": adminA, "principal": principal, "A": A, "db": mon}
    MongoClient(server.mongo_url).drop_database(TEST_DB)


def _wa_template(ctx):
    rows = ctx["adminA"].get("/api/comm/templates").json()["templates"]
    return next(t for t in rows if t["name"] == "Announcement")  # approved, channel both


def test_template_substitution_and_variable_whitelist():
    body = "Hi {{parent_name}}, {{school_name}} note for {{class}}. {{evil}} {{__proto__}}"
    out = server._render_template(body, {"parent_name": "Mr K", "school_name": "SchoolA", "class": "Grade 8", "evil": "IGNORED"})
    assert "Mr K" in out and "SchoolA" in out and "Grade 8" in out
    assert "{{evil}}" in out and "{{__proto__}}" in out and "IGNORED" not in out


def test_whatsapp_free_text_blocked(ctx):
    r = ctx["adminA"].post("/api/comm/send", json={"channel": "whatsapp", "body": "free text",
                                                   "target": {"class_ids": ["cl-g8"]}})
    assert r.status_code == 400 and "template" in r.json()["detail"].lower()


def test_sms_free_text_ok(ctx):
    r = ctx["adminA"].post("/api/comm/send", json={"channel": "sms", "body": "Dear {{parent_name}}, hello",
                                                   "target": {"class_ids": ["cl-g8"]}})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["sent"] == 2 and d["skipped_count"] == 1


def test_pending_template_blocked_on_whatsapp_but_sms_ok(ctx):
    t = ctx["platform"].post("/api/platform/comm/templates", json={
        "name": "Pending Promo", "category": "general", "channel": "both", "body": "Hi {{parent_name}}"}).json()
    ctx["platform"].put(f"/api/platform/comm/templates/{t['id']}", json={"status": "pending"})
    wa = ctx["adminA"].post("/api/comm/send", json={"channel": "whatsapp", "template_id": t["id"],
                                                    "target": {"class_ids": ["cl-g8"]}})
    assert wa.status_code == 400 and "approved" in wa.json()["detail"].lower()
    sms = ctx["adminA"].post("/api/comm/send", json={"channel": "sms", "template_id": t["id"],
                                                     "target": {"class_ids": ["cl-g8"]}})
    assert sms.status_code == 200 and sms.json()["sent"] == 2


def test_recipient_resolution_dry_run_skipped(ctx):
    t = _wa_template(ctx)
    r = ctx["adminA"].post("/api/comm/send", json={"channel": "whatsapp", "template_id": t["id"],
                                                   "target": {"class_ids": ["cl-g8"]}, "dry_run": True})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["dry_run"] and d["recipient_count"] == 2 and d["skipped_count"] == 1
    assert len(d["skipped"]) == 1 and d["skipped"][0]["student_name"] == "No Phone"


def test_unit_principal_out_of_scope_target_403(ctx):
    t = _wa_template(ctx)
    r = ctx["principal"].post("/api/comm/send", json={"channel": "whatsapp", "template_id": t["id"],
                                                      "target": {"class_ids": ["cl-g8"]}, "dry_run": True})
    assert r.status_code == 403


def test_quota_precheck_insufficient_block(ctx):
    t = _wa_template(ctx)
    ctx["platform"].put(f"/api/platform/comm/schools/{ctx['A']}", json={"whatsapp_limit": 1})
    r = ctx["adminA"].post("/api/comm/send", json={"channel": "whatsapp", "template_id": t["id"],
                                                   "target": {"class_ids": ["cl-g8"]}})
    assert r.status_code == 400 and "quota" in r.json()["detail"].lower()
    ctx["platform"].put(f"/api/platform/comm/schools/{ctx['A']}", json={"whatsapp_limit": 1000})


def test_webhook_status_transitions_and_idempotent(ctx):
    t = _wa_template(ctx)
    sent = ctx["adminA"].post("/api/comm/send", json={"channel": "whatsapp", "template_id": t["id"],
                                                      "target": {"class_ids": ["cl-g8"]}}).json()
    assert sent["sent"] == 2
    mid = sent["results"][0]["message_id"]
    w1 = ctx["platform"].post("/api/comm/webhook/twilio", json={"message_id": mid, "status": "read"})
    assert w1.status_code == 200 and w1.json()["status"] == "read"
    msg = ctx["db"].messages.find_one({"id": mid})
    assert msg["status"] == "read"
    hist_len = len(msg["status_history"])
    w2 = ctx["platform"].post("/api/comm/webhook/twilio", json={"message_id": mid, "status": "read"})
    assert w2.status_code == 200 and w2.json().get("idempotent") is True
    assert len(ctx["db"].messages.find_one({"id": mid})["status_history"]) == hist_len


def test_secure_link_roundtrip():
    tok = server._make_secure_link("inst1", "report:123")
    data = server._verify_secure_link(tok)
    assert data and data["iid"] == "inst1" and data["ref"] == "report:123"
    assert server._verify_secure_link(tok + "x") is None
