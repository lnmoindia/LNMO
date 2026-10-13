"""Phase 46 — Phone-keyed parent invites.
Throwaway DB, STUB comm provider. Covers: sibling dedupe (one account, two links) + stub send + quota;
no-phone → skipped + paper-slip code registration; collision → review bucket (not auto-linked) + force-link;
ready-to-invite after phone added; secure link tamper/expiry + password setup; unit-principal scope.
"""
import sys
import uuid
import pytest

sys.path.insert(0, "/app/backend")
import server  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from pymongo import MongoClient  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

TEST_DB = "lnmo_phase46_test"
PA_EMAIL = server.os.environ["PLATFORM_ADMIN_EMAIL"].lower()
PA_PW = server.os.environ["PLATFORM_ADMIN_PASSWORD"]
BASE = "https://testserver"


class Sess:
    def __init__(self, c, tok):
        self._c, self._h = c, {"Authorization": f"Bearer {tok}"}

    def _call(self, m, p, **k):
        self._c.cookies.clear()
        return self._c.request(m, p, headers={**self._h, **k.pop("headers", {})}, **k)

    def get(self, p, **k): return self._call("get", p, **k)
    def post(self, p, **k): return self._call("post", p, **k)


def _stu(mon, A, first, grade, phone=None, guardian=None, adm=None):
    sid = str(uuid.uuid4())
    doc = {"id": sid, "institution_id": A, "first_name": first, "last_name": "T", "class_name": f"Grade {grade}",
           "section": "A", "enrollment_status": "enrolled", "admission_no": adm or f"P46-{first}",
           "created_at": server.now_iso()}
    if phone:
        doc["guardian_phone"] = phone
    if guardian:
        doc["guardian_name"] = guardian
    mon.students.insert_one(doc)
    return sid


@pytest.fixture(scope="module")
def ctx():
    async def _init():
        server.client = AsyncIOMotorClient(server.mongo_url)
        server.db = server.client[TEST_DB]
    server.app.router.on_startup.insert(0, _init)
    MongoClient(server.mongo_url).drop_database(TEST_DB)
    mon = MongoClient(server.mongo_url)[TEST_DB]
    with TestClient(server.app, base_url=BASE) as C:
        def login(email, pw):
            r = C.post("/api/auth/login", json={"email": email, "password": pw})
            assert r.status_code == 200, r.text
            tok = r.cookies.get("access_token"); C.cookies.clear()
            return tok

        platform = Sess(C, login(PA_EMAIL, PA_PW))
        A = platform.post("/api/res/institutions", json={"name": "Invite School", "slug": "p46",
                          "admin_email": "a@p46.test", "admin_password": "Admin@123"}).json()["id"]
        admin = Sess(C, login("a@p46.test", "Admin@123"))
        mon.academic_units.insert_many([{"id": "uHS", "institution_id": A, "name": "HS", "code": "HS"},
                                        {"id": "uHSS", "institution_id": A, "name": "HSS", "code": "HSS"}])
        for g, unit in [(8, "uHS"), (11, "uHSS")]:
            mon.classes.insert_one({"id": f"c{g}", "institution_id": A, "name": f"Grade {g}",
                                    "grade_level": str(g), "academic_unit_id": unit})
        ptid = str(uuid.uuid4())
        mon.users.insert_one({"id": ptid, "name": "HSSP", "email": "pr@p46.test",
                              "password_hash": server.hash_password("Prin@123"), "role": "teacher",
                              "institution_id": A, "status": "active", "must_change_password": False,
                              "created_at": server.now_iso()})
        mon.principal_assignments.insert_one({"id": str(uuid.uuid4()), "institution_id": A, "user_id": ptid,
                                              "scope_type": "units", "unit_ids": ["uHSS"], "designation": "principal"})
        PR = Sess(C, login("pr@p46.test", "Prin@123"))
        ids = {
            "sib1": _stu(mon, A, "Sib1", 8, "9000000001", "Ravi K"),
            "sib2": _stu(mon, A, "Sib2", 8, "+91 90000 00001", "ravi k "),
            "nophone": _stu(mon, A, "NoPhone", 8, adm="P46-NOPH"),
            "late": _stu(mon, A, "Late", 8),
            "col1": _stu(mon, A, "Col1", 8, "9000000003", "Anil"),
            "col2": _stu(mon, A, "Col2", 11, "9000000003", "Bindu"),
            "hss": _stu(mon, A, "Hss", 11, "9000000004", "Hari"),
        }
        yield {"C": C, "admin": admin, "PR": PR, "A": A, "db": mon, **ids}
    MongoClient(server.mongo_url).drop_database(TEST_DB)


def _names(bucket):
    return {r["student_name"].split()[0] for r in bucket}


def test_bulk_invite_dedupe_skip_collision_and_quota(ctx):
    admin, db, A = ctx["admin"], ctx["db"], ctx["A"]
    before = (db.institutions.find_one({"id": A}).get("comm") or {}).get("quota", {}).get("whatsapp", {}).get("used", 0)
    r = admin.post("/api/students/invite-parents", json={"class_ids": ["c8"], "channel": "whatsapp"})
    assert r.status_code == 200, r.text
    b = r.json()
    assert _names(b["invited"]) == {"Sib1", "Sib2"}
    assert {x["action"] for x in b["invited"]} == {"created", "linked_sibling"}
    assert _names(b["skipped_no_phone"]) == {"NoPhone", "Late"}
    assert _names(b["collisions_for_review"]) == {"Col1"}
    parents = list(db.users.find({"institution_id": A, "role": "parent", "phone": "9000000001"}))
    assert len(parents) == 1 and set(parents[0]["student_ids"]) == {ctx["sib1"], ctx["sib2"]}
    assert parents[0]["must_change_password"] is True
    # collision student NOT auto-linked
    assert db.users.count_documents({"role": "parent", "student_ids": ctx["col1"]}) == 0
    # exactly one stub invite message for the shared phone; quota decremented by one
    msgs = list(db.messages.find({"institution_id": A, "module": "parent_invite"}))
    assert len(msgs) == 1 and msgs[0]["recipient_phone"] == "9000000001" and "/setup/parent/" in msgs[0]["body"]
    after = db.institutions.find_one({"id": A})["comm"]["quota"]["whatsapp"]["used"]
    assert after == before + 1
    assert db.parent_invites.count_documents({"institution_id": A}) == 2
    # re-run is idempotent: both siblings already linked, no new message
    b2 = admin.post("/api/students/invite-parents", json={"class_ids": ["c8"]}).json()
    assert _names(b2["already_linked"]) == {"Sib1", "Sib2"} and not b2["invited"]
    assert db.messages.count_documents({"institution_id": A, "module": "parent_invite"}) == 1


def test_secure_link_tamper_expiry_and_setup(ctx):
    C, db, A = ctx["C"], ctx["db"], ctx["A"]
    uid = db.users.find_one({"role": "parent", "phone": "9000000001"})["id"]
    tok = server._make_secure_link(A, f"psetup:{uid}", 72)
    C.cookies.clear()
    r = C.get(f"/api/public/parent-setup/{tok}")
    assert r.status_code == 200 and len(r.json()["children"]) == 2 and r.json()["needs_password"] is True
    assert C.get(f"/api/public/parent-setup/{tok[:-2]}xx").status_code == 400
    expired = server._make_secure_link(A, f"psetup:{uid}", -1)
    assert C.get(f"/api/public/parent-setup/{expired}").status_code == 400
    # a non-invite secure link (other ref) is rejected
    other = server._make_secure_link(A, "report:abc", 72)
    assert C.get(f"/api/public/parent-setup/{other}").status_code == 400
    assert C.post(f"/api/public/parent-setup/{tok}", json={"password": "123"}).status_code == 400
    ok = C.post(f"/api/public/parent-setup/{tok}", json={"password": "Parent@46"})
    assert ok.status_code == 200 and ok.cookies.get("access_token")
    assert db.users.find_one({"id": uid})["must_change_password"] is False
    C.cookies.clear()
    email = db.users.find_one({"id": uid})["email"]
    assert C.post("/api/auth/login", json={"email": email, "password": "Parent@46"}).status_code == 200
    C.cookies.clear()


def test_ready_to_invite_after_phone_added(ctx):
    admin, db = ctx["admin"], ctx["db"]
    ready = {r["student_name"].split()[0] for r in admin.get("/api/students/ready-to-invite").json()["ready"]}
    assert "Late" not in ready and "Sib1" not in ready
    db.students.update_one({"id": ctx["late"]}, {"$set": {"guardian_phone": "9000000009", "guardian_name": "Lata"}})
    ready = admin.get("/api/students/ready-to-invite").json()["ready"]
    assert any(r["student_id"] == ctx["late"] for r in ready)
    r = admin.post(f"/api/students/{ctx['late']}/invite-parent", json={})
    assert r.status_code == 200 and r.json()["invited"][0]["action"] == "created"
    assert db.users.find_one({"role": "parent", "phone": "9000000009"})["student_ids"] == [ctx["late"]]
    ready = admin.get("/api/students/ready-to-invite").json()["ready"]
    assert not any(r["student_id"] == ctx["late"] for r in ready)


def test_paper_slip_code_registration(ctx):
    admin, C, db = ctx["admin"], ctx["C"], ctx["db"]
    slip = admin.post(f"/api/students/{ctx['nophone']}/setup-code").json()
    assert len(slip["code"]) == 8 and slip["admission_no"] == "P46-NOPH"
    rec = db.parent_setup_codes.find_one({"student_id": ctx["nophone"]})
    assert rec["code_hash"] != slip["code"] and rec["used"] is False
    C.cookies.clear()
    bad = C.post("/api/public/parent-register", json={"admission_no": "P46-NOPH", "code": "000000" if slip["code"] != "000000" else "111111",
                                                      "phone": "9000000077", "password": "Paper@46"})
    assert bad.status_code == 400
    ok = C.post("/api/public/parent-register", json={"admission_no": "P46-NOPH", "code": slip["code"],
                                                     "phone": "90000 00077", "name": "Paper Parent", "password": "Paper@46"})
    assert ok.status_code == 200 and ok.cookies.get("access_token")
    p = db.users.find_one({"role": "parent", "phone": "9000000077"})
    assert p["student_ids"] == [ctx["nophone"]] and p["must_change_password"] is False
    C.cookies.clear()
    # single-use
    again = C.post("/api/public/parent-register", json={"admission_no": "P46-NOPH", "code": slip["code"],
                                                        "phone": "9000000078", "password": "Paper@46"})
    assert again.status_code == 400
    C.cookies.clear()


def test_review_bucket_and_force_link(ctx):
    admin, db = ctx["admin"], ctx["db"]
    groups = admin.get("/api/students/invite-review").json()["review"]
    g = next(x for x in groups if x["phone"] == "9000000003")
    assert {s["guardian_name"] for s in g["students"]} == {"Anil", "Bindu"}
    r = admin.post("/api/students/invite-review/resolve",
                   json={"phone": "9000000003", "action": "force_link", "student_ids": [ctx["col1"], ctx["col2"]]})
    assert r.status_code == 200 and r.json()["status"] == "force_linked"
    p = db.users.find_one({"role": "parent", "phone": "9000000003"})
    assert set(p["student_ids"]) == {ctx["col1"], ctx["col2"]}
    assert not any(x["phone"] == "9000000003" for x in admin.get("/api/students/invite-review").json()["review"])
    assert admin.post("/api/students/invite-review/resolve", json={"phone": "x", "action": "nope"}).status_code == 400


def test_unit_principal_scope(ctx):
    PR = ctx["PR"]
    b = PR.post("/api/students/invite-parents", json={"all": True}).json()
    seen = set()
    for k in ("invited", "already_linked", "skipped_no_phone", "collisions_for_review"):
        seen |= _names(b[k])
    assert "Hss" in seen and not seen & {"Sib1", "Sib2", "NoPhone", "Late", "Col1"}
    assert PR.post(f"/api/students/{ctx['sib1']}/invite-parent", json={}).status_code == 403
    assert PR.post(f"/api/students/{ctx['nophone']}/setup-code").status_code == 403
    ready = PR.get("/api/students/ready-to-invite").json()["ready"]
    assert all(r["class"].startswith("Grade 11") for r in ready)
