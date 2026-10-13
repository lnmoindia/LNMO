"""v1.1 step 6d: platform library limited to LNMO platform content (no other school names)."""
import asyncio
from playwright.async_api import async_playwright
from common import PA, shot, login


async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        page = await (await b.new_context(viewport={"width": 1440, "height": 900})).new_page()
        await login(page, *PA)
        await page.goto(page.url.split("/platform")[0] + "/platform/library")
        await page.wait_for_timeout(3000)
        await page.get_by_placeholder("Search title").first.fill("SCERT")
        await page.wait_for_timeout(2500)
        txt = await page.inner_text("body")
        print("LPGS visible:", "LPGS" in txt)
        await shot(page, "pm_09_library")
        await b.close()

asyncio.run(main())
