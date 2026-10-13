"""Phase 35 — @mentions on curriculum review comments.
Covers: mention candidates = contributors + assigned subject teachers; a mentioned teacher gets an
ai_comment_mention bell deep-linking to the curriculum; unrelated teachers are NOT notified;
mentions outside the allowed set are ignored; permissions unchanged (only principal/admin comment).
"""
import sys
import uuid
import pytest

sys.path.insert(0, "/app/backend")
import server  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from pymongo import MongoClient  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

TEST_DB = "lnmo_phase35_test"
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
        A = platform.post("/api/res/institutions", json={"name": "S", "slug": "p35a", "admin_email": "a@p35a.test", "admin_password": "Admin@123"}).json()["id"]
        admin = Sess(C, login("a@p35a.test", "Admin@123"))
        mon.classes.insert_one({"id": "c8", "institution_id": A, "name": "Grade 8", "academic_unit_id": "uHS"})

        def mk(email, name):
            uid = str(uuid.uuid4())
            mon.users.insert_one({"id": uid, "name": name, "email": email, "password_hash": server.hash_password("Teach@123"),
                                  "role": "teacher", "institution_id": A, "status": "active", "must_change_password": False, "created_at": server.now_iso()})
            return uid
        radha = mk("radha@p35a.test", "Radha")    # owner (Grade 8 Maths)
        suma = mk("suma@p35a.test", "Suma")        # second Grade 8 Maths teacher (assigned)
        other = mk("other@p35a.test", "Other")     # unrelated (Grade 8 Science)
        for tid, email in [(radha, "radha@p35a.test"), (suma, "suma@p35a.test")]:
            mon.teacher_assignments.insert_one({"id": str(uuid.uuid4()), "institution_id": A, "teacher_id": tid, "teacher_email": email, "class_name": "Grade 8", "section": "A", "subject": "Mathematics"})
        mon.teacher_assignments.insert_one({"id": str(uuid.uuid4()), "institution_id": A, "teacher_id": other, "teacher_email": "other@p35a.test", "class_name": "Grade 8", "section": "A", "subject": "Science"})
        R = Sess(C, login("radha@p35a.test", "Teach@123"))

        r = R.post("/api/ai/curriculum", json={
            "academic_year": YEAR, "class_name": "Grade 8", "subject": "Mathematics", "name": "G8 Maths",
            "chapters": [{"chapter": "Algebra"}],
            "items": [{"item_type": "textbook", "title": "TB"}, {"item_type": "notes", "chapter": "Algebra", "title": "N", "text_content": "x"}],
            "submit": True})
        cid = r.json()["curriculum"]["id"]
        admin.post(f"/api/ai/curriculum/{cid}/review", json={"action": "approve"})
        yield {"admin": admin, "R": R, "db": mon, "A": A, "cid": cid,
               "radha": radha, "suma": suma, "other": other}
    MongoClient(server.mongo_url).drop_database(TEST_DB)


def _bell(mon, uid, ntype):
    return mon.notifications.count_documents({"user_id": uid, "type": ntype})


def test_mention_candidates_are_contributors_and_subject_teachers(ctx):
    cands = ctx["admin"].get(f"/api/ai/curriculum/{ctx['cid']}/mention-candidates").json()["candidates"]
    ids = {c["id"] for c in cands}
    assert ctx["radha"] in ids and ctx["suma"] in ids  # owner + assigned maths teacher
    assert ctx["other"] not in ids                      # Science teacher is not a candidate


def test_mention_notifies_only_mentioned_teacher(ctx):
    mon = ctx["db"]
    before_suma = _bell(mon, ctx["suma"], "ai_comment_mention")
    before_other = _bell(mon, ctx["other"], "ai_comment_mention")
    r = ctx["admin"].post(f"/api/ai/curriculum/{ctx['cid']}/comments",
                          json={"text": "Please review Chapter 2 together.", "mentions": [ctx["suma"]]})
    assert r.status_code == 200, r.text
    cm = r.json()["comment"]
    assert ctx["suma"] in cm["mentions"] and "Suma" in cm["mention_names"]
    # the mentioned teacher is pinged; an unrelated teacher is not
    assert _bell(mon, ctx["suma"], "ai_comment_mention") == before_suma + 1
    assert _bell(mon, ctx["other"], "ai_comment_mention") == before_other


def test_mention_bell_deep_links_to_curriculum(ctx):
    n = ctx["db"].notifications.find_one({"user_id": ctx["suma"], "type": "ai_comment_mention"},
                                         sort=[("created_at", -1)])
    assert n and n.get("related_id") == ctx["cid"]
    assert "mentioned" in n["title"].lower() and "Grade 8 Mathematics" in n["title"]


def test_invalid_mentions_ignored_and_permissions_unchanged(ctx):
    # a random/unauthorised id is silently dropped, not notified
    before = _bell(ctx["db"], ctx["other"], "ai_comment_mention")
    r = ctx["admin"].post(f"/api/ai/curriculum/{ctx['cid']}/comments",
                          json={"text": "note", "mentions": [ctx["other"], "nonexistent-id"]})
    assert r.status_code == 200
    # 'other' teaches Science (not a candidate for this Maths curriculum) → not a valid mention
    assert ctx["other"] not in r.json()["comment"]["mentions"]
    assert _bell(ctx["db"], ctx["other"], "ai_comment_mention") == before
    # permission unchanged: a plain teacher still cannot post review comments / mention
    assert ctx["R"].post(f"/api/ai/curriculum/{ctx['cid']}/comments", json={"text": "x", "mentions": [ctx["suma"]]}).status_code == 403
    assert ctx["R"].get(f"/api/ai/curriculum/{ctx['cid']}/mention-candidates").status_code == 403
