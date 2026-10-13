"""Phase 50 — fees part C: defaulter list (calc, scoping, throttle, CSV), monthly summary (reconciles with the
Day Book), promotion dues badges + idempotent arrears carry-forward. Throwaway DB, STUB comm provider."""
import sys
import uuid
from datetime import datetime, timezone, timedelta
import pytest

sys.path.insert(0, "/app/backend")
import server  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from pymongo import MongoClient  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

TEST_DB = "lnmo_phase50_test"
PA_EMAIL = server.os.environ["PLATFORM_ADMIN_EMAIL"].lower()
PA_PW = server.os.environ["PLATFORM_ADMIN_PASSWORD"]
from zoneinfo import ZoneInfo  # noqa: E402
LOCAL = datetime.now(ZoneInfo("Asia/Kolkata")).date()  # Phase 51: dues, reminders AND day book use institution tz (IST)
TODAY = LOCAL
D = lambda n: (LOCAL + timedelta(days=n)).isoformat()  # noqa: E731
D45, D8, F20 = D(-45), D(-8), D(20)


class Sess:
    def __init__(self, c, tok):
        self._c, self._h = c, {"Authorization": f"Bearer {tok}"}

    def _call(self, m, p, **k):
        self._c.cookies.clear()
        return self._c.request(m, p, headers={**self._h, **k.pop("headers", {})}, **k)

    def get(self, p, **k): return self._call("get", p, **k)
    def post(self, p, **k): return self._call("post", p, **k)
    def put(self, p, **k): return self._call("put", p, **k)


def _user(mon, iid, email, role, **extra):
    uid = str(uuid.uuid4())
    mon.users.insert_one({"id": uid, "name": email.split("@")[0], "email": email, "password_hash": server.hash_password("Pass@123"),
                          "role": role, "institution_id": iid, "status": "active", "created_at": server.now_iso(), **extra})
    return uid


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
        A = platform.post("/api/res/institutions", json={"name": "Dues School", "slug": "p50a",
                          "admin_email": "a@p50.test", "admin_password": "Admin@123"}).json()["id"]
        B = platform.post("/api/res/institutions", json={"name": "Other School", "slug": "p50b",
                          "admin_email": "b@p50.test", "admin_password": "Admin@123"}).json()["id"]
        admin, admin_b = login("a@p50.test", "Admin@123"), login("b@p50.test", "Admin@123")
        mon.academic_units.insert_many([{"id": "uHS", "institution_id": A, "name": "HS"}, {"id": "uLP", "institution_id": A, "name": "LP"},
                                        {"id": "uB", "institution_id": B, "name": "HS"}])
        for g, u, i in [(5, "uLP", A), (8, "uHS", A), (9, "uHS", A), (8, "uB", B)]:
            mon.classes.insert_one({"id": str(uuid.uuid4()), "institution_id": i, "name": f"Grade {g}", "grade_level": str(g), "academic_unit_id": u})
        for i in (A, B):
            mon.academic_years.insert_one({"id": str(uuid.uuid4()), "institution_id": i, "name": "2026-27", "status": "active"})
        t8 = _user(mon, A, "t8@p50.test", "teacher")
        _user(mon, A, "tx@p50.test", "teacher")
        mon.sections.insert_many([{"id": str(uuid.uuid4()), "institution_id": A, "class_name": "Grade 8", "name": "A", "class_teacher_id": t8},
                                  {"id": str(uuid.uuid4()), "institution_id": A, "class_name": "Grade 8", "name": "B"},
                                  {"id": str(uuid.uuid4()), "institution_id": A, "class_name": "Grade 5", "name": "A"}])
        pr = _user(mon, A, "pr@p50.test", "teacher")
        mon.principal_assignments.insert_one({"id": str(uuid.uuid4()), "institution_id": A, "user_id": pr,
                                              "scope_type": "units", "unit_ids": ["uLP"], "designation": "principal"})
        sid = {}
        for k, g, sec, ph, iid in [("a", 8, "A", "9400000001", A), ("b", 8, "A", None, A), ("c", 5, "A", "9400000003", A),
                                   ("d", 8, "B", "9400000004", A), ("x", 8, "A", "9400000009", B)]:
            sid[k] = str(uuid.uuid4())
            doc = {"id": sid[k], "institution_id": iid, "first_name": k.upper(), "last_name": "D", "class_name": f"Grade {g}",
                   "section": sec, "enrollment_status": "enrolled", "admission_no": f"ADM-{k}", "guardian_name": f"Guardian {k}",
                   "created_at": server.now_iso()}
            if ph:
                doc["guardian_phone"] = ph
            mon.students.insert_one(doc)
            mon.enrollments.insert_one({"id": str(uuid.uuid4()), "institution_id": iid, "student_id": sid[k], "student_name": f"{k.upper()} D",
                                        "academic_year": "2026-27", "class_name": f"Grade {g}", "section": sec, "status": "active"})
        _user(mon, A, "pa@p50.test", "parent", student_ids=[sid["a"]])
        S = {}
        for who, sess, unit, cls, amt, periods in [
                ("hs", admin, "uHS", None, 1000, [{"label": "Term 1", "due_date": D45}, {"label": "Term 2", "due_date": F20}]),
                ("lp", admin, None, "Grade 5", 300, [{"label": "Term 1", "due_date": D8}]),
                ("b", admin_b, "uB", None, 700, [{"label": "Term 1", "due_date": D45}])]:
            body = {"name": who, "academic_year": "2026-27", "heads": [{"title": "Tuition", "amount": amt, "frequency": "term"}]}
            body.update({"academic_unit_id": unit} if unit else {"class_name": cls})
            S[who] = sess.post("/api/fees/structures", json=body).json()
            assert sess.post(f"/api/fees/structures/{S[who]['id']}/apply").json()["created"] >= 1
            if who == "hs":  # flat ₹200 concession for student a → consumed entirely by Term 1
                acc = mon.fee_accounts.find_one({"student_id": sid["a"]})
                assert admin.put(f"/api/fees/accounts/{acc['id']}", json={"discount": {"type": "flat", "value": 200}}).status_code == 200
            sess.post(f"/api/fees/structures/{S[who]['id']}/generate", json={"frequency": "term", "periods": periods})
        inv = lambda k, label="Term 1": mon.fee_invoices.find_one({"student_id": sid[k], "period_label": label})  # noqa: E731
        assert admin.post("/api/fees/payments", json={"invoice_id": inv("a")["id"], "amount": 300, "method": "cash"}).status_code == 200
        p = admin.post("/api/fees/payments", json={"invoice_id": inv("d")["id"], "amount": 100, "method": "upi"}).json()["payment"]
        assert admin.post(f"/api/fees/payments/{p['id']}/reverse", json={"reason": "Bounced"}).status_code == 200
        yield {"admin": admin, "admin_b": admin_b, "A": A, "db": mon, "sid": sid, "inv": inv, "t8": login("t8@p50.test"),
               "tx": login("tx@p50.test"), "pr": login("pr@p50.test"), "pa": login("pa@p50.test")}
    MongoClient(server.mongo_url).drop_database(TEST_DB)


def _rows(sess, **params):
    r = sess.get("/api/fees/defaulters", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def test_defaulter_calculations_reconcile(ctx):
    admin, sid = ctx["admin"], ctx["sid"]
    d = _rows(admin)
    by = {r["student_id"]: r for r in d["rows"]}
    assert set(by) == {sid["a"], sid["b"], sid["c"], sid["d"]}
    a = by[sid["a"]]  # Term1 1000 − 200 concession − 300 paid = 500 overdue; Term2 1000 not due yet
    assert (a["overdue_amount"], a["total_outstanding"], a["days_late"], a["bucket"], a["oldest_due_date"]) == (500, 1500, 45, "31-60", D45)
    assert (a["parent_name"], a["parent_phone"], a["admission_no"]) == ("Guardian a", "9400000001", "ADM-a")
    assert (by[sid["b"]]["overdue_amount"], by[sid["b"]]["total_outstanding"]) == (1000, 2000)
    assert (by[sid["d"]]["overdue_amount"], by[sid["d"]]["total_outstanding"]) == (1000, 2000)  # reversed payment excluded
    assert (by[sid["c"]]["overdue_amount"], by[sid["c"]]["bucket"], by[sid["c"]]["days_late"]) == (300, "1-30", 8)
    assert d["totals"] == {"students": 4, "overdue": 2800, "outstanding": 5800}
    assert d["buckets"] == {"1-30": 1, "31-60": 3, "60+": 0} and d["can_remind"] is True
    accs = admin.get("/api/fees/accounts").json()["accounts"]  # reconcile with student account balances
    bal = {}
    for acc in accs:
        bal[acc["student_id"]] = bal.get(acc["student_id"], 0) + acc["summary"]["balance"]
    assert all(abs(bal[k] - r["total_outstanding"]) < 0.01 for k, r in by.items())
    assert [r["student_id"] for r in _rows(admin, sort="amount")["rows"]][-1] == sid["c"]
    assert _rows(admin, sort="days_late")["rows"][-1]["student_id"] == sid["c"]
    assert [r["student_id"] for r in _rows(admin, bucket="1-30")["rows"]] == [sid["c"]]
    assert {r["student_id"] for r in _rows(admin, min_amount=600)["rows"]} == {sid["b"], sid["d"]}
    assert {r["student_id"] for r in _rows(admin, academic_unit_id="uLP")["rows"]} == {sid["c"]}
    assert {r["student_id"] for r in _rows(admin, class_name="Grade 8", section="B")["rows"]} == {sid["d"]}
    pg = _rows(admin, page_size=1, page=2)
    assert pg["total"] == 4 and len(pg["rows"]) == 1
    assert admin.get("/api/fees/defaulters", params={"bucket": "9-9"}).status_code == 400
    assert admin.get("/api/fees/defaulters", params={"sort": "x"}).status_code == 400


def test_scoping_and_csv(ctx):
    sid = ctx["sid"]
    assert {r["student_id"] for r in _rows(ctx["pr"])["rows"]} == {sid["c"]}
    t = _rows(ctx["t8"])
    assert {r["student_id"] for r in t["rows"]} == {sid["a"], sid["b"]} and t["can_remind"] is False and t["scope"] == "teacher"
    assert _rows(ctx["t8"], class_name="Grade 8", section="B")["rows"] == []
    assert ctx["tx"].get("/api/fees/defaulters").status_code == 403
    assert ctx["pa"].get("/api/fees/defaulters").status_code == 403
    assert ctx["t8"].post("/api/fees/defaulters/remind", json={"student_ids": [sid["a"]]}).status_code == 403
    assert ctx["t8"].get("/api/fees/monthly-summary").status_code == 403
    assert ctx["pa"].get("/api/fees/monthly-summary").status_code == 403
    xb = _rows(ctx["admin_b"])  # other tenant: only its own student
    assert [r["student_id"] for r in xb["rows"]] == [sid["x"]]
    assert ctx["admin_b"].post("/api/fees/defaulters/remind", json={"student_ids": [sid["a"]]}).json()["results"][0]["status"] == "not_found"
    assert ctx["pr"].post("/api/fees/defaulters/remind", json={"student_ids": [sid["a"]]}).json()["results"][0]["status"] == "out_of_scope"
    csv = ctx["admin"].get("/api/fees/defaulters/export.csv", params={"sort": "days_late"})
    assert csv.status_code == 200 and csv.headers["content-type"].startswith("text/csv")
    lines = csv.text.strip().splitlines()
    assert len(lines) == 5 and lines[0].startswith("Student,Admission no") and "500.00" in csv.text
    tcsv = ctx["t8"].get("/api/fees/defaulters/export.csv").text.strip().splitlines()
    assert len(tcsv) == 3
    assert len(ctx["admin"].get("/api/fees/defaulters/export.csv", params={"bucket": "1-30"}).text.strip().splitlines()) == 2


def test_reminder_throttle_shared_with_auto(ctx):
    admin, sid, db, A = ctx["admin"], ctx["sid"], ctx["db"], ctx["A"]
    auto = admin.post("/api/fees/reminders/run", json={"as_of": D(0)}).json()  # c is on its 8-day overdue_repeat
    assert [(r["student_name"], r["status"]) for r in auto["results"]] == [("C D", "sent")]
    r1 = admin.post("/api/fees/defaulters/remind", json={"student_ids": [sid["a"], sid["b"], sid["c"]]}).json()
    st = {x["student_id"]: x["status"] for x in r1["results"]}
    assert st == {sid["a"]: "sent", sid["b"]: "no_contact", sid["c"]: "skipped_throttled"}
    assert (r1["sent"], r1["no_contact"], r1["skipped_throttled"]) == (1, 1, 1)
    r2 = admin.post("/api/fees/defaulters/remind", json={"student_ids": [sid["a"], sid["b"]]}).json()
    assert {x["status"] for x in r2["results"]} == {"skipped_throttled"}
    a_inv2 = ctx["inv"]("a", "Term 2")  # a different invoice of the same student is throttled too
    assert admin.post(f"/api/fees/invoices/{a_inv2['id']}/remind").json()["status"] == "deduped"
    assert db.messages.count_documents({"institution_id": A, "module": "fee_reminder", "recipient_phone": "9400000001"}) == 1
    pr = ctx["pr"].post("/api/fees/defaulters/remind", json={"student_ids": [sid["c"]]}).json()
    assert pr["results"][0]["status"] == "skipped_throttled"
    rows = {r["student_id"]: r for r in _rows(admin)["rows"]}
    assert rows[sid["a"]]["last_reminder_at"] and rows[sid["a"]]["last_reminder_status"] == "sent"
    assert rows[sid["d"]]["last_reminder_at"] is None


def test_monthly_summary_reconciles_with_day_book(ctx):
    admin = ctx["admin"]
    m = D45[:7]
    s = admin.get("/api/fees/monthly-summary", params={"month": m}).json()
    g8 = next(r for r in s["rows"] if r["class_name"] == "Grade 8")
    assert (g8["invoices"], g8["gross"], g8["concession"], g8["billed"], g8["outstanding"]) == (3, 3000, 200, 2800, 2500)
    assert g8["collection_pct"] == round(300 / 2800 * 100, 1)
    cur = TODAY.isoformat()[:7]
    t = admin.get("/api/fees/monthly-summary", params={"month": cur}).json()
    y, mo = map(int, cur.split("-"))
    nxt = datetime(y + (mo == 12), mo % 12 + 1, 1).date()
    days = [(datetime(y, mo, 1).date() + timedelta(days=i)).isoformat() for i in range((nxt - datetime(y, mo, 1).date()).days)]
    book = sum(admin.get("/api/fees/day-book", params={"date": d}).json()["summary"]["total"] for d in days)
    assert t["totals"]["collected"] == book == 300
    assert t["totals"]["prev_dues_collected"] == 300  # paid today against a Term 1 invoice due last month(s)
    assert t["totals"]["prev_dues_collected"] == sum(r["prev_dues_collected"] for r in t["rows"])
    assert t["by_method"] == [{"key": "cash", "total": 300, "count": 1}] and t["reversed"] == {"count": 1, "amount": 100}
    assert sum(x["total"] for x in t["daily"]) == book
    assert t["totals"]["billed"] == sum(r["billed"] for r in t["rows"])
    p = ctx["pr"].get("/api/fees/monthly-summary", params={"month": m}).json()
    assert all(r["class_name"] == "Grade 5" for r in p["rows"])
    assert admin.get("/api/fees/monthly-summary", params={"month": "2026-13"}).status_code == 400


def test_promotion_dues_and_idempotent_carry_forward(ctx):
    admin, sid, db, A, inv = ctx["admin"], ctx["sid"], ctx["db"], ctx["A"], ctx["inv"]
    pv = admin.post("/api/promotion/preview", json={"from_year": "2026-27", "to_year": "2027-28"}).json()
    assert pv["dues"] == {sid["a"]: 1500, sid["b"]: 2000, sid["c"]: 300, sid["d"]: 2000}
    assert pv["dues_summary"] == {"students": 4, "total": 5800}
    run_id = pv["run"]["id"]
    assert admin.get(f"/api/promotion/{run_id}").json()["dues_summary"]["total"] == 5800
    assert ctx["pr"].get(f"/api/promotion/{run_id}").json()["dues"] == {sid["c"]: 300}
    src_a = [inv("a"), inv("a", "Term 2")]
    ex = admin.post(f"/api/promotion/{run_id}/execute").json()  # dues never block promotion
    assert ex["status"] == "executed" and ex["dues_carry_forward"]["created"] == 4 and ex["dues_carry_forward"]["amount"] == 5800
    arr = db.fee_invoices.find_one({"student_id": sid["a"], "is_arrears": True})
    assert arr["academic_year"] == "2027-28" and arr["total"] == 1500 and arr["class_name"] == "Grade 9"
    assert sorted(arr["source_invoice_ids"]) == sorted(i["id"] for i in src_a)
    assert sorted(x["amount"] for x in arr["items"]) == [500, 1000]
    for old in src_a:  # historical invoice untouched except the additive link
        now = db.fee_invoices.find_one({"id": old["id"]})
        assert now["carried_forward_to"] == arr["id"]
        assert (now["total"], now["paid_amount"]) == (old["total"], old["paid_amount"])
    assert db.audit_logs.count_documents({"action": "fee_dues_carry_forward"}) == 4
    again = admin.post("/api/fees/carry-forward", json={"run_id": run_id}).json()
    assert (again["created"], again["already_carried"]) == (0, 4)
    assert db.fee_invoices.count_documents({"institution_id": A, "is_arrears": True}) == 4
    d = {r["student_id"]: r for r in _rows(admin)["rows"]}  # no double counting after rollover
    assert d[sid["a"]]["total_outstanding"] == 1500 and d[sid["a"]]["class_name"] == "Grade 9"
    assert _rows(admin)["totals"]["outstanding"] == 5800
    assert admin.post("/api/fees/payments", json={"invoice_id": src_a[0]["id"], "amount": 10, "method": "cash"}).status_code == 409
    pay = admin.post("/api/fees/payments", json={"invoice_id": arr["id"], "amount": 500, "method": "upi"})
    assert pay.status_code == 200 and pay.json()["invoice"]["balance"] == 1000
    assert ctx["pa"].get(f"/api/parent/child/{sid['a']}/fees").json()["summary"]["balance"] == 1000
    ms = admin.get("/api/fees/monthly-summary", params={"month": TODAY.isoformat()[:7]}).json()["totals"]
    assert (ms["collected"], ms["prev_dues_collected"]) == (800, 800)  # arrears payment counts as previous dues
    assert ctx["t8"].post("/api/fees/carry-forward", json={"run_id": run_id}).status_code == 403


def test_throttle_day_boundary_uses_institution_timezone(ctx):
    admin, sid, db, A = ctx["admin"], ctx["sid"], ctx["db"], ctx["A"]
    remind = lambda k: admin.post("/api/fees/defaulters/remind", json={"student_ids": [sid[k]]}).json()["results"][0]["status"]  # noqa: E731
    local = lambda tz: datetime.now(ZoneInfo(tz)).date().isoformat()  # noqa: E731
    for tz in ("Etc/GMT+12", "Pacific/Kiritimati"):  # UTC−12 vs UTC+14: always different calendar days
        db.institutions.update_one({"id": A}, {"$set": {"timezone": tz}})
        assert remind("d") == "sent"
        assert db.reminders_sent.find_one({"key": f"fee:stu:{sid['d']}:{local(tz)}"})
    assert remind("d") == "skipped_throttled"
    run = admin.post("/api/fees/reminders/run", json={}).json()  # auto path defaults to the school's local date
    assert run["as_of"] == local("Pacific/Kiritimati")
    for tz in (None, "Mars/Base"):  # unset / invalid → Asia/Kolkata; b was reminded earlier on the IST day
        db.institutions.update_one({"id": A}, {"$set": {"timezone": tz}})
        assert remind("b") == "skipped_throttled"
        assert admin.post("/api/fees/reminders/run", json={}).json()["as_of"] == local("Asia/Kolkata")
    db.institutions.update_one({"id": A}, {"$unset": {"timezone": ""}})


def test_openapi_lists_endpoints(ctx):
    paths = ctx["admin"].get("/api/openapi.json").json()["paths"]
    for p in ("/api/fees/defaulters", "/api/fees/defaulters/remind", "/api/fees/defaulters/export.csv",
              "/api/fees/monthly-summary", "/api/fees/carry-forward"):
        assert p in paths


def test_inr_format_and_receipt_pdf_font():
    assert [server._inr(n) for n in (0, 999, 1000, 123456, 1234567.5, 10000000, -1500)] == [
        "₹0.00", "₹999.00", "₹1,000.00", "₹1,23,456.00", "₹12,34,567.50", "₹1,00,00,000.00", "−₹1,500.00"]
    reg, bold, _, money = server._receipt_fonts()
    assert (reg, bold) == ("FeeSans", "FeeSans-Bold") and money(4500) == "₹4,500.00"
    d = {"payment": {"receipt_no": "R-1", "student_name": "S", "method": "cash", "amount": 4500, "collected_at": "2026-10-13T06:00"},
         "invoice": {"items": [{"title": "Tuition", "amount": 6000}], "discount_amount": 1500, "amount_due": 4500, "balance": 0},
         "school": {"name": "X"}}
    assert server._receipt_pdf(d)[:4] == b"%PDF"
