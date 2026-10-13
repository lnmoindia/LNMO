"""Class Hub consolidation — subject-staff writes sync teacher_assignments + subject_requirements,
   class-teacher per-section, unit-principal scope, and Phase 7 regression. Throwaway DB."""
import sys
import pytest

sys.path.insert(0, "/app/backend")
import server  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from pymongo import MongoClient  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

TEST_DB = "lnmo_classhub_test"
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
        _n["i"] += 1
        i = _n["i"]
        platform.post("/api/res/institutions", json={
            "name": f"CH{i}", "slug": f"ch-{i}", "admin_email": f"a{i}@ch.test", "admin_password": "Admin@123"})
        admin = login(f"a{i}@ch.test", "Admin@123")
        admin.post("/api/res/academic_years", json={"name": "2026-27", "status": "active"})
        hs = admin.post("/api/res/academic_units", json={"name": "HS", "code": "HS", "status": "active"}).json()
        lp = admin.post("/api/res/academic_units", json={"name": "LP", "code": "LP", "status": "active"}).json()
        # Grade 8 (HS) with A/B/C and two subjects
        admin.post("/api/res/classes", json={"name": "Grade 8", "academic_unit_id": hs["id"], "status": "active"})
        for sec in ("A", "B", "C"):
            admin.post("/api/res/sections", json={"name": sec, "class_name": "Grade 8", "status": "active"})
        for s in ("Mathematics", "Physics"):
            admin.post("/api/res/subjects", json={"name": s, "status": "active"})
            admin.post("/api/res/subject_offerings", json={"subject": s, "class_name": "Grade 8", "max_marks": 100, "status": "active"})
        # Grade 1 (LP) — out of HS principal scope
        admin.post("/api/res/classes", json={"name": "Grade 1", "academic_unit_id": lp["id"], "status": "active"})
        admin.post("/api/res/sections", json={"name": "A", "class_name": "Grade 1", "status": "active"})
        # teachers
        teachers = {}
        for name in ("Mara", "Nila", "Ravi"):
            teachers[name] = admin.post("/api/teachers", json={
                "name": name, "email": f"{name.lower()}{i}@ch.test", "password": "Teach@123", "status": "active"}).json()
        # a unit principal scoped to HS
        prin = admin.post("/api/teachers", json={
            "name": "Deepa", "email": f"deepa{i}@ch.test", "password": "Teach@123", "status": "active"}).json()
        admin.post("/api/principals", json={"teacher_id": prin["id"], "scope_type": "units",
                                            "unit_ids": [hs["id"]], "designation": "principal"})
        prin_sess = login(f"deepa{i}@ch.test", "Teach@123")
        yield {"admin": admin, "teachers": teachers, "prin": prin_sess,
               "hs": hs["id"], "lp": lp["id"], "i": i, "login": login}
    MongoClient(server.mongo_url).drop_database(TEST_DB)


def test_subject_staff_get_lists_sections_and_subjects(ctx):
    r = ctx["admin"].get("/api/class-hub/Grade 8/subject-staff", params={"academic_year": "2026-27"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["sections"] == ["A", "B", "C"]
    assert {it["subject"] for it in d["items"]} == {"Mathematics", "Physics"}


def test_per_section_write_syncs_both_collections(ctx):
    admin, t = ctx["admin"], ctx["teachers"]
    r = admin.put("/api/class-hub/Grade 8/subject-staff", json={"academic_year": "2026-27", "items": [
        {"subject": "Mathematics", "section_teachers": {"A": t["Mara"]["id"], "B": t["Nila"]["id"]},
         "periods_per_week": 6, "consecutive_periods": 2, "must_be_consecutive": True},
    ]})
    assert r.status_code == 200, r.text
    # teacher_assignments reflect per-section
    ta = admin.get("/api/res/teacher_assignments", params={"limit": 500}).json()["items"]
    math = [a for a in ta if a["class_name"] == "Grade 8" and a.get("subject") == "Mathematics"]
    by_sec = {a["section"]: a["teacher_id"] for a in math}
    assert by_sec.get("A") == t["Mara"]["id"] and by_sec.get("B") == t["Nila"]["id"]
    # subject_requirements reflect the same (sync proof)
    req = admin.get("/api/timetable/requirements", params={"academic_year": "2026-27", "class_name": "Grade 8"}).json()
    m = [it for it in req["items"] if it["subject"] == "Mathematics"][0]
    assert m["periods_per_week"] == 6 and m["consecutive_periods"] == 2 and m["must_be_consecutive"] is True
    assert m["section_teachers"].get("A") == t["Mara"]["id"]
    assert t["Mara"]["id"] in m["teacher_ids"] and t["Nila"]["id"] in m["teacher_ids"]


def test_clearing_a_section_teacher_removes_assignment(ctx):
    admin, t = ctx["admin"], ctx["teachers"]
    admin.put("/api/class-hub/Grade 8/subject-staff", json={"academic_year": "2026-27", "items": [
        {"subject": "Physics", "section_teachers": {"C": t["Ravi"]["id"]}, "periods_per_week": 4}]})
    ta = admin.get("/api/res/teacher_assignments", params={"limit": 500}).json()["items"]
    assert any(a["class_name"] == "Grade 8" and a.get("subject") == "Physics" and a["section"] == "C" for a in ta)
    # now clear C
    admin.put("/api/class-hub/Grade 8/subject-staff", json={"academic_year": "2026-27", "items": [
        {"subject": "Physics", "section_teachers": {"C": ""}, "periods_per_week": 4}]})
    ta = admin.get("/api/res/teacher_assignments", params={"limit": 500}).json()["items"]
    assert not any(a["class_name"] == "Grade 8" and a.get("subject") == "Physics" and a["section"] == "C" for a in ta)


def test_class_teacher_per_section_assignment(ctx):
    admin, t = ctx["admin"], ctx["teachers"]
    secs = {s["name"]: s for s in admin.get("/api/res/sections", params={"limit": 500}).json()["items"] if s["class_name"] == "Grade 8"}
    r = admin.put(f"/api/res/sections/{secs['A']['id']}", json={"class_teacher_id": t["Mara"]["id"]})
    assert r.status_code == 200, r.text
    assert r.json()["class_teacher"] == "Mara"


def test_unit_principal_scope_enforced(ctx):
    prin = ctx["prin"]
    # in-scope HS grade → 200
    assert prin.get("/api/class-hub/Grade 8/subject-staff", params={"academic_year": "2026-27"}).status_code == 200
    # out-of-scope LP grade → 403
    r = prin.get("/api/class-hub/Grade 1/subject-staff", params={"academic_year": "2026-27"})
    assert r.status_code == 403, r.text
    # principal cannot write to out-of-scope grade
    w = prin.put("/api/class-hub/Grade 1/subject-staff", json={"academic_year": "2026-27", "items": []})
    assert w.status_code == 403


def test_phase7_requirements_put_still_works(ctx):
    admin = ctx["admin"]
    r = admin.put("/api/timetable/requirements", json={"academic_year": "2026-27", "class_name": "Grade 8", "items": [
        {"subject": "Mathematics", "periods_per_week": 5, "consecutive_periods": 1, "teacher_ids": []},
        {"subject": "Physics", "periods_per_week": 4, "consecutive_periods": 1, "teacher_ids": []}]})
    assert r.status_code == 200, r.text
    items = {it["subject"]: it for it in r.json()["items"]}
    assert items["Mathematics"]["periods_per_week"] == 5 and items["Physics"]["periods_per_week"] == 4


# ---------------- Refinement batch: per-section offerings, rename cascade, first-period rule ----------------

def _mk_grade(admin, grade, unit_id, secs, subjects):
    admin.post("/api/res/classes", json={"name": grade, "academic_unit_id": unit_id, "status": "active"})
    for s in secs:
        admin.post("/api/res/sections", json={"name": s, "class_name": grade, "status": "active"})
    for s in subjects:
        admin.post("/api/res/subjects", json={"name": s, "status": "active"})


def test_per_section_offering_add_lists_only_that_section(ctx):
    admin, i = ctx["admin"], ctx["i"]
    _mk_grade(admin, "Grade 6", ctx["lp"], ["A", "B", "C"], ["Geography"])
    # offer Geography to A and B only
    for sec in ("A", "B"):
        r = admin.post("/api/class-hub/Grade 6/offerings", json={"subject": "Geography", "section": sec})
        assert r.status_code == 200, r.text
    d = admin.get("/api/class-hub/Grade 6/subject-staff", params={"academic_year": "2026-27"}).json()
    geo = [it for it in d["items"] if it["subject"] == "Geography"][0]
    assert geo["offered_sections"] == ["A", "B"]
    # catalog is returned for the add picker
    assert any(c["name"] == "Geography" for c in d["catalog"])


def test_per_section_offering_remove_cascade(ctx):
    admin, t = ctx["admin"], ctx["teachers"]
    # assign a teacher to Geography A, then remove A → assignment + section teacher cleared
    admin.put("/api/class-hub/Grade 6/subject-staff", json={"academic_year": "2026-27", "items": [
        {"subject": "Geography", "section_teachers": {"A": t["Mara"]["id"], "B": t["Nila"]["id"]}, "periods_per_week": 3}]})
    ta = admin.get("/api/res/teacher_assignments", params={"limit": 500}).json()["items"]
    assert any(a["class_name"] == "Grade 6" and a.get("subject") == "Geography" and a["section"] == "A" for a in ta)
    d = admin.delete("/api/class-hub/Grade 6/offerings", params={"subject": "Geography", "section": "A"}).json()
    assert d["cascade"]["assignments_removed"] >= 1 and d["cascade"]["section_teacher_cleared"] is True
    ta = admin.get("/api/res/teacher_assignments", params={"limit": 500}).json()["items"]
    assert not any(a["class_name"] == "Grade 6" and a.get("subject") == "Geography" and a["section"] == "A" for a in ta)
    geo = [it for it in d["items"] if it["subject"] == "Geography"][0]
    assert geo["offered_sections"] == ["B"]
    # remove last section → requirement row pulled
    d2 = admin.delete("/api/class-hub/Grade 6/offerings", params={"subject": "Geography", "section": "B"}).json()
    assert d2["cascade"]["requirement_removed"] is True
    assert not any(it["subject"] == "Geography" for it in d2["items"])


def test_offering_remove_blocked_with_counts(ctx):
    admin = ctx["admin"]
    admin.post("/api/class-hub/Grade 6/offerings", json={"subject": "Geography", "section": "C"})
    # an assessment referencing the offering blocks removal
    admin.post("/api/res/assessments", json={"name": "Unit Test", "class_name": "Grade 6", "section": "C",
                                             "subject": "Geography", "max_marks": 20, "status": "active"})
    r = admin.delete("/api/class-hub/Grade 6/offerings", params={"subject": "Geography", "section": "C"})
    assert r.status_code == 409 and "assessment" in r.json()["detail"].lower()


def test_section_rename_cascade_from_classhub(ctx):
    admin, i = ctx["admin"], ctx["i"]
    _mk_grade(admin, "Grade 7", ctx["lp"], ["X"], ["History"])
    admin.post("/api/class-hub/Grade 7/offerings", json={"subject": "History", "section": "X"})
    secs = {s["name"]: s for s in admin.get("/api/res/sections", params={"limit": 500}).json()["items"] if s["class_name"] == "Grade 7"}
    r = admin.put(f"/api/res/sections/{secs['X']['id']}", json={"name": "Y"})
    assert r.status_code == 200, r.text
    offs = admin.get("/api/res/subject_offerings", params={"limit": 500}).json()["items"]
    hist = [o for o in offs if o["class_name"] == "Grade 7" and o["subject"] == "History"][0]
    assert hist["section"] == "Y"  # offering followed the rename


def test_first_period_rule_reserves_p1(ctx):
    admin, t = ctx["admin"], ctx["teachers"]
    _mk_grade(admin, "Grade 9", ctx["hs"], ["A"], ["Civics"])
    admin.post("/api/class-hub/Grade 9/offerings", json={"subject": "Civics", "section": "A"})
    # class teacher = Ravi, who teaches Civics in 9A
    secs = {s["name"]: s for s in admin.get("/api/res/sections", params={"limit": 500}).json()["items"] if s["class_name"] == "Grade 9"}
    admin.put(f"/api/res/sections/{secs['A']['id']}", json={"class_teacher_id": t["Ravi"]["id"], "class_teacher_first_period": True})
    admin.put("/api/class-hub/Grade 9/subject-staff", json={"academic_year": "2026-27", "items": [
        {"subject": "Civics", "section_teachers": {"A": t["Ravi"]["id"]}, "periods_per_week": 5}]})
    g = admin.post("/api/timetable/generate", json={"academic_year": "2026-27", "class_name": "Grade 9"}).json()
    grid = admin.get("/api/timetable/grid", params={"academic_year": "2026-27", "class_name": "Grade 9", "section": "A", "mode": "draft"}).json()
    ents = grid["entries"]
    p1 = min(e["period_no"] for e in ents)
    p1_entries = [e for e in ents if e["period_no"] == p1]
    days_with_p1 = {e["day"] for e in p1_entries}
    # every working day's P1 is Civics taught by the class teacher
    assert len(days_with_p1) >= 1
    for e in p1_entries:
        assert e["subject"] == "Civics" and e["teacher_id"] == t["Ravi"]["id"]
    # quota accounting: Civics total == 5 (P1 reservations count toward quota)
    assert sum(1 for e in ents if e["subject"] == "Civics") == 5


def test_first_period_toggle_but_teacher_teaches_nothing(ctx):
    admin, t = ctx["admin"], ctx["teachers"]
    _mk_grade(admin, "Grade 10x", ctx["hs"], ["A"], ["Economics"])
    admin.post("/api/class-hub/Grade 10x/offerings", json={"subject": "Economics", "section": "A"})
    secs = {s["name"]: s for s in admin.get("/api/res/sections", params={"limit": 500}).json()["items"] if s["class_name"] == "Grade 10x"}
    # class teacher Nila, toggle on, but Economics teacher is Mara → ct teaches nothing here
    admin.put(f"/api/res/sections/{secs['A']['id']}", json={"class_teacher_id": t["Nila"]["id"], "class_teacher_first_period": True})
    admin.put("/api/class-hub/Grade 10x/subject-staff", json={"academic_year": "2026-27", "items": [
        {"subject": "Economics", "section_teachers": {"A": t["Mara"]["id"]}, "periods_per_week": 3}]})
    g = admin.post("/api/timetable/generate", json={"academic_year": "2026-27", "class_name": "Grade 10x"}).json()
    assert any("rule skipped" in u["reason"] for u in g["unplaced"])  # clean note, no crash
    assert g["placed_count"] >= 1


def test_offering_endpoints_unit_principal_scope(ctx):
    prin = ctx["prin"]
    # out-of-scope LP grade (Grade 6) → 403 on add and remove
    assert prin.post("/api/class-hub/Grade 6/offerings", json={"subject": "History", "section": "A"}).status_code == 403
    assert prin.delete("/api/class-hub/Grade 6/offerings", params={"subject": "History", "section": "A"}).status_code == 403
