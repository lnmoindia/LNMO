"""Seed #3 — LPGS scale-up. MERGE-ONLY (match by name case-insensitive, skip dupes, never delete).
Does NOT touch timetable entries, publish states, subject_requirements, or principal assignments.
All via API as admin@lpgs.com (teacher must_change cleared via a final DB sweep)."""
import os, re, sys, time, requests
from pymongo import MongoClient

ROOT = "/app"
API = open(f"{ROOT}/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split("\n")[0].strip()
MONGO = [l for l in open(f"{ROOT}/backend/.env") if l.startswith("MONGO_URL=")][0].split('"')[1]
S = requests.Session()
r = S.post(f"{API}/api/auth/login", json={"email": "admin@lpgs.com", "password": "admin123"})
r.raise_for_status()
IID = S.get(f"{API}/api/auth/me").json()["institution_id"]
log = lambda *a: print(*a, flush=True)


def page(res):
    out, p = [], 1
    while True:
        d = S.get(f"{API}/api/res/{res}", params={"limit": 100, "page": p}).json()
        out += d.get("items", [])
        if p >= d.get("pages", 1):
            break
        p += 1
    return out


def post(res, body):
    r = S.post(f"{API}/api/res/{res}", json=body)
    return r.json() if r.status_code == 200 else None


# ---- reference data ----
units = {u["id"]: (u.get("code") or u["name"]).strip().upper() for u in page("academic_units")}
classes = page("classes")  # name, academic_unit_id
cls_div = {c["name"]: units.get(c["academic_unit_id"], "") for c in classes}
subjects = {s["name"].strip().lower(): s for s in page("subjects")}
sections = page("sections")
sec_have = {(s["class_name"], s["name"]) for s in sections}
mc = MongoClient(MONGO)["test_database"]
def fetch_teachers():
    return list(mc.users.find({"institution_id": IID, "role": "teacher"}, {"_id": 0}).sort("created_at", 1))
teachers = fetch_teachers()
emails_used = {u["email"].lower() for u in mc.users.find({"institution_id": IID}, {"email": 1})}

# ---- 1. sections B, C for every grade ----
made = 0
for c in classes:
    for sn in ("B", "C"):
        if (c["name"], sn) not in sec_have:
            if post("sections", {"name": sn, "class_name": c["name"], "status": "active"}):
                made += 1
log(f"sections created: {made}")

# ---- 2. subject master catalog (deduped) ----
CATALOG = ["Malayalam", "English", "Hindi", "Arabic", "Sanskrit", "Urdu", "Tamil", "Kannada",
    "Mathematics", "Environmental Studies (EVS)", "Basic Science", "Science", "Physics", "Chemistry",
    "Biology", "Social Science", "Social Science I", "Social Science II", "History", "Geography",
    "Economics", "Political Science", "Sociology", "Psychology", "Philosophy", "Statistics",
    "Computer Science", "Computer Application", "Information & Communication Technology (ICT)",
    "Electronics", "Entrepreneurship", "Accountancy", "Business Studies", "Commerce", "Home Science",
    "Geography Practical", "Physics Practical", "Chemistry Practical", "Biology Practical",
    "Computer Science Practical", "Computer Application Practical", "Electronics Practical",
    "Mathematics Lab", "Science Lab", "Computer Lab", "Language Lab", "Physical Education",
    "Health Education", "Art Education", "Music", "Work Education", "Vocational Education",
    "General Knowledge", "Life Skills", "Value Education", "Environmental Education", "Agriculture",
    "Horticulture", "Information Technology", "Engineering Graphics", "Biotechnology", "Geology",
    "Home Science Practical", "Psychology Practical", "Journalism", "Communicative English",
    "Library / Library Period", "Robotics", "Artificial Intelligence", "Coding / Programming"]
# short names used in offerings that aren't verbatim in catalog
EXTRA = ["EVS", "ICT"]
sub_made = 0
for name in CATALOG + EXTRA:
    if name.strip().lower() not in subjects:
        d = post("subjects", {"name": name, "status": "active"})
        if d:
            subjects[name.strip().lower()] = d
            sub_made += 1
log(f"subjects created: {sub_made}  total now: {len(subjects)}")

# ---- 3. teachers to 100 ----
FIRST = ["Anoop", "Deepa", "Lakshmi", "Ramesh", "Anita", "Sreeja", "Biju", "Reena", "Manoj", "Latha",
    "Vijay", "Suma", "Praveen", "Divya", "Ajith", "Nisha", "Rahul", "Gopika", "Sanjay", "Meera",
    "Hari", "Jaya", "Kiran", "Leela", "Mahesh", "Neena", "Prasad", "Remya", "Sunil", "Usha",
    "Vineeth", "Asha", "Binu", "Chandni", "Dinesh", "Elizabeth", "Febin", "Geetha", "Harish", "Indu",
    "Jacob", "Kavya", "Liju", "Minu", "Nithin", "Omana", "Pooja", "Rajesh", "Shalini", "Thomas",
    "Uma", "Varun", "Wilson", "Yamuna", "Zakir", "Arun", "Bindu", "Cyriac", "Devika", "Eldho"]
LAST = ["Nair", "Menon", "Pillai", "Thomas", "George", "Varma", "Krishnan", "Kurian", "Raj", "Das",
    "Mohan", "Kumar", "Joseph", "Mathew", "Antony", "Sebastian", "Nambiar", "Panicker", "Warrier", "Iyer"]
want = 100 - len(teachers)
added, fi, li, n = 0, 0, 0, 0
while added < want:
    fn = FIRST[fi % len(FIRST)]
    ln = LAST[li % len(LAST)]
    fi += 1
    if fi % len(FIRST) == 0:
        li += 1
    n += 1
    email = f"{fn.lower()}{n}@lpgs.com"
    if email in emails_used:
        continue
    r = S.post(f"{API}/api/teachers", json={"name": f"{fn} {ln}", "email": email,
               "password": "teach123", "status": "active"})
    if r.status_code == 200:
        emails_used.add(email)
        added += 1
    if added % 25 == 0:
        log(f"  teachers added {added}/{want}")
log(f"teachers created: {added}")
# refetch; trim any surplus over 100 (delete newest teachers with no assignments / not principals)
teachers = fetch_teachers()
if len(teachers) > 100:
    asg_ids = {a.get("teacher_id") for a in mc.teacher_assignments.find({"institution_id": IID}, {"teacher_id": 1})}
    prin_ids = {p.get("user_id") for p in mc.principal_assignments.find({"institution_id": IID}, {"user_id": 1})}
    deletable = [t for t in sorted(teachers, key=lambda x: x.get("created_at", ""), reverse=True)
                 if t["id"] not in asg_ids and t["id"] not in prin_ids]
    for t in deletable[:len(teachers) - 100]:
        mc.users.delete_one({"id": t["id"]})
    teachers = fetch_teachers()
TPOOL = teachers  # list of teacher docs (target 100)
log(f"teacher pool: {len(TPOOL)}")

# ---- 4+5. offerings per division/section + subject-teacher assignment per offering ----
DIV = {
    "LP": ["Malayalam", "English", "Mathematics", "EVS", "ICT", "Hindi", "Arabic", "Sanskrit",
           "Tamil", "Kannada", "Art Education", "Physical Education", "Work Education"],
    "UP": ["Malayalam", "English", "Hindi", "Arabic", "Sanskrit", "Tamil", "Kannada", "Urdu",
           "Mathematics", "Basic Science", "Social Science", "ICT", "Physical Education",
           "Health Education", "Art Education", "Vocational Education"],
    "HS": ["Malayalam", "English", "Hindi", "Arabic", "Sanskrit", "Urdu", "Tamil", "Kannada",
           "Physics", "Chemistry", "Biology", "Mathematics", "Social Science I", "Social Science II",
           "ICT", "Physical Education", "Health Education", "Art Education", "Work Education"],
    "HSS": ["English", "Physics", "Chemistry", "Biology", "Mathematics", "Computer Science"],
}
ACTIVITY = {"Physical Education", "Art Education", "Work Education", "Health Education", "Vocational Education"}

# lead teacher per (division, subject); activity subjects share a dedicated pool
lead = {}
cur = 0
act_pool = TPOOL[80:100] if len(TPOOL) >= 100 else TPOOL[-10:]
acur = 0
for div, subs in DIV.items():
    for s in subs:
        key = (div, s)
        if s in ACTIVITY:
            lead[key] = act_pool[acur % len(act_pool)]
            acur += 1
        else:
            lead[key] = TPOOL[cur % len(TPOOL)]
            cur += 1

off_have = {(o["class_name"], o.get("section") or "", o["subject"]) for o in page("subject_offerings")}
asg_have = {(a.get("class_name"), a.get("section") or "", a.get("subject")) for a in page("teacher_assignments")}
off_made = asg_made = 0
SECS = ["A", "B", "C"]
for c in classes:
    div = cls_div[c["name"]]
    for s in DIV.get(div, []):
        tch = lead[(div, s)]
        for sec in SECS:
            if (c["name"], sec, s) not in off_have:
                if post("subject_offerings", {"subject": s, "class_name": c["name"], "section": sec,
                                              "max_marks": 100, "status": "active"}):
                    off_made += 1
            if (c["name"], sec, s) not in asg_have:
                if post("teacher_assignments", {"teacher_email": tch["email"], "class_name": c["name"],
                                                "section": sec, "subject": s, "status": "active"}):
                    asg_made += 1
    log(f"  {c['name']} ({div}) done — offerings+{off_made} assigns+{asg_made}")
log(f"offerings created: {off_made}  assignments created: {asg_made}")

# ---- 6. class teacher per section (36 distinct teachers, prefer not-yet-leads) ----
sections = page("sections")
ct_cur = 43  # start after the academic leads band
ct_made = 0
for sec in sorted(sections, key=lambda x: (x["class_name"], x["name"])):
    if sec.get("class_teacher_id"):
        continue
    t = TPOOL[ct_cur % len(TPOOL)]
    ct_cur += 1
    r = S.put(f"{API}/api/res/sections/{sec['id']}", json={"class_teacher_id": t["id"]})
    if r.status_code == 200:
        ct_made += 1
log(f"class teachers set: {ct_made}")

# ---- 7. orphan sweep: every teacher has >=1 assignment ----
asg = page("teacher_assignments")
have_t = {a.get("teacher_id") for a in asg}
offerings = page("subject_offerings")
orphans = [t for t in TPOOL if t["id"] not in have_t]
oi = 0
swept = 0
for t in orphans:
    o = offerings[oi % len(offerings)]
    oi += 1
    if post("teacher_assignments", {"teacher_email": t["email"], "class_name": o["class_name"],
                                    "section": o.get("section") or "A", "subject": o["subject"], "status": "active"}):
        swept += 1
log(f"orphan teachers given an assignment: {swept}")

# ---- finalize: clear must_change_password for all LPGS teachers ----
res = mc.users.update_many({"institution_id": IID, "role": "teacher"},
                           {"$set": {"must_change_password": False, "status": "active"}})
log(f"must_change cleared on {res.modified_count} teachers")

# ---- counts ----
log("=== FINAL COUNTS ===")
for res_ in ("sections", "subjects", "subject_offerings", "teacher_assignments"):
    log(f"  {res_}: {len(page(res_))}")
log(f"  teachers: {mc.users.count_documents({'institution_id': IID, 'role': 'teacher'})}")
secs = page("sections")
log(f"  class-teacher coverage: {sum(1 for s in secs if s.get('class_teacher_id'))}/{len(secs)}")
log("DONE")
