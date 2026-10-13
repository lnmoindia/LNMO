"""v1.1 step 6c: AI Tutor staff screens in the enabled state + chat question view."""
import asyncio
from playwright.async_api import async_playwright
from common import ADMIN, PW, shot, login
from s3_capture import go


async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        page = await (await b.new_context(viewport={"width": 1440, "height": 900})).new_page()
        await login(page, "deepa@sunrise-demo.in", PW, slug="sunrise")

        async def pick(pg):
            try:
                sel = pg.locator("[data-testid=ai-subject-select]")
                opts = await sel.locator("option").all_inner_texts()
                lab = "Grade 8 · Science" if "Grade 8 · Science" in opts else None
                print("opts", opts[:6])
                if lab:
                    await sel.select_option(label=lab)
                await pg.wait_for_timeout(3000)
            except Exception as e:
                print("pick", str(e)[:100])
        await go(page, "/teacher/ai-tutor", "ai_02_teacher", wait=3000, before=pick)
        await login(page, *ADMIN, slug="sunrise")

        async def browser(pg):
            try:
                await pg.get_by_text("Curricula browser").first.click()
                await pg.wait_for_timeout(2500)
            except Exception as e:
                print("browser", str(e)[:100])
        await go(page, "/app/ai-tutor", "ai_01_admin", wait=3000, before=browser)
        await b.close()
        return
        await page.click("[data-testid=quick-ai-tutor]")
        await page.wait_for_timeout(2000)
        await page.click("[data-testid=ai-subject-Science]")
        await page.wait_for_timeout(2000)
        await page.get_by_text("Why does ice float").first.click()
        await page.wait_for_timeout(3000)
        await page.evaluate("() => { const m = document.querySelector('[data-testid=ai-messages]'); if (m) m.scrollTop = 0; }")
        await shot(page, "ai_04_student_question")
        await b.close()

asyncio.run(main())
