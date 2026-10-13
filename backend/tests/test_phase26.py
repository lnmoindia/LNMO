"""Phase 26 — homework/assignment visibility & teaching-options sanity. Throwaway DB.

Reproduces the LPGS report ('created homework/assignment but it is not coming'):
- a section with ZERO enrolled students must NOT be offered in teaching-options
- a populated+portal'd section's student DOES see homework/assignment created for them
- the creating teacher always sees their own items in their list
"""
import sys, io
import pytest

sys.path.insert(0, "/app/backend")
import server  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from pymongo import MongoClient  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

TEST_DB = "lnmo_phase26_test"
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
    async def _init():
        server.client = AsyncIOMotorClient(server.mongo_url)
        server.db = server.client[TEST_DB]
    server.app.router.on_startup.insert(0, _init)
    MongoClient(server.mongo_url).drop_database(TEST_DB)

    with _client() as C:
        def login(email, pw):
            r = C.post("/api/auth/login", json={"email": email, "password": pw})
            assert r.status_code == 200, r.text
            tok = r.cookies.get("access_token"); C.cookies.clear()
            return Sess(C, tok)

        platform = login(PA_EMAIL, PA_PW)
        platform.post("/api/res/institutions", json={"name": "S26", "slug": "s26", "admin_email": "a@s26.test", "admin_password": "Admin@123"})
        admin = login("a@s26.test", "Admin@123")
        lp = admin.post("/api/res/academic_units", json={"name": "LP", "code": "LP", "status": "active"}).json()
        admin.post("/api/res/academic_years", json={"name": "2026-27", "status": "active"})
        admin.post("/api/res/classes", json={"name": "Grade 4", "academic_unit_id": lp["id"], "status": "active"})
        # two sections: A (will have a student) and B (empty)
        admin.post("/api/res/sections", json={"name": "A", "class_name": "Grade 4", "status": "active"})
        admin.post("/api/res/sections", json={"name": "B", "class_name": "Grade 4", "status": "active"})
        teacher = admin.post("/api/teachers", json={"name": "Deepa", "email": "deepa@s26.test", "password": "Teach@123", "status": "active"}).json()
        # teacher assigned to BOTH A and B
        admin.post("/api/res/teacher_assignments", json={"teacher_id": teacher["id"], "teacher_email": "deepa@s26.test", "class_name": "Grade 4", "section": "A", "subject": "Malayalam"})
        admin.post("/api/res/teacher_assignments", json={"teacher_id": teacher["id"], "teacher_email": "deepa@s26.test", "class_name": "Grade 4", "section": "B", "subject": "Malayalam"})
        # only section A gets an enrolled + portal'd student
        stu = admin.post("/api/res/students", json={"first_name": "Riya", "last_name": "K", "admission_no": "G4-1", "class_name": "Grade 4", "section": "A", "status": "active"}).json()
        admin.post("/api/res/enrollments", json={"student_id": stu["id"], "class_name": "Grade 4", "section": "A", "academic_year": "2026-27"})
        admin.post(f"/api/students/{stu['id']}/portal-user", json={"email": "riya@s26.test", "password": "Stud@123"})

        yield {"login": login, "admin": admin, "teacher_id": teacher["id"], "student": stu["id"]}
    MongoClient(server.mongo_url).drop_database(TEST_DB)


def test_teaching_options_excludes_empty_sections(ctx):
    deepa = ctx["login"]("deepa@s26.test", "Teach@123")
    opts = deepa.get("/api/teacher/teaching-options").json()["options"]
    combos = {(o["class_name"], o["section"]) for o in opts}
    assert ("Grade 4", "A") in combos          # populated → offered
    assert ("Grade 4", "B") not in combos      # empty → hidden (the bug fix)
    a = next(o for o in opts if o["section"] == "A")
    assert a["student_count"] == 1


def test_homework_visible_to_target_section_student(ctx):
    deepa = ctx["login"]("deepa@s26.test", "Teach@123")
    hw = deepa.post("/api/homework", json={"class_name": "Grade 4", "section": "A", "subject": "Malayalam",
                                           "title": "Essay", "due_date": "2999-01-01"}).json()["homework"]
    # creator sees it in their own list
    assert any(h["id"] == hw["id"] for h in deepa.get("/api/homework").json()["homework"])
    # the Grade 4-A student sees it
    student = ctx["login"]("riya@s26.test", "Stud@123")
    assert any(h["id"] == hw["id"] for h in student.get("/api/homework").json()["homework"])


def test_assignment_visible_to_target_section_student(ctx):
    deepa = ctx["login"]("deepa@s26.test", "Teach@123")
    asg = deepa.post("/api/assignments", json={"class_name": "Grade 4", "section": "A", "subject": "Malayalam",
                                               "title": "Project", "due_date": "2999-01-01", "max_marks": 10}).json()["assignment"]
    assert any(a["id"] == asg["id"] for a in deepa.get("/api/assignments").json()["assignments"])
    student = ctx["login"]("riya@s26.test", "Stud@123")
    assert any(a["id"] == asg["id"] for a in student.get("/api/assignments").json()["assignments"])
