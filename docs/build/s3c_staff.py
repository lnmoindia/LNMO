"""Step 3c: re-shoot staff portals (after clearing first-login password prompt for demo staff) and the issues tab."""
import asyncio
from playwright.async_api import async_playwright
from common import ADMIN, login
from s3_capture import go, click, principal, teacher


async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        for fn in (principal, teacher):
            ctx = await b.new_context(viewport={"width": 1440, "height": 900})
            await fn(await ctx.new_page())
            await ctx.close()
        page = await (await b.new_context(viewport={"width": 1440, "height": 900})).new_page()
        await login(page, *ADMIN, slug="sunrise")

        async def issues(pg):
            await click(pg, "[data-testid=proofs-kind-issues]", 2500)
        await go(page, "/app/fees?tab=proofs", "fe_12_issues", [("[data-testid^=issue-record-payment-]", "Record payment & resolve")], before=issues)
        await b.close()

asyncio.run(main())
