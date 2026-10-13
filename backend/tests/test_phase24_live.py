"""Phase 24 live test against public backend URL."""
import os
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL") or open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split("\n")[0].strip()
CLASS_ID = "6fc07602-c1b8-437c-bed4-afd82c52a5d7"
DOMAIN = "lpgs.com"


def _login(email, password):
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password, "domain": DOMAIN}, timeout=20)
    assert r.status_code == 200, f"login {email} failed: {r.status_code} {r.text}"
    tok = r.cookies.get("access_token") or r.json().get("access_token") or r.json().get("token")
    assert tok, f"no token in response: {r.json()}"
    return tok


def _get_month(token, month="2026-01"):
    return requests.get(
        f"{BASE_URL}/api/classes/{CLASS_ID}/monthly-report",
        params={"month": month},
        headers={"Authorization": f"Bearer {token}"},
        timeout=90,
    )


def test_admin_200():
    tok = _login("admin@lpgs.com", "admin123")
    r = _get_month(tok)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "sections" in data
    assert isinstance(data["sections"], list)
    assert len(data["sections"]) >= 1
    # verify signer block present
    assert "signers" in data or "principal" in data or "institution" in data
    sec = data["sections"][0]
    assert "section" in sec and "class_teacher" in sec and "students" in sec
    if sec["students"]:
        stu = sec["students"][0]
        assert "homework" in stu and "assignments" in stu
        for k in ["assigned","submitted","late","verified","redo","pending"]:
            assert k in stu["homework"], f"missing hw.{k}"
        for k in ["assigned","submitted","late","verified","avg_score","scored_count"]:
            assert k in stu["assignments"], f"missing asg.{k}"
    print("ADMIN OK sections=", len(data["sections"]))


def test_subject_teacher_403():
    tok = _login("prasad27@lpgs.com", "teach123")
    r = _get_month(tok)
    assert r.status_code == 403, f"expected 403 got {r.status_code}: {r.text}"


def test_out_of_scope_principal_403():
    tok = _login("testprincipal@lpgs.com", "teach123")
    r = _get_month(tok)
    assert r.status_code == 403, f"expected 403 got {r.status_code}: {r.text}"


def test_empty_month_clean_zeros():
    tok = _login("admin@lpgs.com", "admin123")
    r = _get_month(tok, month="2000-01")
    assert r.status_code == 200
    data = r.json()
    for sec in data["sections"]:
        for stu in sec["students"]:
            assert stu["homework"]["assigned"] == 0
            assert stu["assignments"]["assigned"] == 0
