"""Live LPGS Phase 31 authorization & flow checks via public URL."""
import os
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://lnmo-fees.preview.emergentagent.com").rstrip("/")
CUR_ID = "a5dcc0c1-f7b1-4a9d-acad-db6dfa7d1381"


def _login(email, password):
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login {email}: {r.status_code} {r.text}"
    return s


def test_admin_detail_and_comments():
    s = _login("admin@lpgs.com", "admin123")
    r = s.get(f"{BASE}/api/ai/curriculum/{CUR_ID}", timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("can_review") is True
    assert "comments" in d and "open_comment_count" in d
    assert d.get("can_comment") is True

    r = s.get(f"{BASE}/api/ai/curriculum/{CUR_ID}/comments", timeout=30)
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, dict) and "comments" in body and isinstance(body["comments"], list)


def test_teacher_owner_access():
    s = _login("prasad27@lpgs.com", "teach123")
    r = s.get(f"{BASE}/api/ai/curriculum/{CUR_ID}", timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("can_contribute") is True
    r2 = s.get(f"{BASE}/api/ai/curriculum/{CUR_ID}/comments", timeout=30)
    assert r2.status_code == 200


def test_unrelated_teacher_forbidden():
    s = _login("manoj@lpgs.com", "teach123")
    r = s.get(f"{BASE}/api/ai/curriculum/{CUR_ID}/comments", timeout=30)
    assert r.status_code == 403, f"expected 403, got {r.status_code} body={r.text}"
    r2 = s.post(
        f"{BASE}/api/ai/curriculum/{CUR_ID}/items",
        data={"item_type": "chapter", "chapter": "QA should not create"},
        timeout=30,
    )
    assert r2.status_code == 403, f"expected 403, got {r2.status_code} body={r2.text}"


def test_teacher_cannot_post_review_comment():
    s = _login("prasad27@lpgs.com", "teach123")
    r = s.post(
        f"{BASE}/api/ai/curriculum/{CUR_ID}/comments",
        json={"text": "teacher trying to review"},
        timeout=30,
    )
    assert r.status_code == 403, f"expected 403 got {r.status_code} body={r.text}"


def test_admin_comment_notify_teacher_resolve_loop():
    admin = _login("admin@lpgs.com", "admin123")
    teacher = _login("prasad27@lpgs.com", "teach123")

    body_text = "QA phase31 live comment (automated)"
    r = admin.post(
        f"{BASE}/api/ai/curriculum/{CUR_ID}/comments",
        json={"text": body_text},
        timeout=30,
    )
    assert r.status_code in (200, 201), r.text
    j = r.json()
    cid = (j.get("comment") or {}).get("id") or j.get("id")
    assert cid, f"no comment id in response: {j}"

    r2 = teacher.get(f"{BASE}/api/notifications", timeout=30)
    assert r2.status_code == 200
    jj = r2.json()
    notifs = jj.get("notifications") if isinstance(jj, dict) else jj
    assert any(n.get("type") == "ai_curriculum_comment" for n in notifs), \
        f"teacher missing comment bell. types={[n.get('type') for n in notifs[:10]]}"

    r3 = teacher.post(
        f"{BASE}/api/ai/comments/{cid}/resolve",
        json={"reply": "QA auto-reply from teacher"},
        timeout=30,
    )
    assert r3.status_code in (200, 204), r3.text

    r4 = admin.get(f"{BASE}/api/notifications", timeout=30)
    assert r4.status_code == 200
    jj2 = r4.json()
    notifs2 = jj2.get("notifications") if isinstance(jj2, dict) else jj2
    assert any(n.get("type") == "ai_comment_resolved" for n in notifs2), \
        f"admin missing resolve bell. types={[n.get('type') for n in notifs2[:10]]}"


def test_pending_curricula_comment_badge_field():
    s = _login("admin@lpgs.com", "admin123")
    r = s.get(f"{BASE}/api/ai/approvals/curricula", timeout=30)
    assert r.status_code == 200
    data = r.json()
    items = data if isinstance(data, list) else data.get("items", [])
    for it in items:
        assert "open_comment_count" in it, f"missing open_comment_count in {it}"
