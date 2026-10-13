"""v1.1 step 6b: student AI Tutor chat (real Gemini answers via the app)."""
import asyncio
from playwright.async_api import async_playwright
from common import PW, shot, login


async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        page = await (await b.new_context(viewport={"width": 1440, "height": 900})).new_page()
        await login(page, "aarav@sunrise-demo.in", PW, slug="sunrise")
        await page.wait_for_timeout(2500)
        el = page.locator("[data-testid=quick-ai-tutor]")
        print("quick", await el.count())
        if await el.count():
            await el.first.click()
        else:
            await page.get_by_text("AI Tutor").first.click()
        await page.wait_for_timeout(3000)
        print("input", await page.locator("[data-testid=ai-input]").count(), "banner", await page.locator("[data-testid=ai-layer-disabled-banner]").count())
        if not await page.locator("[data-testid=ai-input]").count():
            await shot(page, "_dbg_ai")
            btns = page.locator("[data-testid=ai-library] button, [data-testid=ai-tutor-student] button")
            print("buttons", await btns.count(), [await btns.nth(i).inner_text() for i in range(min(8, await btns.count()))])
            await page.click("[data-testid=ai-subject-Science]")
            await page.wait_for_timeout(2500)
        for q in ["Why does ice float on water? Explain for Class 8.", "Give one everyday example where friction is useful."]:
            await page.locator("[data-testid=ai-input]").fill(q)
            await page.click("[data-testid=ai-send]")
            before = len(await page.locator("[data-testid=ai-messages]").inner_text())
            for _ in range(60):
                await page.wait_for_timeout(1000)
                if await page.locator("[data-testid=ai-send]").is_enabled() and len(await page.locator("[data-testid=ai-messages]").inner_text()) > before + len(q) + 40:
                    break
            await page.wait_for_timeout(2000)
        await shot(page, "ai_03_student")
        await b.close()

asyncio.run(main())
