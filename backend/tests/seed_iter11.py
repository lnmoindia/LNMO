"""Seed data for iteration 11 testing (per-section leaders + portal achievements).

Creates in Greenwood: section B for Grade 6, student TEST_Bhavya Rao (Grade 6/B),
an achievement for her, a portal login, and sets her as section B class leader.
Also creates a temp class + student for the cross-class validation test.
Writes created ids to iter11_ids.json. Run `python cleanup_iter11.py` to remove.
"""
import json
import os
import sys

import requests
from dotenv import dotenv_values

fe = dotenv_values("/app/frontend/.env")
BASE = (os.environ.get("REACT_APP_BACKEND_URL") or fe.get("REACT_APP_BACKEND_URL")).rstrip("/")
API = f"{BASE}/api"
IDS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "iter11_ids.json")

ADMIN = {"email": "admin@greenwood.edu", "password": "Green@2026!"}
STUDENT_LOGIN = {"email": "test.bhavya@qa.test", "password": "Kid@2026!"}


def admin_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=ADMIN, timeout=30)
    r.raise_for_status()
    return s


def main():
    s = admin_session()
    ids = {"student_login": STUDENT_LOGIN}

    classes = s.get(f"{API}/res/classes", params={"limit": 100}).json()["items"]
    g6 = next(c for c in classes if c["name"] == "Grade 6")
    ids["class_id"] = g6["id"]
    ids["class_name"] = g6["name"]
    ids["academic_unit_id"] = g6.get("academic_unit_id")

    secs = s.get(f"{API}/res/sections", params={"limit": 200}).json()["items"]
    sec_a = next(x for x in secs if x["class_name"] == "Grade 6" and x["name"] == "A")
    ids["section_a_id"] = sec_a["id"]
    ids["section_a_original_leader"] = sec_a.get("class_leader_id") or ""
    ids["section_a_original_second"] = sec_a.get("second_leader_id") or ""

    sec_b = next((x for x in secs if x["class_name"] == "Grade 6" and x["name"] == "B"), None)
    if not sec_b:
        sec_b = s.post(f"{API}/res/sections", json={"name": "B", "class_name": "Grade 6",
                                                   "room": "R-B1", "capacity": 30}).json()
        ids["section_b_created"] = True
    ids["section_b_id"] = sec_b["id"]

    st = s.post(f"{API}/students/enroll", json={
        "first_name": "TEST_Bhavya", "last_name": "Rao", "admission_no": "TESTB01",
        "class_name": "Grade 6", "section": "B", "enroll": True,
        "academic_year": sec_a.get("academic_year") or "2025-26"}).json()
    ids["student_b_id"] = st["id"]

    ach = s.post(f"{API}/res/achievements", json={
        "student_id": st["id"], "title": "TEST_1st place Science Fair",
        "description": "District level model contest", "date": "2026-02-14"}).json()
    ids["achievement_id"] = ach["id"]

    pu = s.post(f"{API}/students/{st['id']}/portal-user", json=STUDENT_LOGIN)
    if pu.status_code != 200:
        print("portal-user create failed:", pu.status_code, pu.text)
        sys.exit(1)

    r = s.put(f"{API}/res/sections/{sec_b['id']}", json={"class_leader_id": st["id"], "second_leader_id": ""})
    print("section B leader set:", r.status_code, r.json().get("class_leader"))

    # temp class + student for cross-class validation
    tc = s.post(f"{API}/res/classes", json={"name": "TEST_Class_Zeta",
                                            "academic_unit_id": g6.get("academic_unit_id")}).json()
    ids["temp_class_id"] = tc["id"]
    ots = s.post(f"{API}/students/enroll", json={
        "first_name": "TEST_Other", "last_name": "Kid", "class_name": "TEST_Class_Zeta",
        "section": "A", "enroll": True}).json()
    ids["other_student_id"] = ots["id"]

    with open(IDS_FILE, "w") as f:
        json.dump(ids, f, indent=2)
    print(json.dumps(ids, indent=2))


if __name__ == "__main__":
    main()
