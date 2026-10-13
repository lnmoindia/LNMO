"""Phase 21 — Homework module core loop. Throwaway DB, API-driven.

create permission (subject teacher yes / unrelated + class-teacher-only no), submit late-flag,
closed window blocks submit, redo requires feedback + resubmission bumps version, attachment
constraints, parent sees only linked child, unit-principal scope, notification fan-out,
homework-stats aggregates.
"""
import os, sys, io
import pytest

sys.path.insert(0, "/app/backend")
import server  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from pymongo import MongoClient  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

TEST_DB = "lnmo_phase21_test"
PA_EMAIL = server.os.environ["PLATFORM_ADMIN_EMAIL"].lower()
PA_PW = server.os.environ["PLATFORM_ADMIN_PASSWORD"]
BASE = "https://testserver"
PDF = b"%PDF-1.4 test\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 40


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
        platform.post("/api/res/institutions", json={"name": "S21", "slug": "s21", "admin_email": "a@s21.test", "admin_password": "Admin@123"})
        admin = login("a@s21.test", "Admin@123")
        hs = admin.post("/api/res/academic_units", json={"name": "HS", "code": "HS", "status": "active"}).json()
        lp = admin.post("/api/res/academic_units", json={"name": "LP", "code": "LP", "status": "active"}).json()
        admin.post("/api/res/academic_years", json={"name": "2026-27", "status": "active"})
        admin.post("/api/res/classes", json={"name": "Grade 8", "academic_unit_id": hs["id"], "status": "active"})
        admin.post("/api/res/classes", json={"name": "Grade 3", "academic_unit_id": lp["id"], "status": "active"})
        admin.post("/api/res/sections", json={"name": "A", "class_name": "Grade 8", "status": "active"})

        def teacher(n):
            return admin.post("/api/teachers", json={"name": n, "email": f"{n.lower()}@s21.test", "password": "Teach@123", "status": "active"}).json()
        maths = teacher("Maths")       # subject teacher for Grade 8-A Maths
        homeroom = teacher("Homeroom")  # class teacher only, teaches nothing
        lphead = teacher("LPHead")
        admin.post("/api/res/teacher_assignments", json={"teacher_id": maths["id"], "teacher_email": "maths@s21.test", "class_name": "Grade 8", "section": "A", "subject": "Mathematics"})
        # homeroom is class teacher but has NO maths assignment
        admin.post("/api/principals", json={"teacher_id": lphead["id"], "scope_type": "units", "unit_ids": [lp["id"]], "designation": "principal"})

        stu = admin.post("/api/res/students", json={"first_name": "Riya", "last_name": "K", "admission_no": "G8-1", "class_name": "Grade 8", "section": "A", "status": "active"}).json()
        admin.post("/api/res/enrollments", json={"student_id": stu["id"], "class_name": "Grade 8", "section": "A", "academic_year": "2026-27"})
        admin.post(f"/api/students/{stu['id']}/portal-user", json={"email": "riya@s21.test", "password": "Stud@123"})
        admin.post(f"/api/students/{stu['id']}/parent-user", json={"email": "rparent@s21.test", "password": "Parent@123", "name": "RP"})

        yield {"admin": admin, "login": login, "db": mon, "maths": maths, "homeroom": homeroom,
               "lphead": lphead, "student": stu["id"]}
    MongoClient(server.mongo_url).drop_database(TEST_DB)


def _mk(sess, due="2999-01-01"):
    return sess.post("/api/homework", json={"class_name": "Grade 8", "section": "A", "subject": "Mathematics",
                                            "title": "Algebra set", "instructions": "Do Q1-5", "due_date": due})


def test_create_permission(ctx):
    maths = ctx["login"]("maths@s21.test", "Teach@123")
    assert _mk(maths).status_code == 200                      # assigned subject teacher → ok
    homeroom = ctx["login"]("homeroom@s21.test", "Teach@123")
    assert _mk(homeroom).status_code == 403                   # class-teacher-only, not the subject → 403


def test_submit_late_flag_and_closed_block(ctx):
    maths = ctx["login"]("maths@s21.test", "Teach@123")
    student = ctx["login"]("riya@s21.test", "Stud@123")
    # due in the past → late flag true
    hw_late = _mk(maths, due="2000-01-01T00:00:00+00:00").json()["homework"]
    r = student.post(f"/api/homework/{hw_late['id']}/submit", data={"note": "done"},
                     files=[("files", ("a.pdf", io.BytesIO(PDF), "application/pdf"))])
    assert r.status_code == 200 and r.json()["late"] is True
    # closed window blocks submit
    hw_future = _mk(maths).json()["homework"]
    maths.post(f"/api/homework/{hw_future['id']}/close")
    r2 = student.post(f"/api/homework/{hw_future['id']}/submit", data={"note": "x"})
    assert r2.status_code == 400 and "closed" in r2.json()["detail"].lower()


def test_redo_requires_feedback_and_version_bump(ctx):
    maths = ctx["login"]("maths@s21.test", "Teach@123")
    student = ctx["login"]("riya@s21.test", "Stud@123")
    hw = _mk(maths).json()["homework"]
    student.post(f"/api/homework/{hw['id']}/submit", data={"note": "v1"},
                 files=[("files", ("a.pdf", io.BytesIO(PDF), "application/pdf"))])
    subs = maths.get(f"/api/homework/{hw['id']}/submissions").json()["submissions"]
    sid = subs[0]["id"]
    # redo without feedback → 400
    assert maths.post(f"/api/submissions/{sid}/verify", json={"verdict": "redo"}).status_code == 400
    assert maths.post(f"/api/submissions/{sid}/verify", json={"verdict": "redo", "feedback": "redo Q3"}).status_code == 200
    # resubmission bumps version + status back to submitted
    student.post(f"/api/homework/{hw['id']}/submit", data={"note": "v2"},
                 files=[("files", ("b.pdf", io.BytesIO(PDF), "application/pdf"))])
    s2 = ctx["db"].homework_submissions.find_one({"id": sid})
    assert s2["version"] == 2 and s2["status"] == "submitted"
    # verify (no feedback needed)
    assert maths.post(f"/api/submissions/{sid}/verify", json={"verdict": "verified"}).status_code == 200


def test_attachment_constraints(ctx):
    maths = ctx["login"]("maths@s21.test", "Teach@123")
    student = ctx["login"]("riya@s21.test", "Stud@123")
    hw = _mk(maths).json()["homework"]
    # bad type
    bad = student.post(f"/api/homework/{hw['id']}/submit", data={"note": ""},
                       files=[("files", ("a.txt", io.BytesIO(b"x"), "text/plain"))])
    assert bad.status_code == 400
    # too many files (6 > 5)
    many = [("files", (f"f{i}.pdf", io.BytesIO(PDF), "application/pdf")) for i in range(6)]
    assert student.post(f"/api/homework/{hw['id']}/submit", data={"note": ""}, files=many).status_code == 400


def test_parent_sees_only_linked_child_and_stats(ctx):
    maths = ctx["login"]("maths@s21.test", "Teach@123")
    _mk(maths)
    parent = ctx["login"]("rparent@s21.test", "Parent@123")
    hw = parent.get(f"/api/parent/child/{ctx['student']}/homework")
    assert hw.status_code == 200 and len(hw.json()["homework"]) >= 1
    # unlinked child → 403
    assert parent.get("/api/parent/child/does-not-exist/homework").status_code == 403
    stats = ctx["admin"].get(f"/api/students/{ctx['student']}/homework-stats").json()
    assert stats["assigned"] >= 1 and stats["submitted"] >= 1 and stats["late"] >= 1


def test_principal_out_of_scope_and_notifications(ctx):
    # LP principal cannot read a Grade 8 (HS) homework's submissions
    maths = ctx["login"]("maths@s21.test", "Teach@123")
    hw = _mk(maths).json()["homework"]
    lphead = ctx["login"]("lphead@s21.test", "Teach@123")
    assert lphead.get(f"/api/homework/{hw['id']}/submissions").status_code == 403
    # creating homework fanned a notification to the enrolled student
    su = ctx["db"].users.find_one({"email": "riya@s21.test"})
    assert ctx["db"].notifications.count_documents({"user_id": su["id"], "type": "homework_new"}) >= 1
    # submission notified the teacher
    student = ctx["login"]("riya@s21.test", "Stud@123")
    student.post(f"/api/homework/{hw['id']}/submit", data={"note": "n"},
                 files=[("files", ("a.pdf", io.BytesIO(PDF), "application/pdf"))])
    assert ctx["db"].notifications.count_documents({"user_id": ctx["maths"]["id"], "type": "homework_submitted"}) >= 1
