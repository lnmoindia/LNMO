"""Phase 40 — Step-1 textbook via LNMO Library: satisfies submit validation, swap semantics,
reference-only (no new storage object), and teacher owns the swap on a draft.
Throwaway DB; object storage put/get/delete mocked and counted.
"""
import sys
import uuid
import pytest

sys.path.insert(0, "/app/backend")
import server  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from pymongo import MongoClient  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

TEST_DB = "lnmo_phase40_test"
PA_EMAIL = server.os.environ["PLATFORM_ADMIN_EMAIL"].lower()
PA_PW = server.os.environ["PLATFORM_ADMIN_PASSWORD"]
BASE = "https://testserver"


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

    store, put_calls, deleted = {}, [], []
    monkeymodule.setattr(server, "_put_object", lambda path, data, ct: (put_calls.append(path), store.__setitem__(path, (data, ct)), True)[-1])
    monkeymodule.setattr(server, "_get_object", lambda path: store.get(path, (b"", "application/octet-stream")))
    monkeymodule.setattr(server, "_delete_object", lambda path: (deleted.append(path), True)[-1])
    monkeymodule.setattr(server, "_lib_extract_bg", lambda lid, content, mime, name: mon.platform_library.update_one(
        {"id": lid}, {"$set": {"extracted_text": f"EXTRACTED::{len(content)}", "processing": False}}))

    with _client() as C:
        def login(email, pw):
            r = C.post("/api/auth/login", json={"email": email, "password": pw})
            assert r.status_code == 200, r.text
            tok = r.cookies.get("access_token"); C.cookies.clear()
            return tok

        platform = Sess(C, login(PA_EMAIL, PA_PW))
        A = platform.post("/api/res/institutions", json={"name": "Alpha", "slug": "p40", "admin_email": "a@p40.test", "admin_password": "Admin@123"}).json()["id"]
        admin = Sess(C, login("a@p40.test", "Admin@123"))
        mon.classes.insert_one({"id": "c8", "institution_id": A, "name": "Grade 8", "academic_unit_id": "uHS"})
        tid = str(uuid.uuid4())
        mon.users.insert_one({"id": tid, "name": "T", "email": "t@p40.test", "password_hash": server.hash_password("Teach@123"),
                              "role": "teacher", "institution_id": A, "status": "active", "must_change_password": False, "created_at": server.now_iso()})
        mon.teacher_assignments.insert_one({"id": str(uuid.uuid4()), "institution_id": A, "teacher_id": tid, "teacher_email": "t@p40.test", "class_name": "Grade 8", "section": "A", "subject": "Mathematics"})
        T = Sess(C, login("t@p40.test", "Teach@123"))

        r = platform.post("/api/platform/library",
                          data={"grade": "Grade 8", "subject": "Mathematics", "material_type": "textbook", "title": "SCERT G8 Maths"},
                          files={"file": ("scert.pdf", b"%PDF-1.4 scert maths", "application/pdf")})
        LIB = r.json()["item"]["id"]
        yield {"platform": platform, "admin": admin, "T": T, "A": A, "db": mon,
               "store": store, "put_calls": put_calls, "deleted": deleted, "LIB": LIB}
    MongoClient(server.mongo_url).drop_database(TEST_DB)


def _draft(T, year, name="G8 Math"):
    return T.post("/api/ai/curriculum", json={"academic_year": year, "class_name": "Grade 8", "subject": "Mathematics",
                  "name": name, "chapters": [{"chapter": "Ch1"}], "items": [], "submit": False}).json()["curriculum"]["id"]


def test_library_textbook_satisfies_submit_no_new_object(ctx):
    """A draft whose ONLY textbook is a library reference must submit successfully,
    and importing it must NOT create a new storage object."""
    T, db = ctx["T"], ctx["db"]
    cid = _draft(T, "2025-2026")
    puts_before = len(ctx["put_calls"])
    item = T.post(f"/api/ai/curriculum/{cid}/import-library", json={"library_id": ctx["LIB"], "chapter": ""}).json()["item"]
    assert item["item_type"] == "textbook" and item["source"] == "lnmo_library"
    assert len(ctx["put_calls"]) == puts_before  # reference-only: no new file written
    # reuses the shared path + extracted text
    doc = db.curriculum_items.find_one({"id": item["id"]})
    lib = db.platform_library.find_one({"id": ctx["LIB"]})
    assert doc["file_path"] == lib["file_path"] and doc["extracted_text"] == lib["extracted_text"]
    # submit passes with only a library textbook + the chapter
    r = T.post(f"/api/ai/curriculum/{cid}/submit")
    assert r.status_code == 200 and r.json()["status"] == "pending", r.text


def test_swap_uploaded_to_library(ctx):
    """Replace an uploaded textbook with a library reference → old upload file cleaned up,
    new item references the shared library file, no leftover duplicate textbook."""
    T, db = ctx["T"], ctx["db"]
    cid = _draft(T, "2026-2027")
    up = T.post(f"/api/ai/curriculum/{cid}/items", data={"item_type": "textbook", "title": "My upload"},
                files={"file": ("mine.pdf", b"%PDF mine", "application/pdf")}).json()["item"]
    up_doc = db.curriculum_items.find_one({"id": up["id"]})
    old_path = up_doc["file_path"]
    # teacher deletes own uploaded textbook (hard delete + file cleanup), then attaches library one
    assert T.delete(f"/api/ai/items/{up['id']}").status_code == 200
    assert old_path in ctx["deleted"]                       # uploaded file cleaned up
    assert db.curriculum_items.count_documents({"id": up["id"]}) == 0  # hard-deleted
    lib_item = T.post(f"/api/ai/curriculum/{cid}/import-library", json={"library_id": ctx["LIB"], "chapter": ""}).json()["item"]
    tbs = list(db.curriculum_items.find({"curriculum_id": cid, "item_type": "textbook", "status": {"$ne": "deleted"}}))
    assert len(tbs) == 1 and tbs[0]["source"] == "lnmo_library"


def test_swap_library_to_uploaded_keeps_shared_file(ctx):
    """Replace a library textbook with an uploaded one → the shared library file is NOT deleted."""
    T, db = ctx["T"], ctx["db"]
    cid = _draft(T, "2027-2028")
    lib_item = T.post(f"/api/ai/curriculum/{cid}/import-library", json={"library_id": ctx["LIB"], "chapter": ""}).json()["item"]
    lib = db.platform_library.find_one({"id": ctx["LIB"]})
    shared_path = lib["file_path"]
    ctx["deleted"].clear()
    # detach the library textbook (teacher) → shared file must NOT be deleted
    assert T.delete(f"/api/ai/items/{lib_item['id']}").status_code == 200
    assert shared_path not in ctx["deleted"]
    assert ctx["db"].platform_library.find_one({"id": ctx["LIB"]}) is not None  # library item intact
    # now upload a real textbook instead
    T.post(f"/api/ai/curriculum/{cid}/items", data={"item_type": "textbook", "title": "Uploaded TB"},
           files={"file": ("u.pdf", b"%PDF u", "application/pdf")})
    tbs = list(db.curriculum_items.find({"curriculum_id": cid, "item_type": "textbook", "status": {"$ne": "deleted"}}))
    assert len(tbs) == 1 and tbs[0].get("source") != "lnmo_library"


def test_teacher_cannot_hard_delete_item_after_submit(ctx):
    T, admin = ctx["T"], ctx["admin"]
    cid = _draft(T, "2028-2029")
    item = T.post(f"/api/ai/curriculum/{cid}/import-library", json={"library_id": ctx["LIB"], "chapter": ""}).json()["item"]
    T.post(f"/api/ai/curriculum/{cid}/submit")
    # once submitted, the teacher can no longer hard-delete items
    assert T.delete(f"/api/ai/items/{item['id']}").status_code == 409
