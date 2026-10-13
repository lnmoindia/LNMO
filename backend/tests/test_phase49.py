"""Phase 49 — fee reminders (cadence + dedupe + quota + no-phone), day book math, receipt PDF auth.
Throwaway DB, STUB comm provider.
"""
import sys
import uuid
from datetime import date, datetime, timedelta
import pytest

sys.path.insert(0, "/app/backend")
import server  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from pymongo import MongoClient  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

TEST_DB = "lnmo_phase49_test"
PA_EMAIL = server.os.environ["PLATFORM_ADMIN_EMAIL"].lower()
PA_PW = server.os.environ["PLATFORM_ADMIN_PASSWORD"]
DUE = "2027-02-10"
OFF = lambda n: (date.fromisoformat(DUE) + timedelta(days=n)).isoformat()  # noqa: E731
CFG = dict(server.FEE_REMINDER_DEFAULTS)


class Sess:
    def __init__(self, c, tok):
        self._c, self._h = c, {"Authorization": f"Bearer {tok}"}

    def _call(self, m, p, **k):
        self._c.cookies.clear()
        return self._c.request(m, p, headers={**self._h, **k.pop("headers", {})}, **k)

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
    with TestClient(server.app, base_url="https://testserver") as C:
        def login(email, pw="Pass@123"):
            r = C.post("/api/auth/login", json={"email": email, "password": pw})
            assert r.status_code == 200, r.text
            tok = r.cookies.get("access_token"); C.cookies.clear()
            return Sess(C, tok)
        platform = login(PA_EMAIL, PA_PW)
        A = platform.post("/api/res/institutions", json={"name": "Remind School", "slug": "p49",
                          "admin_email": "a@p49.test", "admin_password": "Admin@123"}).json()["id"]
        mon.institutions.update_one({"id": A}, {"$set": {"code": "RMS"}})
        mon.academic_years.insert_one({"id": str(uuid.uuid4()), "institution_id": A, "name": "2026-27", "status": "active"})  # Phase 53: structures need a real year
        admin = login("a@p49.test", "Admin@123")
        mon.academic_units.insert_many([{"id": "uHS", "institution_id": A, "name": "HS"}, {"id": "uLP", "institution_id": A, "name": "LP"}])
        for g, u in [(5, "uLP"), (8, "uHS")]:
            mon.classes.insert_one({"id": f"c{g}", "institution_id": A, "name": f"Grade {g}", "grade_level": str(g), "academic_unit_id": u})
        sid = {}
        for k, g, ph in [("a", 8, "9400000001"), ("b", 8, None), ("c", 5, "9400000003")]:
            sid[k] = str(uuid.uuid4())
            doc = {"id": sid[k], "institution_id": A, "first_name": k.upper(), "last_name": "R", "class_name": f"Grade {g}",
                   "section": "A", "enrollment_status": "enrolled", "admission_no": f"RMS-{k}", "created_at": server.now_iso()}
            if ph:
                doc["guardian_phone"] = ph
            mon.students.insert_one(doc)
        pid = {}
        for k in ("a", "b", "c"):
            pid[k] = str(uuid.uuid4())
            mon.users.insert_one({"id": pid[k], "name": f"P{k}", "email": f"p{k}@p49.test", "password_hash": server.hash_password("Pass@123"),
                                  "role": "parent", "institution_id": A, "status": "active", "student_ids": [sid[k]], "created_at": server.now_iso()})
        ptid = str(uuid.uuid4())
        mon.users.insert_one({"id": ptid, "name": "PR", "email": "pr@p49.test", "password_hash": server.hash_password("Pass@123"),
                              "role": "teacher", "institution_id": A, "status": "active", "created_at": server.now_iso()})
        mon.principal_assignments.insert_one({"id": str(uuid.uuid4()), "institution_id": A, "user_id": ptid,
                                              "scope_type": "units", "unit_ids": ["uLP"], "designation": "principal"})
        S = {k: login(f"p{k}@p49.test") for k in ("a", "b")}
        st = admin.post("/api/fees/structures", json={"name": "S", "academic_year": "2026-27", "academic_unit_id": "uHS",
                        "heads": [{"title": "Exam", "amount": 500, "frequency": "term"}]}).json()
        st5 = admin.post("/api/fees/structures", json={"name": "S5", "academic_year": "2026-27", "class_name": "Grade 5",
                         "heads": [{"title": "Exam", "amount": 300, "frequency": "term"}]}).json()
        for s in (st, st5):
            admin.post(f"/api/fees/structures/{s['id']}/apply")
            admin.post(f"/api/fees/structures/{s['id']}/generate", json={"frequency": "term", "periods": [{"label": "Term 1", "due_date": DUE}]})
        yield {"C": C, "admin": admin, "A": A, "db": mon, "sid": sid, "pid": pid, "pr": login("pr@p49.test"), **{f"p{k}": v for k, v in S.items()}}
    MongoClient(server.mongo_url).drop_database(TEST_DB)


def test_cadence_rules():
    t = server._fee_reminder_type
    assert t(DUE, OFF(-3), CFG) == "before_due"
    assert [t(DUE, OFF(n), CFG) for n in (-4, -2, -1, 0)] == [None, None, None, None]
    assert t(DUE, OFF(1), CFG) == "overdue"
    assert [t(DUE, OFF(n), CFG) for n in (2, 5, 7)] == [None, None, None]
    assert t(DUE, OFF(8), CFG) == "overdue_repeat" and t(DUE, OFF(15), CFG) == "overdue_repeat"
    assert t(DUE, OFF(-5), {**CFG, "before_days": 5}) == "before_due"


def test_auto_sweep_send_dedupe_and_no_phone(ctx):
    admin, db, A, sid, pid = ctx["admin"], ctx["db"], ctx["A"], ctx["sid"], ctx["pid"]
    q0 = (db.institutions.find_one({"id": A}).get("comm") or {}).get("quota", {}).get("whatsapp", {}).get("used", 0)
    r = admin.post("/api/fees/reminders/run", json={"as_of": OFF(-3)}).json()
    st = {x["student_name"].split()[0]: x["status"] for x in r["results"]}
    assert st == {"A": "sent", "B": "bell_only_no_phone", "C": "sent"} and r["sent"] == 2
    msgs = list(db.messages.find({"institution_id": A, "module": "fee_reminder"}))
    assert {m["recipient_phone"] for m in msgs} == {"9400000001", "9400000003"}
    assert all("/fees/invoice/" in m["body"] and DUE in m["body"] for m in msgs)
    assert db.institutions.find_one({"id": A})["comm"]["quota"]["whatsapp"]["used"] == q0 + 2
    for k in ("a", "b", "c"):  # bell for every linked parent, phone or not
        assert db.notifications.count_documents({"user_id": pid[k], "type": "fee_reminder"}) == 1
    # same day again → deduped, nothing new
    r2 = admin.post("/api/fees/reminders/run", json={"as_of": OFF(-3)}).json()
    assert {x["status"] for x in r2["results"]} == {"deduped"}
    assert db.messages.count_documents({"institution_id": A, "module": "fee_reminder"}) == 2
    # no rule day → nothing; overdue day → sent again; weekly repeat
    assert admin.post("/api/fees/reminders/run", json={"as_of": OFF(-1)}).json()["results"] == []
    assert {x["type"] for x in admin.post("/api/fees/reminders/run", json={"as_of": OFF(1)}).json()["results"]} == {"overdue"}
    assert {x["type"] for x in admin.post("/api/fees/reminders/run", json={"as_of": OFF(8)}).json()["results"]} == {"overdue_repeat"}
    assert db.messages.count_documents({"institution_id": A, "module": "fee_reminder"}) == 6
    # disabled school → silent
    assert admin.put("/api/fees/reminder-settings", json={**CFG, "enabled": False}).status_code == 200
    assert admin.post("/api/fees/reminders/run", json={"as_of": OFF(15)}).json()["results"] == []
    admin.put("/api/fees/reminder-settings", json=CFG)
    assert admin.post("/api/fees/reminders/run", json={"as_of": "bad"}).status_code == 400


def test_manual_reminders_quota_dedupe(ctx):
    admin, db, A, sid = ctx["admin"], ctx["db"], ctx["A"], ctx["sid"]
    inv_a = db.fee_invoices.find_one({"student_id": sid["a"]})
    q0 = db.institutions.find_one({"id": A})["comm"]["quota"]["whatsapp"]["used"]
    r = admin.post(f"/api/fees/invoices/{inv_a['id']}/remind").json()
    assert r["status"] == "sent"
    assert db.institutions.find_one({"id": A})["comm"]["quota"]["whatsapp"]["used"] == q0 + 1
    assert admin.post(f"/api/fees/invoices/{inv_a['id']}/remind").json()["status"] == "deduped"
    cls = admin.post("/api/fees/reminders/class", json={"class_name": "Grade 8"}).json()
    assert (cls["sent"], cls["deduped"], cls["bell_only_no_phone"]) == (0, 1, 1)
    assert db.institutions.find_one({"id": A})["comm"]["quota"]["whatsapp"]["used"] == q0 + 1
    assert ctx["pr"].post(f"/api/fees/invoices/{inv_a['id']}/remind").status_code == 403
    assert ctx["pa"].post("/api/fees/reminders/class", json={"class_name": "Grade 8"}).status_code == 403
    # reminder link resolves to child + invoice only
    tok = server._make_secure_link(A, "feeinv:" + inv_a["id"], 24)
    ctx["C"].cookies.clear()
    res = ctx["C"].get(f"/api/public/fee-link/{tok}").json()
    assert res == {"student_id": sid["a"], "invoice_id": inv_a["id"]}
    assert ctx["C"].get(f"/api/public/fee-link/{tok[:-3]}abc").status_code == 400


def test_day_book_grouping(ctx):
    admin, db, sid, pr = ctx["admin"], ctx["db"], ctx["sid"], ctx["pr"]
    ia = db.fee_invoices.find_one({"student_id": sid["a"]})
    ib = db.fee_invoices.find_one({"student_id": sid["b"]})
    ic = db.fee_invoices.find_one({"student_id": sid["c"]})
    pays = [admin.post("/api/fees/payments", json={"invoice_id": i["id"], "amount": a, "method": m}).json()["payment"]
            for i, a, m in [(ia, 200, "cash"), (ia, 100, "upi"), (ib, 150, "upi"), (ic, 300, "cheque")]]
    admin.post(f"/api/fees/payments/{pays[0]['id']}/reverse", json={"reason": "Wrong amount"})
    db.fee_payments.update_one({"id": pays[3]["id"]}, {"$set": {"collected_by": "Clerk Two"}})
    from zoneinfo import ZoneInfo
    today = datetime.now(ZoneInfo("Asia/Kolkata")).date().isoformat()  # Phase 51: day book = institution tz (IST)
    d = admin.get("/api/fees/day-book", params={"date": today}).json()
    assert d["summary"] == {"total": 550, "count": 3, "reversed_count": 1, "reversed_amount": 200}
    assert {m["key"]: (m["total"], m["count"]) for m in d["by_method"]} == {"upi": (250, 2), "cheque": (300, 1)}
    coll = {c["key"]: c["total"] for c in d["by_collector"]}
    assert coll["Clerk Two"] == 300 and sum(coll.values()) == 550
    assert [(c["key"], c["total"]) for c in d["by_class"]] == [("Grade 5", 300), ("Grade 8", 250)]
    assert [p["receipt_no"] for p in d["reversed"]] == [pays[0]["receipt_no"]]
    assert admin.get("/api/fees/day-book", params={"date": "2001-01-01"}).json()["summary"]["count"] == 0
    assert admin.get("/api/fees/day-book", params={"date": "12-12"}).status_code == 400
    sc = pr.get("/api/fees/day-book", params={"date": today}).json()
    assert sc["summary"]["total"] == 300 and [c["key"] for c in sc["by_class"]] == ["Grade 5"]
    ctx["pay_a"] = pays[1]["id"]


def test_receipt_pdf_and_auth(ctx):
    admin, pa, pb = ctx["admin"], ctx["pa"], ctx["pb"]
    r = pa.get(f"/api/fees/payments/{ctx['pay_a']}/receipt.pdf")
    assert r.status_code == 200 and r.content[:4] == b"%PDF" and r.headers["content-type"] == "application/pdf"
    assert "attachment" in r.headers["content-disposition"] and "RMS-2026-" in r.headers["content-disposition"]
    assert admin.get(f"/api/fees/payments/{ctx['pay_a']}/receipt.pdf").content[:4] == b"%PDF"
    assert pb.get(f"/api/fees/payments/{ctx['pay_a']}/receipt.pdf").status_code == 403
    assert ctx["pr"].get(f"/api/fees/payments/{ctx['pay_a']}/receipt.pdf").status_code == 403


def test_amount_in_words():
    w = server._amount_in_words
    assert w(5000) == "Rupees Five Thousand Only"
    assert w(19500) == "Rupees Nineteen Thousand Five Hundred Only"
    assert w(125000.5) == "Rupees One Lakh Twenty Five Thousand and Fifty Paise Only"
    assert w(10000001) == "Rupees One Crore One Only"
