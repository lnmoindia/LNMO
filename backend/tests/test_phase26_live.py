"""Phase 26 live backend tests against public URL (cookie-based auth)."""
import os
import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://lnmo-fees.preview.emergentagent.com").rstrip("/")
GRADE8 = "6fc07602-c1b8-437c-bed4-afd82c52a5d7"


def _sess(email, pwd, path="/api/auth/login"):
    s = requests.Session()
    r = s.post(f"{BASE}{path}", json={"email": email, "password": pwd}, timeout=20)
    assert r.status_code == 200, f"login failed {email}: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def admin():
    return _sess("admin@lpgs.com", "admin123")


@pytest.fixture(scope="module")
def principal():
    return _sess("testprincipal@lpgs.com", "teach123")


@pytest.fixture(scope="module")
def teacher():
    return _sess("prasad27@lpgs.com", "teach123")


@pytest.fixture(scope="module")
def platform():
    return _sess("lnmopvt@gmail.com", "Lnmo@2026!")


def _templates(admin):
    r = admin.get(f"{BASE}/api/comm/templates", timeout=20)
    assert r.status_code == 200, r.text
    return r.json()


def _ann_id(admin):
    data = _templates(admin)
    tpls = data["templates"] if isinstance(data, dict) and "templates" in data else data
    for t in tpls:
        if isinstance(t, dict) and "announcement" in (t.get("name") or "").lower():
            if t.get("status", "approved") == "approved":
                return t["id"]
    raise AssertionError(f"No Announcement template: {tpls}")


def test_templates_list_has_seeded_four(admin):
    data = _templates(admin)
    assert isinstance(data, dict), f"expected dict got {type(data)}"
    assert "variables" in data and isinstance(data["variables"], list)
    tpls = data.get("templates", [])
    names = [t.get("name") for t in tpls]
    for req in ["Announcement", "Exam Alert", "Homework Alert", "Fee Reminder"]:
        assert any(req.lower() in (n or "").lower() for n in names), f"missing {req} in {names}"


def test_dry_run_whatsapp(admin):
    tid = _ann_id(admin)
    payload = {"channel": "whatsapp", "template_id": tid, "target": {"class_ids": [GRADE8]},
               "dry_run": True, "vars": {"message": "Hello", "title": "Hi"}}
    r = admin.post(f"{BASE}/api/comm/send", json=payload, timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("recipient_count") == 2, d
    assert d.get("skipped_count") == 1, d
    assert "quota_remaining" in d and "quota_after" in d, d
    assert d.get("preview") or d.get("preview_text"), d


def test_real_send_whatsapp_decrements(admin):
    tid = _ann_id(admin)
    # dry-run to get quota_remaining
    pre = admin.post(f"{BASE}/api/comm/send", json={"channel": "whatsapp", "template_id": tid,
                     "target": {"class_ids": [GRADE8]}, "dry_run": True, "vars": {"message": "x", "title": "y"}}, timeout=20).json()
    before = pre.get("quota_remaining")
    payload = {"channel": "whatsapp", "template_id": tid, "target": {"class_ids": [GRADE8]},
               "vars": {"message": "Hello live", "title": "Hi"}}
    r = admin.post(f"{BASE}/api/comm/send", json=payload, timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("ok") is True, d
    assert d.get("sent") == 2, d
    assert d.get("skipped_count") == 1, d
    # check quota decremented via another dry-run
    post = admin.post(f"{BASE}/api/comm/send", json={"channel": "whatsapp", "template_id": tid,
                      "target": {"class_ids": [GRADE8]}, "dry_run": True, "vars": {"message": "x", "title": "y"}}, timeout=20).json()
    after = post.get("quota_remaining")
    if before is not None and after is not None:
        assert before - after == 2, f"before={before} after={after}"


def test_whatsapp_free_text_blocked(admin):
    r = admin.post(f"{BASE}/api/comm/send",
                   json={"channel": "whatsapp", "body": "Hi", "target": {"class_ids": [GRADE8]}}, timeout=20)
    assert r.status_code == 400, r.text
    assert "template" in r.text.lower()


def test_sms_free_text_allowed(admin):
    r = admin.post(f"{BASE}/api/comm/send",
                   json={"channel": "sms", "body": "Hi parents live test", "target": {"class_ids": [GRADE8]}}, timeout=30)
    assert r.status_code == 200, r.text


def test_webhook_idempotent(admin):
    tid = _ann_id(admin)
    r = admin.post(f"{BASE}/api/comm/send",
                   json={"channel": "whatsapp", "template_id": tid, "target": {"class_ids": [GRADE8]},
                         "vars": {"message": "x", "title": "y"}}, timeout=30)
    assert r.status_code == 200
    d = r.json()
    mids = d.get("message_ids") or [x.get("message_id") for x in (d.get("results") or []) if x.get("message_id")]
    if not mids:
        pytest.skip(f"no message_ids: {d}")
    mid = mids[0]
    cb = {"message_id": mid, "status": "read"}
    r1 = requests.post(f"{BASE}/api/comm/webhook/twilio", json=cb, timeout=20)
    assert r1.status_code == 200, r1.text
    r2 = requests.post(f"{BASE}/api/comm/webhook/twilio", json=cb, timeout=20)
    assert r2.status_code == 200
    assert r2.json().get("idempotent") is True, r2.json()


def test_audiences(admin):
    r = admin.get(f"{BASE}/api/comm/audiences", timeout=20)
    assert r.status_code == 200
    data = r.json()
    classes = data.get("classes") if isinstance(data, dict) else data
    assert classes and len(classes) > 0
    assert any(("student_count" in c) or ("studentCount" in c) for c in classes)


def test_principal_out_of_scope(principal, admin):
    tid = _ann_id(admin)
    r = principal.post(f"{BASE}/api/comm/send",
                       json={"channel": "whatsapp", "template_id": tid, "target": {"class_ids": [GRADE8]},
                             "vars": {"message": "x"}}, timeout=20)
    assert r.status_code == 403, r.text


def test_teacher_forbidden(teacher):
    r = teacher.post(f"{BASE}/api/comm/send",
                     json={"channel": "sms", "body": "x", "target": {"class_ids": [GRADE8]}}, timeout=20)
    assert r.status_code == 403, r.text


def test_dl_token_tamper():
    r = requests.get(f"{BASE}/api/comm/dl/invalid.tampered.token", timeout=20)
    assert r.status_code == 410, r.text


def test_platform_templates_crud_pending_blocks_wa(platform, admin):
    r = platform.get(f"{BASE}/api/platform/comm/templates", timeout=20)
    assert r.status_code == 200, r.text
    payload = {"name": "TEST_LivePhase26", "channel": "both", "category": "announcement",
               "body": "Hello {{name}}", "status": "approved"}
    r = platform.post(f"{BASE}/api/platform/comm/templates", json=payload, timeout=20)
    assert r.status_code in (200, 201), r.text
    j = r.json()
    tid = j.get("id") or (j.get("template") or {}).get("id")
    assert tid, j
    try:
        r = platform.put(f"{BASE}/api/platform/comm/templates/{tid}",
                         json={"status": "pending"}, timeout=20)
        assert r.status_code == 200, r.text
        r = admin.post(f"{BASE}/api/comm/send",
                       json={"channel": "whatsapp", "template_id": tid, "target": {"class_ids": [GRADE8]},
                             "vars": {"name": "x"}}, timeout=20)
        assert r.status_code == 400, r.text
        r = admin.post(f"{BASE}/api/comm/send",
                       json={"channel": "sms", "template_id": tid, "target": {"class_ids": [GRADE8]},
                             "vars": {"name": "x"}}, timeout=30)
        assert r.status_code == 200, r.text
    finally:
        platform.delete(f"{BASE}/api/platform/comm/templates/{tid}", timeout=20)
