const BASE_STYLES = `
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: Georgia, 'Times New Roman', serif; color: #1a202c; padding: 28px; }
  h1 { font-size: 20px; margin-bottom: 2px; }
  h2 { font-size: 14px; font-weight: normal; color: #555; margin-bottom: 16px; }
  table { width: 100%; border-collapse: collapse; margin-top: 10px; }
  th, td { border: 1px solid #cbd5e0; padding: 6px 8px; font-size: 12px; text-align: left; }
  th { background: #f1f5f9; text-transform: uppercase; font-size: 10px; letter-spacing: 0.05em; }
  .muted { color: #718096; font-size: 11px; }
  .break-row td { background: #f8fafc; text-align: center; color: #94a3b8; font-size: 10px; letter-spacing: 0.15em; text-transform: uppercase; }
  .head { display: flex; justify-content: space-between; align-items: flex-end; border-bottom: 2px solid #1a202c; padding-bottom: 10px; margin-bottom: 6px; }
  .badge { font-size: 11px; }
  .totals td { font-weight: bold; background: #f8fafc; }
  .sig { display: flex; justify-content: space-between; margin-top: 48px; font-size: 11px; color: #555; }
  .sig span { border-top: 1px solid #999; padding-top: 4px; width: 160px; text-align: center; }
  .sigrow { display: flex; justify-content: space-around; align-items: flex-end; margin-top: 56px; gap: 24px; }
  .sigcol { text-align: center; width: 180px; }
  .sigimg { height: 46px; width: auto; max-width: 150px; object-fit: contain; display: block; margin: 0 auto 2px; }
  .sigline { border-top: 1px solid #999; margin-top: 4px; }
  .signame { font-size: 11px; font-weight: bold; margin-top: 4px; }
  .sigrole { font-size: 10px; color: #718096; text-transform: uppercase; letter-spacing: 0.05em; margin-top: 2px; }
  .sigfallback { font-size: 9px; color: #a0aec0; font-style: italic; }
  .sealcol { width: 110px; }
  .sealimg { height: 74px; width: 74px; object-fit: contain; display: block; margin: 0 auto 4px; }
  @media print { body { padding: 8px; } }
`;

const esc = (s) => String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

export function openPrintWindow(title, bodyHtml) {
  const w = window.open("", "_blank");
  if (!w) return;
  w.document.write(`<!DOCTYPE html><html><head><title>${esc(title)}</title><style>${BASE_STYLES}</style></head><body>${bodyHtml}</body></html>`);
  w.document.close();
  w.focus();
  setTimeout(() => w.print(), 300);
}

const DAY_NAMES = { mon: "Monday", tue: "Tuesday", wed: "Wednesday", thu: "Thursday", fri: "Friday", sat: "Saturday", sun: "Sunday" };

export function printTimetable({ schoolName, className, section, year, config, entries }) {
  const cell = (d, pno) => {
    const e = entries.find((x) => x.day === d && x.period_no === pno);
    if (!e) return "";
    return `<strong>${esc(e.subject)}</strong>${e.type === "lab" ? " (Lab)" : ""}<br/><span class="muted">${esc(e.teacher_name || "")}${e.room ? " · " + esc(e.room) : ""}</span>`;
  };
  const rows = config.periods.map((p, i) => {
    const pno = i + 1;
    if (p.is_break) return `<tr class="break-row"><td>${esc(p.label)}<br/><span class="muted">${esc(p.start)}–${esc(p.end)}</span></td><td colspan="${config.working_days.length}">${esc(p.label)}</td></tr>`;
    return `<tr><td><strong>${esc(p.label)}</strong><br/><span class="muted">${esc(p.start)}–${esc(p.end)}</span></td>${config.working_days.map((d) => `<td>${cell(d, pno)}</td>`).join("")}</tr>`;
  }).join("");
  const body = `
    <div class="head"><div><h1>${esc(schoolName || "Weekly Timetable")}</h1><h2>${esc(className)} — Section ${esc(section)} · ${esc(year)}</h2></div><div class="badge">Generated ${new Date().toLocaleDateString()}</div></div>
    <table><thead><tr><th style="width:110px">Period</th>${config.working_days.map((d) => `<th>${DAY_NAMES[d]}</th>`).join("")}</tr></thead><tbody>${rows}</tbody></table>`;
  openPrintWindow(`Timetable ${className} ${section}`, body);
}

export function printExamClass({ schoolName, logoUrl, examName, className, section, rows }) {
  const logo = logoUrl ? `<img src="${esc(logoUrl)}" alt="" style="height:52px;width:auto;object-fit:contain" />` : "";
  const body = `
    <div class="head">
      <div style="display:flex;align-items:center;gap:14px">${logo}<div>
        <h1>${esc(schoolName || "Exam Timetable")}</h1>
        <h2>${esc(examName)} · ${esc(className)}${section ? " - Section " + esc(section) : ""}</h2>
      </div></div>
      <div class="badge">Generated ${new Date().toLocaleString()}</div>
    </div>
    ${rows.length === 0
      ? `<p class="muted" style="padding:18px 0">No papers scheduled for this class.</p>`
      : `<table><thead><tr><th style="width:90px">Date</th><th style="width:80px">Day</th><th style="width:110px">Time</th><th>Subject</th><th style="width:90px">Room</th></tr></thead>
         <tbody>${rows.map((r) => `<tr><td>${esc(r.date)}</td><td>${esc(r.day)}</td><td>${esc(r.time)}</td><td><strong>${esc(r.subject)}</strong></td><td>${esc(r.room || "")}</td></tr>`).join("")}</tbody></table>`}
    <div class="sig"><span>Class Teacher</span><span>Principal</span></div>`;
  openPrintWindow(`Exam — ${className}${section ? " " + section : ""}`, body);
}

export function printReportCard(data) {
  const s = data.student;
  const name = `${s.first_name || ""} ${s.last_name || ""}`.trim();
  const subjectRows = data.subjects.map((r) => `
    <tr>
      <td><strong>${esc(r.subject)}</strong><br/><span class="muted">${r.assessments.map((a) => `${esc(a.name)}: ${a.score}/${a.max_marks}`).join(" · ")}</span></td>
      <td>${r.total_score}</td><td>${r.total_max}</td><td>${r.pct}%</td><td><strong>${esc(r.grade)}</strong></td>
    </tr>`).join("");
  const o = data.overall;
  const body = `
    <div class="head">
      <div><h1>${esc(data.institution.portal_name || data.institution.name || "Report Card")}</h1><h2>Progress Report · ${esc(data.academic_year || "")}</h2></div>
      <div class="badge">Generated ${new Date().toLocaleDateString()}</div>
    </div>
    <table style="margin-bottom:14px"><tbody>
      <tr><th style="width:130px">Student</th><td>${esc(name)}</td><th style="width:130px">Admission No.</th><td>${esc(s.admission_no || "—")}</td></tr>
      <tr><th>Class</th><td>${esc(s.class_name || "—")}${s.section ? " · Section " + esc(s.section) : ""}</td><th>Attendance</th><td>${data.attendance.pct !== null ? `${data.attendance.pct}% (${data.attendance.present}/${data.attendance.total} days)` : "No records"}</td></tr>
    </tbody></table>
    ${data.subjects.length === 0
      ? `<p class="muted" style="padding:18px 0">No published assessment results yet.</p>`
      : `<table><thead><tr><th>Subject</th><th style="width:70px">Scored</th><th style="width:70px">Max</th><th style="width:70px">%</th><th style="width:60px">Grade</th></tr></thead>
         <tbody>${subjectRows}
         <tr class="totals"><td>Overall</td><td>${o.total_score}</td><td>${o.total_max}</td><td>${o.pct}%</td><td>${esc(o.grade || "—")}</td></tr></tbody></table>
         <p class="muted" style="margin-top:8px">Grades: A+ ≥90 · A ≥80 · B+ ≥70 · B ≥60 · C ≥50 · D ≥35 · F below 35</p>`}
    ${assignmentScoresSection(data.assignment_scores)}
    ${signatureRow(data.signers)}`;
  openPrintWindow(`Report Card — ${name}`, body);
}

function assignmentScoresSection(blocks) {
  if (!blocks || blocks.length === 0) return "";
  const rows = blocks.map((b) => `
    <tr><td><strong>${esc(b.subject)}</strong></td>
    <td>${b.items.map((it) => `${esc(it.title)}: ${it.score}/${it.max_marks}`).join(" · ")}</td></tr>`).join("");
  return `<h3 style="margin:16px 0 6px;font-size:13px">Assignment Scores</h3>
    <table><thead><tr><th style="width:140px">Subject</th><th>Assignments (verified)</th></tr></thead>
    <tbody>${rows}</tbody></table>
    <p class="muted" style="margin-top:6px">Teacher-tagged assignments counted toward this report (listed for reference; not weighted into the overall above).</p>`;
}

export function printMonthlyReport(data) {
  const monthLabel = (() => {
    const [y, m] = String(data.month || "").split("-");
    const d = new Date(Number(y), Number(m) - 1, 1);
    return isNaN(d) ? data.month : d.toLocaleDateString(undefined, { month: "long", year: "numeric" });
  })();
  const logoUrl = data.institution?.has_logo
    ? `${process.env.REACT_APP_BACKEND_URL}/api/public/institution-logo?domain=${encodeURIComponent(data.institution.domain || "")}`
    : data.institution?.logo_url;
  const logo = logoUrl ? `<img src="${esc(logoUrl)}" alt="" style="height:52px;width:auto;object-fit:contain" />` : "";
  const sectionBlocks = (data.sections || []).map((sec) => {
    const rows = sec.students.map((st) => {
      const h = st.homework, a = st.assignments;
      return `<tr>
        <td><strong>${esc(st.name)}</strong><br/><span class="muted">${esc(st.admission_no || "")}</span></td>
        <td>${h.submitted}/${h.assigned}</td><td>${h.late}</td><td>${h.verified}</td><td>${h.redo}</td>
        <td>${a.submitted}/${a.assigned}</td><td>${a.avg_score == null ? "—" : a.avg_score}</td>
      </tr>`;
    }).join("");
    return `<h3 style="margin:18px 0 4px;font-size:13px">Section ${esc(sec.section)} <span class="muted">· Class teacher: ${esc(sec.class_teacher || "—")} · ${sec.homework_count} homework · ${sec.assignment_count} assignments</span></h3>
      ${sec.students.length === 0
        ? `<p class="muted" style="padding:8px 0">No enrolled students.</p>`
        : `<table><thead><tr><th>Student</th><th style="width:70px">HW sub</th><th style="width:50px">Late</th><th style="width:60px">Verif.</th><th style="width:50px">Redo</th><th style="width:70px">ASG sub</th><th style="width:70px">Avg score</th></tr></thead><tbody>${rows}</tbody></table>`}`;
  }).join("");
  const body = `
    <div class="head">
      <div style="display:flex;align-items:center;gap:14px">${logo}<div>
        <h1>${esc(data.institution?.portal_name || data.institution?.name || "Monthly Report")}</h1>
        <h2>Monthly Activity Report · ${esc(data.class?.name || "")} · ${esc(monthLabel)}</h2>
      </div></div>
      <div class="badge">Generated ${new Date().toLocaleDateString()}</div>
    </div>
    <p class="muted" style="margin:4px 0 2px">Homework &amp; assignment items due within ${esc(monthLabel)}. "sub" = submitted / assigned.</p>
    ${sectionBlocks || `<p class="muted" style="padding:18px 0">No sections.</p>`}
    ${signatureRow(data.signers)}`;
  openPrintWindow(`Monthly Report — ${data.class?.name || ""} ${monthLabel}`, body);
}


function signatureRow(signers) {
  const s = signers || {};
  const person = (p, roleLabel) => {
    const img = p && p.signature
      ? `<img class="sigimg" src="${p.signature}" alt="signature" />`
      : `<div class="sigimg"></div>`;
    return `<div class="sigcol">
      ${img}
      <div class="sigline"></div>
      <div class="signame">${esc(p && p.name ? p.name : "")}</div>
      <div class="sigrole">${esc(roleLabel)}</div>
      ${p && p.fallback ? `<div class="sigfallback">(subject teacher)</div>` : ""}
    </div>`;
  };
  const seal = s.seal
    ? `<div class="sigcol sealcol"><img class="sealimg" src="${s.seal}" alt="school seal" /><div class="sigrole">School Seal</div></div>`
    : "";
  return `<div class="sigrow">
    ${person(s.class_teacher, "Class Teacher")}
    ${person(s.principal, (s.principal && s.principal.title) || "Principal")}
    ${seal}
  </div>`;
}

const fmtCode = (c) => (c && c.length === 8 ? `${c.slice(0, 4)}-${c.slice(4)}` : c);

function slipHtml({ school_name, student_name, admission_no, class: cls, code, expires_in_days }, setupUrl, logoSrc, compact) {
  const logo = logoSrc ? `<img src="${esc(logoSrc)}" alt="" class="slip-logo" />` : "";
  const adm = admission_no ? `<div class="slip-row"><span>Admission no.</span><b>${esc(admission_no)}</b></div>` : "";
  const how = admission_no
    ? "Enter this setup code (admission no. optional), your name and mobile number, then choose a password."
    : "Enter this setup code — <b>your code IS your identity</b> — plus your name and mobile number, then choose a password.";
  return `<div class="slip${compact ? " slip-compact" : ""}" data-testid="print-slip">
    <div class="slip-head">${logo}<div><div class="slip-school">${esc(school_name)}</div><div class="slip-sub">Parent app invitation</div></div></div>
    <div class="slip-row"><span>Student</span><b>${esc(student_name)}</b></div>
    <div class="slip-row"><span>Class</span><b>${esc(cls)}</b></div>${adm}
    <div class="slip-code-label">Setup code</div><div class="slip-code">${esc(fmtCode(code))}</div>
    <ol class="slip-steps"><li>Open <b>${esc(setupUrl)}</b></li><li>${how}</li><li>Sign in later with your mobile number.</li></ol>
    <div class="slip-foot">Single use · expires in ${esc(expires_in_days)} days · keep private</div>
  </div>`;
}

const SLIP_STYLES = `<style>
  @page { size: A4; margin: 8mm; }
  .slip { border: 1.5px dashed #475569; border-radius: 8px; padding: 14px 16px; font-family: Georgia, serif; color: #1a202c; max-width: 520px; margin: 0 auto 16px; }
  .slip-compact { max-width: none; margin: 0; height: 89mm; padding: 9px 12px; overflow: hidden; }
  .slip-head { display: flex; gap: 8px; align-items: center; border-bottom: 1.5px solid #1a202c; padding-bottom: 5px; margin-bottom: 6px; }
  .slip-logo { height: 30px; width: 30px; object-fit: contain; }
  .slip-school { font-size: 13px; font-weight: bold; }
  .slip-sub { font-size: 10px; color: #555; }
  .slip-row { display: flex; justify-content: space-between; font-size: 11px; padding: 1.5px 0; }
  .slip-row span { color: #718096; }
  .slip-code-label { font-size: 9px; text-transform: uppercase; letter-spacing: 0.1em; color: #718096; margin-top: 5px; }
  .slip-code { font-family: monospace; font-size: 22px; font-weight: bold; letter-spacing: 0.2em; text-align: center; border: 1px solid #cbd5e0; border-radius: 6px; padding: 4px; margin: 2px 0 5px; background: #f8fafc; }
  .slip-steps { font-size: 9.5px; margin-left: 14px; line-height: 1.45; }
  .slip-foot { font-size: 8.5px; color: #a0aec0; margin-top: 4px; }
  .sheet { display: grid; grid-template-columns: 1fr 1fr; gap: 4mm; page-break-after: always; break-after: page; }
  .sheet:last-child { page-break-after: auto; break-after: auto; }
  @media print { body { padding: 0 !important; } }
</style>`;

export function printParentSlip(data) {
  openPrintWindow(`Parent invite — ${data.student_name}`, SLIP_STYLES + slipHtml(data, data.setupUrl, data.logo_src, false));
}

export function printParentSlips(slips, setupUrl, logoSrc, title = "Parent invitation slips") {
  const pages = [];
  for (let i = 0; i < slips.length; i += 6) {
    pages.push(`<div class="sheet" data-testid="slip-sheet">${slips.slice(i, i + 6).map((s) => slipHtml(s, setupUrl, logoSrc, true)).join("")}</div>`);
  }
  openPrintWindow(title, SLIP_STYLES + pages.join(""));
}

export function printFeeReceipt({ payment: p, invoice: inv, school, admission_no }) {
  const money = (n) => `₹${Number(n || 0).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  const logo = school.logo_src ? `<img src="${esc(school.logo_src)}" alt="" style="height:54px;width:54px;object-fit:contain" />` : "";
  const items = (inv.items || []).map((i) => `<tr><td>${esc(i.title)}</td><td style="text-align:right">${money(i.amount)}</td></tr>`).join("");
  const extra = [
    inv.discount_amount ? `<tr><td>Discount</td><td style="text-align:right">− ${money(inv.discount_amount)}</td></tr>` : "",
    inv.fine_amount ? `<tr><td>Late fee</td><td style="text-align:right">${money(inv.fine_amount)}</td></tr>` : "",
  ].join("");
  const stamp = p.reversed ? `<div style="position:fixed;top:40%;left:12%;font-size:72px;color:rgba(220,38,38,.18);transform:rotate(-20deg);font-weight:bold">REVERSED</div>` : "";
  const body = `${stamp}
    <div class="head"><div style="display:flex;gap:12px;align-items:center">${logo}<div><h1>${esc(school.name)}</h1>
      <h2>${esc(school.address || "")}</h2></div></div>
      <div style="text-align:right"><div style="font-size:16px;font-weight:bold;letter-spacing:.08em">FEE RECEIPT</div>
      <div class="badge">No. <b>${esc(p.receipt_no)}</b></div><div class="muted">${esc((p.collected_at || "").slice(0, 10))}</div></div></div>
    <table style="margin-top:14px"><tr><th>Student</th><td>${esc(p.student_name)}</td><th>Admission no.</th><td>${esc(admission_no || "—")}</td></tr>
      <tr><th>Class</th><td>${esc(p.class_name || "")}${p.section ? ` ${esc(p.section)}` : ""}</td><th>Period</th><td>${esc(p.period_label || "")}${p.academic_year && !(p.period_label || "").includes(p.academic_year) ? ` · ${esc(p.academic_year)}` : ""}</td></tr></table>
    <table><tr><th>Fee head</th><th style="text-align:right">Amount</th></tr>${items}${extra}
      <tr class="totals"><td>Invoice total</td><td style="text-align:right">${money(inv.amount_due)}</td></tr>
      <tr class="totals"><td>Received now (${esc(p.method.toUpperCase())}${p.reference ? ` · ${esc(p.reference)}` : ""})</td><td style="text-align:right">${money(p.amount)}</td></tr>
      <tr><td>Balance remaining on this invoice</td><td style="text-align:right">${money(inv.balance)}</td></tr></table>
    ${p.reversed ? `<p style="color:#b91c1c;margin-top:8px;font-size:12px">Reversed ${esc((p.reversed_at || "").slice(0, 10))} · credit note ${esc(p.credit_note_no)} · ${esc(p.reverse_reason)}</p>` : ""}
    ${p.note ? `<p class="muted" style="margin-top:8px">Note: ${esc(p.note)}</p>` : ""}
    <div class="sig"><span>Collected by: ${esc(p.collected_by || "")}</span><span>Authorised signatory</span></div>
    <p class="muted" style="margin-top:18px">This is a system-generated receipt.</p>`;
  openPrintWindow(`Receipt ${p.receipt_no}`, body);
}

export function printDayBook(d) {
  const money = (n) => `₹${Number(n || 0).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  const logo = d.school.logo_src ? `<img src="${esc(d.school.logo_src)}" alt="" style="height:46px;width:46px;object-fit:contain" />` : "";
  const grp = (title, rows) => `<table style="width:32%;display:inline-table;margin-right:1%;vertical-align:top"><tr><th>${title}</th><th style="text-align:right">Count</th><th style="text-align:right">Total</th></tr>
    ${rows.map((r) => `<tr><td>${esc(String(r.key).toUpperCase() === r.key ? r.key : r.key)}</td><td style="text-align:right">${r.count}</td><td style="text-align:right">${money(r.total)}</td></tr>`).join("") || `<tr><td colspan="3" class="muted">None</td></tr>`}</table>`;
  const pays = d.payments.map((p) => `<tr><td>${esc(p.receipt_no)}</td><td>${esc((p.collected_at || "").slice(11, 16))}</td><td>${esc(p.student_name)}</td><td>${esc(p.class_name || "")} ${esc(p.section || "")}</td><td>${esc(p.period_label || "")}</td><td>${esc(p.method.toUpperCase())}${p.reference ? ` · ${esc(p.reference)}` : ""}</td><td>${esc(p.collected_by || "")}</td><td style="text-align:right">${money(p.amount)}</td></tr>`).join("");
  const rev = d.reversed.length ? `<p class="muted" style="margin-top:10px">Excluded — reversed: ${d.reversed.map((p) => `${esc(p.receipt_no)} (${money(p.amount)})`).join(", ")}</p>` : "";
  const body = `<div class="head"><div style="display:flex;gap:12px;align-items:center">${logo}<div><h1>${esc(d.school.name)}</h1><h2>Daily collection report (day book)</h2></div></div>
      <div style="text-align:right"><div class="badge">${esc(d.date)}</div><div style="font-size:18px;font-weight:bold;margin-top:4px">${money(d.summary.total)}</div><div class="muted">${d.summary.count} receipts</div></div></div>
    <div style="margin-top:12px">${grp("Method", d.by_method)}${grp("Collector", d.by_collector)}${grp("Class", d.by_class)}</div>
    <table><tr><th>Receipt</th><th>Time (UTC)</th><th>Student</th><th>Class</th><th>Period</th><th>Method</th><th>Collector</th><th style="text-align:right">Amount</th></tr>${pays || `<tr><td colspan="8" class="muted">No collections on this date.</td></tr>`}
      <tr class="totals"><td colspan="7">Total collected</td><td style="text-align:right">${money(d.summary.total)}</td></tr></table>${rev}
    <div class="sig"><span>Prepared by</span><span>Verified by (Principal / Accountant)</span></div>`;
  openPrintWindow(`Day book ${d.date}`, body);
}

const _money = (n) => `₹${Number(n || 0).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const _feeHead = (school, title, right) => {
  const logo = school?.logo_src ? `<img src="${esc(school.logo_src)}" alt="" style="height:46px;width:46px;object-fit:contain" />` : "";
  return `<div class="head"><div style="display:flex;gap:12px;align-items:center">${logo}<div><h1>${esc(school?.name || "")}</h1><h2>${esc(title)}</h2></div></div><div style="text-align:right">${right}</div></div>`;
};

export function printDefaulters(d, filterLabel) {
  const rows = d.rows.map((r, i) => `<tr><td>${i + 1}</td><td><strong>${esc(r.student_name)}</strong><br/><span class="muted">${esc(r.admission_no || "")}</span></td><td>${esc(r.class_name || "")} ${esc(r.section || "")}</td><td>${esc(r.parent_name || "")}<br/><span class="muted">${esc(r.parent_phone || "—")}</span></td><td>${esc(r.oldest_due_date)}</td><td style="text-align:right">${r.days_late}</td><td style="text-align:right">${_money(r.overdue_amount)}</td><td style="text-align:right">${_money(r.total_outstanding)}</td><td>${esc((r.last_reminder_at || "").slice(0, 10) || "—")}</td></tr>`).join("");
  const body = `${_feeHead(d.school, "Fee defaulters list", `<div class="badge">As of ${esc(d.as_of)}</div><div style="font-size:18px;font-weight:bold;margin-top:4px">${_money(d.totals.overdue)}</div><div class="muted">${d.totals.students} students overdue</div>`)}
    <p class="muted" style="margin-top:6px">${esc(filterLabel || "All classes")} · Ageing: 1-30 days ${d.buckets["1-30"]} · 31-60 days ${d.buckets["31-60"]} · 60+ days ${d.buckets["60+"]}</p>
    <table><tr><th>#</th><th>Student</th><th>Class</th><th>Parent / phone</th><th>Oldest due</th><th style="text-align:right">Days late</th><th style="text-align:right">Overdue</th><th style="text-align:right">Outstanding</th><th>Last reminder</th></tr>
      ${rows || `<tr><td colspan="9" class="muted">No defaulters for these filters.</td></tr>`}
      <tr class="totals"><td colspan="6">Total</td><td style="text-align:right">${_money(d.totals.overdue)}</td><td style="text-align:right">${_money(d.totals.outstanding)}</td><td></td></tr></table>
    <div class="sig"><span>Prepared by</span><span>Verified by (Principal / Accountant)</span></div>`;
  openPrintWindow(`Fee defaulters ${d.as_of}`, body);
}

export function printMonthlySummary(d) {
  const pct = (v) => (v === null || v === undefined ? "—" : `${v}%`);
  const tr = (r, cls = "") => `<tr class="${cls}"><td>${esc(r.class_name || "Total")}</td><td style="text-align:right">${r.invoices}</td><td style="text-align:right">${_money(r.gross)}</td><td style="text-align:right">${_money(r.concession)}</td><td style="text-align:right">${_money(r.billed)}</td><td style="text-align:right">${_money(r.collected)}</td><td style="text-align:right">${_money(r.prev_dues_collected)}</td><td style="text-align:right">${_money(r.outstanding)}</td><td style="text-align:right">${pct(r.collection_pct)}</td></tr>`;
  const methods = d.by_method.map((m) => `<tr><td>${esc(m.key.toUpperCase())}</td><td style="text-align:right">${m.count}</td><td style="text-align:right">${_money(m.total)}</td></tr>`).join("");
  const body = `${_feeHead(d.school, "Monthly fee collection summary", `<div class="badge">${esc(d.month)}</div><div style="font-size:18px;font-weight:bold;margin-top:4px">${_money(d.totals.collected)}</div><div class="muted">collected · ${d.totals.receipts} receipts</div>`)}
    <table><tr><th>Class</th><th style="text-align:right">Invoices</th><th style="text-align:right">Gross</th><th style="text-align:right">Concession</th><th style="text-align:right">Billed (net)</th><th style="text-align:right">Collected</th><th style="text-align:right">of which prev. dues</th><th style="text-align:right">Outstanding</th><th style="text-align:right">Collection %</th></tr>
      ${d.rows.map((r) => tr(r)).join("") || `<tr><td colspan="9" class="muted">No billing or collections this month.</td></tr>`}
      ${tr({ ...d.totals, class_name: "Grand total" }, "totals")}</table>
    <table style="width:45%;margin-top:14px"><tr><th>Payment method</th><th style="text-align:right">Receipts</th><th style="text-align:right">Total</th></tr>${methods || `<tr><td colspan="3" class="muted">None</td></tr>`}</table>
    <p class="muted" style="margin-top:8px">Billed = invoices due this month, net of concessions/waivers (shown separately, excluded from dues). Collected = all receipts dated this month (equals the sum of daily Day Books; reversed receipts excluded${d.reversed.count ? `: ${d.reversed.count} · ${_money(d.reversed.amount)}` : ""}); "of which prev. dues" = the part received against invoices due before this month, including carried-forward Previous dues. Outstanding and Collection % = this month's billing only.${d.totals.carried_forward ? ` Carried forward to next year: ${_money(d.totals.carried_forward)}.` : ""}</p>
    <div class="sig"><span>Accountant</span><span>Principal</span></div>`;
  openPrintWindow(`Monthly fee summary ${d.month}`, body);
}
