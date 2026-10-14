"""Phase 1 — Principal role (elevated teacher) backend tests.

ISOLATION: runs the FastAPI app in-process via TestClient against a SEPARATE test database
(`lnmo_principal_phase1_test`). It creates throwaway institutions, academic units, classes,
teachers and students, and DROPS the test DB at the end. The real database is never touched.

Run serially:  pytest backend/tests/test_principal_phase1.py -v -n 0
"""
import sys
import pytest

sys.path.insert(0, "/app/backend")
import server  # noqa: E402  (loads backend/.env for MONGO_URL / JWT / PLATFORM_ADMIN_*)
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from pymongo import MongoClient  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

TEST_DB = "lnmo_principal_phase1_test"
PA_EMAIL = server.os.environ["PLATFORM_ADMIN_EMAIL"].lower()
PA_PW = server.os.environ["PLATFORM_ADMIN_PASSWORD"]
BASE = "https://testserver"


def _client():
    return TestClient(server.app, base_url=BASE)


class Sess:
    """A per-user view over the SHARED TestClient (single event loop). Auth via Bearer token so
    multiple identities coexist without cookie-jar collisions or cross-loop motor errors."""
    def __init__(self, client, token):
        self._c = client
        self._h = {"Authorization": f"Bearer {token}"}

    def _call(self, method, path, **kw):
        self._c.cookies.clear()  # cookie is checked before the header, so keep the jar empty
        headers = {**self._h, **kw.pop("headers", {})}
        return getattr(self._c, method)(path, headers=headers, **kw)

    def get(self, path, **kw):
        return self._call("get", path, **kw)

    def post(self, path, **kw):
        return self._call("post", path, **kw)

    def put(self, path, **kw):
        return self._call("put", path, **kw)

    def delete(self, path, **kw):
        return self._call("delete", path, **kw)


@pytest.fixture(scope="module")
def world():
    # Create the motor client INSIDE the app's event loop (startup), bound to the throwaway DB.
    async def _init_test_db():
        server.client = AsyncIOMotorClient(server.mongo_url)
        server.db = server.client[TEST_DB]
    server.app.router.on_startup.insert(0, _init_test_db)
    MongoClient(server.mongo_url).drop_database(TEST_DB)

    w = {}
    with _client() as C:  # ONE client/loop; triggers startup: inits test DB + seeds platform admin
        def login(email, pw):
            r = C.post("/api/auth/login", json={"email": email, "password": pw})
            assert r.status_code == 200, f"login {email} -> {r.status_code}: {r.text}"
            token = r.cookies.get("access_token")
            C.cookies.clear()
            return Sess(C, token)

        platform = login(PA_EMAIL, PA_PW)

        # Institution #1 (+ its admin)
        r = platform.post("/api/res/institutions", json={
            "name": "Test School One", "admin_email": "admin1@test.school", "admin_password": "Admin@123"})
        assert r.status_code == 200, r.text
        w["inst1"] = r.json()
        admin = login("admin1@test.school", "Admin@123")
        w["admin"] = admin

        # Institution #2 (+ admin + a teacher) — for cross-institution checks
        r = platform.post("/api/res/institutions", json={
            "name": "Test School Two", "admin_email": "admin2@test.school", "admin_password": "Admin@123"})
        assert r.status_code == 200, r.text
        admin2 = login("admin2@test.school", "Admin@123")
        w["foreign_teacher"] = admin2.post("/api/teachers", json={
            "name": "Foreign T", "email": "foreign@test2.school", "password": "Teach@123", "status": "active"}).json()

        # Two divisions (academic units) in institution #1
        w["unitA"] = admin.post("/api/res/academic_units", json={"name": "Primary", "code": "PRI"}).json()
        w["unitB"] = admin.post("/api/res/academic_units", json={"name": "Secondary", "code": "SEC"}).json()

        # A class + section + student in each unit
        admin.post("/api/res/classes", json={"name": "Grade 1", "grade_level": "1",
                                             "academic_unit_id": w["unitA"]["id"], "status": "active"})
        admin.post("/api/res/classes", json={"name": "Grade 9", "grade_level": "9",
                                             "academic_unit_id": w["unitB"]["id"], "status": "active"})
        admin.post("/api/res/sections", json={"name": "A", "class_name": "Grade 1", "status": "active"})
        admin.post("/api/res/sections", json={"name": "A", "class_name": "Grade 9", "status": "active"})
        w["studentA"] = admin.post("/api/students/enroll", json={
            "first_name": "Stud", "last_name": "Aaa", "enroll": True,
            "class_name": "Grade 1", "section": "A", "academic_year": "2026-27"}).json()
        w["studentB"] = admin.post("/api/students/enroll", json={
            "first_name": "Stud", "last_name": "Bbb", "enroll": True,
            "class_name": "Grade 9", "section": "A", "academic_year": "2026-27"}).json()

        # Teachers (plain teacher accounts to be elevated)
        def mk_teacher(email, name):
            r = admin.post("/api/teachers", json={"name": name, "email": email,
                                                  "password": "Teach@123", "status": "active"})
            assert r.status_code == 200, r.text
            # admin-set initial passwords force a change (enforced server-side since Phase 58); tests skip that step
            MongoClient(server.mongo_url)[TEST_DB].users.update_many({"email": email}, {"$set": {"must_change_password": False}})
            return r.json()

        w["tA"] = mk_teacher("ta@test.school", "Teacher A")
        w["tB"] = mk_teacher("tb@test.school", "Teacher B")
        w["tC"] = mk_teacher("tc@test.school", "Teacher C")
        w["head"] = mk_teacher("head@test.school", "Head One")
        w["head2"] = mk_teacher("head2@test.school", "Head Two")
        w["tUnitDel"] = mk_teacher("tunitdel@test.school", "Unit Del")

        w["login"] = login
        yield w

    MongoClient(server.mongo_url).drop_database(TEST_DB)


def _assign(admin, teacher_id, scope_type, unit_ids=None, designation=None):
    body = {"teacher_id": teacher_id, "scope_type": scope_type, "unit_ids": unit_ids or []}
    if designation:
        body["designation"] = designation
    return admin.post("/api/principals", json=body)


# ---------------- Assignment + designation rules ----------------

def test_assign_first_whole_school_is_principal(world):
    r = _assign(world["admin"], world["head"]["id"], "whole_school")
    assert r.status_code == 200, r.text
    assert r.json()["designation"] == "principal"


def test_second_whole_school_autodefaults_assistant_and_explicit_principal_409(world):
    # explicit principal on an already-held whole-school scope → 400
    r = _assign(world["admin"], world["head2"]["id"], "whole_school", designation="principal")
    assert r.status_code == 400, r.text
    # auto-default becomes assistant_principal
    r = _assign(world["admin"], world["head2"]["id"], "whole_school")
    assert r.status_code == 200, r.text
    assert r.json()["designation"] == "assistant_principal"


def test_unit_scope_designation_rules(world):
    a = world["admin"]
    ua, ub = world["unitA"]["id"], world["unitB"]["id"]
    # First principal of unit A → principal
    r = _assign(a, world["tA"]["id"], "units", [ua])
    assert r.status_code == 200 and r.json()["designation"] == "principal", r.text
    # Explicit principal for unit A again (different teacher) → conflict 400
    r = _assign(a, world["tB"]["id"], "units", [ua], designation="principal")
    assert r.status_code == 400, r.text
    # Auto-default second assignee on unit A → assistant_principal
    r = _assign(a, world["tC"]["id"], "units", [ua])
    assert r.status_code == 200 and r.json()["designation"] == "assistant_principal", r.text
    # Principal of a DIFFERENT unit (B) → principal OK
    r = _assign(a, world["tB"]["id"], "units", [ub])
    assert r.status_code == 200 and r.json()["designation"] == "principal", r.text


def test_assign_rejects_non_teacher_and_cross_institution(world):
    a = world["admin"]
    # random id that is not a teacher in this institution
    r = _assign(a, "00000000-0000-0000-0000-000000000000", "whole_school")
    assert r.status_code == 400, r.text
    # teacher that belongs to another institution
    r = _assign(a, world["foreign_teacher"]["id"], "whole_school")
    assert r.status_code == 400, r.text


def test_assign_duplicate_same_teacher_400(world):
    # tA is already a unit-A principal from an earlier test
    r = _assign(world["admin"], world["tA"]["id"], "units", [world["unitB"]["id"]])
    assert r.status_code == 400, r.text


def test_units_scope_requires_valid_units(world):
    a = world["admin"]
    r = _assign(a, world["tUnitDel"]["id"], "units", [])
    assert r.status_code == 400, r.text
    r = _assign(a, world["tUnitDel"]["id"], "units", ["nonexistent-unit"])
    assert r.status_code == 400, r.text


# ---------------- Permissions: exclusions always 403 for principals ----------------

def test_principal_blocked_on_excluded_endpoints(world):
    p = world["login"]("ta@test.school", "Teach@123")  # unit-A principal
    checks = [
        ("get", "/api/institution/profile", None),
        ("put", "/api/institution/profile", {"name": "x"}),
        ("get", "/api/institution/academic-config", None),
        ("put", "/api/institution/academic-config", {"school_model": "k12"}),
        ("get", "/api/institution/setup-status", None),
        ("get", "/api/res/academic_units", None),
        ("post", "/api/res/academic_units", {"name": "Hacked", "code": "HAK"}),
        ("get", "/api/res/academic_years", None),
        ("get", "/api/users", None),
        ("get", "/api/principals", None),
        ("post", "/api/principals", {"teacher_id": world["tB"]["id"], "scope_type": "whole_school"}),
    ]
    for method, path, body in checks:
        r = getattr(p, method)(path, json=body) if body is not None else getattr(p, method)(path)
        assert r.status_code == 403, f"{method} {path} -> {r.status_code} (expected 403): {r.text}"


# ---------------- Scope enforcement (unit-A principal must not see unit-B data) ----------------

def test_unit_principal_students_scoped(world):
    p = world["login"]("ta@test.school", "Teach@123")
    items = p.get("/api/res/students").json()["items"]
    names = {s.get("last_name") for s in items}
    assert "Aaa" in names and "Bbb" not in names, names
    # /students/filter must also be scoped
    fitems = p.get("/api/students/filter").json()["items"]
    fnames = {s.get("last_name") for s in fitems}
    assert "Aaa" in fnames and "Bbb" not in fnames, fnames


def test_unit_principal_direct_read_outside_scope_404(world):
    p = world["login"]("ta@test.school", "Teach@123")
    r = p.get(f"/api/res/students/{world['studentB']['id']}")
    assert r.status_code == 404, r.text
    # in-scope student is readable
    r = p.get(f"/api/res/students/{world['studentA']['id']}")
    assert r.status_code == 200, r.text


def test_unit_principal_cannot_create_outside_scope(world):
    p = world["login"]("ta@test.school", "Teach@123")
    r = p.post("/api/students/enroll", json={"first_name": "Hack", "enroll": True,
                                             "class_name": "Grade 9", "section": "A", "academic_year": "2026-27"})
    assert r.status_code == 403, r.text


def test_unit_principal_classes_and_attendance_scoped(world):
    p = world["login"]("ta@test.school", "Teach@123")
    classes = p.get("/api/res/classes").json()["items"]
    cnames = {c["name"] for c in classes}
    assert cnames == {"Grade 1"}, cnames
    # attendance sheet for in-scope class → 200; out-of-scope → 403
    assert p.get("/api/attendance/sheet", params={"class_name": "Grade 1", "section": "A"}).status_code == 200
    assert p.get("/api/attendance/sheet", params={"class_name": "Grade 9", "section": "A"}).status_code == 403


# ---------------- Principal CAN manage within scope ----------------

def test_unit_principal_can_create_in_scope(world):
    p = world["login"]("ta@test.school", "Teach@123")
    r = p.post("/api/students/enroll", json={"first_name": "InScope", "enroll": True,
                                             "class_name": "Grade 1", "section": "A", "academic_year": "2026-27"})
    assert r.status_code == 200, r.text


def test_assistant_designation_has_identical_permissions(world):
    # tC is assistant_principal of unit A — must have the SAME access as the principal
    p = world["login"]("tc@test.school", "Teach@123")
    items = p.get("/api/res/students").json()["items"]
    names = {s.get("last_name") for s in items}
    assert "Aaa" in names and "Bbb" not in names, names
    assert p.get("/api/attendance/sheet", params={"class_name": "Grade 1", "section": "A"}).status_code == 200


# ---------------- Whole-school principal reaches everything (but not exclusions) ----------------

def test_whole_school_principal_sees_all_units(world):
    p = world["login"]("head@test.school", "Teach@123")
    names = {s.get("last_name") for s in p.get("/api/res/students").json()["items"]}
    assert {"Aaa", "Bbb"}.issubset(names), names
    assert p.get("/api/attendance/sheet", params={"class_name": "Grade 9", "section": "A"}).status_code == 200
    # still blocked on exclusions
    assert p.get("/api/res/academic_units").status_code == 403


# ---------------- Combined portal: principals keep teacher endpoints ----------------

def test_principal_retains_teacher_endpoints(world):
    for email in ("ta@test.school", "head@test.school"):
        p = world["login"](email, "Teach@123")
        assert p.get("/api/teacher/overview").status_code == 200
        assert p.get("/api/teacher/profile").status_code == 200
        assert p.get("/api/teacher/my-class").status_code == 200
        assert p.get("/api/timetable/teacher-grid").status_code == 200


def test_auth_me_exposes_principal_info(world):
    p = world["login"]("ta@test.school", "Teach@123")
    me = p.get("/api/auth/me").json()
    assert me["role"] == "teacher"
    assert me.get("is_principal") is True
    assert me["principal"]["scope_type"] == "units"
    assert world["unitA"]["id"] in me["principal"]["unit_ids"]


# ---------------- Edge cases: unit delete cleanup + revocation ----------------

def test_deleting_unit_cleans_principal_assignment(world):
    a = world["admin"]
    unit = a.post("/api/res/academic_units", json={"name": "Temp Div", "code": "TMP"}).json()
    r = _assign(a, world["tUnitDel"]["id"], "units", [unit["id"]])
    assert r.status_code == 200, r.text
    # delete the unit → assignment (which referenced only this unit) should be removed
    assert a.delete(f"/api/res/academic_units/{unit['id']}").status_code == 200
    rows = a.get("/api/principals").json()["items"]
    assert all(row["user_id"] != world["tUnitDel"]["id"] for row in rows), rows
    # the teacher no longer has principal powers
    p = world["login"]("tunitdel@test.school", "Teach@123")
    assert p.get("/api/res/students").status_code == 403


def test_revocation_reverts_to_plain_teacher(world):
    a = world["admin"]
    # find head's whole-school assignment and revoke it
    rows = a.get("/api/principals").json()["items"]
    head_row = next(r for r in rows if r["user_id"] == world["head"]["id"])
    assert a.delete(f"/api/principals/{head_row['id']}").status_code == 200
    p = world["login"]("head@test.school", "Teach@123")
    # principal powers gone
    assert p.get("/api/res/students").status_code == 403
    # teacher powers retained
    assert p.get("/api/teacher/overview").status_code == 200
    # /auth/me no longer flags principal
    me = p.get("/api/auth/me").json()
    assert not me.get("is_principal")
