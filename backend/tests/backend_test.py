"""LNMO School ERP - backend API regression tests."""
import os
import re
import uuid
from pathlib import Path

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE_URL = base_url.rstrip("/")
API = f"{BASE_URL}/api"

SUFFIX = uuid.uuid4().hex[:8]
INST_ADMIN_EMAIL = f"test_admin_{SUFFIX}@greenwood.test"
INST_ADMIN_PASSWORD = "Green@2026!"


def creds():
    content = Path("/app/memory/test_credentials.md").read_text(encoding="utf-8")
    e = re.search(r"(?im)^\s*(?:[-*]\s*)?(?:\*\*)?email(?:\*\*)?\s*:\s*`?([^`\s]+)", content)
    p = re.search(r"(?im)^\s*(?:[-*]\s*)?(?:\*\*)?password(?:\*\*)?\s*:\s*`?([^`\s]+)", content)
    if not e or not p:
        pytest.skip("credentials missing")
    return {"email": e.group(1), "password": p.group(1)}


PLATFORM = creds()


@pytest.fixture(scope="session")
def platform_client():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=PLATFORM, timeout=30)
    if r.status_code != 200:
        pytest.fail(f"platform admin login failed {r.status_code}: {r.text[:300]}")
    return s


@pytest.fixture(scope="session")
def state():
    return {}


# ---------------- Auth module ----------------
class TestAuth:
    def test_root(self):
        r = requests.get(f"{API}/", timeout=30)
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_login_sets_httponly_cookies(self):
        s = requests.Session()
        r = s.post(f"{API}/auth/login", json=PLATFORM, timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert data["email"] == PLATFORM["email"].lower()
        assert data["role"] == "platform_admin"
        assert "password_hash" not in data and "_id" not in data
        raw = r.headers.get("set-cookie", "")
        assert "access_token" in raw and "HttpOnly" in raw
        assert "access_token" in s.cookies and "refresh_token" in s.cookies

    def test_me(self, platform_client):
        r = platform_client.get(f"{API}/auth/me", timeout=30)
        assert r.status_code == 200
        assert r.json()["role"] == "platform_admin"

    def test_me_unauthenticated(self):
        r = requests.get(f"{API}/auth/me", timeout=30)
        assert r.status_code == 401

    def test_refresh(self, platform_client):
        r = platform_client.post(f"{API}/auth/refresh", timeout=30)
        assert r.status_code == 200
        assert r.json()["message"] == "refreshed"

    def test_refresh_without_cookie(self):
        r = requests.post(f"{API}/auth/refresh", timeout=30)
        assert r.status_code == 401

    def test_login_missing_fields(self):
        r = requests.post(f"{API}/auth/login", json={"email": "", "password": ""}, timeout=30)
        assert r.status_code == 400

    def test_login_wrong_password(self):
        r = requests.post(f"{API}/auth/login",
                          json={"email": PLATFORM["email"], "password": "wrong-pass"}, timeout=30)
        assert r.status_code == 401

    def test_bruteforce_lockout(self):
        email = f"test_lock_{uuid.uuid4().hex[:8]}@example.test"
        codes = []
        for _ in range(6):
            codes.append(requests.post(f"{API}/auth/login",
                                       json={"email": email, "password": "bad"}, timeout=30).status_code)
        assert codes[:5] == [401] * 5, codes
        assert codes[5] == 429, codes

    def test_logout_clears_cookies(self):
        s = requests.Session()
        s.post(f"{API}/auth/login", json=PLATFORM, timeout=30)
        r = s.post(f"{API}/auth/logout", timeout=30)
        assert r.status_code == 200
        assert s.get(f"{API}/auth/me", timeout=30).status_code == 401


# ---------------- Platform resources (tenants/institutions/plans) ----------------
class TestPlatformResources:
    def test_platform_stats(self, platform_client):
        r = platform_client.get(f"{API}/platform/stats", timeout=30)
        assert r.status_code == 200
        d = r.json()
        for k in ("tenants", "institutions", "plans", "users"):
            assert isinstance(d["counts"][k], int)
        assert isinstance(d["recent_activity"], list)

    def test_tenant_crud(self, platform_client):
        payload = {"name": f"TEST_Tenant_{SUFFIX}", "code": f"TT{SUFFIX}",
                   "contact_email": "tenant@test.test", "status": "active"}
        r = platform_client.post(f"{API}/res/tenants", json=payload, timeout=30)
        assert r.status_code == 200, r.text
        created = r.json()
        assert created["name"] == payload["name"] and "id" in created and "_id" not in created
        tid = created["id"]

        lr = platform_client.get(f"{API}/res/tenants", params={"search": payload["code"]}, timeout=30)
        assert lr.status_code == 200
        items = lr.json()["items"]
        assert any(i["id"] == tid for i in items)

        ur = platform_client.put(f"{API}/res/tenants/{tid}", json={"name": "TEST_Tenant_Updated"}, timeout=30)
        assert ur.status_code == 200 and ur.json()["name"] == "TEST_Tenant_Updated"
        got = platform_client.get(f"{API}/res/tenants", params={"search": payload["code"]}, timeout=30).json()["items"]
        assert got[0]["name"] == "TEST_Tenant_Updated"

        dr = platform_client.delete(f"{API}/res/tenants/{tid}", timeout=30)
        assert dr.status_code == 200
        after = platform_client.get(f"{API}/res/tenants", params={"search": payload["code"]}, timeout=30).json()
        assert after["total"] == 0
        assert platform_client.delete(f"{API}/res/tenants/{tid}", timeout=30).status_code == 404

    def test_plan_crud(self, platform_client):
        r = platform_client.post(f"{API}/res/plans",
                                 json={"name": f"TEST_Plan_{SUFFIX}", "code": f"TP{SUFFIX}", "price": 100}, timeout=30)
        assert r.status_code == 200
        pid = r.json()["id"]
        assert platform_client.put(f"{API}/res/plans/{pid}", json={"price": 200}, timeout=30).json()["price"] == 200
        assert platform_client.delete(f"{API}/res/plans/{pid}", timeout=30).status_code == 200

    def test_create_requires_name(self, platform_client):
        r = platform_client.post(f"{API}/res/tenants", json={"code": "X"}, timeout=30)
        assert r.status_code == 400

    def test_unknown_resource(self, platform_client):
        r = platform_client.get(f"{API}/res/bogus", timeout=30)
        assert r.status_code == 404

    def test_institution_scoped_resource_denied_for_platform_admin(self, platform_client):
        r = platform_client.get(f"{API}/res/students", timeout=30)
        assert r.status_code == 403

    def test_create_institution_with_admin_account(self, platform_client, state):
        payload = {"name": f"TEST_Greenwood_{SUFFIX}", "code": f"GW{SUFFIX}", "city": "Pune",
                   "contact_email": "info@greenwood.test", "status": "active",
                   "admin_name": "Greenwood Admin", "admin_email": INST_ADMIN_EMAIL,
                   "admin_password": INST_ADMIN_PASSWORD}
        r = platform_client.post(f"{API}/res/institutions", json=payload, timeout=30)
        assert r.status_code == 200, r.text
        inst = r.json()
        assert "admin_password" not in inst and "admin_email" not in inst
        state["institution_id"] = inst["id"]
        state["institution_name"] = inst["name"]

        lr = requests.post(f"{API}/auth/login",
                           json={"email": INST_ADMIN_EMAIL, "password": INST_ADMIN_PASSWORD}, timeout=30)
        assert lr.status_code == 200, lr.text
        u = lr.json()
        assert u["role"] == "institution_admin"
        assert u["institution_id"] == inst["id"]
        assert u["institution_name"] == inst["name"]

    def test_duplicate_admin_email_rejected(self, platform_client, state):
        assert state.get("institution_id")
        before = platform_client.get(f"{API}/res/institutions", timeout=30).json()["total"]
        r = platform_client.post(f"{API}/res/institutions",
                                 json={"name": f"TEST_Dup_{SUFFIX}", "admin_email": INST_ADMIN_EMAIL,
                                       "admin_password": "Xx@12345"}, timeout=30)
        assert r.status_code == 400
        after = platform_client.get(f"{API}/res/institutions", timeout=30).json()["total"]
        assert after == before, "institution row leaked after failed admin creation"


# ---------------- Institution scoped ----------------
@pytest.fixture(scope="session")
def inst_client(platform_client, state):
    if not state.get("institution_id"):
        payload = {"name": f"TEST_Greenwood_{SUFFIX}", "code": f"GW{SUFFIX}",
                   "admin_name": "Greenwood Admin", "admin_email": INST_ADMIN_EMAIL,
                   "admin_password": INST_ADMIN_PASSWORD}
        r = platform_client.post(f"{API}/res/institutions", json=payload, timeout=30)
        assert r.status_code == 200, r.text
        state["institution_id"] = r.json()["id"]
        state["institution_name"] = r.json()["name"]
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": INST_ADMIN_EMAIL, "password": INST_ADMIN_PASSWORD}, timeout=30)
    if r.status_code != 200:
        pytest.fail(f"institution admin login failed: {r.status_code} {r.text[:300]}")
    return s


class TestInstitutionResources:
    @pytest.mark.parametrize("resource,payload,update", [
        ("students", {"first_name": "TEST_Amit", "last_name": "Rao", "admission_no": "ADM-T1",
                      "email": "amit@test.test"}, {"last_name": "Rao-Updated"}),
        ("teachers", {"first_name": "TEST_Sunil", "last_name": "Patil", "employee_id": "EMP-T1"},
         {"employee_id": "EMP-T2"}),
        ("classes", {"name": "TEST_Class 5", "grade_level": "5"}, {"grade_level": "6"}),
        ("sections", {"name": "TEST_Sec A", "class_name": "TEST_Class 5"}, {"name": "TEST_Sec B"}),
        ("subjects", {"name": "TEST_Maths", "code": "MTH-T"}, {"code": "MTH-U"}),
    ])
    def test_crud(self, inst_client, state, resource, payload, update):
        if resource == "classes":
            ur = inst_client.post(f"{API}/res/academic_units",
                                  json={"name": f"TEST_Unit_{SUFFIX}", "code": "TU"}, timeout=30)
            assert ur.status_code == 200, ur.text
            payload = {**payload, "academic_unit_id": ur.json()["id"]}
        r = inst_client.post(f"{API}/res/{resource}", json=payload, timeout=30)
        assert r.status_code == 200, r.text
        doc = r.json()
        assert doc["institution_id"] == state["institution_id"]
        assert "_id" not in doc
        item_id = doc["id"]

        lr = inst_client.get(f"{API}/res/{resource}", timeout=30)
        assert lr.status_code == 200
        body = lr.json()
        assert body["total"] >= 1 and any(i["id"] == item_id for i in body["items"])
        assert all(i["institution_id"] == state["institution_id"] for i in body["items"])

        ur = inst_client.put(f"{API}/res/{resource}/{item_id}", json=update, timeout=30)
        assert ur.status_code == 200
        k, v = list(update.items())[0]
        assert ur.json()[k] == v

        assert inst_client.delete(f"{API}/res/{resource}/{item_id}", timeout=30).status_code == 200
        assert inst_client.delete(f"{API}/res/{resource}/{item_id}", timeout=30).status_code == 404

    def test_platform_resource_denied(self, inst_client):
        assert inst_client.get(f"{API}/res/tenants", timeout=30).status_code == 403
        assert inst_client.get(f"{API}/platform/stats", timeout=30).status_code == 403

    def test_institution_stats(self, inst_client):
        r = inst_client.get(f"{API}/institution/stats", timeout=30)
        assert r.status_code == 200
        d = r.json()
        for k in ("students", "teachers", "classes", "sections", "subjects", "users"):
            assert isinstance(d["counts"][k], int)

    def test_pagination(self, inst_client):
        ids = []
        for i in range(3):
            ids.append(inst_client.post(f"{API}/res/subjects",
                                        json={"name": f"TEST_Sub_{i}_{SUFFIX}"}, timeout=30).json()["id"])
        p1 = inst_client.get(f"{API}/res/subjects", params={"page": 1, "limit": 2}, timeout=30).json()
        p2 = inst_client.get(f"{API}/res/subjects", params={"page": 2, "limit": 2}, timeout=30).json()
        assert len(p1["items"]) == 2 and p1["pages"] >= 2
        assert p1["items"][0]["id"] != p2["items"][0]["id"]
        for i in ids:
            inst_client.delete(f"{API}/res/subjects/{i}", timeout=30)

    def test_search(self, inst_client):
        cid = inst_client.post(f"{API}/res/students",
                              json={"first_name": f"TEST_Zephyr{SUFFIX}", "last_name": "Q"}, timeout=30).json()["id"]
        r = inst_client.get(f"{API}/res/students", params={"search": f"Zephyr{SUFFIX}"}, timeout=30).json()
        assert r["total"] == 1 and r["items"][0]["id"] == cid
        empty = inst_client.get(f"{API}/res/students", params={"search": "nomatch_zzz"}, timeout=30).json()
        assert empty["total"] == 0
        inst_client.delete(f"{API}/res/students/{cid}", timeout=30)


class TestUsers:
    def test_create_list_update_delete_user(self, inst_client, state):
        email = f"test_teacher_{SUFFIX}@greenwood.test"
        r = inst_client.post(f"{API}/users", json={"name": "TEST_Teacher One", "email": email,
                                                  "password": "Teach@2026!", "role": "teacher"}, timeout=30)
        assert r.status_code == 200, r.text
        u = r.json()
        assert u["role"] == "teacher" and u["institution_id"] == state["institution_id"]
        assert "password_hash" not in u and "_id" not in u
        uid = u["id"]

        lr = inst_client.get(f"{API}/users", params={"search": email}, timeout=30).json()
        assert lr["total"] == 1
        assert "password_hash" not in lr["items"][0]

        # teacher can login
        ts = requests.Session()
        tl = ts.post(f"{API}/auth/login", json={"email": email, "password": "Teach@2026!"}, timeout=30)
        assert tl.status_code == 200 and tl.json()["role"] == "teacher"
        # teacher has no access to institution resources
        assert ts.get(f"{API}/res/students", timeout=30).status_code == 403
        assert ts.get(f"{API}/users", timeout=30).status_code == 403

        ur = inst_client.put(f"{API}/users/{uid}", json={"name": "TEST_Teacher Renamed", "status": "inactive"},
                             timeout=30)
        assert ur.status_code == 200 and ur.json()["name"] == "TEST_Teacher Renamed"
        # inactive user blocked from login
        il = requests.post(f"{API}/auth/login", json={"email": email, "password": "Teach@2026!"}, timeout=30)
        assert il.status_code == 403

        assert inst_client.delete(f"{API}/users/{uid}", timeout=30).status_code == 200
        assert inst_client.get(f"{API}/users", params={"search": email}, timeout=30).json()["total"] == 0

    def test_duplicate_email_rejected(self, inst_client):
        r = inst_client.post(f"{API}/users", json={"name": "Dup", "email": INST_ADMIN_EMAIL,
                                                   "password": "Xx@12345", "role": "staff"}, timeout=30)
        assert r.status_code == 400
        assert "already in use" in r.json()["detail"].lower()

    def test_invalid_role_rejected(self, inst_client):
        r = inst_client.post(f"{API}/users", json={"name": "Bad", "email": f"bad_{SUFFIX}@t.test",
                                                   "password": "Xx@12345", "role": "superuser"}, timeout=30)
        assert r.status_code == 400

    def test_cannot_delete_self(self, inst_client):
        me = inst_client.get(f"{API}/auth/me", timeout=30).json()
        r = inst_client.delete(f"{API}/users/{me['id']}", timeout=30)
        assert r.status_code == 400


class TestInstitutionProfileAndAudit:
    def test_profile_get_update(self, inst_client, state):
        r = inst_client.get(f"{API}/institution/profile", timeout=30)
        assert r.status_code == 200
        assert r.json()["id"] == state["institution_id"]
        ur = inst_client.put(f"{API}/institution/profile", json={"city": "Mumbai", "phone": "9999999999"}, timeout=30)
        assert ur.status_code == 200 and ur.json()["city"] == "Mumbai"
        assert inst_client.get(f"{API}/institution/profile", timeout=30).json()["phone"] == "9999999999"

    def test_audit_platform(self, platform_client):
        r = platform_client.get(f"{API}/audit", timeout=30)
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) > 0
        actions = {i["action"] for i in items}
        assert {"login"} & actions or {"create"} & actions
        assert all("_id" not in i for i in items)

    def test_audit_institution_scoped(self, inst_client, state):
        r = inst_client.get(f"{API}/audit", timeout=30)
        assert r.status_code == 200
        items = r.json()["items"]
        assert all(i["institution_id"] == state["institution_id"] for i in items)

    def test_audit_requires_auth(self):
        assert requests.get(f"{API}/audit", timeout=30).status_code == 401


# ---------------- Isolation between two institutions ----------------
class TestIsolation:
    def test_second_institution_cannot_see_first(self, platform_client, inst_client, state):
        email2 = f"test_admin2_{SUFFIX}@blue.test"
        r = platform_client.post(f"{API}/res/institutions",
                                 json={"name": f"TEST_Blue_{SUFFIX}", "code": f"BL{SUFFIX}",
                                       "admin_name": "Blue Admin", "admin_email": email2,
                                       "admin_password": "Blue@2026!"}, timeout=30)
        assert r.status_code == 200, r.text
        inst2 = r.json()["id"]
        s2 = requests.Session()
        assert s2.post(f"{API}/auth/login", json={"email": email2, "password": "Blue@2026!"},
                       timeout=30).status_code == 200

        sid = inst_client.post(f"{API}/res/students",
                               json={"first_name": f"TEST_Secret{SUFFIX}", "last_name": "One"},
                               timeout=30).json()["id"]
        listing = s2.get(f"{API}/res/students", timeout=30).json()
        assert all(i["id"] != sid for i in listing["items"])
        assert s2.get(f"{API}/res/students", params={"search": f"Secret{SUFFIX}"}, timeout=30).json()["total"] == 0
        # cross-tenant mutation blocked
        assert s2.put(f"{API}/res/students/{sid}", json={"last_name": "Hacked"}, timeout=30).status_code == 404
        assert s2.delete(f"{API}/res/students/{sid}", timeout=30).status_code == 404
        # users listing isolated
        assert all(u["institution_id"] == inst2 for u in s2.get(f"{API}/users", timeout=30).json()["items"])
        inst_client.delete(f"{API}/res/students/{sid}", timeout=30)
        platform_client.delete(f"{API}/res/institutions/{inst2}", timeout=30)


@pytest.fixture(scope="session", autouse=True)
def cleanup(request):
    yield
    s = requests.Session()
    if s.post(f"{API}/auth/login", json=PLATFORM, timeout=30).status_code != 200:
        return
    insts = s.get(f"{API}/res/institutions", params={"search": SUFFIX, "limit": 50}, timeout=30)
    if insts.status_code == 200:
        for i in insts.json()["items"]:
            s.delete(f"{API}/res/institutions/{i['id']}", timeout=30)
