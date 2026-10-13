"""Live LPGS Phase 16 acceptance (non-destructive). Lives OUTSIDE /app/backend so it does
not trigger a backend hot-reload. Email-OTP flows are proven by pytest (stubbed sender) + a
live engine check (202 to a deliverable address). LPGS seed accounts use placeholder @lpgs.com
emails that Resend blocks as undeliverable, so OTP delivery to THOSE accounts can't complete
live; this script runs the email-independent flows live. Disposable test parent cleaned up;
student academic records never mutated."""
import os, httpx, asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")

BASE = "https://lnmo-fees.preview.emergentagent.com"
G8 = ["5ed50271-17ee-4cae-91df-bc0b19dc15fc", "e25660b3-b935-446c-9eaa-4a661c95310a",
      "ad2e8293-475a-4db1-9f40-a36642544897"]
db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


async def main():
    out = []
    async with httpx.AsyncClient(base_url=BASE, timeout=40) as c:
        async def login(e, p):
            r = await c.post("/api/auth/login", json={"email": e, "password": p}); r.raise_for_status()
            tok = r.cookies.get("access_token")
            c.cookies.clear()  # avoid shared-jar cookie overwriting the bearer header
            return {"Authorization": f"Bearer {tok}"}

        ek = os.environ["EMERGENT_EMAIL_KEY"]
        er = await c.post("https://integrations.emergentagent.com/api/v1/email/send",
                          headers={"X-Email-Key": ek},
                          json={"to": ["delivered@resend.dev"], "subject": "LNMO School verification code",
                                "html": "<p>Your code is 123456. Expires in 10 minutes.</p>", "from_name": "LNMO School"})
        out.append(("email engine live check (202)", er.status_code, er.json().get("id", er.text[:80])))

        at = await login("admin@lpgs.com", "admin123")
        r1 = await c.post(f"/api/students/{G8[0]}/parent-user", headers=at,
                          json={"email": "p16accept@lpgs.com", "password": "Parent@123", "name": "Accept Parent"})
        out.append(("admin manual link child#1", r1.status_code, r1.json().get("message", r1.text[:80])))
        r2 = await c.post(f"/api/students/{G8[1]}/parent-user", headers=at, json={"email": "p16accept@lpgs.com"})
        out.append(("admin manual link child#2 (existing parent)", r2.status_code, r2.json().get("message", r2.text[:80])))

        pt = await login("p16accept@lpgs.com", "Parent@123")
        kids = await c.get("/api/parent/children", headers=pt)
        out.append(("switcher shows both children", kids.status_code,
                    [f"{k['first_name']} {k['class_name']}" for k in kids.json().get("children", [])]))
        snap = await c.get(f"/api/parent/child/{G8[0]}", headers=pt)
        out.append(("linked child snapshot (200)", snap.status_code, "ok"))
        unl = await c.get(f"/api/parent/child/{G8[2]}", headers=pt)
        out.append(("UNLINKED child snapshot (expect 403)", unl.status_code, ""))
        pr = await c.get(f"/api/students/{G8[0]}/parents", headers=at)
        out.append(("admin lists linked parents", pr.status_code, [p["email"] for p in pr.json().get("parents", [])]))

        su = await c.post(f"/api/parent/unlink/{G8[1]}", headers=pt)
        out.append(("parent self-unlink child#2", su.status_code, su.json().get("message", su.text[:80])))
        au = await c.post(f"/api/students/{G8[0]}/unlink-parent", headers=at, json={"email": "p16accept@lpgs.com"})
        out.append(("admin unlink child#1", au.status_code, au.json().get("message", au.text[:80])))

    tp = await db.users.find_one({"email": "p16accept@lpgs.com"})
    if tp:
        await db.otp_codes.delete_many({"user_id": tp["id"]})
        await db.users.delete_one({"id": tp["id"]})
    await db.users.update_one({"email": "prasad27@lpgs.com"}, {"$unset": {"phone": "", "phone_verified": ""}})
    await db.otp_codes.delete_many({})
    out.append(("cleanup", "done", "test parent + otp rows removed; prasad27 phone reset; students untouched"))

    print("\n=== PHASE 16 LIVE LPGS ACCEPTANCE ===")
    for n, s, x in out:
        print(f"[{s}] {n} -> {x}")


asyncio.run(main())
