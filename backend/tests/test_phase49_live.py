"""Phase 49 live checks against LPGS. Read-only / non-mutating.
Verifies: day-book (admin ok, teacher/parent 403), receipt PDF (admin/parent cross-child 403, teacher 403),
reminder-settings PUT role guards (NO body change), /api/public/fee-link bad token → 400.
"""
import os
import re
import pytest
import requests

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE}/api"

ADMIN = ("admin@lpgs.com", "admin123", "lpgs")
PARENT = ("parent.demo@lpgs.com", "parent123", "lpgs")
TEACHER = ("prasad27@lpgs.com", "teach123", "lpgs")

FATHIMA_RECEIPT = "LPGS-2026-000001"  # UPI 5000 — Fathima (Grade 8-A), demo parent child
HARITHA_RECEIPT = "LPGS-2026-000002"  # cash 100 reversed — Haritha, NOT demo parent child


def _login(email, password, slug):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password, "institution_slug": slug}, timeout=15)
    assert r.status_code == 200, f"login {email}: {r.status_code} {r.text}"
    tok = r.json().get("access_token") or r.cookies.get("access_token")
    assert tok
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def heads():
    return {"admin": _login(*ADMIN), "parent": _login(*PARENT), "teacher": _login(*TEACHER)}


def _payment_id_by_receipt(admin_h, receipt_no):
    r = requests.get(f"{API}/fees/payments", headers=admin_h, timeout=15)
    assert r.status_code == 200
    for p in r.json().get("payments", r.json() if isinstance(r.json(), list) else []):
        if p.get("receipt_no") == receipt_no:
            return p["id"]
    pytest.skip(f"Receipt {receipt_no} not found")


def test_day_book_admin_ok_bad_date(heads):
    r = requests.get(f"{API}/fees/day-book", params={"date": "2026-10-12"}, headers=heads["admin"], timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    assert "summary" in d and "by_method" in d and "by_collector" in d and "by_class" in d
    assert d["summary"]["total"] == 5000 and d["summary"]["count"] == 1
    assert any(m["key"].lower() == "upi" and m["total"] == 5000 for m in d["by_method"])
    assert any(c["key"] == "Grade 8" and c["total"] == 5000 for c in d["by_class"])
    # bad date → 400
    r2 = requests.get(f"{API}/fees/day-book", params={"date": "12-12"}, headers=heads["admin"], timeout=15)
    assert r2.status_code == 400


def test_day_book_teacher_parent_403(heads):
    for who in ("teacher", "parent"):
        r = requests.get(f"{API}/fees/day-book", params={"date": "2026-10-12"}, headers=heads[who], timeout=15)
        assert r.status_code == 403, f"{who}: {r.status_code}"


def test_receipt_pdf_admin(heads):
    pid = _payment_id_by_receipt(heads["admin"], FATHIMA_RECEIPT)
    r = requests.get(f"{API}/fees/payments/{pid}/receipt.pdf", headers=heads["admin"], timeout=20)
    assert r.status_code == 200
    assert r.content[:4] == b"%PDF" and r.content.rstrip().endswith(b"%%EOF")
    assert "application/pdf" in r.headers.get("content-type", "")


def test_receipt_pdf_parent_own_vs_other(heads):
    admin_h = heads["admin"]
    pid_f = _payment_id_by_receipt(admin_h, FATHIMA_RECEIPT)
    pid_h = _payment_id_by_receipt(admin_h, HARITHA_RECEIPT)
    r_own = requests.get(f"{API}/fees/payments/{pid_f}/receipt.pdf", headers=heads["parent"], timeout=20)
    assert r_own.status_code == 200 and r_own.content[:4] == b"%PDF"
    r_other = requests.get(f"{API}/fees/payments/{pid_h}/receipt.pdf", headers=heads["parent"], timeout=15)
    assert r_other.status_code == 403


def test_receipt_pdf_teacher_403(heads):
    pid = _payment_id_by_receipt(heads["admin"], FATHIMA_RECEIPT)
    r = requests.get(f"{API}/fees/payments/{pid}/receipt.pdf", headers=heads["teacher"], timeout=15)
    assert r.status_code == 403


def test_reminder_endpoint_guards(heads):
    for who in ("teacher", "parent"):
        assert requests.post(f"{API}/fees/reminders/run", json={}, headers=heads[who], timeout=10).status_code == 403
        assert requests.post(f"{API}/fees/reminders/class", json={"class_name": "Grade 8"}, headers=heads[who], timeout=10).status_code == 403
        assert requests.put(f"{API}/fees/reminder-settings", json={"enabled": True}, headers=heads[who], timeout=10).status_code == 403


def test_public_fee_link_bad_token():
    r = requests.get(f"{API}/public/fee-link/this_is_not_a_valid_token_abc", timeout=10)
    assert r.status_code == 400


def test_reminder_settings_get(heads):
    r = requests.get(f"{API}/fees/reminder-settings", headers=heads["admin"], timeout=10)
    assert r.status_code == 200
    s = r.json()
    assert "enabled" in s and "before_days" in s and "overdue_after_days" in s and "repeat_every_days" in s
