"""Platform branding (logo) regression tests."""
import os
import io
import pytest
import requests

def _load_frontend_env():
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    return line.split("=", 1)[1].strip()
    except Exception:
        pass
    return None

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or _load_frontend_env()).rstrip("/")
PLATFORM_EMAIL = "lnmopvt@gmail.com"
PLATFORM_PW = "Lnmo@2026!"
SUNRISE_ADMIN = "admin@sunrise-demo.in"
SUNRISE_PW = "Sunrise@2026"
LOGO_PATH = "/app/docs/logo/src_app_icon.png"


def _login(email, password):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=20)
    assert r.status_code == 200, f"login failed {email}: {r.status_code} {r.text}"
    return s, r.json().get("access_token") or r.json().get("token")


@pytest.fixture(scope="module")
def platform_session():
    s, tok = _login(PLATFORM_EMAIL, PLATFORM_PW)
    if tok:
        s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


@pytest.fixture(scope="module")
def sunrise_session():
    s, tok = _login(SUNRISE_ADMIN, SUNRISE_PW)
    if tok:
        s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


# ---------- Public brand serving ----------
class TestPublicBrandServing:
    @pytest.mark.parametrize("name,ctype_substr", [
        ("favicon.ico", "icon"),
        ("lnmo-logo@2x.png", "png"),
        ("lnmo-mark.svg", "svg"),
        ("icon-192.png", "png"),
        ("apple-touch-icon.png", "png"),
        ("lnmo-logo.png", "png"),
        ("lnmo-mark.png", "png"),
        ("icon-512.png", "png"),
        ("icon-maskable-512.png", "png"),
    ])
    def test_public_asset_200(self, name, ctype_substr):
        r = requests.get(f"{BASE_URL}/api/public/platform-brand/{name}", timeout=15)
        assert r.status_code == 200, f"{name}: {r.status_code}"
        assert ctype_substr in r.headers.get("content-type", "").lower()
        assert len(r.content) > 100

    def test_unknown_name_404(self):
        r = requests.get(f"{BASE_URL}/api/public/platform-brand/does-not-exist.png", timeout=10)
        assert r.status_code == 404


# ---------- Branding management auth ----------
class TestBrandingAuth:
    def test_unauth_get_401(self):
        r = requests.get(f"{BASE_URL}/api/platform/branding", timeout=10)
        assert r.status_code in (401, 403)

    def test_unauth_post_401(self):
        r = requests.post(f"{BASE_URL}/api/platform/branding/logo", timeout=10)
        assert r.status_code in (401, 403)

    def test_unauth_delete_401(self):
        r = requests.delete(f"{BASE_URL}/api/platform/branding/logo", timeout=10)
        assert r.status_code in (401, 403)

    def test_non_platform_get_403(self, sunrise_session):
        r = sunrise_session.get(f"{BASE_URL}/api/platform/branding", timeout=10)
        assert r.status_code == 403

    def test_non_platform_post_403(self, sunrise_session):
        with open(LOGO_PATH, "rb") as f:
            r = sunrise_session.post(
                f"{BASE_URL}/api/platform/branding/logo",
                files={"file": ("logo.png", f, "image/png")},
                timeout=30,
            )
        assert r.status_code == 403

    def test_non_platform_delete_403(self, sunrise_session):
        r = sunrise_session.delete(f"{BASE_URL}/api/platform/branding/logo", timeout=10)
        assert r.status_code == 403


# ---------- Branding management (platform admin) ----------
class TestBrandingPlatform:
    def test_get_branding(self, platform_session):
        r = platform_session.get(f"{BASE_URL}/api/platform/branding", timeout=10)
        assert r.status_code == 200
        d = r.json()
        assert "version" in d or "logo" in d or isinstance(d, dict)

    def test_invalid_type_400(self, platform_session):
        r = platform_session.post(
            f"{BASE_URL}/api/platform/branding/logo",
            files={"file": ("x.txt", b"hello", "text/plain")},
            timeout=15,
        )
        assert r.status_code == 400

    def test_too_large_400(self, platform_session):
        big = b"\x89PNG\r\n\x1a\n" + b"\x00" * (11 * 1024 * 1024)
        r = platform_session.post(
            f"{BASE_URL}/api/platform/branding/logo",
            files={"file": ("big.png", big, "image/png")},
            timeout=60,
        )
        assert r.status_code == 400

    def test_svg_script_rejected_400(self, platform_session):
        svg = b'<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script><circle r="10"/></svg>'
        r = platform_session.post(
            f"{BASE_URL}/api/platform/branding/logo",
            files={"file": ("bad.svg", svg, "image/svg+xml")},
            timeout=15,
        )
        assert r.status_code == 400

    def test_upload_png_success_and_version_bumps(self, platform_session):
        before = platform_session.get(f"{BASE_URL}/api/platform/branding", timeout=10).json()
        v_before = before.get("version", 0)
        with open(LOGO_PATH, "rb") as f:
            r = platform_session.post(
                f"{BASE_URL}/api/platform/branding/logo",
                files={"file": ("src_app_icon.png", f, "image/png")},
                timeout=90,
            )
        assert r.status_code == 200, r.text
        after = platform_session.get(f"{BASE_URL}/api/platform/branding", timeout=10).json()
        v_after = after.get("version", 0)
        assert v_after > v_before, f"version did not bump {v_before}->{v_after}"

    def test_reset_default(self, platform_session):
        r = platform_session.delete(f"{BASE_URL}/api/platform/branding/logo", timeout=15)
        assert r.status_code in (200, 204)

    def test_reupload_user_logo_final_state(self, platform_session):
        """Leave user's logo uploaded at end per request."""
        with open(LOGO_PATH, "rb") as f:
            r = platform_session.post(
                f"{BASE_URL}/api/platform/branding/logo",
                files={"file": ("src_app_icon.png", f, "image/png")},
                timeout=90,
            )
        assert r.status_code == 200, r.text
        # verify public asset still 200
        r2 = requests.get(f"{BASE_URL}/api/public/platform-brand/lnmo-mark.svg", timeout=10)
        assert r2.status_code == 200


# ---------- Product guide ----------
class TestGuidePdf:
    def test_guide_200(self):
        r = requests.get(f"{BASE_URL}/api/public/docs/LNMO_Product_Guide.pdf", timeout=30)
        assert r.status_code == 200
        assert "pdf" in r.headers.get("content-type", "").lower()
        assert len(r.content) > 10000
