"""Phase 34 — Platform AI Layer master switch + enforcement hierarchy. LLM not needed (chat blocked
before any LLM call). Covers: master OFF → student chat/library 403 even when curriculum ai_enabled;
master ON → per-curriculum toggles govern; non-platform roles cannot write features (403);
features doc shape forward-compatible. Throwaway DB.
"""
import sys
import uuid
import pytest

sys.path.insert(0, "/app/backend")
import server  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from pymongo import MongoClient  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

TEST_DB = "lnmo_phase34_test"
PA_EMAIL = server.os.environ["PLATFORM_ADMIN_EMAIL"].lower()
PA_PW = server.os.environ["PLATFORM_ADMIN_PASSWORD"]
BASE = "https://testserver"
YEAR = "2025-2026"


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
            return tok

        platform = Sess(C, login(PA_EMAIL, PA_PW))
        a = platform.post("/api/res/institutions", json={"name": "S", "slug": "p34a", "admin_email": "a@p34a.test", "admin_password": "Admin@123"}).json()
        A = a["id"]
        mon.academic_years.insert_one({"id": "y1", "institution_id": A, "name": YEAR, "is_active": True})
        mon.classes.insert_one({"id": "c8", "institution_id": A, "name": "Grade 8", "academic_unit_id": "uHS"})
        mon.subject_offerings.insert_one({"id": str(uuid.uuid4()), "institution_id": A, "class_name": "Grade 8", "subject": "Mathematics"})
        sid = str(uuid.uuid4())
        mon.students.insert_one({"id": sid, "institution_id": A, "class_name": "Grade 8", "section": "A", "name": "T", "admission_no": "1"})
        uid = str(uuid.uuid4())
        mon.users.insert_one({"id": uid, "name": "T", "email": "stu@p34a.test", "password_hash": server.hash_password("Stu@123"),
                              "role": "student", "institution_id": A, "student_id": sid, "status": "active", "must_change_password": False, "created_at": server.now_iso()})
        # a published + ai_enabled curriculum (so per-curriculum is ON; only the platform layer gates it)
        cid = str(uuid.uuid4())
        mon.curricula.insert_one({"id": cid, "institution_id": A, "academic_year": YEAR, "class_name": "Grade 8",
                                  "subject": "Mathematics", "name": "G8 Maths", "status": "published",
                                  "ai_enabled": True, "is_deleted": False, "created_at": server.now_iso()})
        mon.curriculum_items.insert_one({"id": str(uuid.uuid4()), "curriculum_id": cid, "institution_id": A,
                                         "item_type": "notes", "chapter": "Algebra", "title": "N", "text_content": "x",
                                         "status": "approved", "active": True, "contributed_at": server.now_iso()})
        S = Sess(C, login("stu@p34a.test", "Stu@123"))
        yield {"platform": platform, "S": S, "A": A, "db": mon}
    MongoClient(server.mongo_url).drop_database(TEST_DB)


def test_master_off_by_default_blocks_student(ctx):
    # default: no features → layer OFF → chat + library 403 even though curriculum ai_enabled=True
    r = ctx["S"].post("/api/ai/tutor/chat", json={"subject": "Mathematics", "message": "hi"})
    assert r.status_code == 403 and "not available for your school" in r.json()["detail"]
    lib = ctx["S"].get("/api/ai/library")
    assert lib.status_code == 403
    subs = ctx["S"].get("/api/ai/tutor/subjects").json()
    assert subs["ai_layer_enabled"] is False
    assert all(s["enabled"] is False for s in subs["subjects"])  # toggles overridden by master OFF


def test_non_platform_cannot_write_features(ctx):
    # the school admin is not a platform admin
    admin = Sess(ctx["S"]._c, ctx["S"]._c.post("/api/auth/login", json={"email": "a@p34a.test", "password": "Admin@123"}).cookies.get("access_token"))
    ctx["S"]._c.cookies.clear()
    r = admin.put(f"/api/platform/institutions/{ctx['A']}/features", json={"ai_layer_enabled": True})
    assert r.status_code == 403


def test_platform_enables_layer_then_toggles_govern(ctx):
    r = ctx["platform"].put(f"/api/platform/institutions/{ctx['A']}/features", json={"ai_layer_enabled": True})
    assert r.status_code == 200 and r.json()["features"]["ai_layer_enabled"] is True
    # now the master is ON → per-curriculum ai_enabled governs → Mathematics is enabled
    subs = ctx["S"].get("/api/ai/tutor/subjects").json()
    assert subs["ai_layer_enabled"] is True
    assert any(s["subject"] == "Mathematics" and s["enabled"] for s in subs["subjects"])
    # library now returns (approved material visible)
    assert ctx["S"].get("/api/ai/library").status_code == 200
    # a subject whose curriculum is NOT ai_enabled stays disabled even with master ON
    ctx["db"].curricula.update_one({"institution_id": ctx["A"], "subject": "Mathematics"}, {"$set": {"ai_enabled": False}})
    subs2 = ctx["S"].get("/api/ai/tutor/subjects").json()
    assert all(not s["enabled"] for s in subs2["subjects"])  # school toggle governs when master ON
    # restore for summary test
    ctx["db"].curricula.update_one({"institution_id": ctx["A"], "subject": "Mathematics"}, {"$set": {"ai_enabled": True}})


def test_ai_summary_and_forward_compatible_shape(ctx):
    s = ctx["platform"].get(f"/api/platform/institutions/{ctx['A']}/ai").json()
    assert s["features"]["ai_layer_enabled"] is True
    assert s["summary"]["curricula"] >= 1 and s["summary"]["ai_enabled_curricula"] >= 1
    assert "tutor_messages_month" in s["summary"]
    # features is a dict (forward-compatible: future keys like elsa/risk_detection slot in alongside)
    doc = ctx["db"].institutions.find_one({"id": ctx["A"]})
    assert isinstance(doc.get("features"), dict) and "ai_layer_enabled" in doc["features"]
