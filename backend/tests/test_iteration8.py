"""Iteration 8 — Subjects architecture upgrade:
- Subject catalog (name, code, type, default_max_marks, status)
- Subject offerings with practical/lab support (has_practical, theory/practical max, derived max_marks)
- POST /api/subject-offerings/bulk (create + dedupe + class-not-found skip + authz)
"""
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
SFX = uuid.uuid4().hex[:6]


@pytest.fixture(scope="module")
def admin():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=ADMIN, timeout=30)
    if r.status_code != 200:
        pytest.fail(f"admin login failed {r.status_code}: {r.text[:300]}")
    return s


@pytest.fixture(scope="module")
def state():
    return {"subjects": [], "classes": [], "offerings": []}


@pytest.fixture(scope="module", autouse=True)
def cleanup(admin, state):
    yield
    for oid in state["offerings"]:
        admin.delete(f"{API}/res/subject_offerings/{oid}", timeout=30)
    for cid in state["classes"]:
        admin.delete(f"{API}/res/classes/{cid}", timeout=30)
    for sid in state["subjects"]:
        admin.delete(f"{API}/res/subjects/{sid}", timeout=30)


@pytest.fixture(scope="module")
def unit_id(admin):
    r = admin.get(f"{API}/res/academic_units", params={"limit": 50}, timeout=30)
    assert r.status_code == 200, r.text[:300]
    items = r.json()["items"]
    assert items, "no academic units present in Greenwood"
    return items[0]["id"]


# ---------------- Subject catalog CRUD ----------------

class TestSubjectCatalog:
    def test_create_practical_subject_and_persist(self, admin, state):
        payload = {"name": f"TEST_Physics_{SFX}", "code": f"PHY{SFX}",
                   "type": "Practical / Lab", "default_max_marks": 100, "status": "active"}
        r = admin.post(f"{API}/res/subjects", json=payload, timeout=30)
        assert r.status_code == 200, r.text[:300]
        doc = r.json()
        assert "_id" not in doc
        sid = doc["id"]
        state["subjects"].append(sid)
        assert doc["type"] == "Practical / Lab"
        assert doc["default_max_marks"] == 100

        g = admin.get(f"{API}/res/subjects/{sid}", timeout=30)
        assert g.status_code == 200
        fetched = g.json()
        assert fetched["name"] == payload["name"]
        assert fetched["type"] == "Practical / Lab"
        assert fetched["default_max_marks"] == 100
        assert fetched["code"] == payload["code"]

    def test_update_subject(self, admin, state):
        sid = state["subjects"][0]
        u = admin.put(f"{API}/res/subjects/{sid}", json={"type": "Core", "default_max_marks": 80}, timeout=30)
        assert u.status_code == 200, u.text[:300]
        assert u.json()["type"] == "Core"
        g = admin.get(f"{API}/res/subjects/{sid}", timeout=30)
        assert g.json()["default_max_marks"] == 80
        assert g.json()["type"] == "Core"

    def test_delete_subject(self, admin):
        c = admin.post(f"{API}/res/subjects", json={"name": f"TEST_Del_{SFX}", "type": "Elective"}, timeout=30)
        assert c.status_code == 200
        sid = c.json()["id"]
        d = admin.delete(f"{API}/res/subjects/{sid}", timeout=30)
        assert d.status_code in (200, 204), d.text[:200]
        g = admin.get(f"{API}/res/subjects/{sid}", timeout=30)
        assert g.status_code == 404

    def test_subject_lookup_includes_new_subject(self, admin, state):
        r = admin.get(f"{API}/lookup/subjects", timeout=30)
        assert r.status_code == 200
        values = [o["value"] for o in r.json()]
        assert f"TEST_Physics_{SFX}" in values


# ---------------- Single subject offering (theory + practical) ----------------

class TestSingleOffering:
    def test_theory_offering_defaults_to_100(self, admin, state, unit_id):
        subj = f"TEST_Physics_{SFX}"
        r = admin.post(f"{API}/res/subject_offerings",
                       json={"subject": subj, "class_name": "Grade 6", "section": "",
                             "has_practical": False, "max_marks": 100}, timeout=30)
        assert r.status_code == 200, r.text[:300]
        doc = r.json()
        state["offerings"].append(doc["id"])
        assert doc["has_practical"] is False
        assert doc["max_marks"] == 100
        assert doc["theory_max_marks"] == 100
        assert doc["practical_max_marks"] == 0

        g = admin.get(f"{API}/res/subject_offerings/{doc['id']}", timeout=30)
        assert g.status_code == 200
        assert g.json()["max_marks"] == 100
        assert g.json()["has_practical"] is False

    def test_practical_offering_derives_total(self, admin, state):
        subj = f"TEST_Physics_{SFX}"
        r = admin.post(f"{API}/res/subject_offerings",
                       json={"subject": subj, "class_name": "Grade 6", "section": "A",
                             "has_practical": True, "theory_max_marks": 70,
                             "practical_max_marks": 30}, timeout=30)
        assert r.status_code == 200, r.text[:300]
        doc = r.json()
        state["offerings"].append(doc["id"])
        assert doc["has_practical"] is True
        assert doc["theory_max_marks"] == 70
        assert doc["practical_max_marks"] == 30
        assert doc["max_marks"] == 100

        g = admin.get(f"{API}/res/subject_offerings/{doc['id']}", timeout=30)
        assert g.json()["max_marks"] == 100

    def test_duplicate_offering_rejected(self, admin):
        subj = f"TEST_Physics_{SFX}"
        r = admin.post(f"{API}/res/subject_offerings",
                       json={"subject": subj, "class_name": "Grade 6", "section": ""}, timeout=30)
        assert r.status_code == 400
        assert "already offered" in r.json()["detail"].lower()

    def test_offering_bad_class_rejected(self, admin):
        r = admin.post(f"{API}/res/subject_offerings",
                       json={"subject": f"TEST_Physics_{SFX}", "class_name": f"NoSuch_{SFX}"}, timeout=30)
        assert r.status_code == 400
        assert "does not exist" in r.json()["detail"].lower()

    def test_offering_missing_subject_rejected(self, admin):
        r = admin.post(f"{API}/res/subject_offerings", json={"class_name": "Grade 6"}, timeout=30)
        assert r.status_code == 400

    def test_update_offering_to_practical_renormalizes(self, admin, state):
        """Editing an existing offering should re-derive marks (theory+practical=total)."""
        oid = state["offerings"][0]  # the theory offering
        u = admin.put(f"{API}/res/subject_offerings/{oid}",
                      json={"has_practical": True, "theory_max_marks": 60,
                            "practical_max_marks": 50}, timeout=30)
        assert u.status_code == 200, u.text[:300]
        g = admin.get(f"{API}/res/subject_offerings/{oid}", timeout=30)
        doc = g.json()
        assert doc["has_practical"] is True
        assert doc["theory_max_marks"] == 60
        assert doc["practical_max_marks"] == 50
        assert doc["max_marks"] == 110, f"derived total not recomputed on update: {doc}"


# ---------------- Bulk offer ----------------

class TestBulkOffer:
    def test_setup_extra_classes(self, admin, state, unit_id):
        for name in (f"TEST_C1_{SFX}", f"TEST_C2_{SFX}"):
            r = admin.post(f"{API}/res/classes", json={"name": name, "academic_unit_id": unit_id}, timeout=30)
            assert r.status_code == 200, r.text[:300]
            state["classes"].append(r.json()["id"])
        assert len(state["classes"]) == 2

    def test_bulk_create_practical(self, admin, state):
        subj = f"TEST_Physics_{SFX}"
        body = {"subject": subj, "class_names": [f"TEST_C1_{SFX}", f"TEST_C2_{SFX}"],
                "section": "", "has_practical": True,
                "theory_max_marks": 70, "practical_max_marks": 30}
        r = admin.post(f"{API}/subject-offerings/bulk", json=body, timeout=60)
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        assert data["created"] == 2, data
        assert data["skipped"] == []
        assert data["total"] == 2

        lst = admin.get(f"{API}/res/subject_offerings", params={"search": subj, "limit": 50}, timeout=30)
        assert lst.status_code == 200
        rows = [i for i in lst.json()["items"] if i["class_name"].startswith(f"TEST_C")]
        assert len(rows) == 2
        for row in rows:
            state["offerings"].append(row["id"])
            assert row["has_practical"] is True
            assert row["max_marks"] == 100
            assert row["theory_max_marks"] == 70
            assert row["practical_max_marks"] == 30
            assert "_id" not in row

    def test_bulk_dedupe_and_bad_class(self, admin, state):
        subj = f"TEST_Physics_{SFX}"
        body = {"subject": subj,
                "class_names": [f"TEST_C1_{SFX}", f"NOPE_{SFX}"],
                "section": "", "has_practical": False, "max_marks": 50}
        r = admin.post(f"{API}/subject-offerings/bulk", json=body, timeout=60)
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        assert data["created"] == 0, data
        reasons = {s["class"]: s["reason"] for s in data["skipped"]}
        assert reasons.get(f"TEST_C1_{SFX}") == "Already offered"
        assert reasons.get(f"NOPE_{SFX}") == "Class not found"

    def test_bulk_validation_errors(self, admin):
        r1 = admin.post(f"{API}/subject-offerings/bulk",
                        json={"subject": "", "class_names": ["Grade 6"]}, timeout=30)
        assert r1.status_code == 400
        r2 = admin.post(f"{API}/subject-offerings/bulk",
                        json={"subject": "Mathematics", "class_names": []}, timeout=30)
        assert r2.status_code == 400

    def test_bulk_requires_institution_admin(self):
        s = requests.Session()
        anon = s.post(f"{API}/subject-offerings/bulk",
                      json={"subject": "Mathematics", "class_names": ["Grade 6"]}, timeout=30)
        assert anon.status_code in (401, 403), anon.status_code

        t = requests.Session()
        lr = t.post(f"{API}/auth/login", json=TEACHER, timeout=30)
        if lr.status_code == 200:
            r = t.post(f"{API}/subject-offerings/bulk",
                       json={"subject": "Mathematics", "class_names": ["Grade 6"]}, timeout=30)
            assert r.status_code == 403, f"teacher should not bulk-offer: {r.status_code}"
        else:
            print(f"teacher login unavailable ({lr.status_code}); skipped teacher authz check")


# ---------------- Regression: class hub related endpoints ----------------

class TestRegression:
    @pytest.mark.parametrize("resource", ["classes", "sections", "enrollments",
                                          "teacher_assignments", "subjects",
                                          "subject_offerings", "academic_units"])
    def test_list_endpoints_ok(self, admin, resource):
        r = admin.get(f"{API}/res/{resource}", params={"limit": 5}, timeout=30)
        assert r.status_code == 200, f"{resource}: {r.status_code} {r.text[:200]}"
        body = r.json()
        assert "items" in body and "total" in body
        for it in body["items"]:
            assert "_id" not in it

    def test_dashboard_and_me(self, admin):
        me = admin.get(f"{API}/auth/me", timeout=30)
        assert me.status_code == 200
        assert me.json()["role"] == "institution_admin"
        d = admin.get(f"{API}/institution/stats", timeout=30)
        assert d.status_code == 200, d.text[:300]
        s = admin.get(f"{API}/institution/setup-status", timeout=30)
        assert s.status_code == 200, s.text[:300]
