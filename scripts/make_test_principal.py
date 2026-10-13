"""Create an additive TEST principal on LPGS (HS-only) for reproducing/verifying the principal
portal 403 bug. Does NOT touch deepa.s. Idempotent."""
import os, asyncio, httpx
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")

BASE = "https://lnmo-fees.preview.emergentagent.com"
HS_UNIT = "2b32fe13-f104-490d-a4d8-8e3768960325"  # LPGS HS academic unit


async def main():
    async with httpx.AsyncClient(base_url=BASE, timeout=40) as c:
        r = await c.post("/api/auth/login", json={"email": "admin@lpgs.com", "password": "admin123"})
        tok = r.cookies.get("access_token"); c.cookies.clear()
        H = {"Authorization": f"Bearer {tok}"}
        # create teacher (idempotent-ish: ignore error if exists)
        tr = await c.post("/api/teachers", headers=H, json={
            "name": "Test Principal", "email": "testprincipal@lpgs.com",
            "password": "teach123", "status": "active"})
        print("create teacher:", tr.status_code, tr.text[:120])
        # find the teacher id
        lst = await c.get("/api/teachers", headers=H, params={"search": "testprincipal", "limit": 10})
        items = lst.json().get("items", [])
        tid = next((t["id"] for t in items if t["email"] == "testprincipal@lpgs.com"), None)
        print("teacher id:", tid)
        if tid:
            pr = await c.post("/api/principals", headers=H, json={
                "teacher_id": tid, "scope_type": "units", "unit_ids": [HS_UNIT], "designation": "principal"})
            print("assign principal:", pr.status_code, pr.text[:160])


asyncio.run(main())
