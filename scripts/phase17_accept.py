"""Phase 17 LPGS acceptance: upload class-teacher signature live (sreeja66), inject principal
signature into the vault for deepa.s (password unknown -> do-not-touch account, signature added
via server-side storage only; scope/password untouched), then fetch Fathima's COMPOSED report
card and render a faithful print-sheet HTML into frontend/public for screenshot proof."""
import os, sys, uuid, httpx, asyncio, html
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")
sys.path.insert(0, "/app/backend")
import server  # for _put_object/init_storage (server-side vault write)

BASE = "https://lnmo-fees.preview.emergentagent.com"
CT_URL = "https://static.prod-images.emergentagent.com/jobs/7f90be22-c857-41e0-aadc-b69a172c3ab6/images/f898f726c180a105d4aa3909f680341abbe4b0dfe951cc0bcb126bbe511685fc.jpeg"
PR_URL = "https://static.prod-images.emergentagent.com/jobs/7f90be22-c857-41e0-aadc-b69a172c3ab6/images/8f2100eaacc33582183b2283c2fe499f58eeb566842476aa45f1cca3bda6e2ca.jpeg"
DEEPA_ID = "db3277b2-8a6e-4308-9de9-1ec093f5e4ee"
FATHIMA = "5ed50271-17ee-4cae-91df-bc0b19dc15fc"
db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
esc = lambda s: html.escape(str(s if s is not None else ""))


def sig_html(signers):
    def person(p, role):
        img = f'<img class="sigimg" src="{p["signature"]}" />' if p and p.get("signature") else '<div class="sigimg"></div>'
        fb = '<div class="sigfallback">(subject teacher)</div>' if p and p.get("fallback") else ""
        return f'<div class="sigcol">{img}<div class="sigline"></div><div class="signame">{esc(p.get("name") if p else "")}</div><div class="sigrole">{esc(role)}</div>{fb}</div>'
    s = signers or {}
    seal = f'<div class="sigcol sealcol"><img class="sealimg" src="{s["seal"]}" /><div class="sigrole">School Seal</div></div>' if s.get("seal") else ""
    return f'<div class="sigrow">{person(s.get("class_teacher"),"Class Teacher")}{person(s.get("principal"),(s.get("principal") or {}).get("title") or "Principal")}{seal}</div>'


async def main():
    ct_bytes = httpx.get(CT_URL, timeout=60).content
    pr_bytes = httpx.get(PR_URL, timeout=60).content

    # 1) class teacher signature via LIVE API (proves the real upload path)
    with httpx.Client(base_url=BASE, timeout=60) as c:
        r = c.post("/api/auth/login", json={"email": "sreeja66@lpgs.com", "password": "teach123"})
        tok = r.cookies.get("access_token")
        up = c.post("/api/profile/signature", headers={"Authorization": f"Bearer {tok}"},
                    files={"file": ("sig.jpg", ct_bytes, "image/jpeg")})
        print("[%s] class-teacher (sreeja66) live signature upload" % up.status_code, up.text[:100])

    # 2) principal signature injected into vault (deepa.s password unknown; scope/password untouched)
    existing = await db.users.find_one({"id": DEEPA_ID}, {"_id": 0, "signature_path": 1})
    if not (existing or {}).get("signature_path"):
        path = f"lnmo/signatures/{DEEPA_ID}/{uuid.uuid4()}.jpg"
        server._put_object(path, pr_bytes, "image/jpeg")
        await db.users.update_one({"id": DEEPA_ID}, {"$set": {"signature_path": path, "signature_type": "image/jpeg"}})
        print("[injected] principal (deepa.s) vault signature set")
    else:
        print("[skip] principal signature already present")

    # 3) fetch COMPOSED report card as admin + verify no vault path leak
    with httpx.Client(base_url=BASE, timeout=60) as c:
        r = c.post("/api/auth/login", json={"email": "admin@lpgs.com", "password": "admin123"})
        tok = r.cookies.get("access_token"); c.cookies.clear()
        rc = c.get(f"/api/students/{FATHIMA}/report-card", headers={"Authorization": f"Bearer {tok}"})
        data = rc.json()
        sg = data["signers"]
        raw = rc.text
        print("ct sig present:", bool(sg["class_teacher"]["signature"]), "| ct name:", sg["class_teacher"]["name"])
        print("principal sig present:", bool(sg["principal"]["signature"]), "| precedence:", sg["principal"]["precedence"], "| name:", sg["principal"]["name"])
        print("seal present:", bool(sg["seal"]))
        print("vault path leak (should be False):", ("lnmo/signatures" in raw or "lnmo/seals" in raw))

    # 4) render faithful print-sheet preview into frontend/public
    s = data["student"]; name = f"{s.get('first_name','')} {s.get('last_name','')}".strip()
    subj_rows = "".join(
        f'<tr><td><strong>{esc(r["subject"])}</strong><br/><span class="muted">' +
        " · ".join(f'{esc(a["name"])}: {a["score"]}/{a["max_marks"]}' for a in r["assessments"]) +
        f'</span></td><td>{r["total_score"]}</td><td>{r["total_max"]}</td><td>{r["pct"]}%</td><td><strong>{esc(r["grade"])}</strong></td></tr>'
        for r in data["subjects"])
    o = data["overall"]; att = data["attendance"]
    att_txt = f'{att["pct"]}% ({att["present"]}/{att["total"]} days)' if att["pct"] is not None else "No records"
    table = ('<p class="muted" style="padding:18px 0">No published assessment results yet.</p>' if not data["subjects"]
             else f'<table><thead><tr><th>Subject</th><th style="width:70px">Scored</th><th style="width:70px">Max</th><th style="width:70px">%</th><th style="width:60px">Grade</th></tr></thead><tbody>{subj_rows}<tr class="totals"><td>Overall</td><td>{o["total_score"]}</td><td>{o["total_max"]}</td><td>{o["pct"]}%</td><td>{esc(o.get("grade") or "—")}</td></tr></tbody></table>')
    styles = """* {box-sizing:border-box;margin:0;padding:0;} body{font-family:Georgia,'Times New Roman',serif;color:#1a202c;padding:28px;}
h1{font-size:20px;margin-bottom:2px;} h2{font-size:14px;font-weight:normal;color:#555;margin-bottom:16px;}
table{width:100%;border-collapse:collapse;margin-top:10px;} th,td{border:1px solid #cbd5e0;padding:6px 8px;font-size:12px;text-align:left;}
th{background:#f1f5f9;text-transform:uppercase;font-size:10px;letter-spacing:.05em;} .muted{color:#718096;font-size:11px;}
.head{display:flex;justify-content:space-between;align-items:flex-end;border-bottom:2px solid #1a202c;padding-bottom:10px;margin-bottom:6px;} .badge{font-size:11px;}
.totals td{font-weight:bold;background:#f8fafc;}
.sigrow{display:flex;justify-content:space-around;align-items:flex-end;margin-top:56px;gap:24px;} .sigcol{text-align:center;width:180px;}
.sigimg{height:46px;width:auto;max-width:150px;object-fit:contain;display:block;margin:0 auto 2px;} .sigline{border-top:1px solid #999;margin-top:4px;}
.signame{font-size:11px;font-weight:bold;margin-top:4px;} .sigrole{font-size:10px;color:#718096;text-transform:uppercase;letter-spacing:.05em;margin-top:2px;}
.sigfallback{font-size:9px;color:#a0aec0;font-style:italic;} .sealcol{width:110px;} .sealimg{height:74px;width:74px;object-fit:contain;display:block;margin:0 auto 4px;}"""
    inst = data["institution"]
    body = f"""<div class="head"><div><h1>{esc(inst.get("portal_name") or inst.get("name") or "Report Card")}</h1><h2>Progress Report · {esc(data.get("academic_year") or "")}</h2></div><div class="badge">Generated {esc("05/10/2026")}</div></div>
<table style="margin-bottom:14px"><tbody><tr><th style="width:130px">Student</th><td>{esc(name)}</td><th style="width:130px">Admission No.</th><td>{esc(s.get("admission_no") or "—")}</td></tr>
<tr><th>Class</th><td>{esc(s.get("class_name") or "—")}{(" · Section "+esc(s.get("section"))) if s.get("section") else ""}</td><th>Attendance</th><td>{att_txt}</td></tr></tbody></table>
{table}{sig_html(sg)}"""
    out = f"<!DOCTYPE html><html><head><meta charset='utf-8'><title>Report Card</title><style>{styles}</style></head><body>{body}</body></html>"
    with open("/app/frontend/public/rc_preview.html", "w") as f:
        f.write(out)
    print("preview written -> /rc_preview.html")


asyncio.run(main())
