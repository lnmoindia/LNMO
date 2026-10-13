import os
import re
from pathlib import Path
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
load_dotenv("/app/frontend/.env")
BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
SHOTS = Path("/app/docs/shots")
SHOTS.mkdir(parents=True, exist_ok=True)
BANNED = ["Sunrise Demo Setup", "sunrise-setup", "Mylode", "MHSK", "mhsk", "LPGS", "lpgs", "Fees Demo", "feesdemo", "p50demo", "UPI School", "Other School"]
PA = (os.environ["PLATFORM_ADMIN_EMAIL"], os.environ["PLATFORM_ADMIN_PASSWORD"])
ADMIN = ("admin@sunrise-demo.in", "Sunrise@2026")
PW = "Sunrise@2026"

HIDE_JS = """(banned) => {
  const bad = (t) => banned.some((b) => t.includes(b));
  document.querySelectorAll('tr, li, [role=option], [data-testid*=card], [data-testid*=row]').forEach((el) => {
    if (bad(el.innerText || '') && !el.querySelector('table')) el.style.display = 'none';
  });
  document.querySelectorAll('input[type=password]').forEach((el) => { el.value = el.value ? '••••••••••' : ''; });
}"""

MARK_JS = """([sel, label]) => {
  const el = document.querySelector(sel); if (!el) return false;
  const r = el.getBoundingClientRect();
  const box = document.createElement('div');
  box.className = '__doc_hl';
  Object.assign(box.style, {position:'fixed', left:(r.left-6)+'px', top:(r.top-6)+'px', width:(r.width+12)+'px', height:(r.height+12)+'px',
    border:'3px solid #f43f5e', borderRadius:'10px', zIndex:99999, pointerEvents:'none', boxShadow:'0 0 0 4px rgba(244,63,94,.18)'});
  document.body.appendChild(box);
  if (label) { const t = document.createElement('div'); t.className='__doc_hl'; t.textContent = label;
    Object.assign(t.style, {position:'fixed', left:Math.max(4, r.left-6)+'px', top:Math.max(4, r.top-34)+'px', background:'#f43f5e', color:'#fff',
      font:'600 13px system-ui, sans-serif', padding:'4px 10px', borderRadius:'999px', zIndex:99999, pointerEvents:'none'});
    document.body.appendChild(t); }
  return true;
}"""


async def shot(page, name, marks=(), full=False, wait=900):
    await page.wait_for_timeout(wait)
    await page.evaluate(HIDE_JS, BANNED)
    for sel, label in marks:
        try:
            await page.evaluate(MARK_JS, [sel, label])
        except Exception:
            pass
    await page.screenshot(path=str(SHOTS / f"{name}.png"), full_page=full)
    await page.evaluate("() => document.querySelectorAll('.__doc_hl').forEach(e => e.remove())")
    print("shot", name)


async def login(page, email, pw, slug="", shot_name=None):
    await page.context.clear_cookies()
    await page.goto(f"{BASE}/login{('/' + slug) if slug else ''}")
    await page.wait_for_selector("input[type=password]")
    await page.locator("input").nth(0).fill(email)
    if shot_name:
        await shot(page, shot_name, [("button[type=submit]", "Sign in")])
    await page.locator("input[type=password]").fill(pw)
    await page.get_by_role("button", name=re.compile("Sign in", re.I)).click()
    await page.wait_for_timeout(3500)
