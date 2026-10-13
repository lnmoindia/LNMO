"""Step 2: seed the demo school through the API (fictional names, dummy +91 98000 xxxxx numbers). Idempotent-ish."""
import io
import sys
import requests
from PIL import Image, ImageDraw
from pymongo import MongoClient
from common import ADMIN, PW

API = "http://localhost:8001/api"
db = MongoClient("mongodb://localhost:27017")["test_database"]
IID = db.institutions.find_one({"name": "Sunrise Public School (Demo)"})["id"]
AY = "2026-27"


def sess(email, pw):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": pw})
    r.raise_for_status()
    s.headers["Authorization"] = f"Bearer {r.cookies.get('access_token')}"
    return s


def ok(r, what):
    if r.status_code >= 400:
        print("FAIL", what, r.status_code, r.text[:300])
        return {}
    return r.json()


a = sess(*ADMIN)
if db.students.count_documents({"institution_id": IID}) >= 20 and "--force" not in sys.argv:
    print("already seeded"); raise SystemExit
db.institutions.update_one({"id": IID}, {"$set": {"address": "MG Road, Ernakulam, Kochi 682016", "slug": "sunrise", "is_demo": True}})
ok(a.post(f"{API}/res/academic_years", json={"name": AY, "status": "active", "start_date": "2026-06-01", "end_date": "2027-03-31"}), "ay")
units = {n: ok(a.post(f"{API}/res/academic_units", json={"name": n, "code": c, "status": "active"}), n)["id"] for n, c in (("Primary", "PRI"), ("High School", "HS"))}
CLASSES = {"Grade 5": ("Primary", ["A"]), "Grade 8": ("High School", ["A", "B"]), "Grade 9": ("High School", ["A"])}
SUBJECTS = ["English", "Mathematics", "Science", "Social Science", "Hindi", "Computer Science"]
for cn, (u, secs) in CLASSES.items():
    ok(a.post(f"{API}/res/classes", json={"name": cn, "academic_unit_id": units[u], "status": "active", "grade_level": cn.split()[-1]}), cn)
    for s in secs:
        ok(a.post(f"{API}/res/sections", json={"name": s, "class_name": cn, "status": "active"}), cn + s)
for s in SUBJECTS:
    ok(a.post(f"{API}/res/subjects", json={"name": s, "code": s[:3].upper(), "status": "active"}), s)
    for cn in CLASSES:
        ok(a.post(f"{API}/res/subject_offerings", json={"subject": s, "class_name": cn, "max_marks": 100, "status": "active"}), s + cn)
T = {}
for i, n in enumerate(["Lakshmi Menon", "Rahul Nair", "Deepa Krishnan", "Arjun Pillai", "Fathima Rasheed", "Suresh Kumar", "Meera Iyer",
                       "Thomas Mathew", "Sindhu Raghavan"]):
    em = n.split()[0].lower() + "@sunrise-demo.in"
    T[n] = ok(a.post(f"{API}/teachers", json={"name": n, "email": em, "password": PW, "status": "active", "phone": f"+91 98000 0{i:02d}10",
                                              "designation": "Teacher"}), n)
ok(a.post(f"{API}/principals", json={"teacher_id": T["Thomas Mathew"]["id"], "scope_type": "units", "unit_ids": [units["High School"]], "designation": "principal"}), "pr hs")
ok(a.post(f"{API}/principals", json={"teacher_id": T["Sindhu Raghavan"]["id"], "scope_type": "units", "unit_ids": [units["Primary"]], "designation": "principal"}), "pr lp")
secs = {(s["class_name"], s["name"]): s for s in ok(a.get(f"{API}/res/sections", params={"limit": 500}), "secs")["items"]}
for (cn, s), t in {("Grade 8", "A"): "Lakshmi Menon", ("Grade 8", "B"): "Rahul Nair", ("Grade 9", "A"): "Deepa Krishnan", ("Grade 5", "A"): "Fathima Rasheed"}.items():
    ok(a.put(f"{API}/res/sections/{secs[(cn, s)]['id']}", json={"class_teacher_id": T[t]["id"]}), "ct")
STAFF = {"English": "Meera Iyer", "Mathematics": "Lakshmi Menon", "Science": "Deepa Krishnan", "Social Science": "Rahul Nair",
         "Hindi": "Suresh Kumar", "Computer Science": "Arjun Pillai"}
PPW = {"English": 6, "Mathematics": 7, "Science": 6, "Social Science": 5, "Hindi": 4, "Computer Science": 2}
for cn, (_, ss) in CLASSES.items():
    items = [{"subject": sub, "section_teachers": {s: T["Fathima Rasheed" if cn == "Grade 5" and sub in ("English", "Mathematics") else STAFF[sub]]["id"] for s in ss},
              "periods_per_week": PPW[sub]} for sub in SUBJECTS]
    ok(a.put(f"{API}/class-hub/{cn}/subject-staff", json={"academic_year": AY, "items": items}), "staff " + cn)
ok(a.post(f"{API}/timetable/config", json={"academic_year": AY, "working_days": ["mon", "tue", "wed", "thu", "fri", "sat"], "periods": [
    {"label": "P1", "start": "09:00", "end": "09:45"}, {"label": "P2", "start": "09:45", "end": "10:30"}, {"label": "Break", "start": "10:30", "end": "10:45", "is_break": True},
    {"label": "P3", "start": "10:45", "end": "11:30"}, {"label": "P4", "start": "11:30", "end": "12:15"}, {"label": "Lunch", "start": "12:15", "end": "13:00", "is_break": True},
    {"label": "P5", "start": "13:00", "end": "13:45"}, {"label": "P6", "start": "13:45", "end": "14:30"}]}), "ttcfg")
for cn in CLASSES:
    g = ok(a.post(f"{API}/timetable/generate", json={"academic_year": AY, "class_name": cn, "auto_balance": True}), "gen " + cn)
    bid = g.get("batch_id") or (g.get("batch") or {}).get("id")
    print(cn, "generate keys", list(g)[:8], "batch", bid)
    if bid:
        ok(a.post(f"{API}/timetable/publish", json={"batch_id": bid}), "publish " + cn)
NAMES = [("Aarav", "Menon", "Grade 8", "A"), ("Diya", "Nair", "Grade 8", "A"), ("Ishaan", "Pillai", "Grade 8", "A"), ("Ananya", "Varma", "Grade 8", "A"),
         ("Vihaan", "Joseph", "Grade 8", "A"), ("Saanvi", "Kurian", "Grade 8", "A"), ("Kabir", "Rao", "Grade 8", "B"), ("Myra", "Thomas", "Grade 8", "B"),
         ("Advik", "Hegde", "Grade 8", "B"), ("Navya", "Das", "Grade 8", "B"), ("Reyansh", "George", "Grade 8", "B"), ("Tara", "Shetty", "Grade 9", "A"),
         ("Arnav", "Bhat", "Grade 9", "A"), ("Kiara", "Mathew", "Grade 9", "A"), ("Rohan", "Iyer", "Grade 9", "A"), ("Meher", "Ali", "Grade 9", "A"),
         ("Aditi", "Krishnan", "Grade 5", "A"), ("Dev", "Sharma", "Grade 5", "A"), ("Riya", "Paul", "Grade 5", "A"), ("Yash", "Gupta", "Grade 5", "A"),
         ("Zara", "Khan", "Grade 5", "A"), ("Neel", "Reddy", "Grade 5", "A")]
S = {}
for i, (fn, ln, cn, sec) in enumerate(NAMES, 1):
    body = {"first_name": fn, "last_name": ln, "admission_no": f"SPS-{i:03d}", "class_name": cn, "section": sec, "academic_year": AY,
            "guardian_name": f"{['Mr', 'Mrs'][i % 2]} {ln}", "gender": "female" if fn in ("Diya", "Ananya", "Saanvi", "Myra", "Navya", "Tara", "Kiara", "Meher", "Aditi", "Riya", "Zara") else "male",
            "date_of_birth": f"20{13 if cn == 'Grade 8' else 12 if cn == 'Grade 9' else 16}-0{(i % 9) + 1}-1{i % 9}", "enroll": True, "status": "active"}
    if i % 6:
        body["guardian_phone"] = f"98000{i:03d}00"
    r = ok(a.post(f"{API}/students/enroll", json=body), "enroll " + fn)
    S[fn] = r.get("student", r).get("id") if isinstance(r, dict) else None
print("students", len([v for v in S.values() if v]))
ok(a.post(f"{API}/students/{S['Aarav']}/parent-user", json={"email": "parent.menon@sunrise-demo.in", "password": PW, "name": "Priya Menon"}), "parent1")
ok(a.post(f"{API}/students/{S['Diya']}/parent-user", json={"email": "parent.nair@sunrise-demo.in", "password": PW, "name": "Ramesh Nair"}), "parent2")
ok(a.post(f"{API}/students/{S['Aarav']}/portal-user", json={"email": "aarav@sunrise-demo.in", "password": PW}), "student")
# exam (past window) + marks
ex = ok(a.post(f"{API}/exams", json={"name": "Term 1 Examination 2026", "type": "term", "division_configs": [
    {"academic_unit_id": units["High School"], "date_start": "2026-09-14", "date_end": "2026-09-19",
     "slots_per_day": [{"start": "09:30", "end": "12:30", "label": "Morning"}]},
    {"academic_unit_id": units["Primary"], "date_start": "2026-09-14", "date_end": "2026-09-19",
     "slots_per_day": [{"start": "10:00", "end": "12:00", "label": "Morning"}]}]}), "exam").get("exam", {})
if ex:
    ok(a.post(f"{API}/exams/{ex['id']}/generate", json={"create_registers": True}), "exam gen")
    ok(a.post(f"{API}/exams/{ex['id']}/publish"), "exam publish")
    import random
    random.seed(7)
    for asm in db.assessments.find({"institution_id": IID, "exam_id": ex["id"]}):
        studs = [s["id"] for s in db.students.find({"institution_id": IID, "class_name": asm["class_name"], **({"section": asm["section"]} if asm.get("section") else {})})]
        ok(a.post(f"{API}/assessments/{asm['id']}/marks", json={"entries": [{"student_id": s, "score": random.randint(48, 98), "status": "present"} for s in studs]}), "marks")
        ok(a.post(f"{API}/assessments/{asm['id']}/publish"), "pub asm")
ok(a.post(f"{API}/notices", json={"title": "Onam celebrations on 28 August", "body": "Traditional dress welcome. Classes end at 12:30.", "status": "published"}), "notice")
ok(a.post(f"{API}/notices", json={"title": "PTA meeting — Saturday 24 October", "body": "Parents of Grades 8 & 9: 10 am in the main hall.", "status": "published"}), "notice2")
# fees
st = {}
for u, heads in (("High School", [{"title": "Tuition fee", "amount": 9000, "frequency": "term"}, {"title": "Computer lab", "amount": 1500, "frequency": "term"}]),
                 ("Primary", [{"title": "Tuition fee", "amount": 6000, "frequency": "term"}])):
    st[u] = ok(a.post(f"{API}/fees/structures", json={"name": f"{u} fees {AY}", "academic_year": AY, "academic_unit_id": units[u], "heads": heads,
                                                     "late_fee": {"enabled": True, "type": "flat", "amount": 100, "grace_days": 10}}), "struct")
    ok(a.post(f"{API}/fees/structures/{st[u]['id']}/apply"), "apply")
acc = db.fee_accounts.find_one({"institution_id": IID, "student_id": S["Saanvi"]})
ok(a.put(f"{API}/fees/accounts/{acc['id']}", json={"discount": {"type": "percent", "value": 25, "reason": "Sibling concession"}}), "disc")
for u in st:
    ok(a.post(f"{API}/fees/structures/{st[u]['id']}/generate", json={"frequency": "term", "periods": [
        {"label": "Term 1", "due_date": "2026-07-15"}, {"label": "Term 2", "due_date": "2026-09-30"}, {"label": "Term 3", "due_date": "2026-12-15"}]}), "gen")
inv = lambda n, p: db.fee_invoices.find_one({"student_id": S[n], "period_label": p})  # noqa: E731
methods = ["cash", "upi", "cheque", "bank"]
k = 0
for fn, *_ in NAMES:
    i1 = inv(fn, "Term 1")
    if not i1 or fn in ("Kabir", "Meher"):
        continue
    k += 1
    ok(a.post(f"{API}/fees/payments", json={"invoice_id": i1["id"], "amount": i1["total"], "method": methods[k % 4],
                                           "reference": f"UTR4{k:011d}" if methods[k % 4] == "upi" else (f"CHQ{k:06d}" if methods[k % 4] == "cheque" else None),
                                           "paid_on": f"2026-07-{(k % 14) + 1:02d}"}), "pay1")
    i2 = inv(fn, "Term 2")
    if k % 3 == 0:
        ok(a.post(f"{API}/fees/payments", json={"invoice_id": i2["id"], "amount": i2["total"], "method": methods[(k + 1) % 4], "paid_on": f"2026-10-{(k % 9) + 1:02d}"}), "pay2")
    elif k % 3 == 1:
        ok(a.post(f"{API}/fees/payments", json={"invoice_id": i2["id"], "amount": round(i2["total"] / 2), "method": "cash", "paid_on": "2026-10-12"}), "pay2p")
ok(a.put(f"{API}/fees/upi-settings", json={"enabled": True, "vpa": "sunrisepublic@okhdfc", "payee_name": "Sunrise Public School",
                                         "instructions": "Write the admission number (e.g. SPS-001) in the UPI note."}), "upi")
p1, p2 = sess("parent.menon@sunrise-demo.in", PW), sess("parent.nair@sunrise-demo.in", PW)
img = Image.new("RGB", (360, 640), (245, 247, 250))
d = ImageDraw.Draw(img)
d.rectangle([0, 0, 360, 90], fill=(16, 122, 87)); d.text((20, 32), "Payment successful", fill="white")
for j, line in enumerate(["Paid to Sunrise Public School", "sunrisepublic@okhdfc", "Rs 10,500.00", "UPI Ref 512345678901", "12 Oct 2026, 09:12"]):
    d.text((20, 130 + j * 40), line, fill=(30, 41, 59))
buf = io.BytesIO(); img.save(buf, "PNG")
t2 = db.fee_invoices.find_one({"student_id": S["Aarav"], "period_label": "Term 2"})
bal = round(t2["total"] - t2.get("paid_amount", 0), 2)
ok(p1.post(f"{API}/parent/fees/invoices/{t2['id']}/proofs", files={"file": ("gpay.png", buf.getvalue(), "image/png")},
           data={"amount": str(bal), "paid_on": "2026-10-12", "utr": "512345678901", "note": "Paid via Google Pay"}), "proof")
d2 = db.fee_invoices.find_one({"student_id": S["Diya"], "period_label": "Term 2"})
ok(p2.post(f"{API}/parent/fees/invoices/{d2['id']}/issues", data={"message": "I paid ₹5,250 by bank transfer on 10 Oct but it still shows due. Please check."}), "issue")
print("seed done", S)
