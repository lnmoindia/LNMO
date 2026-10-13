"""Phase 36 — LNMO Central Library + Kerala SCERT chapter templates.
Covers: large-file upload path accepts ~45MB + background extraction fills extracted_text;
non-platform upload 403; template seed + teacher prefill fetch; import → pending → principal
approve → active with library badge; school submit → platform approve → published. Throwaway DB.
"""
import sys
import time
import uuid
import pytest

sys.path.insert(0, "/app/backend")
import server  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from pymongo import MongoClient  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

TEST_DB = "lnmo_phase36_test"
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

    # avoid real object storage + heavy extraction during tests
    monkeymodule.setattr(server, "_put_object", lambda path, data, ct: True)
    monkeymodule.setattr(server, "_delete_object", lambda path: True)
    monkeymodule.setattr(server, "_ai_extract_text", lambda content, mime, name: f"EXTRACTED::{len(content)} bytes")
    # the real bg thread targets env DB_NAME; in tests, redirect it to the throwaway DB
    monkeymodule.setattr(server, "_lib_extract_bg", lambda lid, content, mime, name: mon.platform_library.update_one(
        {"id": lid}, {"$set": {"extracted_text": f"EXTRACTED::{len(content)} bytes", "processing": False}}))

    with _client() as C:
        def login(email, pw):
            r = C.post("/api/auth/login", json={"email": email, "password": pw})
            assert r.status_code == 200, r.text
            tok = r.cookies.get("access_token"); C.cookies.clear()
            return tok

        platform = Sess(C, login(PA_EMAIL, PA_PW))
        A = platform.post("/api/res/institutions", json={"name": "S", "slug": "p36a", "admin_email": "a@p36a.test", "admin_password": "Admin@123"}).json()["id"]
        admin = Sess(C, login("a@p36a.test", "Admin@123"))
        mon.classes.insert_one({"id": "c8", "institution_id": A, "name": "Grade 8", "academic_unit_id": "uHS"})
        tid = str(uuid.uuid4())
        mon.users.insert_one({"id": tid, "name": "Radha", "email": "r@p36a.test", "password_hash": server.hash_password("Teach@123"),
                              "role": "teacher", "institution_id": A, "status": "active", "must_change_password": False, "created_at": server.now_iso()})
        mon.teacher_assignments.insert_one({"id": str(uuid.uuid4()), "institution_id": A, "teacher_id": tid, "teacher_email": "r@p36a.test", "class_name": "Grade 8", "section": "A", "subject": "Mathematics"})
        R = Sess(C, login("r@p36a.test", "Teach@123"))
        # a published curriculum to import into
        cid = R.post("/api/ai/curriculum", json={"academic_year": YEAR, "class_name": "Grade 8", "subject": "Mathematics",
                     "name": "G8 Maths", "chapters": [{"chapter": "Algebra"}],
                     "items": [{"item_type": "textbook", "title": "TB"}], "submit": True}).json()["curriculum"]["id"]
        admin.post(f"/api/ai/curriculum/{cid}/review", json={"action": "approve"})
        yield {"platform": platform, "admin": admin, "R": R, "db": mon, "A": A, "cid": cid}
    MongoClient(server.mongo_url).drop_database(TEST_DB)


def test_scert_template_seeded_and_teacher_prefill(ctx):
    t = ctx["R"].get("/api/ai/curriculum-template", params={"grade": "Grade 8", "subject": "Mathematics"}).json()["template"]
    assert t and len(t["chapters"]) >= 5 and t["board"] == "kerala_scert"


def test_large_file_upload_and_background_extraction(ctx):
    big = b"%PDF-1.4\n" + b"0" * (45 * 1024 * 1024)  # ~45MB
    r = ctx["platform"].post("/api/platform/library",
                             data={"grade": "Grade 8", "subject": "Mathematics", "material_type": "textbook", "title": "SCERT G8 Maths Textbook"},
                             files={"file": ("textbook.pdf", big, "application/pdf")})
    assert r.status_code == 200, r.text
    item = r.json()["item"]
    assert item["size"] == len(big) and item["status"] == "published"
    lid = item["id"]
    ctx["_lid"] = lid
    # background extraction fills extracted_text shortly after
    for _ in range(40):
        doc = ctx["db"].platform_library.find_one({"id": lid})
        if not doc.get("processing"):
            break
        time.sleep(0.1)
    doc = ctx["db"].platform_library.find_one({"id": lid})
    assert doc["processing"] is False and doc["extracted_text"].startswith("EXTRACTED::")


def test_oversize_rejected(ctx):
    toobig = b"%PDF" + b"0" * (61 * 1024 * 1024)
    r = ctx["platform"].post("/api/platform/library",
                             data={"grade": "Grade 8", "subject": "Science", "material_type": "textbook", "title": "X"},
                             files={"file": ("x.pdf", toobig, "application/pdf")})
    assert r.status_code == 400 and "60 MB" in r.json()["detail"]


def test_non_platform_cannot_upload(ctx):
    r = ctx["R"].post("/api/platform/library",
                      data={"grade": "Grade 8", "subject": "Mathematics", "material_type": "textbook", "title": "hack"})
    assert r.status_code == 403


def test_import_library_pending_then_principal_approve_active_with_badge(ctx):
    cid, lid = ctx["cid"], ctx["_lid"]
    # teacher browses published library and imports the textbook
    lib = ctx["R"].get("/api/ai/central-library", params={"grade": "Grade 8", "subject": "Mathematics"}).json()["items"]
    assert any(x["id"] == lid for x in lib)
    imp = ctx["R"].post(f"/api/ai/curriculum/{cid}/import-library", json={"library_id": lid})
    assert imp.status_code == 200, imp.text
    item = imp.json()["item"]
    assert item["status"] == "pending" and item["source"] == "lnmo_library" and item["library_id"] == lid
    # principal (admin) approves → active in knowledge base, badge retained
    assert ctx["admin"].post(f"/api/ai/items/{item['id']}/review", json={"action": "approve"}).json()["status"] == "approved"
    det = ctx["admin"].get(f"/api/ai/curriculum/{cid}").json()
    got = next(i for i in det["items"] if i["id"] == item["id"])
    assert got["status"] == "approved" and got["active"] and got["source"] == "lnmo_library"


def test_material_import_requires_chapter(ctx):
    # add a published 'notes' library item then try importing without a chapter
    nid = ctx["platform"].post("/api/platform/library",
                               data={"grade": "Grade 8", "subject": "Mathematics", "material_type": "notes", "title": "Notes"}).json()["item"]["id"]
    r = ctx["R"].post(f"/api/ai/curriculum/{ctx['cid']}/import-library", json={"library_id": nid})
    assert r.status_code == 400 and "chapter" in r.json()["detail"].lower()
    ok = ctx["R"].post(f"/api/ai/curriculum/{ctx['cid']}/import-library", json={"library_id": nid, "chapter": "Algebra"})
    assert ok.status_code == 200


def test_school_submit_then_platform_approve(ctx):
    cid = ctx["cid"]
    # teacher contributes a worksheet then submits it to the central library
    wid = ctx["R"].post(f"/api/ai/curriculum/{cid}/items", data={"item_type": "worksheet", "title": "My WS", "chapter": "Algebra"}).json()["item"]["id"]
    s = ctx["R"].post(f"/api/ai/curriculum/{cid}/submit-to-library", json={"item_id": wid})
    assert s.status_code == 200 and s.json()["status"] == "pending"
    # platform sees it as a pending school submission
    pend = ctx["platform"].get("/api/platform/library", params={"status": "pending", "source": "school"}).json()["items"]
    # (source filter not a server param; filter client-side)
    pend = [x for x in ctx["platform"].get("/api/platform/library", params={"status": "pending"}).json()["items"] if x["source"] == "school"]
    assert any(x["title"] == "My WS" and x["submitted_by_school"] == ctx["A"] for x in pend)
    sub = next(x for x in pend if x["title"] == "My WS")
    # platform approves → published centrally
    assert ctx["platform"].post(f"/api/platform/library/{sub['id']}/approve").json()["status"] == "published"
