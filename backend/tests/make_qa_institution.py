"""Create a blank-slate QA institution + admin for UI wizard testing."""
import os
import sys
import requests
from dotenv import dotenv_values

BASE = (dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"]).rstrip("/") + "/api"
s = requests.Session()
s.post(f"{BASE}/auth/login", json={"email": "lnmopvt@gmail.com", "password": "Lnmo@2026!"}, timeout=30).raise_for_status()

if len(sys.argv) > 1 and sys.argv[1] == "clean":
    r = s.get(f"{BASE}/res/institutions", params={"search": "QA_Wizard", "limit": 50}, timeout=30).json()
    for i in r["items"]:
        print("deleting", i["name"], s.delete(f"{BASE}/res/institutions/{i['id']}", timeout=30).status_code)
    raise SystemExit

email = "qa.wizard@qa.test"
# remove previous run
r = s.get(f"{BASE}/res/institutions", params={"search": "QA_Wizard", "limit": 50}, timeout=30).json()
for i in r["items"]:
    s.delete(f"{BASE}/res/institutions/{i['id']}", timeout=30)

resp = s.post(f"{BASE}/res/institutions", json={
    "name": "QA_Wizard School", "code": "QAWIZ", "admin_name": "QA Wizard Admin",
    "admin_email": email, "admin_password": "Wizard@2026!"}, timeout=30)
print(resp.status_code, resp.text[:300])
print("admin:", email, "Wizard@2026!")
