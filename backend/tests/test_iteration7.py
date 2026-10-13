"""Iteration 7 — student area enhancements: next-admission-no, /students/filter,
portal-user creation, /portal/me, gender + phone persistence."""
import os
import uuid

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
API = f"{base_url.rstrip('/')}/api"

ADMIN = {"email": "admin@greenwood.edu", "password": "Green@2026!"}
TEACHER = {"email": "meera@greenwood.edu", "password": "Teach@2026!"}
SUFFIX = uuid.uuid4().hex[:6]
PORTAL_EMAIL = f"test_portal_{SUFFIX}@greenwood.test"
PORTAL_PASSWORD = "Portal@2026!"


@pytest.fixture(scope="module")
def admin():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=ADMIN, timeout=30)
    if r.status_code != 200:
        pytest.fail(f"admin login failed {r.status_code}: {r.text[:300]}")
    return s


@pytest.fixture(scope="module")
def teacher():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=TEACHER, timeout=30)
    if r.status_code != 200:
        pytest.fail(f"teacher login failed {r.status_code}: {r.text[:300]}")
    return s


@pytest.fixture(scope="module")
def state():
    return {"student_ids": [], "portal_user": None}


@pytest.fixture(scope="module", autouse=True)
def cleanup(admin, state):
    yield
    for sid in state["student_ids"]:
        admin.delete(f"{API}/res/students/{sid}", timeout=30)
    if state["portal_user"]:
        uid, sid = state["portal_user"]
        d = admin.delete(f"{API}/users/{uid}", timeout=30)
        print("cleanup delete user", uid, d.status_code)
        admin.put(f"{API}/res/students/{sid}", json={"has_portal_access": False, "portal_email": "", "user_id": ""}, timeout=30)


def get_student(sess, sid):
    """No single-GET route exists; resolve via the filter list endpoint."""
    r = sess.get(f"{API}/students/filter", params={"limit": 200}, timeout=30)
    assert r.status_code == 200, r.text[:300]
    for i in r.json()["items"]:
        if i["id"] == sid:
            return i
    return None


# ---------------- next-admission-no ----------------
class TestAdmissionNo:
    def test_next_admission_no_format(self, admin):
        r = admin.get(f"{API}/students/next-admission-no", timeout=30)
        assert r.status_code == 200
        adm = r.json()["admission_no"]
        assert adm.startswith("GH-2026-"), adm
        assert len(adm.split("-")[-1]) == 4

    def test_unique_vs_existing(self, admin, state):
        adm = admin.get(f"{API}/students/next-admission-no", timeout=30).json()["admission_no"]
        r = admin.post(f"{API}/res/students", json={
            "first_name": "TEST_Adm", "last_name": "Seq", "admission_no": adm,
            "gender": "others", "phone": "+91 9999900001",
        }, timeout=30)
        assert r.status_code in (200, 201), r.text[:300]
        sid = r.json()["id"]
        state["student_ids"].append(sid)
        nxt = admin.get(f"{API}/students/next-admission-no", timeout=30).json()["admission_no"]
        assert nxt != adm

    def test_requires_institution_admin(self, teacher):
        r = teacher.get(f"{API}/students/next-admission-no", timeout=30)
        assert r.status_code == 403

    def test_unauthenticated(self):
        r = requests.get(f"{API}/students/next-admission-no", timeout=30)
        assert r.status_code in (401, 403)


# ---------------- gender + phone persistence ----------------
class TestStudentFieldPersistence:
    def test_create_with_gender_and_dialcode_phone(self, admin, state):
        payload = {"first_name": "TEST_Phone", "last_name": "Case", "gender": "female",
                   "phone": "+91 9876543210", "guardian_name": "TEST Guardian",
                   "guardian_phone": "+44 7700900123", "class_name": "Grade 6", "section": "A"}
        r = admin.post(f"{API}/res/students", json=payload, timeout=30)
        assert r.status_code in (200, 201), r.text[:300]
        sid = r.json()["id"]
        state["student_ids"].append(sid)
        d = get_student(admin, sid)
        assert d is not None
        assert "_id" not in d
        assert d["gender"] == "female"
        assert d["phone"] == "+91 9876543210"
        assert d["guardian_phone"] == "+44 7700900123"

        u = admin.put(f"{API}/res/students/{sid}", json={"gender": "others"}, timeout=30)
        assert u.status_code == 200, u.text[:300]
        assert get_student(admin, sid)["gender"] == "others"


# ---------------- /students/filter ----------------
class TestStudentFilter:
    def test_no_filters_lists_all(self, admin):
        r = admin.get(f"{API}/students/filter", timeout=30)
        assert r.status_code == 200
        d = r.json()
        for k in ("items", "total", "page", "pages"):
            assert k in d
        assert d["total"] >= 1
        assert all("_id" not in i and "password_hash" not in i for i in d["items"])

    def test_class_filter(self, admin):
        r = admin.get(f"{API}/students/filter", params={"class_name": "Grade 6"}, timeout=30)
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) >= 1
        assert all(i["class_name"] == "Grade 6" for i in items)

    def test_class_section_filter(self, admin):
        r = admin.get(f"{API}/students/filter", params={"class_name": "Grade 6", "section": "A"}, timeout=30)
        assert r.status_code == 200
        assert all(i["section"] == "A" and i["class_name"] == "Grade 6" for i in r.json()["items"])

    def test_unknown_class_returns_zero(self, admin):
        r = admin.get(f"{API}/students/filter", params={"class_name": "NoSuchClass"}, timeout=30)
        assert r.status_code == 200
        assert r.json()["total"] == 0

    def test_subject_filter_no_offerings_returns_zero(self, admin):
        r = admin.get(f"{API}/students/filter", params={"subject": "Mathematics"}, timeout=30)
        assert r.status_code == 200
        # Greenwood has no subject offerings -> expected 0
        assert r.json()["total"] == 0

    def test_search(self, admin):
        r = admin.get(f"{API}/students/filter", params={"search": "Aarav"}, timeout=30)
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) >= 1
        assert any("Aarav" in (i.get("first_name") or "") for i in items)

    def test_pagination_fields(self, admin):
        r = admin.get(f"{API}/students/filter", params={"page": 1, "limit": 1}, timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert len(d["items"]) <= 1
        assert d["page"] == 1 and d["pages"] >= 1

    def test_teacher_forbidden(self, teacher):
        r = teacher.get(f"{API}/students/filter", timeout=30)
        assert r.status_code == 403


# ---------------- portal user + /portal/me ----------------
class TestPortal:
    @pytest.fixture(scope="class")
    def spare_student(self, admin, state):
        r = admin.post(f"{API}/res/students", json={
            "first_name": "TEST_Spare", "last_name": "Portal", "gender": "male",
            "phone": "+1 5551234567", "class_name": "Grade 6", "section": "A"}, timeout=30)
        assert r.status_code in (200, 201), r.text[:300]
        sid = r.json()["id"]
        state["student_ids"].append(sid)
        return sid

    def test_create_portal_user_and_login(self, admin, state):
        stu = admin.get(f"{API}/students/filter", params={"search": "Aarav"}, timeout=30).json()["items"][0]
        sid = stu["id"]
        r = admin.post(f"{API}/students/{sid}/portal-user",
                       json={"email": PORTAL_EMAIL, "password": PORTAL_PASSWORD}, timeout=30)
        assert r.status_code in (200, 201), r.text[:300]
        body = r.json()
        assert body["email"] == PORTAL_EMAIL
        assert "id" in body
        state["portal_user"] = (body["id"], sid)

        g = get_student(admin, sid)
        assert g["has_portal_access"] is True
        assert g["portal_email"] == PORTAL_EMAIL

        dup = admin.post(f"{API}/students/{sid}/portal-user",
                         json={"email": f"x{PORTAL_EMAIL}", "password": PORTAL_PASSWORD}, timeout=30)
        assert dup.status_code == 400
        assert "already" in dup.json()["detail"].lower()

    def test_missing_fields(self, admin, spare_student):
        r = admin.post(f"{API}/students/{spare_student}/portal-user", json={"email": "", "password": ""}, timeout=30)
        assert r.status_code == 400

    def test_unknown_student_404(self, admin):
        r = admin.post(f"{API}/students/{uuid.uuid4()}/portal-user",
                       json={"email": f"nope_{SUFFIX}@x.test", "password": "Abcd@2026!"}, timeout=30)
        assert r.status_code == 404

    def test_duplicate_email_rejected(self, admin, state, spare_student):
        assert state["portal_user"], "run test_create_portal_user_and_login first"
        r = admin.post(f"{API}/students/{spare_student}/portal-user",
                       json={"email": PORTAL_EMAIL, "password": PORTAL_PASSWORD}, timeout=30)
        assert r.status_code == 400
        assert "in use" in r.json()["detail"].lower()

    def test_student_login_and_portal_me(self, state):
        assert state["portal_user"], "portal user must exist"
        s = requests.Session()
        r = s.post(f"{API}/auth/login", json={"email": PORTAL_EMAIL, "password": PORTAL_PASSWORD}, timeout=30)
        assert r.status_code == 200, r.text[:300]
        me = r.json().get("user") or r.json()
        assert me.get("role") == "student"

        p = s.get(f"{API}/portal/me", timeout=30)
        assert p.status_code == 200, p.text[:300]
        d = p.json()
        assert d["student"]["admission_no"] == "GW001"
        assert d["student"]["class_name"] == "Grade 6"
        assert "_id" not in d["student"]
        assert "password_hash" not in d["student"]
        assert set(d["attendance"].keys()) == {"present", "total", "pct"}
        assert isinstance(d["results"], list)

    def test_student_cannot_access_admin_endpoints(self, state):
        assert state["portal_user"]
        s = requests.Session()
        r = s.post(f"{API}/auth/login", json={"email": PORTAL_EMAIL, "password": PORTAL_PASSWORD}, timeout=30)
        assert r.status_code == 200
        assert s.get(f"{API}/students/filter", timeout=30).status_code == 403
        assert s.get(f"{API}/res/students", timeout=30).status_code == 403

    def test_portal_me_forbidden_for_admin(self, admin):
        assert admin.get(f"{API}/portal/me", timeout=30).status_code == 403

    def test_orphan_portal_user_after_student_delete(self, admin):
        """Deleting a student leaves its portal user able to log in; /portal/me must 404 not 500."""
        email = f"test_orphan_{SUFFIX}@greenwood.test"
        r = admin.post(f"{API}/res/students", json={
            "first_name": "TEST_Orphan", "last_name": "Del", "class_name": "Grade 6", "section": "A"}, timeout=30)
        sid = r.json()["id"]
        pu = admin.post(f"{API}/students/{sid}/portal-user", json={"email": email, "password": PORTAL_PASSWORD}, timeout=30)
        assert pu.status_code in (200, 201), pu.text[:300]
        uid = pu.json()["id"]
        assert admin.delete(f"{API}/res/students/{sid}", timeout=30).status_code in (200, 204)
        s2 = requests.Session()
        lr = s2.post(f"{API}/auth/login", json={"email": email, "password": PORTAL_PASSWORD}, timeout=30)
        print("orphan login status", lr.status_code)
        if lr.status_code == 200:
            me = s2.get(f"{API}/portal/me", timeout=30)
            print("orphan /portal/me", me.status_code, me.text[:150])
            assert me.status_code == 404
        admin.delete(f"{API}/users/{uid}", timeout=30)
