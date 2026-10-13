"""Live backend smoke test for Phase 50 against public URL (cookie auth)."""
import os, requests, json

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://lnmo-fees.preview.emergentagent.com").rstrip("/")

def login(email, pwd):
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login", json={"email": email, "password": pwd}, timeout=30)
    assert r.status_code == 200, f"login {email}: {r.status_code} {r.text}"
    return s

# ---- OpenAPI ----
r = requests.get(f"{BASE}/api/openapi.json", timeout=30)
paths = r.json().get("paths", {})
for p in ["/api/fees/defaulters", "/api/fees/defaulters/remind", "/api/fees/defaulters/export.csv",
          "/api/fees/monthly-summary", "/api/fees/carry-forward"]:
    assert p in paths, f"missing {p}"
print("OpenAPI OK")

# ---- Admin feesdemo ----
admin = login("admin@feesdemo.test", "admin123")
r = admin.get(f"{BASE}/api/fees/defaulters", timeout=30)
assert r.status_code == 200, r.text
d = r.json()
rows = d.get("rows", [])
print(f"Admin defaulters total={d.get('total')}, overdue_total={d.get('overdue_total')}, buckets={d.get('bucket_counts')}")
print("names:", sorted(x.get("student_name","") for x in rows))

r = admin.get(f"{BASE}/api/fees/monthly-summary?month=2026-10", timeout=30)
assert r.status_code == 200, r.text
m = r.json()
print("monthly keys:", list(m.keys()))
print("monthly collected/billed/outstanding:", m.get("collected"), m.get("billed"), m.get("outstanding"))

r = admin.get(f"{BASE}/api/fees/defaulters/export.csv", timeout=30)
assert r.status_code == 200
assert "text/csv" in r.headers.get("content-type",""), r.headers
print("CSV OK size=", len(r.text))

# Filters
r = admin.get(f"{BASE}/api/fees/defaulters?bucket=60%2B", timeout=30)
print("filter 60+ count:", len(r.json().get("rows", [])))
r = admin.get(f"{BASE}/api/fees/defaulters?bucket=31-60", timeout=30)
print("filter 31-60 count:", len(r.json().get("rows", [])))

# ---- Principal LP ----
plp = login("principal.lp@feesdemo.test", "teach123")
r = plp.get(f"{BASE}/api/fees/defaulters", timeout=30)
assert r.status_code == 200
print("principal.lp names:", [x.get("student_name") for x in r.json().get("rows", [])])

r = plp.get(f"{BASE}/api/fees/monthly-summary?month=2026-10", timeout=30)
print("principal.lp monthly rows:", r.status_code, len(r.json().get("per_class", [])) if r.status_code==200 else r.text[:200])

# ---- Class teacher ----
ct = login("classteacher@feesdemo.test", "teach123")
r = ct.get(f"{BASE}/api/fees/defaulters", timeout=30)
print("classteacher defaulters:", r.status_code, sorted(x.get("student_name") for x in r.json().get("rows", [])) if r.status_code==200 else r.text[:200])
r = ct.post(f"{BASE}/api/fees/defaulters/remind", json={"student_ids":["x"]}, timeout=30)
print("classteacher remind status:", r.status_code)
r = ct.get(f"{BASE}/api/fees/monthly-summary?month=2026-10", timeout=30)
print("classteacher monthly:", r.status_code)

# ---- plain teacher ----
pt = login("plainteacher@feesdemo.test", "teach123")
r = pt.get(f"{BASE}/api/fees/defaulters", timeout=30)
print("plainteacher defaulters:", r.status_code)

# ---- parent ----
par = login("parent@feesdemo.test", "parent123")
r1 = par.get(f"{BASE}/api/fees/defaulters", timeout=30)
r2 = par.post(f"{BASE}/api/fees/defaulters/remind", json={"student_ids":["x"]}, timeout=30)
r3 = par.get(f"{BASE}/api/fees/monthly-summary?month=2026-10", timeout=30)
print("parent defaulters/remind/monthly:", r1.status_code, r2.status_code, r3.status_code)

# ---- LPGS cross-tenant ----
lpgs = login("admin@lpgs.com", "admin123")
r = lpgs.get(f"{BASE}/api/fees/defaulters", timeout=30)
print("lpgs defaulters total:", r.json().get("total"), "rows:", len(r.json().get("rows", [])))
if rows:
    fd_student = rows[0]["student_id"]
    r = lpgs.post(f"{BASE}/api/fees/defaulters/remind", json={"student_ids":[fd_student]}, timeout=30)
    print("lpgs remind feesdemo student:", r.status_code, r.text[:300])

# ---- Remind flow: admin reminds Arjun (has phone) then same again -> throttle ----
arjun = next((x for x in rows if "Arjun" in x.get("student_name","")), None)
bhavya = next((x for x in rows if "Bhavya" in x.get("student_name","")), None)
if arjun:
    r = admin.post(f"{BASE}/api/fees/defaulters/remind", json={"student_ids":[arjun["student_id"]]}, timeout=30)
    print("remind arjun 1st:", r.status_code, r.text[:300])
    r = admin.post(f"{BASE}/api/fees/defaulters/remind", json={"student_ids":[arjun["student_id"]]}, timeout=30)
    print("remind arjun 2nd (expect throttled):", r.status_code, r.text[:300])
if bhavya:
    r = admin.post(f"{BASE}/api/fees/defaulters/remind", json={"student_ids":[bhavya["student_id"]]}, timeout=30)
    print("remind bhavya (expect no_contact):", r.status_code, r.text[:300])

# ---- Day book vs monthly for Oct 2026 ----
# fetch day-book totals for each day in Oct and sum
total_db = 0.0
for day in range(1, 32):
    date = f"2026-10-{day:02d}"
    r = admin.get(f"{BASE}/api/fees/day-book?date={date}", timeout=30)
    if r.status_code == 200:
        total_db += float(r.json().get("totals", {}).get("total", r.json().get("total", 0)) or 0)
print("Sum of day-book Oct totals:", total_db)
print("Monthly dump:", json.dumps(m, indent=2)[:1800])

print("DONE")
