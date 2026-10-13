"""Phase 51 demo additions for the TEST school p50demo (never LPGS). Idempotent.
Run after seed_phase50_demo.py: cd /app/backend && python tests/seed_phase51_demo.py"""
import io
import os
import sys
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import requests
from dotenv import load_dotenv
from pymongo import MongoClient
from PIL import Image, ImageDraw

sys.path.insert(0, "/app/backend")
load_dotenv("/app/backend/.env")
from server import hash_password, now_iso  # noqa: E402

API = "http://localhost:8001/api"
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
inst = db.institutions.find_one({"slug": "p50demo"})
assert inst, "run seed_phase50_demo.py first"
A = inst["id"]


def sess(email, pw):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": pw})
    r.raise_for_status()
    s.headers["Authorization"] = f"Bearer {r.cookies.get('access_token')}"
    return s


admin = sess("admin@feesdemo.test", "admin123")
admin.put(f"{API}/fees/upi-settings", json={"enabled": True, "vpa": "feesdemo@okaxis", "payee_name": "Fees Demo School",
                                            "instructions": "Write the admission number in the UPI note."}).raise_for_status()
if not db.users.find_one({"email": "principal.hs@feesdemo.test"}):
    hs = db.academic_units.find_one({"institution_id": A, "name": "HS"})
    uid = str(uuid.uuid4())
    db.users.insert_one({"id": uid, "name": "Hari HS Principal", "email": "principal.hs@feesdemo.test", "password_hash": hash_password("teach123"),
                         "role": "teacher", "institution_id": A, "status": "active", "must_change_password": False, "created_at": now_iso()})
    db.principal_assignments.insert_one({"id": str(uuid.uuid4()), "institution_id": A, "user_id": uid, "scope_type": "units",
                                         "unit_ids": [hs["id"]], "designation": "principal"})
arjun = db.students.find_one({"institution_id": A, "first_name": "Arjun"})
inv = next((i for i in db.fee_invoices.find({"student_id": arjun["id"], "status": {"$ne": "paid"}}).sort("due_date", 1)
            if i["total"] - i.get("paid_amount", 0) >= 6000), None)
if inv and not db.fee_payment_proofs.find_one({"institution_id": A, "status": "pending"}):
    img = Image.new("RGB", (360, 640), (245, 247, 250))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 360, 90], fill=(16, 122, 87))
    d.text((20, 30), "Payment successful", fill="white")
    for i, line in enumerate(["Paid to Fees Demo School", "feesdemo@okaxis", "Rs 6,000.00", "UPI Ref 412345678901", "13 Oct 2026, 10:42"]):
        d.text((20, 130 + i * 40), line, fill=(30, 41, 59))
    b = io.BytesIO(); img.save(b, "PNG")
    parent = sess("parent@feesdemo.test", "parent123")
    yday = (datetime.now(ZoneInfo("Asia/Kolkata")).date() - timedelta(days=1)).isoformat()
    r = parent.post(f"{API}/parent/fees/invoices/{inv['id']}/proofs", files={"file": ("gpay.png", b.getvalue(), "image/png")},
                    data={"amount": "6000", "paid_on": yday, "utr": "412345678901", "note": "Paid via GPay"})
    r.raise_for_status()
    print("pending proof", r.json()["proof"]["id"])
print("phase51 demo ready")
