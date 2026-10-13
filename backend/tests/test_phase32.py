"""Phase 32 — AI Tutor Response Structuring engine. LLM is MOCKED (no network).
Covers: intent->strategy mapping; strategy template present in the prompt per intent;
homework-intent Socratic guidance instruction present; anti-hallucination boundary strings;
memory extraction upsert + injection into a later prompt; memory pruning/merge; new-chat
isolation with memory retention; learning-check carry-over. Engine is pure + independent.
"""
import sys
import uuid
import pytest

sys.path.insert(0, "/app/backend")
import server  # noqa: E402
import ai_response_engine as reng  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from pymongo import MongoClient  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

TEST_DB = "lnmo_phase32_test"
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


# ---------------- Pure-engine unit tests (no DB) ----------------
def test_intent_strategy_mapping():
    assert reng.strategy_for("learn-concept") == "concept_explanation"
    assert reng.strategy_for("homework-help") == "problem_solving"
    assert reng.strategy_for("check-answer") == "answer_checking"
    assert reng.strategy_for("simpler-explanation") == "explain_simply"
    assert reng.strategy_for("follow-up") == "follow_up"


def test_rule_intent_detection():
    assert reng.detect_intent_rule("Explain photosynthesis")[0] == "learn-concept"
    assert reng.detect_intent_rule("solve 2x + 3 = 7")[0] == "solve-problem"
    assert reng.detect_intent_rule("can you do my homework for me")[0] == "homework-help"
    assert reng.detect_intent_rule("is this correct? my answer is 42")[0] == "check-answer"
    assert reng.detect_intent_rule("I didn't understand, explain simpler")[0] == "simpler-explanation"
    assert reng.detect_intent_rule("what about the second part", has_history=True)[0] == "follow-up"


def test_prompt_has_strategy_and_boundaries():
    # homework -> Socratic guidance instruction present; boundaries always present
    p = reng.build_system_prompt("Grade 8", "Mathematics", "", "homework-help")
    assert "SOCRATIC" in p and "do NOT just hand over the final answer" in p
    assert "Prioritise the school's APPROVED MATERIALS" in p
    assert "Never claim to be a teacher, principal" in p
    # concept vs explain-simply differ
    assert "Concept explanation" in reng.build_system_prompt("Grade 8", "Maths", "", "learn-concept")
    assert "simplest possible terms" in reng.build_system_prompt("Grade 8", "Maths", "", "simpler-explanation").lower() or \
        "SIMPLEST" in reng.build_system_prompt("Grade 8", "Maths", "", "simpler-explanation")


def test_memory_injection_and_grade_in_prompt():
    mem = [{"kind": "struggle", "text": "word problems with fractions"}]
    p = reng.build_system_prompt("Grade 8", "Mathematics", "", "learn-concept", memory_entries=mem)
    assert "PRIVATE TUTOR NOTES" in p and "word problems with fractions" in p
    assert "NEVER mention these notes" in p
    assert "Grade 8" in p  # grade adaptation injected


def test_memory_parse_and_merge_prune():
    parsed = reng.parse_memory_extraction("struggle: fractions\nstrength: quick at algebra\nblah\npreference: likes diagrams")
    kinds = {e["kind"] for e in parsed}
    assert kinds == {"struggle", "strength", "preference"} and len(parsed) == 3
    # merge drops exact duplicates (same kind+text) and caps size
    existing = [{"kind": "struggle", "text": "fractions"}]
    merged = reng.merge_memory(existing, [{"kind": "struggle", "text": "fractions"}, {"kind": "strength", "text": "geometry"}])
    texts = [(e["kind"], e["text"]) for e in merged]
    assert texts.count(("struggle", "fractions")) == 1 and ("strength", "geometry") in texts


def test_learning_check_extraction():
    assert reng.extract_check_question("Great. Now can you solve 3x=9 yourself?") is not None
    assert reng.extract_check_question("The capital of France is Paris.") is None


# ---------------- Integration tests (LLM mocked) ----------------
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
        a = platform.post("/api/res/institutions", json={"name": "S", "slug": "p32a", "admin_email": "a@p32a.test", "admin_password": "Admin@123"}).json()
        A = a["id"]
        mon.institutions.update_one({"id": A}, {"$set": {"features.ai_layer_enabled": True}})
        mon.academic_years.insert_one({"id": "y1", "institution_id": A, "name": YEAR, "is_active": True})
        mon.classes.insert_one({"id": "c8", "institution_id": A, "name": "Grade 8", "academic_unit_id": "uHS"})
        sid = str(uuid.uuid4())
        mon.students.insert_one({"id": sid, "institution_id": A, "class_name": "Grade 8", "section": "A",
                                 "name": "Tester", "admission_no": "G8-1"})
        uid = str(uuid.uuid4())
        mon.users.insert_one({"id": uid, "name": "Tester", "email": "stu@p32a.test",
                              "password_hash": server.hash_password("Stu@123"), "role": "student",
                              "institution_id": A, "student_id": sid, "status": "active",
                              "must_change_password": False, "created_at": server.now_iso()})
        # a published + ai_enabled Grade 8 Maths curriculum with one approved note
        cid = str(uuid.uuid4())
        mon.curricula.insert_one({"id": cid, "institution_id": A, "academic_year": YEAR, "class_name": "Grade 8",
                                  "subject": "Mathematics", "name": "G8 Maths", "status": "published",
                                  "ai_enabled": True, "is_deleted": False, "created_at": server.now_iso()})
        mon.curriculum_items.insert_one({"id": str(uuid.uuid4()), "curriculum_id": cid, "institution_id": A,
                                         "item_type": "notes", "chapter": "Algebra", "title": "Algebra basics",
                                         "text_content": "A linear equation like 2x+3=7 is solved by isolating x.",
                                         "status": "approved", "active": True, "contributor_name": "T",
                                         "contributed_at": server.now_iso()})
        S = Sess(C, login("stu@p32a.test", "Stu@123"))
        yield {"S": S, "db": mon, "A": A, "uid": uid, "cid": cid}
    MongoClient(server.mongo_url).drop_database(TEST_DB)


def _mock_llm(monkeypatch, answer="Here is the explanation. Can you try 2x=8?", mem_raw=""):
    async def fake(system_message, user_text, session_id):
        if "intent classifier" in system_message:
            return "learn-concept"
        if "DURABLE learning signals" in system_message:
            return mem_raw
        return answer
    monkeypatch.setattr(server, "_ai_llm_generate", fake)


def test_chat_stores_intent_and_strategy_metadata(ctx, monkeypatch):
    _mock_llm(monkeypatch, answer="Linear equations isolate x. Can you solve 3x=9?")
    r = ctx["S"].post("/api/ai/tutor/chat", json={"subject": "Mathematics", "message": "explain linear equations"})
    assert r.status_code == 200, r.text
    chat_id = r.json()["chat_id"]
    msgs = list(ctx["db"].tutor_messages.find({"chat_id": chat_id}))
    asst = [m for m in msgs if m["role"] == "assistant"][0]
    assert asst["intent"] == "learn-concept" and asst["strategy"] == "concept_explanation"
    # learning-check question captured for the next turn
    assert asst.get("check_question") and asst["check_question"].endswith("?")
    ctx["_chat"] = chat_id


def test_memory_update_function_upserts(ctx, monkeypatch):
    server._AI_MEMORY_SYNC = True
    _mock_llm(monkeypatch, answer="Let's go step by step. Can you try?", mem_raw="struggle: solving for x in linear equations")
    r = ctx["S"].post("/api/ai/tutor/chat", json={"subject": "Mathematics", "message": "I can't solve for x"})
    assert r.status_code == 200, r.text
    server._AI_MEMORY_SYNC = False
    doc = ctx["db"].student_memory.find_one({"student_id": ctx["uid"], "subject": "Mathematics"})
    assert doc and any("solving for x" in e["text"] for e in doc["entries"])


def test_memory_injected_into_later_prompt(ctx, monkeypatch):
    # memory stored by the previous test must now appear in the next prompt
    captured = {}

    async def fake(system_message, user_text, session_id):
        if "intent classifier" in system_message:
            return "learn-concept"
        if "DURABLE learning signals" in system_message:
            return ""
        captured["sys"] = system_message
        return "ok"
    monkeypatch.setattr(server, "_ai_llm_generate", fake)
    r = ctx["S"].post("/api/ai/tutor/chat", json={"subject": "Mathematics", "message": "teach me equations again"})
    assert r.status_code == 200
    assert "PRIVATE TUTOR NOTES" in captured["sys"] and "solving for x" in captured["sys"]


def test_new_chat_isolation_but_memory_persists(ctx, monkeypatch):
    captured = {}

    async def fake(system_message, user_text, session_id):
        if "intent classifier" in system_message:
            return "learn-concept"
        if "DURABLE learning signals" in system_message:
            return ""
        captured["sys"] = system_message
        return "fresh answer"
    monkeypatch.setattr(server, "_ai_llm_generate", fake)
    # brand-new chat (no chat_id) → no prior conversation turns, but memory still injected
    r = ctx["S"].post("/api/ai/tutor/chat", json={"subject": "Mathematics", "message": "what is a variable"})
    assert r.status_code == 200
    assert r.json()["chat_id"] != ctx["_chat"]
    assert "CONVERSATION SO FAR" not in captured["sys"]          # fresh context, not amnesia of memory
    assert "PRIVATE TUTOR NOTES" in captured["sys"]              # memory retained across chats
