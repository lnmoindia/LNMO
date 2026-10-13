"""Phase 31 — Curriculum fixes: chapter/topic contribution on published curricula,
full detail view, review comments + resolution + bell notifications, open-comment counts,
and authorization constraints. Throwaway DB.
"""
import sys
import uuid
import pytest

sys.path.insert(0, "/app/backend")
import server  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from pymongo import MongoClient  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

TEST_DB = "lnmo_phase31_test"
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
        return getattr(self._c, m)(p, headers={**self._h, **k.pop("headers", {})}, **k)

    def get(self, p, **k): return self._call("get", p, **k)
    def post(self, p, **k): return self._call("post", p, **k)
    def put(self, p, **k): return self._call("put", p, **k)


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

        pa_tok = login(PA_EMAIL, PA_PW)
        platform = Sess(C, pa_tok)
        a = platform.post("/api/res/institutions", json={"name": "SchoolA", "slug": "p31a", "admin_email": "a@p31a.test", "admin_password": "Admin@123"}).json()
        A = a["id"]
        admin = Sess(C, login("a@p31a.test", "Admin@123"))

        mon.classes.insert_one({"id": "c8", "institution_id": A, "name": "Grade 8", "academic_unit_id": "uHS", "academic_unit_name": "HS"})

        def mk_teacher(email, name):
            uid = str(uuid.uuid4())
            mon.users.insert_one({"id": uid, "name": name, "email": email, "password_hash": server.hash_password("Teach@123"),
                                  "role": "teacher", "institution_id": A, "status": "active", "must_change_password": False, "created_at": server.now_iso()})
            return uid
        radha = mk_teacher("radha@p31a.test", "Radha")   # Grade 8 Maths (owner)
        suma = mk_teacher("suma@p31a.test", "Suma")       # Grade 8 Maths (second teacher)
        other = mk_teacher("other@p31a.test", "Other")    # Grade 8 Science only
        for tid, email in [(radha, "radha@p31a.test"), (suma, "suma@p31a.test")]:
            mon.teacher_assignments.insert_one({"id": str(uuid.uuid4()), "institution_id": A, "teacher_id": tid, "teacher_email": email, "class_name": "Grade 8", "section": "A", "subject": "Mathematics"})
        mon.teacher_assignments.insert_one({"id": str(uuid.uuid4()), "institution_id": A, "teacher_id": other, "teacher_email": "other@p31a.test", "class_name": "Grade 8", "section": "A", "subject": "Science"})

        R = Sess(C, login("radha@p31a.test", "Teach@123"), radha)
        S = Sess(C, login("suma@p31a.test", "Teach@123"), suma)
        O = Sess(C, login("other@p31a.test", "Teach@123"), other)
        yield {"admin": admin, "R": R, "S": S, "O": O, "A": A, "db": mon,
               "radha": radha, "suma": suma, "other": other}
    MongoClient(server.mongo_url).drop_database(TEST_DB)


def _bell_count(mon, uid, ntype):
    return mon.notifications.count_documents({"user_id": uid, "type": ntype})


def test_setup_published_curriculum(ctx):
    r = ctx["R"].post("/api/ai/curriculum", json={
        "academic_year": YEAR, "class_name": "Grade 8", "subject": "Mathematics",
        "name": "Grade 8 Maths", "syllabus_text": "Algebra, Geometry",
        "chapters": [{"chapter": "Chapter 1: Algebra", "topics": ["Linear eqns"]}],
        "items": [{"item_type": "textbook", "title": "Class textbook", "text_content": "ref"},
                  {"item_type": "notes", "chapter": "Chapter 1: Algebra", "title": "Algebra notes", "text_content": "x+y=10"}],
        "submit": True})
    assert r.status_code == 200, r.text
    cid = r.json()["curriculum"]["id"]
    ctx["_cid"] = cid
    assert ctx["admin"].post(f"/api/ai/curriculum/{cid}/review", json={"action": "approve"}).json()["status"] == "published"


def test_chapter_added_to_published_goes_pending_then_approved_then_visible(ctx):
    cid = ctx["_cid"]
    # Teacher adds a NEW chapter to the already-published curriculum
    r = ctx["R"].post(f"/api/ai/curriculum/{cid}/items", data={
        "item_type": "chapter", "chapter": "Chapter 2: Geometry", "title": "Chapter 2: Geometry"})
    assert r.status_code == 200, r.text
    chid = r.json()["item"]["id"]
    assert r.json()["item"]["status"] == "pending"

    # Add a topic under the pending chapter
    tr = ctx["R"].post(f"/api/ai/curriculum/{cid}/items", data={
        "item_type": "topic", "chapter": "Chapter 2: Geometry", "topic": "Triangles", "title": "Triangles"})
    assert tr.status_code == 200, tr.text

    # Pending chapter visible to contributor in detail with pending status
    det = ctx["R"].get(f"/api/ai/curriculum/{cid}").json()
    ch = next(i for i in det["items"] if i["id"] == chid)
    assert ch["status"] == "pending"

    # Shows in the admin pending-items queue
    groups = ctx["admin"].get("/api/ai/approvals/items").json()["groups"]
    pending_ids = [i["id"] for g in groups for i in g["items"]]
    assert chid in pending_ids

    # Approve → becomes approved + active + visible in approved tree
    assert ctx["admin"].post(f"/api/ai/items/{chid}/review", json={"action": "approve"}).json()["status"] == "approved"
    det2 = ctx["admin"].get(f"/api/ai/curriculum/{cid}").json()
    ch2 = next(i for i in det2["items"] if i["id"] == chid)
    assert ch2["status"] == "approved" and ch2["active"] is True


def test_detail_completeness(ctx):
    det = ctx["admin"].get(f"/api/ai/curriculum/{ctx['_cid']}").json()
    assert set(["curriculum", "items", "comments", "open_comment_count", "can_review", "can_contribute"]).issubset(det)
    assert det["curriculum"]["syllabus_text"]
    it = det["items"][0]
    for f in ("item_type", "status", "version", "contributor_name", "contributed_at"):
        assert f in it
    assert det["can_review"] is True  # admin


def test_comment_notifies_teacher_resolve_notifies_reviewer(ctx):
    cid, mon = ctx["_cid"], ctx["db"]
    before_teacher = _bell_count(mon, ctx["radha"], "ai_curriculum_comment")
    # Admin leaves a curriculum-level comment → contributing teacher (owner Radha) notified
    cr = ctx["admin"].post(f"/api/ai/curriculum/{cid}/comments", json={"text": "Please expand the algebra notes."})
    assert cr.status_code == 200, cr.text
    cmid = cr.json()["comment"]["id"]
    assert cr.json()["comment"]["status"] == "open"
    assert _bell_count(mon, ctx["radha"], "ai_curriculum_comment") == before_teacher + 1

    # Open-comment count surfaces on the detail
    assert ctx["admin"].get(f"/api/ai/curriculum/{cid}").json()["open_comment_count"] >= 1

    # Teacher sees it and resolves with a reply → commenting reviewer (admin) notified
    admin_uid = mon.users.find_one({"email": "a@p31a.test"})["id"]
    before_admin = _bell_count(mon, admin_uid, "ai_comment_resolved")
    seen = ctx["R"].get(f"/api/ai/curriculum/{cid}/comments").json()["comments"]
    assert any(c["id"] == cmid for c in seen)
    rr = ctx["R"].post(f"/api/ai/comments/{cmid}/resolve", json={"reply": "Expanded, thanks."})
    assert rr.status_code == 200, rr.text
    assert _bell_count(mon, admin_uid, "ai_comment_resolved") == before_admin + 1
    after = ctx["admin"].get(f"/api/ai/curriculum/{cid}").json()
    resolved = next(c for c in after["comments"] if c["id"] == cmid)
    assert resolved["status"] == "resolved" and resolved["reply"] == "Expanded, thanks."


def test_authorization_constraints(ctx):
    cid = ctx["_cid"]
    # A plain teacher cannot leave review comments (reviewers only)
    assert ctx["R"].post(f"/api/ai/curriculum/{cid}/comments", json={"text": "x"}).status_code == 403
    # A teacher who doesn't teach this grade+subject cannot view/contribute
    assert ctx["O"].get(f"/api/ai/curriculum/{cid}/comments").status_code == 403
    assert ctx["O"].post(f"/api/ai/curriculum/{cid}/items", data={"item_type": "chapter", "chapter": "Hack", "title": "Hack"}).status_code == 403

    # Admin comments targeting the OWNER (Radha); a different teacher (Suma) cannot resolve it
    cmid = ctx["admin"].post(f"/api/ai/curriculum/{cid}/comments", json={"text": "Owner-targeted note"}).json()["comment"]["id"]
    assert ctx["S"].post(f"/api/ai/comments/{cmid}/resolve", json={}).status_code == 403
    # The targeted owner can resolve
    assert ctx["R"].post(f"/api/ai/comments/{cmid}/resolve", json={}).status_code == 200


def test_item_level_comment_targets_item_contributor(ctx):
    cid, mon = ctx["_cid"], ctx["db"]
    # Suma contributes a worksheet (pending)
    wid = ctx["S"].post(f"/api/ai/curriculum/{cid}/items", data={
        "item_type": "worksheet", "chapter": "Chapter 1: Algebra", "title": "WS"}).json()["item"]["id"]
    before = _bell_count(mon, ctx["suma"], "ai_curriculum_comment")
    # Admin comments on that item → Suma (the item contributor) is notified, not the owner
    cr = ctx["admin"].post(f"/api/ai/curriculum/{cid}/comments", json={"text": "Fix Q3", "item_id": wid})
    assert cr.status_code == 200
    assert cr.json()["comment"]["item_id"] == wid
    assert _bell_count(mon, ctx["suma"], "ai_curriculum_comment") == before + 1
    # Owner Radha (not the target) still cannot resolve Suma's item comment
    cmid = cr.json()["comment"]["id"]
    assert ctx["R"].post(f"/api/ai/comments/{cmid}/resolve", json={}).status_code == 403
    assert ctx["S"].post(f"/api/ai/comments/{cmid}/resolve", json={}).status_code == 200
