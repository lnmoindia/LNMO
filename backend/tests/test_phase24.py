"""Phase 24 — class-teacher monthly report (homework + assignments roll-up). Throwaway DB.

aggregation math (due-in-month counts, out-of-month excluded), class-teacher access vs 403,
unit-principal scope, empty month clean zeros, print payload includes signers.
"""
import sys, io
import pytest

sys.path.insert(0, "/app/backend")
import server  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from pymongo import MongoClient  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

TEST_DB = "lnmo_phase24_test"
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
        platform.post("/api/res/institutions", json={"name": "S24", "slug": "s24", "admin_email": "a@s24.test", "admin_password": "Admin@123"})
        admin = login("a@s24.test", "Admin@123")
        hs = admin.post("/api/res/academic_units", json={"name": "HS", "code": "HS", "status": "active"}).json()
        lp = admin.post("/api/res/academic_units", json={"name": "LP", "code": "LP", "status": "active"}).json()
        admin.post("/api/res/academic_years", json={"name": "2026-27", "status": "active"})
        g8 = admin.post("/api/res/classes", json={"name": "Grade 8", "academic_unit_id": hs["id"], "status": "active"}).json()
        admin.post("/api/res/classes", json={"name": "Grade 3", "academic_unit_id": lp["id"], "status": "active"})
        secA = admin.post("/api/res/sections", json={"name": "A", "class_name": "Grade 8", "status": "active"}).json()

        def teacher(n):
            return admin.post("/api/teachers", json={"name": n, "email": f"{n.lower()}@s24.test", "password": "Teach@123", "status": "active"}).json()
        maths = teacher("Maths")       # subject teacher + class teacher of G8-A
        other = teacher("Other")       # unrelated teacher
        lphead = teacher("LPHead")     # LP principal
        admin.post("/api/res/teacher_assignments", json={"teacher_id": maths["id"], "teacher_email": "maths@s24.test", "class_name": "Grade 8", "section": "A", "subject": "Mathematics"})
        # make maths the class teacher of G8-A
        admin.put(f"/api/res/sections/{secA['id']}", json={"class_teacher_id": maths["id"]})
        admin.post("/api/principals", json={"teacher_id": lphead["id"], "scope_type": "units", "unit_ids": [lp["id"]], "designation": "principal"})

        stu = admin.post("/api/res/students", json={"first_name": "Riya", "last_name": "K", "admission_no": "G8-1", "class_name": "Grade 8", "section": "A", "status": "active"}).json()
        admin.post("/api/res/enrollments", json={"student_id": stu["id"], "class_name": "Grade 8", "section": "A", "academic_year": "2026-27"})
        admin.post(f"/api/students/{stu['id']}/portal-user", json={"email": "riya@s24.test", "password": "Stud@123"})

        yield {"admin": admin, "login": login, "db": mon, "maths": maths, "other": other,
               "lphead": lphead, "class_id": g8["id"], "student": stu["id"]}
    MongoClient(server.mongo_url).drop_database(TEST_DB)


def _seed_activity(ctx):
    """2 homework due in 2026-05, 1 homework due in 2026-06; student submits one May HW (late); 1 assignment May scored."""
    maths = ctx["login"]("maths@s24.test", "Teach@123")
    student = ctx["login"]("riya@s24.test", "Stud@123")
    hw_may1 = maths.post("/api/homework", json={"class_name": "Grade 8", "section": "A", "subject": "Mathematics", "title": "May HW1", "due_date": "2026-05-10T09:00:00+00:00"}).json()["homework"]
    maths.post("/api/homework", json={"class_name": "Grade 8", "section": "A", "subject": "Mathematics", "title": "May HW2", "due_date": "2026-05-20T09:00:00+00:00"})
    maths.post("/api/homework", json={"class_name": "Grade 8", "section": "A", "subject": "Mathematics", "title": "June HW", "due_date": "2026-06-05T09:00:00+00:00"})
    # student submits May HW1 (due is in the past → late)
    student.post(f"/api/homework/{hw_may1['id']}/submit", data={"note": "done"}, files=[("files", ("a.pdf", io.BytesIO(PDF), "application/pdf"))])
    # assignment due May, submitted + scored
    asg = maths.post("/api/assignments", json={"class_name": "Grade 8", "section": "A", "subject": "Mathematics", "title": "May ASG", "due_date": "2026-05-15T09:00:00+00:00", "max_marks": 20}).json()["assignment"]
    student.post(f"/api/assignments/{asg['id']}/submit", data={"note": "a"}, files=[("files", ("a.pdf", io.BytesIO(PDF), "application/pdf"))])
    sid = maths.get(f"/api/assignments/{asg['id']}/submissions").json()["submissions"][0]["id"]
    maths.post(f"/api/assignment-submissions/{sid}/verify", json={"verdict": "verified", "score": 16})
    return maths


def test_aggregation_month_window(ctx):
    _seed_activity(ctx)
    r = ctx["admin"].get(f"/api/classes/{ctx['class_id']}/monthly-report", params={"month": "2026-05"})
    assert r.status_code == 200
    data = r.json()
    secA = next(s for s in data["sections"] if s["section"] == "A")
    assert secA["homework_count"] == 2  # only the 2 May homework (June excluded)
    assert secA["assignment_count"] == 1
    row = next(x for x in secA["students"] if x["student_id"] == ctx["student"])
    assert row["homework"]["assigned"] == 2 and row["homework"]["submitted"] == 1 and row["homework"]["late"] == 1
    assert row["homework"]["pending"] == 1
    assert row["assignments"]["assigned"] == 1 and row["assignments"]["verified"] == 1
    assert row["assignments"]["avg_score"] == 16 and row["assignments"]["scored_count"] == 1
    # print payload carries signers like report cards
    assert "signers" in data and "class_teacher" in data["signers"] and "principal" in data["signers"]


def test_class_teacher_access_and_403(ctx):
    maths = ctx["login"]("maths@s24.test", "Teach@123")  # class teacher of G8-A
    assert maths.get(f"/api/classes/{ctx['class_id']}/monthly-report", params={"month": "2026-05"}).status_code == 200
    other = ctx["login"]("other@s24.test", "Teach@123")  # not a class teacher of this class
    assert other.get(f"/api/classes/{ctx['class_id']}/monthly-report", params={"month": "2026-05"}).status_code == 403


def test_unit_principal_scope(ctx):
    # LP principal cannot see a Grade 8 (HS) class report
    lphead = ctx["login"]("lphead@s24.test", "Teach@123")
    assert lphead.get(f"/api/classes/{ctx['class_id']}/monthly-report", params={"month": "2026-05"}).status_code == 403


def test_empty_month_clean_zeros(ctx):
    data = ctx["admin"].get(f"/api/classes/{ctx['class_id']}/monthly-report", params={"month": "2020-01"}).json()
    secA = next(s for s in data["sections"] if s["section"] == "A")
    assert secA["homework_count"] == 0 and secA["assignment_count"] == 0
    row = next(x for x in secA["students"] if x["student_id"] == ctx["student"])
    assert row["homework"] == {"assigned": 0, "submitted": 0, "late": 0, "verified": 0, "redo": 0, "pending": 0}
    assert row["assignments"]["assigned"] == 0 and row["assignments"]["avg_score"] is None
