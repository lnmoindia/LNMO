"""v1.1 step 5: fill empty screens for the Sunrise demo through real APIs (STUB messaging)."""
from datetime import date, timedelta
import requests
from pymongo import MongoClient
from common import ADMIN, PA, PW

API = "http://localhost:8001/api"
db = MongoClient("mongodb://localhost:27017")["test_database"]
IID = db.institutions.find_one({"name": "Sunrise Public School (Demo)"})["id"]


def sess(email, pw):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": pw})
    r.raise_for_status()
    s.headers["Authorization"] = f"Bearer {r.cookies.get('access_token')}"
    return s


def ok(r, what):
    print(("OK  " if r.status_code < 400 else "FAIL"), what, r.status_code, "" if r.status_code < 400 else r.text[:200])
    return r.json() if r.status_code < 400 else {}


pa, a = sess(*PA), sess(*ADMIN)
lak, menon = sess("lakshmi@sunrise-demo.in", PW), sess("parent.menon@sunrise-demo.in", PW)
if not db.plans.count_documents({"name": "Starter"}):
    for n, c, pr, mx, d in [("Starter", "STARTER", 2999, 300, "Core ERP, fees, parent portal"), ("Growth", "GROWTH", 6999, 1200, "Everything in Starter + smart timetable, exams, WhatsApp"),
                            ("Enterprise", "ENT", 14999, 5000, "Multi-campus, AI Tutor, priority support")]:
        ok(pa.post(f"{API}/res/plans", json={"name": n, "code": c, "price_monthly": pr, "max_students": mx, "description": d, "status": "active"}), "plan " + n)
for ex in db.exams.find({"institution_id": IID}):
    ok(a.post(f"{API}/exams/{ex['id']}/publish-results", json={"publish": True}), "publish results")
studs = {s["first_name"]: s["id"] for s in db.students.find({"institution_id": IID})}
ok(a.post(f"{API}/fees/defaulters/remind", json={"student_ids": [studs[n] for n in ("Kabir", "Meher", "Ishaan", "Advik") if n in studs]}), "fee reminders")
ok(a.post(f"{API}/comm/send", json={"channel": "sms", "body": "Dear parent, the PTA meeting is on Saturday 24 October at 10 am in the main hall. - Sunrise Public School",
                                    "target": {"all": True}, "module": "notice"}), "notice sms")
ok(a.post(f"{API}/students/invite-parents", json={"channel": "whatsapp", "class_name": "Grade 9"}), "parent invites")
for who, s, title, desc, cat in [("teacher", lak, "Marks entry: allow decimal marks for practicals", "Science practicals are marked out of 25 with half marks.", "suggestion"),
                                  ("parent", menon, "Receipt PDF not opening on my phone", "The receipt downloads but shows a blank page on an old Android phone.", "bug"),
                                  ("admin", a, "How do we print paper invite slips for Grade 5?", "Need slips for families without a phone on file.", "question")]:
    ok(s.post(f"{API}/support/issues", data={"title": title, "description": desc, "category": cat, "route": "/app"}), "ticket " + who)
g8a = [s["id"] for s in db.students.find({"institution_id": IID, "class_name": "Grade 8", "section": "A"})]
d, n = date.today(), 0
while n < 5:
    d -= timedelta(days=1)
    if d.weekday() == 6:
        continue
    n += 1
    ok(lak.post(f"{API}/attendance/sheet", json={"class_name": "Grade 8", "section": "A", "date": d.isoformat(), "finalized": True,
                                                 "entries": {sid: ("absent" if (i + n) % 7 == 0 else "present") for i, sid in enumerate(g8a)}}), "att " + d.isoformat())
for t, due in [("Linear equations — Exercise 4.2 (Q1–Q12)", 3), ("Mensuration worksheet: surface area of cuboids", 6)]:
    ok(lak.post(f"{API}/homework", json={"class_name": "Grade 8", "section": "A", "subject": "Mathematics", "title": t,
                                         "instructions": "Show all working in your notebook.", "due_date": (date.today() + timedelta(days=due)).isoformat()}), "hw")
print("history", db.messages.count_documents({"institution_id": IID}), "tickets", db.support_issues.count_documents({"institution_id": IID}) if "support_issues" in db.list_collection_names() else "?")
