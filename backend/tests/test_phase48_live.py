"""Phase 48 live acceptance against LPGS pilot (no destructive writes to demo data).
Validates demo structure invariants, idempotent generation, parent/student views, scope + role guards.
Creates TEST_P48 throwaway structure (no apply/students) for validation errors, deletes it after.
Records a small ₹100 payment on Haritha Sania's Term 1 invoice, then REVERSES it (credit note).
"""
import os, re, uuid
import pytest
import requests

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")


def _login(email, password, slug=None):
    s = requests.Session()
    url = f"{BASE}/api/auth/login"
    r = s.post(url, json={"email": email, "password": password, **({"institution_slug": slug} if slug else {})})
    assert r.status_code == 200, (email, r.status_code, r.text)
    tok = r.cookies.get("access_token")
    s.headers.update({"Authorization": f"Bearer {tok}"})
    s.cookies.clear()
    return s


@pytest.fixture(scope="module")
def admin():
    return _login("admin@lpgs.com", "admin123", "lpgs")


@pytest.fixture(scope="module")
def parent_demo():
    return _login("parent.demo@lpgs.com", "parent123", "lpgs")


@pytest.fixture(scope="module")
def teacher():
    return _login("prasad27@lpgs.com", "teach123", "lpgs")


@pytest.fixture(scope="module")
def student():
    return _login("g8student@lpgs.com", "student123", "lpgs")


@pytest.fixture(scope="module")
def unrelated_parent():
    # parent linked only to Aravind (Grade 1) — must get 403 on Fathima's data
    return _login("9876500001", "Slip@2026", "lpgs")


def _get_demo_struct(admin):
    r = admin.get(f"{BASE}/api/fees/structures")
    assert r.status_code == 200, r.text
    for s in r.json()["structures"]:
        if (s.get("name") == "HS Fee Structure 2026-27"
                and s.get("academic_year") == "2026-27"
                and s.get("invoice_count", 0) > 0):
            return s
    pytest.fail("Demo HS Fee Structure 2026-27 not found")


def test_demo_structure_exists_and_counts(admin):
    s = _get_demo_struct(admin)
    assert s.get("account_count", 0) >= 3
    assert s.get("invoice_count", 0) >= 12


def test_edit_blocked_but_clone_works(admin):
    s = _get_demo_struct(admin)
    # PUT must 409
    r = admin.put(f"{BASE}/api/fees/structures/{s['id']}",
                  json={"name": s["name"], "academic_year": s["academic_year"], "heads": s["heads"]})
    assert r.status_code == 409, (r.status_code, r.text)
    # Clone works
    c = admin.post(f"{BASE}/api/fees/structures/{s['id']}/clone")
    assert c.status_code == 200, c.text
    cid = c.json()["id"]
    # Delete clone to keep DB clean (no invoices yet)
    d = admin.request("delete", f"{BASE}/api/fees/structures/{cid}")
    # If no explicit delete, mark deletion via mongo would be needed; accept 200/204/404/405.
    assert d.status_code in (200, 204, 404, 405), d.status_code


def test_structure_validation_errors(admin):
    # Both unit + class → 400
    bad = {"name": f"TEST_P48 badBoth {uuid.uuid4().hex[:6]}", "academic_year": "2026-27",
           "academic_unit_id": "nope", "class_name": "Grade 8",
           "heads": [{"title": "X", "amount": 1, "frequency": "annual"}]}
    r = admin.post(f"{BASE}/api/fees/structures", json=bad)
    assert r.status_code == 400
    # Duplicate head titles → 400
    bad2 = {"name": f"TEST_P48 dup {uuid.uuid4().hex[:6]}", "academic_year": "2026-27",
            "class_name": "Grade 12",
            "heads": [{"title": "Tuition", "amount": 100, "frequency": "annual"},
                      {"title": "tuition ", "amount": 50, "frequency": "annual"}]}
    r2 = admin.post(f"{BASE}/api/fees/structures", json=bad2)
    assert r2.status_code == 400


def test_generate_idempotent_on_demo(admin):
    """Re-run generate for existing term periods — must create 0 and skip existing."""
    s = _get_demo_struct(admin)
    # Discover existing term periods from accounts/invoices
    accts = admin.get(f"{BASE}/api/fees/accounts", params={"structure_id": s["id"]}).json()["accounts"]
    assert accts, "demo accounts missing"
    led = admin.get(f"{BASE}/api/fees/accounts/{accts[0]['id']}").json()
    term_periods = []
    seen = set()
    for inv in led["invoices"]:
        if inv["frequency"] == "term" and inv["period_label"] not in seen:
            seen.add(inv["period_label"])
            term_periods.append({"label": inv["period_label"], "due_date": inv["due_date"]})
    assert len(term_periods) >= 1
    r = admin.post(f"{BASE}/api/fees/structures/{s['id']}/generate",
                   json={"frequency": "term", "periods": term_periods})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["created"] == 0
    assert body.get("skipped_existing", 0) >= len(term_periods) * len(accts)


def test_fathima_ledger_and_overpay_guard(admin):
    s = _get_demo_struct(admin)
    accts = admin.get(f"{BASE}/api/fees/accounts", params={"structure_id": s["id"]}).json()["accounts"]
    fathima = None
    for a in accts:
        name = (a.get("student_name") or "").lower()
        if "fathima" in name:
            fathima = a
            break
    assert fathima, "Fathima account not found"
    led = admin.get(f"{BASE}/api/fees/accounts/{fathima['id']}").json()
    assert led["summary"]["total"] == 19500
    assert led["summary"]["paid"] == 5000
    assert led["summary"]["balance"] == 14500
    annual = [i for i in led["invoices"] if i["frequency"] == "annual"][0]
    assert annual["status"] == "partial"
    # Overpay → 400
    over = admin.post(f"{BASE}/api/fees/payments",
                      json={"invoice_id": annual["id"], "amount": annual["balance"] + 1, "method": "cash"})
    assert over.status_code == 400


@pytest.fixture(scope="module")
def haritha_term1(admin):
    s = _get_demo_struct(admin)
    accts = admin.get(f"{BASE}/api/fees/accounts", params={"structure_id": s["id"]}).json()["accounts"]
    for a in accts:
        if "haritha" in (a.get("student_name") or "").lower():
            led = admin.get(f"{BASE}/api/fees/accounts/{a['id']}").json()
            for inv in led["invoices"]:
                if inv["period_label"] == "Term 1":
                    return a, inv
    pytest.fail("Haritha Term 1 invoice not found")


def test_payment_and_reversal_cycle(admin, haritha_term1):
    _, inv = haritha_term1
    pre_bal = inv["balance"]
    r = admin.post(f"{BASE}/api/fees/payments",
                   json={"invoice_id": inv["id"], "amount": 100, "method": "cash", "reference": "TEST_P48"})
    assert r.status_code == 200, r.text
    pay = r.json()["payment"]
    recno = pay["receipt_no"]
    assert re.match(r"^LPGS-2026-\d{6}$", recno), recno
    assert int(recno.split("-")[-1]) >= 2  # should be at least 000002
    # Reverse (admin only)
    rev = admin.post(f"{BASE}/api/fees/payments/{pay['id']}/reverse",
                     json={"reason": "TEST_P48 reversal — verifying credit note flow"})
    assert rev.status_code == 200, rev.text
    revbody = rev.json()
    assert revbody["invoice"]["balance"] == pre_bal
    # Credit note present on payment doc via list endpoint
    lst = admin.get(f"{BASE}/api/fees/payments", params={"receipt_no": recno}).json()["payments"]
    assert lst and lst[0]["reversed"] is True
    assert lst[0]["credit_note_no"] == f"CN-{recno}"
    # Double-reverse blocked
    again = admin.post(f"{BASE}/api/fees/payments/{pay['id']}/reverse", json={"reason": "nope again"})
    assert again.status_code == 400
    # Save receipt no for later tests
    pytest._phase48_rec = recno


def test_parent_portal_views(parent_demo, admin):
    # Discover Fathima + Sachin student ids from parent dashboard
    me = parent_demo.get(f"{BASE}/api/parent/children").json()
    kids = me.get("children") or me.get("students") or []
    fathima_id = sachin_id = None
    for k in kids:
        n = (k.get("name") or f"{k.get('first_name','')} {k.get('last_name','')}" ).lower()
        if "fathima" in n:
            fathima_id = k["id"]
        if "sachin" in n:
            sachin_id = k["id"]
    assert fathima_id and sachin_id, kids
    v = parent_demo.get(f"{BASE}/api/parent/child/{fathima_id}/fees").json()
    assert v["summary"]["total"] == 19500
    assert v["summary"]["paid"] == 5000
    assert v["summary"]["balance"] == 14500
    # Sachin: no fee account
    v2 = parent_demo.get(f"{BASE}/api/parent/child/{sachin_id}/fees").json()
    assert v2["summary"]["invoices"] == 0 or v2["summary"]["total"] == 0


def test_api_security_scope_and_roles(admin, teacher, student, unrelated_parent, parent_demo):
    # teacher + student → 403 on money endpoints
    for s in (teacher, student):
        assert s.get(f"{BASE}/api/fees/structures").status_code == 403
        assert s.get(f"{BASE}/api/fees/accounts").status_code == 403
        r = s.post(f"{BASE}/api/fees/payments", json={"invoice_id": "x", "amount": 1, "method": "cash"})
        assert r.status_code == 403
    # Unrelated parent should get 403 on another parent's child
    me = parent_demo.get(f"{BASE}/api/parent/children").json()
    kids = me.get("children") or me.get("students") or []
    fathima_id = next(k["id"] for k in kids if "fathima" in (k.get("name") or k.get("first_name","")).lower())
    r = unrelated_parent.get(f"{BASE}/api/parent/child/{fathima_id}/fees")
    assert r.status_code == 403
