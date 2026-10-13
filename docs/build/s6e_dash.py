"""v1.1 step 6e: platform dashboard (plans now populated; platform email masked)."""
import asyncio
from playwright.async_api import async_playwright
from common import PA, BANNED, shot, login

MASK_JS = """([email, banned]) => {
  const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  const hide = [];
  while (w.nextNode()) {
    const n = w.currentNode;
    if (n.nodeValue.includes(email)) n.nodeValue = n.nodeValue.replace(email, 'Platform Manager');
    if (banned.some((b) => n.nodeValue.includes(b))) hide.push(n.parentElement);
  }
  hide.forEach((el) => { const row = el.closest('li, tr, a, div.flex, div') ; if (row) row.style.display = 'none'; });
}"""


async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        page = await (await b.new_context(viewport={"width": 1440, "height": 900})).new_page()
        await login(page, *PA)
        await page.goto(page.url.split("/platform")[0] + "/platform")
        await page.wait_for_timeout(3500)
        await page.evaluate(MASK_JS, [PA[0], BANNED + ["setup@", "admin@sunrise-setup"]])
        txt = await page.inner_text("body")
        print("leak:", PA[0] in txt, any(x in txt for x in BANNED))
        await shot(page, "pm_02_dashboard")
        await b.close()

asyncio.run(main())
