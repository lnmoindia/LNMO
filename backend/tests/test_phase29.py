"""Phase 29 — AI Tutor part 1: shared curriculum KB + contribution/approval workflow.
Throwaway DB. No AI chat (Phase 30).

Covers: uniqueness invariant (409 on dup create); unauthorized teacher 403; create→submit→approve→
published; per-item independent approval; version chain (replace → old inactive, new v2); changes-
requested → revise → resubmit; unit-principal scope; ai_enabled only on published; PDF text extraction.
"""
import sys
import io
import uuid
import pytest

sys.path.insert(0, "/app/backend")
import server  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from pymongo import MongoClient  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

TEST_DB = "lnmo_phase29_test"
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
        return getattr(self._c, m)(p, headers={**self._h, **k.pop("headers", {})}, **k)

    def get(self, p, **k): return self._call("get", p, **k)
    def post(self, p, **k): return self._call("post", p, **k)
    def put(self, p, **k): return self._call("put", p, **k)


def _mini_pdf(text):
    """A tiny valid PDF whose text layer contains `text` (built via reportlab)."""
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.drawString(100, 700, text)
    c.showPage(); c.save()
    return buf.getvalue()


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
            return Sess(C, tok)

        platform = login(PA_EMAIL, PA_PW)
        a = platform.post("/api/res/institutions", json={"name": "SchoolA", "slug": "p29a", "admin_email": "a@p29a.test", "admin_password": "Admin@123"}).json()
        A = a["id"]
        admin = login("a@p29a.test", "Admin@123")

        mon.classes.insert_many([
            {"id": "c8", "institution_id": A, "name": "Grade 8", "academic_unit_id": "uHS", "academic_unit_name": "HS"},
            {"id": "c4", "institution_id": A, "name": "Grade 4", "academic_unit_id": "uLP", "academic_unit_name": "LP"},
        ])

        def mk_teacher(email, name):
            uid = str(uuid.uuid4())
            mon.users.insert_one({"id": uid, "name": name, "email": email, "password_hash": server.hash_password("Teach@123"),
                                  "role": "teacher", "institution_id": A, "status": "active", "must_change_password": False, "created_at": server.now_iso()})
            return uid
        radha = mk_teacher("radha@p29a.test", "Radha")   # Grade 8 Maths
        suma = mk_teacher("suma@p29a.test", "Suma")       # Grade 8 Maths (second teacher)
        other = mk_teacher("other@p29a.test", "Other")    # Grade 8 Science only
        for tid, email in [(radha, "radha@p29a.test"), (suma, "suma@p29a.test")]:
            mon.teacher_assignments.insert_one({"id": str(uuid.uuid4()), "institution_id": A, "teacher_id": tid, "teacher_email": email, "class_name": "Grade 8", "section": "A", "subject": "Mathematics"})
        mon.teacher_assignments.insert_one({"id": str(uuid.uuid4()), "institution_id": A, "teacher_id": other, "teacher_email": "other@p29a.test", "class_name": "Grade 8", "section": "A", "subject": "Science"})

        # unit principal for LP only (not HS/Grade 8)
        puid = mk_teacher("lpprin@p29a.test", "LP Principal")
        mon.principal_assignments.insert_one({"id": str(uuid.uuid4()), "user_id": puid, "institution_id": A, "scope_type": "units", "unit_ids": ["uLP"], "status": "active", "designation": "principal", "created_at": server.now_iso()})

        R = login("radha@p29a.test", "Teach@123")
        S = login("suma@p29a.test", "Teach@123")
        O = login("other@p29a.test", "Teach@123")
        LP = login("lpprin@p29a.test", "Teach@123")
        yield {"admin": admin, "R": R, "S": S, "O": O, "LP": LP, "A": A, "db": mon}
    MongoClient(server.mongo_url).drop_database(TEST_DB)


def _create_g8_maths(sess, submit=True):
    return sess.post("/api/ai/curriculum", json={
        "academic_year": YEAR, "class_name": "Grade 8", "subject": "Mathematics",
        "name": "Grade 8 Maths", "syllabus_text": "Algebra, Geometry",
        "chapters": [{"chapter": "Chapter 1: Algebra", "topics": ["Linear eqns"]}, {"chapter": "Chapter 2: Geometry"}],
        "items": [{"item_type": "textbook", "title": "Class textbook", "text_content": "textbook reference"},
                  {"item_type": "notes", "chapter": "Chapter 1: Algebra", "title": "Algebra notes", "text_content": "x+y=10"}],
        "submit": submit})


def test_unauthorized_teacher_cannot_create(ctx):
    r = ctx["O"].post("/api/ai/curriculum", json={"academic_year": YEAR, "class_name": "Grade 8",
                      "subject": "Mathematics", "name": "x", "submit": True})
    assert r.status_code == 403


def test_create_submit_and_uniqueness(ctx):
    r = _create_g8_maths(ctx["R"], submit=True)
    assert r.status_code == 200, r.text
    assert r.json()["curriculum"]["status"] == "pending" and r.json()["item_count"] == 5
    ctx["_cid"] = r.json()["curriculum"]["id"]
    # second create for same year+grade+subject → 409 (must contribute instead)
    dup = _create_g8_maths(ctx["S"], submit=True)
    assert dup.status_code == 409
    # lookup routes to contribute
    look = ctx["S"].get(f"/api/ai/curriculum?academic_year={YEAR}&class_name=Grade 8&subject=Mathematics").json()
    assert look["exists"] is True and look["can_contribute"] is True


def test_admin_approve_publishes_and_approves_initial_items(ctx):
    cid = ctx["_cid"]
    pend = ctx["admin"].get("/api/ai/approvals/curricula").json()["curricula"]
    assert any(c["id"] == cid for c in pend)
    res = ctx["admin"].post(f"/api/ai/curriculum/{cid}/review", json={"action": "approve"}).json()
    assert res["status"] == "published" and res["approved_items"] == 5
    det = ctx["admin"].get(f"/api/ai/curriculum/{cid}").json()
    assert det["curriculum"]["status"] == "published"
    assert all(i["status"] == "approved" for i in det["items"])


def test_second_teacher_contribution_independent_approval(ctx):
    cid = ctx["_cid"]
    # Suma contributes a worksheet to Chapter 1 → pending
    r = ctx["S"].post(f"/api/ai/curriculum/{cid}/items", data={
        "item_type": "worksheet", "chapter": "Chapter 1: Algebra", "title": "Algebra worksheet",
        "description": "practice"})
    assert r.status_code == 200, r.text
    wid = r.json()["item"]["id"]
    ctx["_wid"] = wid
    # pending items queue shows it, grouped
    groups = ctx["admin"].get("/api/ai/approvals/items").json()["groups"]
    pending_ids = [i["id"] for g in groups for i in g["items"]]
    assert wid in pending_ids
    # Radha's already-approved items are NOT in the pending queue (never re-approved)
    det_before = ctx["admin"].get(f"/api/ai/curriculum/{cid}").json()["items"]
    radha_approved = [i["id"] for i in det_before if i["contributor_name"] == "Radha" and i["status"] == "approved"]
    assert radha_approved and not (set(radha_approved) & set(pending_ids))
    # approve just Suma's item
    ctx["admin"].post(f"/api/ai/items/{wid}/review", json={"action": "approve"})
    det = ctx["admin"].get(f"/api/ai/curriculum/{cid}").json()["items"]
    w = next(i for i in det if i["id"] == wid)
    assert w["status"] == "approved" and w["active"] is True
    # both contributors present
    assert {"Radha", "Suma"} <= {i["contributor_name"] for i in det}


def test_version_chain_replace(ctx):
    cid, wid = ctx["_cid"], ctx["_wid"]
    r = ctx["S"].post(f"/api/ai/curriculum/{cid}/items", data={
        "item_type": "worksheet", "chapter": "Chapter 1: Algebra", "title": "Algebra worksheet v2",
        "supersedes": wid})
    assert r.status_code == 200
    v2 = r.json()["item"]
    assert v2["version"] == 2 and v2["supersedes"] == wid
    # old still active until the replacement is approved
    old = next(i for i in ctx["admin"].get(f"/api/ai/curriculum/{cid}").json()["items"] if i["id"] == wid)
    assert old["active"] is True
    ctx["admin"].post(f"/api/ai/items/{v2['id']}/review", json={"action": "approve"})
    items = {i["id"]: i for i in ctx["admin"].get(f"/api/ai/curriculum/{cid}").json()["items"]}
    assert items[wid]["active"] is False and items[wid]["status"] == "approved"  # retained, inactive
    assert items[v2["id"]]["active"] is True and items[v2["id"]]["version"] == 2


def test_changes_requested_revise_resubmit(ctx):
    # new curriculum (different subject) → request changes → revise → resubmit → approve
    c = ctx["R"].post("/api/ai/curriculum", json={"academic_year": YEAR, "class_name": "Grade 8",
                      "subject": "Physics", "name": "G8 Physics", "syllabus_text": "draft", "submit": True})
    assert c.status_code == 403  # Radha doesn't teach Physics
    # admin creates it instead
    c = ctx["admin"].post("/api/ai/curriculum", json={"academic_year": YEAR, "class_name": "Grade 8",
                         "subject": "Physics", "name": "G8 Physics", "syllabus_text": "draft",
                         "chapters": [{"chapter": "Motion"}], "items": [{"item_type": "textbook", "title": "Physics TB"}],
                         "submit": True})
    cid = c.json()["curriculum"]["id"]
    ctx["admin"].post(f"/api/ai/curriculum/{cid}/review", json={"action": "changes", "note": "add chapters"})
    assert ctx["admin"].get(f"/api/ai/curriculum/{cid}").json()["curriculum"]["status"] == "changes_requested"
    ctx["admin"].put(f"/api/ai/curriculum/{cid}", json={"syllabus_text": "fuller syllabus"})
    ctx["admin"].post(f"/api/ai/curriculum/{cid}/submit")
    assert ctx["admin"].get(f"/api/ai/curriculum/{cid}").json()["curriculum"]["status"] == "pending"
    ctx["admin"].post(f"/api/ai/curriculum/{cid}/review", json={"action": "approve"})
    assert ctx["admin"].get(f"/api/ai/curriculum/{cid}").json()["curriculum"]["status"] == "published"


def test_unit_principal_scope(ctx):
    # LP principal cannot see Grade 8 pending curricula, and cannot review a Grade 8 curriculum
    pend = ctx["LP"].get("/api/ai/approvals/curricula").json()["curricula"]
    assert all(c["class_name"] != "Grade 8" for c in pend)
    r = ctx["LP"].post(f"/api/ai/curriculum/{ctx['_cid']}/review", json={"action": "approve"})
    assert r.status_code == 403


def test_ai_enabled_only_on_published(ctx):
    cid = ctx["_cid"]
    ok = ctx["admin"].put(f"/api/ai/curriculum/{cid}/ai-enabled", json={"enabled": True})
    assert ok.status_code == 200 and ok.json()["ai_enabled"] is True
    # a draft curriculum cannot be enabled
    d = ctx["admin"].post("/api/ai/curriculum", json={"academic_year": YEAR, "class_name": "Grade 4",
                         "subject": "English", "name": "d", "submit": False}).json()["curriculum"]
    bad = ctx["admin"].put(f"/api/ai/curriculum/{d['id']}/ai-enabled", json={"enabled": True})
    assert bad.status_code == 400


def test_pdf_text_extraction(ctx):
    cid = ctx["_cid"]
    pdf = _mini_pdf("PHOTOSYNTHESIS CHAPTER TEXT")
    r = ctx["R"].post(f"/api/ai/curriculum/{cid}/items",
                      data={"item_type": "reference", "chapter": "Chapter 2: Geometry", "title": "ref.pdf"},
                      files={"file": ("ref.pdf", io.BytesIO(pdf), "application/pdf")})
    assert r.status_code == 200, r.text
    iid = r.json()["item"]["id"]
    assert r.json()["item"]["has_file"] and r.json()["item"]["has_extracted_text"]
    hist = ctx["admin"].get(f"/api/ai/curriculum/{cid}/history").json()["history"]
    item = next(i for i in hist if i["id"] == iid)
    assert item["has_extracted_text"]
    # file download works
    assert ctx["R"].get(f"/api/ai/items/{iid}/file").status_code == 200
