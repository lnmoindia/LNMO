"""Phase 23 — Homework/assignment monitoring dashboards + due reminders. Throwaway DB, API-driven.

monitor aggregation correctness, unit-principal scoping, reminder job (tomorrow-due only,
idempotent, skips closed), manual reminder dedupe.
"""
import sys, io, asyncio
from datetime import datetime, timezone, timedelta
import pytest

sys.path.insert(0, "/app/backend")
import server  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from pymongo import MongoClient  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

TEST_DB = "lnmo_phase23_test"
PA_EMAIL = server.os.environ["PLATFORM_ADMIN_EMAIL"].lower()
PA_PW = server.os.environ["PLATFORM_ADMIN_PASSWORD"]
BASE = "https://testserver"
PDF = b"%PDF-1.4 test\n"


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


def _tomorrow():
    return (datetime.now(timezone.utc).date() + timedelta(days=1)).isoformat()


@pytest.fixture(scope="module")
def ctx():
    async def _init():
        server.client = AsyncIOMotorClient(server.mongo_url)
        server.db = server.client[TEST_DB]
    server.app.router.on_startup.insert(0, _init)
    MongoClient(server.mongo_url).drop_database(TEST_DB)
    mon = MongoClient(server.mongo_url)[TEST_DB]
    store = {}
    server._put_object = lambda path, data, ctype: store.__setitem__(path, (data, ctype)) or {"path": path}
    server._get_object = lambda path: store[path]

    with _client() as C:
        def login(email, pw):
            r = C.post("/api/auth/login", json={"email": email, "password": pw})
            assert r.status_code == 200, r.text
            tok = r.cookies.get("access_token"); C.cookies.clear()
            return Sess(C, tok)

        platform = login(PA_EMAIL, PA_PW)
        platform.post("/api/res/institutions", json={"name": "S23", "slug": "s23", "admin_email": "a@s23.test", "admin_password": "Admin@123"})
        admin = login("a@s23.test", "Admin@123")
        hs = admin.post("/api/res/academic_units", json={"name": "HS", "code": "HS", "status": "active"}).json()
        lp = admin.post("/api/res/academic_units", json={"name": "LP", "code": "LP", "status": "active"}).json()
        admin.post("/api/res/academic_years", json={"name": "2026-27", "status": "active"})
        admin.post("/api/res/classes", json={"name": "Grade 8", "academic_unit_id": hs["id"], "status": "active"})
        admin.post("/api/res/classes", json={"name": "Grade 3", "academic_unit_id": lp["id"], "status": "active"})
        admin.post("/api/res/sections", json={"name": "A", "class_name": "Grade 8", "status": "active"})
        admin.post("/api/res/sections", json={"name": "A", "class_name": "Grade 3", "status": "active"})

        def teacher(n):
            return admin.post("/api/teachers", json={"name": n, "email": f"{n.lower()}@s23.test", "password": "Teach@123", "status": "active"}).json()
        maths = teacher("Maths")       # HS Grade 8 Maths
        lphead = teacher("LPHead")     # LP principal
        admin.post("/api/res/teacher_assignments", json={"teacher_id": maths["id"], "teacher_email": "maths@s23.test", "class_name": "Grade 8", "section": "A", "subject": "Mathematics"})
        admin.post("/api/principals", json={"teacher_id": lphead["id"], "scope_type": "units", "unit_ids": [lp["id"]], "designation": "principal"})

        # two students in Grade 8-A
        for i, (fn, adm) in enumerate([("Riya", "G8-1"), ("Sam", "G8-2")]):
            stu = admin.post("/api/res/students", json={"first_name": fn, "last_name": "K", "admission_no": adm, "class_name": "Grade 8", "section": "A", "status": "active"}).json()
            admin.post("/api/res/enrollments", json={"student_id": stu["id"], "class_name": "Grade 8", "section": "A", "academic_year": "2026-27"})
            if i == 0:
                admin.post(f"/api/students/{stu['id']}/portal-user", json={"email": "riya@s23.test", "password": "Stud@123"})
                first_student = stu["id"]

        yield {"admin": admin, "login": login, "db": mon, "maths": maths, "lphead": lphead, "student": first_student}
    MongoClient(server.mongo_url).drop_database(TEST_DB)


def _mk_hw(sess, due="2999-01-01", title="HW1"):
    return sess.post("/api/homework", json={"class_name": "Grade 8", "section": "A", "subject": "Mathematics",
                                            "title": title, "instructions": "x", "due_date": due}).json()["homework"]


def test_monitor_aggregation(ctx):
    maths = ctx["login"]("maths@s23.test", "Teach@123")
    student = ctx["login"]("riya@s23.test", "Stud@123")
    hw = _mk_hw(maths, title="MonitorHW")
    # one of two students submits
    student.post(f"/api/homework/{hw['id']}/submit", data={"note": "done"},
                 files=[("files", ("a.pdf", io.BytesIO(PDF), "application/pdf"))])
    mon = ctx["admin"].get("/api/homework/monitor", params={"type": "homework"}).json()
    assert mon["type"] == "homework"
    # Grade 8-A has 2 enrolled; 1 submitted → 50% for this item's class row
    g8 = next(c for c in mon["classes"] if c["class_name"] == "Grade 8" and c["section"] == "A")
    assert g8["assigned"] >= 2 and g8["submitted"] >= 1
    # teacher activity row for maths
    trow = next(t for t in mon["teachers"] if t["teacher_id"] == ctx["maths"]["id"])
    assert trow["items_created"] >= 1 and trow["submissions_received"] >= 1 and trow["pending"] >= 1
    # pending verifications queue has the fresh submission
    assert mon["stats"]["pending_verifications"] >= 1
    assert any(p["title"] == "MonitorHW" for p in mon["pending"])


def test_monitor_principal_scope(ctx):
    maths = ctx["login"]("maths@s23.test", "Teach@123")
    _mk_hw(maths, title="HSonly")
    lphead = ctx["login"]("lphead@s23.test", "Teach@123")
    mon = lphead.get("/api/homework/monitor", params={"type": "homework"}).json()
    # LP principal: Grade 8 (HS) classes must be absent
    assert all(c["class_name"] != "Grade 8" for c in mon["classes"])
    assert all(p["class_name"] != "Grade 8" for p in mon["pending"])


def test_monitor_assignment_type(ctx):
    maths = ctx["login"]("maths@s23.test", "Teach@123")
    maths.post("/api/assignments", json={"class_name": "Grade 8", "section": "A", "subject": "Mathematics",
                                         "title": "AsgMon", "due_date": "2999-01-01", "max_marks": 10})
    mon = ctx["admin"].get("/api/homework/monitor", params={"type": "assignment"}).json()
    assert mon["type"] == "assignment"
    assert any(t["teacher_id"] == ctx["maths"]["id"] for t in mon["teachers"])


def _run_sweep():
    """Run the async sweep on a fresh loop with its own motor client (TestClient owns the app loop)."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    old = server.db
    server.db = AsyncIOMotorClient(server.mongo_url)[TEST_DB]
    try:
        return loop.run_until_complete(server._due_reminder_sweep())
    finally:
        server.db = old
        loop.close()


def test_reminder_job_tomorrow_only_and_idempotent(ctx):
    maths = ctx["login"]("maths@s23.test", "Teach@123")
    # due tomorrow (open) → should remind; due far future → should not; closed tomorrow → should not
    due_tom = _mk_hw(maths, due=_tomorrow() + "T09:00:00+00:00", title="DueTom")
    _mk_hw(maths, due="2999-01-01", title="DueFar")
    closed_tom = _mk_hw(maths, due=_tomorrow() + "T09:00:00+00:00", title="ClosedTom")
    maths.post(f"/api/homework/{closed_tom['id']}/close")

    db = ctx["db"]
    before = db.notifications.count_documents({"type": "homework_due_soon"})
    _run_sweep()
    after = db.notifications.count_documents({"type": "homework_due_soon"})
    assert after > before  # created some reminders
    # the reminder references the tomorrow-due open item, not the closed/far ones
    ref_ids = {n["related_id"] for n in db.notifications.find({"type": "homework_due_soon"})}
    assert due_tom["id"] in ref_ids
    assert closed_tom["id"] not in ref_ids
    # idempotent: second run adds nothing
    _run_sweep()
    assert db.notifications.count_documents({"type": "homework_due_soon"}) == after


def test_manual_reminder_dedupe_and_perms(ctx):
    maths = ctx["login"]("maths@s23.test", "Teach@123")
    hw = _mk_hw(maths, title="ManualRemind")
    r1 = maths.post(f"/api/homework/{hw['id']}/remind").json()
    assert r1["sent"] >= 1
    r2 = maths.post(f"/api/homework/{hw['id']}/remind").json()
    assert r2["sent"] == 0  # once-per-item-per-day dedupe
    # closed item → 400
    maths.post(f"/api/homework/{hw['id']}/close")
    assert maths.post(f"/api/homework/{hw['id']}/remind").status_code == 400
    # another teacher cannot remind someone else's item (lphead is not the owner) → 403
    lphead = ctx["login"]("lphead@s23.test", "Teach@123")
    hw2 = _mk_hw(maths, title="Owned")
    assert lphead.post(f"/api/homework/{hw2['id']}/remind").status_code == 403
