"""Phase 37 — draft resume/edit round-trip, bulk library upload, reorder chapters + move materials.
Throwaway DB; object storage + extraction mocked.
"""
import sys
import json
import time
import uuid
import pytest

sys.path.insert(0, "/app/backend")
import server  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from pymongo import MongoClient  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

TEST_DB = "lnmo_phase37_test"
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
    def put(self, p, **k): return self._call("put", p, **k)
    def delete(self, p, **k): return self._call("delete", p, **k)


@pytest.fixture(scope="module")
def ctx(monkeymodule):
    async def _init():
        server.client = AsyncIOMotorClient(server.mongo_url)
        server.db = server.client[TEST_DB]
    server.app.router.on_startup.insert(0, _init)
    MongoClient(server.mongo_url).drop_database(TEST_DB)
    mon = MongoClient(server.mongo_url)[TEST_DB]

    monkeymodule.setattr(server, "_put_object", lambda path, data, ct: True)
    monkeymodule.setattr(server, "_delete_object", lambda path: True)
    monkeymodule.setattr(server, "_ai_extract_text", lambda content, mime, name: f"EXTRACTED::{len(content)}")
    monkeymodule.setattr(server, "_lib_extract_bg", lambda lid, content, mime, name: mon.platform_library.update_one(
        {"id": lid}, {"$set": {"extracted_text": f"EXTRACTED::{len(content)}", "processing": False}}))

    with _client() as C:
        def login(email, pw):
            r = C.post("/api/auth/login", json={"email": email, "password": pw})
            assert r.status_code == 200, r.text
            tok = r.cookies.get("access_token"); C.cookies.clear()
            return tok

        platform = Sess(C, login(PA_EMAIL, PA_PW))
        A = platform.post("/api/res/institutions", json={"name": "S", "slug": "p37a", "admin_email": "a@p37a.test", "admin_password": "Admin@123"}).json()["id"]
        admin = Sess(C, login("a@p37a.test", "Admin@123"))
        mon.classes.insert_one({"id": "c8", "institution_id": A, "name": "Grade 8", "academic_unit_id": "uHS"})
        # owning teacher
        tid = str(uuid.uuid4())
        mon.users.insert_one({"id": tid, "name": "Radha", "email": "r@p37a.test", "password_hash": server.hash_password("Teach@123"),
                              "role": "teacher", "institution_id": A, "status": "active", "must_change_password": False, "created_at": server.now_iso()})
        mon.teacher_assignments.insert_one({"id": str(uuid.uuid4()), "institution_id": A, "teacher_id": tid, "teacher_email": "r@p37a.test", "class_name": "Grade 8", "section": "A", "subject": "Mathematics"})
        R = Sess(C, login("r@p37a.test", "Teach@123"))
        # an unrelated teacher (different subject) for permission checks
        uid = str(uuid.uuid4())
        mon.users.insert_one({"id": uid, "name": "Other", "email": "o@p37a.test", "password_hash": server.hash_password("Teach@123"),
                              "role": "teacher", "institution_id": A, "status": "active", "must_change_password": False, "created_at": server.now_iso()})
        mon.teacher_assignments.insert_one({"id": str(uuid.uuid4()), "institution_id": A, "teacher_id": uid, "teacher_email": "o@p37a.test", "class_name": "Grade 9", "section": "A", "subject": "Physics"})
        U = Sess(C, login("o@p37a.test", "Teach@123"))
        yield {"platform": platform, "admin": admin, "R": R, "U": U, "db": mon, "A": A}
    MongoClient(server.mongo_url).drop_database(TEST_DB)


# ───────────────────────── BUG: draft resume / edit round-trip ─────────────────────────
def test_draft_save_resume_edit_submit_roundtrip(ctx):
    R = ctx["R"]
    # save a DRAFT (textbook + 2 chapters + a material), not submitted
    cid = R.post("/api/ai/curriculum", json={
        "academic_year": YEAR, "class_name": "Grade 8", "subject": "Mathematics", "name": "Draft Maths",
        "chapters": [{"chapter": "Algebra", "topics": ["Linear"]}, {"chapter": "Geometry"}],
        "items": [{"item_type": "textbook", "title": "TB"}], "submit": False}).json()["curriculum"]["id"]
    ctx["_draft"] = cid
    note = R.post(f"/api/ai/curriculum/{cid}/items", data={"item_type": "notes", "title": "Algebra notes", "chapter": "Algebra"}).json()["item"]["id"]

    # RESUME: the draft is fully readable (pre-fill source) — textbook + chapters + material all present
    det = R.get(f"/api/ai/curriculum/{cid}").json()
    assert det["curriculum"]["status"] == "draft"
    types = [i["item_type"] for i in det["items"]]
    assert "textbook" in types and types.count("chapter") == 2 and "notes" in types

    # EDIT the draft's name + syllabus (unsubmitted edit allowed)
    assert R.put(f"/api/ai/curriculum/{cid}", json={"name": "Draft Maths v2", "syllabus_text": "Updated"}).status_code == 200
    # add a new chapter while resuming
    R.post(f"/api/ai/curriculum/{cid}/items", data={"item_type": "chapter", "chapter": "Mensuration", "title": "Mensuration"})

    # SUBMIT the resumed draft → pending
    s = R.post(f"/api/ai/curriculum/{cid}/submit")
    assert s.status_code == 200 and s.json()["status"] == "pending"
    det2 = R.get(f"/api/ai/curriculum/{cid}").json()
    assert det2["curriculum"]["name"] == "Draft Maths v2" and det2["curriculum"]["syllabus_text"] == "Updated"
    assert det2["curriculum"]["status"] == "pending"


def test_cannot_edit_after_submission(ctx):
    # once pending, a plain owner can no longer PUT name/syllabus
    cid = ctx["_draft"]
    r = ctx["R"].put(f"/api/ai/curriculum/{cid}", json={"name": "nope"})
    assert r.status_code == 400 and "draft" in r.json()["detail"].lower()


# ───────────────────────── FEATURE B: reorder chapters + move materials ─────────────────────────
def test_reorder_chapters_persists_and_tree_reflects_order(ctx):
    cid = ctx["_draft"]  # chapters: Algebra, Geometry, Mensuration
    # reorder to Mensuration, Algebra, Geometry
    r = ctx["R"].post(f"/api/ai/curriculum/{cid}/chapters/reorder", json={"chapters": ["Mensuration", "Algebra", "Geometry"]})
    assert r.status_code == 200
    det = ctx["R"].get(f"/api/ai/curriculum/{cid}").json()
    ch_order = [i["chapter"] for i in det["items"] if i["item_type"] == "chapter"]
    assert ch_order == ["Mensuration", "Algebra", "Geometry"], ch_order


def test_move_material_between_chapters(ctx):
    cid = ctx["_draft"]
    det = ctx["R"].get(f"/api/ai/curriculum/{cid}").json()
    note = next(i for i in det["items"] if i["item_type"] == "notes")
    assert note["chapter"] == "Algebra"
    r = ctx["R"].post(f"/api/ai/items/{note['id']}/move", json={"chapter": "Geometry"})
    assert r.status_code == 200
    det2 = ctx["R"].get(f"/api/ai/curriculum/{cid}").json()
    moved = next(i for i in det2["items"] if i["id"] == note["id"])
    assert moved["chapter"] == "Geometry"


def test_cannot_move_chapter_node(ctx):
    cid = ctx["_draft"]
    det = ctx["R"].get(f"/api/ai/curriculum/{cid}").json()
    chap = next(i for i in det["items"] if i["item_type"] == "chapter")
    r = ctx["R"].post(f"/api/ai/items/{chap['id']}/move", json={"chapter": "Algebra"})
    assert r.status_code == 400


def test_textbook_can_be_added_to_published_curriculum(ctx):
    # a published curriculum accepts a textbook item without a chapter via the contribute flow
    admin = ctx["admin"]
    cid = admin.post("/api/ai/curriculum", json={"academic_year": YEAR, "class_name": "Grade 8", "subject": "Social Science",
                     "name": "G8 Social", "chapters": [{"chapter": "History"}],
                     "items": [{"item_type": "textbook", "title": "TB"}], "submit": True}).json()["curriculum"]["id"]
    admin.post(f"/api/ai/curriculum/{cid}/review", json={"action": "approve"})
    # add a textbook (structural — no chapter required) and a reference (material — chapter required)
    tb = admin.post(f"/api/ai/curriculum/{cid}/items", data={"item_type": "textbook", "title": "Extra textbook"})
    assert tb.status_code == 200 and tb.json()["item"]["item_type"] == "textbook"
    ref_no_ch = admin.post(f"/api/ai/curriculum/{cid}/items", data={"item_type": "reference", "title": "Ref"})
    assert ref_no_ch.status_code == 400  # reference is a material → needs a chapter
    ref_ok = admin.post(f"/api/ai/curriculum/{cid}/items", data={"item_type": "reference", "title": "Ref", "chapter": "History"})
    assert ref_ok.status_code == 200


def test_unrelated_teacher_cannot_reorder_or_move(ctx):
    cid = ctx["_draft"]
    det = ctx["admin"].get(f"/api/ai/curriculum/{cid}").json()
    note = next(i for i in det["items"] if i["item_type"] == "notes")
    assert ctx["U"].post(f"/api/ai/curriculum/{cid}/chapters/reorder", json={"chapters": ["Algebra"]}).status_code == 403
    assert ctx["U"].post(f"/api/ai/items/{note['id']}/move", json={"chapter": "Algebra"}).status_code == 403


# ───────────────────────── FEATURE A: bulk library upload ─────────────────────────
def test_bulk_upload_tags_per_row_and_overrides(ctx):
    meta = [
        {"grade": "Grade 8", "subject": "Mathematics", "material_type": "textbook", "title": "Maths TB", "academic_year": "2025-2026"},
        {"grade": "Grade 8", "subject": "Basic Science", "material_type": "notes"},  # title defaults to filename
        {"grade": "Grade 9", "subject": "Physics", "material_type": "worksheet", "title": "Phy WS"},
    ]
    files = [
        ("files", ("maths.pdf", b"%PDF-1.4 maths", "application/pdf")),
        ("files", ("science.pdf", b"%PDF-1.4 science", "application/pdf")),
        ("files", ("physics.pdf", b"%PDF-1.4 physics", "application/pdf")),
    ]
    r = ctx["platform"].post("/api/platform/library/bulk", data={"meta": json.dumps(meta)}, files=files)
    assert r.status_code == 200, r.text
    created = r.json()["items"]
    assert r.json()["count"] == 3 and len(created) == 3
    by_title = {c["title"]: c for c in created}
    # per-row tags honored
    assert by_title["Maths TB"]["grade"] == "Grade 8" and by_title["Maths TB"]["subject"] == "Mathematics" and by_title["Maths TB"]["material_type"] == "textbook"
    assert by_title["Phy WS"]["grade"] == "Grade 9" and by_title["Phy WS"]["material_type"] == "worksheet"
    # academic_year flows through when provided (apply-to-all bar)
    assert by_title["Maths TB"]["academic_year"] == "2025-2026"
    # missing title defaults to filename
    assert "science.pdf" in by_title and by_title["science.pdf"]["subject"] == "Basic Science"
    # background extraction runs per file
    for c in created:
        for _ in range(30):
            d = ctx["db"].platform_library.find_one({"id": c["id"]})
            if not d.get("processing"):
                break
            time.sleep(0.1)
        d = ctx["db"].platform_library.find_one({"id": c["id"]})
        assert d["processing"] is False and d["extracted_text"].startswith("EXTRACTED::")


def test_bulk_count_mismatch_and_non_platform(ctx):
    # meta/files length mismatch → 400
    r = ctx["platform"].post("/api/platform/library/bulk",
                             data={"meta": json.dumps([{"grade": "Grade 8", "subject": "X", "material_type": "notes"}])},
                             files=[("files", ("a.pdf", b"%PDF", "application/pdf")),
                                    ("files", ("b.pdf", b"%PDF", "application/pdf"))])
    assert r.status_code == 400
    # non-platform user forbidden
    r2 = ctx["R"].post("/api/platform/library/bulk",
                       data={"meta": json.dumps([{"grade": "Grade 8", "subject": "X", "material_type": "notes"}])},
                       files=[("files", ("a.pdf", b"%PDF", "application/pdf"))])
    assert r2.status_code == 403
