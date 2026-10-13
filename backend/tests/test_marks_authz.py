"""Authorization probe: can a teacher read/write marks for an assessment of a class they are NOT assigned to?"""
import os
import uuid

import pytest
import requests
from dotenv import dotenv_values

base = dotenv_values("/app/frontend/.env").get("REACT_APP_BACKEND_URL")
API = base.rstrip("/") + "/api"
ADMIN = {"email": "admin@greenwood.edu", "password": "Green@2026!"}
TEACHER = {"email": "meera@greenwood.edu", "password": "Teach@2026!"}


def _client(creds):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=creds, timeout=30)
    assert r.status_code == 200, r.text
    return s


class TestMarksAuthorization:
    def test_teacher_cannot_touch_unassigned_class_marks(self):
        admin, teacher = _client(ADMIN), _client(TEACHER)
        created = admin.post(f"{API}/res/assessments", json={
            "name": f"TEST_UNASSIGNED_{uuid.uuid4().hex[:6]}", "class_name": "Grade 11",
            "section": "Z", "subject": "Physics", "max_marks": 20}, timeout=30)
        assert created.status_code == 200, created.text
        aid = created.json()["id"]
        try:
            get_r = teacher.get(f"{API}/assessments/{aid}/marks", timeout=30)
            post_r = teacher.post(f"{API}/assessments/{aid}/marks",
                                  json={"entries": [{"student_id": str(uuid.uuid4()), "score": 5,
                                                     "status": "present"}]}, timeout=30)
            print("teacher GET marks (unassigned class):", get_r.status_code)
            print("teacher POST marks (unassigned class):", post_r.status_code)
            assert (get_r.status_code, post_r.status_code) == (403, 403), (
                f"teacher marks access to unassigned class not blocked: "
                f"GET={get_r.status_code}, POST={post_r.status_code}")
        finally:
            admin.delete(f"{API}/res/assessments/{aid}", timeout=30)
