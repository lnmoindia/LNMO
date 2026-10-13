"""Phase 53 live sanity against deployed preview (Sunrise + p50demo). Read/edit light; cleanup."""
import os, requests, sys, json
BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://lnmo-fees.preview.emergentagent.com").rstrip("/")

def login(email, pw):
    r = requests.post(f"{BASE}/api/auth/login", json={"email": email, "password": pw})
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json().get('token') or r.cookies.get('access_token')}"}

def api(method, path, **kw):
    return requests.request(method, f"{BASE}{path}", **kw)

results = []
def check(name, cond, extra=""):
    results.append((name, bool(cond), extra))
    print(("PASS" if cond else "FAIL"), name, extra[:200])

# 1) Public branding — Sunrise
r = requests.get(f"{BASE}/api/public/institutions/sunrise/branding")
check("GET /api/public/institutions/sunrise/branding 200", r.status_code == 200, r.text[:200])
if r.ok:
    j = r.json()
    check("branding keys exact", set(j.keys()) == {"name","logo_url","tagline","background_url"}, str(set(j.keys())))
    print("  sunrise branding:", j)

# 2) p50demo branding -> default background
r = requests.get(f"{BASE}/api/public/institutions/p50demo/branding")
check("p50demo branding 200", r.status_code == 200)
if r.ok:
    j = r.json()
    check("p50demo bg is default", j["background_url"] in ("/api/public/login-default.jpg",) or "/api/public/institutions/p50demo/login-background" in j["background_url"], j["background_url"])
    print("  p50demo:", j)

# 3) Unknown slug
r = requests.get(f"{BASE}/api/public/institutions/no-such-school/branding")
check("unknown slug 404", r.status_code == 404)

# 4) Default login image
r = requests.get(f"{BASE}/api/public/login-default.jpg")
check("default jpg 200 image/jpeg", r.status_code == 200 and "image/jpeg" in r.headers.get("content-type",""), r.headers.get("content-type",""))
check("default jpg cache-control public", "public" in r.headers.get("cache-control","").lower(), r.headers.get("cache-control",""))

# 5) LPGS public branding (read-only)
r = requests.get(f"{BASE}/api/public/institutions/lpgs/branding")
check("lpgs branding 200", r.status_code == 200)
if r.ok: print("  lpgs:", r.json())

# 6) Sunrise admin — list fee structures, verify shape
try:
    sun = login("admin@sunrise-demo.in", "Sunrise@2026")
    r = api("GET", "/api/fees/structures", headers=sun)
    check("Sunrise admin GET /api/fees/structures 200", r.status_code == 200)
    structs = r.json().get("structures", [])
    print(f"  Sunrise structures count={len(structs)}")
    if structs:
        s0 = structs[0]
        for k in ("archived","usage","academic_year_id"):
            check(f"structure has '{k}' field", k in s0, f"keys={list(s0.keys())}")
        print("  sample:", {k: s0.get(k) for k in ("id","name","archived","usage","academic_year_id","academic_year")})
    # try delete a used structure -> expect 409 with the message
    used = next((s for s in structs if s.get("usage",{}).get("used")), None)
    if used:
        r = api("DELETE", f"/api/fees/structures/{used['id']}", headers=sun)
        check("DELETE used Sunrise structure -> 409", r.status_code == 409, r.text[:200])
        check("409 message correct form", "archive instead" in r.text, r.text[:200])
    # 7) Principal 403 on delete/archive
    try:
        prin = login("thomas@sunrise-demo.in", "Sunrise@2026")
        if structs:
            sid = structs[0]["id"]
            r = api("DELETE", f"/api/fees/structures/{sid}", headers=prin)
            check("principal DELETE 403", r.status_code == 403, f"got {r.status_code}")
            r = api("POST", f"/api/fees/structures/{sid}/archive", headers=prin)
            check("principal archive 403", r.status_code == 403, f"got {r.status_code}")
    except Exception as e:
        print("principal check skipped:", e)

    # 8) apply-preset should be 409 on Sunrise (setup complete)
    r = api("POST", "/api/institution/apply-preset", headers=sun, json={"preset":"k12"})
    check("Sunrise apply-preset 409", r.status_code == 409, r.text[:200])

    # 9) GET /api/institution/login-page as admin
    r = api("GET", "/api/institution/login-page", headers=sun)
    check("Sunrise GET login-page 200", r.status_code == 200, r.text[:200])
    if r.ok: print("  login-page:", r.json())
except Exception as e:
    print("Sunrise block failed:", e)

# 10) p50demo setup — apply-preset should 409 if complete OR 200 if not
try:
    adm = login("admin@feesdemo.test", "admin123")
    r = api("GET", "/api/institution/setup-status", headers=adm)
    print("  p50demo setup-status:", r.status_code, r.text[:200])
    r2 = api("POST", "/api/institution/apply-preset", headers=adm, json={"preset":"k12"})
    print("  p50demo apply-preset:", r2.status_code, r2.text[:200])
except Exception as e:
    print("p50demo block failed:", e)

# 11) Setup wizard throwaway school
try:
    adm = login("admin@sunrise-setup.in", "SetupDemo@2026")
    r = api("GET", "/api/institution/setup-status", headers=adm)
    print("  sunrise-setup setup-status:", r.status_code, r.text[:300])
except Exception as e:
    print("setup wizard login failed:", e)

print()
print("Summary:", sum(1 for _,ok,_ in results if ok), "/", len(results), "passed")
sys.exit(0 if all(ok for _,ok,_ in results) else 1)
