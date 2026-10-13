"""Phase 47 — parent phone login, invite progress funnel + reminders, bulk paper slips.
Throwaway DB, STUB comm provider.
"""
import sys
import uuid
import pytest

sys.path.insert(0, "/app/backend")
import server  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from pymongo import MongoClient  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

TEST_DB = "lnmo_phase47_test"
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


def _parent(mon, iid, phone, pw="Par@1234", status="active", must=False, invited=True, sids=None):
    uid = str(uuid.uuid4())
    mon.users.insert_one({"id": uid, "name": f"P{phone}", "email": f"p{phone}.{uid[:4]}@x.parent.invite", "phone": phone,
                          "password_hash": server.hash_password(pw), "role": "parent", "institution_id": iid,
                          "status": status, "must_change_password": must, "invited": invited,
                          "student_ids": sids or [], "created_at": server.now_iso()})
    return uid


def _stu(mon, A, first, grade, phone=None):
    sid = str(uuid.uuid4())
    doc = {"id": sid, "institution_id": A, "first_name": first, "last_name": "Q", "class_name": f"Grade {grade}",
           "section": "A", "enrollment_status": "enrolled", "admission_no": f"Q-{first}", "created_at": server.now_iso()}
    if phone:
        doc.update({"guardian_phone": phone, "guardian_name": f"G{phone}"})
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
    with TestClient(server.app, base_url="https://testserver") as C:
        def login(email, pw):
            r = C.post("/api/auth/login", json={"email": email, "password": pw})
            assert r.status_code == 200, r.text
            tok = r.cookies.get("access_token"); C.cookies.clear()
            return tok
        platform = Sess(C, login(PA_EMAIL, PA_PW))
        A = platform.post("/api/res/institutions", json={"name": "Alpha", "slug": "p47a", "domain": "p47a.test",
                          "admin_email": "a@p47a.test", "admin_password": "Admin@123"}).json()["id"]
        B = platform.post("/api/res/institutions", json={"name": "Beta", "slug": "p47b",
                          "admin_email": "a@p47b.test", "admin_password": "Admin@123"}).json()["id"]
        admin = Sess(C, login("a@p47a.test", "Admin@123"))
        mon.academic_units.insert_many([{"id": "uLP", "institution_id": A, "name": "LP"},
                                        {"id": "uHS", "institution_id": A, "name": "HS"}])
        for g, u in [(5, "uLP"), (8, "uHS")]:
            mon.classes.insert_one({"id": f"c{g}", "institution_id": A, "name": f"Grade {g}", "grade_level": str(g), "academic_unit_id": u})
        ptid = str(uuid.uuid4())
        mon.users.insert_one({"id": ptid, "name": "LPP", "email": "pr@p47a.test", "password_hash": server.hash_password("Prin@123"),
                              "role": "teacher", "institution_id": A, "status": "active", "must_change_password": False,
                              "created_at": server.now_iso()})
        mon.principal_assignments.insert_one({"id": str(uuid.uuid4()), "institution_id": A, "user_id": ptid,
                                              "scope_type": "units", "unit_ids": ["uLP"], "designation": "principal"})
        PR = Sess(C, login("pr@p47a.test", "Prin@123"))
        # login fixtures
        uniq = _parent(mon, A, "9100000001")
        _parent(mon, A, "9100000002", pw="AlphaPw1")
        dupB = _parent(mon, B, "9100000002", pw="BetaPw12")
        _parent(mon, A, "9100000003")
        _parent(mon, B, "9100000003", status="inactive")
        mon.users.insert_one({"id": str(uuid.uuid4()), "name": "T", "email": "t@p47a.test", "phone": "9100000009",
                              "password_hash": server.hash_password("Teach@123"), "role": "teacher", "institution_id": A,
                              "status": "active", "created_at": server.now_iso()})
        # funnel fixtures: Grade 8 → 3 phone students (2 siblings share a phone) + 1 no-phone; Grade 5 → 3 no-phone + 1 phone
        s8 = {"a": _stu(mon, A, "A8", 8, "9200000001"), "b": _stu(mon, A, "B8", 8, "9200000001"),
              "c": _stu(mon, A, "C8", 8, "9200000002"), "d": _stu(mon, A, "D8", 8, "9200000003"),
              "n": _stu(mon, A, "N8", 8)}
        s5 = {k: _stu(mon, A, f"{k}5", 5) for k in ("x", "y", "z")}
        s5["p"] = _stu(mon, A, "P5", 5, "9200000005")
        yield {"C": C, "admin": admin, "PR": PR, "A": A, "B": B, "db": mon, "uniq": uniq, "dupB": dupB, "s8": s8, "s5": s5}
    MongoClient(server.mongo_url).drop_database(TEST_DB)


def _login(C, ident, pw, **ctx):
    C.cookies.clear()
    r = C.post("/api/auth/login", json={"email": ident, "password": pw, **ctx})
    C.cookies.clear()
    return r


# ---------- 1. phone login ----------
def test_phone_login_normalization_generic_unique(ctx):
    C = ctx["C"]
    for ident in ("9100000001", "+91 91000 00001", "91-9100000001", "091000-00001", "(910) 000-0001"):
        r = _login(C, ident, "Par@1234")
        assert r.status_code == 200, (ident, r.text)
        assert r.json()["id"] == ctx["uniq"] and r.json()["role"] == "parent"
    # only an inactive duplicate in another school → still globally unique among ACTIVE
    assert _login(C, "9100000003", "Par@1234").status_code == 200


def test_phone_login_ambiguous_and_branded(ctx):
    C, db = ctx["C"], ctx["db"]
    r = _login(C, "9100000002", "AlphaPw1")
    assert r.status_code == 400 and "school's login link" in r.json()["detail"]
    rb = _login(C, "9100000002", "BetaPw12", slug="p47b")
    assert rb.status_code == 200 and rb.json()["id"] == ctx["dupB"]
    ra = _login(C, "+91 9100000002", "AlphaPw1", domain="p47a.test")
    assert ra.status_code == 200 and ra.json()["institution_id"] == ctx["A"]
    # branded context never crosses schools: Beta's password at Alpha → 401
    assert _login(C, "9100000002", "BetaPw12", slug="p47a").status_code == 401
    db.login_attempts.delete_many({})


def test_phone_login_failures_and_email_regression(ctx):
    C, db = ctx["C"], ctx["db"]
    r = _login(C, "9199999999", "whatever1")
    assert r.status_code == 401 and r.json()["detail"] == "Invalid mobile number or password"
    assert _login(C, "9100000001", "wrongpass").status_code == 401
    pu = db.users.find_one({"role": "parent", "phone": "9100000001"}, {"id": 1})
    assert db.login_attempts.find_one({"identifier": f"user:{pu['id']}"})["count"] == 1
    # teachers are never matched by phone
    assert _login(C, "9100000009", "Teach@123").status_code == 401
    # not a phone/email and no school context → admission-number guidance (Phase 55)
    r = _login(C, "12345", "x12345")
    assert r.status_code == 400 and "school's login link" in r.json()["detail"]
    # email login unchanged
    assert _login(C, "t@p47a.test", "Teach@123").status_code == 200
    assert _login(C, "A@P47A.TEST", "Admin@123").status_code == 200
    # lockout per phone identifier
    for _ in range(server.LOCK_MAX):
        _login(C, "9100000001", "wrongpass")
    assert _login(C, "9100000001", "Par@1234").status_code == 429
    db.login_attempts.delete_many({})
    assert _login(C, "9100000001", "Par@1234").status_code == 200


# ---------- 2. progress funnel + reminders ----------
def test_progress_funnel_math(ctx):
    admin, db, s8 = ctx["admin"], ctx["db"], ctx["s8"]
    b = admin.post("/api/students/invite-parents", json={"class_ids": ["c8"]}).json()
    assert len(b["invited"]) == 4 and len(b["skipped_no_phone"]) == 1
    # parent of D8 completes setup
    uid = db.users.find_one({"role": "parent", "phone": "9200000003"})["id"]
    tok = server._make_secure_link(ctx["A"], f"psetup:{uid}", 72)
    ctx["C"].cookies.clear()
    assert ctx["C"].post(f"/api/public/parent-setup/{tok}", json={"password": "Done@123"}).status_code == 200
    ctx["C"].cookies.clear()
    rows = {r["class_name"]: r for r in admin.get("/api/students/invite-progress").json()["classes"]}
    g8 = rows["Grade 8"]
    assert (g8["enrolled"], g8["invited"], g8["setup_completed"], g8["pending"], g8["no_phone"], g8["not_invited"]) == (5, 4, 1, 3, 1, 0)
    g5 = rows["Grade 5"]
    assert (g5["enrolled"], g5["invited"], g5["no_phone"], g5["not_invited"]) == (4, 0, 3, 1)
    assert list(rows) == ["Grade 5", "Grade 8"]


def test_reminder_dedupe_and_quota(ctx):
    admin, db, A = ctx["admin"], ctx["db"], ctx["A"]
    q0 = db.institutions.find_one({"id": A})["comm"]["quota"]["whatsapp"]["used"]
    m0 = db.messages.count_documents({"institution_id": A, "module": "parent_invite"})
    r = admin.post("/api/students/invite-reminder", json={"class_id": "c8"}).json()
    # pending parents: shared-phone sibling account (A8+B8) + C8's → 2 distinct parents
    assert r["ok"] and r["pending_parents"] == 2 and r["sent"] == 2
    assert db.institutions.find_one({"id": A})["comm"]["quota"]["whatsapp"]["used"] == q0 + 2
    assert db.messages.count_documents({"institution_id": A, "module": "parent_invite"}) == m0 + 2
    again = admin.post("/api/students/invite-reminder", json={"class_id": "c8"}).json()
    assert again["ok"] is False and again["code"] == "already_sent_today" and again["sent"] == 0
    assert db.institutions.find_one({"id": A})["comm"]["quota"]["whatsapp"]["used"] == q0 + 2
    rows = {x["class_name"]: x for x in admin.get("/api/students/invite-progress").json()["classes"]}
    assert rows["Grade 8"]["reminder_sent_today"] is True and rows["Grade 5"]["reminder_sent_today"] is False
    # Grade 5 has nobody pending → ok with 0 sent
    r5 = admin.post("/api/students/invite-reminder", json={"class_id": "c5"}).json()
    assert r5["ok"] and r5["sent"] == 0
    assert admin.post("/api/students/invite-reminder", json={"class_id": "nope"}).status_code == 404


# ---------- 3. bulk slips ----------
def test_bulk_slips_one_per_student_and_regeneration(ctx):
    admin, db, C, s5 = ctx["admin"], ctx["db"], ctx["C"], ctx["s5"]
    r = admin.post("/api/students/setup-codes/bulk", json={"class_ids": ["c5"]}).json()
    assert r["count"] == 3 and {x["student_id"] for x in r["slips"]} == {s5["x"], s5["y"], s5["z"]}
    assert len({x["code"] for x in r["slips"]}) == 3
    for sid in (s5["x"], s5["y"], s5["z"]):
        assert db.parent_setup_codes.count_documents({"student_id": sid, "used": False}) == 1
    old = next(x["code"] for x in r["slips"] if x["student_id"] == s5["x"])
    r2 = admin.post("/api/students/setup-codes/bulk", json={"class_ids": ["c5"]}).json()
    new = next(x["code"] for x in r2["slips"] if x["student_id"] == s5["x"])
    assert new != old and db.parent_setup_codes.count_documents({"student_id": s5["x"], "used": False}) == 1
    C.cookies.clear()
    assert C.post("/api/public/parent-register", json={"code": old, "phone": "9300000001", "password": "Slip@123"}).status_code == 400
    ok = C.post("/api/public/parent-register", json={"code": new, "phone": "9300000001", "password": "Slip@123"})
    assert ok.status_code == 200
    C.cookies.clear()
    # linked student drops out of the next bulk run; phone student never included
    r3 = admin.post("/api/students/setup-codes/bulk", json={"class_ids": ["c5"]}).json()
    assert {x["student_id"] for x in r3["slips"]} == {s5["y"], s5["z"]}
    # Grade 8 no-phone student only
    r8 = admin.post("/api/students/setup-codes/bulk", json={"class_names": ["Grade 8"]}).json()
    assert [x["student_id"] for x in r8["slips"]] == [ctx["s8"]["n"]]


# ---------- principal scope on all three ----------
def test_principal_scope(ctx):
    PR = ctx["PR"]
    names = [r["class_name"] for r in PR.get("/api/students/invite-progress").json()["classes"]]
    assert names == ["Grade 5"]
    assert PR.post("/api/students/invite-reminder", json={"class_id": "c8"}).status_code == 403
    assert PR.post("/api/students/setup-codes/bulk", json={"class_ids": ["c8"]}).status_code == 403
    allr = PR.post("/api/students/setup-codes/bulk", json={"all": True}).json()
    assert allr["count"] == 2 and all(x["class"].startswith("Grade 5") for x in allr["slips"])
