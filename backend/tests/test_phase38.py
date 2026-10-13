"""Phase 38 — teacher deletes own DRAFT curriculum (hard delete), with permission boundaries.
Throwaway DB; object storage + extraction mocked.
"""
import sys
import uuid
import pytest

sys.path.insert(0, "/app/backend")
import server  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from pymongo import MongoClient  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

TEST_DB = "lnmo_phase38_test"
PA_EMAIL = server.os.environ["PLATFORM_ADMIN_EMAIL"].lower()
PA_PW = server.os.environ["PLATFORM_ADMIN_PASSWORD"]
BASE = "https://testserver"
YEAR = "2025-2026"


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
    def delete(self, p, **k): return self._call("delete", p, **k)


@pytest.fixture(scope="module")
def ctx(monkeymodule):
    async def _init():
        server.client = AsyncIOMotorClient(server.mongo_url)
        server.db = server.client[TEST_DB]
    server.app.router.on_startup.insert(0, _init)
    MongoClient(server.mongo_url).drop_database(TEST_DB)
    mon = MongoClient(server.mongo_url)[TEST_DB]

    deleted_paths = []
    monkeymodule.setattr(server, "_put_object", lambda path, data, ct: True)
    monkeymodule.setattr(server, "_delete_object", lambda path: deleted_paths.append(path) or True)

    with _client() as C:
        def login(email, pw):
            r = C.post("/api/auth/login", json={"email": email, "password": pw})
            assert r.status_code == 200, r.text
            tok = r.cookies.get("access_token"); C.cookies.clear()
            return tok

        platform = Sess(C, login(PA_EMAIL, PA_PW))
        A = platform.post("/api/res/institutions", json={"name": "S", "slug": "p38", "admin_email": "a@p38.test", "admin_password": "Admin@123"}).json()["id"]
        admin = Sess(C, login("a@p38.test", "Admin@123"))
        mon.classes.insert_one({"id": "c8", "institution_id": A, "name": "Grade 8", "academic_unit_id": "uHS"})

        def mk_teacher(name, email, subject):
            tid = str(uuid.uuid4())
            mon.users.insert_one({"id": tid, "name": name, "email": email, "password_hash": server.hash_password("Teach@123"),
                                  "role": "teacher", "institution_id": A, "status": "active", "must_change_password": False, "created_at": server.now_iso()})
            mon.teacher_assignments.insert_one({"id": str(uuid.uuid4()), "institution_id": A, "teacher_id": tid, "teacher_email": email, "class_name": "Grade 8", "section": "A", "subject": subject})
            return Sess(C, login(email, "Teach@123")), tid

        R, rid = mk_teacher("Radha", "r@p38.test", "Mathematics")
        O, oid = mk_teacher("Omar", "o@p38.test", "Mathematics")
        for subj in ["Biology", "Chemistry", "History", "Geography", "Economics"]:
            mon.teacher_assignments.insert_one({"id": str(uuid.uuid4()), "institution_id": A, "teacher_id": rid, "teacher_email": "r@p38.test", "class_name": "Grade 8", "section": "A", "subject": subj})
        yield {"platform": platform, "admin": admin, "R": R, "O": O, "db": mon, "A": A, "deleted_paths": deleted_paths}
    MongoClient(server.mongo_url).drop_database(TEST_DB)


def _mk_draft(sess, subject, name):
    cid = sess.post("/api/ai/curriculum", json={
        "academic_year": YEAR, "class_name": "Grade 8", "subject": subject, "name": name,
        "chapters": [{"chapter": "Ch1"}], "items": [{"item_type": "textbook", "title": "TB"}], "submit": False}).json()["curriculum"]["id"]
    # add a material with a stored file path
    sess.post(f"/api/ai/curriculum/{cid}/items", data={"item_type": "notes", "title": "N", "chapter": "Ch1"},
              files={"file": ("n.txt", b"hello", "text/plain")})
    return cid


def test_teacher_deletes_own_draft_hard(ctx):
    R, db = ctx["R"], ctx["db"]
    cid = _mk_draft(R, "Mathematics", "Draft A")
    # a file path exists on the material
    paths_before = [i.get("file_path") for i in db.curriculum_items.find({"curriculum_id": cid}) if i.get("file_path")]
    assert paths_before
    r = R.delete(f"/api/ai/curriculum/{cid}")
    assert r.status_code == 200 and r.json()["hard"] is True
    # docs + items physically gone (hard delete)
    assert db.curricula.count_documents({"id": cid}) == 0
    assert db.curriculum_items.count_documents({"curriculum_id": cid}) == 0
    # best-effort file cleanup was attempted
    assert any(p in ctx["deleted_paths"] for p in paths_before)


def test_deleting_draft_frees_unique_slot(ctx):
    R = ctx["R"]
    cid1 = _mk_draft(R, "Biology", "Bio v1")
    assert R.delete(f"/api/ai/curriculum/{cid1}").status_code == 200
    # same grade+subject+year can be created again (slot freed)
    r = R.post("/api/ai/curriculum", json={"academic_year": YEAR, "class_name": "Grade 8", "subject": "Biology",
               "name": "Bio v2", "chapters": [{"chapter": "Ch1"}], "items": [{"item_type": "textbook", "title": "TB"}], "submit": False})
    assert r.status_code == 200


def test_teacher_cannot_delete_others_draft(ctx):
    R, O = ctx["R"], ctx["O"]
    cid = _mk_draft(R, "Chemistry", "Chem draft")
    assert O.delete(f"/api/ai/curriculum/{cid}").status_code == 403
    # owner can still delete it
    assert R.delete(f"/api/ai/curriculum/{cid}").status_code == 200


def test_teacher_cannot_delete_pending_or_published(ctx):
    R, admin = ctx["R"], ctx["admin"]
    # pending
    cid = _mk_draft(R, "History", "Hist draft")
    R.post(f"/api/ai/curriculum/{cid}/submit")
    assert R.delete(f"/api/ai/curriculum/{cid}").status_code == 409
    # published (admin approves)
    admin.post(f"/api/ai/curriculum/{cid}/review", json={"action": "approve"})
    assert R.delete(f"/api/ai/curriculum/{cid}").status_code == 409


def test_changes_requested_draft_is_deletable(ctx):
    R, admin = ctx["R"], ctx["admin"]
    cid = _mk_draft(R, "Geography", "Geo draft")
    R.post(f"/api/ai/curriculum/{cid}/submit")
    admin.post(f"/api/ai/curriculum/{cid}/review", json={"action": "changes", "note": "fix"})
    det = R.get(f"/api/ai/curriculum/{cid}").json()
    assert det["curriculum"]["status"] == "changes_requested"
    assert R.delete(f"/api/ai/curriculum/{cid}").status_code == 200


def test_admin_hard_delete_still_works(ctx):
    R, admin = ctx["R"], ctx["admin"]
    cid = _mk_draft(R, "Economics", "Eco")
    R.post(f"/api/ai/curriculum/{cid}/submit")
    admin.post(f"/api/ai/curriculum/{cid}/review", json={"action": "approve"})
    r = admin.delete(f"/api/ai/curriculum/{cid}")
    assert r.status_code == 200 and r.json()["hard"] is True
    assert ctx["db"].curricula.count_documents({"id": cid}) == 0
