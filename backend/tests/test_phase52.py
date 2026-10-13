"""Phase 52 — cancel absence / remove single cover + portal substitute notice. Throwaway DB, controllable clock."""
import sys
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo
import pytest

sys.path.insert(0, "/app/backend")
import server  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from pymongo import MongoClient  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

TEST_DB = "lnmo_phase52_test"
PA_EMAIL = server.os.environ["PLATFORM_ADMIN_EMAIL"].lower()
PA_PW = server.os.environ["PLATFORM_ADMIN_PASSWORD"]
IST = ZoneInfo("Asia/Kolkata")
NOW = [datetime(2027, 1, 1, 8, 0, tzinfo=IST)]


async def _fake_now(iid):
    return NOW[0]


def at(date, hhmm):
    y, m, d = (int(x) for x in date.split("-"))
    hh, mm = (int(x) for x in hhmm.split(":"))
    NOW[0] = datetime(y, m, d, hh, mm, tzinfo=IST)


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
    real_now = server._sub_now
    server._sub_now = _fake_now
    mon = MongoClient(server.mongo_url)[TEST_DB]
    MongoClient(server.mongo_url).drop_database(TEST_DB)
    with TestClient(server.app, base_url="https://testserver") as C:
        def login(email, pw):
            r = C.post("/api/auth/login", json={"email": email, "password": pw})
            assert r.status_code == 200, r.text
            tok = r.cookies.get("access_token")
            C.cookies.clear()
            return Sess(C, tok)

        platform = login(PA_EMAIL, PA_PW)
        platform.post("/api/res/institutions", json={"name": "S52", "slug": "s52", "admin_email": "a@s52.test", "admin_password": "Admin@123"})
        admin = login("a@s52.test", "Admin@123")
        A = mon.institutions.find_one({"slug": "s52"})["id"]
        admin.post("/api/res/academic_years", json={"name": "2026-27", "status": "active"})
        hs = admin.post("/api/res/academic_units", json={"name": "HS", "code": "HS", "status": "active"}).json()
        lp = admin.post("/api/res/academic_units", json={"name": "LP", "code": "LP", "status": "active"}).json()
        t = {n: admin.post("/api/teachers", json={"name": n, "email": f"{n.lower()}@s52.test", "password": "Teach@123", "status": "active"}).json()
             for n in ("Tabs", "Mina", "Max", "Free", "Busy", "Deepa")}
        for i, n in enumerate(t):
            mon.users.update_one({"id": t[n]["id"]}, {"$set": {"phone": f"+91 90000 0000{i}"}})
        admin.post("/api/res/classes", json={"name": "Grade 8", "academic_unit_id": hs["id"], "status": "active"})
        admin.post("/api/res/classes", json={"name": "Grade 1", "academic_unit_id": lp["id"], "status": "active"})
        for cls, sec in (("Grade 8", "A"), ("Grade 8", "B"), ("Grade 1", "A")):
            admin.post("/api/res/sections", json={"name": sec, "class_name": cls, "status": "active"})
        for s, cls, sec in (("Maths", "Grade 8", "A"), ("Science", "Grade 8", "A"), ("Maths", "Grade 8", "B"), ("Rhymes", "Grade 1", "A")):
            admin.post("/api/res/subjects", json={"name": s, "status": "active"})
            admin.post("/api/res/subject_offerings", json={"subject": s, "class_name": cls, "section": sec, "max_marks": 100, "status": "active"})

        def place(cls, sec, p, subj, who):
            r = admin.post("/api/timetable/place", json={"academic_year": "2026-27", "class_name": cls, "section": sec, "day": "wed",
                                                         "period_no": p, "subject": subj, "teacher_id": t[who]["id"], "override": True})
            assert r.status_code == 200, r.text
        place("Grade 8", "A", 1, "Maths", "Tabs")
        place("Grade 8", "A", 2, "Science", "Tabs")
        place("Grade 8", "B", 1, "Maths", "Max")
        place("Grade 1", "A", 1, "Rhymes", "Busy")
        admin.post("/api/principals", json={"teacher_id": t["Deepa"]["id"], "scope_type": "units", "unit_ids": [hs["id"]], "designation": "principal"})

        mon.students.insert_many([
            {"id": "s8a", "institution_id": A, "first_name": "Ria", "last_name": "K", "class_name": "Grade 8", "section": "A", "enrollment_status": "enrolled"},
            {"id": "s8b", "institution_id": A, "first_name": "Om", "last_name": "B", "class_name": "Grade 8", "section": "B", "enrollment_status": "enrolled"},
        ])

        def portal_user(name, email, role, **extra):
            mon.users.insert_one({"id": str(uuid.uuid4()), "name": name, "email": email, "password_hash": server.hash_password("Pass@123"),
                                  "role": role, "institution_id": A, "status": "active", "must_change_password": False,
                                  "created_at": server.now_iso(), **extra})
            return login(email, "Pass@123")
        yield {"admin": admin, "t": t, "db": mon, "login": login, "prin": login("deepa@s52.test", "Teach@123"),
               "stu8a": portal_user("Ria", "ria@s52.test", "student", student_id="s8a"),
               "stu8b": portal_user("Om", "om@s52.test", "student", student_id="s8b"),
               "parent": portal_user("Mr K", "pk@s52.test", "parent", student_ids=["s8a"])}
    server._sub_now = real_now
    MongoClient(server.mongo_url).drop_database(TEST_DB)


def _absent(admin, teacher_id, date):
    r = admin.post("/api/absences", json={"teacher_id": teacher_id, "date": date, "reason": "Fever"})
    assert r.status_code == 200, r.text
    ab = r.json()["absence"]
    subs = sorted(admin.get(f"/api/absences/{ab['id']}").json()["substitutions"], key=lambda s: s["period_no"])
    return ab, subs


def _bells(db, uid, ntype, related):
    return db.notifications.count_documents({"user_id": uid, "type": ntype, "related_id": related})


def test_cancel_absence_keeps_started_periods_and_notifies(ctx):
    admin, t, db = ctx["admin"], ctx["t"], ctx["db"]
    at("2027-01-05", "18:00")
    ab, subs = _absent(admin, t["Tabs"]["id"], "2027-01-06")
    assert [s["period_no"] for s in subs] == [1, 2]
    p1, p2 = subs
    assert admin.post(f"/api/substitutions/{p1['id']}/assign", json={"teacher_id": t["Mina"]["id"]}).status_code == 200
    assert admin.post(f"/api/substitutions/{p2['id']}/request", json={"teacher_ids": [t["Free"]["id"], t["Deepa"]["id"]]}).status_code == 200
    at("2027-01-06", "09:30")  # P1 (09:00) has started, P2 (09:45) has not
    pv = admin.get(f"/api/absences/{ab['id']}/cancel-preview").json()
    assert pv["kept_periods"] == [1] and pv["asked_count"] == 2 and pv["assigned_count"] == 0
    assert admin.post(f"/api/absences/{ab['id']}/cancel", json={"reason": "ok"}).status_code == 422
    assert admin.post(f"/api/absences/{ab['id']}/cancel", json={}).status_code == 422
    msgs0 = db.messages.count_documents({"module": "substitution"})
    r = admin.post(f"/api/absences/{ab['id']}/cancel", json={"reason": "Recovered, back at school"})
    assert r.status_code == 200, r.text
    assert r.json()["substitutions_cancelled"] == 1 and r.json()["kept_periods"] == [1]
    s1, s2 = (db.substitutions.find_one({"id": x["id"]}) for x in (p1, p2))
    assert s1["status"] == "assigned" and s2["status"] == "cancelled" and s2["cancel_reason"] == "Recovered, back at school"
    assert db.substitutions.count_documents({"absence_id": ab["id"]}) == 2  # never deleted
    assert _bells(db, t["Free"]["id"], "sub_cancelled", p2["id"]) == 1 and _bells(db, t["Deepa"]["id"], "sub_cancelled", p2["id"]) == 1
    assert _bells(db, t["Mina"]["id"], "sub_cancelled", p1["id"]) == 0  # past period untouched
    assert _bells(db, t["Tabs"]["id"], "absence_cancelled", ab["id"]) == 1
    n = db.notifications.find_one({"user_id": t["Free"]["id"], "type": "sub_cancelled"})
    assert "Grade 8 A P2 on 2027-01-06 is cancelled — Tabs is back" in n["body"]
    assert db.messages.count_documents({"module": "substitution"}) - msgs0 == 3  # 2 asked + original teacher (STUB)
    a = db.absences.find_one({"id": ab["id"]})
    assert a["status"] == "cancelled" and a["cancelled_by_name"] and a["kept_periods"] == [1]
    assert db.audit_logs.count_documents({"action": "cancel_absence", "entity_id": ab["id"]}) == 1
    assert admin.post(f"/api/absences/{ab['id']}/cancel", json={"reason": "again please"}).status_code == 400
    hist = admin.get("/api/absences", params={"date": "2027-01-06"}).json()["absences"]
    assert any(x["id"] == ab["id"] and x["status"] == "cancelled" and x["cancel_reason"] for x in hist)


def test_remove_single_cover(ctx):
    admin, t, db, login = ctx["admin"], ctx["t"], ctx["db"], ctx["login"]
    at("2027-01-12", "12:00")
    ab, (p1, p2) = _absent(admin, t["Tabs"]["id"], "2027-01-13")
    admin.post(f"/api/substitutions/{p1['id']}/assign", json={"teacher_id": t["Mina"]["id"]})
    admin.post(f"/api/substitutions/{p2['id']}/request", json={"teacher_ids": [t["Free"]["id"]]})
    mina = login("mina@s52.test", "Teach@123")
    assert any(x["id"] == p1["id"] for x in mina.get("/api/me/substitutions").json()["assigned"])
    r = admin.post(f"/api/substitutions/{p1['id']}/remove-cover", json={"reason": "swap"})
    assert r.status_code == 200 and r.json()["notified"] == 1
    s = db.substitutions.find_one({"id": p1["id"]})
    assert s["status"] == "open" and s["substitute_teacher_id"] is None and s["cover_history"][-1]["teacher_name"] == "Mina"
    assert _bells(db, t["Mina"]["id"], "sub_cancelled", p1["id"]) == 1
    assert _bells(db, t["Free"]["id"], "sub_cancelled", p1["id"]) == 0  # only that substitute
    assert not any(x["id"] == p1["id"] for x in mina.get("/api/me/substitutions").json()["assigned"])
    assert admin.post(f"/api/substitutions/{p1['id']}/remove-cover", json={}).status_code == 400  # nothing to remove
    at("2027-01-13", "10:00")  # P2 started 09:45
    assert admin.post(f"/api/substitutions/{p2['id']}/remove-cover", json={}).status_code == 400
    assert db.audit_logs.count_documents({"action": "remove_cover", "entity_id": p1["id"]}) == 1


def test_principal_and_teacher_cancel_scope(ctx):
    admin, t, prin, login = ctx["admin"], ctx["t"], ctx["prin"], ctx["login"]
    at("2027-01-18", "12:00")
    ab, _ = _absent(admin, t["Busy"]["id"], "2027-01-20")  # LP-only teacher
    assert prin.get(f"/api/absences/{ab['id']}/cancel-preview").status_code == 403
    assert prin.post(f"/api/absences/{ab['id']}/cancel", json={"reason": "not mine"}).status_code == 403
    hs_ab, subs = _absent(admin, t["Max"]["id"], "2027-01-20")
    assert prin.post(f"/api/absences/{hs_ab['id']}/cancel", json={"reason": "in my division"}).status_code == 200
    # a principal can't remove cover outside their divisions
    busy_sub = admin.get(f"/api/absences/{ab['id']}").json()["substitutions"][0]
    admin.post(f"/api/substitutions/{busy_sub['id']}/assign", json={"teacher_id": t["Free"]["id"]})
    assert prin.post(f"/api/substitutions/{busy_sub['id']}/remove-cover", json={}).status_code == 403
    # teacher: own leave only, and only before it starts
    tabs, mina = login("tabs@s52.test", "Teach@123"), login("mina@s52.test", "Teach@123")
    own = tabs.post("/api/absences", json={"teacher_id": t["Tabs"]["id"], "date": "2027-01-27", "reason": "Wedding"}).json()["absence"]
    assert mina.post(f"/api/absences/{own['id']}/cancel", json={"reason": "not hers"}).status_code == 403
    at("2027-01-27", "10:00")
    assert tabs.post(f"/api/absences/{own['id']}/cancel", json={"reason": "too late now"}).status_code == 400
    at("2027-01-26", "10:00")
    assert tabs.post(f"/api/absences/{own['id']}/cancel", json={"reason": "plans changed"}).status_code == 200


def test_portal_substitute_notice_and_isolation(ctx):
    admin, t, db = ctx["admin"], ctx["t"], ctx["db"]
    at("2027-02-03", "07:30")
    ab, (p1, p2) = _absent(admin, t["Tabs"]["id"], "2027-02-03")
    admin.post(f"/api/substitutions/{p1['id']}/assign", json={"teacher_id": t["Mina"]["id"]})
    tc = ctx["stu8a"].get("/api/portal/timetable").json()["today_changes"]
    assert tc["date"] == "2027-02-03" and tc["day"] == "wed"
    assert tc["items"] == [{"period_no": 1, "period_label": "P1", "kind": "substitute", "substitute_name": "Mina"},
                           {"period_no": 2, "period_label": "P2", "kind": "absent", "substitute_name": None}]
    raw = ctx["stu8a"].get("/api/portal/timetable").text
    assert "Fever" not in raw and "@s52.test" not in raw and "+91" not in raw
    assert ctx["stu8b"].get("/api/portal/timetable").json()["today_changes"]["items"] == []
    pr = ctx["parent"].get("/api/parent/child/s8a/timetable")
    assert pr.status_code == 200 and pr.json()["today_changes"]["items"] == tc["items"] and pr.json()["entries"]
    assert ctx["parent"].get("/api/parent/child/s8b/timetable").status_code == 403
    assert "Fever" not in pr.text
    # remove a single cover → back to "cover being arranged"
    admin.post(f"/api/substitutions/{p1['id']}/remove-cover", json={})
    assert ctx["stu8a"].get("/api/portal/timetable").json()["today_changes"]["items"][0]["kind"] == "absent"
    # cancel the absence → notice disappears
    assert admin.post(f"/api/absences/{ab['id']}/cancel", json={"reason": "Back after all"}).status_code == 200
    assert ctx["stu8a"].get("/api/portal/timetable").json()["today_changes"]["items"] == []
    assert ctx["parent"].get("/api/parent/child/s8a/timetable").json()["today_changes"]["items"] == []
    # another day → nothing
    at("2027-02-04", "08:00")
    assert ctx["stu8a"].get("/api/portal/timetable").json()["today_changes"]["items"] == []
