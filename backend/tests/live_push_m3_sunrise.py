"""LIVE check of push hooks on Sunrise (never LPGS) with FAKE device tokens → Expo answers DeviceNotRegistered (expected).
Run: cd /app/backend && python tests/live_push_m3_sunrise.py"""
import os
import time
from datetime import datetime, timedelta, timezone

import requests
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/app/backend/.env")
API = open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split()[0].rstrip("/") + "/api"
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
inst = db.institutions.find_one({"slug": "sunrise"})
assert inst["code"] == "SPS"
IID = inst["id"]
PW = "Sunrise@2026"
FAKE = {"parent": "ExponentPushToken[QAsunriseParentMenon01]", "student": "ExponentPushToken[QAsunriseStudentAarav1]",
        "teacher": "ExponentPushToken[QAsunriseTeacherLaksh1]"}
EMAIL = {"parent": "parent.menon@sunrise-demo.in", "student": "aarav@sunrise-demo.in", "teacher": "lakshmi@sunrise-demo.in",
         "admin": "admin@sunrise-demo.in"}


def hdr(who):
    r = requests.post(f"{API}/auth/login", json={"email": EMAIL[who], "password": PW}, headers={"X-Client": "mobile"})
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}", "X-Client": "mobile"}


H = {k: hdr(k) for k in EMAIL}
UID = {k: db.users.find_one({"email": v})["id"] for k, v in EMAIL.items()}


def reg_all():
    for k, tok in FAKE.items():
        requests.post(f"{API}/push/register", headers=H[k], json={"token": tok, "platform": "android", "device_name": "QA fake", "app_version": "1.0.0"}).raise_for_status()


def pushes(since, label):
    time.sleep(5)
    rows = list(db.messages.find({"institution_id": IID, "channel": "push", "created_at": {"$gt": since}}, {"_id": 0}).sort("created_at", 1))
    print(f"\n== {label}: {len(rows)} push entr{'y' if len(rows) == 1 else 'ies'}")
    for m in rows:
        who = next((k for k, v in UID.items() if v == m["recipient_user_id"]), m["recipient_name"])
        print(f"   → {who:8} {m['module']:15} {m['meta']['type']:18} route={m['meta'].get('route')}  status={m['status']}  error={(m.get('error') or '')[:70]}")
    return rows


def step(label, fn):
    reg_all()
    since = datetime.now(timezone.utc).isoformat()
    ctx = fn()
    return pushes(since, label), ctx


tok_rows = list(db.push_tokens.find({"token": {"$in": list(FAKE.values())}}, {"_id": 0, "token": 1, "user_id": 1, "role": 1, "active": 1}))
reg_all()
print("push_tokens lookup:", [(t["role"], t["token"][-10:], db.push_tokens.find_one({"token": t["token"]})["active"]) for t in db.push_tokens.find({"token": {"$in": list(FAKE.values())}})])

# 1) chat both directions
TID = "5b52628e-2404-4629-9921-67eb249c6b0f"
step("chat parent→teacher", lambda: requests.post(f"{API}/chat/threads/{TID}/messages", headers=H["parent"], data={"body": "QA push check (parent)"}).raise_for_status())
step("chat teacher→parent", lambda: requests.post(f"{API}/chat/threads/{TID}/messages", headers=H["teacher"], data={"body": "QA push check (teacher reply)"}).raise_for_status())

# 2) fee reminder (manual) for Aarav's overdue activity fee
step("fee reminder (manual)", lambda: print("   remind:", requests.post(f"{API}/fees/invoices/b59725c4-ada0-442c-8c9c-9acb6bde5aef/remind", headers=H["admin"]).json().get("status")))

# 3) payment proof → rejected (a NEW proof on Term 4; the existing pending proofs are untouched)
PNG = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d4944415478da63f8ffff3f0005fe02fea7d6a4b40000000049454e44ae426082")
pr = requests.post(f"{API}/parent/fees/invoices/9aa18a4e-450a-463d-bf02-add1c93f9927/proofs", headers=H["parent"],
                   files={"file": ("qa.png", PNG, "image/png")}, data={"amount": "100", "paid_on": "2026-10-14", "utr": "QAPUSH001", "note": "QA push test"})
pid = (pr.json().get("proof") or pr.json()).get("id")
step("payment proof rejected", lambda: requests.post(f"{API}/fees/proofs/{pid}/reject", headers=H["admin"], json={"reason": "QA push test — please ignore"}).raise_for_status())


# 4) notice to Grade 8 A (by lakshmi), then deleted
def notice():
    r = requests.post(f"{API}/notices", headers=H["teacher"], json={"title": "QA push test notice", "body": "Please ignore — testing phone alerts.",
                                                                     "target": {"scope": "classes", "classes": [{"class_name": "Grade 8", "section": "A"}]}})
    r.raise_for_status()
    return r.json().get("notice", r.json())["id"]


_, nid = step("notice published (8A)", notice)
print("   notice cleanup:", requests.delete(f"{API}/notices/{nid}", headers=H["teacher"]).status_code)


# 5) homework for Grade 8 A, then soft-hidden
def homework():
    due = (datetime.now(timezone.utc) + timedelta(days=2)).date().isoformat()
    r = requests.post(f"{API}/homework", headers=H["teacher"], json={"class_name": "Grade 8", "section": "A", "subject": "Mathematics",
                                                                      "title": "QA push test homework", "instructions": "Ignore", "due_date": due})
    r.raise_for_status()
    return r.json().get("homework", r.json())["id"]


_, hid = step("homework created (8A)", homework)
db.homework.update_one({"id": hid}, {"$set": {"deleted": True, "status": "closed", "deleted_at": datetime.now(timezone.utc).isoformat(), "deleted_by": "qa-cleanup (push M3 live check)"}})

# 6) cover for TODAY: request → assign lakshmi (teacher_covers + section timetable push), then restore the seed's open cover
SID = "2f1b2b1e-aca1-42e7-b661-291a0bfe03a8"
orig = db.substitutions.find_one({"id": SID}, {"_id": 0})
step("cover requested → teacher", lambda: requests.post(f"{API}/substitutions/{SID}/request", headers=H["admin"], json={"teacher_ids": [UID["teacher"]]}).raise_for_status())
step("cover assigned today → teacher + 8A students/parents", lambda: print("   assign:", requests.post(f"{API}/substitutions/{SID}/assign", headers=H["admin"], json={"teacher_id": UID["teacher"]}).json()))
db.substitutions.replace_one({"id": SID}, orig)
print("   cover restored to:", db.substitutions.find_one({"id": SID})["status"])

# 7) test endpoint (self only)
reg_all()
print("\n== /push/test (parent):", requests.post(f"{API}/push/test", headers=H["parent"]).json())
print("\nfinal token states:", [(t["role"], t["active"], t.get("deactivated_reason")) for t in db.push_tokens.find({"token": {"$in": list(FAKE.values())}})])
