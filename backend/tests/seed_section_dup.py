"""Seed/clean two classes each with a section named 'A' for UI section-dropdown testing.
Usage: python seed_section_dup.py [clean]
"""
import sys
import os
import requests
from dotenv import dotenv_values

base = (os.environ.get("REACT_APP_BACKEND_URL") or dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"]).rstrip("/") + "/api"
s = requests.Session()
r = s.post(f"{base}/auth/login", json={"email": "admin@greenwood.edu", "password": "Green@2026!"})
r.raise_for_status()

CLASSES = ["TEST_Grade1", "TEST_Grade2"]

if len(sys.argv) > 1 and sys.argv[1] == "clean":
    for res in ("subject_offerings", "sections", "classes"):
        items = s.get(f"{base}/res/{res}", params={"limit": 500}).json().get("items", [])
        for it in items:
            if it.get("class_name") in CLASSES or it.get("name") in CLASSES:
                print("delete", res, it.get("name") or it.get("id"), s.delete(f"{base}/res/{res}/{it['id']}").status_code)
    # remove TEST_ subjects
    subs = s.get(f"{base}/res/subjects", params={"limit": 500, "search": "TEST"}).json().get("items", [])
    for it in subs:
        if str(it.get("name", "")).startswith("TEST"):
            print("delete subject", it["name"], s.delete(f"{base}/res/subjects/{it['id']}").status_code)
    sys.exit(0)

uid = s.get(f"{base}/lookup/academic_units").json()[0]["value"]
for c in CLASSES:
    rc = s.post(f"{base}/res/classes", json={"name": c, "academic_unit_id": uid})
    print("class", c, rc.status_code, rc.text[:120])
    for sec in ("A", "B"):
        rs = s.post(f"{base}/res/sections", json={"name": sec, "class_name": c, "capacity": 30})
        print("  section", sec, rs.status_code, rs.text[:120])
print("sections lookup:", s.get(f"{base}/lookup/sections").json())
