"""Phase 4 — platform cleanup (tenants removal) + school branding (logo + slug) backend tests.

ISOLATION: runs the FastAPI app in-process via TestClient against a SEPARATE test database
(`lnmo_phase4_test`), creates throwaway institutions, and DROPS the test DB at the end.

Run serially:  pytest backend/tests/test_phase4.py -v -n 0
"""
import sys
import struct
import zlib
import pytest

sys.path.insert(0, "/app/backend")
import server  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from pymongo import MongoClient  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

TEST_DB = "lnmo_phase4_test"
PA_EMAIL = server.os.environ["PLATFORM_ADMIN_EMAIL"].lower()
PA_PW = server.os.environ["PLATFORM_ADMIN_PASSWORD"]
BASE = "https://testserver"


def _tiny_png():
    # 1x1 transparent PNG
    sig = b"\x89PNG\r\n\x1a\n"
    def chunk(typ, data):
        return struct.pack(">I", len(data)) + typ + data + struct.pack(">I", zlib.crc32(typ + data) & 0xffffffff)
    ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0))
    idat = chunk(b"IDAT", zlib.compress(b"\x00\x00\x00\x00\x00"))
    iend = chunk(b"IEND", b"")
    return sig + ihdr + idat + iend


def _client():
    return TestClient(server.app, base_url=BASE)


class Sess:
    def __init__(self, client, token):
        self._c = client
        self._h = {"Authorization": f"Bearer {token}"}

    def _call(self, method, path, **kw):
        self._c.cookies.clear()
        headers = {**self._h, **kw.pop("headers", {})}
        return getattr(self._c, method)(path, headers=headers, **kw)

    def get(self, p, **k): return self._call("get", p, **k)
    def post(self, p, **k): return self._call("post", p, **k)
    def put(self, p, **k): return self._call("put", p, **k)
    def delete(self, p, **k): return self._call("delete", p, **k)


@pytest.fixture(scope="module")
def world():
    async def _init_test_db():
        server.client = AsyncIOMotorClient(server.mongo_url)
        server.db = server.client[TEST_DB]
    server.app.router.on_startup.insert(0, _init_test_db)
    MongoClient(server.mongo_url).drop_database(TEST_DB)

    w = {}
    with _client() as C:
        def login(email, pw):
            r = C.post("/api/auth/login", json={"email": email, "password": pw})
            assert r.status_code == 200, r.text
            tok = r.cookies.get("access_token")
            C.cookies.clear()
            return Sess(C, tok)

        w["C"] = C
        platform = login(PA_EMAIL, PA_PW)
        w["platform"] = platform

        r = platform.post("/api/res/institutions", json={
            "name": "Greenwood High", "domain": "greenwood.edu", "slug": "greenwood",
            "admin_email": "admin@greenwood.edu", "admin_password": "Admin@123"})
        assert r.status_code == 200, r.text
        w["inst"] = r.json()
        w["admin"] = login("admin@greenwood.edu", "Admin@123")
        w["login"] = login
        yield w

    MongoClient(server.mongo_url).drop_database(TEST_DB)


# ---------------- Tenants removal ----------------

def test_platform_stats_has_no_tenants_key(world):
    counts = world["platform"].get("/api/platform/stats").json()["counts"]
    assert "tenants" not in counts
    assert {"institutions", "plans", "users"}.issubset(counts.keys())


def test_tenants_resource_is_gone(world):
    # unknown resource → 404 for list/create
    assert world["platform"].get("/api/res/tenants").status_code == 404
    assert world["platform"].post("/api/res/tenants", json={"name": "X"}).status_code == 404


def test_search_excludes_tenants(world):
    r = world["platform"].get("/api/search", params={"q": "green"})
    assert r.status_code == 200
    labels = [g["label"] for g in r.json().get("groups", [])]
    assert "Tenants" not in labels


# ---------------- Slug normalization + uniqueness ----------------

def test_slug_rejects_invalid_characters(world):
    r = world["platform"].post("/api/res/institutions", json={"name": "Bad One", "slug": "bad slug"})
    assert r.status_code == 400, r.text


def test_slug_is_normalized_lowercase(world):
    r = world["platform"].post("/api/res/institutions", json={"name": "Upper School", "slug": "UpperCase"})
    assert r.status_code == 200, r.text
    assert r.json()["slug"] == "uppercase"


def test_duplicate_slug_conflicts_400(world):
    r = world["platform"].post("/api/res/institutions", json={"name": "Dup", "slug": "greenwood"})
    assert r.status_code == 400, r.text


def test_update_to_taken_slug_conflicts_400(world):
    created = world["platform"].post("/api/res/institutions", json={"name": "Movable", "slug": "movable"}).json()
    # taking an existing slug → 400
    r = world["platform"].put(f"/api/res/institutions/{created['id']}", json={"slug": "greenwood"})
    assert r.status_code == 400, r.text
    # a fresh slug → 200
    r = world["platform"].put(f"/api/res/institutions/{created['id']}", json={"slug": "movable-2"})
    assert r.status_code == 200 and r.json()["slug"] == "movable-2", r.text


def test_institution_admin_cannot_change_slug(world):
    # slug is platform-owned; profile PUT must ignore it
    world["admin"].put("/api/institution/profile", json={"name": "Greenwood High", "slug": "hacked"})
    inst = world["platform"].get(f"/api/res/institutions/{world['inst']['id']}").json()
    assert inst["slug"] == "greenwood"


# ---------------- Public branding: slug/domain parity ----------------

def test_branding_by_slug_and_domain_parity(world):
    C = world["C"]
    by_domain = C.get("/api/public/branding", params={"domain": "greenwood.edu"}).json()
    by_slug = C.get("/api/public/branding", params={"slug": "greenwood"}).json()
    assert by_domain.get("name") == by_slug.get("name") == "Greenwood High"
    assert by_slug.get("slug") == "greenwood"
    assert by_domain.get("domain") == "greenwood.edu"
    # unknown → {}
    assert C.get("/api/public/branding", params={"slug": "nope"}).json() == {}
    assert C.get("/api/public/branding").json() == {}


# ---------------- Logo: constraints + public endpoint ----------------

def test_logo_rejects_bad_content_type(world):
    r = world["admin"].post("/api/institution/logo",
                            files={"file": ("x.txt", b"hello", "text/plain")})
    assert r.status_code == 400, r.text


def test_logo_rejects_too_large(world):
    big = b"\x89PNG\r\n\x1a\n" + b"0" * (4 * 1024 * 1024 + 10)
    r = world["admin"].post("/api/institution/logo",
                            files={"file": ("big.png", big, "image/png")})
    assert r.status_code == 400, r.text


def test_public_logo_404_when_none(world):
    C = world["C"]
    assert C.get("/api/public/institution-logo", params={"slug": "greenwood"}).status_code == 404
    assert C.get("/api/public/institution-logo").status_code == 404


def test_logo_upload_and_public_fetch_roundtrip(world):
    C = world["C"]
    r = world["admin"].post("/api/institution/logo",
                            files={"file": ("logo.png", _tiny_png(), "image/png")})
    if r.status_code == 502:
        pytest.skip("object storage unavailable in this environment")
    assert r.status_code == 200 and r.json().get("has_logo") is True, r.text
    # branding now reports has_logo
    assert C.get("/api/public/branding", params={"slug": "greenwood"}).json().get("has_logo") is True
    # public logo (auth-free) returns image bytes
    pr = C.get("/api/public/institution-logo", params={"slug": "greenwood"})
    assert pr.status_code == 200 and pr.headers["content-type"].startswith("image/") and len(pr.content) > 0
    assert C.get("/api/public/institution-logo", params={"domain": "greenwood.edu"}).status_code == 200
    # delete → falls back to 404
    assert world["admin"].delete("/api/institution/logo").status_code == 200
    assert C.get("/api/public/institution-logo", params={"slug": "greenwood"}).status_code == 404
    assert C.get("/api/public/branding", params={"slug": "greenwood"}).json().get("has_logo") is False
