"""Phase 6 — editable classes/sections: rename cascade, delete guard, capacity warn, scope. Throwaway DB."""
import sys
import pytest

sys.path.insert(0, "/app/backend")
import server  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from pymongo import MongoClient  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

TEST_DB = "lnmo_phase6_test"
PA_EMAIL = server.os.environ["PLATFORM_ADMIN_EMAIL"].lower()
PA_PW = server.os.environ["PLATFORM_ADMIN_PASSWORD"]
BASE = "https://testserver"
_n = {"i": 0}


def _client():
    return TestClient(server.app, base_url=BASE)


class Sess:
    def __init__(self, c, tok):
        self._c = c
        self._h = {"Authorization": f"Bearer {tok}"}

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
    with _client() as C:
        def login(email, pw):
            r = C.post("/api/auth/login", json={"email": email, "password": pw})
            assert r.status_code == 200, r.text
            tok = r.cookies.get("access_token")
            C.cookies.clear()
            return Sess(C, tok)

        platform = login(PA_EMAIL, PA_PW)

        def new_school():
            _n["i"] += 1
            i = _n["i"]
            platform.post("/api/res/institutions", json={
                "name": f"S{i}", "slug": f"s6-{i}", "admin_email": f"a{i}@s6.test", "admin_password": "Admin@123"})
            return login(f"a{i}@s6.test", "Admin@123"), i

        yield {"login": login, "new_school": new_school, "C": C}
    MongoClient(server.mongo_url).drop_database(TEST_DB)


def _scaffold(admin, grade="Grade 8", section="A", cap=None):
    """Create a unit + class + section + academic year. Returns (unit_id, class_id, section_id)."""
    u = admin.post("/api/res/academic_units", json={"name": "HS", "code": "HS", "status": "active"}).json()
    c = admin.post("/api/res/classes", json={"name": grade, "grade_level": "8", "academic_unit_id": u["id"], "status": "active"}).json()
    sec_body = {"name": section, "class_name": grade, "status": "active"}
    if cap is not None:
        sec_body["capacity"] = cap
    s = admin.post("/api/res/sections", json=sec_body).json()
    admin.post("/api/res/academic_years", json={"name": "2026-27", "status": "active"})
    return u["id"], c["id"], s["id"]


def test_rename_class_cascades_everywhere(ctx):
    admin, _ = ctx["new_school"]()
    uid, cid, sid = _scaffold(admin, "Grade 8", "A")
    # student enrolled
    st = admin.post("/api/students/enroll", json={"first_name": "Zoe", "enroll": True,
                    "class_name": "Grade 8", "section": "A", "academic_year": "2026-27"}).json()
    # attendance
    admin.post("/api/attendance/sheet", json={"class_name": "Grade 8", "section": "A",
               "date": "2026-09-10", "entries": {st["id"]: "present"}})
    # assessment + a timetable entry (timetable_entries isn't a /res resource → seed/verify via DB)
    assess = admin.post("/api/res/assessments", json={"name": "T1", "class_name": "Grade 8", "section": "A",
             "subject": "MATHS", "max_marks": 50, "status": "draft", "academic_year": "2026-27"}).json()
    iid = admin.get("/api/auth/me").json()["institution_id"]
    tdb = MongoClient(server.mongo_url)[TEST_DB]
    tdb.timetable_entries.insert_one({"id": "tt1", "institution_id": iid, "class_name": "Grade 8",
                                      "section": "A", "day": "mon", "period_no": 1, "subject": "MATHS"})
    # rename the class
    r = admin.put(f"/api/classes/{cid}", json={"name": "Grade Eight"})
    assert r.status_code == 200, r.text
    # all references moved
    assert admin.get("/api/res/students", params={"limit": 50}).json()["items"][0]["class_name"] == "Grade Eight"
    assert admin.get("/api/res/sections", params={"limit": 50}).json()["items"][0]["class_name"] == "Grade Eight"
    att = admin.get("/api/attendance/records").json()["items"]
    assert all(a["class_name"] == "Grade Eight" for a in att) and att
    assert admin.get("/api/res/assessments", params={"limit": 50}).json()["items"][0]["class_name"] == "Grade Eight"
    assert tdb.timetable_entries.find_one({"id": "tt1"})["class_name"] == "Grade Eight"
    # no leftover under old name
    assert admin.get("/api/students/filter", params={"class_name": "Grade 8"}).json()["total"] == 0


def test_rename_section_cascades(ctx):
    admin, _ = ctx["new_school"]()
    uid, cid, sid = _scaffold(admin, "Grade 5", "A")
    st = admin.post("/api/students/enroll", json={"first_name": "Ann", "enroll": True,
                    "class_name": "Grade 5", "section": "A", "academic_year": "2026-27"}).json()
    r = admin.put(f"/api/sections/{sid}", json={"name": "B", "capacity": 40, "room": "R12"})
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "B" and r.json()["capacity"] == 40 and r.json()["room"] == "R12"
    stu = admin.get(f"/api/res/students/{st['id']}").json()
    assert stu["section"] == "B"


def test_principal_scope_blocks_out_of_scope_rename(ctx):
    admin, i = ctx["new_school"]()
    # two units each with a class
    ua = admin.post("/api/res/academic_units", json={"name": "LP", "code": "LP", "status": "active"}).json()
    ub = admin.post("/api/res/academic_units", json={"name": "HS", "code": "HS", "status": "active"}).json()
    ca = admin.post("/api/res/classes", json={"name": "Grade 1", "academic_unit_id": ua["id"], "status": "active"}).json()
    cb = admin.post("/api/res/classes", json={"name": "Grade 9", "academic_unit_id": ub["id"], "status": "active"}).json()
    t = admin.post("/api/teachers", json={"name": "P", "email": f"p{i}@s6.test", "password": "Teach@123", "status": "active"}).json()
    admin.post("/api/principals", json={"teacher_id": t["id"], "scope_type": "units", "unit_ids": [ua["id"]]})
    prin = ctx["login"](f"p{i}@s6.test", "Teach@123")
    # in-scope rename ok
    assert prin.put(f"/api/classes/{ca['id']}", json={"name": "Grade One"}).status_code == 200
    # out-of-scope rename blocked
    assert prin.put(f"/api/classes/{cb['id']}", json={"name": "Hacked"}).status_code == 403


def test_delete_blocked_with_counts_then_allowed_when_empty(ctx):
    admin, _ = ctx["new_school"]()
    uid, cid, sid = _scaffold(admin, "Grade 2", "A")
    st = admin.post("/api/students/enroll", json={"first_name": "Lia", "enroll": True,
                    "class_name": "Grade 2", "section": "A", "academic_year": "2026-27"}).json()
    # section delete blocked
    r = admin.delete(f"/api/sections/{sid}")
    assert r.status_code == 409 and "student" in r.json()["detail"].lower(), r.text
    # class delete blocked
    r = admin.delete(f"/api/classes/{cid}")
    assert r.status_code == 409 and "Grade 2" in r.json()["detail"], r.text
    # remove student → now deletable
    admin.delete(f"/api/res/students/{st['id']}")
    assert admin.delete(f"/api/sections/{sid}").status_code == 200
    assert admin.delete(f"/api/classes/{cid}").status_code == 200


def test_capacity_warning_on_enroll_and_bulk(ctx):
    admin, _ = ctx["new_school"]()
    uid, cid, sid = _scaffold(admin, "Grade 3", "A", cap=1)
    # first enroll fills capacity (1/1); the enroll that hits capacity warns but succeeds
    first = admin.post("/api/students/enroll", json={"first_name": "One", "enroll": True,
                       "class_name": "Grade 3", "section": "A", "academic_year": "2026-27"})
    assert first.status_code == 200 and "warning" in first.json(), first.text
    # second enroll also succeeds (over capacity) with warning
    second = admin.post("/api/students/enroll", json={"first_name": "Two", "enroll": True,
                        "class_name": "Grade 3", "section": "A", "academic_year": "2026-27"})
    assert second.status_code == 200 and "capacity" in second.json()["warning"], second.text
    # bulk enroll returns a warning too
    bulk = admin.post("/api/students/bulk-enroll", json={"class_name": "Grade 3", "section": "A",
                      "academic_year": "2026-27", "students": [{"first_name": "Three"}]})
    assert bulk.status_code == 200 and bulk.json().get("warning"), bulk.text


def test_duplicate_section_rejected(ctx):
    admin, _ = ctx["new_school"]()
    uid, cid, sid = _scaffold(admin, "Grade 4", "A")
    # add-section with same name → 400
    r = admin.post(f"/api/classes/{cid}/sections", json={"name": "A"})
    assert r.status_code == 400, r.text
    # a new section name is fine
    assert admin.post(f"/api/classes/{cid}/sections", json={"name": "B", "capacity": 30, "room": "101"}).status_code == 200
