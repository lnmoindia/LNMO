"""Phase 23 — Live LPGS validation of monitor endpoint and manual reminder.
READ-ONLY where possible; manual-remind test creates a tiny throwaway HW and closes it after.
"""
import os, requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE:
    # fallback to frontend .env
    with open("/app/frontend/.env") as f:
        for ln in f:
            if ln.startswith("REACT_APP_BACKEND_URL"):
                BASE = ln.split("=", 1)[1].strip().strip('"').rstrip("/")
API = f"{BASE}/api"


def _tok(email, pw):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=15)
    assert r.status_code == 200, (email, r.status_code, r.text[:200])
    return r.cookies.get("access_token") or r.json().get("access_token")


def _hdr(t):
    return {"Authorization": f"Bearer {t}"}


def test_admin_monitor_homework():
    t = _tok("admin@lpgs.com", "admin123")
    r = requests.get(f"{API}/homework/monitor", params={"type": "homework"}, headers=_hdr(t), timeout=30)
    assert r.status_code == 200, r.text[:300]
    j = r.json()
    assert j["type"] == "homework"
    for k in ("stats", "teachers", "classes", "pending"):
        assert k in j
    for k in ("active", "submission_rate", "pending_verifications", "late_rate"):
        assert k in j["stats"]
    # pending sorted oldest-first
    ages = [p["age_days"] for p in j["pending"]]
    assert ages == sorted(ages, reverse=True), f"pending not oldest-first: {ages[:10]}"
    print(f"admin homework monitor: active={j['stats']['active']} rate={j['stats']['submission_rate']}% pending={j['stats']['pending_verifications']} late={j['stats']['late_rate']}% teachers={len(j['teachers'])} classes={len(j['classes'])}")


def test_admin_monitor_assignment():
    t = _tok("admin@lpgs.com", "admin123")
    r = requests.get(f"{API}/homework/monitor", params={"type": "assignment"}, headers=_hdr(t), timeout=30)
    assert r.status_code == 200, r.text[:300]
    assert r.json()["type"] == "assignment"


def test_invalid_type_400():
    t = _tok("admin@lpgs.com", "admin123")
    r = requests.get(f"{API}/homework/monitor", params={"type": "bogus"}, headers=_hdr(t), timeout=15)
    assert r.status_code == 400, (r.status_code, r.text[:200])


def test_principal_scope_UP_no_grade8():
    t = _tok("testprincipal@lpgs.com", "teach123")
    r = requests.get(f"{API}/homework/monitor", params={"type": "homework"}, headers=_hdr(t), timeout=30)
    assert r.status_code == 200, r.text[:300]
    j = r.json()
    g8_cls = [c for c in j["classes"] if c["class_name"] == "Grade 8"]
    g8_pend = [p for p in j["pending"] if p.get("class_name") == "Grade 8"]
    assert g8_cls == [], f"UP principal should NOT see Grade 8 classes: {g8_cls}"
    assert g8_pend == [], f"UP principal should NOT see Grade 8 pending: {g8_pend[:3]}"
    # should see UP (grades 5-7) only (if any items in UP)
    seen = {c["class_name"] for c in j["classes"]}
    bad = seen - {"Grade 5", "Grade 6", "Grade 7"}
    assert not bad, f"UP principal saw out-of-scope classes: {bad}"
    print(f"UP principal classes visible: {sorted(seen)}")


def test_teacher_forbidden_403():
    t = _tok("prasad27@lpgs.com", "teach123")
    r = requests.get(f"{API}/homework/monitor", params={"type": "homework"}, headers=_hdr(t), timeout=15)
    assert r.status_code == 403, (r.status_code, r.text[:200])


def test_student_forbidden_403():
    t = _tok("g8student@lpgs.com", "student123")
    r = requests.get(f"{API}/homework/monitor", params={"type": "homework"}, headers=_hdr(t), timeout=15)
    assert r.status_code == 403, (r.status_code, r.text[:200])


def test_default_date_range_current_month():
    # omit from/to; expect 200 and sensible aggregation
    t = _tok("admin@lpgs.com", "admin123")
    r = requests.get(f"{API}/homework/monitor", params={"type": "homework"}, headers=_hdr(t), timeout=20)
    assert r.status_code == 200


def test_manual_reminder_dedupe_and_closed():
    """Create tiny throwaway HW as prasad27, remind twice (expect sent>=1 then 0), close, remind -> 400."""
    t = _tok("prasad27@lpgs.com", "teach123")
    # Create a throwaway homework due far future to avoid the sweep sending bells now
    r = requests.post(f"{API}/homework",
                      json={"class_name": "Grade 8", "section": "A", "subject": "Mathematics",
                            "title": "TEST_P23_REMIND", "instructions": "throwaway",
                            "due_date": "2099-12-31T23:59:00+00:00"},
                      headers=_hdr(t), timeout=20)
    assert r.status_code in (200, 201), r.text[:300]
    hw_id = r.json().get("homework", {}).get("id") or r.json().get("id")
    assert hw_id, r.text[:300]
    try:
        r1 = requests.post(f"{API}/homework/{hw_id}/remind", headers=_hdr(t), timeout=20)
        assert r1.status_code == 200, (r1.status_code, r1.text[:200])
        j1 = r1.json()
        assert j1.get("sent", 0) >= 1, j1
        r2 = requests.post(f"{API}/homework/{hw_id}/remind", headers=_hdr(t), timeout=20)
        assert r2.status_code == 200
        assert r2.json().get("sent") == 0, r2.json()
        # non-owner (another HS teacher) -> 403
        other = _tok("manoj@lpgs.com", "teach123")
        r3 = requests.post(f"{API}/homework/{hw_id}/remind", headers=_hdr(other), timeout=20)
        assert r3.status_code == 403, (r3.status_code, r3.text[:200])
    finally:
        # close + delete
        requests.post(f"{API}/homework/{hw_id}/close", headers=_hdr(t), timeout=15)
        # remind on closed -> 400
        r4 = requests.post(f"{API}/homework/{hw_id}/remind", headers=_hdr(t), timeout=15)
        assert r4.status_code == 400, (r4.status_code, r4.text[:200])
        # attempt cleanup (best effort)
        requests.delete(f"{API}/homework/{hw_id}", headers=_hdr(t), timeout=15)
