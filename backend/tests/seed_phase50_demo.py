"""Phase 50 demo seed — separate TEST institution (never LPGS). Idempotent: skips if slug p50demo exists.
Run: cd /app/backend && python tests/seed_phase50_demo.py"""
import os
import uuid
from datetime import datetime, timezone, timedelta
import requests
from dotenv import load_dotenv
from pymongo import MongoClient
import sys

sys.path.insert(0, "/app/backend")
load_dotenv("/app/backend/.env")
from server import hash_password, now_iso  # noqa: E402

API = "http://localhost:8001/api"
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
T = datetime.now(timezone.utc).date()
D = lambda n: (T + timedelta(days=n)).isoformat()  # noqa: E731


def sess(email, pw):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": pw})
    r.raise_for_status()
    s.headers["Authorization"] = f"Bearer {r.cookies.get('access_token')}"
    return s


if db.institutions.find_one({"slug": "p50demo"}):
    print("already seeded"); raise SystemExit
pa = sess(os.environ["PLATFORM_ADMIN_EMAIL"], os.environ["PLATFORM_ADMIN_PASSWORD"])
r = pa.post(f"{API}/res/institutions", json={"name": "Fees Demo School (TEST)", "slug": "p50demo", "domain": "feesdemo.test",
                                              "admin_email": "admin@feesdemo.test", "admin_password": "admin123"})
r.raise_for_status()
A = r.json()["id"]
db.institutions.update_one({"id": A}, {"$set": {"code": "FDS", "domain": "feesdemo.test", "is_test": True,
                                          "contact_email": "admin@feesdemo.test", "phone": "+91 90000 00000"}})
db.academic_configuration.insert_one({"id": str(uuid.uuid4()), "institution_id": A, "preset": "custom"})
db.subjects.insert_one({"id": str(uuid.uuid4()), "institution_id": A, "name": "Mathematics", "code": "MATH", "status": "active"})
admin = sess("admin@feesdemo.test", "admin123")
units = {"LP": str(uuid.uuid4()), "HS": str(uuid.uuid4())}
for n, u in units.items():
    db.academic_units.insert_one({"id": u, "institution_id": A, "name": n, "code": n, "status": "active", "created_at": now_iso()})
for g, u in [(4, "LP"), (8, "HS"), (9, "HS")]:
    db.classes.insert_one({"id": str(uuid.uuid4()), "institution_id": A, "name": f"Grade {g}", "grade_level": str(g),
                           "academic_unit_id": units[u], "academic_unit_name": u, "created_at": now_iso()})
db.academic_years.insert_one({"id": str(uuid.uuid4()), "institution_id": A, "name": "2026-27", "status": "active", "created_at": now_iso()})


def user(email, name, role, pw, **extra):
    uid = str(uuid.uuid4())
    db.users.insert_one({"id": uid, "name": name, "email": email, "password_hash": hash_password(pw), "role": role,
                         "institution_id": A, "status": "active", "must_change_password": False, "created_at": now_iso(), **extra})
    return uid


ct = user("classteacher@feesdemo.test", "Anu Class Teacher", "teacher", "teach123")
user("plainteacher@feesdemo.test", "Ravi Plain Teacher", "teacher", "teach123")
pr = user("principal.lp@feesdemo.test", "Lekha LP Principal", "teacher", "teach123")
db.principal_assignments.insert_one({"id": str(uuid.uuid4()), "institution_id": A, "user_id": pr, "scope_type": "units",
                                     "unit_ids": [units["LP"]], "designation": "principal"})
for cn, sec, t in [("Grade 8", "A", ct), ("Grade 8", "B", None), ("Grade 4", "A", None), ("Grade 9", "A", None)]:
    db.sections.insert_one({"id": str(uuid.uuid4()), "institution_id": A, "class_name": cn, "name": sec, "status": "active",
                            "class_teacher_id": t or "", "class_teacher": "Anu Class Teacher" if t else ""})
studs = [("Arjun", "Menon", 8, "A", "9811100001"), ("Bhavya", "Nair", 8, "A", None), ("Chitra", "Das", 8, "A", "9811100003"),
         ("Dev", "Pillai", 8, "B", "9811100004"), ("Esha", "Varma", 8, "B", "9811100005"), ("Farhan", "Ali", 4, "A", "9811100006"),
         ("Gita", "Rao", 4, "A", "9811100007")]
sid = {}
for i, (fn, ln, g, sec, ph) in enumerate(studs, 1):
    s = str(uuid.uuid4()); sid[fn] = s
    doc = {"id": s, "institution_id": A, "first_name": fn, "last_name": ln, "class_name": f"Grade {g}", "section": sec,
           "enrollment_status": "enrolled", "admission_no": f"FDS-{i:03d}", "guardian_name": f"{ln} Parent", "created_at": now_iso()}
    if ph:
        doc["guardian_phone"] = ph
    db.students.insert_one(doc)
    db.enrollments.insert_one({"id": str(uuid.uuid4()), "institution_id": A, "student_id": s, "student_name": f"{fn} {ln}",
                               "admission_no": doc["admission_no"], "academic_year": "2026-27", "class_name": f"Grade {g}",
                               "section": sec, "status": "active", "created_at": now_iso()})
user("parent@feesdemo.test", "Menon Parent", "parent", "parent123", student_ids=[sid["Arjun"]], phone="9811100001")
hs = admin.post(f"{API}/fees/structures", json={"name": "HS Fees 2026-27", "academic_year": "2026-27", "academic_unit_id": units["HS"],
                "heads": [{"title": "Tuition", "amount": 6000, "frequency": "term"}]}).json()
lp = admin.post(f"{API}/fees/structures", json={"name": "LP Fees 2026-27", "academic_year": "2026-27", "academic_unit_id": units["LP"],
                "heads": [{"title": "Tuition", "amount": 4000, "frequency": "term"}]}).json()
for st in (hs, lp):
    admin.post(f"{API}/fees/structures/{st['id']}/apply").raise_for_status()
acc = db.fee_accounts.find_one({"institution_id": A, "student_id": sid["Chitra"]})
admin.put(f"{API}/fees/accounts/{acc['id']}", json={"discount": {"type": "percent", "value": 25, "reason": "Sibling concession"}}).raise_for_status()
periods = [{"label": "Term 1", "due_date": D(-75)}, {"label": "Term 2", "due_date": D(-40)}, {"label": "Term 3", "due_date": D(-12)},
           {"label": "Term 4", "due_date": D(30)}]
for st in (hs, lp):
    admin.post(f"{API}/fees/structures/{st['id']}/generate", json={"frequency": "term", "periods": periods}).raise_for_status()
inv = lambda n, p: db.fee_invoices.find_one({"student_id": sid[n], "period_label": p})  # noqa: E731
for n, p, amt, m in [("Arjun", "Term 1", 6000, "cash"), ("Arjun", "Term 2", 2500, "upi"), ("Dev", "Term 1", 6000, "bank"),
                     ("Dev", "Term 2", 6000, "upi"), ("Dev", "Term 3", 6000, "cash"), ("Esha", "Term 1", 6000, "cheque"),
                     ("Farhan", "Term 1", 1000, "cash"), ("Gita", "Term 1", 4000, "upi"), ("Gita", "Term 2", 4000, "upi"),
                     ("Gita", "Term 3", 4000, "cash"), ("Chitra", "Term 1", 4500, "cash")]:
    admin.post(f"{API}/fees/payments", json={"invoice_id": inv(n, p)["id"], "amount": amt, "method": m}).raise_for_status()
print("seeded", A)
