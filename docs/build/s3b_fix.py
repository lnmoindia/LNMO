"""Step 3b: re-shoot the few screens that need direct navigation."""
import asyncio
from pymongo import MongoClient
from playwright.async_api import async_playwright
from common import BASE, ADMIN, shot, login
from s3_capture import go, click

db = MongoClient("mongodb://localhost:27017")["test_database"]
IID = db.institutions.find_one({"name": "Sunrise Public School (Demo)"})["id"]
AARAV = db.students.find_one({"institution_id": IID, "first_name": "Aarav"})["id"]
ACC = db.fee_accounts.find_one({"institution_id": IID, "student_id": db.students.find_one({"institution_id": IID, "first_name": "Diya"})["id"]})["id"]


async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        page = await (await b.new_context(viewport={"width": 1440, "height": 900})).new_page()
        await login(page, *ADMIN, slug="sunrise")
        await go(page, f"/app/students/{AARAV}", "pf_01_student_profile", wait=3500)

        async def ledger(pg):
            await click(pg, f"[data-testid=fee-account-open-{ACC}]", 2500)
        await go(page, "/app/fees?tab=accounts", "fe_03_ledger", [("[data-testid=fee-ledger-statement]", "Statement PDF")], before=ledger)

        async def collect(pg):
            await ledger(pg)
            await click(pg, "[data-testid^=fee-collect-]", 1500)
            await pg.locator("[data-testid=fee-collect-date]").fill("2026-10-10")
            await pg.wait_for_timeout(600)
        await go(page, "/app/fees?tab=accounts", "fe_04_collect", [("[data-testid=fee-collect-date]", "Payment date (backdating allowed)")], before=collect)
        await b.close()

if __name__ == "__main__":
    asyncio.run(main())
