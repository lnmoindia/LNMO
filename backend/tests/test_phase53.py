"""Phase 53 — fee structure soft delete / archive + branded school login page. Throwaway DB."""
import io
import sys
import pytest
from PIL import Image

sys.path.insert(0, "/app/backend")
import server  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from pymongo import MongoClient  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

TEST_DB = "lnmo_phase53_test"
PA_EMAIL = server.os.environ["PLATFORM_ADMIN_EMAIL"].lower()
PA_PW = server.os.environ["PLATFORM_ADMIN_PASSWORD"]


class Sess:
    def __init__(self, c, tok):
        self._c, self._h = c, {"Authorization": f"Bearer {tok}"}

    def _call(self, m, p, **k):
        self._c.cookies.clear()
        return getattr(self._c, m)(p, headers={**self._h, **k.pop("headers", {})}, **k)

    def get(self, p, **k): return self._call("get", p, **k)
    def post(self, p, **k): return self._call("post", p, **k)
    def put(self, p, **k): return self._call("put", p, **k)
    def delete(self, p, **k): return self._call("delete", p, **k)


def _struct(name, cls="Grade 8"):
    return {"name": name, "academic_year": "2026-27", "class_name": cls, "active": True,
            "heads": [{"title": "Tuition", "amount": 1000, "frequency": "term"}]}


@pytest.fixture(scope="module")
def ctx():
    async def _init():
        server.client = AsyncIOMotorClient(server.mongo_url)
        server.db = server.client[TEST_DB]
    server.app.router.on_startup.insert(0, _init)
    mon = MongoClient(server.mongo_url)[TEST_DB]
    MongoClient(server.mongo_url).drop_database(TEST_DB)
    with TestClient(server.app, base_url="https://testserver") as C:
        def login(email, pw):
            r = C.post("/api/auth/login", json={"email": email, "password": pw})
            assert r.status_code == 200, r.text
            tok = r.cookies.get("access_token")
            C.cookies.clear()
            return Sess(C, tok)
        platform = login(PA_EMAIL, PA_PW)
        for slug in ("s53", "o53"):
            platform.post("/api/res/institutions", json={"name": slug.upper() + " School", "slug": slug,
                                                         "admin_email": f"a@{slug}.test", "admin_password": "Admin@123"})
        admin, other = login("a@s53.test", "Admin@123"), login("a@o53.test", "Admin@123")
        A = mon.institutions.find_one({"slug": "s53"})["id"]
        admin.post("/api/res/academic_years", json={"name": "2026-27", "status": "active"})
        hs = admin.post("/api/res/academic_units", json={"name": "HS", "code": "HS", "status": "active"}).json()
        admin.post("/api/res/classes", json={"name": "Grade 8", "academic_unit_id": hs["id"], "status": "active"})
        admin.post("/api/res/sections", json={"name": "A", "class_name": "Grade 8", "status": "active"})
        mon.students.insert_many([{"id": f"st{i}", "institution_id": A, "first_name": f"Kid{i}", "last_name": "X", "class_name": "Grade 8",
                                   "section": "A", "enrollment_status": "enrolled"} for i in range(2)])
        t = admin.post("/api/teachers", json={"name": "Prin", "email": "prin@s53.test", "password": "Teach@123", "status": "active"}).json()
        admin.post("/api/principals", json={"teacher_id": t["id"], "scope_type": "whole_school", "designation": "principal"})
        yield {"admin": admin, "other": other, "prin": login("prin@s53.test", "Teach@123"), "db": mon, "C": C, "A": A}
    MongoClient(server.mongo_url).drop_database(TEST_DB)


def _list(admin):
    return {s["id"]: s for s in admin.get("/api/fees/structures").json()["structures"]}


def test_unused_structure_soft_delete(ctx):
    admin, db = ctx["admin"], ctx["db"]
    st = admin.post("/api/fees/structures", json=_struct("Unused 2026")).json()
    assert _list(admin)[st["id"]]["usage"]["used"] is False
    assert ctx["prin"].delete(f"/api/fees/structures/{st['id']}").status_code == 403
    assert ctx["other"].delete(f"/api/fees/structures/{st['id']}").status_code == 404  # other school
    r = admin.delete(f"/api/fees/structures/{st['id']}")
    assert r.status_code == 200, r.text
    doc = db.fee_structures.find_one({"id": st["id"]})
    assert doc and doc["deleted"] is True and doc["deleted_by"] and doc["deleted_at"]  # soft
    assert st["id"] not in _list(admin)
    assert admin.delete(f"/api/fees/structures/{st['id']}").status_code == 404
    assert admin.post(f"/api/fees/structures/{st['id']}/apply").status_code == 404
    assert db.audit_logs.count_documents({"action": "fee_structure_delete", "entity_id": st["id"]}) == 1


def test_used_structure_409_archive_unarchive_and_history_intact(ctx):
    admin, prin, db = ctx["admin"], ctx["prin"], ctx["db"]
    st = admin.post("/api/fees/structures", json=_struct("Used 2026")).json()
    assert admin.post(f"/api/fees/structures/{st['id']}/apply").json()["created"] == 2
    g = admin.post(f"/api/fees/structures/{st['id']}/generate", json={"frequency": "term", "periods": [{"label": "Term 1", "due_date": "2026-06-30"}]})
    assert g.json()["created"] == 2
    inv = db.fee_invoices.find_one({"structure_id": st["id"], "student_id": "st0"})
    pay = admin.post("/api/fees/payments", json={"invoice_id": inv["id"], "amount": 400, "method": "cash"})
    assert pay.status_code == 200, pay.text
    u = _list(admin)[st["id"]]["usage"]
    assert u["used"] and u["students"] == 2 and u["invoices"] == 2 and u["payments"] == 1
    r = admin.delete(f"/api/fees/structures/{st['id']}")
    assert r.status_code == 409 and "Used by 2 student(s) / 2 invoice(s) — archive instead" in r.json()["detail"]
    assert not db.fee_structures.find_one({"id": st["id"]}).get("deleted")
    # archive: admin only
    assert prin.post(f"/api/fees/structures/{st['id']}/archive").status_code == 403
    a = admin.post(f"/api/fees/structures/{st['id']}/archive")
    assert a.status_code == 200 and a.json()["status"] == "archived"
    row = _list(admin)[st["id"]]
    assert row["archived"] is True
    # no new invoices / no new students
    g2 = admin.post(f"/api/fees/structures/{st['id']}/generate", json={"frequency": "term", "periods": [{"label": "Term 2", "due_date": "2026-10-30"}]})
    assert g2.status_code == 409 and "archived" in g2.json()["detail"]
    assert admin.post(f"/api/fees/structures/{st['id']}/apply").status_code == 409
    # history keeps working
    assert len(admin.get("/api/fees/accounts", params={"structure_id": st["id"]}).json()["accounts"]) == 2
    pays = admin.get("/api/fees/payments").json()
    pid = (pays.get("payments") or pays.get("items"))[0]["id"]
    assert admin.get(f"/api/fees/payments/{pid}/receipt").status_code == 200
    assert admin.get("/api/fees/day-book").status_code == 200
    d = admin.get("/api/fees/defaulters", params={"as_of": "2026-12-01"})
    assert d.status_code == 200 and "Kid0" in d.text
    stmt = admin.get("/api/fees/students/st0/statement")
    assert stmt.status_code == 200 and "Term 1" in stmt.text
    # unarchive
    assert prin.post(f"/api/fees/structures/{st['id']}/unarchive").status_code == 403
    assert admin.post(f"/api/fees/structures/{st['id']}/unarchive").json()["status"] == "active"
    assert admin.post(f"/api/fees/structures/{st['id']}/generate", json={"frequency": "term", "periods": [{"label": "Term 2", "due_date": "2026-10-30"}]}).json()["created"] == 2
    for act in ("fee_structure_archive", "fee_structure_unarchive"):
        assert db.audit_logs.count_documents({"action": act, "entity_id": st["id"]}) == 1


def test_delete_race_rolls_back(ctx, monkeypatch):
    admin, db = ctx["admin"], ctx["db"]
    st = admin.post("/api/fees/structures", json=_struct("Racy 2026")).json()
    real = server._structure_usage
    calls = {"n": 0}

    async def racy(sid):
        calls["n"] += 1
        if calls["n"] == 2:  # an account appears between the check and the mark
            await server.db.fee_accounts.insert_one({"id": "race-acc", "institution_id": ctx["A"], "structure_id": sid, "student_id": "st1", "status": "active"})
        return await real(sid)
    monkeypatch.setattr(server, "_structure_usage", racy)
    r = admin.delete(f"/api/fees/structures/{st['id']}")
    assert r.status_code == 409
    assert db.fee_structures.find_one({"id": st["id"]})["deleted"] is False
    assert st["id"] in _list(admin)


def _jpg(w=2600, h=1400, color=(200, 120, 60)):
    b = io.BytesIO()
    Image.new("RGB", (w, h), color).save(b, "JPEG", quality=95)
    return b.getvalue()


def test_login_branding_public_endpoint_upload_and_reset(ctx):
    admin, prin, C, db = ctx["admin"], ctx["prin"], ctx["C"], ctx["db"]
    C.cookies.clear()
    r = C.get("/api/public/institutions/s53/branding")
    assert r.status_code == 200
    assert set(r.json()) == {"name", "logo_url", "tagline", "background_url"}
    assert r.json()["background_url"] == "/api/public/login-default.jpg" and r.json()["tagline"] == ""
    dflt = C.get("/api/public/login-default.jpg")
    assert dflt.status_code == 200 and dflt.headers["content-type"] == "image/jpeg" and "max-age" in dflt.headers["cache-control"]
    assert C.get("/api/public/institutions/nope-xyz/branding").status_code == 404
    # admin-only settings
    assert prin.put("/api/institution/login-page", json={"tagline": "x"}).status_code == 403
    assert admin.put("/api/institution/login-page", json={"tagline": "x" * 81}).status_code == 422
    assert admin.put("/api/institution/login-page", json={"tagline": "Learning that lights the way"}).status_code == 200
    assert admin.post("/api/institution/login-page/background", files={"file": ("a.gif", b"GIF89a", "image/gif")}).status_code == 400
    assert admin.post("/api/institution/login-page/background", files={"file": ("big.jpg", b"0" * (5 * 1024 * 1024 + 1), "image/jpeg")}).status_code == 400
    assert admin.post("/api/institution/login-page/background", files={"file": ("bad.jpg", b"notanimage", "image/jpeg")}).status_code == 400
    up = admin.post("/api/institution/login-page/background", files={"file": ("bg.jpg", _jpg(), "image/jpeg")})
    assert up.status_code == 200, up.text
    assert up.json()["has_background"] is True
    C.cookies.clear()
    pub = C.get("/api/public/institutions/s53/branding").json()
    assert pub["tagline"] == "Learning that lights the way" and pub["background_url"].startswith("/api/public/institutions/s53/login-background?v=")
    img = C.get(pub["background_url"])
    assert img.status_code == 200 and "public" in img.headers["cache-control"]
    assert Image.open(io.BytesIO(img.content)).width == 1920  # resized
    assert C.get("/api/public/institutions/o53/login-background").status_code == 404  # other school has none
    # reset → default
    assert admin.delete("/api/institution/login-page/background").json()["has_background"] is False
    C.cookies.clear()
    assert C.get("/api/public/institutions/s53/branding").json()["background_url"] == "/api/public/login-default.jpg"
    for act in ("login_page_tagline", "login_page_background_upload", "login_page_background_reset"):
        assert db.audit_logs.count_documents({"action": act}) >= 1


def test_structure_year_must_be_institution_year(ctx):
    admin, other, db = ctx["admin"], ctx["other"], ctx["db"]
    yid = db.academic_years.find_one({"institution_id": ctx["A"], "name": "2026-27"})["id"]
    body = {**_struct("By id"), "academic_year_id": yid}
    body.pop("academic_year")
    r = admin.post("/api/fees/structures", json=body)
    assert r.status_code == 200 and r.json()["academic_year_id"] == yid and r.json()["academic_year"] == "2026-27"
    # another institution's year id → 404; unknown text → 400; nothing → 400
    other.post("/api/res/academic_years", json={"name": "2030-31", "status": "active"})
    oid = db.academic_years.find_one({"name": "2030-31"})["id"]
    assert admin.post("/api/fees/structures", json={**body, "academic_year_id": oid}).status_code == 404
    assert admin.post("/api/fees/structures", json={**_struct("Bad"), "academic_year": "1999-00"}).status_code == 400
    nb = _struct("None"); nb.pop("academic_year")
    assert admin.post("/api/fees/structures", json=nb).status_code == 400
    # closed year: not allowed for new, but an existing structure keeps it on edit
    closed = admin.post("/api/res/academic_years", json={"name": "2025-26", "status": "closed"}).json()
    assert admin.post("/api/fees/structures", json={**body, "academic_year_id": closed["id"]}).status_code == 400
    sid = db.fee_structures.insert_one({"id": "legacy-closed", "institution_id": ctx["A"], "name": "Old", "academic_year": "2025-26",
                                        "class_name": "Grade 8", "heads": [{"id": "h1", "title": "T", "amount": 1, "frequency": "term", "optional": False}],
                                        "late_fee": {"enabled": False, "type": "flat", "value": 0, "grace_days": 0}, "active": True,
                                        "created_at": "2025-06-01"}).inserted_id
    assert sid
    row = _list(admin)["legacy-closed"]
    assert row["academic_year_id"] == closed["id"]  # legacy text mapped at read time
    assert "academic_year_id" not in db.fee_structures.find_one({"id": "legacy-closed"})  # no write
    upd = {**_struct("Old (edited)"), "academic_year_id": closed["id"]}
    upd.pop("academic_year")
    assert admin.put("/api/fees/structures/legacy-closed", json=upd).status_code == 200
    # clone of an archived structure is a fresh active one
    admin.post("/api/fees/structures/legacy-closed/archive")
    cl = admin.post("/api/fees/structures/legacy-closed/clone").json()
    assert cl.get("status") != "archived"


def test_presets_only_while_setup_incomplete(ctx):
    admin, db = ctx["admin"], ctx["db"]
    # s53 setup is incomplete (no profile phone / config / subjects) → preset allowed
    r = admin.post("/api/institution/apply-preset", json={"preset": "k12"})
    assert r.status_code == 200, r.text
    db.institutions.update_one({"id": ctx["A"]}, {"$set": {"contact_email": "office@s53.test", "phone": "+91 90000 11111"}})
    db.academic_configuration.update_one({"institution_id": ctx["A"]}, {"$set": {"institution_type": "school"}}, upsert=True)
    admin.post("/api/res/subjects", json={"name": "Maths", "status": "active"})
    assert admin.get("/api/institution/setup-status").json()["setup_complete"] is True
    units = db.academic_units.count_documents({"institution_id": ctx["A"]})
    r = admin.post("/api/institution/apply-preset", json={"preset": "lp_up_hs_hss"})
    assert r.status_code == 409 and "setup wizard" in r.json()["detail"]
    r = admin.put("/api/institution/academic-config", json={"institution_type": "school", "school_model": "k12", "apply_presets": True})
    assert r.status_code == 409
    assert db.academic_units.count_documents({"institution_id": ctx["A"]}) == units
