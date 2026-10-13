"""Remove everything created by seed_iter11.py and restore section A leaders."""
import json
import os

import requests
from dotenv import dotenv_values

fe = dotenv_values("/app/frontend/.env")
BASE = (os.environ.get("REACT_APP_BACKEND_URL") or fe.get("REACT_APP_BACKEND_URL")).rstrip("/")
API = f"{BASE}/api"
IDS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "iter11_ids.json")
ADMIN = {"email": "admin@greenwood.edu", "password": "Green@2026!"}


def main():
    with open(IDS_FILE) as f:
        ids = json.load(f)
    s = requests.Session()
    s.post(f"{API}/auth/login", json=ADMIN, timeout=30).raise_for_status()

    if ids.get("achievement_id"):
        print("del ach", s.delete(f"{API}/res/achievements/{ids['achievement_id']}").status_code)
    if ids.get("student_b_id"):
        print("revoke portal", s.delete(f"{API}/students/{ids['student_b_id']}/portal-user").status_code)
        print("del student B", s.delete(f"{API}/res/students/{ids['student_b_id']}").status_code)
    if ids.get("section_b_created") and ids.get("section_b_id"):
        print("del section B", s.delete(f"{API}/res/sections/{ids['section_b_id']}").status_code)
    if ids.get("other_student_id"):
        print("del other student", s.delete(f"{API}/res/students/{ids['other_student_id']}").status_code)
    if ids.get("temp_class_id"):
        print("del temp class", s.delete(f"{API}/res/classes/{ids['temp_class_id']}").status_code)
    if ids.get("section_a_id"):
        r = s.put(f"{API}/res/sections/{ids['section_a_id']}", json={
            "class_leader_id": ids.get("section_a_original_leader") or "",
            "second_leader_id": ids.get("section_a_original_second") or ""})
        print("restore section A", r.status_code, r.json().get("class_leader"))
    os.remove(IDS_FILE)


if __name__ == "__main__":
    main()
