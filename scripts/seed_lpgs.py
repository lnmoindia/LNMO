"""Idempotent LPGS gap-fill seed (Option C: adapt in place, never delete/recreate).
Runs against the live API as platform admin (slug) + institution admin (gap-fill)."""
import os, sys, time, re, requests

BASE = None
with open("/app/frontend/.env") as f:
    for line in f:
        if line.startswith("REACT_APP_BACKEND_URL"):
            BASE = line.split("=", 1)[1].strip() + "/api"
PA_EMAIL = os.popen("grep PLATFORM_ADMIN_EMAIL /app/backend/.env | cut -d= -f2").read().strip().strip('"').lower()
PA_PW = os.popen("grep PLATFORM_ADMIN_PASSWORD /app/backend/.env | cut -d= -f2").read().strip().strip('"')

def sess(email, pw):
    s = requests.Session()
    r = s.post(f"{BASE}/auth/login", json={"email": email, "password": pw}, timeout=30)
    r.raise_for_status()
    return s

def g(s, path, **kw):
    r = s.get(f"{BASE}{path}", timeout=30, **kw); r.raise_for_status(); return r.json()
def p(s, path, body):
    r = s.post(f"{BASE}{path}", json=body, timeout=60)
    if r.status_code >= 400: return {"__err": r.status_code, "detail": r.text}
    return r.json()
def put(s, path, body):
    r = s.put(f"{BASE}{path}", json=body, timeout=60)
    if r.status_code >= 400: return {"__err": r.status_code, "detail": r.text}
    return r.json()

platform = sess(PA_EMAIL, PA_PW)
admin = sess("admin@lpgs.com", "admin123")

# --- gentle stability poll: compare class count 45s apart ---
def snapshot():
    cl = g(admin, "/res/classes", params={"limit": 200})["items"]
    return len(cl)
c1 = snapshot()
print(f"[poll] classes now: {c1}; waiting 45s to respect user mid-wizard...")
time.sleep(45)
c2 = snapshot()
print(f"[poll] classes after wait: {c2}  (changed={c1 != c2})")

inst = g(platform, "/res/institutions", params={"limit": 50})["items"]
lpgs = next(i for i in inst if i["id"].startswith("65772aac") or "LPGS" in (i.get("name") or ""))
IID = lpgs["id"]
print("institution:", lpgs.get("name"), "| domain:", lpgs.get("domain"), "| slug:", lpgs.get("slug"))

# 1) slug + trim name (platform admin)
upd = {}
if not lpgs.get("slug"):
    upd["slug"] = "lpgs"
if (lpgs.get("name") or "") != (lpgs.get("name") or "").strip():
    upd["name"] = lpgs["name"].strip()
if upd:
    r = put(platform, f"/res/institutions/{IID}", {**lpgs, **upd})
    print("slug/name update:", {k: r.get(k) for k in ("slug", "name")} if "__err" not in r else r)
else:
    print("slug already set:", lpgs.get("slug"))

# refresh units/classes
units = {u["name"]: u["id"] for u in g(admin, "/res/academic_units", params={"limit": 50})["items"]}
print("units:", list(units))
LP = units.get("Lower Primary"); HS = units.get("High School")

def classes():
    return {c["name"].upper(): c for c in g(admin, "/res/classes", params={"limit": 200})["items"]}
def sections_for(cn):
    return [s for s in g(admin, "/res/sections", params={"limit": 500})["items"] if (s.get("class_name") or "").upper() == cn.upper()]

cls = classes()
summary = {"classes_created": [], "sections_created": [], "teachers_created": [], "students_created": [], "principals": []}

# 2) ensure classes in a SECOND unit (High School): GRADE 8, GRADE 9
def ensure_class(name, grade, unit_id):
    cls_now = classes()
    if name.upper() not in cls_now:
        r = p(admin, "/res/classes", {"name": name, "grade_level": grade, "academic_unit_id": unit_id, "status": "active"})
        summary["classes_created"].append(name)
    if not sections_for(name):
        p(admin, "/res/sections", {"name": "A", "class_name": name, "status": "active"})
        summary["sections_created"].append(f"{name}-A")

if HS:
    ensure_class("GRADE 8", "8", HS)
    ensure_class("GRADE 9", "9", HS)
# ensure LP grade sections exist
for cn in ("GRADE 1", "GRADE 2"):
    if cn.upper() in classes() and not sections_for(cn):
        p(admin, "/res/sections", {"name": "A", "class_name": cn, "status": "active"})
        summary["sections_created"].append(f"{cn}-A")

# 3) subjects (add a few if only MATHS)
existing_subj = {s["name"].upper() for s in g(admin, "/res/subjects", params={"limit": 100})["items"]}
for sub, code in [("ENGLISH", "ENG"), ("SCIENCE", "SCI"), ("SOCIAL STUDIES", "SOC")]:
    if sub not in existing_subj:
        p(admin, "/res/subjects", {"name": sub, "code": code, "type": "core", "status": "active"})

# 4) teachers: deepa (LP) exists; add lakshmi(LP), ramesh(HS), anita(HS)
def teachers():
    return {t["email"]: t for t in g(admin, "/teachers", params={"limit": 100})["items"]}
TPW = "teach123"
want_teachers = [
    ("lakshmi@lpgs.com", "Lakshmi Nair"),
    ("ramesh@lpgs.com", "Ramesh Kumar"),
    ("anita@lpgs.com", "Anita Joseph"),
]
tnow = teachers()
for email, name in want_teachers:
    if email not in tnow:
        r = p(admin, "/teachers", {"name": name, "email": email, "password": TPW, "status": "active"})
        if "__err" not in r:
            summary["teachers_created"].append(email)
tnow = teachers()
deepa = tnow.get("deepa@lpgs.com")

# 5) teacher assignments (class_name, section, subject, teacher)
def assign(teacher, cn, sub="MATHS"):
    if not teacher: return
    dup = [a for a in g(admin, "/res/teacher_assignments", params={"limit": 500})["items"]
           if a.get("class_name") == cn and (a.get("teacher_email") == teacher["email"])]
    if dup: return
    p(admin, "/res/teacher_assignments", {"teacher_id": teacher["id"], "teacher_email": teacher["email"],
      "teacher_name": teacher["name"], "class_name": cn, "section": "A", "subject": sub})
assign(deepa, "GRADE 1")
assign(tnow.get("lakshmi@lpgs.com"), "GRADE 2")
assign(tnow.get("ramesh@lpgs.com"), "GRADE 8")
assign(tnow.get("anita@lpgs.com"), "GRADE 9")

# offer MATHS in HS classes so assessments/portals are consistent
for cn in ("GRADE 8", "GRADE 9"):
    if cn.upper() in classes():
        p(admin, "/subject-offerings/bulk", {"subject": "MATHS", "class_names": [cn], "section": "", "max_marks": 50})

# 6) students: ensure >=3 per division across LP + HS
def students():
    return g(admin, "/res/students", params={"limit": 200})["items"]
YEAR = "2026-27"
roster = [
    ("Aarav", "Menon", "GRADE 1"), ("Diya", "Pillai", "GRADE 1"), ("Kiran", "Das", "GRADE 2"),
    ("Meera", "Nair", "GRADE 2"),
    ("Rahul", "Varma", "GRADE 8"), ("Sneha", "Iyer", "GRADE 8"), ("Arjun", "Mohan", "GRADE 9"),
    ("Pooja", "Raj", "GRADE 9"),
]
have = {(s.get("first_name"), s.get("last_name")) for s in students()}
student_ids = {}
for fn, ln, cn in roster:
    if cn.upper() not in classes():
        continue
    if (fn, ln) in have:
        continue
    r = p(admin, "/students/enroll", {"first_name": fn, "last_name": ln, "enroll": True,
          "class_name": cn, "section": "A", "academic_year": YEAR})
    if "__err" not in r:
        summary["students_created"].append(f"{fn} {ln} ({cn})")
        student_ids[(fn, ln)] = r["id"]

# 7) a couple of student portal logins (1 LP, 1 HS)
portal_logins = []
def portal_user(first, last):
    alls = students()
    st = next((s for s in alls if s.get("first_name") == first and s.get("last_name") == last), None)
    if not st or st.get("has_portal_access"):
        return
    r = p(admin, f"/students/{st['id']}/portal-user", {})
    if "__err" not in r:
        portal_logins.append({"name": f"{first} {last}", **{k: r.get(k) for k in ("email", "password", "username")}})
portal_user("Aarav", "Menon")
portal_user("Rahul", "Varma")

# 8) attendance for GRADE 1 and GRADE 8 (one date)
def mark_attendance(cn):
    sheet = g(admin, "/attendance/sheet", params={"class_name": cn, "section": "A", "date": "2026-09-10"})
    ids = [s["id"] for s in sheet.get("students", [])]
    if not ids: return
    entries = {sid: ("present" if i % 4 else "absent") for i, sid in enumerate(ids)}
    p(admin, "/attendance/sheet", {"class_name": cn, "section": "A", "date": "2026-09-10", "entries": entries})
mark_attendance("GRADE 1")
mark_attendance("GRADE 8")

# 9) one assessment with marks (GRADE 8 MATHS) + publish
assess_id = None
existing_assess = [a for a in g(admin, "/res/assessments", params={"limit": 100})["items"]
                   if a.get("name") == "Unit Test 1" and a.get("class_name") == "GRADE 8"]
if existing_assess:
    assess_id = existing_assess[0]["id"]
elif "GRADE 8" in classes():
    r = p(admin, "/res/assessments", {"name": "Unit Test 1", "class_name": "GRADE 8", "section": "A",
          "subject": "MATHS", "max_marks": 50, "status": "draft", "date": "2026-09-12",
          "academic_year": YEAR, "type": "test"})
    if "__err" not in r:
        assess_id = r["id"]
if assess_id:
    md = g(admin, f"/assessments/{assess_id}/marks")
    entries = [{"student_id": s["id"], "score": 30 + (i * 5) % 20, "status": "present"} for i, s in enumerate(md.get("students", []))]
    if entries:
        p(admin, f"/assessments/{assess_id}/marks", {"entries": entries})
        p(admin, f"/assessments/{assess_id}/publish", {"publish": True})

# 10) one notice
if not any(n.get("title") == "Welcome to LPGS" for n in g(admin, "/res/notices", params={"limit": 50})["items"]):
    p(admin, "/res/notices", {"title": "Welcome to LPGS", "body": "School reopens for the 2026-27 session. Welcome back!",
      "message": "School reopens for the 2026-27 session. Welcome back!", "audience": "all", "date": "2026-09-01"})

# 11) principal assignments
existing_pa = {x["user_id"]: x for x in g(admin, "/principals")["items"]}
def assign_principal(teacher, scope_type, unit_ids, designation):
    if not teacher: return
    if teacher["id"] in existing_pa:
        summary["principals"].append({teacher["email"]: "already assigned"})
        return
    r = p(admin, "/principals", {"teacher_id": teacher["id"], "scope_type": scope_type,
          "unit_ids": unit_ids, "designation": designation})
    summary["principals"].append({teacher["email"]: r if "__err" in r else {"id": r.get("id"), "designation": r.get("designation"), "scope": scope_type}})

tnow = teachers()
assign_principal(tnow.get("ramesh@lpgs.com"), "whole_school", [], "principal")
assign_principal(tnow.get("deepa@lpgs.com"), "units", [LP], "principal")
assign_principal(tnow.get("lakshmi@lpgs.com"), "units", [LP], "assistant_principal")

# 12) clear must_change_password for teachers so testers can log in (flag only)
import pymongo
mc = pymongo.MongoClient(os.popen('grep MONGO_URL /app/backend/.env | cut -d\'"\' -f2').read().strip())
dbn = os.popen('grep DB_NAME /app/backend/.env | cut -d\'"\' -f2').read().strip()
res = mc[dbn].users.update_many({"institution_id": IID, "role": "teacher"}, {"$set": {"must_change_password": False}})
print("cleared must_change_password for teachers:", res.modified_count)

print("\n===== SUMMARY =====")
import json
print(json.dumps(summary, indent=2))
print("portal_logins:", json.dumps(portal_logins, indent=2))
