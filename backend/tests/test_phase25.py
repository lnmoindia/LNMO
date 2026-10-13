"""Phase 25 follow-up — redo verdict must 400 on empty/whitespace feedback on BOTH
homework (POST /api/submissions/{id}/verify) and assignment
(POST /api/assignment-submissions/{id}/verify) endpoints. Throwaway DB.
"""
import sys, io
import pytest

sys.path.insert(0, "/app/backend")
import server  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from pymongo import MongoClient  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

TEST_DB = "lnmo_phase25_test"
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


@pytest.fixture(scope="module")
def ctx():
    async def _init():
        server.client = AsyncIOMotorClient(server.mongo_url)
        server.db = server.client[TEST_DB]
    server.app.router.on_startup.insert(0, _init)
    MongoClient(server.mongo_url).drop_database(TEST_DB)
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
        platform.post("/api/res/institutions", json={"name": "S25", "slug": "s25", "admin_email": "a@s25.test", "admin_password": "Admin@123"})
        admin = login("a@s25.test", "Admin@123")
        hs = admin.post("/api/res/academic_units", json={"name": "HS", "code": "HS", "status": "active"}).json()
        admin.post("/api/res/academic_years", json={"name": "2026-27", "status": "active"})
        admin.post("/api/res/classes", json={"name": "Grade 8", "academic_unit_id": hs["id"], "status": "active"})
        admin.post("/api/res/sections", json={"name": "A", "class_name": "Grade 8", "status": "active"})
        maths = admin.post("/api/teachers", json={"name": "Maths", "email": "maths@s25.test", "password": "Teach@123", "status": "active"}).json()
        admin.post("/api/res/teacher_assignments", json={"teacher_id": maths["id"], "teacher_email": "maths@s25.test", "class_name": "Grade 8", "section": "A", "subject": "Mathematics"})
        stu = admin.post("/api/res/students", json={"first_name": "Riya", "last_name": "K", "admission_no": "G8-1", "class_name": "Grade 8", "section": "A", "status": "active"}).json()
        admin.post("/api/res/enrollments", json={"student_id": stu["id"], "class_name": "Grade 8", "section": "A", "academic_year": "2026-27"})
        admin.post(f"/api/students/{stu['id']}/portal-user", json={"email": "riya@s25.test", "password": "Stud@123"})
        yield {"login": login, "admin": admin}
    MongoClient(server.mongo_url).drop_database(TEST_DB)


def _hw_sub(ctx):
    maths = ctx["login"]("maths@s25.test", "Teach@123")
    student = ctx["login"]("riya@s25.test", "Stud@123")
    hw = maths.post("/api/homework", json={"class_name": "Grade 8", "section": "A", "subject": "Mathematics", "title": "HW", "due_date": "2999-01-01"}).json()["homework"]
    student.post(f"/api/homework/{hw['id']}/submit", data={"note": "x"}, files=[("files", ("a.pdf", io.BytesIO(PDF), "application/pdf"))])
    sid = maths.get(f"/api/homework/{hw['id']}/submissions").json()["submissions"][0]["id"]
    return maths, sid


def _asg_sub(ctx):
    maths = ctx["login"]("maths@s25.test", "Teach@123")
    student = ctx["login"]("riya@s25.test", "Stud@123")
    asg = maths.post("/api/assignments", json={"class_name": "Grade 8", "section": "A", "subject": "Mathematics", "title": "ASG", "due_date": "2999-01-01", "max_marks": 20}).json()["assignment"]
    student.post(f"/api/assignments/{asg['id']}/submit", data={"note": "x"}, files=[("files", ("a.pdf", io.BytesIO(PDF), "application/pdf"))])
    sid = maths.get(f"/api/assignments/{asg['id']}/submissions").json()["submissions"][0]["id"]
    return maths, sid


@pytest.mark.parametrize("feedback", [None, "", "   ", "\n\t "])
def test_homework_redo_rejects_blank_feedback(ctx, feedback):
    maths, sid = _hw_sub(ctx)
    body = {"verdict": "redo"}
    if feedback is not None:
        body["feedback"] = feedback
    r = maths.post(f"/api/submissions/{sid}/verify", json=body)
    assert r.status_code == 400, r.text
    # submission stays 'submitted' (not advanced to redo)
    subs = maths.get(f"/api/homework/{sid.split(':')[0] or ''}", params={}) if False else None
    # good feedback now works
    assert maths.post(f"/api/submissions/{sid}/verify", json={"verdict": "redo", "feedback": "please redo intro"}).status_code == 200


@pytest.mark.parametrize("feedback", [None, "", "   ", "\n\t "])
def test_assignment_redo_rejects_blank_feedback(ctx, feedback):
    maths, sid = _asg_sub(ctx)
    body = {"verdict": "redo"}
    if feedback is not None:
        body["feedback"] = feedback
    r = maths.post(f"/api/assignment-submissions/{sid}/verify", json=body)
    assert r.status_code == 400, r.text
    assert maths.post(f"/api/assignment-submissions/{sid}/verify", json={"verdict": "redo", "feedback": "fix step 2"}).status_code == 200
