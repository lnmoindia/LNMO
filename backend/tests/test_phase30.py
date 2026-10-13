"""Phase 30 — AI Tutor chat + resource library. LLM is MOCKED (never hits the network).
Throwaway DB.

Covers: approved-only retrieval (pending/rejected items never reach the prompt); enable-gate 403;
wrong-grade 403; teacher/parent roles 403 on chat; library scope (own grade, approved only);
rate-limit 429; general-fallback flag when no match.
"""
import sys
import uuid
import pytest

sys.path.insert(0, "/app/backend")
import server  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from pymongo import MongoClient  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

TEST_DB = "lnmo_phase30_test"
PA_EMAIL = server.os.environ["PLATFORM_ADMIN_EMAIL"].lower()
PA_PW = server.os.environ["PLATFORM_ADMIN_PASSWORD"]
BASE = "https://testserver"
YEAR = "2026-27"

# ---- capture what context reaches the LLM so we can assert approved-only retrieval ----
CAPTURED = {}


async def _fake_llm(system_message, user_text, session_id):
    # capture ONLY the main tutor-answer prompt; ignore the Phase 32 classify / memory-extraction calls
    if "AI Tutor" in system_message:
        CAPTURED["system"] = system_message
        CAPTURED["user"] = user_text
    return f"MOCK ANSWER for: {user_text[:40]}"


@pytest.fixture(autouse=True)
def _patch_llm(monkeypatch):
    monkeypatch.setattr(server, "_ai_llm_generate", _fake_llm)
    monkeypatch.setattr(server, "_active_year_name", lambda iid: _coro(YEAR))


def _coro(v):
    async def _c():
        return v
    return _c()


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
        A = platform.post("/api/res/institutions", json={"name": "SchoolA", "slug": "p30a", "admin_email": "a@p30a.test", "admin_password": "Admin@123"}).json()["id"]
        mon.institutions.update_one({"id": A}, {"$set": {"features.ai_layer_enabled": True}})

        mon.classes.insert_many([
            {"id": "c8", "institution_id": A, "name": "Grade 8", "academic_unit_id": "u", "academic_unit_name": "HS"},
            {"id": "c9", "institution_id": A, "name": "Grade 9", "academic_unit_id": "u", "academic_unit_name": "HS"},
        ])
        mon.subject_offerings.insert_many([
            {"id": str(uuid.uuid4()), "institution_id": A, "class_name": "Grade 8", "subject": "Mathematics"},
            {"id": str(uuid.uuid4()), "institution_id": A, "class_name": "Grade 8", "subject": "Science"},
        ])
        # Published + ai_enabled Grade 8 Maths
        cur = {"id": "curM", "institution_id": A, "academic_year": YEAR, "class_name": "Grade 8",
               "subject": "Mathematics", "name": "G8 Maths", "syllabus_text": "", "status": "published",
               "ai_enabled": True, "created_by": "t1", "created_at": server.now_iso()}
        # Grade 8 Science published but NOT ai_enabled (gate test)
        curS = dict(cur); curS.update({"id": "curS", "subject": "Science", "ai_enabled": False})
        mon.curricula.insert_many([cur, curS])

        def item(cid, status, title, text, itype="notes", active=True, chapter="Chapter 1"):
            return {"id": str(uuid.uuid4()), "curriculum_id": cid, "institution_id": A, "item_type": itype,
                    "chapter": chapter, "topic": "", "title": title, "description": "", "text_content": text,
                    "extracted_text": "", "status": status, "active": active, "version": 1,
                    "contributed_by": "t1", "contributor_name": "Radha", "contributed_at": server.now_iso()}
        mon.curriculum_items.insert_many([
            item("curM", "approved", "Linear Equations", "A linear equation APPROVEDLINEARTOKEN looks like ax+b=0"),
            item("curM", "pending", "Secret Draft", "PENDINGSECRETTOKEN should never reach the prompt"),
            item("curM", "rejected", "Bad Material", "REJECTEDSECRETTOKEN should never reach the prompt"),
            item("curM", "approved", "Quadratics worksheet", "quadratic APPROVEDQUADTOKEN practice", itype="worksheet", chapter="Chapter 2"),
        ])

        # student in Grade 8, student in Grade 9, a teacher, a parent
        def mk(role, email, extra):
            uid = str(uuid.uuid4())
            mon.users.insert_one({"id": uid, "name": email, "email": email, "password_hash": server.hash_password("Pw@123"),
                                  "role": role, "institution_id": A, "status": "active", "must_change_password": False,
                                  "created_at": server.now_iso(), **extra})
            return uid
        mon.students.insert_many([
            {"id": "s8", "institution_id": A, "first_name": "Ria", "last_name": "K", "class_name": "Grade 8", "section": "A", "enrollment_status": "enrolled"},
            {"id": "s9", "institution_id": A, "first_name": "Jo", "last_name": "P", "class_name": "Grade 9", "section": "A", "enrollment_status": "enrolled"},
        ])
        mk("student", "s8@p30a.test", {"student_id": "s8"})
        mk("student", "s9@p30a.test", {"student_id": "s9"})
        mk("teacher", "t@p30a.test", {})
        mk("parent", "par@p30a.test", {"student_ids": ["s8"]})

        yield {"A": A, "db": mon,
               "s8": login("s8@p30a.test", "Pw@123"), "s9": login("s9@p30a.test", "Pw@123"),
               "teacher": login("t@p30a.test", "Pw@123"), "parent": login("par@p30a.test", "Pw@123")}
    MongoClient(server.mongo_url).drop_database(TEST_DB)


def test_chat_retrieval_approved_only(ctx):
    CAPTURED.clear()
    r = ctx["s8"].post("/api/ai/tutor/chat", json={"subject": "Mathematics", "message": "explain linear equations"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["grounded"] is True and "MOCK ANSWER" in d["answer"]
    assert any("Linear Equations" == t["title"] for t in d["used_item_titles"])
    # the prompt must contain ONLY approved content, never pending/rejected
    sysp = CAPTURED["system"]
    assert "APPROVEDLINEARTOKEN" in sysp
    assert "PENDINGSECRETTOKEN" not in sysp and "REJECTEDSECRETTOKEN" not in sysp


def test_general_fallback_flag(ctx):
    CAPTURED.clear()
    r = ctx["s8"].post("/api/ai/tutor/chat", json={"subject": "Mathematics", "message": "zzqqxx nonmatching gibberish term"})
    assert r.status_code == 200
    d = r.json()
    assert d["grounded"] is False and d["used_item_titles"] == []
    assert "general explanation" in CAPTURED["system"].lower()


def test_enable_gate_403(ctx):
    r = ctx["s8"].post("/api/ai/tutor/chat", json={"subject": "Science", "message": "hi"})
    assert r.status_code == 403 and "not enabled" in r.json()["detail"].lower()


def test_wrong_grade_403(ctx):
    # Grade 9 student has no Grade 8 Maths curriculum → treated as not enabled
    r = ctx["s9"].post("/api/ai/tutor/chat", json={"subject": "Mathematics", "message": "hi"})
    assert r.status_code == 403


def test_non_student_roles_403(ctx):
    assert ctx["teacher"].post("/api/ai/tutor/chat", json={"subject": "Mathematics", "message": "hi"}).status_code == 403
    assert ctx["parent"].post("/api/ai/tutor/chat", json={"subject": "Mathematics", "message": "hi"}).status_code == 403
    assert ctx["teacher"].get("/api/ai/library").status_code == 403


def test_library_scope_approved_only(ctx):
    lib = ctx["s8"].get("/api/ai/library").json()
    assert lib["class_name"] == "Grade 8"
    subs = {s["subject"]: s for s in lib["subjects"]}
    assert "Mathematics" in subs and "Science" not in subs  # Science not ai_enabled → excluded
    mats = [m["title"] for ch in subs["Mathematics"]["chapters"] for m in ch["materials"]]
    assert "Linear Equations" in mats and "Quadratics worksheet" in mats
    assert "Secret Draft" not in mats and "Bad Material" not in mats
    # Grade 9 student sees nothing (no enabled curricula for their grade)
    assert ctx["s9"].get("/api/ai/library").json()["subjects"] == []


def test_subjects_enabled_flags(ctx):
    subs = {s["subject"]: s["enabled"] for s in ctx["s8"].get("/api/ai/tutor/subjects").json()["subjects"]}
    assert subs.get("Mathematics") is True and subs.get("Science") is False


def test_rate_limit_429(ctx):
    db = ctx["db"]
    # pre-seed the student up to the cap with user turns dated now
    sid = db.users.find_one({"email": "s8@p30a.test"})["id"]
    now = server.now_iso()
    db.tutor_messages.insert_many([{"id": str(uuid.uuid4()), "student_id": sid, "role": "user",
                                    "subject": "Mathematics", "content": "x", "created_at": now}
                                   for _ in range(server.AI_TUTOR_DAILY_CAP)])
    r = ctx["s8"].post("/api/ai/tutor/chat", json={"subject": "Mathematics", "message": "one more"})
    assert r.status_code == 429 and "limit" in r.json()["detail"].lower()
