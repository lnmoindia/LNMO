"""v1.2 step 7: substitutions + Class Hub data for the Sunrise demo, through real APIs."""
import requests
from pymongo import MongoClient
from common import ADMIN, PW

API = "http://localhost:8001/api"
db = MongoClient("mongodb://localhost:27017")["test_database"]
IID = db.institutions.find_one({"name": "Sunrise Public School (Demo)"})["id"]
Q = {"institution_id": IID}
TODAY, YDAY, TMRW = "2026-10-13", "2026-10-12", "2026-10-14"


def sess(email):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": ADMIN[1] if email == ADMIN[0] else PW})
    r.raise_for_status()
    s.headers["Authorization"] = f"Bearer {r.cookies.get('access_token')}"
    return s


def ok(r, what):
    print(("OK  " if r.status_code < 400 else "FAIL"), what, r.status_code, "" if r.status_code < 400 else r.text[:200])
    return r.json() if r.status_code < 400 else {}


a = sess(ADMIN[0])
T = {u["email"].split("@")[0]: u["id"] for u in db.users.find({**Q, "role": "teacher"})}
if not db.absences.count_documents(Q):
    # history: yesterday Suresh was absent, all periods auto-covered
    ab = ok(a.post(f"{API}/absences", json={"teacher_id": T["suresh"], "date": YDAY, "reason": "Family function"}), "absence suresh")
    ok(a.post(f"{API}/absences/{ab['absence']['id']}/auto-assign"), "auto-assign yesterday")
    # today: Arjun called in sick
    ab = ok(a.post(f"{API}/absences", json={"teacher_id": T["arjun"], "date": TODAY, "reason": "Fever — called in at 7:30 AM"}), "absence arjun")
    subs = sorted(a.get(f"{API}/absences/{ab['absence']['id']}").json()["substitutions"], key=lambda s: s["period_no"])
    print("subs", [(s["period_no"], s["class_name"], s["section"], s["subject"]) for s in subs])
    if subs:
        best = a.get(f"{API}/substitutions/{subs[0]['id']}/suggestions").json()["suggestions"][0]
        ok(a.post(f"{API}/substitutions/{subs[0]['id']}/assign", json={"teacher_id": best["teacher_id"]}), f"assign {best['name']}")
    if len(subs) > 1:
        sug = a.get(f"{API}/substitutions/{subs[1]['id']}/suggestions").json()["suggestions"]
        ids = [s["teacher_id"] for s in sug[:2]]
        ok(a.post(f"{API}/substitutions/{subs[1]['id']}/request", json={"teacher_ids": ids}), "request 2")
        email = next(k for k, v in T.items() if v == ids[0])
        ok(sess(f"{email}@sunrise-demo.in").post(f"{API}/substitutions/{subs[1]['id']}/respond", json={"accept": True}), f"{email} accepts")
        if len(ids) > 1:
            print("requested-still-pending:", next(k for k, v in T.items() if v == ids[1]))
    # pending leave request from a teacher for tomorrow
    ok(sess("rahul@sunrise-demo.in").post(f"{API}/absences", json={"teacher_id": T["rahul"], "date": TMRW, "reason": "Doctor's appointment"}), "rahul leave request")

# Class Hub: leaders, Period-1 rule, rooms, achievements
for sec in db.sections.find(Q):
    studs = [e["student_id"] for e in db.enrollments.find({**Q, "class_name": sec["class_name"], "section": sec["name"]})]
    body = {"room": {"Grade 5": "R-105", "Grade 8": "R-208", "Grade 9": "R-309"}[sec["class_name"]] + sec["name"], "capacity": 40}
    if len(studs) >= 2:
        body.update(class_leader_id=studs[0], second_leader_id=studs[1])
    if sec["class_name"] == "Grade 8" and sec["name"] == "A":
        body["class_teacher_first_period"] = True
    ok(a.put(f"{API}/res/sections/{sec['id']}", json=body), f"section {sec['class_name']} {sec['name']}")
if not db.achievements.count_documents(Q):
    S = {s["first_name"]: s["id"] for s in db.students.find(Q)}
    for fn, title, desc, d in [("Aarav", "District Science Fair — 2nd place", "Model on rainwater harvesting", "2026-09-26"),
                               ("Diya", "Inter-school quiz winner", "Kerala heritage quiz, team captain", "2026-10-03"),
                               ("Ananya", "State U-14 chess — bronze", "Rapid format", "2026-08-30")]:
        if fn in S:
            ok(a.post(f"{API}/res/achievements", json={"student_id": S[fn], "title": title, "description": desc, "date": d}), "ach " + fn)
print("absences", db.absences.count_documents(Q), "subs", db.substitutions.count_documents(Q), "ach", db.achievements.count_documents(Q))
