"""v1.1 step 6f: platform sign-in screen with a placeholder email (no real address)."""
import asyncio
import os
from playwright.async_api import async_playwright
from common import shot

BASE = os.environ["DOC_BASE_URL"] if "DOC_BASE_URL" in os.environ else open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split()[0]


async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        page = await (await b.new_context(viewport={"width": 1440, "height": 900})).new_page()
        await page.goto(BASE + "/login")
        await page.wait_for_timeout(2500)
        await page.locator("input").nth(0).fill("platform@lnmo-demo.in")
        await page.locator("input[type=password]").fill("demo-password")
        await shot(page, "pm_01_login", marks=[("button[type=submit]", "Sign in")])
        await b.close()

asyncio.run(main())
