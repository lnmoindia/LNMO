"""Iteration 13 cleanup: remove test-created draft assessment + marks, portal user,
and the attendance sheet created by the class-teacher access test (2026-07-03).
Usage: python cleanup_iter13.py
"""
import os

import requests
from dotenv import dotenv_values
from pymongo import MongoClient

fe = dotenv_values("/app/frontend/.env")
be = dotenv_values("/app/backend/.env")
API = (os.environ.get("REACT_APP_BACKEND_URL") or fe["REACT_APP_BACKEND_URL"]).rstrip("/") + "/api"
db = MongoClient(be["MONGO_URL"])[be["DB_NAME"]]

s = requests.Session()
s.post(f"{API}/auth/login", json={"email": "admin@greenwood.edu", "password": "Green@2026!"}, timeout=30)

# test assessments
for a in s.get(f"{API}/res/assessments?limit=100", timeout=30).json()["items"]:
    if str(a.get("name", "")).startswith("TEST_"):
        db.marks.delete_many({"assessment_id": a["id"]})
        print("del assessment", a["name"], s.delete(f"{API}/res/assessments/{a['id']}", timeout=30).status_code)

# test achievements
for ach in s.get(f"{API}/res/achievements?limit=100", timeout=30).json()["items"]:
    if str(ach.get("title", "")).startswith("TEST_"):
        print("del achievement", ach["title"], s.delete(f"{API}/res/achievements/{ach['id']}", timeout=30).status_code)

# test students / classes
for st in s.get(f"{API}/res/students?limit=200", timeout=30).json()["items"]:
    if str(st.get("first_name", "")).startswith("TEST_"):
        print("del student", st["first_name"], s.delete(f"{API}/res/students/{st['id']}", timeout=30).status_code)
for sec in s.get(f"{API}/res/sections?limit=200", timeout=30).json()["items"]:
    if str(sec.get("class_name", "")).startswith("TEST_"):
        print("del section", sec["class_name"], s.delete(f"{API}/res/sections/{sec['id']}", timeout=30).status_code)
for c in s.get(f"{API}/res/classes?limit=200", timeout=30).json()["items"]:
    if str(c.get("name", "")).startswith("TEST_"):
        print("del class", c["name"], s.delete(f"{API}/res/classes/{c['id']}", timeout=30).status_code)

# portal user
print("portal", s.delete(f"{API}/students/9fa05e4b-3ec9-4e53-8fb2-8a69b517a4dc/portal-user", timeout=30).status_code)

# attendance sheet created by tests
r = db.attendance.delete_many({"class_name": "Grade 6", "section": "A", "date": "2026-07-03"})
print("attendance 2026-07-03 removed:", r.deleted_count)
print("remaining Grade6A attendance dates:",
      [d["date"] for d in db.attendance.find({"class_name": "Grade 6", "section": "A"}, {"date": 1})])
