"""Phase 41 — Promotion & academic-year rollover.
Throwaway DB. Covers: preview mapping + auto-clone of the to-year row; teacher recommend →
principal confirm (unconfirmed rec never detains); execute correctness (promote/detain/
graduate/transfer incl. login disable + alumni); double-execute 409; rollback success and
rollback blocked when the new year has data; unit-principal scope; old-year data untouched.
"""
import sys
import uuid
import pytest

sys.path.insert(0, "/app/backend")
import server  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from pymongo import MongoClient  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

TEST_DB = "lnmo_phase41_test"
PA_EMAIL = server.os.environ["PLATFORM_ADMIN_EMAIL"].lower()
PA_PW = server.os.environ["PLATFORM_ADMIN_PASSWORD"]
BASE = "https://testserver"
FROM_Y = "2026-27"
TO_Y = "2027-28"


def _client():
    return TestClient(server.app, base_url=BASE)


class Sess:
    def __init__(self, c, tok):
        self._c, self._h = c, {"Authorization": f"Bearer {tok}"}

    def _call(self, m, p, **k):
        self._c.cookies.clear()
        return self._c.request(m, p, headers={**self._h, **k.pop("headers", {})}, **k)

    def get(self, p, **k): return self._call("get", p, **k)
    def post(self, p, **k): return self._call("post", p, **k)
    def put(self, p, **k): return self._call("put", p, **k)
    def delete(self, p, **k): return self._call("delete", p, **k)


def _seed_student(mon, iid, name, grade, section, year, user_id=None):
    sid = str(uuid.uuid4())
    doc = {"id": sid, "institution_id": iid, "first_name": name, "last_name": "X",
           "admission_no": name[:3].upper(), "enrollment_status": "enrolled",
           "class_name": f"Grade {grade}", "section": section, "academic_year": year}
    if user_id:
        doc["user_id"] = user_id
    mon.students.insert_one(doc)
    mon.enrollments.insert_one({"id": str(uuid.uuid4()), "institution_id": iid, "student_id": sid,
                                "student_name": f"{name} X", "admission_no": doc["admission_no"],
                                "academic_year": year, "class_name": f"Grade {grade}", "section": section})
    return sid


@pytest.fixture(scope="module")
def ctx(monkeymodule):
    async def _init():
        server.client = AsyncIOMotorClient(server.mongo_url)
        server.db = server.client[TEST_DB]
    server.app.router.on_startup.insert(0, _init)
    MongoClient(server.mongo_url).drop_database(TEST_DB)
    mon = MongoClient(server.mongo_url)[TEST_DB]

    with _client() as C:
        def login(email, pw):
            r = C.post("/api/auth/login", json={"email": email, "password": pw})
            assert r.status_code == 200, r.text
            tok = r.cookies.get("access_token"); C.cookies.clear()
            return tok

        platform = Sess(C, login(PA_EMAIL, PA_PW))
        A = platform.post("/api/res/institutions", json={"name": "Promo", "slug": "p41",
                          "admin_email": "a@p41.test", "admin_password": "Admin@123"}).json()["id"]
        admin = Sess(C, login("a@p41.test", "Admin@123"))

        # divisions + classes (span years) + sections
        mon.academic_units.insert_many([
            {"id": "uHS", "institution_id": A, "name": "HS", "code": "HS"},
            {"id": "uHSS", "institution_id": A, "name": "HSS", "code": "HSS"},
        ])
        for g, unit in [(8, "uHS"), (9, "uHS"), (10, "uHS"), (11, "uHSS"), (12, "uHSS")]:
            uname = "HS" if unit == "uHS" else "HSS"
            mon.classes.insert_one({"id": f"c{g}", "institution_id": A, "name": f"Grade {g}",
                                    "grade_level": str(g), "academic_unit_id": unit, "academic_unit_name": uname})
            mon.sections.insert_one({"id": f"s{g}A", "institution_id": A, "name": "A",
                                     "class_name": f"Grade {g}", "status": "active"})
        mon.academic_years.insert_one({"id": str(uuid.uuid4()), "institution_id": A, "name": FROM_Y, "status": "active"})

        # class teacher for Grade 8-A
        ctid = str(uuid.uuid4())
        mon.users.insert_one({"id": ctid, "name": "ClassTeacher", "email": "ct@p41.test",
                              "password_hash": server.hash_password("Teach@123"), "role": "teacher",
                              "institution_id": A, "status": "active", "must_change_password": False,
                              "created_at": server.now_iso()})
        mon.sections.update_one({"id": "s8A"}, {"$set": {"class_teacher_id": ctid, "class_teacher": "ClassTeacher"}})
        CT = Sess(C, login("ct@p41.test", "Teach@123"))

        # unit principal over HSS only
        ptid = str(uuid.uuid4())
        mon.users.insert_one({"id": ptid, "name": "HSSPrincipal", "email": "pr@p41.test",
                              "password_hash": server.hash_password("Prin@123"), "role": "teacher",
                              "institution_id": A, "status": "active", "must_change_password": False,
                              "created_at": server.now_iso()})
        mon.principal_assignments.insert_one({"id": str(uuid.uuid4()), "institution_id": A, "user_id": ptid,
                                              "scope_type": "units", "unit_ids": ["uHSS"], "designation": "principal"})
        PR = Sess(C, login("pr@p41.test", "Prin@123"))

        # students: a portal-login student in Grade 8, a plain Grade 8, a Grade 12 (graduate), a Grade 11
        suid = str(uuid.uuid4())
        mon.users.insert_one({"id": suid, "name": "S", "email": "s1@p41.test",
                              "password_hash": server.hash_password("Stud@123"), "role": "student",
                              "institution_id": A, "status": "active", "student_id": None, "created_at": server.now_iso()})
        s_alice = _seed_student(mon, A, "Alice", 8, "A", FROM_Y, user_id=suid)
        mon.users.update_one({"id": suid}, {"$set": {"student_id": s_alice}})
        mon.students.update_one({"id": s_alice}, {"$set": {"has_portal_access": True, "user_id": suid}})
        s_bob = _seed_student(mon, A, "Bob", 8, "A", FROM_Y)
        s_grad = _seed_student(mon, A, "Grace", 12, "A", FROM_Y)
        s_hss = _seed_student(mon, A, "Harry", 11, "A", FROM_Y)

        yield {"admin": admin, "CT": CT, "PR": PR, "A": A, "db": mon,
               "s_alice": s_alice, "s_bob": s_bob, "s_grad": s_grad, "s_hss": s_hss, "suid": suid}
    MongoClient(server.mongo_url).drop_database(TEST_DB)


def _preview(admin):
    return admin.post("/api/promotion/preview", json={"from_year": FROM_Y, "to_year": TO_Y})


def _decisions(admin):
    rid = admin.get("/api/promotion/runs").json()["runs"][0]["id"]
    return rid, admin.get(f"/api/promotion/{rid}").json()["decisions"]


def test_preview_mapping_and_autoclone(ctx):
    admin, db = ctx["admin"], ctx["db"]
    assert db.academic_years.find_one({"institution_id": ctx["A"], "name": TO_Y}) is None
    r = _preview(admin)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["structure"]["academic_year_created"] is True
    assert db.academic_years.find_one({"institution_id": ctx["A"], "name": TO_Y}) is not None  # created
    by_id = {d["student_id"]: d for d in body["decisions"]}
    assert by_id[ctx["s_alice"]]["to_class"] == "Grade 9" and by_id[ctx["s_alice"]]["to_section"] == "A"
    assert by_id[ctx["s_grad"]]["decision"] == "graduate" and by_id[ctx["s_grad"]]["to_class"] is None
    # preview must NOT mutate the student's current placement
    assert db.students.find_one({"id": ctx["s_alice"]})["class_name"] == "Grade 8"


def test_recommend_then_confirm(ctx):
    admin, CT, db = ctx["admin"], ctx["CT"], ctx["db"]
    _preview(admin)
    rid, decs = _decisions(admin)
    bob = next(d for d in decs if d["student_id"] == ctx["s_bob"])
    # class teacher recommends detain — recommendation alone must NOT change the decision
    rr = CT.put(f"/api/promotion/decisions/{bob['id']}/recommend", json={"recommendation": "detain", "note": "weak in maths"})
    assert rr.status_code == 200, rr.text
    reread = db.promotion_decisions.find_one({"id": bob["id"]})
    assert reread["teacher_recommendation"] == "detain" and reread["decision"] == "promote"  # unconfirmed
    # principal/admin confirms detain
    dr = admin.put(f"/api/promotion/decisions/{bob['id']}", json={"decision": "detain"})
    assert dr.status_code == 200 and dr.json()["decision"] == "detain" and dr.json()["to_class"] == "Grade 8"


def test_unit_principal_scope(ctx):
    admin, PR = ctx["admin"], ctx["PR"]
    _preview(admin)
    rid, _ = _decisions(admin)
    # HSS principal only sees HSS classes (Grade 11/12), never Grade 8
    decs = PR.get(f"/api/promotion/{rid}").json()["decisions"]
    classes = {d["from_class"] for d in decs}
    assert classes <= {"Grade 11", "Grade 12"} and "Grade 8" not in classes
    # and cannot decide on a Grade 8 student
    g8 = admin.get(f"/api/promotion/{rid}").json()["decisions"]
    bob = next(d for d in g8 if d["student_id"] == ctx["s_bob"])
    assert PR.put(f"/api/promotion/decisions/{bob['id']}", json={"decision": "promote"}).status_code == 403


def test_execute_rollback_and_guards(ctx):
    admin, db = ctx["admin"], ctx["db"]
    _preview(admin)
    rid, decs = _decisions(admin)
    byid = {d["student_id"]: d for d in decs}
    # confirm: Bob detained, Harry transferred_out, (Grace auto-graduate, Alice auto-promote)
    admin.put(f"/api/promotion/decisions/{byid[ctx['s_bob']]['id']}", json={"decision": "detain"})
    admin.put(f"/api/promotion/decisions/{byid[ctx['s_hss']]['id']}", json={"decision": "transfer_out"})

    r = admin.post(f"/api/promotion/{rid}/execute")
    assert r.status_code == 200, r.text
    # double-execute blocked
    assert admin.post(f"/api/promotion/{rid}/execute").status_code == 409

    alice = db.students.find_one({"id": ctx["s_alice"]})
    assert alice["class_name"] == "Grade 9" and alice["academic_year"] == TO_Y
    assert db.enrollments.find_one({"student_id": ctx["s_alice"], "academic_year": FROM_Y})["status"] == "completed"
    assert db.enrollments.find_one({"student_id": ctx["s_alice"], "academic_year": TO_Y, "status": "active"})
    bob = db.students.find_one({"id": ctx["s_bob"]})
    assert bob["class_name"] == "Grade 8" and bob["academic_year"] == TO_Y  # detained: same grade, new year
    assert db.students.find_one({"id": ctx["s_grad"]})["enrollment_status"] == "alumni"
    harry = db.students.find_one({"id": ctx["s_hss"]})
    assert harry["enrollment_status"] == "transferred"
    assert db.users.find_one({"id": ctx["suid"]})["status"] == "active"  # Alice promoted → login untouched

    # rollback BLOCKED when the new year already has timetable data
    db.timetable_entries.insert_one({"id": str(uuid.uuid4()), "institution_id": ctx["A"], "academic_year": TO_Y})
    assert admin.post(f"/api/promotion/{rid}/rollback").status_code == 409
    db.timetable_entries.delete_many({"institution_id": ctx["A"], "academic_year": TO_Y})

    # rollback succeeds and restores everything
    assert admin.post(f"/api/promotion/{rid}/rollback").status_code == 200
    assert db.students.find_one({"id": ctx["s_alice"]})["class_name"] == "Grade 8"
    assert db.students.find_one({"id": ctx["s_grad"]})["enrollment_status"] == "enrolled"
    assert db.enrollments.count_documents({"student_id": ctx["s_alice"], "academic_year": TO_Y}) == 0
    assert db.enrollments.find_one({"student_id": ctx["s_alice"], "academic_year": FROM_Y})["status"] == "active"


def test_transfer_login_disable_roundtrip(ctx):
    """A transferred-out student with a portal login gets disabled on execute and re-enabled on rollback."""
    admin, db = ctx["admin"], ctx["db"]
    _preview(admin)
    rid, decs = _decisions(admin)
    byid = {d["student_id"]: d for d in decs}
    admin.put(f"/api/promotion/decisions/{byid[ctx['s_alice']]['id']}", json={"decision": "transfer_out"})
    admin.post(f"/api/promotion/{rid}/execute")
    assert db.users.find_one({"id": ctx["suid"]})["status"] == "inactive"      # login disabled
    assert db.students.find_one({"id": ctx["s_alice"]})["enrollment_status"] == "transferred"
    admin.post(f"/api/promotion/{rid}/rollback")
    assert db.users.find_one({"id": ctx["suid"]})["status"] == "active"         # re-enabled
    assert db.students.find_one({"id": ctx["s_alice"]})["enrollment_status"] == "enrolled"
