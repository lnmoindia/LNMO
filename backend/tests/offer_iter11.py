"""Add two subject offerings (whole-class blank section + section A) for UI scoping test.
Usage: python offer_iter11.py add | python offer_iter11.py clean
"""
import json
import os
import sys

import requests
from dotenv import dotenv_values

fe = dotenv_values("/app/frontend/.env")
API = (os.environ.get("REACT_APP_BACKEND_URL") or fe.get("REACT_APP_BACKEND_URL")).rstrip("/") + "/api"
F = os.path.join(os.path.dirname(os.path.abspath(__file__)), "iter11_offers.json")
ADMIN = {"email": "admin@greenwood.edu", "password": "Green@2026!"}

s = requests.Session()
s.post(f"{API}/auth/login", json=ADMIN, timeout=30).raise_for_status()

if sys.argv[1] == "add":
    ids = []
    for payload in ({"subject": "Mathematics", "class_name": "Grade 6", "section": "", "max_marks": 100},
                    {"subject": "Mathematics", "class_name": "Grade 6", "section": "A", "max_marks": 50}):
        r = s.post(f"{API}/res/subject_offerings", json=payload)
        print(r.status_code, r.text[:200])
        if r.status_code == 200:
            ids.append(r.json()["id"])
    json.dump(ids, open(F, "w"))
else:
    for i in json.load(open(F)):
        print("del", s.delete(f"{API}/res/subject_offerings/{i}").status_code)
    os.remove(F)
