"""Phase 46b LIVE — hits deployed LPGS backend via REACT_APP_BACKEND_URL.
Verifies: LPGS admission-no backfill coverage, next-admission-no, paper-slip code
flow (throwaway student), live Slip Parent login. Cleans up throwaway data.
"""
import os
import re
import time
import pytest
import requests

BASE = "https://lnmo-fees.preview.emergentagent.com".rstrip("/")

ADMIN_EMAIL = "admin@lpgs.com"
ADMIN_PW = "admin123"
SLIP_PARENT_EMAIL = "p9876500001@lpgs.parent.invite"
SLIP_PARENT_PW = "Slip@2026"


def _login(email, pw):
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login", json={"email": email, "password": pw}, timeout=20)
    assert r.status_code == 200, f"login {email}: {r.status_code} {r.text[:200]}"
    tok = r.cookies.get("access_token") or r.json().get("access_token")
    s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


@pytest.fixture(scope="module")
def admin():
    return _login(ADMIN_EMAIL, ADMIN_PW)


def test_lpgs_admission_backfill_complete(admin):
    """All 36 LPGS students have unique LPGS-G{n}-{nnn} admission numbers."""
    r = admin.get(f"{BASE}/api/res/students?limit=500", timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    rows = data if isinstance(data, list) else (data.get("items") or data.get("students") or [])
    assert len(rows) >= 36, f"expected >=36 LPGS students, got {len(rows)}"
    adms = [s.get("admission_no") for s in rows]
    missing = [s for s in rows if not s.get("admission_no")]
    assert not missing, f"students missing admission_no: {[s.get('first_name') for s in missing]}"
    pat = re.compile(r"^LPGS-G\d{1,2}-\d{3}$")
    bad = [a for a in adms if not pat.match(a)]
    # Allow legacy custom formats but flag; LPGS seeds expected to be strict
    lpgs_fmt = [a for a in adms if pat.match(a)]
    assert len(lpgs_fmt) >= 36, f"expected 36+ LPGS-G*-* adms, got {len(lpgs_fmt)}; non-matching: {bad[:5]}"
    dups = {a for a in adms if adms.count(a) > 1}
    assert not dups, f"duplicate admission numbers: {dups}"


def test_next_admission_no_grade8(admin):
    r = admin.get(f"{BASE}/api/students/next-admission-no", params={"class_name": "Grade 8"}, timeout=20)
    assert r.status_code == 200, r.text
    nxt = r.json().get("admission_no")
    assert re.fullmatch(r"LPGS-G8-\d{3}", nxt), f"unexpected next adm: {nxt}"


def test_backfill_is_idempotent_assigns_zero(admin):
    r = admin.post(f"{BASE}/api/students/backfill-admission-nos", timeout=30)
    assert r.status_code == 200, r.text
    assert r.json().get("assigned", -1) == 0, f"expected 0 new assignments, got {r.json()}"


def test_slip_parent_live_login_sees_child():
    s = _login(SLIP_PARENT_EMAIL, SLIP_PARENT_PW)
    r = s.get(f"{BASE}/api/auth/me", timeout=15)
    assert r.status_code == 200, r.text
    me = r.json()
    assert me.get("role") == "parent", me
    # Fetch parent children
    r2 = s.get(f"{BASE}/api/portal/parent/children", timeout=20)
    if r2.status_code == 404:
        r2 = s.get(f"{BASE}/api/parent/children", timeout=20)
    assert r2.status_code == 200, f"children endpoint: {r2.status_code} {r2.text[:200]}"
    body = r2.json()
    kids = body if isinstance(body, list) else (body.get("children") or body.get("students") or [])
    names = " ".join([f"{k.get('first_name','')} {k.get('last_name','')} {k.get('name','')}" for k in kids]).lower()
    adms = [k.get("admission_no") for k in kids]
    assert "aravind" in names or "fathima" in names, f"expected Aravind Fathima in children, got {kids}"
    assert "LPGS-G1-001" in adms, f"expected LPGS-G1-001 in {adms}"


def test_auto_assign_on_create_throwaway(admin):
    """Create a throwaway student via /api/students/enroll WITHOUT admission_no → auto-assigned.
    Also verify explicit admission_no is preserved. Clean up both."""
    created_ids = []
    try:
        payload = {"first_name": "TEST_P46B_auto", "last_name": "ZZ", "class_name": "Grade 8",
                   "section": "A", "enroll": True}
        r = admin.post(f"{BASE}/api/students/enroll", json=payload, timeout=20)
        assert r.status_code == 200, r.text
        js = r.json()
        sid = js.get("id") or js.get("student_id")
        adm = js.get("admission_no")
        created_ids.append(sid)
        assert sid and re.fullmatch(r"LPGS-G8-\d{3}", adm or ""), f"auto-assign failed: {js}"

        # explicit admission_no retained
        payload2 = {"first_name": "TEST_P46B_explicit", "last_name": "ZZ", "class_name": "Grade 8",
                    "section": "A", "enroll": True, "admission_no": "TEST-CUSTOM-999"}
        r2 = admin.post(f"{BASE}/api/students/enroll", json=payload2, timeout=20)
        assert r2.status_code == 200, r2.text
        js2 = r2.json()
        created_ids.append(js2.get("id"))
        assert js2.get("admission_no") == "TEST-CUSTOM-999", js2
    finally:
        for sid in created_ids:
            if sid:
                try:
                    admin.delete(f"{BASE}/api/res/students/{sid}", timeout=15)
                except Exception:
                    pass


def test_paper_slip_code_register_e2e(admin):
    """Create throwaway student (no phone) → generate setup-code → register via code alone → cleanup."""
    sid = None
    phone = "9990046199"
    try:
        payload = {"first_name": "TEST_P46B_slip", "last_name": "ZZ", "class_name": "Grade 8",
                   "section": "A", "enroll": True}
        r = admin.post(f"{BASE}/api/students/enroll", json=payload, timeout=20)
        assert r.status_code == 200, r.text
        sid = r.json()["id"]

        # Generate setup code
        rc = admin.post(f"{BASE}/api/students/{sid}/setup-code", timeout=20)
        assert rc.status_code == 200, rc.text
        slip = rc.json()
        code = slip["code"]
        assert re.fullmatch(r"[A-Z2-9]{8}", code), f"bad code: {code}"
        assert not set(code) & set("01IOL"), f"forbidden chars in {code}"
        assert "admission_no" in slip and "student_name" in slip and "expires_in_days" in slip

        # Wrong code -> 400
        pub = requests.Session()
        bad = pub.post(f"{BASE}/api/public/parent-register",
                       json={"code": "ZZZZZZZZ", "phone": phone, "password": "Slip@123"}, timeout=15)
        assert bad.status_code == 400, bad.text

        time.sleep(1)  # avoid rate limiter

        # Code + wrong admission no -> 400, code stays unused
        pub2 = requests.Session()
        bad2 = pub2.post(f"{BASE}/api/public/parent-register",
                        json={"code": code, "admission_no": "LPGS-G8-999",
                              "phone": phone, "password": "Slip@123"}, timeout=15)
        assert bad2.status_code == 400, bad2.text

        time.sleep(1)

        # Code alone (dash + lowercase) -> 200
        pretty = f"{code[:4]}-{code[4:]}".lower()
        pub3 = requests.Session()
        ok = pub3.post(f"{BASE}/api/public/parent-register",
                       json={"code": pretty, "phone": f"{phone[:5]} {phone[5:]}",
                             "name": "TEST Slip Parent", "password": "Slip@123"}, timeout=20)
        assert ok.status_code == 200, ok.text

        time.sleep(1)

        # Single-use: reuse -> 400
        pub4 = requests.Session()
        again = pub4.post(f"{BASE}/api/public/parent-register",
                         json={"code": code, "phone": "9990046100", "password": "Slip@123"}, timeout=15)
        assert again.status_code == 400, again.text
    finally:
        # Cleanup: delete throwaway student + parent user by phone
        if sid:
            try:
                admin.delete(f"{BASE}/api/res/students/{sid}", timeout=15)
            except Exception:
                pass
        try:
            # Try to find+delete parent user by phone via admin endpoint
            u = admin.get(f"{BASE}/api/res/users", params={"q": phone, "limit": 10}, timeout=15)
            if u.status_code == 200:
                data = u.json()
                items = data if isinstance(data, list) else (data.get("items") or [])
                for usr in items:
                    if usr.get("phone") == phone and usr.get("role") == "parent":
                        admin.delete(f"{BASE}/api/res/users/{usr['id']}", timeout=15)
        except Exception:
            pass
