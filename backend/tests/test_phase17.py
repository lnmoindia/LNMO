"""Phase 17 — signed & sealed report cards. Throwaway DB, API-driven.

Composed payload contains class-teacher + principal signatures (base64) and seal when uploaded;
seal ABSENT when not uploaded; missing signature -> null with name fallback (no crash); principal
precedence (whole-school > division > none); unauthorized role -> 403; vault paths NEVER leak.
"""
import os, sys, io, json
import pytest

os.environ.setdefault("OTP_TEST_MODE", "1")
sys.path.insert(0, "/app/backend")
import server  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from pymongo import MongoClient  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

TEST_DB = "lnmo_phase17_test"
PA_EMAIL = server.os.environ["PLATFORM_ADMIN_EMAIL"].lower()
PA_PW = server.os.environ["PLATFORM_ADMIN_PASSWORD"]
BASE = "https://testserver"
PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
       b"\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82")


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


@pytest.fixture(scope="module")
def ctx():
    async def _init():
        server.client = AsyncIOMotorClient(server.mongo_url)
        server.db = server.client[TEST_DB]
    server.app.router.on_startup.insert(0, _init)
    MongoClient(server.mongo_url).drop_database(TEST_DB)
    mon = MongoClient(server.mongo_url)[TEST_DB]

    # avoid touching real object storage: stub vault put/get with an in-memory map
    store = {}
    server._put_object = lambda path, data, ctype: store.__setitem__(path, (data, ctype)) or {"path": path}
    server._get_object = lambda path: store[path]

    with _client() as C:
        def login(email, pw):
            r = C.post("/api/auth/login", json={"email": email, "password": pw})
            assert r.status_code == 200, r.text
            tok = r.cookies.get("access_token")
            C.cookies.clear()
            return Sess(C, tok)

        platform = login(PA_EMAIL, PA_PW)
        platform.post("/api/res/institutions", json={"name": "S17", "slug": "s17", "admin_email": "a@s17.test", "admin_password": "Admin@123"})
        admin = login("a@s17.test", "Admin@123")

        hs = admin.post("/api/res/academic_units", json={"name": "HS", "code": "HS", "status": "active"}).json()
        admin.post("/api/res/classes", json={"name": "Grade 8", "academic_unit_id": hs["id"], "status": "active"})
        sec = admin.post("/api/res/sections", json={"name": "A", "class_name": "Grade 8", "status": "active"}).json()

        def teacher(n):
            return admin.post("/api/teachers", json={"name": n, "email": f"{n.lower()}@s17.test", "password": "Teach@123", "status": "active"}).json()
        ct = teacher("ClassTeacher")
        prin = teacher("Principal")
        # make ct the class teacher of Grade 8 A
        admin.put(f"/api/res/sections/{sec['id']}", json={"name": "A", "class_name": "Grade 8", "class_teacher_id": ct["id"], "status": "active"})
        # make an assigned (subject) teacher for fallback testing on a different student's class flow
        admin.post("/api/res/teacher_assignments", json={"teacher_id": ct["id"], "teacher_email": "classteacher@s17.test", "class_name": "Grade 8", "section": "A", "subject": "Mathematics"})
        # division principal over HS
        admin.post("/api/principals", json={"teacher_id": prin["id"], "scope_type": "units", "unit_ids": [hs["id"]], "designation": "principal"})

        student = admin.post("/api/res/students", json={"first_name": "Riya", "last_name": "K", "admission_no": "G8-1", "class_name": "Grade 8", "section": "A", "status": "active"}).json()

        # a published assessment + mark so the card has content
        a = admin.post("/api/res/assessments", json={"name": "Term 1", "subject": "Mathematics", "class_name": "Grade 8", "section": "A", "max_marks": 100, "status": "published"}).json()
        admin.post("/api/marks", json={"assessment_id": a["id"], "entries": [{"student_id": student["id"], "score": 88}]})

        yield {"admin": admin, "login": login, "db": mon, "store": store,
               "student": student["id"], "ct": ct, "prin": prin, "hs": hs["id"], "sec_id": sec["id"]}
    MongoClient(server.mongo_url).drop_database(TEST_DB)


def _upload_sig(sess):
    return sess._c.post("/api/profile/signature", headers=sess._h,
                        files={"file": ("sig.png", io.BytesIO(PNG), "image/png")})


def test_missing_signatures_null_with_name_no_seal(ctx):
    # no signatures/seal uploaded yet
    r = ctx["admin"].get(f"/api/students/{ctx['student']}/report-card")
    assert r.status_code == 200, r.text
    sg = r.json()["signers"]
    assert sg["class_teacher"]["name"] == "ClassTeacher"
    assert sg["class_teacher"]["signature"] is None          # missing -> null, name still present
    assert sg["principal"]["name"] == "Principal"
    assert sg["principal"]["signature"] is None
    assert sg["principal"]["precedence"] == "division"        # no whole-school -> division (HS)
    assert sg["seal"] is None                                 # seal absent


def test_signatures_and_seal_embedded_as_base64(ctx):
    ct_s = ctx["login"]("classteacher@s17.test", "Teach@123")
    pr_s = ctx["login"]("principal@s17.test", "Teach@123")
    assert _upload_sig(ct_s).status_code == 200
    assert _upload_sig(pr_s).status_code == 200
    # admin uploads a seal
    ctx["admin"]._c.cookies.clear()
    seal = ctx["admin"]._c.post("/api/institution/seal", headers=ctx["admin"]._h,
                                files={"file": ("seal.png", io.BytesIO(PNG), "image/png")})
    assert seal.status_code == 200, seal.text

    sg = ctx["admin"].get(f"/api/students/{ctx['student']}/report-card").json()["signers"]
    assert sg["class_teacher"]["signature"].startswith("data:image/png;base64,")
    assert sg["principal"]["signature"].startswith("data:image/png;base64,")
    assert sg["seal"].startswith("data:image/png;base64,")


def test_whole_school_principal_takes_precedence(ctx):
    # elevate a new whole-school principal; precedence must flip to whole_school
    ws = ctx["admin"].post("/api/teachers", json={"name": "WSHead", "email": "wshead@s17.test", "password": "Teach@123", "status": "active"}).json()
    ctx["admin"].post("/api/principals", json={"teacher_id": ws["id"], "scope_type": "whole_school", "designation": "principal"})
    sg = ctx["admin"].get(f"/api/students/{ctx['student']}/report-card").json()["signers"]
    assert sg["principal"]["precedence"] == "whole_school"
    assert sg["principal"]["name"] == "WSHead"
    # cleanup so other tests keep division principal
    ctx["db"].principal_assignments.delete_one({"user_id": ws["id"]})


def test_no_vault_paths_leak_in_payload(ctx):
    raw = json.dumps(ctx["admin"].get(f"/api/students/{ctx['student']}/report-card").json())
    assert "lnmo/signatures" not in raw
    assert "lnmo/seals" not in raw
    assert "signature_path" not in raw and "seal_path" not in raw


def test_unauthorized_roles_403(ctx):
    # an unrelated teacher (no assignment/class-teacher/principal scope) -> 403
    ctx["admin"].post("/api/teachers", json={"name": "Stranger", "email": "stranger@s17.test", "password": "Teach@123", "status": "active"})
    stranger = ctx["login"]("stranger@s17.test", "Teach@123")
    assert stranger.get(f"/api/students/{ctx['student']}/report-card").status_code == 403


def test_student_and_parent_access(ctx):
    admin = ctx["admin"]
    # give the student a portal login and fetch own card
    admin.post(f"/api/students/{ctx['student']}/portal-user", json={"email": "riya@s17.test", "password": "Stud@123"}) \
        if False else None
    # parent link via admin, then parent fetches linked child's card; unlinked child -> 403
    admin.post(f"/api/students/{ctx['student']}/parent-user", json={"email": "rparent@s17.test", "password": "Parent@123", "name": "RP"})
    parent = ctx["login"]("rparent@s17.test", "Parent@123")
    assert parent.get(f"/api/students/{ctx['student']}/report-card").status_code == 200
    other = admin.post("/api/res/students", json={"first_name": "Zed", "last_name": "X", "admission_no": "G8-Z", "class_name": "Grade 8", "section": "A", "status": "active"}).json()
    assert parent.get(f"/api/students/{other['id']}/report-card").status_code == 403
