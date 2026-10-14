"""Phase 57: factory reset runs ONLY against a throwaway DB in a subprocess; preview DB counts must not change."""
import os
import subprocess
import sys
import uuid

import requests
from pymongo import MongoClient

API = open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split()[0].rstrip("/") + "/api"


def _env():
    out = {}
    for line in open("/app/backend/.env"):
        if "=" in line:
            k, v = line.strip().split("=", 1)
            out[k] = v.strip('"')
    return out


E = _env()
prev = MongoClient(E["MONGO_URL"])[E["DB_NAME"]]
WATCH = ("institutions", "users", "students", "fee_invoices", "audit_logs", "attendance", "timetable_entries")


def _counts():
    return {c: prev[c].count_documents({}) for c in WATCH}


def test_preview_endpoints_refuse():
    s = requests.Session()
    assert s.post(f"{API}/auth/login", json={"identifier": E["PLATFORM_ADMIN_EMAIL"], "password": E["PLATFORM_ADMIN_PASSWORD"]}).status_code == 200
    for m, p in (("get", "/platform/reset/preview"), ("post", "/platform/reset/backup")):
        r = getattr(s, m)(f"{API}{p}")
        assert r.status_code == 409 and r.json()["detail"] == "Reset is disabled on preview", (p, r.text)
    r = s.post(f"{API}/platform/reset/run", json={"password": "x", "phrase": "RESET PRODUCTION", "backup_id": "x"})
    assert r.status_code == 409
    sun = requests.Session()
    sun.post(f"{API}/auth/login", json={"identifier": "admin@sunrise-demo.in", "password": "Sunrise@2026", "slug": "sunrise"})
    assert sun.get(f"{API}/platform/reset/status").status_code == 403


def test_reset_on_temp_db():
    before = _counts()
    env = {**os.environ, **E, "DB_NAME": f"lnmo_reset_test_{uuid.uuid4().hex[:8]}"}
    try:
        for mode, ok in (([], "ALL OK"), (["boot"], "BOOT OK")):
            r = subprocess.run([sys.executable, "tests/_reset_harness.py", *mode], cwd="/app/backend", env=env, capture_output=True, text=True, timeout=240)
            print(r.stdout[-4000:], r.stderr[-1500:])
            assert r.returncode == 0 and ok in r.stdout
    finally:
        MongoClient(E["MONGO_URL"]).drop_database(env["DB_NAME"])
    assert env["DB_NAME"] not in MongoClient(E["MONGO_URL"]).list_database_names()
    assert _counts() == before, "preview data changed!"
