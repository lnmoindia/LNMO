"""Phase 10 — teacher absence + substitution engine. Throwaway DB."""
import sys
import pytest

sys.path.insert(0, "/app/backend")
import server  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from pymongo import MongoClient  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

TEST_DB = "lnmo_phase10_test"
PA_EMAIL = server.os.environ["PLATFORM_ADMIN_EMAIL"].lower()
PA_PW = server.os.environ["PLATFORM_ADMIN_PASSWORD"]
BASE = "https://testserver"
MON = "2026-01-05"  # a Monday


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
    with _client() as C:
        def login(email, pw):
            r = C.post("/api/auth/login", json={"email": email, "password": pw})
            assert r.status_code == 200, r.text
            tok = r.cookies.get("access_token")
            C.cookies.clear()
            return Sess(C, tok)

        platform = login(PA_EMAIL, PA_PW)
        platform.post("/api/res/institutions", json={
            "name": "S10", "slug": "s10", "admin_email": "a@s10.test", "admin_password": "Admin@123"})
        admin = login("a@s10.test", "Admin@123")
        admin.post("/api/res/academic_years", json={"name": "2026-27", "status": "active"})
        hs = admin.post("/api/res/academic_units", json={"name": "HS", "code": "HS", "status": "active"}).json()
        lp = admin.post("/api/res/academic_units", json={"name": "LP", "code": "LP", "status": "active"}).json()

        def teacher(name):
            return admin.post("/api/teachers", json={"name": name, "email": f"{name.lower()}@s10.test",
                                                     "password": "Teach@123", "status": "active"}).json()
        tt = {n: teacher(n) for n in ("Tabs", "Mina", "Max", "Free", "Busy", "Deepa")}
        # Grade 8 (HS) A/B with Maths + Science
        admin.post("/api/res/classes", json={"name": "Grade 8", "academic_unit_id": hs["id"], "status": "active"})
        for sec in ("A", "B"):
            admin.post("/api/res/sections", json={"name": sec, "class_name": "Grade 8", "status": "active"})
        for s in ("Maths", "Science"):
            admin.post("/api/res/subjects", json={"name": s, "status": "active"})
            for sec in ("A", "B"):
                admin.post("/api/res/subject_offerings", json={"subject": s, "class_name": "Grade 8", "section": sec, "max_marks": 100, "status": "active"})
        # Grade 1 (LP) for principal-scope negatives
        admin.post("/api/res/classes", json={"name": "Grade 1", "academic_unit_id": lp["id"], "status": "active"})
        admin.post("/api/res/sections", json={"name": "A", "class_name": "Grade 1", "status": "active"})
        admin.post("/api/res/subjects", json={"name": "Rhymes", "status": "active"})
        admin.post("/api/res/subject_offerings", json={"subject": "Rhymes", "class_name": "Grade 1", "section": "A", "max_marks": 100, "status": "active"})

        # subject-match assignments (per section)
        def assign(t, sec, subj, grade="Grade 8"):
            admin.post("/api/res/teacher_assignments", json={"teacher_email": t["email"], "class_name": grade, "section": sec, "subject": subj})
        assign(tt["Tabs"], "A", "Maths")       # absent teacher teaches Maths A + Science A
        assign(tt["Tabs"], "A", "Science")
        assign(tt["Mina"], "A", "Maths")       # EXACT match for Maths A
        assign(tt["Max"], "B", "Maths")        # same subject, different section

        # published Monday timetable: Tabs teaches Maths P1 and Science P2 in 8A; Busy teaches Rhymes P1 in 1A
        def place(sess, grade, sec, p, subj, t):
            r = sess.post("/api/timetable/place", json={"academic_year": "2026-27", "class_name": grade,
                          "section": sec, "day": "mon", "period_no": p, "subject": subj, "teacher_id": t["id"], "override": True})
            assert r.status_code == 200, r.text
        place(admin, "Grade 8", "A", 1, "Maths", tt["Tabs"])
        place(admin, "Grade 8", "A", 2, "Science", tt["Tabs"])
        place(admin, "Grade 1", "A", 1, "Rhymes", tt["Busy"])

        # principal Deepa scoped to HS only
        admin.post("/api/principals", json={"teacher_id": tt["Deepa"]["id"], "scope_type": "units",
                                            "unit_ids": [hs["id"]], "designation": "principal"})
        prin = login("deepa@s10.test", "Teach@123")
        yield {"admin": admin, "t": tt, "prin": prin, "login": login}
    MongoClient(server.mongo_url).drop_database(TEST_DB)


def _subs_of(admin, absence_id):
    return admin.get(f"/api/absences/{absence_id}").json()["substitutions"]


def test_direct_mark_absent_detects_affected_periods(ctx):
    admin, t = ctx["admin"], ctx["t"]
    r = admin.post("/api/absences", json={"teacher_id": t["Tabs"]["id"], "date": MON, "reason": "sick"})
    assert r.status_code == 200, r.text
    assert r.json()["absence"]["status"] == "approved"
    assert r.json()["substitutions_created"] == 2  # Maths P1 + Science P2
    subs = _subs_of(admin, r.json()["absence"]["id"])
    assert {s["subject"] for s in subs} == {"Maths", "Science"}
    assert all(s["status"] == "open" and s["day"] == "mon" for s in subs)
    ctx["absence_id"] = r.json()["absence"]["id"]


def test_duplicate_absence_blocked(ctx):
    admin, t = ctx["admin"], ctx["t"]
    r = admin.post("/api/absences", json={"teacher_id": t["Tabs"]["id"], "date": MON})
    assert r.status_code == 400


def test_suggestions_rank_exact_section_match_first_and_exclude_busy(ctx):
    admin, t = ctx["admin"], ctx["t"]
    subs = _subs_of(admin, ctx["absence_id"])
    maths = [s for s in subs if s["subject"] == "Maths"][0]
    sug = admin.get(f"/api/substitutions/{maths['id']}/suggestions").json()["suggestions"]
    ids = [s["teacher_id"] for s in sug]
    assert t["Tabs"]["id"] not in ids            # original excluded
    assert t["Busy"]["id"] not in ids            # teaching P1 Monday → excluded
    assert sug[0]["teacher_id"] == t["Mina"]["id"] and sug[0]["match"] == 2   # exact section match first
    # Max teaches Maths (other section) → match 1, ranks above plain-free
    max_row = [s for s in sug if s["teacher_id"] == t["Max"]["id"]][0]
    assert max_row["match"] == 1


def test_assign_and_busy_guard(ctx):
    admin, t = ctx["admin"], ctx["t"]
    subs = _subs_of(admin, ctx["absence_id"])
    maths = [s for s in subs if s["subject"] == "Maths"][0]
    # assigning a busy teacher (teaching P1) → 400
    bad = admin.post(f"/api/substitutions/{maths['id']}/assign", json={"teacher_id": t["Busy"]["id"]})
    assert bad.status_code == 400
    ok = admin.post(f"/api/substitutions/{maths['id']}/assign", json={"teacher_id": t["Mina"]["id"]})
    assert ok.status_code == 200
    subs = _subs_of(admin, ctx["absence_id"])
    maths = [s for s in subs if s["subject"] == "Maths"][0]
    assert maths["status"] == "assigned" and maths["substitute_teacher_id"] == t["Mina"]["id"]
    # the assigned teacher sees it + got a notification
    mina = ctx["login"]("mina@s10.test", "Teach@123")
    assert any(s["id"] == maths["id"] for s in mina.get("/api/me/substitutions").json()["assigned"])
    assert mina.get("/api/notifications").json()["unread"] >= 1


def test_request_accept_flow(ctx):
    admin, t = ctx["admin"], ctx["t"]
    subs = _subs_of(admin, ctx["absence_id"])
    sci = [s for s in subs if s["subject"] == "Science"][0]
    r = admin.post(f"/api/substitutions/{sci['id']}/request", json={"teacher_ids": [t["Free"]["id"]]})
    assert r.status_code == 200
    free = ctx["login"]("free@s10.test", "Teach@123")
    reqs = free.get("/api/me/substitutions").json()["requests"]
    assert any(s["id"] == sci["id"] for s in reqs)
    resp = free.post(f"/api/substitutions/{sci['id']}/respond", json={"accept": True})
    assert resp.status_code == 200 and resp.json()["response"] == "accepted"
    # principal makes the final pick (assign the accepting teacher)
    admin.post(f"/api/substitutions/{sci['id']}/assign", json={"teacher_id": t["Free"]["id"]})
    subs = _subs_of(admin, ctx["absence_id"])
    sci = [s for s in subs if s["subject"] == "Science"][0]
    assert sci["status"] == "assigned"


def test_teacher_self_request_then_approve_creates_subs(ctx):
    admin, t = ctx["admin"], ctx["t"]
    # Max self-requests leave on Monday (teaches nothing Monday → 0 subs, but flow works)
    maxs = ctx["login"]("max@s10.test", "Teach@123")
    r = maxs.post("/api/absences", json={"teacher_id": t["Max"]["id"], "date": MON, "reason": "personal"})
    assert r.status_code == 200 and r.json()["absence"]["status"] == "requested"
    # teacher cannot mark someone else absent
    assert maxs.post("/api/absences", json={"teacher_id": t["Free"]["id"], "date": MON}).status_code == 403
    ap = admin.post(f"/api/absences/{r.json()['absence']['id']}/approve")
    assert ap.status_code == 200


def test_bulk_auto_assign(ctx):
    admin, t = ctx["admin"], ctx["t"]
    # fresh absence for Mina on Monday? Mina has no Monday periods. Use Tabs again on a different date.
    TUE = "2026-01-06"
    admin.post("/api/timetable/place", json={"academic_year": "2026-27", "class_name": "Grade 8", "section": "A",
               "day": "tue", "period_no": 1, "subject": "Maths", "teacher_id": t["Tabs"]["id"], "override": True})
    ab = admin.post("/api/absences", json={"teacher_id": t["Tabs"]["id"], "date": TUE}).json()["absence"]
    res = admin.post(f"/api/absences/{ab['id']}/auto-assign").json()
    assert res["assigned"] >= 1
    subs = _subs_of(admin, ab["id"])
    assert all(s["status"] == "assigned" for s in subs)


def test_unit_principal_scope(ctx):
    admin, prin, t = ctx["admin"], ctx["prin"], ctx["t"]
    # principal sees HS (Grade 8) subs on Monday
    rows = prin.get("/api/substitutions", params={"date": MON}).json()["substitutions"]
    assert rows and all(s["class_name"] == "Grade 8" for s in rows)
    # dashboard works for principal
    d = prin.get("/api/substitutions/dashboard", params={"date": MON}).json()
    assert "open" in d and "assigned" in d
    # principal cannot mark an LP-only teacher absent (Busy teaches only Grade 1) → 403
    assert prin.post("/api/absences", json={"teacher_id": t["Busy"]["id"], "date": MON}).status_code == 403


# ---------------- Fix pack: cancel cascade, delete, date overlay ----------------

def test_cancel_cascades_to_substitutions(ctx):
    admin, t = ctx["admin"], ctx["t"]
    WED = "2027-01-06"  # a future Wednesday (Phase 52: only not-yet-started periods are cancellable)
    admin.post("/api/timetable/place", json={"academic_year": "2026-27", "class_name": "Grade 8", "section": "A",
               "day": "wed", "period_no": 1, "subject": "Maths", "teacher_id": t["Tabs"]["id"], "override": True})
    ab = admin.post("/api/absences", json={"teacher_id": t["Tabs"]["id"], "date": WED}).json()["absence"]
    subs = _subs_of(admin, ab["id"])
    assert len(subs) >= 1
    sid = subs[0]["id"]
    admin.post(f"/api/substitutions/{sid}/assign", json={"teacher_id": t["Mina"]["id"]})
    # before cancel: dashboard shows activity
    d0 = admin.get("/api/substitutions/dashboard", params={"date": WED}).json()
    assert d0["absent_today"] >= 1 and (d0["assigned"] + d0["open"]) >= 1
    # cancel the absence → subs cancelled
    res = admin.post(f"/api/absences/{ab['id']}/cancel", json={"reason": "Back at school"}).json()
    assert res["substitutions_cancelled"] >= 1
    subs2 = _subs_of(admin, ab["id"])
    assert all(s["status"] == "cancelled" for s in subs2)
    # dashboard back to baseline for that date
    d1 = admin.get("/api/substitutions/dashboard", params={"date": WED}).json()
    assert d1["open"] == 0 and d1["requested"] == 0 and d1["assigned"] == 0 and d1["absent_today"] == 0
    # active list excludes cancelled; history (?status=cancelled) retains them
    active = admin.get("/api/substitutions", params={"date": WED}).json()["substitutions"]
    assert all(s["status"] != "cancelled" for s in active)
    hist = admin.get("/api/substitutions", params={"date": WED, "status": "cancelled"}).json()["substitutions"]
    assert len(hist) >= 1


def test_delete_substitution_permission_and_audit(ctx):
    admin, prin, t = ctx["admin"], ctx["prin"], ctx["t"]
    THU = "2026-01-08"
    admin.post("/api/timetable/place", json={"academic_year": "2026-27", "class_name": "Grade 8", "section": "A",
               "day": "thu", "period_no": 2, "subject": "Science", "teacher_id": t["Tabs"]["id"], "override": True})
    ab = admin.post("/api/absences", json={"teacher_id": t["Tabs"]["id"], "date": THU}).json()["absence"]
    sid = _subs_of(admin, ab["id"])[0]["id"]
    # delete works for admin
    assert admin.delete(f"/api/substitutions/{sid}").status_code == 200
    assert admin.get(f"/api/absences/{ab['id']}").json()["substitutions"] == []
    # out-of-scope principal cannot delete a Grade 1 sub
    admin.post("/api/timetable/place", json={"academic_year": "2026-27", "class_name": "Grade 1", "section": "A",
               "day": "thu", "period_no": 1, "subject": "Rhymes", "teacher_id": t["Busy"]["id"], "override": True})
    ab1 = admin.post("/api/absences", json={"teacher_id": t["Busy"]["id"], "date": THU}).json()["absence"]
    s1 = _subs_of(admin, ab1["id"])
    if s1:
        assert prin.delete(f"/api/substitutions/{s1[0]['id']}").status_code == 403


def test_substitution_overlay_on_grid_and_teacher(ctx):
    admin, t = ctx["admin"], ctx["t"]
    FRI = "2026-01-09"  # Friday
    admin.post("/api/timetable/place", json={"academic_year": "2026-27", "class_name": "Grade 8", "section": "A",
               "day": "fri", "period_no": 1, "subject": "Maths", "teacher_id": t["Tabs"]["id"], "override": True})
    ab = admin.post("/api/absences", json={"teacher_id": t["Tabs"]["id"], "date": FRI}).json()["absence"]
    sid = _subs_of(admin, ab["id"])[0]["id"]
    admin.post(f"/api/substitutions/{sid}/assign", json={"teacher_id": t["Mina"]["id"]})
    # CLASS grid overlay for that date: P1 Friday shows the substitute
    grid = admin.get("/api/timetable/grid", params={"academic_year": "2026-27", "class_name": "Grade 8", "section": "A", "mode": "published", "date": FRI}).json()
    p1fri = [e for e in grid["entries"] if e["day"] == "fri" and e["period_no"] == 1][0]
    assert p1fri.get("substitution") and p1fri["substitution"]["substitute_teacher_id"] == t["Mina"]["id"]
    # without date → no overlay
    grid0 = admin.get("/api/timetable/grid", params={"academic_year": "2026-27", "class_name": "Grade 8", "section": "A", "mode": "published"}).json()
    p1fri0 = [e for e in grid0["entries"] if e["day"] == "fri" and e["period_no"] == 1][0]
    assert "substitution" not in p1fri0
    # SUBSTITUTE teacher view: the covered period appears on Friday P1, flagged
    mina = ctx["login"]("mina@s10.test", "Teach@123")
    tv = mina.get(f"/api/timetable/teacher/{t['Mina']['id']}", params={"academic_year": "2026-27", "date": FRI}).json()
    fri = [d for d in tv["schedule"] if d["day"] == "fri"][0]
    p1 = [p for p in fri["periods"] if p["period_no"] == 1][0]
    assert p1["entry"] and p1["entry"].get("is_substitution") and p1["entry"]["class_name"] == "Grade 8"
    # ORIGINAL teacher view: Friday P1 shows covered-by
    tabs = ctx["login"]("tabs@s10.test", "Teach@123")
    tv2 = tabs.get(f"/api/timetable/teacher/{t['Tabs']['id']}", params={"academic_year": "2026-27", "date": FRI}).json()
    fri2 = [d for d in tv2["schedule"] if d["day"] == "fri"][0]
    p1o = [p for p in fri2["periods"] if p["period_no"] == 1][0]
    assert p1o["entry"] and p1o["entry"].get("substitution", {}).get("covered_by")
