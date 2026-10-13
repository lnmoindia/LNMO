"""Seed #2 — full Kerala structure for LPGS. Idempotent/merge, no timetable. As admin@lpgs.com."""
import os, json, requests, pymongo
BASE = [l for l in open("/app/frontend/.env").read().splitlines() if l.startswith("REACT_APP_BACKEND_URL")][0].split("=",1)[1].strip()+"/api"
admin = requests.Session(); admin.post(f"{BASE}/auth/login", json={"email":"admin@lpgs.com","password":"admin123"}, timeout=30)
iid = admin.get(f"{BASE}/auth/me").json()["institution_id"]
YEAR = "2026-27"
def gj(p, **kw): return admin.get(f"{BASE}{p}", timeout=30, **kw).json()
def pj(p, b):
    r = admin.post(f"{BASE}{p}", json=b, timeout=60)
    return r.json() if r.status_code < 400 else {"__err": r.status_code, "d": r.text[:120]}

# --- existing state (case-insensitive maps) ---
_ulist = gj("/res/academic_units", params={"limit":100})["items"]
units = {u["name"].strip().lower(): u for u in _ulist}
bycode = {(u.get("code") or "").strip().upper(): u for u in _ulist}
UNIT = {  # division label -> unit doc (match preset short codes OR the long names)
  "LP": bycode.get("LP") or units.get("lower primary"),
  "UP": bycode.get("UP") or units.get("upper primary"),
  "HS": bycode.get("HS") or units.get("high school"),
  "HSS": bycode.get("HSS") or units.get("higher secondary"),
}
classes = {c["name"].strip().lower(): c for c in gj("/res/classes", params={"limit":200})["items"]}
subjects = {s["name"].strip().lower(): s for s in gj("/res/subjects", params={"limit":200})["items"]}
summary = {"classes_created":[], "sections_created":[], "subjects_created":[], "offerings":0,
           "teachers_created":[], "assignments":0, "students_created":0}

GRADES = {
  "LP": [1,2,3,4], "UP": [5,6,7], "HS": [8,9,10], "HSS": [11,12],
}
SUBJECTS = {
  "LP": ["Malayalam","English","Hindi","Mathematics","EVS"],
  "UP": ["Malayalam","English","Hindi","Mathematics","Science","Social Science"],
  "HS": ["Malayalam","English","Hindi","Mathematics","Physics","Chemistry","Biology","Social Science"],
  "HSS": ["English","Physics","Chemistry","Biology","Mathematics","Computer Science"],  # Science stream
}
# reuse existing differently-named records: MATHS->Mathematics, SOCIAL STUDIES->Social Science
ALIAS = {"mathematics":"maths", "social science":"social studies"}

def ensure_subject(name):
    key = name.strip().lower()
    if key in subjects: return subjects[key]
    if ALIAS.get(key) in subjects:  # reuse existing divergent record
        return subjects[ALIAS[key]]
    code = "".join(w[0] for w in name.split())[:4].upper()
    r = pj("/res/subjects", {"name": name, "code": code, "type":"core", "status":"active"})
    if "__err" not in r:
        subjects[key] = r; summary["subjects_created"].append(name)
        return r
    return None

def ensure_class(grade, unit_doc):
    name = f"Grade {grade}"; key = name.strip().lower()
    # also treat existing "GRADE N" (user) as the same
    existing = classes.get(key) or classes.get(f"grade {grade}")
    if not existing:
        for k,c in classes.items():
            if k.replace("  "," ").strip() == f"grade {grade}":
                existing = c; break
    if existing:
        cls = existing
    else:
        r = pj("/res/classes", {"name": name, "grade_level": str(grade),
               "academic_unit_id": unit_doc["id"], "status":"active"})
        if "__err" in r: print("class err", grade, r); return None
        classes[key] = r; summary["classes_created"].append(name); cls = r
    # ensure section A
    secs = gj("/res/sections", params={"limit":500})["items"]
    has_a = any((s.get("class_name","").strip().lower()==cls["name"].strip().lower() and s.get("name","").strip().lower()=="a") for s in secs)
    if not has_a:
        pj(f"/classes/{cls['id']}/sections", {"name":"A", "capacity":40})
        summary["sections_created"].append(f"{cls['name']}-A")
    return cls

# offerings (dedup via existing)
existing_off = {(o["class_name"].strip().lower(), o["subject"].strip().lower())
                for o in gj("/res/subject_offerings", params={"limit":1000})["items"]}
def ensure_offering(class_name, subject_name):
    k = (class_name.strip().lower(), subject_name.strip().lower())
    if k in existing_off: return
    r = pj("/subject-offerings/bulk", {"subject": subject_name, "class_names":[class_name], "section":"", "max_marks":100})
    if "__err" not in r:
        existing_off.add(k); summary["offerings"] += 1

# --- build classes + subjects + offerings per division ---
div_classes = {}
for div, grades in GRADES.items():
    udoc = UNIT[div]
    if not udoc: print("missing unit", div); continue
    subs = [ensure_subject(s) for s in SUBJECTS[div]]
    subs = [s for s in subs if s]
    div_classes[div] = []
    for g in grades:
        cls = ensure_class(g, udoc)
        if not cls: continue
        div_classes[div].append(cls)
        for s in subs:
            ensure_offering(cls["name"], s["name"])

# --- teachers: keep existing 4, add ~6 more ---
teachers = {t["email"]: t for t in gj("/teachers", params={"limit":200})["items"]}
NEW_TEACHERS = [
  ("Sreeja Menon","sreeja@lpgs.com","LP"), ("Biju Thomas","biju@lpgs.com","UP"),
  ("Reena George","reena@lpgs.com","UP"), ("Manoj Pillai","manoj@lpgs.com","HS"),
  ("Latha Krishnan","latha@lpgs.com","HSS"), ("Vijay Nair","vijay@lpgs.com","HSS"),
]
for name,email,div in NEW_TEACHERS:
    if email not in teachers:
        r = pj("/teachers", {"name":name,"email":email,"password":"teach123","status":"active"})
        if "__err" not in r:
            teachers[email]=r; summary["teachers_created"].append(email)
# map division -> teacher emails (existing + new)
DIV_TEACHERS = {
  "LP": ["deepa@lpgs.com","lakshmi@lpgs.com","sreeja@lpgs.com"],
  "UP": ["biju@lpgs.com","reena@lpgs.com"],
  "HS": ["ramesh@lpgs.com","anita@lpgs.com","manoj@lpgs.com"],
  "HSS": ["latha@lpgs.com","vijay@lpgs.com"],
}
# existing assignments dedup
existing_as = {(a.get("class_name","").strip().lower(), a.get("teacher_email",""))
               for a in gj("/res/teacher_assignments", params={"limit":1000})["items"]}
def assign(cls_name, email, subject=None):
    t = teachers.get(email)
    if not t: return
    if (cls_name.strip().lower(), email) in existing_as: 
        # still ensure class has a teacher; count as covered
        return
    body = {"teacher_id":t["id"], "teacher_email":email, "teacher_name":t["name"],
            "class_name":cls_name, "section":"A"}
    if subject: body["subject"]=subject
    r = pj("/res/teacher_assignments", body)
    if "__err" not in r:
        existing_as.add((cls_name.strip().lower(), email)); summary["assignments"]+=1

# every class gets a class teacher (round-robin within division) + subject teachers
for div, cls_list in div_classes.items():
    tlist = [e for e in DIV_TEACHERS[div] if e in teachers]
    if not tlist: continue
    subs = SUBJECTS[div]
    for i, cls in enumerate(cls_list):
        # class teacher
        assign(cls["name"], tlist[i % len(tlist)])
        # subject teachers: spread subjects across division teachers
        for j, sname in enumerate(subs):
            assign(cls["name"], tlist[j % len(tlist)], subject=sname)

# --- students: ~2-3 per grade, keep existing ---
studs = gj("/res/students", params={"limit":500})["items"]
by_class = {}
for s in studs:
    by_class.setdefault((s.get("class_name") or "").strip().lower(), 0)
    by_class[(s.get("class_name") or "").strip().lower()] += 1
NAMES = ["Aravind","Anjali","Fathima","Govind","Haritha","Irfan","Jyothi","Kiran","Nithya","Rahul",
         "Sania","Thomas","Vishnu","Zara","Amal","Devika","Nikhil","Parvathy","Sachin","Varsha"]
ni = 0
for div, cls_list in div_classes.items():
    for cls in cls_list:
        have = by_class.get(cls["name"].strip().lower(), 0)
        need = max(0, 3 - have)
        for _ in range(need):
            fn = NAMES[ni % len(NAMES)]; ni += 1
            ln = NAMES[(ni*2) % len(NAMES)]; ni += 1
            r = pj("/students/enroll", {"first_name":fn, "last_name":ln, "enroll":True,
                   "class_name":cls["name"], "section":"A", "academic_year":YEAR})
            if "__err" not in r: summary["students_created"]+=1

# clear must_change for all teachers
mc = pymongo.MongoClient(os.popen('grep MONGO_URL /app/backend/.env | cut -d\'"\' -f2').read().strip())
dbn = os.popen('grep DB_NAME /app/backend/.env | cut -d\'"\' -f2').read().strip()
mc[dbn].users.update_many({"institution_id":iid,"role":"teacher"},{"$set":{"must_change_password":False}})

print(json.dumps(summary, indent=2))
# counts
print("TOTAL classes:", gj("/res/classes", params={"limit":1})["total"])
print("TOTAL students:", gj("/res/students", params={"limit":1})["total"])
print("TOTAL teachers:", gj("/teachers", params={"limit":1})["total"])
print("TOTAL subjects:", gj("/res/subjects", params={"limit":1})["total"])
print("TOTAL offerings:", gj("/res/subject_offerings", params={"limit":1})["total"])
print("TOTAL assignments:", gj("/res/teacher_assignments", params={"limit":1})["total"])
