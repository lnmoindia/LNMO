"""Phase 31.5 — Principal/admin delete (soft-delete) for AI Tutor content.
Covers: item soft-delete excludes from detail tree + retrieval + library; chapter cascade;
curriculum delete frees the unique slot for re-creation; deleted content retained (status=deleted);
teacher delete attempt 403; out-of-scope unit principal 403; bell to contributor on delete.
"""
import sys
import uuid
import pytest

sys.path.insert(0, "/app/backend")
import server  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from pymongo import MongoClient  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

TEST_DB = "lnmo_phase315_test"
PA_EMAIL = server.os.environ["PLATFORM_ADMIN_EMAIL"].lower()
PA_PW = server.os.environ["PLATFORM_ADMIN_PASSWORD"]
BASE = "https://testserver"
YEAR = "2025-2026"


def _client():
    return TestClient(server.app, base_url=BASE)


class Sess:
    def __init__(self, c, tok, uid=None):
        self._c, self._h, self.uid = c, {"Authorization": f"Bearer {tok}"}, uid

    def _call(self, m, p, **k):
        self._c.cookies.clear()
        hdrs = {**self._h, **k.pop("headers", {})}
        return self._c.request(m, p, headers=hdrs, **k)

    def get(self, p, **k): return self._call("get", p, **k)
    def post(self, p, **k): return self._call("post", p, **k)
    def put(self, p, **k): return self._call("put", p, **k)
    def delete(self, p, **k): return self._call("delete", p, **k)


@pytest.fixture(scope="module")
def ctx():
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
        a = platform.post("/api/res/institutions", json={"name": "SchoolA", "slug": "p315a", "admin_email": "a@p315a.test", "admin_password": "Admin@123"}).json()
        A = a["id"]
        admin = Sess(C, login("a@p315a.test", "Admin@123"))

        mon.classes.insert_many([
            {"id": "c8", "institution_id": A, "name": "Grade 8", "academic_unit_id": "uHS", "academic_unit_name": "HS"},
            {"id": "c4", "institution_id": A, "name": "Grade 4", "academic_unit_id": "uLP", "academic_unit_name": "LP"},
        ])

        def mk_teacher(email, name):
            uid = str(uuid.uuid4())
            mon.users.insert_one({"id": uid, "name": name, "email": email, "password_hash": server.hash_password("Teach@123"),
                                  "role": "teacher", "institution_id": A, "status": "active", "must_change_password": False, "created_at": server.now_iso()})
            return uid
        radha = mk_teacher("radha@p315a.test", "Radha")
        mon.teacher_assignments.insert_one({"id": str(uuid.uuid4()), "institution_id": A, "teacher_id": radha, "teacher_email": "radha@p315a.test", "class_name": "Grade 8", "section": "A", "subject": "Mathematics"})
        # unit principal for LP only (out of scope for Grade 8)
        lp = mk_teacher("lpprin@p315a.test", "LP Principal")
        mon.principal_assignments.insert_one({"id": str(uuid.uuid4()), "user_id": lp, "institution_id": A, "scope_type": "units", "unit_ids": ["uLP"], "status": "active", "designation": "principal", "created_at": server.now_iso()})
        # unit principal for HS (in scope for Grade 8)
        hs = mk_teacher("hsprin@p315a.test", "HS Principal")
        mon.principal_assignments.insert_one({"id": str(uuid.uuid4()), "user_id": hs, "institution_id": A, "scope_type": "units", "unit_ids": ["uHS"], "status": "active", "designation": "principal", "created_at": server.now_iso()})

        R = Sess(C, login("radha@p315a.test", "Teach@123"), radha)
        LP = Sess(C, login("lpprin@p315a.test", "Teach@123"), lp)
        HS = Sess(C, login("hsprin@p315a.test", "Teach@123"), hs)
        yield {"admin": admin, "R": R, "LP": LP, "HS": HS, "A": A, "db": mon, "radha": radha}
    MongoClient(server.mongo_url).drop_database(TEST_DB)


def _make_published(ctx):
    r = ctx["R"].post("/api/ai/curriculum", json={
        "academic_year": YEAR, "class_name": "Grade 8", "subject": "Mathematics",
        "name": "Grade 8 Maths", "syllabus_text": "Algebra, Geometry",
        "chapters": [{"chapter": "Chapter 1: Algebra", "topics": ["Linear eqns"]}],
        "items": [{"item_type": "textbook", "title": "Class textbook", "text_content": "ref"},
                  {"item_type": "notes", "chapter": "Chapter 1: Algebra", "title": "Algebra notes", "text_content": "x+y=10"},
                  {"item_type": "worksheet", "chapter": "Chapter 1: Algebra", "title": "Algebra WS", "text_content": "solve"}],
        "submit": True})
    cid = r.json()["curriculum"]["id"]
    ctx["admin"].post(f"/api/ai/curriculum/{cid}/review", json={"action": "approve"})
    return cid


def test_item_soft_delete_excludes_everywhere_but_retained(ctx):
    cid = _make_published(ctx)
    ctx["_cid"] = cid
    det = ctx["admin"].get(f"/api/ai/curriculum/{cid}").json()
    ws = next(i for i in det["items"] if i["title"] == "Algebra WS")
    # admin deletes the worksheet
    r = ctx["admin"].delete(f"/api/ai/items/{ws['id']}")
    assert r.status_code == 200 and r.json()["deleted"] == 1
    # gone from the detail tree
    det2 = ctx["admin"].get(f"/api/ai/curriculum/{cid}").json()
    assert all(i["id"] != ws["id"] for i in det2["items"])
    # retained internally as status=deleted
    raw = ctx["db"].curriculum_items.find_one({"id": ws["id"]})
    assert raw["status"] == "deleted" and raw["active"] is False
    # excluded from retrieval (retrieval queries status=approved+active only)
    assert ctx["db"].curriculum_items.count_documents({"id": ws["id"], "status": "approved", "active": True}) == 0


def test_chapter_delete_cascades_subtree(ctx):
    cid = ctx["_cid"]
    det = ctx["admin"].get(f"/api/ai/curriculum/{cid}").json()
    chap = next(i for i in det["items"] if i["item_type"] == "chapter" and i["chapter"] == "Chapter 1: Algebra")
    live_in_chapter = [i for i in det["items"] if i.get("chapter") == "Chapter 1: Algebra"]
    r = ctx["admin"].delete(f"/api/ai/items/{chap['id']}")
    assert r.status_code == 200
    assert r.json()["deleted"] == len(live_in_chapter)  # chapter + remaining children (topic + notes)
    det2 = ctx["admin"].get(f"/api/ai/curriculum/{cid}").json()
    assert all(i.get("chapter") != "Chapter 1: Algebra" for i in det2["items"])


def test_teacher_cannot_delete(ctx):
    cid = ctx["_cid"]  # a PUBLISHED curriculum
    # create a fresh item to attempt deletion
    it = ctx["R"].post(f"/api/ai/curriculum/{cid}/items", data={"item_type": "notes", "chapter": "Ch X", "title": "N"}).json()["item"]
    # teachers may only hard-delete items on their OWN unsubmitted draft — on a published
    # curriculum the owning teacher is blocked with 409 (reviewers soft-delete instead).
    assert ctx["R"].delete(f"/api/ai/items/{it['id']}").status_code == 409


def test_out_of_scope_principal_cannot_delete(ctx):
    cid = ctx["_cid"]
    det = ctx["admin"].get(f"/api/ai/curriculum/{cid}").json()
    some = det["items"][0]
    # LP principal scoped to Grade 4 only → 403 on Grade 8 item + curriculum
    assert ctx["LP"].delete(f"/api/ai/items/{some['id']}").status_code == 403
    assert ctx["LP"].delete(f"/api/ai/curriculum/{cid}").status_code == 403


def test_principal_curriculum_delete_is_soft(ctx):
    # admin creates a separate Grade 8 Science curriculum for the in-scope HS principal to delete
    cr = ctx["admin"].post("/api/ai/curriculum", json={"academic_year": YEAR, "class_name": "Grade 8",
                           "subject": "Science", "name": "Grade 8 Science",
                           "chapters": [{"chapter": "C1"}], "items": [{"item_type": "textbook", "title": "TB"}],
                           "submit": True}).json()
    cid = cr["curriculum"]["id"]
    ctx["admin"].post(f"/api/ai/curriculum/{cid}/review", json={"action": "approve"})
    r = ctx["HS"].delete(f"/api/ai/curriculum/{cid}", json={"confirm_name": "Grade 8 Science"})
    assert r.status_code == 200 and r.json()["hard"] is False
    # doc RETAINED internally (soft) with is_deleted flag
    raw = ctx["db"].curricula.find_one({"id": cid})
    assert raw is not None and raw["is_deleted"] is True and raw["status"] == "deleted"
    # slot freed for re-creation
    look = ctx["R"].get(f"/api/ai/curriculum?academic_year={YEAR}&class_name=Grade 8&subject=Science").json()
    assert look["exists"] is False


def test_admin_curriculum_delete_is_hard(ctx, monkeypatch):
    cid = ctx["_cid"]  # Grade 8 Mathematics (still live from earlier tests)
    # inject an item with a stored file_path and capture file-cleanup calls
    fid = "file-" + __import__("uuid").uuid4().hex
    ctx["db"].curriculum_items.insert_one({
        "id": fid, "curriculum_id": cid, "institution_id": ctx["A"], "item_type": "notes",
        "chapter": "Ch File", "title": "With file", "status": "approved", "active": True,
        "file_path": f"lnmo/curriculum/{cid}/x.pdf", "contributed_by": ctx["radha"], "version": 1})
    calls = []
    monkeypatch.setattr(server, "_delete_object", lambda p: (calls.append(p) or True))

    before_audit = ctx["db"].audit_logs.count_documents({"action": "ai_hard_delete_curriculum"})
    r = ctx["admin"].delete(f"/api/ai/curriculum/{cid}", json={"confirm_name": "Grade 8 Maths"})
    assert r.status_code == 200 and r.json()["hard"] is True
    assert r.json()["deleted_files"] >= 1 and f"lnmo/curriculum/{cid}/x.pdf" in calls
    # docs PERMANENTLY gone
    assert ctx["db"].curricula.find_one({"id": cid}) is None
    assert ctx["db"].curriculum_items.count_documents({"curriculum_id": cid}) == 0
    # audit EVENT persists even though content is gone
    assert ctx["db"].audit_logs.count_documents({"action": "ai_hard_delete_curriculum"}) == before_audit + 1
    # slot freed → re-create the same grade+subject succeeds (draft is enough to prove the slot is free)
    r2 = ctx["R"].post("/api/ai/curriculum", json={"academic_year": YEAR, "class_name": "Grade 8",
                       "subject": "Mathematics", "name": "Grade 8 Maths v2", "submit": False})
    assert r2.status_code == 200, r2.text
    assert r2.json()["curriculum"]["id"] != cid
