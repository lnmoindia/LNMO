"""Phase 46b — self-sufficient paper slips + admission-no backfill/auto-assign.
Throwaway DB. Covers: register by code alone (no admission no); wrong code fails; code + wrong admission
fails; single-use; case/dash-insensitive code; backfill idempotent + {CODE}-G{n}-{nnn} format; auto-assign
on create (enroll, /res, bulk) and next-admission-no per grade.
"""
import re
import sys
import uuid
import pytest

sys.path.insert(0, "/app/backend")
import server  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from pymongo import MongoClient  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

TEST_DB = "lnmo_phase46b_test"
PA_EMAIL = server.os.environ["PLATFORM_ADMIN_EMAIL"].lower()
PA_PW = server.os.environ["PLATFORM_ADMIN_PASSWORD"]


class Sess:
    def __init__(self, c, tok):
        self._c, self._h = c, {"Authorization": f"Bearer {tok}"}

    def _call(self, m, p, **k):
        self._c.cookies.clear()
        return self._c.request(m, p, headers={**self._h, **k.pop("headers", {})}, **k)

    def get(self, p, **k): return self._call("get", p, **k)
    def post(self, p, **k): return self._call("post", p, **k)


def _raw_student(mon, A, first, grade, adm=None):
    sid = str(uuid.uuid4())
    doc = {"id": sid, "institution_id": A, "first_name": first, "last_name": "B", "class_name": f"Grade {grade}",
           "section": "A", "enrollment_status": "enrolled", "created_at": server.now_iso()}
    if adm:
        doc["admission_no"] = adm
    mon.students.insert_one(doc)
    mon.enrollments.insert_one({"id": str(uuid.uuid4()), "institution_id": A, "student_id": sid,
                                "class_name": f"Grade {grade}", "section": "A", "admission_no": adm})
    return sid


@pytest.fixture(scope="module")
def ctx():
    async def _init():
        server.client = AsyncIOMotorClient(server.mongo_url)
        server.db = server.client[TEST_DB]
    server.app.router.on_startup.insert(0, _init)
    MongoClient(server.mongo_url).drop_database(TEST_DB)
    mon = MongoClient(server.mongo_url)[TEST_DB]
    server._otp_ip_hits.clear()
    with TestClient(server.app, base_url="https://testserver") as C:
        def login(email, pw):
            r = C.post("/api/auth/login", json={"email": email, "password": pw})
            assert r.status_code == 200, r.text
            tok = r.cookies.get("access_token"); C.cookies.clear()
            return tok
        platform = Sess(C, login(PA_EMAIL, PA_PW))
        A = platform.post("/api/res/institutions", json={"name": "Slip School", "slug": "p46b",
                          "admin_email": "a@p46b.test", "admin_password": "Admin@123"}).json()["id"]
        mon.institutions.update_one({"id": A}, {"$set": {"code": "TST"}})
        for g in (4, 8):
            mon.classes.insert_one({"id": f"c{g}", "institution_id": A, "name": f"Grade {g}", "grade_level": str(g)})
            mon.sections.insert_one({"id": f"s{g}", "institution_id": A, "name": "A", "class_name": f"Grade {g}", "status": "active"})
        admin = Sess(C, login("a@p46b.test", "Admin@123"))
        ids = {"has": _raw_student(mon, A, "Has", 8, "TST-G8-001"),
               "m8a": _raw_student(mon, A, "MissA", 8), "m8b": _raw_student(mon, A, "MissB", 8),
               "m4": _raw_student(mon, A, "MissC", 4)}
        yield {"C": C, "admin": admin, "A": A, "db": mon, **ids}
    MongoClient(server.mongo_url).drop_database(TEST_DB)


def _adm(db, sid):
    return db.students.find_one({"id": sid})["admission_no"]


def test_register_by_code_alone_and_guards(ctx):
    admin, C, db, A = ctx["admin"], ctx["C"], ctx["db"], ctx["A"]
    legacy = _raw_student(db, A, "Legacy", 8)  # no admission no
    slip = admin.post(f"/api/students/{legacy}/setup-code").json()
    assert slip["admission_no"] is None and re.fullmatch(r"[A-Z2-9]{8}", slip["code"])
    assert not set(slip["code"]) & set("01IOL")
    rec = db.parent_setup_codes.find_one({"student_id": legacy})
    assert rec["code_hash"] != slip["code"]
    C.cookies.clear()
    # wrong code fails
    assert C.post("/api/public/parent-register", json={"code": "ZZZZZZZZ", "phone": "9000001111",
                                                       "password": "Slip@123"}).status_code == 400
    # missing code fails
    assert C.post("/api/public/parent-register", json={"phone": "9000001111", "password": "Slip@123"}).status_code == 400
    # code alone (lower-case, dashed) works → linked
    pretty = f"{slip['code'][:4]}-{slip['code'][4:]}".lower()
    ok = C.post("/api/public/parent-register", json={"code": pretty, "phone": "90000 01111",
                                                     "name": "Code Parent", "password": "Slip@123"})
    assert ok.status_code == 200, ok.text
    p = db.users.find_one({"role": "parent", "phone": "9000001111"})
    assert p["student_ids"] == [legacy] and p["institution_id"] == A
    C.cookies.clear()
    # single-use
    assert C.post("/api/public/parent-register", json={"code": slip["code"], "phone": "9000001112",
                                                       "password": "Slip@123"}).status_code == 400
    C.cookies.clear()


def test_code_with_admission_no_must_match(ctx):
    admin, C, db = ctx["admin"], ctx["C"], ctx["db"]
    slip = admin.post(f"/api/students/{ctx['has']}/setup-code").json()
    assert slip["admission_no"] == "TST-G8-001"
    C.cookies.clear()
    bad = C.post("/api/public/parent-register", json={"code": slip["code"], "admission_no": "TST-G8-999",
                                                      "phone": "9000002222", "password": "Slip@123"})
    assert bad.status_code == 400
    assert db.parent_setup_codes.find_one({"student_id": ctx["has"], "used": False})  # still usable
    ok = C.post("/api/public/parent-register", json={"code": slip["code"], "admission_no": "tst-g8-001",
                                                     "phone": "9000002222", "password": "Slip@123"})
    assert ok.status_code == 200
    assert db.users.find_one({"role": "parent", "phone": "9000002222"})["student_ids"] == [ctx["has"]]
    C.cookies.clear()


def test_backfill_idempotent_and_format(ctx):
    admin, db = ctx["admin"], ctx["db"]
    r = admin.post("/api/students/backfill-admission-nos").json()
    by_id = {x["student_id"]: x["admission_no"] for x in r["items"]}
    assert ctx["has"] not in by_id
    assert {by_id[ctx["m8a"]], by_id[ctx["m8b"]]} <= {"TST-G8-002", "TST-G8-003", "TST-G8-004"}
    assert by_id[ctx["m4"]] == "TST-G4-001"
    assert all(re.fullmatch(r"TST-G\d+-\d{3}", a) for a in by_id.values())
    assert len(set(by_id.values())) == len(by_id)
    assert _adm(db, ctx["has"]) == "TST-G8-001"
    assert db.enrollments.find_one({"student_id": ctx["m4"]})["admission_no"] == "TST-G4-001"
    again = admin.post("/api/students/backfill-admission-nos").json()
    assert again["assigned"] == 0
    assert db.students.count_documents({"institution_id": ctx["A"], "admission_no": {"$in": [None, ""]}}) == 0


def test_auto_assign_on_create_and_next(ctx):
    admin, db, A = ctx["admin"], ctx["db"], ctx["A"]
    taken = set(db.students.distinct("admission_no", {"institution_id": A}))
    nxt = admin.get("/api/students/next-admission-no", params={"class_name": "Grade 4"}).json()["admission_no"]
    assert nxt == "TST-G4-002"
    e = admin.post("/api/students/enroll", json={"first_name": "Newbie", "enroll": True,
                                                 "class_name": "Grade 4", "section": "A"})
    assert e.status_code == 200, e.text
    assert e.json()["admission_no"] == "TST-G4-002"
    assert db.enrollments.find_one({"student_id": e.json()["id"]})["admission_no"] == "TST-G4-002"
    keep = admin.post("/api/students/enroll", json={"first_name": "Own", "admission_no": "CUSTOM-1"}).json()
    assert keep["admission_no"] == "CUSTOM-1"
    res = admin.post("/api/res/students", json={"first_name": "ResMade", "class_name": "Grade 8"}).json()
    assert re.fullmatch(r"TST-G8-\d{3}", res["admission_no"]) and res["admission_no"] not in taken
    b = admin.post("/api/students/bulk-enroll", json={"class_name": "Grade 8", "section": "A", "students": [
        {"first_name": "Bulk1"}, {"first_name": "Bulk2", "admission_no": "TST-G8-010"}, {"first_name": "Bulk3"}]})
    assert b.status_code == 200 and b.json()["created"] == 3
    adms = [db.students.find_one({"institution_id": A, "first_name": n})["admission_no"] for n in ("Bulk1", "Bulk2", "Bulk3")]
    assert adms[1] == "TST-G8-010" and len(set(adms)) == 3 and all(a.startswith("TST-G8-") for a in adms)
    allv = [s["admission_no"] for s in db.students.find({"institution_id": A})]
    assert len(allv) == len(set(allv))
