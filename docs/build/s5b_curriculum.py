"""v1.1 step 5b: Grade 8 Science curriculum for the AI Tutor via the real teacher→principal flow (Sunrise only)."""
import requests
from pymongo import MongoClient
from common import PW

API = "http://localhost:8001/api"
db = MongoClient("mongodb://localhost:27017")["test_database"]
IID = db.institutions.find_one({"name": "Sunrise Public School (Demo)"})["id"]


def sess(email):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": PW})
    r.raise_for_status()
    s.headers["Authorization"] = f"Bearer {r.cookies.get('access_token')}"
    return s


deepa, thomas = sess("deepa@sunrise-demo.in"), sess("thomas@sunrise-demo.in")
cur = db.curricula.find_one({"institution_id": IID, "class_name": "Grade 8", "subject": "Science"})
if not cur:
    r = deepa.post(f"{API}/ai/curriculum", json={"academic_year": "2026-27", "class_name": "Grade 8", "subject": "Science",
                                               "name": "Grade 8 Science — Term 1", "syllabus_text": "Matter and its states; Force and pressure", "submit": False})
    print("create", r.status_code, r.text[:200])
    cur = db.curricula.find_one({"institution_id": IID, "class_name": "Grade 8", "subject": "Science"})
cid = cur["id"]
for ch, topic, txt in [("Chapter 3: Matter and its states", "Density and floating",
                        "Density = mass / volume. An object floats if it is less dense than the liquid. Water is unusual: ice is about 9% less dense than liquid water because hydrogen bonds hold molecules in an open hexagonal lattice when it freezes."),
                       ("Chapter 5: Force and pressure", "Friction",
                        "Friction is a force that opposes relative motion between surfaces in contact. It helps us walk, write with a pencil, and lets car brakes and tyres grip the road. It also causes wear and heat; lubricants and ball bearings reduce it.")]:
    if not db.curriculum_items.find_one({"curriculum_id": cid, "topic": topic}) if "curriculum_items" in db.list_collection_names() else True:
        for it, extra in (("chapter", {"title": ch}), ("notes", {"title": topic, "topic": topic, "text_content": txt})):
            r = deepa.post(f"{API}/ai/curriculum/{cid}/items", data={"item_type": it, "chapter": ch, **extra})
            print("item", it, r.status_code, r.text[:120])
r = deepa.post(f"{API}/ai/curriculum/{cid}/items", data={"item_type": "textbook", "title": "Science Textbook for Class VIII (demo notes)",
               "text_content": "Demo reference text: matter, density, floating and sinking; force, pressure and friction."})
print("textbook", r.status_code, r.text[:160])
print("submit", deepa.post(f"{API}/ai/curriculum/{cid}/submit").status_code)
for coll in ("curriculum_items", "ai_items"):
    if coll in db.list_collection_names():
        for it in db[coll].find({"curriculum_id": cid, "status": {"$ne": "approved"}}):
            print("item review", thomas.post(f"{API}/ai/items/{it['id']}/review", json={"action": "approve"}).status_code)
print("review", thomas.post(f"{API}/ai/curriculum/{cid}/review", json={"action": "approve", "note": "Looks good"}).text[:160])
print("enable", thomas.put(f"{API}/ai/curriculum/{cid}/ai-enabled", json={"enabled": True}).text[:120])
