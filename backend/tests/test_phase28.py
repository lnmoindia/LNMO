"""Phase 28 — Notices module (attachments, targeted audience, bell fan-out, send-as-message).
Throwaway DB.

Covers: attachment count/type constraints; teacher creates notice for own class (200) and other
class (403); audience-targeted visibility (Grade 4 student doesn't see a Grade 8 notice); publish
bell fan-out to the right students+parents; send-with-attachment → WhatsApp media row vs SMS
secure-link row; quota decrement; no-phone skip.
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

TEST_DB = "lnmo_phase28_test"
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
        return getattr(self._c, m)(p, headers={**self._h, **k.pop("headers", {})}, **k)

    def get(self, p, **k): return self._call("get", p, **k)
    def post(self, p, **k): return self._call("post", p, **k)
    def delete(self, p, **k): return self._call("delete", p, **k)


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
        a = platform.post("/api/res/institutions", json={"name": "SchoolA", "slug": "p28a", "admin_email": "a@p28a.test", "admin_password": "Admin@123"}).json()
        A = a["id"]
        admin = login("a@p28a.test", "Admin@123")

        mon.classes.insert_many([
            {"id": "cl8", "institution_id": A, "name": "Grade 8", "academic_unit_id": "uHS", "academic_unit_name": "HS"},
            {"id": "cl9", "institution_id": A, "name": "Grade 9", "academic_unit_id": "uHS", "academic_unit_name": "HS"},
            {"id": "cl4", "institution_id": A, "name": "Grade 4", "academic_unit_id": "uLP", "academic_unit_name": "LP"},
        ])
        mon.sections.insert_many([
            {"id": str(uuid.uuid4()), "institution_id": A, "class_name": "Grade 8", "name": "A"},
            {"id": str(uuid.uuid4()), "institution_id": A, "class_name": "Grade 4", "name": "A"},
        ])
        # students: Grade 8-A (2, one without phone) + Grade 4-A (1)
        mon.students.insert_many([
            {"id": "s8a", "institution_id": A, "first_name": "Ria", "last_name": "K", "class_name": "Grade 8", "section": "A", "enrollment_status": "enrolled", "guardian_name": "Mr K", "guardian_phone": "9000000001"},
            {"id": "s8b", "institution_id": A, "first_name": "No", "last_name": "Phone", "class_name": "Grade 8", "section": "A", "enrollment_status": "enrolled", "guardian_name": "Mr NP"},
            {"id": "s4a", "institution_id": A, "first_name": "Kiran", "last_name": "M", "class_name": "Grade 4", "section": "A", "enrollment_status": "enrolled", "guardian_name": "Mrs M", "guardian_phone": "9000000044"},
        ])
        # student + parent portal users
        s8uid, s4uid = str(uuid.uuid4()), str(uuid.uuid4())
        mon.users.insert_many([
            {"id": s8uid, "name": "Ria", "email": "ria@p28a.test", "password_hash": server.hash_password("Stud@123"), "role": "student", "student_id": "s8a", "institution_id": A, "status": "active", "must_change_password": False, "created_at": server.now_iso()},
            {"id": s4uid, "name": "Kiran", "email": "kiran@p28a.test", "password_hash": server.hash_password("Stud@123"), "role": "student", "student_id": "s4a", "institution_id": A, "status": "active", "must_change_password": False, "created_at": server.now_iso()},
            {"id": str(uuid.uuid4()), "name": "Parent8", "email": "p8@p28a.test", "password_hash": server.hash_password("Par@123"), "role": "parent", "student_ids": ["s8a"], "institution_id": A, "status": "active", "must_change_password": False, "created_at": server.now_iso()},
        ])
        # teacher assigned to Grade 8-A Maths only
        tuid = str(uuid.uuid4())
        mon.users.insert_one({"id": tuid, "name": "Maths Sir", "email": "maths@p28a.test", "password_hash": server.hash_password("Teach@123"), "role": "teacher", "institution_id": A, "status": "active", "must_change_password": False, "created_at": server.now_iso()})
        mon.teacher_assignments.insert_one({"id": str(uuid.uuid4()), "institution_id": A, "teacher_id": tuid, "teacher_email": "maths@p28a.test", "class_name": "Grade 8", "section": "A", "subject": "Maths"})

        teacher = login("maths@p28a.test", "Teach@123")
        student8 = login("ria@p28a.test", "Stud@123")
        student4 = login("kiran@p28a.test", "Stud@123")

        yield {"admin": admin, "teacher": teacher, "student8": student8, "student4": student4,
               "A": A, "db": mon, "platform": platform}
    MongoClient(server.mongo_url).drop_database(TEST_DB)


def _png(n):
    return ("f.png", io.BytesIO(b"\x89PNG\r\n" + b"x" * n), "image/png")


def test_teacher_notice_own_class_200_other_class_403(ctx):
    ok = ctx["teacher"].post("/api/notices", json={"title": "G8 Maths test tomorrow",
                             "target": {"scope": "classes", "classes": [{"class_name": "Grade 8", "section": "A"}]}})
    assert ok.status_code == 200, ok.text
    bad = ctx["teacher"].post("/api/notices", json={"title": "G9 note",
                              "target": {"scope": "classes", "classes": [{"class_name": "Grade 9", "section": "A"}]}})
    assert bad.status_code == 403
    # teacher cannot post school-wide
    school = ctx["teacher"].post("/api/notices", json={"title": "all", "target": {"scope": "school"}})
    assert school.status_code == 403


def test_attachment_type_and_count_limits(ctx):
    n = ctx["admin"].post("/api/notices", json={"title": "Circular", "target": {"scope": "school"}}).json()["notice"]
    # wrong type (docx not allowed on notices)
    bad = ctx["admin"].post(f"/api/notices/{n['id']}/attachments",
                            files=[("files", ("x.docx", io.BytesIO(b"x"), "application/vnd.openxmlformats-officedocument.wordprocessingml.document"))])
    assert bad.status_code == 400
    # too many files (>3)
    many = ctx["admin"].post(f"/api/notices/{n['id']}/attachments",
                             files=[("files", _png(10)) for _ in range(4)])
    assert many.status_code == 400
    # valid single PDF
    good = ctx["admin"].post(f"/api/notices/{n['id']}/attachments",
                             files=[("files", ("c.pdf", io.BytesIO(b"%PDF-1.4 x"), "application/pdf"))])
    assert good.status_code == 200 and len(good.json()["attachments"]) == 1


def test_targeted_visibility(ctx):
    # Grade 8-only notice
    n8 = ctx["admin"].post("/api/notices", json={"title": "G8 ONLY",
                           "target": {"scope": "classes", "classes": [{"class_name": "Grade 8"}]}}).json()["notice"]
    titles8 = [x["title"] for x in ctx["student8"].get("/api/notices/feed").json()["notices"]]
    titles4 = [x["title"] for x in ctx["student4"].get("/api/notices/feed").json()["notices"]]
    assert "G8 ONLY" in titles8 and "G8 ONLY" not in titles4
    # division-targeted (LP) → only Grade 4 student sees it
    nlp = ctx["admin"].post("/api/notices", json={"title": "LP DIV",
                            "target": {"scope": "divisions", "division_ids": ["uLP"]}}).json()["notice"]
    assert "LP DIV" in [x["title"] for x in ctx["student4"].get("/api/notices/feed").json()["notices"]]
    assert "LP DIV" not in [x["title"] for x in ctx["student8"].get("/api/notices/feed").json()["notices"]]
    assert n8 and nlp


def test_publish_fanout_to_right_bells(ctx):
    ctx["db"].notifications.delete_many({})
    n = ctx["admin"].post("/api/notices", json={"title": "G8 Sports day",
                          "target": {"scope": "classes", "classes": [{"class_name": "Grade 8"}]}}).json()
    assert n["notified_students"] == 2  # both Grade 8 students
    bells = list(ctx["db"].notifications.find({"type": "notice_new"}))
    uids = {b["user_id"] for b in bells}
    # Grade 8 student + its linked parent get a bell; Grade 4 student does NOT
    s8 = ctx["db"].users.find_one({"email": "ria@p28a.test"})["id"]
    s4 = ctx["db"].users.find_one({"email": "kiran@p28a.test"})["id"]
    p8 = ctx["db"].users.find_one({"email": "p8@p28a.test"})["id"]
    assert s8 in uids and p8 in uids and s4 not in uids


def test_send_whatsapp_media_vs_sms_link_and_quota(ctx):
    n = ctx["admin"].post("/api/notices", json={"title": "Exam circular",
                          "target": {"scope": "classes", "classes": [{"class_name": "Grade 8"}]}}).json()["notice"]
    ctx["admin"].post(f"/api/notices/{n['id']}/attachments",
                      files=[("files", ("c.pdf", io.BytesIO(b"%PDF-1.4 hello"), "application/pdf"))])
    before = ctx["admin"].get("/api/comm/status").json()["whatsapp"]["used"]
    # WhatsApp → media document, 1 recipient (s8a has phone), 1 skipped (s8b no phone)
    wa = ctx["admin"].post(f"/api/notices/{n['id']}/send", json={"channel": "whatsapp"}).json()
    assert wa["sent"] == 1 and wa["skipped_count"] == 1 and wa["has_attachment"] is True
    msg = ctx["db"].messages.find_one({"module": "notice", "channel": "whatsapp", "recipient_student_id": "s8a"})
    assert msg["has_media"] is True and "/api/comm/dl/" in (msg["media_url"] or "")
    after = ctx["admin"].get("/api/comm/status").json()["whatsapp"]["used"]
    assert after == before + 1
    # SMS → secure link in body, no media
    sms = ctx["admin"].post(f"/api/notices/{n['id']}/send", json={"channel": "sms"}).json()
    assert sms["sent"] == 1
    smsg = ctx["db"].messages.find_one({"module": "notice", "channel": "sms", "recipient_student_id": "s8a"})
    assert smsg["has_media"] is False and "/api/comm/dl/" in (smsg["body"] or "")


def test_teacher_can_send_own_notice_only(ctx):
    mine = ctx["teacher"].post("/api/notices", json={"title": "G8 reminder",
                               "target": {"scope": "classes", "classes": [{"class_name": "Grade 8", "section": "A"}]}}).json()["notice"]
    ok = ctx["teacher"].post(f"/api/notices/{mine['id']}/send", json={"channel": "whatsapp", "dry_run": True})
    assert ok.status_code == 200 and ok.json()["recipient_count"] == 1
    # a notice authored by admin → teacher cannot send it
    other = ctx["admin"].post("/api/notices", json={"title": "admin only", "target": {"scope": "school"}}).json()["notice"]
    assert ctx["teacher"].post(f"/api/notices/{other['id']}/send", json={"channel": "sms", "dry_run": True}).status_code == 403
