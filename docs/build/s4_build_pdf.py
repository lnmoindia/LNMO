"""Step 4: build /app/docs/LNMO_Product_Guide.pdf (HTML → Chromium PDF, A4 portrait)."""
import asyncio
import html
from pathlib import Path
from PIL import Image
from playwright.async_api import async_playwright

SH = Path("/app/docs/shots")
IMG = Path("/app/docs/build/img")
IMG.mkdir(parents=True, exist_ok=True)
OUT = Path("/app/docs/LNMO_Product_Guide.pdf")
E = html.escape


def img(name):
    src = SH / f"{name}.png"
    if not src.exists():
        return None
    dst = IMG / f"{name}.jpg"
    im = Image.open(src).convert("RGB")
    if im.width > 1440:
        im = im.resize((1440, int(im.height * 1440 / im.width)))
    im.save(dst, "JPEG", quality=78, optimize=True)
    return dst


S = [  # id, title, who, purpose, steps, shots[(name, caption)], tips
 ("pm", "Platform Manager: onboard a new school", "LNMO Platform Manager",
  "Create and manage schools (tenants), plans, messaging credits and support from one console. Each school's data is completely isolated.",
  ["Sign in at /login with the platform manager account.", "Open Tenancy → Institutions and click “New Institution”.",
   "Enter the school name, code, domain, city and contact details, plus the first Institution Admin's name, login email and password.",
   "Click Create. The school appears in the list and its admin can sign in immediately at /login/<school-slug>.",
   "Use Plans to define subscription tiers, Communication to approve SMS/WhatsApp credit requests, and Issues to triage support tickets and app crash reports.",
   "Open a school → Features / AI to switch on the AI Tutor layer for that school only."],
  [("pm_01_login", "Sign-in screen"), ("pm_03_institutions", "Institutions list — add a school"), ("pm_04_create_form", "Create-institution form, complete with the Create button — the first admin login is created in the same step (shown for the throwaway “Sunrise Demo Setup” school)"),
   ("pm_05_created", "The new school appears instantly"), ("pm_02_dashboard", "Platform dashboard"), ("pm_06_plans", "Plans"),
   ("pm_07_issues", "Issues & Crashes: tickets raised from inside the school app, plus one genuine browser crash that the app reported automatically"), ("pm_08_comm", "Platform communication: credits, templates, approvals"), ("pm_09_library", "LNMO Library (shared curriculum content)"),
   ("pm_10_ai_before", "Institution → Features / AI: AI Layer off (default)"), ("pm_11_ai_enabled", "AI Layer switched on for Sunrise only")],
  ["Passwords are never shown again after creation — the admin can reset them from their profile.", "Every platform action is written to the Audit Log."]),
 ("onb", "Institution Admin onboarding", "Institution Admin",
  "Set the school up in about an hour: profile, academic structure, staff, principals and students.",
  ["Sign in at /login/<school-slug>. A fresh school opens the Setup wizard, which tracks each step.",
   "Settings → school profile, logo and seal (used on receipts, report cards and print views).",
   "Academic Years: create the year (e.g. 2026-27) with start/end dates. Academic Units: create divisions such as Primary and High School.",
   "Class Hub: classes, sections, class teachers and the subject teacher for every section; Subjects: the subject catalogue (bulk import supported).",
   "Teachers: add staff; mark a teacher as Principal and scope them to one or more divisions — they only ever see those classes.",
   "Students: add one by one or import from CSV; each student gets an admission number and is enrolled in the active year."],
  [("ad_02_setup_wizard", "Setup wizard on first login (a fresh throwaway school, “Sunrise Demo Setup”)"), ("ad_02b_setup_progress", "Wizard in progress: completed steps are ticked"), ("ad_04_setup_done", "Setup checklist completed (Sunrise)"), ("ad_03_dashboard", "Admin dashboard"),
   ("ad_05_settings", "School profile, logo and seal"), ("ad_07_years", "Academic years"), ("ad_08_units", "Academic units (divisions)"),
   ("ad_09_classhub", "Class Hub: sections, class teachers, subject staff"), ("ad_10_subjects", "Subjects"), ("ad_11_teachers", "Teachers and principals"),
   ("ad_12_users", "User accounts"), ("ad_13_students", "Students")],
  ["Principal scoping is by division: a High School principal cannot open Primary classes, fees or reports.", "Use Users to deactivate accounts — records are never hard-deleted."]),
 ("par", "Parent onboarding (OTP & paper invite slips)", "Admin / Principal → Parent",
  "Get every parent onto the parent portal, whether or not a phone number is on file.",
  ["Students page → Invite parents: parents with a phone number receive a WhatsApp/SMS invite link and verify with an OTP.",
   "For families without a phone on file, print paper setup slips (one per student, with a one-time setup code).",
   "The parent opens /setup/parent, enters the code or link, sets a password and is linked to their child (multiple children are supported).",
   "Track pending/accepted invites and send reminders from the same screen."],
  [("po_01_invites", "Students page with parent invite tools")],
  ["In this demo, SMS/WhatsApp run in STUB (demo) mode: messages are logged in history, not delivered."]),
 ("tt", "Smart Timetable", "Admin / Principal",
  "Generate a clash-free weekly timetable from subject requirements, then publish it to teachers, students and parents.",
  ["Timetable → configuration: working days, periods and breaks (per year, optionally per division).",
   "Class Hub → set periods per week and the teacher for each subject/section.",
   "Generate for a class: the solver places every period without teacher or class clashes and reports anything it could not place.",
   "Review the draft grid, drag to adjust, then Publish. Use Substitutions for day-to-day absences."],
  [("tt_01_timetable", "Generated class timetable"), ("tt_02_substitutions", "Substitutions — empty because no teacher is marked absent today"), ("rt_03_timetable", "A teacher's personal timetable")],
  ["Re-generate any time before publishing; published timetables are versioned."]),
 ("ex", "Exams, assessments and report cards", "Admin / Principal / Teacher",
  "Plan an exam timetable per division, collect marks from subject teachers and publish results and report cards.",
  ["Exams → New exam: name, type and a date window plus time slots for each division.",
   "Generate the exam schedule (no student sits two papers at once) and the mark registers.",
   "Teachers enter marks in Marks Entry; after publishing, only a principal/admin can correct marks (audited).",
   "Publish results: students and parents see marks and report cards; report cards can also be sent to parents."],
  [("ex_02_exams", "Exams"), ("ex_03_exam_detail", "Exam schedule and registers"), ("ex_01_assessments", "Assessments — all Term 1 papers published"), ("rt_04_marks", "Teacher marks entry (published)"),
   ("rs_03_results", "Student: published results with score trends")],
  ["Results here are visible to students and parents only after Publish results."]),
 ("pf", "Profiles", "Admin / Principal / Teacher",
  "One profile per student and teacher: personal details, guardians, class history, attendance, marks, achievements and fees.",
  ["Open Students and click a student to view their profile.", "Teachers maintain their own profile under My Profile."],
  [("pf_01_student_profile", "Student profile"), ("rt_08_profile", "Teacher profile")], []),
 ("ai", "AI Tutor", "Student (managed by Admin / Teacher)",
  "A safe AI study companion aligned to the school's curriculum; teachers can review and comment on curriculum content.",
  ["Platform Manager switches on the AI Layer for the school (Institution → Features / AI).",
   "Teachers add chapters, notes and textbook material for their class and subject under AI Tutor, then submit the curriculum.",
   "The admin or principal approves it under AI Tutor → Pending curricula, and turns the AI Tutor on for that curriculum in the Curricula browser.",
   "Student portal → AI Tutor: pick the subject and ask a question; answers come from the approved curriculum, step by step."],
  [("ai_03_student", "Student AI Tutor: a real answer to a Grade 8 Science question, generated live by Gemini"),
   ("ai_01_admin", "AI Tutor administration: Grade 8 Science published with the AI Tutor on"),
   ("ai_02_teacher", "Teacher workspace: approved chapters and materials")],
  ["Subjects without an approved curriculum show “Not enabled yet” to students."]),
 ("fe", "Fees", "Admin (collection also by Principals for their divisions)",
  "End-to-end offline fee management: structures, ledgers, receipts, day book, defaulters and reminders, monthly reports, UPI QR and payment proofs.",
  ["Structures: define fee heads per division and year (term/monthly/one-time, late fee), apply to students and generate invoices.",
   "Accounts → Ledger: every invoice and payment for a student; set concessions; download the statement PDF.",
   "Collect: amount, method (cash/UPI/cheque/bank), reference and payment date (backdating allowed, audited). A numbered receipt and PDF are issued instantly.",
   "Day Book: the day's collection by method, collector and class; print for the daily cash closing.",
   "Defaulters: overdue students with ageing buckets; one-tap or bulk reminders (max one per student per day); CSV and print.",
   "Monthly Summary: billed vs collected per class, previous dues, collection %, printable management report.",
   "UPI: enable in Settings → UPI payments; parents see a QR for the exact balance and upload a screenshot (“I've paid”).",
   "Payment proofs: staff approve (creates a normal receipt dated on the payment date) or reject with a reason; parent “I have already paid” issues are handled in the same tab."],
  [("fe_01_structures", "Fee structures"), ("fe_02_accounts", "Student accounts"), ("fe_03_ledger", "Ledger with statement download"),
   ("fe_04_collect", "Collect payment with payment date"), ("fe_05_receipts", "Receipts register"), ("fe_06_daybook", "Day Book"),
   ("fe_07_defaulters", "Defaulters with one-tap reminders"), ("fe_09_monthly", "Monthly collection summary"), ("ad_06_upi_settings", "UPI settings"),
   ("rpa_02_parent_fees", "Parent: UPI QR, “I've paid”, verification pending"), ("fe_10_parent_qr_mobile", "Parent on mobile: Open UPI app"),
   ("fe_11_proofs", "Staff payment-proof queue"), ("fe_12_issues", "Fee issues thread")],
  ["To reverse a wrong receipt use the ↺ action in the ledger: the payment is kept and flagged with a credit note — never deleted.",
   "Unpaid balances carry forward automatically as “Previous dues” at year-end promotion."]),
 ("cm", "Communications", "Admin / Principal",
  "Notices, WhatsApp/SMS messages, templates and message history in one place.",
  ["Notices: publish to the whole school, a division or a class (with attachments).", "Communication: send WhatsApp/SMS to parents using approved templates; view delivery history and credit balance."],
  [("cm_01_comm", "Communication centre: history of fee reminders, notices and parent invites (STUB / Test mode)"), ("op_03_notices", "Notices")], ["Demo/STUB mode in this environment: nothing is delivered to real phones."]),
 ("pr", "Promotion / Rollover", "Admin (whole-school principal)",
  "Move every student to the next year in one auditable run, with recommendations from class teachers.",
  ["Promotion → choose from-year and to-year → Preview: each student gets a decision (promote, detain, graduate, transfer).",
   "Students with unpaid fees show “Dues pending ₹X” and a summary banner — a warning only, promotion is not blocked.",
   "Execute after typing the confirmation. Unpaid balances move to the new year as a “Previous dues” invoice (idempotent, linked to originals). A rollback is available."],
  [("pr_01_promotion", "Promotion preview with dues warning")], []),
 ("ops", "Other modules: attendance, homework, audit and support", "Admin / Principal / Teacher",
  "Daily operations that round out the ERP.",
  ["Attendance: class teachers mark daily attendance; admins see school-wide registers.", "Homework / Assignments: teachers post work, students submit, the monitor tracks completion.",
   "Audit Log: every create/update/payment action with who and when.", "Support: raise an issue to the LNMO team from inside the app."],
  [("op_01_attendance", "Attendance"), ("op_02_homework", "Homework monitor"), ("rt_06_homework", "Teacher: homework posted"), ("op_04_audit", "Audit log"),
   ("op_05_support", "Support: tickets raised by the school"), ("rpa_04_report_card", "Report an issue — available to every user, including parents")], []),
 ("tour", "Portal tours: principal, teacher, parent and student", "Each role",
  "What each person sees after signing in.",
  ["Principal: a school dashboard limited to their divisions, plus fees, defaulters, timetable, exams and promotion within scope.",
   "Teacher: My Class (for class teachers), timetable, marks entry, attendance, homework, view-only fee defaulters for their own section.",
   "Parent: every linked child in one place — attendance, marks, homework, notices, fees with UPI QR, receipts and statement.",
   "Student: timetable, homework, results, notices and the AI Tutor."],
  [("rp_01_principal_dash", "Principal dashboard"), ("rp_02_principal_defaulters", "Principal: defaulters for their divisions"),
   ("rt_01_dash", "Teacher dashboard"), ("rt_02_myclass", "Teacher: My Class"), ("rt_05_attendance", "Teacher: attendance"), ("rt_07_feedefaulters", "Teacher: fee defaulters (view only)"),
   ("rpa_01_parent_home", "Parent portal"), ("rpa_03_mobile_home", "Parent portal on mobile"), ("rs_01_student_home", "Student portal"), ("rs_02_student_mobile", "Student portal on mobile")], []),
]

MATRIX = [("Create schools, plans, credits", "✓", "", "", "", "", ""), ("School setup, structure, users", "", "✓", "", "", "", ""),
          ("Classes / students in scope", "", "All", "Own divisions", "Own class", "", ""), ("Timetable generate & publish", "", "✓", "✓ (scope)", "View", "View", "View"),
          ("Marks entry", "", "✓", "✓ (scope)", "Own subjects", "", ""), ("Publish results / correct marks", "", "✓", "✓ (scope)", "", "View", "View"),
          ("Fee structures & concessions", "", "✓", "View", "", "", ""), ("Collect / reverse / approve UPI proofs", "", "✓", "✓ (scope)", "", "", ""),
          ("Defaulters & reminders", "", "✓", "✓ (scope)", "View own section", "", ""), ("Pay by UPI, upload proof, raise issue", "", "", "", "", "Own children", ""),
          ("Promotion / rollover", "", "✓", "Whole-school only", "Recommend", "", ""), ("AI Tutor", "", "Manage", "Manage", "Manage", "", "Use"),
          ("Audit log", "✓", "✓", "✓ (scope)", "", "", "")]
GLOSS = [("Institution / tenant", "One school. Its data is isolated from every other school."), ("Division / Academic unit", "A group of classes such as Primary or High School; principals are scoped by division."),
         ("Day Book", "The daily collection register used for cash closing."), ("Defaulter", "A student with an invoice past its due date and an unpaid balance."),
         ("Previous dues / arrears", "Unpaid balance carried into the next academic year at promotion."), ("UTR", "The 12-digit UPI/bank transaction reference."),
         ("Payment proof", "A parent-uploaded payment screenshot awaiting staff verification."), ("STUB mode", "Demo messaging: messages are logged but not delivered.")]
FAQ = [("How do I collect cash?", "Fees → Accounts → open the student's Ledger → Collect on the invoice → method Cash, amount, payment date → Record. Print or download the receipt."),
       ("How do I reverse a payment?", "Open the Ledger, click ↺ on the receipt and enter a reason. The receipt is kept, marked reversed with a credit-note number, and the balance is restored."),
       ("A parent paid by UPI — how is it recorded?", "The parent uploads the screenshot with “I've paid”. In Fees → Payment proofs, approve it (edit the amount/UTR if needed); a normal UPI receipt is created on the payment date."),
       ("Can a principal see other divisions?", "No. Every list, report, fee action and export is filtered to the divisions assigned to that principal."),
       ("Is data ever deleted?", "Operational records are never hard-deleted: they are deactivated, reversed or rolled back with an audit trail.")]


def section_html(i, s):
    sid, title, who, purpose, steps, shots, tips = s
    figs = []
    for name, cap in shots:
        p = img(name)
        if p:
            narrow = ' style="width:62%"' if name == "pm_04_create_form" else ""
            figs.append(f'<figure><img src="file://{p}"{narrow}/><figcaption>{E(cap)}</figcaption></figure>')
    return f"""<section id="{sid}" class="chap"><div class="kicker">Section {i}</div><h1>{E(title)}</h1>
      <div class="meta"><span><b>Who:</b> {E(who)}</span></div><p class="lead">{E(purpose)}</p>
      <h3>Steps</h3><ol>{''.join(f'<li>{E(x)}</li>' for x in steps)}</ol>
      {('<div class="tip"><b>Tips</b><ul>' + ''.join(f'<li>{E(t)}</li>' for t in tips) + '</ul></div>') if tips else ''}
      {''.join(figs)}</section>"""


def build_html():
    toc = "".join(f'<li><a href="#{s[0]}"><span>{i}. {E(s[1])}</span></a></li>' for i, s in enumerate(S, 3))
    roles = "".join(f'<div class="role"><b>{r}</b><small>{d}</small></div>{"<div class=arrow>→</div>" if k < 5 else ""}' for k, (r, d) in enumerate([
        ("Platform Manager", "Creates schools"), ("Institution Admin", "Runs the school"), ("Principal", "Scoped to divisions"),
        ("Teacher", "Classes & subjects"), ("Parent", "Own children"), ("Student", "Own learning")]))
    mods = "".join(f'<div class="mod"><b>{a}</b><small>{b}</small></div>' for a, b in [
        ("Setup & People", "Wizard, profile, years, units, classes, staff, principals, students, users"), ("Academics", "Class Hub, subjects, smart timetable, substitutions"),
        ("Assessment", "Exams, mark registers, results, report cards"), ("Daily operations", "Attendance, homework, assignments, notices"),
        ("Fees", "Structures, ledgers, receipts, day book, defaulters, UPI QR, proofs, statements"), ("Communication", "WhatsApp/SMS, templates, credits, history"),
        ("AI Tutor", "Curriculum-aligned AI help for students"), ("Year-end", "Promotion / rollover with dues carry-forward"), ("Governance", "Audit log, support, crash analytics")])
    matrix = "".join(f"<tr><td>{E(r[0])}</td>" + "".join(f"<td>{E(c)}</td>" for c in r[1:]) + "</tr>" for r in MATRIX)
    gloss = "".join(f"<tr><td><b>{E(a)}</b></td><td>{E(b)}</td></tr>" for a, b in GLOSS)
    faq = "".join(f"<div class='faq'><b>{E(q)}</b><p>{E(a)}</p></div>" for q, a in FAQ)
    chapters = "".join(section_html(i, s) for i, s in enumerate(S, 3))
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
    @page {{ size: A4; margin: 18mm 14mm 16mm 14mm; }}
    * {{ box-sizing: border-box; }} body {{ font-family: 'Liberation Sans', 'FreeSans', Arial, sans-serif; color: #1e293b; font-size: 10.5pt; line-height: 1.5; margin: 0; }}
    .cover {{ height: 255mm; background: #0b1020; color: #fff; padding: 28mm 18mm; position: relative; page-break-after: always; border-radius: 6px; }}
    .logo {{ width: 64px; height: 64px; border-radius: 16px; background: #4f46e5; display: flex; align-items: center; justify-content: center; font-size: 34px; font-weight: 800; }}
    .cover h1 {{ color: #fff; font-size: 34pt; line-height: 1.1; margin: 22mm 0 6mm; }} .cover .sub {{ color: #a5b4fc; font-size: 13pt; }}
    .cover .band {{ position: absolute; left: 18mm; right: 18mm; bottom: 26mm; border-top: 1px solid #334155; padding-top: 6mm; color: #cbd5e1; font-size: 10pt; display: flex; justify-content: space-between; }}
    .cover .accent {{ height: 6px; width: 80px; background: #10b981; border-radius: 3px; margin-top: 8mm; }}
    h1 {{ font-size: 20pt; color: #0f172a; margin: 0 0 3mm; }} h2 {{ font-size: 14pt; color: #312e81; margin: 7mm 0 2mm; }} h3 {{ font-size: 11.5pt; color: #312e81; margin: 5mm 0 1mm; }}
    .chap {{ page-break-before: always; }} .kicker {{ color: #4f46e5; font-weight: 700; text-transform: uppercase; letter-spacing: .12em; font-size: 8.5pt; }}
    .lead {{ font-size: 11.5pt; color: #334155; }} .meta {{ font-size: 9.5pt; color: #475569; margin-bottom: 2mm; }}
    ol li {{ margin-bottom: 1.2mm; }} figure {{ margin: 5mm 0; page-break-inside: avoid; }}
    figure img {{ width: 100%; border: 1px solid #cbd5e1; border-radius: 6px; box-shadow: 0 1px 3px rgba(15,23,42,.12); }}
    figcaption {{ font-size: 8.5pt; color: #64748b; margin-top: 1.5mm; }} figcaption::before {{ content: "▲ "; color: #4f46e5; }}
    .tip {{ background: #ecfdf5; border-left: 4px solid #10b981; padding: 3mm 5mm; border-radius: 4px; font-size: 9.5pt; page-break-inside: avoid; }}
    .tip ul {{ margin: 1mm 0 0; padding-left: 5mm; }}
    .toc ol {{ list-style: none; padding: 0; }} .toc li a {{ display: block; padding: 2.2mm 0; border-bottom: 1px dotted #cbd5e1; color: #1e293b; text-decoration: none; font-size: 11pt; }}
    .roles {{ display: flex; align-items: stretch; gap: 2mm; margin: 4mm 0; }} .role {{ flex: 1; background: #eef2ff; border: 1px solid #c7d2fe; border-radius: 8px; padding: 3mm 2mm; text-align: center; font-size: 9pt; }}
    .role small, .mod small {{ display: block; color: #64748b; font-size: 8pt; margin-top: 1mm; }} .arrow {{ align-self: center; color: #4f46e5; font-weight: 700; }}
    .mods {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 3mm; }} .mod {{ border: 1px solid #e2e8f0; border-top: 3px solid #4f46e5; border-radius: 6px; padding: 3mm; font-size: 9.5pt; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 8.8pt; margin-top: 3mm; }} th, td {{ border: 1px solid #cbd5e1; padding: 1.8mm 2mm; text-align: left; vertical-align: top; }}
    th {{ background: #eef2ff; color: #312e81; }} .mx td:not(:first-child), .mx th:not(:first-child) {{ text-align: center; }}
    .faq {{ margin: 3mm 0; page-break-inside: avoid; }} .faq p {{ margin: 1mm 0 0; color: #334155; }}
    .hl {{ display: grid; grid-template-columns: 1fr 1fr; gap: 3mm; }} .hl div {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 3mm; font-size: 9.5pt; }}
    </style></head><body>
    <div class="cover"><div class="logo">L</div><h1>LNMO School ERP —<br/>Product Guide</h1><div class="sub">Every role, every module, step by step — with real screens</div><div class="accent"></div>
      <div class="band"><span>Version 1.1 · October 2026</span><span>Demo school: Sunrise Public School (Demo)</span></div></div>
    <section class="toc"><div class="kicker">Contents</div><h1>Table of contents</h1><ol>
      <li><a href="#overview"><span>1. Product overview</span></a></li><li><a href="#security"><span>2. Multi-school isolation & security</span></a></li>{toc}
      <li><a href="#appendix"><span>{len(S) + 3}. Appendix: permissions, glossary, FAQ</span></a></li></ol>
      <p style="font-size:9pt;color:#64748b;margin-top:8mm">All names, phone numbers and figures in this guide are fictional demo data. Messaging (SMS/WhatsApp) runs in demo (STUB) mode.</p></section>
    <section id="overview" class="chap"><div class="kicker">Section 1</div><h1>Product overview</h1>
      <p class="lead">LNMO is a cloud School ERP for Indian K-12 schools. One platform runs many schools; each school gets its admin console, staff workspace and parent/student portals — on desktop and mobile.</p>
      <h2>Key benefits</h2><div class="hl"><div><b>One-hour setup</b><br/>Guided wizard, CSV imports and presets.</div><div><b>Smart timetable</b><br/>Clash-free generation in seconds.</div>
      <div><b>Fees without a gateway</b><br/>Receipts, day book, defaulters, UPI QR and proofs — money goes straight to the school.</div><div><b>Parents onboard easily</b><br/>OTP invites or paper slips.</div>
      <div><b>Division-scoped principals</b><br/>Each principal sees only their part of the school.</div><div><b>Audit everything</b><br/>No hard deletes; every change is traceable.</div></div>
      <h2>Roles</h2><div class="roles">{roles}</div><h2>Module map</h2><div class="mods">{mods}</div></section>
    <section id="security" class="chap"><div class="kicker">Section 2</div><h1>Multi-school isolation & security</h1>
      <ul><li><b>Strict tenant isolation:</b> every record carries its school's ID and every query is filtered by it. A user of one school cannot see or change another school's data, even by guessing links.</li>
      <li><b>Role and scope checks on the server:</b> principals are limited to their divisions, teachers to their classes/subjects, parents to their own children — enforced on every API call, not just hidden in the menu.</li>
      <li><b>Secure sign-in:</b> passwords are hashed; sessions use secure, HTTP-only cookies; brute-force protection on login.</li>
      <li><b>Private files:</b> photos, payment screenshots and attachments are stored in private object storage and served only to authorised users.</li>
      <li><b>No silent changes:</b> payments are reversed with credit notes rather than deleted; promotions can be rolled back; the audit log records who did what and when.</li>
      <li><b>Messaging controls:</b> templates and credits are approved by the platform; this demo runs in STUB mode.</li></ul></section>
    {chapters}
    <section id="appendix" class="chap"><div class="kicker">Section {len(S) + 3}</div><h1>Appendix</h1><h2>Role & permission matrix</h2>
      <table class="mx"><tr><th>Capability</th><th>Platform</th><th>Admin</th><th>Principal</th><th>Teacher</th><th>Parent</th><th>Student</th></tr>{matrix}</table>
      <h2>Glossary</h2><table>{gloss}</table><h2>FAQ</h2>{faq}</section></body></html>"""


async def main():
    (Path("/app/docs/build") / "guide.html").write_text(build_html(), encoding="utf-8")
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page()
        await pg.goto("file:///app/docs/build/guide.html")
        await pg.wait_for_timeout(1500)
        foot = '<div style="font-size:7.5px;color:#64748b;width:100%;padding:0 14mm;display:flex;justify-content:space-between;font-family:Arial"><span>LNMO School ERP — Product Guide · v1.1 · Oct 2026</span><span>Page <span class="pageNumber"></span> / <span class="totalPages"></span></span></div>'
        head = '<div style="font-size:7.5px;color:#4f46e5;width:100%;padding:0 14mm;font-family:Arial;font-weight:bold;letter-spacing:.1em">LNMO</div>'
        await pg.pdf(path=str(OUT), format="A4", print_background=True, display_header_footer=True, header_template=head, footer_template=foot,
                     margin={"top": "18mm", "bottom": "16mm", "left": "14mm", "right": "14mm"})
        await b.close()
    print("pdf", OUT, OUT.stat().st_size // 1024, "KB")

asyncio.run(main())
