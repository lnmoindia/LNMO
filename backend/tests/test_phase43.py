"""Phase 43 — Crash analytics + issue reporting.
Throwaway DB; object storage mocked. Covers: crash dedupe by signature (2 posts → 1 row, count 2);
unauthenticated crash accepted; IP rate-limit (throttle) behavior; issue create + screenshot
constraints; platform-only list (institution admin 403 on global, 200 own-school report view);
status transitions + note.
"""
import sys
import uuid
import pytest

sys.path.insert(0, "/app/backend")
import server  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from pymongo import MongoClient  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

TEST_DB = "lnmo_phase43_test"
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
        return self._c.request(m, p, headers={**self._h, **k.pop("headers", {})}, **k)

    def get(self, p, **k): return self._call("get", p, **k)
    def post(self, p, **k): return self._call("post", p, **k)
    def put(self, p, **k): return self._call("put", p, **k)


@pytest.fixture(scope="module")
def ctx(monkeymodule):
    async def _init():
        server.client = AsyncIOMotorClient(server.mongo_url)
        server.db = server.client[TEST_DB]
    server.app.router.on_startup.insert(0, _init)
    MongoClient(server.mongo_url).drop_database(TEST_DB)
    mon = MongoClient(server.mongo_url)[TEST_DB]
    store = {}
    monkeymodule.setattr(server, "_put_object", lambda path, data, ct: (store.__setitem__(path, (data, ct)), {"path": path})[-1])
    monkeymodule.setattr(server, "_get_object", lambda path: store.get(path, (b"", "image/png")))

    with _client() as C:
        def login(email, pw):
            r = C.post("/api/auth/login", json={"email": email, "password": pw})
            assert r.status_code == 200, r.text
            tok = r.cookies.get("access_token"); C.cookies.clear()
            return tok

        platform = Sess(C, login(PA_EMAIL, PA_PW))
        A = platform.post("/api/res/institutions", json={"name": "Supp", "slug": "p43",
                          "admin_email": "a@p43.test", "admin_password": "Admin@123"}).json()["id"]
        admin = Sess(C, login("a@p43.test", "Admin@123"))
        # a student-role portal user
        suid = str(uuid.uuid4())
        mon.users.insert_one({"id": suid, "name": "Pupil", "email": "s@p43.test",
                              "password_hash": server.hash_password("Stud@123"), "role": "student",
                              "institution_id": A, "status": "active", "must_change_password": False,
                              "created_at": server.now_iso()})
        student = Sess(C, login("s@p43.test", "Stud@123"))
        yield {"C": C, "platform": platform, "admin": admin, "student": student, "A": A, "db": mon}
    MongoClient(server.mongo_url).drop_database(TEST_DB)


def test_crash_dedupe_by_signature(ctx):
    C, db = ctx["C"], ctx["db"]
    payload = {"message": "Boom at X", "stack": "at foo (app.js:10:5)\nat bar (app.js:2:1)",
               "page_url": "https://x/app", "route": "/app"}
    r1 = C.post("/api/support/crash", json=payload)
    assert r1.status_code == 200 and r1.json()["deduped"] is False
    r2 = C.post("/api/support/crash", json=payload)
    assert r2.status_code == 200 and r2.json()["deduped"] is True and r2.json()["occurrence_count"] == 2
    sig = r1.json()["id"]
    rows = list(db.issues.find({"type": "crash", "title": "Boom at X"}))
    assert len(rows) == 1 and rows[0]["occurrence_count"] == 2 and rows[0]["error_signature"]
    # a different signature creates a new row
    r3 = C.post("/api/support/crash", json={**payload, "message": "Totally different"})
    assert r3.json()["deduped"] is False
    assert db.issues.count_documents({"type": "crash"}) == 2


def test_crash_unauthenticated_accepted(ctx):
    C, db = ctx["C"], ctx["db"]
    C.cookies.clear()
    r = C.post("/api/support/crash", json={"message": "anon crash", "stack": "at z (a.js:1:1)"})
    assert r.status_code == 200
    row = db.issues.find_one({"title": "anon crash"})
    assert row["role"] == "anonymous" and row["institution_id"] is None and row["user_id"] is None


def test_crash_rate_limit(ctx, monkeymodule):
    C = ctx["C"]
    monkeymodule.setattr(server, "CRASH_RATE_MAX", 3)
    server._rate_buckets.pop("crash", None)
    codes = [C.post("/api/support/crash", json={"message": f"rl {i}", "stack": "x"}).status_code for i in range(4)]
    assert codes[:3] == [200, 200, 200] and codes[3] == 429


def test_issue_create_and_screenshot_constraints(ctx):
    student, db = ctx["student"], ctx["db"]
    # plain report (no screenshot)
    r = student.post("/api/support/issues", data={"title": "Marks not showing", "description": "blank page",
                     "category": "bug", "page_url": "https://x/portal", "route": "/portal"})
    assert r.status_code == 200 and r.json()["status"] == "open"
    doc = db.issues.find_one({"id": r.json()["id"]})
    assert doc["type"] == "report" and doc["institution_id"] == ctx["A"] and doc["role"] == "student"
    # with a valid screenshot
    r2 = student.post("/api/support/issues", data={"title": "With shot", "category": "bug"},
                      files={"screenshot": ("s.png", b"\x89PNG fakebytes", "image/png")})
    assert r2.status_code == 200 and db.issues.find_one({"id": r2.json()["id"]})["screenshot_path"]
    # non-image rejected
    bad = student.post("/api/support/issues", data={"title": "pdf", "category": "bug"},
                       files={"screenshot": ("s.pdf", b"%PDF", "application/pdf")})
    assert bad.status_code == 400
    # oversize rejected (>5MB)
    big = student.post("/api/support/issues", data={"title": "big", "category": "bug"},
                       files={"screenshot": ("big.png", b"x" * (5 * 1024 * 1024 + 1), "image/png")})
    assert big.status_code == 400
    # invalid category rejected
    assert student.post("/api/support/issues", data={"title": "t", "category": "nope"}).status_code == 400


def test_platform_only_list_and_school_view(ctx):
    platform, admin = ctx["platform"], ctx["admin"]
    # platform sees the global list (crashes + reports)
    allr = platform.get("/api/support/issues").json()["issues"]
    assert any(i["type"] == "crash" for i in allr) and any(i["type"] == "report" for i in allr)
    # institution admin is forbidden on the global list
    assert admin.get("/api/support/issues").status_code == 403
    assert admin.get("/api/support/issues/stats").status_code == 403
    # institution admin gets a read-only view of OWN school's REPORTS only (no crashes)
    mine = admin.get("/api/support/my-school-issues")
    assert mine.status_code == 200
    kinds = {i["type"] for i in mine.json()["issues"]}
    assert kinds == {"report"} and all(i["institution_id"] == ctx["A"] for i in mine.json()["issues"])


def test_status_transitions_and_note(ctx):
    platform, db = ctx["platform"], ctx["db"]
    iid = db.issues.find_one({"type": "report", "title": "Marks not showing"})["id"]
    r = platform.put(f"/api/support/issues/{iid}", json={"status": "in_progress"})
    assert r.status_code == 200 and r.json()["status"] == "in_progress"
    r2 = platform.put(f"/api/support/issues/{iid}", json={"status": "resolved", "platform_note": "fixed in build 42"})
    assert r2.json()["status"] == "resolved" and r2.json()["platform_note"] == "fixed in build 42"
    assert r2.json()["resolved_by"] and r2.json()["resolved_at"]
    # invalid status rejected
    assert platform.put(f"/api/support/issues/{iid}", json={"status": "banana"}).status_code == 400
