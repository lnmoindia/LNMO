"""Phase 39 — LNMO Library reference-only attach + in-app preview + search + delete guard.
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

TEST_DB = "lnmo_phase39_test"
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

    store = {}          # path -> (bytes, ct)
    put_calls = []
    deleted = []
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
        A = platform.post("/api/res/institutions", json={"name": "Alpha", "slug": "p39a", "admin_email": "a@p39a.test", "admin_password": "Admin@123"}).json()["id"]
        B = platform.post("/api/res/institutions", json={"name": "Beta", "slug": "p39b", "admin_email": "a@p39b.test", "admin_password": "Admin@123"}).json()["id"]
        admin = Sess(C, login("a@p39a.test", "Admin@123"))
        for iid in (A, B):
            mon.classes.insert_one({"id": f"c8-{iid}", "institution_id": iid, "name": "Grade 8", "academic_unit_id": "uHS"})

        def mk_teacher(iid, email):
            tid = str(uuid.uuid4())
            mon.users.insert_one({"id": tid, "name": "T", "email": email, "password_hash": server.hash_password("Teach@123"),
                                  "role": "teacher", "institution_id": iid, "status": "active", "must_change_password": False, "created_at": server.now_iso()})
            mon.teacher_assignments.insert_one({"id": str(uuid.uuid4()), "institution_id": iid, "teacher_id": tid, "teacher_email": email, "class_name": "Grade 8", "section": "A", "subject": "Mathematics"})
            return Sess(C, login(email, "Teach@123"))

        TA = mk_teacher(A, "t@p39a.test")   # teacher at school A
        TB = mk_teacher(B, "t@p39b.test")   # teacher at school B
        # a student at school A
        sid = str(uuid.uuid4())
        mon.students.insert_one({"id": sid, "institution_id": A, "class_name": "Grade 8", "name": "Stu", "status": "active"})
        suid = str(uuid.uuid4())
        mon.users.insert_one({"id": suid, "name": "Stu", "email": "s@p39a.test", "password_hash": server.hash_password("Stud@123"),
                              "role": "student", "institution_id": A, "student_id": sid, "status": "active", "must_change_password": False, "created_at": server.now_iso()})
        STU = Sess(C, login("s@p39a.test", "Stud@123"))

        # platform publishes two library items (PDF bytes)
        def pub(title, subject, desc=""):
            r = platform.post("/api/platform/library",
                              data={"grade": "Grade 8", "subject": subject, "material_type": "textbook", "title": title, "description": desc},
                              files={"file": (f"{title}.pdf", b"%PDF-1.4 " + title.encode(), "application/pdf")})
            assert r.status_code == 200, r.text
            return r.json()["item"]["id"]

        LIB_MATH = pub("Algebra Master", "Mathematics", "covers linear equations")
        LIB_OTHER = pub("Geometry Notes", "Mathematics", "shapes and angles")
        yield {"platform": platform, "admin": admin, "TA": TA, "TB": TB, "STU": STU,
               "A": A, "B": B, "db": mon, "store": store, "put_calls": put_calls, "deleted": deleted,
               "LIB_MATH": LIB_MATH, "LIB_OTHER": LIB_OTHER}
    MongoClient(server.mongo_url).drop_database(TEST_DB)


def _mk_curriculum(sess, iid, subject="Mathematics", name="G8 Math", year=YEAR):
    cid = sess.post("/api/ai/curriculum", json={"academic_year": year, "class_name": "Grade 8", "subject": subject,
                    "name": name, "chapters": [{"chapter": "Ch1"}], "items": [{"item_type": "textbook", "title": "TB"}], "submit": False}).json()["curriculum"]["id"]
    return cid


# ───────── reference-only ─────────
def test_import_stores_reference_only_no_byte_copy(ctx):
    TA, db = ctx["TA"], ctx["db"]
    cid = _mk_curriculum(TA, ctx["A"])
    puts_before = len(ctx["put_calls"])  # the textbook upload already counted
    r = TA.post(f"/api/ai/curriculum/{cid}/import-library", json={"library_id": ctx["LIB_MATH"], "chapter": "Ch1"})
    assert r.status_code == 200
    item = r.json()["item"]
    # NO new object-storage file was created by the import
    assert len(ctx["put_calls"]) == puts_before
    doc = db.curriculum_items.find_one({"id": item["id"]})
    lib = db.platform_library.find_one({"id": ctx["LIB_MATH"]})
    # item points at the SAME stored file path and reuses the library's extracted text
    assert doc["file_path"] == lib["file_path"]
    assert doc["library_id"] == ctx["LIB_MATH"]
    assert doc["extracted_text"] == lib["extracted_text"] and doc["extracted_text"]


def test_imported_item_file_served_from_single_library_path(ctx):
    TA = ctx["TA"]
    cid = _mk_curriculum(TA, ctx["A"], name="G8 Math2", year="2026-2027")
    item = TA.post(f"/api/ai/curriculum/{cid}/import-library", json={"library_id": ctx["LIB_MATH"], "chapter": "Ch1"}).json()["item"]
    r = TA.get(f"/api/ai/items/{item['id']}/file")
    assert r.status_code == 200 and r.content.startswith(b"%PDF")


# ───────── delete guard ─────────
def test_library_delete_blocked_while_referenced_then_allowed(ctx):
    platform, TA, db = ctx["platform"], ctx["TA"], ctx["db"]
    cid = _mk_curriculum(TA, ctx["A"], name="G8 Math3", year="2027-2028")
    item = TA.post(f"/api/ai/curriculum/{cid}/import-library", json={"library_id": ctx["LIB_OTHER"], "chapter": "Ch1"}).json()["item"]
    # blocked with 409 + referencing schools
    r = platform.delete(f"/api/platform/library/{ctx['LIB_OTHER']}")
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert detail["reference_count"] >= 1 and "Alpha" in detail["schools"]
    # detach (admin/principal removes the imported item) → now deletable
    assert ctx["admin"].delete(f"/api/ai/items/{item['id']}").status_code == 200
    r2 = platform.delete(f"/api/platform/library/{ctx['LIB_OTHER']}")
    assert r2.status_code == 200


# ───────── preview endpoint auth ─────────
def test_preview_endpoints_auth(ctx):
    TA, TB, STU = ctx["TA"], ctx["TB"], ctx["STU"]
    lid = ctx["LIB_MATH"]
    # teacher of ANY school can preview the shared catalogue file + detail
    assert TA.get(f"/api/ai/central-library/{lid}/file").status_code == 200
    assert TB.get(f"/api/ai/central-library/{lid}/file").status_code == 200
    d = TB.get(f"/api/ai/central-library/{lid}")
    assert d.status_code == 200 and d.json()["extracted_text"]
    # students have NO direct access to the library preview routes
    assert STU.get(f"/api/ai/central-library/{lid}/file").status_code == 403
    assert STU.get(f"/api/ai/central-library/{lid}").status_code == 403


# ───────── search ─────────
def test_search_and_filters(ctx):
    TA, platform = ctx["TA"], ctx["platform"]
    # publish dedicated items so this test is order-independent
    platform.post("/api/platform/library",
                  data={"grade": "Grade 8", "subject": "Mathematics", "material_type": "notes", "title": "Trigonometry Primer", "description": "sine cosine tangent"},
                  files={"file": ("trig.pdf", b"%PDF trig", "application/pdf")})
    # search by description keyword
    r = TA.get("/api/ai/central-library", params={"q": "linear"})
    titles = [x["title"] for x in r.json()["items"]]
    assert "Algebra Master" in titles and "Trigonometry Primer" not in titles
    # search by title keyword
    r2 = TA.get("/api/ai/central-library", params={"q": "Trigonometry"})
    titles2 = [x["title"] for x in r2.json()["items"]]
    assert titles2 and all("Trigonometry" in t for t in titles2)
    # search by description keyword of the new item
    r2b = TA.get("/api/ai/central-library", params={"q": "cosine"})
    assert "Trigonometry Primer" in [x["title"] for x in r2b.json()["items"]]
    # grade/subject filter still works
    r3 = TA.get("/api/ai/central-library", params={"grade": "Grade 8", "subject": "Mathematics"})
    assert all(x["grade"] == "Grade 8" and x["subject"] == "Mathematics" for x in r3.json()["items"])
    # mime surfaced for the preview decision
    assert all("mime" in x for x in r3.json()["items"])
