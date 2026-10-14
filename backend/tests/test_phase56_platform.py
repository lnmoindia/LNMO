"""Phase 56: platform institution console, admin password reset (real Resend send) and login-email change.
Uses a throwaway school whose admins use Resend's delivered+*@resend.dev test inbox."""
import hashlib
import secrets
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests
from pymongo import MongoClient

API = open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split()[0].rstrip("/") + "/api"


def _env(k):
    for line in open("/app/backend/.env"):
        if line.startswith(k + "="):
            return line.split("=", 1)[1].strip().strip('"')


db = MongoClient(_env("MONGO_URL"))[_env("DB_NAME")]
SUN = "e8f49f14-df1b-41e1-ac30-499cdc81522c"
TAG = uuid.uuid4().hex[:6]
A_EMAIL, B_EMAIL = f"delivered+p56a{TAG}@resend.dev", f"delivered+p56b{TAG}@resend.dev"
PW1, PW2 = "Temp@1234x", "NewPass@2026"


def _login(ident, pw, **kw):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"identifier": ident, "email": ident, "password": pw, **kw})
    return s, r


@pytest.fixture(scope="module")
def ctx():
    pa, r = _login("lnmopvt@gmail.com", "Lnmo@2026!")
    assert r.status_code == 200
    r = pa.post(f"{API}/res/institutions", json={"name": f"P56 Throwaway {TAG}", "code": f"P56{TAG}".upper(), "domain": f"p56{TAG}.test",
                                                 "city": "Testville", "admin_name": "Throwaway Admin", "admin_email": A_EMAIL, "admin_password": PW1})
    assert r.status_code in (200, 201), r.text
    iid = r.json()["id"]
    db.institutions.update_one({"id": iid}, {"$set": {"is_demo": True}})
    admin = db.users.find_one({"institution_id": iid, "role": "institution_admin"})
    yield {"pa": pa, "iid": iid, "uid": admin["id"]}
    db.institutions.update_one({"id": iid}, {"$set": {"status": "inactive"}})


def test_non_platform_forbidden(ctx):
    s, r = _login("admin@sunrise-demo.in", "Sunrise@2026", slug="sunrise")
    assert r.status_code == 200
    iid, uid = ctx["iid"], ctx["uid"]
    for m, p, body in [("get", "/platform/summary", None), ("get", "/platform/institutions-list", None),
                       ("get", f"/platform/institutions/{iid}/overview", None), ("get", f"/platform/institutions/{iid}/analytics", None),
                       ("get", f"/platform/institutions/{iid}/plan", None), ("put", f"/platform/institutions/{iid}/plan", {}),
                       ("get", f"/platform/institutions/{iid}/admins", None), ("get", f"/platform/institutions/{iid}/activity", None),
                       ("post", f"/platform/institutions/{iid}/admins/{uid}/password-reset", None),
                       ("post", f"/platform/institutions/{iid}/admins/{uid}/email", {"email": "x@y.test"})]:
        r = getattr(s, m)(f"{API}{p}", json=body) if body is not None else getattr(s, m)(f"{API}{p}")
        assert r.status_code == 403, (p, r.status_code)
    assert requests.get(f"{API}/platform/summary").status_code == 401


def test_console_reads(ctx):
    pa = ctx["pa"]
    s = pa.get(f"{API}/platform/summary").json()
    assert s["schools"] >= 5 and len(s["logins_trend"]) == 30
    lst = pa.get(f"{API}/platform/institutions-list").json()["items"]
    sun = next(i for i in lst if i["id"] == SUN)
    assert sun["students"] == db.students.count_documents({"institution_id": SUN})
    ov = pa.get(f"{API}/platform/institutions/{SUN}/overview").json()
    assert ov["login_key"] == "sunrise" and ov["setup"]["total"] == 12 and ov["academic_year"]["name"]
    an = pa.get(f"{API}/platform/institutions/{SUN}/analytics").json()
    assert an["modules"]["storage_bytes"] is None and an["modules"]["ai_tokens"] is None
    assert an["people"]["teachers"] == db.users.count_documents({"institution_id": SUN, "role": "teacher"})
    assert pa.get(f"{API}/platform/institutions/nope/overview").status_code == 404


def test_plan_update_audited(ctx):
    pa, iid = ctx["pa"], ctx["iid"]
    starter = db.plans.find_one({"code": "STARTER"})
    assert pa.put(f"{API}/platform/institutions/{iid}/plan", json={"plan_id": "bogus"}).status_code == 400
    r = pa.put(f"{API}/platform/institutions/{iid}/plan", json={"plan_id": starter["id"], "status": "active", "expires_at": "2027-03-31",
                                                                "max_students": 50, "whatsapp_limit": 200, "sms_limit": 20, "ai_messages_month": 500})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["plan"]["id"] == starter["id"] and d["limits"]["students"] == 50 and d["limits"]["whatsapp"] == 200 and d["expires_at"] == "2027-03-31"
    assert db.audit_logs.find_one({"action": "platform_plan_update", "entity_id": iid})
    acts = pa.get(f"{API}/platform/institutions/{iid}/activity", params={"platform_only": True}).json()["items"]
    assert any(a["action"] == "platform_plan_update" for a in acts)


def _known_token(uid, iid, hours=24):
    tok = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    db.password_resets.update_many({"user_id": uid, "used_at": None, "invalidated_at": None}, {"$set": {"invalidated_at": now.isoformat()}})
    db.password_resets.insert_one({"id": str(uuid.uuid4()), "user_id": uid, "institution_id": iid, "token_hash": hashlib.sha256(tok.encode()).hexdigest(),
                                   "created_at": now.isoformat(), "expires_at": (now + timedelta(hours=hours)).isoformat(),
                                   "created_by": "pytest", "used_at": None, "invalidated_at": None})
    return tok


def test_password_reset_flow(ctx):
    pa, iid, uid = ctx["pa"], ctx["iid"], ctx["uid"]
    old_sess, r = _login(A_EMAIL, PW1)
    assert r.status_code == 200 and old_sess.get(f"{API}/auth/me").status_code == 200
    r = pa.post(f"{API}/platform/institutions/{iid}/admins/{uid}/password-reset")
    assert r.status_code == 200, r.text
    first = r.json()
    assert first["message_id"] and first["sent_to"] == A_EMAIL
    doc1 = db.password_resets.find_one({"message_id": first["message_id"]})
    assert doc1 and "token" not in doc1 and len(doc1["token_hash"]) == 64
    time.sleep(3)  # stay under the provider's burst limit
    r = pa.post(f"{API}/platform/institutions/{iid}/admins/{uid}/password-reset")
    assert r.status_code == 200
    assert db.password_resets.find_one({"id": doc1["id"]})["invalidated_at"]  # new link invalidates the old
    assert db.audit_logs.find_one({"action": "password_reset_sent", "entity_id": uid})
    tok = _known_token(uid, iid)
    info = requests.get(f"{API}/public/password-reset/{tok}").json()
    assert info["email_masked"].startswith("de") and "school" in info
    assert requests.post(f"{API}/public/password-reset/{tok}", json={"password": "weak"}).status_code == 400
    r = requests.post(f"{API}/public/password-reset/{tok}", json={"password": PW2})
    assert r.status_code == 200, r.text
    assert old_sess.get(f"{API}/auth/me").status_code == 401  # all old sessions revoked
    r = requests.post(f"{API}/public/password-reset/{tok}", json={"password": PW2 + "x"})
    assert r.status_code == 410 and "already been used" in r.json()["detail"]
    _, r = _login(A_EMAIL, PW1)
    assert r.status_code == 401
    _, r = _login(A_EMAIL, PW2)
    assert r.status_code == 200
    exp = _known_token(uid, iid, hours=-1)
    r = requests.get(f"{API}/public/password-reset/{exp}")
    assert r.status_code == 410 and "expired" in r.json()["detail"]
    assert requests.get(f"{API}/public/password-reset/garbage-token").status_code == 410
    db.login_attempts.delete_many({"identifier": {"$in": [A_EMAIL, f"user:{uid}"]}})


def test_change_email(ctx):
    pa, iid, uid = ctx["pa"], ctx["iid"], ctx["uid"]
    r = pa.post(f"{API}/platform/institutions/{iid}/admins/{uid}/email", json={"email": "admin@sunrise-demo.in"})
    assert r.status_code == 409
    assert pa.post(f"{API}/platform/institutions/{iid}/admins/{uid}/email", json={"email": "not-an-email"}).status_code == 422
    assert pa.post(f"{API}/platform/institutions/{SUN}/admins/{uid}/email", json={"email": B_EMAIL}).status_code == 404
    time.sleep(3)
    r = pa.post(f"{API}/platform/institutions/{iid}/admins/{uid}/email", json={"email": B_EMAIL.upper()})
    assert r.status_code == 200, r.text
    n = r.json()["notifications"]
    assert n[A_EMAIL]["message_id"] and n[B_EMAIL]["message_id"]
    _, r = _login(B_EMAIL, PW2)
    assert r.status_code == 200
    _, r = _login(A_EMAIL, PW2)
    assert r.status_code == 401
    assert db.audit_logs.find_one({"action": "admin_email_change", "entity_id": uid})
    db.login_attempts.delete_many({"identifier": {"$in": [A_EMAIL, B_EMAIL, f"user:{uid}"]}})
    admins = pa.get(f"{API}/platform/institutions/{iid}/admins").json()["admins"]
    assert admins[0]["email"] == B_EMAIL and admins[0]["last_login"]
