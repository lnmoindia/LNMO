"""Phase 48 — Fees core. Throwaway DB.
structure→accounts (optional toggle); invoices per frequency + idempotency; discount math (flat+%);
partial payment status; receipt numbering sequential + per-year reset; fine after grace; reversal audit;
parent/student own-only views; unit-principal read scope; teacher/student 403 on money endpoints.
"""
import sys
import uuid
from datetime import date, timedelta
import pytest

sys.path.insert(0, "/app/backend")
import server  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from pymongo import MongoClient  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

TEST_DB = "lnmo_phase48_test"
PA_EMAIL = server.os.environ["PLATFORM_ADMIN_EMAIL"].lower()
PA_PW = server.os.environ["PLATFORM_ADMIN_PASSWORD"]
D = lambda n: (date.today() + timedelta(days=n)).isoformat()  # noqa: E731


class Sess:
    def __init__(self, c, tok):
        self._c, self._h = c, {"Authorization": f"Bearer {tok}"}

    def _call(self, m, p, **k):
        self._c.cookies.clear()
        return self._c.request(m, p, headers={**self._h, **k.pop("headers", {})}, **k)

    def get(self, p, **k): return self._call("get", p, **k)
    def post(self, p, **k): return self._call("post", p, **k)
    def put(self, p, **k): return self._call("put", p, **k)


def _user(mon, A, email, role, **extra):
    uid = str(uuid.uuid4())
    mon.users.insert_one({"id": uid, "name": email.split("@")[0], "email": email, "password_hash": server.hash_password("Pass@123"),
                          "role": role, "institution_id": A, "status": "active", "must_change_password": False,
                          "created_at": server.now_iso(), **extra})
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
        A = platform.post("/api/res/institutions", json={"name": "Fee School", "slug": "p48",
                          "admin_email": "a@p48.test", "admin_password": "Admin@123"}).json()["id"]
        mon.institutions.update_one({"id": A}, {"$set": {"code": "TFS"}})
        for yn, ys in (("2026-27", "active"), ("2027-28", "upcoming")):  # Phase 53: structures need a real year
            mon.academic_years.insert_one({"id": str(uuid.uuid4()), "institution_id": A, "name": yn, "status": ys})
        admin = login("a@p48.test", "Admin@123")
        mon.academic_units.insert_many([{"id": "uHS", "institution_id": A, "name": "HS"}, {"id": "uLP", "institution_id": A, "name": "LP"}])
        for g, u in [(5, "uLP"), (8, "uHS"), (9, "uHS")]:
            mon.classes.insert_one({"id": f"c{g}", "institution_id": A, "name": f"Grade {g}", "grade_level": str(g), "academic_unit_id": u})
        sid = {}
        for k, g in [("s1", 8), ("s2", 8), ("s3", 8), ("s4", 5), ("s5", 9)]:
            sid[k] = str(uuid.uuid4())
            mon.students.insert_one({"id": sid[k], "institution_id": A, "first_name": k.upper(), "last_name": "F", "class_name": f"Grade {g}",
                                     "section": "A", "enrollment_status": "enrolled", "admission_no": f"TFS-{k}", "created_at": server.now_iso()})
        ptid = _user(mon, A, "pr@p48.test", "teacher")
        mon.principal_assignments.insert_one({"id": str(uuid.uuid4()), "institution_id": A, "user_id": ptid,
                                              "scope_type": "units", "unit_ids": ["uLP"], "designation": "principal"})
        _user(mon, A, "t@p48.test", "teacher")
        _user(mon, A, "st@p48.test", "student", student_id=sid["s1"])
        _user(mon, A, "p1@p48.test", "parent", student_ids=[sid["s1"]])
        _user(mon, A, "p2@p48.test", "parent", student_ids=[sid["s4"]])
        S = {k: login(f"{k}@p48.test") for k in ("pr", "t", "st", "p1", "p2")}
        yield {"C": C, "admin": admin, "A": A, "db": mon, "sid": sid, **S}
    MongoClient(server.mongo_url).drop_database(TEST_DB)


HS = {"name": "HS Fees", "academic_year": "2026-27", "academic_unit_id": "uHS",
      "heads": [{"title": "Tuition", "amount": 12000, "frequency": "annual"},
                {"title": "Bus", "amount": 6000, "frequency": "annual", "optional": True},
                {"title": "Exam", "amount": 500, "frequency": "term"}],
      "late_fee": {"enabled": True, "type": "flat", "value": 100, "grace_days": 10}}


def _acc(ctx, key):
    return ctx["db"].fee_accounts.find_one({"student_id": ctx["sid"][key]})


def test_structure_validation_apply_and_toggle(ctx):
    admin = ctx["admin"]
    assert admin.post("/api/fees/structures", json={**HS, "class_name": "Grade 8"}).status_code == 400
    dup = {**HS, "heads": HS["heads"] + [{"title": "tuition ", "amount": 1, "frequency": "annual"}]}
    assert admin.post("/api/fees/structures", json=dup).status_code == 400
    r = admin.post("/api/fees/structures", json=HS)
    assert r.status_code == 200, r.text
    st = r.json()
    ctx["struct"] = st
    bus = next(h["id"] for h in st["heads"] if h["title"] == "Bus")
    ctx["bus"] = bus
    ap = admin.post(f"/api/fees/structures/{st['id']}/apply").json()
    assert ap["created"] == 4  # Grade 8 ×3 + Grade 9 ×1 (unit HS)
    assert admin.post(f"/api/fees/structures/{st['id']}/apply").json()["created"] == 0
    assert _acc(ctx, "s1")["included_head_ids"] == [bus]  # optional heads default ON
    a2 = _acc(ctx, "s2")["id"]
    assert admin.put(f"/api/fees/accounts/{a2}", json={"included_head_ids": []}).status_code == 200
    tuition = next(h["id"] for h in st["heads"] if h["title"] == "Tuition")
    assert admin.put(f"/api/fees/accounts/{a2}", json={"included_head_ids": [tuition]}).status_code == 400
    assert admin.put(f"/api/fees/accounts/{_acc(ctx, 's3')['id']}", json={"discount": {"type": "percent", "value": 10, "reason": "sibling"}}).status_code == 200
    assert admin.put(f"/api/fees/accounts/{_acc(ctx, 's1')['id']}", json={"discount": {"type": "flat", "value": 1000}}).status_code == 200
    assert admin.put(f"/api/fees/accounts/{_acc(ctx, 's1')['id']}", json={"discount": {"type": "percent", "value": 150}}).status_code == 400


def test_generate_frequencies_idempotent_discounts(ctx):
    admin, db, st = ctx["admin"], ctx["db"], ctx["struct"]
    url = f"/api/fees/structures/{st['id']}/generate"
    assert admin.post(url, json={"frequency": "annual", "periods": [{"label": "A", "due_date": D(30)}, {"label": "B", "due_date": D(40)}]}).status_code == 400
    assert admin.post(url, json={"frequency": "monthly", "periods": [{"label": "Jan", "due_date": D(30)}]}).status_code == 400
    r = admin.post(url, json={"frequency": "annual", "periods": [{"label": "Annual 2026-27", "due_date": D(30)}]}).json()
    assert r["created"] == 4
    tot = lambda k: db.fee_invoices.find_one({"student_id": ctx["sid"][k], "frequency": "annual"})["total"]  # noqa: E731
    assert (tot("s1"), tot("s2"), tot("s3"), tot("s5")) == (17000, 12000, 16200, 18000)
    terms = [{"label": f"Term {i}", "due_date": D(30 + 60 * i)} for i in (1, 2, 3)]
    assert admin.post(url, json={"frequency": "term", "periods": terms}).json()["created"] == 12
    again = admin.post(url, json={"frequency": "term", "periods": terms}).json()
    assert again == {"created": 0, "skipped_existing": 12}
    t = lambda k: [i["total"] for i in db.fee_invoices.find({"student_id": ctx["sid"][k], "frequency": "term"})]  # noqa: E731
    assert t("s1") == [500, 500, 500]  # flat discount fully consumed by the annual invoice
    assert t("s3") == [450, 450, 450]  # percent applies to every invoice
    assert db.fee_accounts.find_one({"student_id": ctx["sid"]["s1"]})["discount_used"] == 1000
    # edit blocked after invoices; clone allowed & editable
    assert admin.put(f"/api/fees/structures/{st['id']}", json=HS).status_code == 409
    cl = admin.post(f"/api/fees/structures/{st['id']}/clone").json()
    assert cl["id"] != st["id"] and admin.put(f"/api/fees/structures/{cl['id']}", json={**HS, "name": "HS v2"}).status_code == 200


def test_partial_payment_receipts_and_year_reset(ctx):
    admin, db = ctx["admin"], ctx["db"]
    inv = db.fee_invoices.find_one({"student_id": ctx["sid"]["s2"], "frequency": "annual"})
    r1 = admin.post("/api/fees/payments", json={"invoice_id": inv["id"], "amount": 5000, "method": "upi", "reference": "UPI123"})
    assert r1.status_code == 200, r1.text
    assert r1.json()["invoice"]["status"] == "partial" and r1.json()["invoice"]["balance"] == 7000
    assert r1.json()["payment"]["receipt_no"] == "TFS-2026-000001"
    assert admin.post("/api/fees/payments", json={"invoice_id": inv["id"], "amount": 7000.01, "method": "cash"}).status_code == 400
    r2 = admin.post("/api/fees/payments", json={"invoice_id": inv["id"], "amount": 7000, "method": "cash"}).json()
    assert r2["invoice"]["status"] == "paid" and r2["payment"]["receipt_no"] == "TFS-2026-000002"
    assert admin.post("/api/fees/payments", json={"invoice_id": inv["id"], "amount": 1, "method": "cash"}).status_code == 400
    assert admin.post("/api/fees/payments", json={"invoice_id": inv["id"], "amount": -5, "method": "cash"}).status_code == 422
    ctx["pay1"] = r1.json()["payment"]["id"]
    # new academic year → numbering resets
    st2 = admin.post("/api/fees/structures", json={**HS, "name": "G9 next", "academic_unit_id": None, "class_name": "Grade 9",
                                                   "academic_year": "2027-28"}).json()
    db.fee_accounts.update_many({"student_id": ctx["sid"]["s5"], "structure_id": ctx["struct"]["id"]}, {"$set": {"status": "closed"}})
    assert admin.post(f"/api/fees/structures/{st2['id']}/apply").json()["created"] == 1
    admin.post(f"/api/fees/structures/{st2['id']}/generate", json={"frequency": "annual", "periods": [{"label": "Annual 2027-28", "due_date": D(300)}]})
    inv9 = db.fee_invoices.find_one({"structure_id": st2["id"]})
    r9 = admin.post("/api/fees/payments", json={"invoice_id": inv9["id"], "amount": 100, "method": "bank"}).json()
    assert r9["payment"]["receipt_no"] == "TFS-2027-000001"
    r3 = admin.post("/api/fees/payments", json={"invoice_id": db.fee_invoices.find_one({"student_id": ctx["sid"]["s3"], "frequency": "annual"})["id"],
                                                "amount": 50, "method": "cash"}).json()
    assert r3["payment"]["receipt_no"] == "TFS-2026-000003"


def test_late_fine_after_grace(ctx):
    admin, db = ctx["admin"], ctx["db"]
    late = db.fee_invoices.find_one({"student_id": ctx["sid"]["s1"], "period_label": "Term 1"})
    within = db.fee_invoices.find_one({"student_id": ctx["sid"]["s1"], "period_label": "Term 2"})
    db.fee_invoices.update_one({"id": late["id"]}, {"$set": {"due_date": D(-20)}})
    db.fee_invoices.update_one({"id": within["id"]}, {"$set": {"due_date": D(-5)}})
    led = admin.get(f"/api/fees/accounts/{late['account_id']}").json()
    v = {i["period_label"]: i for i in led["invoices"]}
    assert v["Term 1"]["status"] == "overdue" and v["Term 1"]["fine_projected"] == 100 and v["Term 1"]["amount_due"] == 600
    assert v["Term 2"]["status"] == "overdue" and v["Term 2"]["fine_amount"] == 0  # within grace
    assert admin.post("/api/fees/payments", json={"invoice_id": late["id"], "amount": 550, "method": "cash"}).status_code == 200
    doc = db.fee_invoices.find_one({"id": late["id"]})
    assert doc["fine_applied"] is True and doc["fine_amount"] == 100
    r = admin.post("/api/fees/payments", json={"invoice_id": late["id"], "amount": 50, "method": "cash"}).json()
    assert r["invoice"]["status"] == "paid" and r["invoice"]["amount_due"] == 600  # fine applied exactly once
    ctx["s1_pay"] = r["payment"]["id"]


def test_reversal_keeps_trail(ctx):
    admin, db = ctx["admin"], ctx["db"]
    n = db.fee_payments.count_documents({})
    assert admin.post(f"/api/fees/payments/{ctx['pay1']}/reverse", json={"reason": "ab"}).status_code == 422
    r = admin.post(f"/api/fees/payments/{ctx['pay1']}/reverse", json={"reason": "Wrong student"})
    assert r.status_code == 200 and r.json()["invoice"]["status"] == "partial" and r.json()["invoice"]["balance"] == 5000
    p = db.fee_payments.find_one({"id": ctx["pay1"]})
    assert p["reversed"] and p["credit_note_no"] == "CN-TFS-2026-000001" and p["reverse_reason"] == "Wrong student"
    assert db.fee_payments.count_documents({}) == n
    assert admin.post(f"/api/fees/payments/{ctx['pay1']}/reverse", json={"reason": "again!"}).status_code == 400
    acts = {a["action"] for a in db.audit_logs.find({"institution_id": ctx["A"]})}
    assert {"fee_payment", "fee_payment_reverse", "fee_structure_create", "fee_invoices_generate"} <= acts


def test_parent_and_student_views(ctx):
    p1, p2, st, sid = ctx["p1"], ctx["p2"], ctx["st"], ctx["sid"]
    v = p1.get(f"/api/parent/child/{sid['s1']}/fees").json()
    assert v["summary"]["invoices"] == 4 and v["summary"]["paid"] == 600
    assert v["summary"]["balance"] == v["summary"]["total"] - v["summary"]["paid"]
    assert p1.get(f"/api/parent/child/{sid['s4']}/fees").status_code == 403
    assert st.get("/api/portal/fees").json()["summary"] == v["summary"]
    assert p1.get(f"/api/fees/payments/{ctx['s1_pay']}/receipt").status_code == 200
    assert st.get(f"/api/fees/payments/{ctx['s1_pay']}/receipt").status_code == 200
    assert p2.get(f"/api/fees/payments/{ctx['s1_pay']}/receipt").status_code == 403
    rc = ctx["admin"].get(f"/api/fees/payments/{ctx['s1_pay']}/receipt").json()
    assert rc["payment"]["receipt_no"].startswith("TFS-2026-") and rc["school"]["name"] == "Fee School"


def test_scope_and_role_guards(ctx):
    pr, t, st, admin, sid = ctx["pr"], ctx["t"], ctx["st"], ctx["admin"], ctx["sid"]
    assert pr.get("/api/fees/structures").json()["structures"] == []
    assert pr.get("/api/fees/accounts").json()["accounts"] == []
    assert pr.get(f"/api/fees/accounts/{_acc(ctx, 's1')['id']}").status_code == 403
    assert pr.get("/api/fees/payments").json()["payments"] == []
    assert pr.get(f"/api/fees/payments/{ctx['s1_pay']}/receipt").status_code == 403
    inv = ctx["db"].fee_invoices.find_one({"student_id": sid["s3"], "frequency": "term"})
    assert pr.post("/api/fees/payments", json={"invoice_id": inv["id"], "amount": 1, "method": "cash"}).status_code == 403
    assert pr.post("/api/fees/structures", json=HS).status_code == 403
    for s in (t, st):
        assert s.get("/api/fees/structures").status_code == 403
        assert s.get("/api/fees/accounts").status_code == 403
        assert s.post("/api/fees/payments", json={"invoice_id": inv["id"], "amount": 1, "method": "cash"}).status_code == 403
    assert t.get(f"/api/fees/payments/{ctx['s1_pay']}/receipt").status_code == 403
    # LP structure becomes visible to the LP principal
    lp = admin.post("/api/fees/structures", json={**HS, "name": "LP", "academic_unit_id": "uLP"}).json()
    admin.post(f"/api/fees/structures/{lp['id']}/apply")
    assert [s["name"] for s in pr.get("/api/fees/structures").json()["structures"]] == ["LP"]
    assert [a["student_id"] for a in pr.get("/api/fees/accounts").json()["accounts"]] == [sid["s4"]]
