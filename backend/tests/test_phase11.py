"""Phase 11 — notification center fan-out, scoping, unread/mark-read. Throwaway DB."""
import sys
import pytest

sys.path.insert(0, "/app/backend")
import server  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from pymongo import MongoClient  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

TEST_DB = "lnmo_phase11_test"
PA_EMAIL = server.os.environ["PLATFORM_ADMIN_EMAIL"].lower()
PA_PW = server.os.environ["PLATFORM_ADMIN_PASSWORD"]
BASE = "https://testserver"
MON = "2026-01-05"


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
    with _client() as C:
        def login(email, pw):
            r = C.post("/api/auth/login", json={"email": email, "password": pw})
            assert r.status_code == 200, r.text
            tok = r.cookies.get("access_token")
            C.cookies.clear()
            return Sess(C, tok)

        platform = login(PA_EMAIL, PA_PW)
        platform.post("/api/res/institutions", json={
            "name": "S11", "slug": "s11", "admin_email": "a@s11.test", "admin_password": "Admin@123"})
        admin = login("a@s11.test", "Admin@123")
        admin.post("/api/res/academic_years", json={"name": "2026-27", "status": "active"})
        hs = admin.post("/api/res/academic_units", json={"name": "HS", "code": "HS", "status": "active"}).json()
        lp = admin.post("/api/res/academic_units", json={"name": "LP", "code": "LP", "status": "active"}).json()

        def teacher(n):
            return admin.post("/api/teachers", json={"name": n, "email": f"{n.lower()}@s11.test", "password": "Teach@123", "status": "active"}).json()
        tt = {n: teacher(n) for n in ("Manoj", "Prasad", "Lp1", "DeepaHS", "WholeP")}
        # Grade 8 HS (Manoj teaches), Grade 1 LP (Lp1 teaches)
        admin.post("/api/res/classes", json={"name": "Grade 8", "academic_unit_id": hs["id"], "status": "active"})
        admin.post("/api/res/sections", json={"name": "A", "class_name": "Grade 8", "status": "active"})
        admin.post("/api/res/subjects", json={"name": "Maths", "status": "active"})
        admin.post("/api/res/subject_offerings", json={"subject": "Maths", "class_name": "Grade 8", "section": "A", "max_marks": 100, "status": "active"})
        admin.post("/api/res/classes", json={"name": "Grade 1", "academic_unit_id": lp["id"], "status": "active"})
        admin.post("/api/res/sections", json={"name": "A", "class_name": "Grade 1", "status": "active"})
        admin.post("/api/res/subjects", json={"name": "Rhymes", "status": "active"})
        admin.post("/api/res/subject_offerings", json={"subject": "Rhymes", "class_name": "Grade 1", "section": "A", "max_marks": 100, "status": "active"})
        admin.post("/api/res/teacher_assignments", json={"teacher_email": tt["Manoj"]["email"], "class_name": "Grade 8", "section": "A", "subject": "Maths"})
        admin.post("/api/res/teacher_assignments", json={"teacher_email": tt["Prasad"]["email"], "class_name": "Grade 8", "section": "A", "subject": "Maths"})
        admin.post("/api/res/teacher_assignments", json={"teacher_email": tt["Lp1"]["email"], "class_name": "Grade 1", "section": "A", "subject": "Rhymes"})
        # published Monday period for Manoj (so absence creates a sub)
        admin.post("/api/timetable/place", json={"academic_year": "2026-27", "class_name": "Grade 8", "section": "A", "day": "mon", "period_no": 1, "subject": "Maths", "teacher_id": tt["Manoj"]["id"], "override": True})
        # principals: DeepaHS scoped to HS; WholeP whole-school
        admin.post("/api/principals", json={"teacher_id": tt["DeepaHS"]["id"], "scope_type": "units", "unit_ids": [hs["id"]], "designation": "principal"})
        admin.post("/api/principals", json={"teacher_id": tt["WholeP"]["id"], "scope_type": "whole_school", "designation": "principal"})
        yield {"admin": admin, "t": tt, "login": login, "hs": hs["id"], "lp": lp["id"]}
    MongoClient(server.mongo_url).drop_database(TEST_DB)


def _unread(sess):
    return sess.get("/api/notifications").json()["unread"]


def test_absence_request_fans_out_to_in_scope_managers_only(ctx):
    admin, t = ctx["admin"], ctx["t"]
    manoj = ctx["login"]("manoj@s11.test", "Teach@123")
    # Manoj self-requests leave (Grade 8 / HS)
    r = manoj.post("/api/absences", json={"teacher_id": t["Manoj"]["id"], "date": MON, "reason": "sick"})
    assert r.status_code == 200 and r.json()["absence"]["status"] == "requested"
    deepa = ctx["login"]("deepahs@s11.test", "Teach@123")
    whole = ctx["login"]("wholep@s11.test", "Teach@123")
    assert any(n["type"] == "absence_request" for n in deepa.get("/api/notifications").json()["notifications"])  # HS scope covers Grade 8
    assert any(n["type"] == "absence_request" for n in whole.get("/api/notifications").json()["notifications"])  # whole-school
    assert _unread(admin) >= 1  # admin always
    ctx["absence_id"] = r.json()["absence"]["id"]


def test_lp_only_absence_not_sent_to_hs_principal(ctx):
    admin, t = ctx["admin"], ctx["t"]
    lp1 = ctx["login"]("lp1@s11.test", "Teach@123")
    lp1.post("/api/absences", json={"teacher_id": t["Lp1"]["id"], "date": MON, "reason": "x"})
    deepa = ctx["login"]("deepahs@s11.test", "Teach@123")
    lp_reqs = [n for n in deepa.get("/api/notifications").json()["notifications"]
               if n["type"] == "absence_request" and "Lp1" in n["body"]]
    assert lp_reqs == []  # HS principal must NOT see an LP-only teacher's request
    whole = ctx["login"]("wholep@s11.test", "Teach@123")
    assert any("Lp1" in n["body"] for n in whole.get("/api/notifications").json()["notifications"] if n["type"] == "absence_request")


def test_direct_assign_notifies_substitute(ctx):
    admin, t = ctx["admin"], ctx["t"]
    admin.post(f"/api/absences/{ctx['absence_id']}/approve")
    subs = admin.get(f"/api/absences/{ctx['absence_id']}").json()["substitutions"]
    sid = subs[0]["id"]
    admin.post(f"/api/substitutions/{sid}/assign", json={"teacher_id": t["Prasad"]["id"]})
    prasad = ctx["login"]("prasad@s11.test", "Teach@123")
    assert any(n["type"] == "sub_assigned" for n in prasad.get("/api/notifications").json()["notifications"])
    # Manoj (original/absent) should NOT get a 'sub_assigned'
    manoj = ctx["login"]("manoj@s11.test", "Teach@123")
    assert not any(n["type"] == "sub_assigned" for n in manoj.get("/api/notifications").json()["notifications"])


def test_unread_count_and_mark_read(ctx):
    prasad = ctx["login"]("prasad@s11.test", "Teach@123")
    before = _unread(prasad)
    assert before >= 1
    nid = prasad.get("/api/notifications").json()["notifications"][0]["id"]
    prasad.post(f"/api/notifications/{nid}/read")
    assert _unread(prasad) == before - 1
    prasad.post("/api/notifications/mark-read", json={"all": True})
    assert _unread(prasad) == 0


def test_timetable_publish_notifies_teachers(ctx):
    admin, t = ctx["admin"], ctx["t"]
    admin.put("/api/class-hub/Grade 8/subject-staff", json={"academic_year": "2026-27", "items": [
        {"subject": "Maths", "section_teachers": {"A": t["Manoj"]["id"]}, "periods_per_week": 5}]})
    admin.post("/api/timetable/generate", json={"academic_year": "2026-27", "class_name": "Grade 8"})
    grid = admin.get("/api/timetable/grid", params={"academic_year": "2026-27", "class_name": "Grade 8", "section": "A", "mode": "draft"}).json()
    assert grid.get("draft_batch"), "expected a draft batch"
    admin.post("/api/timetable/publish", json={"batch_id": grid["draft_batch"]["id"]})
    who = ctx["login"]("manoj@s11.test", "Teach@123")
    assert any(n["type"] == "timetable_published" for n in who.get("/api/notifications").json()["notifications"])


def test_no_cross_institution_leak(ctx):
    # second institution's admin must have zero notifications from S11 events
    platform = ctx["login"](PA_EMAIL, PA_PW)
    platform.post("/api/res/institutions", json={"name": "S11b", "slug": "s11b", "admin_email": "a@s11b.test", "admin_password": "Admin@123"})
    other = ctx["login"]("a@s11b.test", "Admin@123")
    assert other.get("/api/notifications").json()["total"] == 0
