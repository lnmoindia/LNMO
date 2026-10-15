"""Phase M3: push notifications. In-process (TestClient) on a throwaway school; the Expo HTTP endpoint is MOCKED here only."""
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import bcrypt
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.chdir(Path(__file__).resolve().parents[1])
import server  # noqa: E402
import push  # noqa: E402

db = server.db  # motor (used only inside the app loop via portal)
from pymongo import MongoClient  # noqa: E402
sdb = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

TAG = uuid.uuid4().hex[:6]
PW = "Passw0rd!x"
H = bcrypt.hashpw(PW.encode(), bcrypt.gensalt()).decode()
TOK = lambda n: f"ExponentPushToken[m3{TAG}{n}xxxxxxxxxxxx]"  # noqa: E731


class FakeExpo:
    """Mocked https://exp.host push + receipts. `plan` = list of HTTP codes to return before succeeding."""
    def __init__(self):
        self.sent, self.receipts, self.plan, self.bad, self.receipt_err = [], [], [], set(), set()

    async def __call__(self, url, payload):
        if self.plan:
            return self.plan.pop(0), {"errors": [{"message": "busy"}]}
        if url.endswith("/getReceipts"):
            self.receipts.append(payload)
            return 200, {"data": {i: ({"status": "error", "message": "gone", "details": {"error": "DeviceNotRegistered"}}
                                      if i in self.receipt_err else {"status": "ok"}) for i in payload["ids"]}}
        self.sent += payload
        data = []
        for m in payload:
            if m["to"] in self.bad:
                data.append({"status": "error", "message": "not registered", "details": {"error": "DeviceNotRegistered"}})
            else:
                data.append({"status": "ok", "id": "tkt-" + m["to"][-14:-1]})
        return 200, {"data": data}

    def to(self, token):
        return [m for m in self.sent if m["to"] == token]


@pytest.fixture(scope="module")
def ctx(monkeymodule):
    iid = str(uuid.uuid4())
    sdb.institutions.insert_one({"id": iid, "name": f"M3 Throwaway {TAG}", "code": f"M3{TAG}".upper(), "slug": f"m3{TAG}",
                                 "status": "active", "setup_complete": True, "timezone": "Asia/Kolkata", "created_at": "2026-10-14T00:00:00+00:00"})
    u = lambda **k: {"id": str(uuid.uuid4()), "institution_id": iid, "password_hash": H, "status": "active", **k}  # noqa: E731
    st = {"id": str(uuid.uuid4()), "institution_id": iid, "first_name": "Kiran", "last_name": "Rao", "class_name": "Grade 8",
          "section": "A", "enrollment_status": "enrolled", "status": "active"}
    U = {"admin": u(name="Admin", email=f"admin{TAG}@m3.test", role="institution_admin"),
         "ct": u(name="Class Teacher", email=f"ct{TAG}@m3.test", role="teacher"),
         "stu": u(name="Kiran", email=f"kiran{TAG}@m3.test", role="student", student_id=st["id"]),
         "par": u(name="Parent Rao", email=f"par{TAG}@m3.test", role="parent", student_ids=[st["id"]])}
    st["user_id"] = U["stu"]["id"]
    sdb.users.insert_many([dict(x) for x in U.values()])
    sdb.students.insert_one(dict(st))
    sdb.sections.insert_one({"id": str(uuid.uuid4()), "institution_id": iid, "class_name": "Grade 8", "name": "A", "class_teacher_id": U["ct"]["id"]})
    fake = FakeExpo()
    monkeymodule.setattr(push, "_http_post", fake)
    monkeymodule.setattr(push, "RECEIPT_DELAY_S", 0)
    monkeymodule.setattr(push, "RETRY_BASE_S", 0)
    with TestClient(server.app, base_url="https://testserver") as c:
        def hdr(k):
            r = c.post("/api/auth/login", json={"email": U[k]["email"], "password": PW}, headers={"X-Client": "mobile"})
            assert r.status_code == 200, r.text
            return {"Authorization": f"Bearer {r.json()['access_token']}", "X-Client": "mobile"}
        A = {k: hdr(k) for k in U}
        c.cookies.clear()  # mobile clients authenticate with Bearer only

        def drain():
            c.portal.call(push.drain)
        yield {"iid": iid, "U": U, "st": st, "c": c, "A": A, "fake": fake, "drain": drain}
    for col in ("users", "students", "sections", "notifications", "messages", "parent_threads", "parent_messages", "push_preferences", "audit_logs"):
        sdb[col].delete_many({"institution_id": iid})
    sdb.push_tokens.delete_many({"token": {"$regex": f"m3{TAG}"}})
    sdb.push_throttle.delete_many({"key": {"$regex": "|".join(x["id"] for x in U.values())}})
    sdb.push_preferences.delete_many({"user_id": {"$in": [x["id"] for x in U.values()]}})
    sdb.institutions.delete_one({"id": iid})


def reg(ctx, who, n, platform="android"):
    r = ctx["c"].post("/api/push/register", headers=ctx["A"][who], json={"token": TOK(n), "platform": platform, "device_name": "Pixel", "app_version": "1.0.0"})
    assert r.status_code == 200, r.text


def test_register_validation_scoping_and_prefs(ctx):
    c, A = ctx["c"], ctx["A"]
    assert c.post("/api/push/register", json={"token": TOK(0)}).status_code == 401
    assert c.post("/api/push/register", headers=A["par"], json={"token": "not-a-token"}).status_code == 400
    reg(ctx, "par", 0)
    t = sdb.push_tokens.find_one({"token": TOK(0)})
    assert t["user_id"] == ctx["U"]["par"]["id"] and t["institution_id"] == ctx["iid"] and t["active"] and t["platform"] == "android"
    reg(ctx, "stu", 0)  # same device signs in as another user → token moves
    assert sdb.push_tokens.count_documents({"token": TOK(0)}) == 1 and sdb.push_tokens.find_one({"token": TOK(0)})["user_id"] == ctx["U"]["stu"]["id"]
    assert c.post("/api/push/unregister", headers=A["par"], json={"token": TOK(0)}).json()["deactivated"] == 0  # not the parent's any more
    assert c.post("/api/push/unregister", headers=A["stu"], json={"token": TOK(0)}).json()["deactivated"] == 1
    assert not sdb.push_tokens.find_one({"token": TOK(0)})["active"]
    keys = [x["key"] for x in c.get("/api/push/preferences", headers=A["stu"]).json()["categories"]]
    assert keys == ["homework", "notices", "timetable"]
    keys = [x["key"] for x in c.get("/api/push/preferences", headers=A["ct"]).json()["categories"]]
    assert keys == ["messages", "notices", "teacher_covers"]
    assert c.put("/api/push/preferences", headers=A["par"], json={"preferences": {"nope": True}}).status_code == 400
    r = c.put("/api/push/preferences", headers=A["par"], json={"preferences": {"fees": False, "nope": True}}).json()
    assert r["preferences"]["fees"] is False and r["preferences"]["messages"] is True
    c.put("/api/push/preferences", headers=A["par"], json={"preferences": {"fees": True}})


def test_test_push_self_only_logged_and_receipts(ctx):
    c, A, fake = ctx["c"], ctx["A"], ctx["fake"]
    assert c.post("/api/push/test", headers=A["ct"]).json()["devices"] == 0
    reg(ctx, "par", 1)
    reg(ctx, "ct", 2)
    n0 = len(fake.sent)
    r = c.post("/api/push/test", headers=A["par"]).json()
    ctx["drain"]()
    assert r["ok"] and r["devices"] == 1 and [m["to"] for m in fake.sent[n0:]] == [TOK(1)]  # caller's device only
    m = fake.sent[-1]
    assert m["channelId"] == "school" and m["title"] == "Test notification" and isinstance(m["badge"], int)
    doc = sdb.messages.find_one({"id": r["results"][0]["message_id"]}, {"_id": 0})
    assert doc["channel"] == "push" and doc["institution_id"] == ctx["iid"] and doc["recipient_user_id"] == ctx["U"]["par"]["id"]
    assert doc["status"] == "delivered" and [h["status"] for h in doc["status_history"]] == ["queued", "sent", "delivered"]  # receipt checked
    assert "token" not in doc["meta"] and doc["meta"]["token_tail"]


def test_retry_on_429_then_success(ctx):
    fake = ctx["fake"]
    fake.plan = [429, 503]
    r = ctx["c"].post("/api/push/test", headers=ctx["A"]["par"]).json()
    ctx["drain"]()
    assert r["ok"] and not fake.plan


def test_device_not_registered_deactivates(ctx):
    fake = ctx["fake"]
    reg(ctx, "par", 3)
    fake.bad.add(TOK(3))
    r = ctx["c"].post("/api/push/test", headers=ctx["A"]["par"]).json()
    ctx["drain"]()
    st = {x["status"] for x in r["results"]}
    assert st == {"sent", "failed"}
    t = sdb.push_tokens.find_one({"token": TOK(3)})
    assert t["active"] is False and t["deactivated_reason"] == "DeviceNotRegistered"
    # a receipt-level DeviceNotRegistered also deactivates
    reg(ctx, "par", 4)
    fake.receipt_err.add("tkt-" + TOK(4)[-14:-1])
    ctx["c"].post("/api/push/test", headers=ctx["A"]["par"])
    ctx["drain"]()
    assert sdb.push_tokens.find_one({"token": TOK(4)})["active"] is False


def test_chat_push_route_and_60s_collapse(ctx):
    c, A, fake, U = ctx["c"], ctx["A"], ctx["fake"], ctx["U"]
    n0 = len(fake.to(TOK(2)))
    r = c.post("/api/chat/threads", headers=A["par"], data={"student_id": ctx["st"]["id"], "body": "Hello teacher", "target": "class_teacher"})
    assert r.status_code == 200, r.text
    tid = r.json()["thread"]["id"]
    ctx["drain"]()
    got = fake.to(TOK(2))[n0:]
    assert len(got) == 1 and got[0]["data"]["route"] == f"/thread/{tid}" and got[0]["channelId"] == "messages"
    assert got[0]["data"]["category"] == "messages" and "student_id" not in got[0]["data"]  # staff: no child switch
    for i in range(2):
        assert c.post(f"/api/chat/threads/{tid}/messages", headers=A["par"], data={"body": f"follow-up {i}"}).status_code == 200
    ctx["drain"]()
    assert len(fake.to(TOK(2))[n0:]) == 1  # collapsed within 60s
    assert sdb.notifications.count_documents({"user_id": U["ct"]["id"], "type": "parent_message"}) == 3  # bell unchanged
    p0 = len(fake.to(TOK(1)))
    assert c.post(f"/api/chat/threads/{tid}/messages", headers=A["ct"], data={"body": "Hi! Noted."}).status_code == 200
    ctx["drain"]()
    pm = fake.to(TOK(1))[p0:]
    assert len(pm) == 1 and pm[0]["data"]["route"] == f"/thread/{tid}" and pm[0]["data"]["student_id"] == ctx["st"]["id"]


def test_event_mapping_prefs_and_roles(ctx):
    iid, U, fake = ctx["iid"], ctx["U"], ctx["fake"]
    reg(ctx, "stu", 5)
    reg(ctx, "admin", 6)
    hw = str(uuid.uuid4())
    sdb.homework.insert_one({"id": hw, "institution_id": iid, "class_name": "Grade 8", "section": "A", "title": "T", "subject": "Maths"})
    try:
        ctx["c"].put("/api/push/preferences", headers=ctx["A"]["stu"], json={"preferences": {"homework": False}})
        s0, p0 = len(fake.to(TOK(5))), len(fake.to(TOK(1)))
        for uid in (U["stu"]["id"], U["par"]["id"]):
            ctx["c"].portal.call(server._notify, iid, uid, "homework_new", "New homework: Maths", "Do it", hw)
        ctx["drain"]()
        assert len(fake.to(TOK(5))) == s0  # student switched homework off
        pm = fake.to(TOK(1))[p0:]
        assert len(pm) == 1 and pm[0]["data"] == {"type": "homework_new", "category": "homework", "route": "/more/homework", "student_id": ctx["st"]["id"]}
        ctx["c"].put("/api/push/preferences", headers=ctx["A"]["stu"], json={"preferences": {"homework": True}})
        ctx["c"].portal.call(server._notify, iid, U["stu"]["id"], "assignment_new", "New assignment", "x", hw)
        ctx["c"].portal.call(server._notify, iid, U["stu"]["id"], "notice_new", "New notice: Sports day", "y", "n1")
        ctx["c"].portal.call(server._notify, iid, U["stu"]["id"], "homework_verified", "Checked", "z", hw)  # unmapped → bell only
        ctx["c"].portal.call(server._notify, iid, U["admin"]["id"], "notice_new", "x", "y", "n1")  # admin has no mobile app
        ctx["drain"]()
        sm = fake.to(TOK(5))[s0:]
        assert [m["data"]["route"] for m in sm] == [f"/student/work/assignment/{hw}", "/more/notices"]
        assert not fake.to(TOK(6))
        f0 = len(fake.to(TOK(1)))
        ctx["c"].portal.call(server._notify, iid, U["par"]["id"], "fee_reminder", "Fee due: Kiran · Term 2", "Rs. 1,000.00 due on 2026-10-21", "inv-x")
        ctx["c"].portal.call(server._notify, iid, U["ct"]["id"], "sub_requested", "Substitution request", "Can you cover?", "sub-x")
        ctx["c"].portal.call(push.deliver, "other-school", U["par"]["id"], "notice_new", "x", "y", "n1")  # wrong institution
        ctx["drain"]()
        fm = fake.to(TOK(1))[f0:]
        assert len(fm) == 1 and fm[0]["channelId"] == "fees" and fm[0]["data"]["route"] == "/fees"
        tm = fake.to(TOK(2))[-1]
        assert tm["data"]["route"] == "/teacher/more/substitutions" and tm["channelId"] == "teacher"
    finally:
        sdb.homework.delete_one({"id": hw})


def test_section_cover_today_push_only(ctx):
    iid, fake = ctx["iid"], ctx["fake"]
    today = datetime.now(ZoneInfo("Asia/Kolkata")).date().isoformat()
    sub = {"id": "sub-" + TAG, "date": today, "class_name": "Grade 8", "section": "A", "period_no": 3, "subject": "English", "substitute_name": "Ms Sindhu"}
    s0, p0 = len(fake.to(TOK(5))), len(fake.to(TOK(1)))
    ctx["c"].portal.call(push._section_cover, iid, sub, "assigned")
    ctx["c"].portal.call(push._section_cover, iid, {**sub, "date": "2001-01-01"}, "assigned")  # not today → nothing
    ctx["drain"]()
    sm, pm = fake.to(TOK(5))[s0:], fake.to(TOK(1))[p0:]
    assert len(sm) == 1 and sm[0]["data"]["route"] == "/student/timetable" and "Ms Sindhu" in sm[0]["body"]
    assert len(pm) == 1 and pm[0]["data"]["route"] == "/timetable" and pm[0]["data"]["student_id"] == ctx["st"]["id"]
    assert sm[0]["data"]["category"] == "timetable" and sm[0]["channelId"] == "school"
    assert sdb.notifications.count_documents({"user_id": ctx["U"]["stu"]["id"], "type": "timetable_change"}) == 0  # push-only


def test_openapi_lists_push_endpoints(ctx):
    paths = ctx["c"].get("/api/openapi.json").json()["paths"]
    for p in ("/api/push/register", "/api/push/unregister", "/api/push/preferences", "/api/push/test", "/api/push/badge"):
        assert p in paths
    assert "put" in paths["/api/push/preferences"] and "get" in paths["/api/push/preferences"]
