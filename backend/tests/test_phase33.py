"""Phase 33 — Create-curriculum wizard backend rules.
Covers: submit without textbook -> 400; submit without chapter -> 400; material without chapter -> 400
on contribute; happy-path (textbook + chapter + material) -> submit pending; draft save mid-wizard
stays draft. Throwaway DB.
"""
import sys
import uuid
import pytest

sys.path.insert(0, "/app/backend")
import server  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from pymongo import MongoClient  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

TEST_DB = "lnmo_phase33_test"
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
        a = platform.post("/api/res/institutions", json={"name": "S", "slug": "p33a", "admin_email": "a@p33a.test", "admin_password": "Admin@123"}).json()
        A = a["id"]
        mon.classes.insert_one({"id": "c8", "institution_id": A, "name": "Grade 8", "academic_unit_id": "uHS"})
        tid = str(uuid.uuid4())
        mon.users.insert_one({"id": tid, "name": "Radha", "email": "r@p33a.test", "password_hash": server.hash_password("Teach@123"),
                              "role": "teacher", "institution_id": A, "status": "active", "must_change_password": False, "created_at": server.now_iso()})
        mon.teacher_assignments.insert_one({"id": str(uuid.uuid4()), "institution_id": A, "teacher_id": tid, "teacher_email": "r@p33a.test", "class_name": "Grade 8", "section": "A", "subject": "Mathematics"})
        R = Sess(C, login("r@p33a.test", "Teach@123"))
        yield {"R": R, "db": mon, "A": A}
    MongoClient(server.mongo_url).drop_database(TEST_DB)


def _draft(ctx, chapters, items, year=YEAR):
    return ctx["R"].post("/api/ai/curriculum", json={
        "academic_year": year, "class_name": "Grade 8", "subject": "Mathematics",
        "name": "G8 Maths", "chapters": chapters, "items": items, "submit": False})


def test_create_submit_without_textbook_400(ctx):
    r = ctx["R"].post("/api/ai/curriculum", json={
        "academic_year": YEAR, "class_name": "Grade 8", "subject": "Mathematics", "name": "X",
        "chapters": [{"chapter": "Ch1"}], "items": [], "submit": True})
    assert r.status_code == 400 and "textbook" in r.json()["detail"].lower()


def test_create_submit_without_chapter_400(ctx):
    r = ctx["R"].post("/api/ai/curriculum", json={
        "academic_year": YEAR, "class_name": "Grade 8", "subject": "Mathematics", "name": "X",
        "chapters": [], "items": [{"item_type": "textbook", "title": "TB"}], "submit": True})
    assert r.status_code == 400 and "chapter" in r.json()["detail"].lower()


def test_material_without_chapter_400(ctx):
    d = _draft(ctx, [{"chapter": "Ch1"}], [{"item_type": "textbook", "title": "TB"}], year="2020-21")
    assert d.status_code == 200, d.text
    cid = d.json()["curriculum"]["id"]
    # contributing a material (worksheet) WITHOUT a chapter is rejected
    r = ctx["R"].post(f"/api/ai/curriculum/{cid}/items", data={"item_type": "worksheet", "title": "WS", "chapter": ""})
    assert r.status_code == 400 and "chapter" in r.json()["detail"].lower()
    # with a chapter it succeeds
    ok = ctx["R"].post(f"/api/ai/curriculum/{cid}/items", data={"item_type": "worksheet", "title": "WS", "chapter": "Ch1"})
    assert ok.status_code == 200
    ctx["_cid"] = cid


def test_submit_endpoint_requires_textbook_and_chapter(ctx):
    # draft with ONLY a chapter (no textbook) → submit blocked
    d = _draft(ctx, [{"chapter": "Ch1"}], [], year="2021-22")
    cid = d.json()["curriculum"]["id"]
    r = ctx["R"].post(f"/api/ai/curriculum/{cid}/submit")
    assert r.status_code == 400 and "textbook" in r.json()["detail"].lower()


def test_happy_path_wizard_submits_pending(ctx):
    # mirror the wizard: draft (chapters) → add textbook → add material → submit
    d = _draft(ctx, [{"chapter": "Ch1", "topics": ["t1"]}], [], year="2022-23")
    cid = d.json()["curriculum"]["id"]
    assert ctx["R"].post(f"/api/ai/curriculum/{cid}/items", data={"item_type": "textbook", "title": "Class Textbook", "chapter": ""}).status_code == 200
    assert ctx["R"].post(f"/api/ai/curriculum/{cid}/items", data={"item_type": "notes", "title": "Notes", "chapter": "Ch1"}).status_code == 200
    r = ctx["R"].post(f"/api/ai/curriculum/{cid}/submit")
    assert r.status_code == 200 and r.json()["status"] == "pending"
    det = ctx["R"].get(f"/api/ai/curriculum?academic_year=2022-23&class_name=Grade 8&subject=Mathematics").json()
    types = {i["item_type"] for i in det["items"]}
    assert "textbook" in types and "chapter" in types and "notes" in types


def test_draft_save_mid_wizard_stays_draft(ctx):
    # the "Finish later" path: create draft with textbook+chapter but DON'T submit
    d = _draft(ctx, [{"chapter": "ChA"}], [{"item_type": "textbook", "title": "TB"}], year="2023-24")
    cid = d.json()["curriculum"]["id"]
    assert d.json()["curriculum"]["status"] == "draft"
    doc = ctx["db"].curricula.find_one({"id": cid})
    assert doc["status"] == "draft" and doc["submitted_at"] is None
