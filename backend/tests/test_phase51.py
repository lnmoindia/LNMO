"""Phase 51 — UPI QR (decoded), parent payment proofs (object storage), approve/reject via the shared payment path,
fee issue threads, backdated payment dates (institution tz), principal collection scope, statement PDF.
Throwaway DB; object storage monkeypatched in-memory; comm engine in STUB mode."""
import base64
import io
import sys
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import pytest

sys.path.insert(0, "/app/backend")
import server  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from pymongo import MongoClient  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image  # noqa: E402

TEST_DB = "lnmo_phase51_test"
PA_EMAIL = server.os.environ["PLATFORM_ADMIN_EMAIL"].lower()
PA_PW = server.os.environ["PLATFORM_ADMIN_PASSWORD"]
LOCAL = datetime.now(ZoneInfo("Asia/Kolkata")).date()
D = lambda n: (LOCAL + timedelta(days=n)).isoformat()  # noqa: E731
FAKE = {}


def _png():
    b = io.BytesIO()
    Image.new("RGB", (40, 40), (20, 120, 60)).save(b, "PNG")
    return b.getvalue()


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
    mon.users.insert_one({"id": uid, "name": email.split("@")[0].upper(), "email": email, "password_hash": server.hash_password("Pass@123"),
                          "role": role, "institution_id": iid, "status": "active", "created_at": server.now_iso(), **extra})
    return uid


@pytest.fixture(scope="module")
def ctx():
    async def _init():
        server.client = AsyncIOMotorClient(server.mongo_url)
        server.db = server.client[TEST_DB]
    server.app.router.on_startup.insert(0, _init)
    orig = server._put_object, server._get_object
    server._put_object = lambda path, data, ct: (FAKE.__setitem__(path, (data, ct)), {"path": path})[1]
    server._get_object = lambda path: FAKE[path]
    MongoClient(server.mongo_url).drop_database(TEST_DB)
    mon = MongoClient(server.mongo_url)[TEST_DB]
    with TestClient(server.app, base_url="https://testserver") as C:
        def login(email, pw="Pass@123"):
            r = C.post("/api/auth/login", json={"email": email, "password": pw})
            assert r.status_code == 200, r.text
            tok = r.cookies.get("access_token"); C.cookies.clear()
            return Sess(C, tok)
        platform = login(PA_EMAIL, PA_PW)
        A = platform.post("/api/res/institutions", json={"name": "UPI School", "slug": "p51a", "admin_email": "a@p51.test",
                                                         "admin_password": "Admin@123"}).json()["id"]
        B = platform.post("/api/res/institutions", json={"name": "Other", "slug": "p51b", "admin_email": "b@p51.test",
                                                         "admin_password": "Admin@123"}).json()["id"]
        mon.institutions.update_one({"id": A}, {"$set": {"code": "UPS"}})
        admin, admin_b = login("a@p51.test", "Admin@123"), login("b@p51.test", "Admin@123")
        mon.academic_units.insert_many([{"id": "uHS", "institution_id": A, "name": "HS"}, {"id": "uLP", "institution_id": A, "name": "LP"}])
        for g, u in [(4, "uLP"), (8, "uHS")]:
            mon.classes.insert_one({"id": str(uuid.uuid4()), "institution_id": A, "name": f"Grade {g}", "grade_level": str(g), "academic_unit_id": u})
        mon.academic_years.insert_one({"id": str(uuid.uuid4()), "institution_id": A, "name": "2026-27", "start_date": D(-200), "status": "active"})
        pr = {}
        for k, unit in (("pl", "uLP"), ("ph", "uHS")):
            pr[k] = _user(mon, A, f"{k}@p51.test", "teacher")
            mon.principal_assignments.insert_one({"id": str(uuid.uuid4()), "institution_id": A, "user_id": pr[k],
                                                  "scope_type": "units", "unit_ids": [unit], "designation": "principal"})
        _user(mon, A, "t@p51.test", "teacher")
        sid = {}
        for k, g, ph in (("a", 8, "9500000001"), ("c", 4, "9500000003")):
            sid[k] = str(uuid.uuid4())
            mon.students.insert_one({"id": sid[k], "institution_id": A, "first_name": k.upper(), "last_name": "Kid", "class_name": f"Grade {g}",
                                     "section": "A", "enrollment_status": "enrolled", "admission_no": f"ADM/{k}1", "guardian_phone": ph,
                                     "guardian_name": f"G{k}", "created_at": server.now_iso()})
        _user(mon, A, "pa@p51.test", "parent", student_ids=[sid["a"]])
        _user(mon, A, "pc@p51.test", "parent", student_ids=[sid["c"]])
        for unit, amt in (("uHS", 1000), ("uLP", 500)):
            st = admin.post("/api/fees/structures", json={"name": unit, "academic_year": "2026-27", "academic_unit_id": unit,
                                                          "heads": [{"title": "Tuition", "amount": amt, "frequency": "term"}]}).json()
            admin.post(f"/api/fees/structures/{st['id']}/apply")
            admin.post(f"/api/fees/structures/{st['id']}/generate", json={"frequency": "term", "periods": [
                {"label": "Term 1", "due_date": D(-10)}, {"label": "Term 2", "due_date": D(40)}]})
        inv = lambda k, p="Term 1": mon.fee_invoices.find_one({"student_id": sid[k], "period_label": p})  # noqa: E731
        yield {"admin": admin, "admin_b": admin_b, "A": A, "db": mon, "sid": sid, "inv": inv,
               **{k: login(f"{k}@p51.test") for k in ("pl", "ph", "t", "pa", "pc")}}
    server._put_object, server._get_object = orig
    MongoClient(server.mongo_url).drop_database(TEST_DB)


def _fees(sess, sid):
    r = sess.get(f"/api/parent/child/{sid}/fees")
    assert r.status_code == 200, r.text
    return r.json()


def _t1(fees):
    return next(i for i in fees["invoices"] if i["period_label"] == "Term 1")


def _decode(data_uri):
    import zxingcpp
    img = Image.open(io.BytesIO(base64.b64decode(data_uri.split(",", 1)[1])))
    return zxingcpp.read_barcodes(img)[0].text


def test_upi_settings_validation_and_audit(ctx):
    admin, db = ctx["admin"], ctx["db"]
    assert admin.put("/api/fees/upi-settings", json={"enabled": True, "vpa": "notavpa", "payee_name": "X"}).status_code == 400
    assert admin.put("/api/fees/upi-settings", json={"enabled": True, "vpa": "school@okaxis", "payee_name": ""}).status_code == 400
    assert ctx["ph"].put("/api/fees/upi-settings", json={"enabled": False}).status_code == 403
    assert _t1(_fees(ctx["pa"], ctx["sid"]["a"]))["upi"] is None  # not configured yet
    r = admin.put("/api/fees/upi-settings", json={"enabled": True, "vpa": "school@okaxis", "payee_name": "UPI School", "instructions": "Add child name"})
    assert r.status_code == 200 and ctx["ph"].get("/api/fees/upi-settings").json()["vpa"] == "school@okaxis"
    assert db.audit_logs.count_documents({"action": "fee_upi_settings"}) == 1


def test_qr_encodes_current_balance(ctx):
    pa, sid, admin = ctx["pa"], ctx["sid"], ctx["admin"]
    up = _t1(_fees(pa, sid["a"]))["upi"]
    assert up["uri"].startswith("upi://pay?pa=school@okaxis&pn=UPI%20School&am=1000.00&cu=INR&tn=Fee%20ADM%2Fa1%20")
    assert _decode(up["qr"]) == up["uri"] and "&tr=ADMa1" in up["uri"]
    admin.post("/api/fees/payments", json={"invoice_id": ctx["inv"]("a")["id"], "amount": 300, "method": "cash"})
    up2 = _t1(_fees(pa, sid["a"]))["upi"]
    assert "am=700.00" in _decode(up2["qr"]) and up2["amount"] == 700
    pi = pa.get(f"/api/fees/invoices/{ctx['inv']('a')['id']}/pay-info").json()
    assert pi["upi"]["uri"] == up2["uri"] and pi["admission_no"] == "ADM/a1"
    assert pa.get(f"/api/fees/invoices/{ctx['inv']('c')['id']}/pay-info").status_code == 403
    assert ctx["pa"].get(f"/api/parent/child/{sid['c']}/fees").status_code == 403
    admin.put("/api/fees/upi-settings", json={"enabled": False, "vpa": "school@okaxis", "payee_name": "UPI School"})
    assert _t1(_fees(pa, sid["a"]))["upi"] is None
    admin.put("/api/fees/upi-settings", json={"enabled": True, "vpa": "school@okaxis", "payee_name": "UPI School"})


def _proof(sess, inv_id, amount, paid_on, utr="", data=None, name="pay.png", ctype="image/png"):
    return sess.post(f"/api/parent/fees/invoices/{inv_id}/proofs", files={"file": (name, data or _png(), ctype)},
                     data={"amount": str(amount), "paid_on": paid_on, "utr": utr, "note": "paid via GPay"})


def test_proof_upload_validation_and_queue(ctx):
    pa, sid, inv = ctx["pa"], ctx["sid"], ctx["inv"]("a")["id"]
    assert _proof(pa, inv, 700, D(1)).status_code == 400  # future date
    assert _proof(pa, inv, 701, D(-2)).status_code == 400  # > balance
    assert _proof(pa, inv, 700, D(-2), data=b"%PDF-1", name="x.pdf", ctype="application/pdf").status_code == 400
    assert _proof(pa, inv, 700, D(-2), data=b"0" * (5 * 1024 * 1024 + 1)).status_code == 400
    assert _proof(pa, ctx["inv"]("c")["id"], 100, D(-2)).status_code == 403  # not my child
    r = _proof(pa, inv, 700, D(-2), utr="123456789012")
    assert r.status_code == 200, r.text
    p = r.json()["proof"]
    ctx["proof_a"] = p["id"]
    assert r.json()["utr_warning"] == [] and "file_path" not in p
    stored = ctx["db"].fee_payment_proofs.find_one({"id": p["id"]})
    assert stored["file_path"] in FAKE and FAKE[stored["file_path"]][1] == "image/png"  # object storage, not Mongo
    assert "data" not in stored and isinstance(stored["file_path"], str)
    assert _proof(pa, inv, 700, D(-2)).status_code == 409  # duplicate pending
    f = _fees(pa, sid["a"])
    assert f["proofs"][0]["status"] == "pending"
    # c's parent reuses the same UTR → warning (not blocked)
    w = _proof(ctx["pc"], ctx["inv"]("c")["id"], 500, D(-1), utr="123456789012")
    assert w.status_code == 200 and w.json()["utr_warning"][0]["kind"] == "proof"
    ctx["proof_c"] = w.json()["proof"]["id"]
    assert {x["id"] for x in ctx["admin"].get("/api/fees/proofs").json()["proofs"]} == {ctx["proof_a"], ctx["proof_c"]}
    assert [x["id"] for x in ctx["ph"].get("/api/fees/proofs").json()["proofs"]] == [ctx["proof_a"]]
    assert [x["id"] for x in ctx["pl"].get("/api/fees/proofs").json()["proofs"]] == [ctx["proof_c"]]
    assert ctx["t"].get("/api/fees/proofs").status_code == 403
    assert ctx["admin"].get("/api/fees/proofs/stats").json() == {"pending_proofs": 2, "open_issues": 0, "total": 2}
    assert ctx["admin"].get(f"/api/fees/proofs/{ctx['proof_a']}/file").content == _png()
    assert ctx["pc"].get(f"/api/fees/proofs/{ctx['proof_a']}/file").status_code == 403
    assert ctx["pa"].get(f"/api/fees/proofs/{ctx['proof_a']}/file").status_code == 200
    assert ctx["admin_b"].post(f"/api/fees/proofs/{ctx['proof_a']}/approve", json={}).status_code == 404


def test_approve_creates_normal_payment(ctx):
    db, sid = ctx["db"], ctx["sid"]
    assert ctx["pl"].post(f"/api/fees/proofs/{ctx['proof_a']}/approve", json={}).status_code == 403  # other division
    r = ctx["ph"].post(f"/api/fees/proofs/{ctx['proof_a']}/approve", json={})
    assert r.status_code == 200, r.text
    pay = r.json()["payment"]
    assert (pay["method"], pay["reference"], pay["paid_on"], pay["amount"], pay["collected_by"], pay["proof_id"]) == \
        ("upi", "123456789012", D(-2), 700, "PH", ctx["proof_a"])
    assert pay["receipt_no"].startswith("UPS-2026-") and r.json()["invoice"]["balance"] == 0
    assert ctx["ph"].post(f"/api/fees/proofs/{ctx['proof_a']}/approve", json={}).status_code == 409
    book = ctx["admin"].get("/api/fees/day-book", params={"date": D(-2)}).json()
    assert pay["receipt_no"] in [p["receipt_no"] for p in book["payments"]]
    acc = db.fee_accounts.find_one({"student_id": sid["a"]})
    assert pay["receipt_no"] in [p["receipt_no"] for p in ctx["admin"].get(f"/api/fees/accounts/{acc['id']}").json()["payments"]]
    assert ctx["pa"].get(f"/api/fees/payments/{pay['id']}/receipt.pdf").content[:4] == b"%PDF"
    f = _fees(ctx["pa"], sid["a"])
    assert _t1(f)["upi"] is None and f["proofs"][0]["status"] == "approved" and f["proofs"][0]["receipt_no"] == pay["receipt_no"]
    assert db.messages.count_documents({"module": "fee_proof", "recipient_phone": "9500000001"}) >= 1
    assert db.audit_logs.count_documents({"action": "fee_proof_approve"}) == 1


def test_reject_shows_reason_and_allows_resubmit(ctx):
    pc, sid, inv = ctx["pc"], ctx["sid"], ctx["inv"]("c")["id"]
    assert ctx["pl"].post(f"/api/fees/proofs/{ctx['proof_c']}/reject", json={"reason": "x"}).status_code == 422
    r = ctx["pl"].post(f"/api/fees/proofs/{ctx['proof_c']}/reject", json={"reason": "Amount not received in bank"})
    assert r.status_code == 200 and r.json()["proof"]["status"] == "rejected"
    f = _fees(pc, sid["c"])
    assert f["proofs"][0]["reject_reason"] == "Amount not received in bank"
    again = _proof(pc, inv, 500, D(-1), utr="999988887777")
    assert again.status_code == 200 and again.json()["utr_warning"] == []
    ctx["proof_c2"] = again.json()["proof"]["id"]


def test_issue_thread_end_to_end(ctx):
    pc, sid, inv = ctx["pc"], ctx["sid"], ctx["inv"]("c")["id"]
    r = pc.post(f"/api/parent/fees/invoices/{inv}/issues", data={"message": "I already paid on GPay"}, files={"file": ("s.png", _png(), "image/png")})
    assert r.status_code == 200, r.text
    iss = r.json()
    assert iss["status"] == "open" and iss["messages"][0]["has_file"]
    assert pc.post(f"/api/parent/fees/invoices/{inv}/issues", data={"message": "again"}).status_code == 409
    assert [i["id"] for i in ctx["pl"].get("/api/fees/issues").json()["issues"]] == [iss["id"]]
    assert ctx["ph"].get("/api/fees/issues").json()["issues"] == []
    assert ctx["admin"].get("/api/fees/proofs/stats").json()["open_issues"] == 1
    mid = iss["messages"][0]["id"]
    assert ctx["pl"].get(f"/api/fees/issues/{iss['id']}/messages/{mid}/file").content == _png()
    assert ctx["pa"].get(f"/api/fees/issues/{iss['id']}/messages/{mid}/file").status_code == 403
    rep = ctx["pl"].post(f"/api/fees/issues/{iss['id']}/reply", json={"text": "Checking with the bank"})
    assert rep.json()["messages"][-1]["by"] == "staff"
    pr = pc.post(f"/api/parent/fees/issues/{iss['id']}/messages", data={"message": "UTR is 999988887777"})
    assert pr.json()["messages"][-1]["by"] == "parent" and len(pr.json()["messages"]) == 3
    assert ctx["ph"].post(f"/api/fees/issues/{iss['id']}/record-payment", json={"amount": 500}).status_code == 403
    # proof c2 is still pending → approve it from the queue is also possible; here staff records from the issue
    ctx["db"].fee_payment_proofs.update_one({"id": ctx["proof_c2"]}, {"$set": {"status": "rejected", "reject_reason": "Duplicate of issue"}})
    done = ctx["pl"].post(f"/api/fees/issues/{iss['id']}/record-payment", json={"amount": 500, "utr": "999988887777", "paid_on": D(-1)})
    assert done.status_code == 200, done.text
    assert done.json()["issue"]["status"] == "resolved" and done.json()["payment"]["paid_on"] == D(-1)
    assert _fees(pc, sid["c"])["issues"][0]["status"] == "resolved"
    assert ctx["pl"].post(f"/api/fees/issues/{iss['id']}/status", json={"status": "open"}).json()["status"] == "open"
    assert ctx["pl"].post(f"/api/fees/issues/{iss['id']}/status", json={"status": "resolved"}).json()["status"] == "resolved"


def test_backdated_payment_dates_and_principal_scope(ctx):
    admin, db = ctx["admin"], ctx["db"]
    t2 = ctx["inv"]("a", "Term 2")["id"]
    assert admin.post("/api/fees/payments", json={"invoice_id": t2, "amount": 10, "method": "cash", "paid_on": D(1)}).status_code == 400
    assert admin.post("/api/fees/payments", json={"invoice_id": t2, "amount": 10, "method": "cash", "paid_on": D(-201)}).status_code == 400
    r = admin.post("/api/fees/payments", json={"invoice_id": t2, "amount": 100, "method": "cash", "paid_on": D(-5)}).json()["payment"]
    assert r["paid_on"] == D(-5) and r["backdated"] and r["recorded_at"][:10] >= D(-1)
    assert r["receipt_no"] in [p["receipt_no"] for p in admin.get("/api/fees/day-book", params={"date": D(-5)}).json()["payments"]]
    assert r["receipt_no"] not in [p["receipt_no"] for p in admin.get("/api/fees/day-book", params={"date": D(0)}).json()["payments"]]
    ms = admin.get("/api/fees/monthly-summary", params={"month": D(-5)[:7]}).json()
    assert any(d["date"] == D(-5) for d in ms["daily"])
    assert db.audit_logs.find_one({"action": "fee_payment", "entity_id": r["id"]})["entity_name"].count("BACKDATED") == 1
    assert ctx["pl"].post("/api/fees/payments", json={"invoice_id": t2, "amount": 10, "method": "cash"}).status_code == 403
    assert ctx["t"].post("/api/fees/payments", json={"invoice_id": t2, "amount": 10, "method": "cash"}).status_code == 403
    p2 = ctx["ph"].post("/api/fees/payments", json={"invoice_id": t2, "amount": 50, "method": "upi"})
    assert p2.status_code == 200 and p2.json()["payment"]["collected_by"] == "PH"
    pid = p2.json()["payment"]["id"]
    assert ctx["pl"].post(f"/api/fees/payments/{pid}/reverse", json={"reason": "wrong"}).status_code == 403
    assert ctx["ph"].post(f"/api/fees/payments/{pid}/reverse", json={"reason": "wrong entry"}).status_code == 200


def test_statement_reconciles_with_ledger(ctx):
    import pypdfium2 as pdfium
    admin, sid, db = ctx["admin"], ctx["sid"], ctx["db"]
    acc = db.fee_accounts.find_one({"student_id": sid["a"]})
    led = admin.get(f"/api/fees/accounts/{acc['id']}").json()
    st = admin.get(f"/api/fees/students/{sid['a']}/statement", params={"academic_year": "2026-27"}).json()
    assert (st["totals"]["paid"], st["closing_balance"]) == (led["summary"]["paid"], led["summary"]["balance"])
    live = sum(p["amount"] for p in led["payments"] if not p["reversed"])
    assert st["payments_total"] == live == 1100 and st["reversed_total"] == 50
    pdf = admin.get(f"/api/fees/students/{sid['a']}/statement.pdf", params={"academic_year": "2026-27"})
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
    doc = pdfium.PdfDocument(pdf.content)
    text = "".join(doc[i].get_textpage().get_text_range() for i in range(len(doc)))
    assert server._inr(st["closing_balance"]) in text and "FEE STATEMENT" in text and "REVERSED" in text
    assert ctx["pa"].get(f"/api/parent/child/{sid['a']}/fees/statement.pdf").content[:4] == b"%PDF"
    assert ctx["pa"].get(f"/api/parent/child/{sid['c']}/fees/statement.pdf").status_code == 403
    assert ctx["pl"].get(f"/api/fees/students/{sid['a']}/statement.pdf").status_code == 403
    assert ctx["admin_b"].get(f"/api/fees/students/{sid['a']}/statement").status_code == 404


def test_openapi_has_phase51_endpoints(ctx):
    paths = ctx["admin"].get("/api/openapi.json").json()["paths"]
    for p in ("/api/fees/upi-settings", "/api/fees/invoices/{inv_id}/pay-info", "/api/parent/fees/invoices/{inv_id}/proofs",
              "/api/fees/proofs", "/api/fees/proofs/stats", "/api/fees/proofs/{pid}/approve", "/api/fees/proofs/{pid}/reject",
              "/api/fees/proofs/{pid}/file", "/api/parent/fees/invoices/{inv_id}/issues", "/api/fees/issues",
              "/api/fees/issues/{iss_id}/reply", "/api/fees/issues/{iss_id}/record-payment", "/api/fees/students/{sid}/statement.pdf",
              "/api/parent/child/{sid}/fees/statement.pdf"):
        assert p in paths, p
