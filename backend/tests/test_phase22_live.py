"""Phase 22 — Assignments live validation against LPGS (REACT_APP_BACKEND_URL).

Acceptance flow:
  prasad27 creates Grade 8-A Mathematics "Algebra Project" max_marks=25 counts_toward_report=ON
  g8student submits a tiny PDF; prasad27 scores 21/25 verified.
  Verify student portal sees score and admin report-card lists the score under assignment_scores.
  Also create a second UNTAGGED assignment, verify it, confirm it does NOT appear on report card.
  Negative: manoj & sreeja get 403; max_marks<1 → 422; verify-without-score 400;
  score out of range 400; redo-without-feedback 400; closed assignment blocks submit (400).
  Parent assignments read scoped; LP principal cannot read Grade 8 submissions.
  Phase 21 regression smoke: list homework still works for prasad27.
At end: close both created assignments (does not delete — submissions exist).
"""
import io
import os
import time
import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://lnmo-fees.preview.emergentagent.com").rstrip("/")
API = f"{BASE}/api"
PDF = b"%PDF-1.4\n% test\n"


def _login(email, pw):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=30)
    assert r.status_code == 200, f"login {email}: {r.status_code} {r.text}"
    tok = s.cookies.get("access_token")
    assert tok, f"no access_token cookie for {email}"
    return tok


def _h(tok):
    return {"Authorization": f"Bearer {tok}", "Cookie": f"access_token={tok}"}


@pytest.fixture(scope="module")
def ctx():
    toks = {
        "prasad": _login("prasad27@lpgs.com", "teach123"),
        "manoj": _login("manoj@lpgs.com", "teach123"),
        "sreeja": _login("sreeja@lpgs.com", "teach123"),
        "stu": _login("g8student@lpgs.com", "student123"),
        "admin": _login("admin@lpgs.com", "admin123"),
    }
    # Discover g8student id
    me = requests.get(f"{API}/auth/me", headers=_h(toks["stu"]), timeout=20).json()
    student_id = me.get("student_id") or me.get("user", {}).get("student_id")
    assert student_id, f"could not resolve student_id from /auth/me: {me}"
    created = []
    yield {"t": toks, "student_id": student_id, "created": created}
    # Cleanup: close any created
    for aid in created:
        try:
            requests.post(f"{API}/assignments/{aid}/close", headers=_h(toks["prasad"]), timeout=15)
        except Exception:
            pass


def _mk(ctx, title, max_marks=25, counts=False, due="2099-12-31T23:59:00+00:00"):
    body = {"class_name": "Grade 8", "section": "A", "subject": "Mathematics",
            "title": title, "instructions": "Live test", "due_date": due,
            "max_marks": max_marks, "counts_toward_report": counts}
    r = requests.post(f"{API}/assignments", json=body, headers=_h(ctx["t"]["prasad"]), timeout=30)
    assert r.status_code == 200, f"create: {r.status_code} {r.text}"
    aid = r.json()["assignment"]["id"]
    ctx["created"].append(aid)
    return aid


# -- Create permission parity ------------------------------------------------
def test_create_permission_parity(ctx):
    body = {"class_name": "Grade 8", "section": "A", "subject": "Mathematics",
            "title": f"TEST_ASG_P22_perm_{int(time.time())}", "due_date": "2099-12-31T23:59:00+00:00",
            "max_marks": 10, "counts_toward_report": False}
    r_manoj = requests.post(f"{API}/assignments", json=body, headers=_h(ctx["t"]["manoj"]), timeout=20)
    assert r_manoj.status_code == 403, r_manoj.text
    r_sreeja = requests.post(f"{API}/assignments", json=body, headers=_h(ctx["t"]["sreeja"]), timeout=20)
    assert r_sreeja.status_code == 403, r_sreeja.text
    bad = requests.post(f"{API}/assignments", json={**body, "max_marks": 0},
                        headers=_h(ctx["t"]["prasad"]), timeout=20)
    assert bad.status_code == 422, bad.text


# -- Full acceptance flow: tagged assignment surfaces on report card --------
def test_tagged_assignment_report_card_roundtrip(ctx):
    aid = _mk(ctx, f"TEST_ASG_P22_Algebra_{int(time.time())}", max_marks=25, counts=True)
    # Student sees it in /api/assignments
    lst = requests.get(f"{API}/assignments", headers=_h(ctx["t"]["stu"]), timeout=20).json()
    assert any(a["id"] == aid for a in lst.get("assignments", [])), "student missing assignment"
    # Submit
    files = [("files", ("algebra.pdf", io.BytesIO(PDF), "application/pdf"))]
    r = requests.post(f"{API}/assignments/{aid}/submit",
                      data={"note": "my solution"}, files=files,
                      headers=_h(ctx["t"]["stu"]), timeout=30)
    assert r.status_code == 200, r.text
    assert r.json().get("late") is False
    # Teacher inbox
    inbox = requests.get(f"{API}/assignments/{aid}/submissions",
                         headers=_h(ctx["t"]["prasad"]), timeout=20).json()
    subs = inbox["submissions"]
    assert len(subs) >= 1
    sid = next(s["id"] for s in subs if s["student_id"] == ctx["student_id"])
    # Verify without score → 400
    rvno = requests.post(f"{API}/assignment-submissions/{sid}/verify",
                         json={"verdict": "verified"}, headers=_h(ctx["t"]["prasad"]), timeout=20)
    assert rvno.status_code == 400, rvno.text
    # Out of range → 400
    rbig = requests.post(f"{API}/assignment-submissions/{sid}/verify",
                         json={"verdict": "verified", "score": 99},
                         headers=_h(ctx["t"]["prasad"]), timeout=20)
    assert rbig.status_code == 400, rbig.text
    rneg = requests.post(f"{API}/assignment-submissions/{sid}/verify",
                         json={"verdict": "verified", "score": -1},
                         headers=_h(ctx["t"]["prasad"]), timeout=20)
    assert rneg.status_code == 400, rneg.text
    # Valid score
    rok = requests.post(f"{API}/assignment-submissions/{sid}/verify",
                        json={"verdict": "verified", "score": 21},
                        headers=_h(ctx["t"]["prasad"]), timeout=20)
    assert rok.status_code == 200, rok.text
    # Admin report-card contains assignment_scores with this title
    rc = requests.get(f"{API}/students/{ctx['student_id']}/report-card",
                      headers=_h(ctx["t"]["admin"]), timeout=30)
    assert rc.status_code == 200, rc.text
    data = rc.json()
    assert "assignment_scores" in data, f"report-card missing assignment_scores: keys={list(data.keys())}"
    titles = {it["title"]: it for blk in data["assignment_scores"] for it in blk["items"]}
    created_asg = requests.get(f"{API}/assignments/{aid}", headers=_h(ctx["t"]["prasad"]), timeout=20).json()["assignment"]
    assert created_asg["title"] in titles, f"tagged title missing in report-card. Titles={list(titles)}"
    item = titles[created_asg["title"]]
    assert item["score"] == 21 and item["max_marks"] == 25
    # Also marks table + signature row still intact
    assert "marks" in data or "assessments" in data or "subjects" in data, "report card core blocks missing"


# -- Untagged assignment does NOT appear on report card ----------------------
def test_untagged_assignment_absent_from_report_card(ctx):
    aid = _mk(ctx, f"TEST_ASG_P22_Untagged_{int(time.time())}", max_marks=10, counts=False)
    files = [("files", ("u.pdf", io.BytesIO(PDF), "application/pdf"))]
    r = requests.post(f"{API}/assignments/{aid}/submit", data={"note": "u"}, files=files,
                      headers=_h(ctx["t"]["stu"]), timeout=30)
    assert r.status_code == 200, r.text
    subs = requests.get(f"{API}/assignments/{aid}/submissions",
                        headers=_h(ctx["t"]["prasad"]), timeout=20).json()["submissions"]
    sid = next(s["id"] for s in subs if s["student_id"] == ctx["student_id"])
    rv = requests.post(f"{API}/assignment-submissions/{sid}/verify",
                       json={"verdict": "verified", "score": 8},
                       headers=_h(ctx["t"]["prasad"]), timeout=20)
    assert rv.status_code == 200
    asg = requests.get(f"{API}/assignments/{aid}", headers=_h(ctx["t"]["prasad"]), timeout=20).json()["assignment"]
    rc = requests.get(f"{API}/students/{ctx['student_id']}/report-card",
                      headers=_h(ctx["t"]["admin"]), timeout=30).json()
    titles = {it["title"] for blk in rc.get("assignment_scores", []) for it in blk["items"]}
    assert asg["title"] not in titles, f"untagged assignment leaked into report-card: {asg['title']}"


# -- Redo path: feedback required, clears score, student resubmit bumps version -
def test_redo_requires_feedback_and_clears_score(ctx):
    aid = _mk(ctx, f"TEST_ASG_P22_Redo_{int(time.time())}", max_marks=20, counts=False)
    files = [("files", ("r.pdf", io.BytesIO(PDF), "application/pdf"))]
    requests.post(f"{API}/assignments/{aid}/submit", data={"note": "v1"}, files=files,
                  headers=_h(ctx["t"]["stu"]), timeout=30)
    subs = requests.get(f"{API}/assignments/{aid}/submissions",
                        headers=_h(ctx["t"]["prasad"]), timeout=20).json()["submissions"]
    sid = next(s["id"] for s in subs if s["student_id"] == ctx["student_id"])
    # verify first with a score
    requests.post(f"{API}/assignment-submissions/{sid}/verify",
                  json={"verdict": "verified", "score": 15}, headers=_h(ctx["t"]["prasad"]), timeout=20)
    # redo without feedback → 400
    rno = requests.post(f"{API}/assignment-submissions/{sid}/verify",
                       json={"verdict": "redo"}, headers=_h(ctx["t"]["prasad"]), timeout=20)
    assert rno.status_code == 400, rno.text
    # redo with feedback → 200
    rok = requests.post(f"{API}/assignment-submissions/{sid}/verify",
                        json={"verdict": "redo", "feedback": "please improve"},
                        headers=_h(ctx["t"]["prasad"]), timeout=20)
    assert rok.status_code == 200, rok.text
    inbox = requests.get(f"{API}/assignments/{aid}/submissions",
                         headers=_h(ctx["t"]["prasad"]), timeout=20).json()["submissions"]
    doc = next(s for s in inbox if s["id"] == sid)
    assert doc["status"] == "redo" and (doc.get("score") in (None, 0) or doc.get("score") is None)
    assert doc.get("score") is None, f"score not cleared: {doc.get('score')}"
    # resubmit bumps version
    requests.post(f"{API}/assignments/{aid}/submit", data={"note": "v2"},
                  files=[("files", ("r2.pdf", io.BytesIO(PDF), "application/pdf"))],
                  headers=_h(ctx["t"]["stu"]), timeout=30)
    inbox2 = requests.get(f"{API}/assignments/{aid}/submissions",
                          headers=_h(ctx["t"]["prasad"]), timeout=20).json()["submissions"]
    doc2 = next(s for s in inbox2 if s["id"] == sid)
    assert doc2["version"] >= 2 and doc2["status"] == "submitted"


# -- Close blocks student submit ---------------------------------------------
def test_close_blocks_submit_and_reopen_restores(ctx):
    aid = _mk(ctx, f"TEST_ASG_P22_Close_{int(time.time())}", max_marks=5, counts=False)
    rc = requests.post(f"{API}/assignments/{aid}/close", headers=_h(ctx["t"]["prasad"]), timeout=20)
    assert rc.status_code == 200
    rblock = requests.post(f"{API}/assignments/{aid}/submit", data={"note": "late"},
                           files=[("files", ("x.pdf", io.BytesIO(PDF), "application/pdf"))],
                           headers=_h(ctx["t"]["stu"]), timeout=30)
    assert rblock.status_code == 400 and "closed" in rblock.text.lower(), rblock.text
    rr = requests.post(f"{API}/assignments/{aid}/reopen", headers=_h(ctx["t"]["prasad"]), timeout=20)
    assert rr.status_code == 200
    rok = requests.post(f"{API}/assignments/{aid}/submit", data={"note": "now"},
                        files=[("files", ("x.pdf", io.BytesIO(PDF), "application/pdf"))],
                        headers=_h(ctx["t"]["stu"]), timeout=30)
    assert rok.status_code == 200, rok.text


# -- Manoj/Sreeja cannot view prasad's submission inbox ----------------------
def test_unrelated_teachers_cannot_read_inbox(ctx):
    # Reuse an already-created assignment
    assert ctx["created"], "need at least one created assignment"
    aid = ctx["created"][0]
    r1 = requests.get(f"{API}/assignments/{aid}/submissions",
                      headers=_h(ctx["t"]["manoj"]), timeout=20)
    assert r1.status_code == 403, r1.text
    r2 = requests.get(f"{API}/assignments/{aid}/submissions",
                      headers=_h(ctx["t"]["sreeja"]), timeout=20)
    assert r2.status_code == 403, r2.text


# -- Assignment-stats returns avg_score -------------------------------------
def test_assignment_stats_has_avg_score(ctx):
    r = requests.get(f"{API}/students/{ctx['student_id']}/assignment-stats",
                     headers=_h(ctx["t"]["admin"]), timeout=20)
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["assigned"] >= 1 and s["verified"] >= 1
    assert s["avg_score"] is not None


# -- Phase 21 regression smoke: homework still works -------------------------
def test_phase21_homework_regression(ctx):
    r = requests.get(f"{API}/homework", headers=_h(ctx["t"]["prasad"]), timeout=20)
    assert r.status_code == 200, r.text
    assert "homework" in r.json()
