"""Create/revoke a temporary portal login for Aarav Shah (iteration 12 UI test).

Usage: python portal_user_iter12.py create|delete
"""
import os
import sys

import requests
from dotenv import dotenv_values

fe = dotenv_values("/app/frontend/.env")
API = (os.environ.get("REACT_APP_BACKEND_URL") or fe["REACT_APP_BACKEND_URL"]).rstrip("/") + "/api"
AARAV = "9fa05e4b-3ec9-4e53-8fb2-8a69b517a4dc"
LOGIN = {"email": "test_aarav_portal@qa.test", "password": "Portal@2026!"}

s = requests.Session()
r = s.post(f"{API}/auth/login", json={"email": "admin@greenwood.edu", "password": "Green@2026!"}, timeout=30)
r.raise_for_status()
action = sys.argv[1] if len(sys.argv) > 1 else "create"
if action == "create":
    print(s.post(f"{API}/students/{AARAV}/portal-user", json=LOGIN, timeout=30).status_code)
else:
    print(s.delete(f"{API}/students/{AARAV}/portal-user", timeout=30).status_code)
