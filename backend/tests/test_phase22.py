"""Phase 22 — Assignments module (scored sibling of homework). Throwaway DB, API-driven.

create-scope parity, verify requires score in range, redo clears score + requires feedback,
counts_toward_report surfaces on report-card only when tagged AND verified, late/close parity,
parent read-only, unit-principal scope, notification fan-out, assignment-stats avg score.
"""
import sys, io
import pytest

sys.path.insert(0, "/app/backend")
import server  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from pymongo import MongoClient  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

TEST_DB = "lnmo_phase22_test"
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
    def put(self, p, **k): return self._call("put", p, **k)
    def delete(self, p, **k): return self._call("delete", p, **k)


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
        platform.post("/api/res/institutions", json={"name": "S22", "slug": "s22", "admin_email": "a@s22.test", "admin_password": "Admin@123"})
        admin = login("a@s22.test", "Admin@123")
        hs = admin.post("/api/res/academic_units", json={"name": "HS", "code": "HS", "status": "active"}).json()
        lp = admin.post("/api/res/academic_units", json={"name": "LP", "code": "LP", "status": "active"}).json()
        admin.post("/api/res/academic_years", json={"name": "2026-27", "status": "active"})
        admin.post("/api/res/classes", json={"name": "Grade 8", "academic_unit_id": hs["id"], "status": "active"})
        admin.post("/api/res/classes", json={"name": "Grade 3", "academic_unit_id": lp["id"], "status": "active"})
        admin.post("/api/res/sections", json={"name": "A", "class_name": "Grade 8", "status": "active"})

        def teacher(n):
            return admin.post("/api/teachers", json={"name": n, "email": f"{n.lower()}@s22.test", "password": "Teach@123", "status": "active"}).json()
        maths = teacher("Maths")
        homeroom = teacher("Homeroom")
        lphead = teacher("LPHead")
        admin.post("/api/res/teacher_assignments", json={"teacher_id": maths["id"], "teacher_email": "maths@s22.test", "class_name": "Grade 8", "section": "A", "subject": "Mathematics"})
        admin.post("/api/principals", json={"teacher_id": lphead["id"], "scope_type": "units", "unit_ids": [lp["id"]], "designation": "principal"})

        stu = admin.post("/api/res/students", json={"first_name": "Riya", "last_name": "K", "admission_no": "G8-1", "class_name": "Grade 8", "section": "A", "status": "active"}).json()
        admin.post("/api/res/enrollments", json={"student_id": stu["id"], "class_name": "Grade 8", "section": "A", "academic_year": "2026-27"})
        admin.post(f"/api/students/{stu['id']}/portal-user", json={"email": "riya@s22.test", "password": "Stud@123"})
        admin.post(f"/api/students/{stu['id']}/parent-user", json={"email": "rparent@s22.test", "password": "Parent@123", "name": "RP"})

        yield {"admin": admin, "login": login, "db": mon, "maths": maths, "homeroom": homeroom,
               "lphead": lphead, "student": stu["id"]}
    MongoClient(server.mongo_url).drop_database(TEST_DB)


def _mk(sess, due="2999-01-01", max_marks=25, counts=False, title="Algebra Project"):
    return sess.post("/api/assignments", json={"class_name": "Grade 8", "section": "A", "subject": "Mathematics",
                                               "title": title, "instructions": "Build it", "due_date": due,
                                               "max_marks": max_marks, "counts_toward_report": counts})


def test_create_permission_parity(ctx):
    maths = ctx["login"]("maths@s22.test", "Teach@123")
    assert _mk(maths).status_code == 200
    homeroom = ctx["login"]("homeroom@s22.test", "Teach@123")
    assert _mk(homeroom).status_code == 403
    # max_marks < 1 rejected (Pydantic 422)
    bad = maths.post("/api/assignments", json={"class_name": "Grade 8", "section": "A", "subject": "Mathematics",
                                               "title": "x", "due_date": "2999-01-01", "max_marks": 0})
    assert bad.status_code == 422


def test_verify_requires_score_in_range(ctx):
    maths = ctx["login"]("maths@s22.test", "Teach@123")
    student = ctx["login"]("riya@s22.test", "Stud@123")
    a = _mk(maths, max_marks=25).json()["assignment"]
    student.post(f"/api/assignments/{a['id']}/submit", data={"note": "v1"},
                 files=[("files", ("a.pdf", io.BytesIO(PDF), "application/pdf"))])
    sub = maths.get(f"/api/assignments/{a['id']}/submissions").json()["submissions"][0]
    sid = sub["id"]
    # verified without score → 400
    assert maths.post(f"/api/assignment-submissions/{sid}/verify", json={"verdict": "verified"}).status_code == 400
    # score out of range → 400
    assert maths.post(f"/api/assignment-submissions/{sid}/verify", json={"verdict": "verified", "score": 26}).status_code == 400
    assert maths.post(f"/api/assignment-submissions/{sid}/verify", json={"verdict": "verified", "score": -1}).status_code == 400
    # valid score → 200 and stored
    assert maths.post(f"/api/assignment-submissions/{sid}/verify", json={"verdict": "verified", "score": 21}).status_code == 200
    assert ctx["db"].assignment_submissions.find_one({"id": sid})["score"] == 21


def test_redo_clears_score_and_requires_feedback(ctx):
    maths = ctx["login"]("maths@s22.test", "Teach@123")
    student = ctx["login"]("riya@s22.test", "Stud@123")
    a = _mk(maths).json()["assignment"]
    student.post(f"/api/assignments/{a['id']}/submit", data={"note": "v1"},
                 files=[("files", ("a.pdf", io.BytesIO(PDF), "application/pdf"))])
    sid = maths.get(f"/api/assignments/{a['id']}/submissions").json()["submissions"][0]["id"]
    maths.post(f"/api/assignment-submissions/{sid}/verify", json={"verdict": "verified", "score": 20})
    # redo without feedback → 400
    assert maths.post(f"/api/assignment-submissions/{sid}/verify", json={"verdict": "redo"}).status_code == 400
    # redo with feedback → 200, score cleared, status redo
    assert maths.post(f"/api/assignment-submissions/{sid}/verify", json={"verdict": "redo", "feedback": "improve intro"}).status_code == 200
    doc = ctx["db"].assignment_submissions.find_one({"id": sid})
    assert doc["status"] == "redo" and doc["score"] is None
    # resubmit bumps version
    student.post(f"/api/assignments/{a['id']}/submit", data={"note": "v2"},
                 files=[("files", ("b.pdf", io.BytesIO(PDF), "application/pdf"))])
    assert ctx["db"].assignment_submissions.find_one({"id": sid})["version"] == 2


def test_counts_toward_report_surfaces_only_when_tagged_and_verified(ctx):
    maths = ctx["login"]("maths@s22.test", "Teach@123")
    student = ctx["login"]("riya@s22.test", "Stud@123")
    # tagged assignment, verified
    tagged = _mk(maths, max_marks=25, counts=True, title="Report Project").json()["assignment"]
    student.post(f"/api/assignments/{tagged['id']}/submit", data={"note": "r"},
                 files=[("files", ("a.pdf", io.BytesIO(PDF), "application/pdf"))])
    tsid = maths.get(f"/api/assignments/{tagged['id']}/submissions").json()["submissions"][0]["id"]
    maths.post(f"/api/assignment-submissions/{tsid}/verify", json={"verdict": "verified", "score": 22})
    # untagged assignment, verified
    untagged = _mk(maths, max_marks=10, counts=False, title="Untagged Task").json()["assignment"]
    student.post(f"/api/assignments/{untagged['id']}/submit", data={"note": "u"},
                 files=[("files", ("a.pdf", io.BytesIO(PDF), "application/pdf"))])
    usid = maths.get(f"/api/assignments/{untagged['id']}/submissions").json()["submissions"][0]["id"]
    maths.post(f"/api/assignment-submissions/{usid}/verify", json={"verdict": "verified", "score": 8})

    rc = ctx["admin"].get(f"/api/students/{ctx['student']}/report-card").json()
    titles = [it["title"] for blk in rc["assignment_scores"] for it in blk["items"]]
    assert "Report Project" in titles          # tagged + verified → present
    assert "Untagged Task" not in titles        # untagged → absent
    block = next(b for b in rc["assignment_scores"] if b["subject"] == "Mathematics")
    item = next(it for it in block["items"] if it["title"] == "Report Project")
    assert item["score"] == 22 and item["max_marks"] == 25


def test_late_close_parent_scope_parity(ctx):
    maths = ctx["login"]("maths@s22.test", "Teach@123")
    student = ctx["login"]("riya@s22.test", "Stud@123")
    late = _mk(maths, due="2000-01-01T00:00:00+00:00").json()["assignment"]
    r = student.post(f"/api/assignments/{late['id']}/submit", data={"note": "x"},
                     files=[("files", ("a.pdf", io.BytesIO(PDF), "application/pdf"))])
    assert r.status_code == 200 and r.json()["late"] is True
    closed = _mk(maths).json()["assignment"]
    maths.post(f"/api/assignments/{closed['id']}/close")
    assert student.post(f"/api/assignments/{closed['id']}/submit", data={"note": "y"}).status_code == 400
    # parent read-only sees linked child's assignments; unlinked → 403
    parent = ctx["login"]("rparent@s22.test", "Parent@123")
    assert parent.get(f"/api/parent/child/{ctx['student']}/assignments").status_code == 200
    assert parent.get("/api/parent/child/nope/assignments").status_code == 403
    # LP principal cannot read Grade 8 submissions
    lphead = ctx["login"]("lphead@s22.test", "Teach@123")
    assert lphead.get(f"/api/assignments/{closed['id']}/submissions").status_code == 403


def test_notifications_and_stats(ctx):
    maths = ctx["login"]("maths@s22.test", "Teach@123")
    a = _mk(maths, max_marks=20, counts=True).json()["assignment"]
    su = ctx["db"].users.find_one({"email": "riya@s22.test"})
    assert ctx["db"].notifications.count_documents({"user_id": su["id"], "type": "assignment_new"}) >= 1
    student = ctx["login"]("riya@s22.test", "Stud@123")
    student.post(f"/api/assignments/{a['id']}/submit", data={"note": "n"},
                 files=[("files", ("a.pdf", io.BytesIO(PDF), "application/pdf"))])
    assert ctx["db"].notifications.count_documents({"user_id": ctx["maths"]["id"], "type": "assignment_submitted"}) >= 1
    sid = maths.get(f"/api/assignments/{a['id']}/submissions").json()["submissions"][0]["id"]
    maths.post(f"/api/assignment-submissions/{sid}/verify", json={"verdict": "verified", "score": 18})
    # verdict fan-out to student + parent
    assert ctx["db"].notifications.count_documents({"user_id": su["id"], "type": "assignment_verified"}) >= 1
    stats = ctx["admin"].get(f"/api/students/{ctx['student']}/assignment-stats").json()
    assert stats["assigned"] >= 1 and stats["verified"] >= 1 and stats["avg_score"] is not None
