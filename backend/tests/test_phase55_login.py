"""Phase 55: admission-number login, per-account lockout across identifiers, admin unlock scoping.
Sunrise/TEST only; every lock created here is cleared and aarav ends unlocked with Sunrise@2026."""
import os
import pytest
import requests
from pymongo import MongoClient

BASE = os.environ.get("REACT_APP_BACKEND_URL") or open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split()[0]
API = BASE.rstrip("/") + "/api"
PW = "Sunrise@2026"
AARAV = "aarav@sunrise-demo.in"


def _env(k):
    for line in open("/app/backend/.env"):
        if line.startswith(k + "="):
            return line.split("=", 1)[1].strip().strip('"')


db = MongoClient(_env("MONGO_URL"))[_env("DB_NAME")]


def _login(ident, pw, **ctx):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"identifier": ident, "email": ident, "password": pw, **ctx})
    return s, r


def _clear(user_id):
    u = db.users.find_one({"id": user_id})
    keys = [f"user:{user_id}", u["email"].lower()]
    st = db.students.find_one({"user_id": user_id})
    if st and st.get("admission_no"):
        keys.append(f"adm:{u['institution_id']}:{st['admission_no'].strip().lower()}")
    db.login_attempts.delete_many({"identifier": {"$in": keys}})


@pytest.fixture(scope="module")
def ctx():
    u = db.users.find_one({"email": AARAV})
    st = db.students.find_one({"user_id": u["id"]})
    _clear(u["id"])
    yield {"uid": u["id"], "adm": st["admission_no"], "iid": u["institution_id"]}
    _clear(u["id"])
    _, r = _login(AARAV, PW, slug="sunrise")
    assert r.status_code == 200


def test_admission_login_branded(ctx):
    for ident in (ctx["adm"], ctx["adm"].lower(), f"  {ctx['adm']}  "):
        _, r = _login(ident, PW, slug="sunrise")
        assert r.status_code == 200 and r.json()["role"] == "student", r.text
    _, r = _login(ctx["adm"], PW, domain="sunrise-demo.in")
    assert r.status_code == 200
    _, r = _login(AARAV, PW, slug="sunrise")
    assert r.status_code == 200


def test_admission_requires_school_and_no_cross_school(ctx):
    _, r = _login(ctx["adm"], PW)
    assert r.status_code == 400 and "school's login link" in r.json()["detail"]
    _, r = _login(ctx["adm"], PW, slug="p50demo")
    assert r.status_code == 401 and r.json()["detail"] == "Invalid credentials"
    _, r = _login("NOPE-999", PW, slug="sunrise")
    assert r.status_code == 401 and r.json()["detail"] == "Invalid credentials"
    db.login_attempts.delete_many({"identifier": {"$regex": "^adm:.*:(nope-999|sps-001)$"}})
    _clear(ctx["uid"])


def test_admission_only_for_students():
    # an admin's employee/other id is never an admission identifier; a parent phone keeps its own path
    _, r = _login("admin", "x", slug="sunrise")
    assert r.status_code == 401 and r.json()["detail"] == "Invalid credentials"
    db.login_attempts.delete_many({"identifier": {"$regex": ":admin$"}})


def test_lockout_shared_across_identifiers_and_unlock(ctx):
    _clear(ctx["uid"])
    for i in range(5):
        ident = AARAV if i % 2 == 0 else ctx["adm"]
        _, r = _login(ident, "wrong-pass", slug="sunrise")
        assert r.status_code == 401
    for ident in (AARAV, ctx["adm"]):
        _, r = _login(ident, PW, slug="sunrise")
        assert r.status_code == 429, ident
    admin, r = _login("admin@sunrise-demo.in", PW, slug="sunrise")
    assert r.status_code == 200
    st = admin.get(f"{API}/account-locks/{ctx['uid']}").json()
    assert st["locked"] and st["locked_until"] and st["last_failed_at"]
    assert any(l["user_id"] == ctx["uid"] for l in admin.get(f"{API}/account-locks").json()["locks"])
    # student-record id resolves to the same account
    sid = db.students.find_one({"user_id": ctx["uid"]})["id"]
    assert admin.get(f"{API}/account-locks/{sid}").json()["locked"]
    r = admin.post(f"{API}/account-locks/{ctx['uid']}/unlock")
    assert r.status_code == 200 and r.json()["ok"]
    assert db.audit_logs.find_one({"action": "unlock_account", "entity_id": ctx["uid"]})
    assert db.audit_logs.find_one({"action": "account_locked", "entity_id": ctx["uid"]})
    assert not admin.get(f"{API}/account-locks/{ctx['uid']}").json()["locked"]
    _, r = _login(ctx["adm"], PW, slug="sunrise")
    assert r.status_code == 200


def test_unlock_scoping(ctx):
    other_admin, r = _login("admin@feesdemo.test", "admin123", slug="p50demo")
    assert r.status_code == 200
    assert other_admin.get(f"{API}/account-locks/{ctx['uid']}").status_code == 403
    assert other_admin.post(f"{API}/account-locks/{ctx['uid']}/unlock").status_code == 403
    teacher, r = _login("lakshmi@sunrise-demo.in", PW, slug="sunrise")
    assert r.status_code == 200
    assert teacher.post(f"{API}/account-locks/{ctx['uid']}/unlock").status_code == 403
    # LP-only principal at TEST school cannot unlock a Grade 8 student there
    lp, r = _login("principal.lp@feesdemo.test", "teach123", slug="p50demo")
    assert r.status_code == 200
    g8 = db.students.find_one({"institution_id": db.institutions.find_one({"slug": "p50demo"})["id"],
                               "class_name": {"$regex": "8"}, "user_id": {"$nin": [None, ""]}})
    if g8:
        assert lp.post(f"{API}/account-locks/{g8['user_id']}/unlock").status_code == 403
    # platform admin: school admins only
    pa, r = _login("lnmopvt@gmail.com", "Lnmo@2026!")
    assert r.status_code == 200
    assert pa.post(f"{API}/account-locks/{ctx['uid']}/unlock").status_code == 403
    sadmin = db.users.find_one({"email": "admin@sunrise-demo.in"})
    assert pa.post(f"{API}/account-locks/{sadmin['id']}/unlock").status_code == 200
