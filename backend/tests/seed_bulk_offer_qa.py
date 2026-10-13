"""Seed/clean extra classes + a practical subject for UI bulk-offer testing.
Usage: python seed_bulk_offer_qa.py [clean]
"""
import os
import sys

import requests
from dotenv import dotenv_values

env = dotenv_values("/app/frontend/.env")
API = f"{(os.environ.get('REACT_APP_BACKEND_URL') or env['REACT_APP_BACKEND_URL']).rstrip('/')}/api"
CLASSES = ["QA Grade 7", "QA Grade 8", "QA Grade 9"]
SUBJECT = "QA Chemistry"

s = requests.Session()
r = s.post(f"{API}/auth/login", json={"email": "admin@greenwood.edu", "password": "Green@2026!"}, timeout=30)
r.raise_for_status()
unit = s.get(f"{API}/res/academic_units", params={"limit": 10}, timeout=30).json()["items"][0]

if len(sys.argv) > 1 and sys.argv[1] == "clean":
    offs = s.get(f"{API}/res/subject_offerings", params={"limit": 500}, timeout=30).json()["items"]
    for o in offs:
        if o["class_name"] in CLASSES or o["subject"] == SUBJECT:
            print("del offering", o["subject"], o["class_name"], s.delete(f"{API}/res/subject_offerings/{o['id']}", timeout=30).status_code)
    for c in s.get(f"{API}/res/classes", params={"limit": 200}, timeout=30).json()["items"]:
        if c["name"] in CLASSES:
            print("del class", c["name"], s.delete(f"{API}/res/classes/{c['id']}", timeout=30).status_code)
    for sub in s.get(f"{API}/res/subjects", params={"limit": 200}, timeout=30).json()["items"]:
        if sub["name"] == SUBJECT:
            print("del subject", s.delete(f"{API}/res/subjects/{sub['id']}", timeout=30).status_code)
    sys.exit(0)

for name in CLASSES:
    resp = s.post(f"{API}/res/classes", json={"name": name, "academic_unit_id": unit["id"]}, timeout=30)
    print("class", name, resp.status_code, resp.text[:120])
resp = s.post(f"{API}/res/subjects", json={"name": SUBJECT, "code": "QCHEM", "type": "Practical / Lab",
                                           "default_max_marks": 100, "status": "active"}, timeout=30)
print("subject", resp.status_code, resp.text[:150])
print("unit used:", unit["name"])
