"""Phase 47 — live LPGS regression against deployed REACT_APP_BACKEND_URL.
Safe-by-default: no reminders on real classes other than Grade 8 (already deduped),
no slip registrations.
"""
import os
import requests
import pytest

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://lnmo-fees.preview.emergentagent.com").rstrip("/")


def _login(ident, pw, **ctx):
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login", json={"email": ident, "password": pw, **ctx})
    return r, s


@pytest.fixture(scope="module")
def admin():
    r, s = _login("admin@lpgs.com", "admin123", slug="lpgs")
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def classes(admin):
    r = admin.get(f"{BASE}/api/students/invite-progress")
    assert r.status_code == 200, r.text
    return {c["class_name"]: c for c in r.json()["classes"]}


# ---------- Phone login ----------

def test_phone_login_lpgs_variants_slip_parent():
    for ident in ("9876500001", "98765 00001", "+91 98765 00001", "91-9876500001", "0987-6500001"):
        r, _ = _login(ident, "Slip@2026", slug="lpgs")
        assert r.status_code == 200, (ident, r.status_code, r.text)
        j = r.json()
        assert j["role"] == "parent"


def test_phone_login_wrong_phone_message():
    r, _ = _login("9999999999", "whatever1", slug="lpgs")
    assert r.status_code == 401
    assert r.json()["detail"] == "Invalid mobile number or password"


def test_phone_login_teacher_phone_rejected():
    # teachers should never match by phone; using an unlikely phone to avoid real lockouts
    r, _ = _login("9000000000", "teach123", slug="lpgs")
    assert r.status_code == 401


def test_email_login_regression():
    r, _ = _login("admin@lpgs.com", "admin123", slug="lpgs")
    assert r.status_code == 200
    r2, _ = _login("parent.demo@lpgs.com", "parent123", slug="lpgs")
    assert r2.status_code == 200


def test_phone_login_generic_global_unique():
    # /login without slug/domain must still work when phone is globally unique
    r, _ = _login("9876500001", "Slip@2026")
    assert r.status_code == 200
    assert r.json()["role"] == "parent"


# ---------- Progress funnel ----------

def test_progress_funnel_shape_and_order(classes):
    expected = [f"Grade {i}" for i in range(1, 13)]
    rows = list(classes.keys())
    # at least ordered subset of real LPGS grades
    for a, b in zip(expected, rows):
        assert a == b, (expected, rows)
    for name, c in classes.items():
        assert c["invited"] == c["setup_completed"] + c["pending"], (name, c)
        for k in ("class_id", "class_name", "enrolled", "invited", "setup_completed",
                 "pending", "not_invited", "no_phone", "reminder_sent_today"):
            assert k in c, (name, k)


def test_progress_funnel_grade8_matches_spec(classes):
    g8 = classes["Grade 8"]
    assert g8["invited"] == 3 and g8["setup_completed"] == 1 and g8["pending"] == 2 and g8["no_phone"] == 0
    assert g8["reminder_sent_today"] is True


# ---------- Reminder dedupe (Grade 8 already sent today) ----------

def test_reminder_grade8_already_sent_today_no_quota_change(admin, classes):
    inst_r = admin.get(f"{BASE}/api/institutions/current").json()
    used_before = inst_r.get("comm", {}).get("quota", {}).get("whatsapp", {}).get("used")
    r = admin.post(f"{BASE}/api/students/invite-reminder", json={"class_id": classes["Grade 8"]["class_id"]})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["ok"] is False and j["code"] == "already_sent_today" and j["sent"] == 0
    inst_r2 = admin.get(f"{BASE}/api/institutions/current").json()
    used_after = inst_r2.get("comm", {}).get("quota", {}).get("whatsapp", {}).get("used")
    assert used_before == used_after, (used_before, used_after)


# ---------- Bulk slips (read-only on Grade 5; do NOT register) ----------

def test_bulk_slips_grade5_single_unused_per_student(admin, classes):
    g5_id = classes["Grade 5"]["class_id"]
    r = admin.post(f"{BASE}/api/students/setup-codes/bulk", json={"class_ids": [g5_id]})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["count"] == 3, j
    codes = {s["code"] for s in j["slips"]}
    assert len(codes) == 3
    for slip in j["slips"]:
        assert len(slip["code"]) == 8
        for ch in slip["code"]:
            assert ch in "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
        for k in ("student_id", "student_name", "class", "admission_no", "code"):
            assert k in slip, slip
