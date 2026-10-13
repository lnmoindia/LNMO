"""Seed helper: creates 20 students for the UI institution admin to test pagination."""
import os
import sys
import requests
from dotenv import dotenv_values

BASE = (os.environ.get("REACT_APP_BACKEND_URL") or dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"]).rstrip("/")
API = f"{BASE}/api"
email, password, n = sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 20

s = requests.Session()
r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
r.raise_for_status()
created = 0
for i in range(n):
    resp = s.post(f"{API}/res/students",
                  json={"first_name": f"PAGE_{i:02d}", "last_name": "Test", "admission_no": f"PG{i:02d}"}, timeout=30)
    created += resp.status_code == 200
print("created", created)
