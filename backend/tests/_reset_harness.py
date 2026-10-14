"""Isolated factory-reset harness. Run ONLY with DB_NAME set to a throwaway database (see test_phase57_reset.py)."""
import gzip
import json
import os
import sys
import time
import uuid

DB = os.environ["DB_NAME"]
assert DB.startswith("lnmo_reset_test_"), "refusing to run against a non-throwaway database"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from pymongo import MongoClient  # noqa: E402
from starlette.requests import Request  # noqa: E402

raw = MongoClient(os.environ["MONGO_URL"])[DB]
PA_EMAIL, PA_PW = os.environ["PLATFORM_ADMIN_EMAIL"].lower(), os.environ["PLATFORM_ADMIN_PASSWORD"]
IID = str(uuid.uuid4())


def check(cond, msg):
    if not cond:
        print("FAIL:", msg)
        sys.exit(1)
    print("ok:", msg)


def fake_req(host):
    return Request({"type": "http", "headers": [(b"host", host.encode())], "method": "GET", "path": "/"})


def seed():
    raw.institutions.insert_one({"id": IID, "name": "Fake School", "code": "FAKE", "slug": "fake", "status": "active", "created_at": server.now_iso()})
    raw.users.insert_one({"id": str(uuid.uuid4()), "email": "admin@fake.test", "role": "institution_admin", "institution_id": IID,
                          "password_hash": server.hash_password("x"), "status": "active"})
    raw.users.insert_one({"id": str(uuid.uuid4()), "email": "kid@fake.test", "role": "student", "institution_id": IID,
                          "password_hash": server.hash_password("x"), "status": "active"})
    raw.students.insert_one({"id": str(uuid.uuid4()), "institution_id": IID, "name": "Kid", "photo_path": "lnmo/photos/s1/a.jpg"})
    raw.attendance.insert_one({"id": str(uuid.uuid4()), "institution_id": IID, "date": "2026-10-01"})
    raw.comm_templates.insert_one({"id": str(uuid.uuid4()), "institution_id": IID, "name": "School tpl"})
    raw.platform_library.insert_many([{"id": "lib-platform", "title": "Platform item"},
                                      {"id": "lib-school", "title": "School item", "submitted_by_school": IID}])
    raw.plans.insert_one({"id": "plan-1", "name": "Starter", "max_students": 100})
    raw.zz_custom.insert_many([{"id": "u1", "institution_id": IID}, {"id": "u2", "global": True}])
    raw.audit_logs.insert_one({"id": "a1", "action": "login", "institution_id": IID})


def wait_job(c):
    for _ in range(60):
        j = c.get("/api/platform/reset/status").json()["job"]
        if j and j["status"] != "running":
            return j
        time.sleep(0.5)
    return j


def main():
    # 1) guard refuses preview hosts / the preview DB name (guard is the real function here)
    for h in ("lnmo-fees.preview.emergentagent.com", "localhost:8001", "127.0.0.1"):
        try:
            server.reset_guard(fake_req(h))
            check(False, f"guard blocks {h}")
        except HTTPException as e:
            check(e.status_code == 409 and "preview" in e.detail, f"guard blocks {h}")
    saved = os.environ["DB_NAME"]
    os.environ["DB_NAME"] = server.PREVIEW_DB_NAME
    try:
        server.reset_guard(fake_req("school.example.com"))
        check(False, "guard blocks preview DB name")
    except HTTPException as e:
        check(e.status_code == 409, "guard blocks preview DB name")
    os.environ["DB_NAME"] = saved
    check(server.reset_guard(fake_req("lnmo.example.com"))["db"] == DB, "guard allows a production-like host + DB")

    with TestClient(server.app, base_url="https://testserver") as c:
        seed()
        server.app.dependency_overrides[server.reset_guard] = lambda: {"host": "testserver", "db": DB}
        r = c.post("/api/auth/login", json={"identifier": PA_EMAIL, "email": PA_EMAIL, "password": PA_PW})
        check(r.status_code == 200, "platform admin signs in on temp DB")
        rr = c.get("/api/platform/reset/preview")
        print("preview:", rr.status_code, rr.text[:300])
        pv = rr.json()
        acts = {p["collection"]: p for p in pv["plan"]}
        check(acts["institutions"]["delete"] == 1 and acts["plans"]["action"] == "keep", "dry run classifies institutions/plans")
        check(acts["users"]["delete"] == 2 and acts["users"]["total"] == 3, "dry run keeps platform user")
        check(acts["zz_custom"]["action"] == "unclassified" and acts["zz_custom"]["delete"] == 1, "unclassified: only institution docs")
        check(acts["platform_library"]["delete"] == 1 and acts["comm_templates"]["delete"] == 1, "partial: school library/template only")
        r = c.post("/api/platform/reset/run", json={"password": PA_PW, "phrase": "RESET PRODUCTION", "backup_id": "nope"})
        check(r.status_code == 400, "run without a backup is refused")
        b = c.post("/api/platform/reset/backup").json()
        dl = c.get(b["download_url"])
        data = json.loads(gzip.decompress(dl.content))
        check(dl.status_code == 200 and data["collections"]["institutions"][0]["id"] == IID and b["storage_refs"] == 1, "backup downloadable + complete")
        check(c.post("/api/platform/reset/run", json={"password": PA_PW, "phrase": "reset production", "backup_id": b["id"]}).status_code == 400, "wrong phrase → 400")
        check(c.post("/api/platform/reset/run", json={"password": "wrong", "phrase": "RESET PRODUCTION", "backup_id": b["id"]}).status_code == 403, "wrong password → 403")
        r = c.post("/api/platform/reset/run", json={"password": PA_PW, "phrase": "RESET PRODUCTION", "backup_id": b["id"]})
        check(r.status_code == 202, "run accepted")
        j = wait_job(c)
        check(j["status"] == "completed" and j["final_backup_id"], f"job completed ({j.get('deleted_total')} docs)")
        check(raw.institutions.count_documents({}) == 0 and raw.students.count_documents({}) == 0 and raw.audit_logs.count_documents({}) == 0, "school data gone")
        check(raw.users.count_documents({}) == 1 and raw.users.find_one({})["role"] == "platform_admin", "only platform admin kept")
        check(raw.plans.count_documents({}) == 1 and raw.platform_library.count_documents({}) == 1, "plans + platform library kept")
        check(raw.comm_templates.count_documents({"institution_id": None}) > 0 and raw.comm_templates.count_documents({"institution_id": IID}) == 0, "global templates kept")
        check([d["id"] for d in raw.zz_custom.find({})] == ["u2"], "unclassified non-institution doc kept")
        check(raw.platform_events.count_documents({"type": "reset_completed"}) == 1, "platform_events final record")
        check(c.get("/api/auth/me").status_code == 200, "platform manager still signed in")
        check(c.post("/api/platform/reset/run", json={"password": PA_PW, "phrase": "RESET PRODUCTION", "backup_id": b["id"]}).status_code == 429, "1 reset per hour")
        # resume: simulate an interrupted job (stale heartbeat, partial steps) + leftover data
        raw.platform_events.delete_many({"type": "reset_completed"})
        raw.platform_events.update_many({"type": "reset_job"}, {"$set": {"status": "completed", "finished_at": "2000-01-01T00:00:00+00:00"}})
        jid = str(uuid.uuid4())
        raw.platform_events.insert_one({"type": "reset_job", "id": jid, "status": "running", "stage": "deleting", "started_by": "x",
                                        "started_by_email": PA_EMAIL, "started_at": server.now_iso(), "heartbeat": "2000-01-01T00:00:00+00:00",
                                        "final_backup_id": "pre", "steps": {"attendance": {"done": True, "deleted": 5}}})
        raw.students.insert_one({"id": "left", "institution_id": IID})
        r = c.post("/api/platform/reset/run", json={"password": PA_PW, "phrase": "RESET PRODUCTION", "backup_id": ""})
        check(r.status_code == 202 and r.json() == {"job_id": jid, "resumed": True}, "interrupted job resumes")
        j = wait_job(c)
        check(j["id"] == jid and j["status"] == "completed" and raw.students.count_documents({}) == 0, "resume finished deletion")
        check(j["deleted_counts"].get("attendance") == 5 and j["deleted_counts"].get("students") == 1, "resume kept earlier progress")
        server.app.dependency_overrides.clear()
        r = c.post("/api/res/institutions", json={"name": "Fresh School", "code": "FRESH", "admin_name": "A", "admin_email": "a@fresh.test", "admin_password": "Fresh@1234"})
        check(r.status_code in (200, 201), "new institution can be created after reset")
    print("ALL OK")


def boot():
    with TestClient(server.app, base_url="https://testserver") as c2:
        check(c2.get("/api/").status_code == 200, "app boots cleanly on the reset DB (fresh process)")
        check(raw.institutions.count_documents({}) == 1, "boot didn't re-seed demo schools")
        check(raw.users.count_documents({"role": "platform_admin"}) == 1, "platform admin still present after boot")
    print("BOOT OK")


if __name__ == "__main__":
    if sys.argv[1:] == ["boot"]:
        boot()
    else:
        main()
