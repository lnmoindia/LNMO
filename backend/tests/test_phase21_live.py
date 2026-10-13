"""Phase 21 live tests against running services (LPGS) end-to-end.

Flow: prasad (subject teacher Grade 8 Maths) -> create & manage HW;
manoj & sreeja (unrelated) -> 403 on create;
g8student -> submit -> redo cycle -> re-submit -> verify;
close/reopen; stats; notifications.
"""
import os
import time
import io
import pytest
import requests
from datetime import datetime, timezone, timedelta

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://lnmo-fees.preview.emergentagent.com").rstrip("/")
API = BASE + "/api"

PRASAD = ("prasad27@lpgs.com", "teach123")
MANOJ = ("manoj@lpgs.com", "teach123")
SREEJA = ("sreeja@lpgs.com", "teach123")
STU = ("g8student@lpgs.com", "student123")
ADMIN = ("admin@lpgs.com", "admin123")


def login(email, pw):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=30)
    assert r.status_code == 200, f"login {email}: {r.status_code} {r.text}"
    tok = r.json().get("access_token")
    if tok:
        s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


@pytest.fixture(scope="module")
def ctx():
    sessions = {
        "prasad": login(*PRASAD),
        "manoj": login(*MANOJ),
        "sreeja": login(*SREEJA),
        "stu": login(*STU),
        "admin": login(*ADMIN),
    }
    r = sessions["prasad"].get(f"{API}/teacher/teaching-options", timeout=30)
    assert r.status_code == 200, r.text
    opts = r.json().get("options", [])
    target = None
    for o in opts:
        if "8" in o.get("class_name", "") and o.get("section") == "A" and "math" in o.get("subject", "").lower():
            target = o
            break
    assert target, f"Grade 8-A Math option missing: {opts}"
    print("Target:", target)
    data = {"sessions": sessions, "opt": target, "created_ids": []}
    yield data
    for hid in data["created_ids"]:
        rr = sessions["prasad"].delete(f"{API}/homework/{hid}", timeout=30)
        if rr.status_code not in (200, 204):
            sessions["prasad"].post(f"{API}/homework/{hid}/close", timeout=30)


def _payload(opt, title):
    due = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    return {
        "class_name": opt["class_name"],
        "section": opt["section"],
        "subject": opt["subject"],
        "title": title,
        "instructions": "automated phase21 live test",
        "due_date": due,
    }


def test_create_prasad_subject_teacher_ok(ctx):
    pl = _payload(ctx["opt"], f"TEST_HW_P21_{int(time.time())}")
    r = ctx["sessions"]["prasad"].post(f"{API}/homework", json=pl, timeout=30)
    assert r.status_code in (200, 201), r.text
    hid = r.json()["homework"]["id"]
    ctx["created_ids"].append(hid)
    ctx["hw_id"] = hid
    print("created hw", hid)


def test_create_blocked_unrelated_hs_teacher_manoj(ctx):
    pl = _payload(ctx["opt"], "TEST_HW_P21_manoj_denied")
    r = ctx["sessions"]["manoj"].post(f"{API}/homework", json=pl, timeout=30)
    assert r.status_code == 403, f"expected 403, got {r.status_code} {r.text}"


def test_create_blocked_unrelated_lp_teacher_sreeja(ctx):
    pl = _payload(ctx["opt"], "TEST_HW_P21_sreeja_denied")
    r = ctx["sessions"]["sreeja"].post(f"{API}/homework", json=pl, timeout=30)
    assert r.status_code == 403, f"expected 403, got {r.status_code} {r.text}"


def test_student_sees_homework_in_list(ctx):
    r = ctx["sessions"]["stu"].get(f"{API}/homework", timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    items = body if isinstance(body, list) else body.get("items") or body.get("homework") or []
    ids = [it.get("id") for it in items]
    assert ctx["hw_id"] in ids, f"not in {ids[:5]} (body keys={list(body)[:5] if isinstance(body, dict) else 'list'})"


def test_student_submit_file_and_note(ctx):
    pdf = b"%PDF-1.4\n%TEST live submission v1\n"
    files = [("files", ("hw.pdf", io.BytesIO(pdf), "application/pdf"))]
    data = {"note": "TEST live submission note v1"}
    r = ctx["sessions"]["stu"].post(f"{API}/homework/{ctx['hw_id']}/submit", files=files, data=data, timeout=60)
    assert r.status_code in (200, 201), r.text
    # /submit returns {message, late}; fetch the inbox to get the submission id
    inbox = ctx["sessions"]["prasad"].get(f"{API}/homework/{ctx['hw_id']}/submissions", timeout=30).json()
    subs = inbox.get("submissions") if isinstance(inbox, dict) else inbox
    assert subs, inbox
    ctx["submission_id"] = subs[0]["id"]
    assert subs[0].get("version", 1) >= 1, subs[0]


def test_teacher_sees_submission_in_inbox(ctx):
    r = ctx["sessions"]["prasad"].get(f"{API}/homework/{ctx['hw_id']}/submissions", timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    subs = body.get("submissions") if isinstance(body, dict) else body
    sids = [s.get("id") for s in subs]
    assert ctx["submission_id"] in sids


def test_unrelated_teacher_cannot_view_submissions(ctx):
    r = ctx["sessions"]["manoj"].get(f"{API}/homework/{ctx['hw_id']}/submissions", timeout=30)
    assert r.status_code == 403, r.text


def test_redo_requires_feedback(ctx):
    r = ctx["sessions"]["prasad"].post(
        f"{API}/submissions/{ctx['submission_id']}/verify", json={"verdict": "redo"}, timeout=30)
    assert r.status_code == 400, f"got {r.status_code} {r.text}"


def test_redo_with_feedback_then_resubmit_bumps_version(ctx):
    r = ctx["sessions"]["prasad"].post(
        f"{API}/submissions/{ctx['submission_id']}/verify",
        json={"verdict": "redo", "feedback": "please redo neatly"}, timeout=30)
    assert r.status_code == 200, r.text
    pdf = b"%PDF-1.4\n%TEST v2\n"
    files = [("files", ("hw2.pdf", io.BytesIO(pdf), "application/pdf"))]
    r = ctx["sessions"]["stu"].post(f"{API}/homework/{ctx['hw_id']}/submit", files=files, data={"note": "v2"}, timeout=60)
    assert r.status_code in (200, 201), r.text
    inbox = ctx["sessions"]["prasad"].get(f"{API}/homework/{ctx['hw_id']}/submissions", timeout=30).json()
    subs = inbox.get("submissions") if isinstance(inbox, dict) else inbox
    this = next((s for s in subs if s["id"] == ctx["submission_id"]), None)
    assert this, inbox
    assert this.get("version", 1) >= 2, this
    assert (this.get("status") or "").lower() in ("submitted", "pending"), this


def test_teacher_verifies_final(ctx):
    r = ctx["sessions"]["prasad"].post(
        f"{API}/submissions/{ctx['submission_id']}/verify", json={"verdict": "verified"}, timeout=30)
    assert r.status_code == 200, r.text


def test_close_blocks_submission_and_reopen_works(ctx):
    pl = _payload(ctx["opt"], f"TEST_HW_P21_close_{int(time.time())}")
    r = ctx["sessions"]["prasad"].post(f"{API}/homework", json=pl, timeout=30)
    assert r.status_code in (200, 201), r.text
    hid = r.json()["homework"]["id"]
    ctx["created_ids"].append(hid)
    r = ctx["sessions"]["prasad"].post(f"{API}/homework/{hid}/close", timeout=30)
    assert r.status_code == 200, r.text
    files = [("files", ("x.pdf", io.BytesIO(b"%PDF-1.4 x"), "application/pdf"))]
    r = ctx["sessions"]["stu"].post(f"{API}/homework/{hid}/submit", files=files, data={"note": "late"}, timeout=30)
    assert r.status_code == 400, f"got {r.status_code} {r.text}"
    r = ctx["sessions"]["prasad"].post(f"{API}/homework/{hid}/reopen", timeout=30)
    assert r.status_code == 200, r.text


def test_student_homework_stats(ctx):
    me = ctx["sessions"]["stu"].get(f"{API}/auth/me", timeout=30).json()
    sid = me.get("student_id") or (me.get("user") or {}).get("student_id") or me.get("id")
    if not sid:
        pytest.skip(f"no student_id in /auth/me: {me}")
    r = ctx["sessions"]["stu"].get(f"{API}/students/{sid}/homework-stats", timeout=30)
    assert r.status_code == 200, r.text
    stats = r.json()
    for k in ("assigned", "submitted", "verified"):
        assert k in stats, stats


def test_student_bell_has_new_homework(ctx):
    r = ctx["sessions"]["stu"].get(f"{API}/notifications", timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    items = body if isinstance(body, list) else body.get("items") or body.get("notifications") or []
    assert any("homework" in str(it).lower() for it in items), f"no homework bell: {items[:3]}"


def test_teacher_bell_has_submission(ctx):
    r = ctx["sessions"]["prasad"].get(f"{API}/notifications", timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    items = body if isinstance(body, list) else body.get("items") or body.get("notifications") or []
    assert any(("submission" in str(it).lower() or "homework" in str(it).lower()) for it in items), f"no bell: {items[:3]}"
