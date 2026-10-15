"""Idempotent mobile-app test data for the Sunrise demo school ONLY (never LPGS). Run: python scripts/seed_mobile_test.py"""
import asyncio
import io
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server as S  # noqa: E402
from reportlab.pdfgen import canvas  # noqa: E402

db = S.db
SLUG = "sunrise"
TAG = "mobile_seed_v1"
AY = "2026-27"
PARENT2 = ("mobile.parent@sunrise-demo.in", "Sunrise@2026", "Kavya Rao")
TEACH = {k: None for k in ("lakshmi", "rahul", "suresh", "sindhu", "fathima", "deepa", "anitha")}


def uid():
    return str(uuid.uuid4())


async def upsert(col, key, doc):
    """Insert once (matched by key); returns the stored doc. Never duplicates."""
    ex = await db[col].find_one(key, {"_id": 0})
    if ex:
        return ex, False
    doc = {"id": uid(), "created_at": S.now_iso(), "seed": TAG, **key, **doc}
    await db[col].insert_one(dict(doc))
    return doc, True


def pdf_bytes():
    b = io.BytesIO()
    c = canvas.Canvas(b)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(72, 760, "Sunrise Public School - Sports Day Circular")
    c.setFont("Helvetica", 12)
    for i, line in enumerate(["Sports Day is on Saturday. Students report at 8:30 am in house colours.",
                              "Parents are welcome from 10 am. Please send a water bottle and cap.",
                              "(Demo circular for mobile-app testing.)"]):
        c.drawString(72, 720 - i * 20, line)
    c.save()
    return b.getvalue()


async def main():
    inst = await db.institutions.find_one({"slug": SLUG}, {"_id": 0})
    assert inst and inst["code"] == "SPS", "Sunrise not found"
    iid = inst["id"]
    log = []
    tz = ZoneInfo("Asia/Kolkata")
    today = datetime.now(tz).date()
    d = lambda n: (today + timedelta(days=n)).isoformat()  # noqa: E731
    users = {u["email"].split("@")[0]: u for u in await db.users.find({"institution_id": iid}, {"_id": 0, "password_hash": 0}).to_list(100)}
    for k in TEACH:
        TEACH[k] = users[k if k != "anitha" else "admin"]
    admin = TEACH["anitha"]

    # UPI must be enabled with a demo VPA
    upi = inst.get("upi") or {}
    if not (upi.get("enabled") and upi.get("vpa")):
        await db.institutions.update_one({"id": iid}, {"$set": {"upi": {**upi, "enabled": True, "vpa": "sunrisepublic@okhdfc",
                                                                        "payee_name": "Sunrise Public School"}}})
        log.append("UPI enabled")

    p1 = await db.users.find_one({"email": "parent.menon@sunrise-demo.in", "institution_id": iid}, {"_id": 0})
    aarav = await db.students.find_one({"institution_id": iid, "admission_no": "SPS-001"}, {"_id": 0})

    # ---- second parent + two fictional siblings ----
    sibs = []
    for first, cls, sec, dob, gender in (("Ishaan", "Grade 5", "A", "2016-06-21", "male"), ("Anika", "Grade 8", "A", "2013-09-03", "female")):
        st = await db.students.find_one({"institution_id": iid, "first_name": first, "last_name": "Rao", "seed": TAG}, {"_id": 0})
        if not st:
            prefix, taken = await S._adm_ctx(iid)
            st = {"id": uid(), "institution_id": iid, "first_name": first, "last_name": "Rao", "admission_no": S._next_adm(prefix, cls, taken),
                  "class_name": cls, "section": sec, "guardian_name": PARENT2[2], "guardian_email": PARENT2[0], "gender": gender,
                  "date_of_birth": dob, "status": "active", "enrollment_status": "enrolled", "academic_year": AY,
                  "created_at": S.now_iso(), "seed": TAG}
            await db.students.insert_one(dict(st))
            log.append(f"student {first} Rao {st['admission_no']} ({cls} {sec})")
        await upsert("enrollments", {"institution_id": iid, "student_id": st["id"], "academic_year": AY},
                     {"student_name": f"{first} Rao", "admission_no": st["admission_no"], "class_name": cls, "section": sec})
        sibs.append(st)
    ishaan, anika = sibs
    p2 = await db.users.find_one({"email": PARENT2[0]}, {"_id": 0})
    if not p2:
        p2 = {"id": uid(), "name": PARENT2[2], "email": PARENT2[0], "role": "parent", "institution_id": iid, "status": "active",
              "relation": "Mother", "created_at": S.now_iso(), "seed": TAG}
        await db.users.insert_one({**p2, "password_hash": S.hash_password(PARENT2[1])})
        log.append(f"parent {PARENT2[0]}")
    await db.users.update_one({"id": p2["id"]}, {"$set": {"password_hash": S.hash_password(PARENT2[1]), "must_change_password": False,
                                                          "status": "active", "student_ids": [ishaan["id"], anika["id"]]}})
    for st in sibs:
        await db.students.update_one({"id": st["id"]}, {"$set": {"parent_user_id": p2["id"]}})

    # ---- fees: one unpaid (due in 7 days) + one overdue, no proofs ----
    structs = {s["name"]: s["id"] for s in await db.fee_structures.find({"institution_id": iid}, {"_id": 0, "id": 1, "name": 1}).to_list(20)}
    fee_plan = [(aarav, 4500.0, 1200.0), (anika, 4500.0, 1200.0), (ishaan, 3200.0, 800.0)]
    for st, amt, od in fee_plan:
        sid_struct = structs["High School fees 2026-27" if st["class_name"] != "Grade 5" else "Primary fees 2026-27"]
        acc, _ = await upsert("fee_accounts", {"institution_id": iid, "student_id": st["id"], "academic_year": AY},
                              {"student_name": f"{st['first_name']} {st['last_name']}", "admission_no": st["admission_no"],
                               "class_name": st["class_name"], "section": st["section"], "structure_id": sid_struct,
                               "included_head_ids": [], "discount": None, "discount_used": 0.0, "status": "active"})
        for label, title, total, due, status in (("Term 4", "Term 4 fee", amt, d(7), "pending"),
                                                 ("Activity fee", "Activity & sports fee", od, d(-10), "overdue")):
            _, new = await upsert("fee_invoices", {"institution_id": iid, "account_id": acc["id"], "period_label": label},
                                  {"frequency": "term", "structure_id": acc["structure_id"], "student_id": st["id"],
                                   "student_name": f"{st['first_name']} {st['last_name']}", "class_name": st["class_name"],
                                   "section": st["section"], "academic_year": AY, "items": [{"head_id": None, "title": title, "amount": total}],
                                   "subtotal": total, "discount_amount": 0.0, "fine_amount": 0.0, "fine_applied": False, "total": total,
                                   "paid_amount": 0.0, "due_date": due, "status": status, "generated_at": S.now_iso(),
                                   "generated_by": "admin@sunrise-demo.in"})
            if new:
                log.append(f"invoice {st['first_name']}: {label} ₹{total:,.0f} due {due}")

    # ---- homework (due tomorrow + overdue) and one assignment ----
    hw_plan = [("Grade 8", "A", "Science", TEACH["deepa"], "Science: label a plant cell diagram", d(1)),
               ("Grade 8", "A", "Mathematics", TEACH["lakshmi"], "Maths: Exercise 7.2 (linear equations)", d(-2)),
               ("Grade 5", "A", "English", TEACH["fathima"], "English: write 10 sentences about your pet", d(1))]
    for cls, sec, subj, t, title, due in hw_plan:
        _, new = await upsert("homework", {"institution_id": iid, "class_name": cls, "section": sec, "title": title},
                              {"academic_year": AY, "subject": subj, "teacher_id": t["id"], "instructions": "Complete in your notebook.",
                               "attachments": [], "due_date": due, "status": "open"})
        log += [f"homework {cls}{sec}: {title} (due {due})"] if new else []
    _, new = await upsert("assignments", {"institution_id": iid, "class_name": "Grade 8", "section": "A", "title": "Science project: water filter model"},
                          {"academic_year": AY, "subject": "Science", "teacher_id": TEACH["deepa"]["id"],
                           "instructions": "Build a simple water filter and submit a photo with a short write-up.",
                           "attachments": [], "due_date": f"{d(5)}T17:00:00+05:30", "status": "open", "max_marks": 20,
                           "counts_toward_report": True})
    log += [f"assignment Grade 8A due {d(5)}"] if new else []

    # ---- notices (today + yesterday, one with a PDF) ----
    yday = (datetime.now(tz) - timedelta(days=1)).astimezone(ZoneInfo("UTC")).isoformat()
    n1, new1 = await upsert("notices", {"institution_id": iid, "title": "Sports Day circular"},
                            {"body": "Sports Day is this Saturday. Please see the attached circular.", "status": "published",
                             "target": {"scope": "school", "division_ids": [], "classes": []}, "attachments": [],
                             "author_id": admin["id"], "author_name": admin["name"]})
    if not n1.get("attachments"):
        path = f"lnmo/notices/{n1['id']}/{uid()}.pdf"
        data = pdf_bytes()
        S._put_object(path, data, "application/pdf")
        await db.notices.update_one({"id": n1["id"]}, {"$set": {"attachments": [
            {"path": path, "name": "sports-day-circular.pdf", "size": len(data), "type": "application/pdf"}]}})
        log.append("notice with PDF (today)")
    _, new = await upsert("notices", {"institution_id": iid, "title": "Half-day on Friday (staff meeting)"},
                          {"body": "School closes at 12:15 pm on Friday. Buses leave at 12:30 pm.", "status": "published",
                           "target": {"scope": "school", "division_ids": [], "classes": []}, "attachments": [],
                           "author_id": admin["id"], "author_name": admin["name"], "created_at": yday})
    log += ["notice (yesterday)"] if new else []

    # ---- today's cover: one substitute assigned + one needs cover (Aarav's later periods) ----
    dow = today.strftime("%a").lower()[:3]
    tt = {e["period_no"]: e for e in await db.timetable_entries.find(
        {"institution_id": iid, "class_name": "Grade 8", "section": "A", "day": dow, "status": "active"}, {"_id": 0}).to_list(20)}
    later = sorted(tt)[-2:]
    for pno, sub in zip(later, ("open", "assigned")):
        e = tt[pno]
        ab, _ = await upsert("absences", {"institution_id": iid, "teacher_id": e["teacher_id"], "date": today.isoformat(), "status": "approved"},
                             {"teacher_name": e["teacher_name"], "academic_year": AY, "reason": "Personal leave", "requested_by": admin["id"], "approved_by": admin["id"], "kept_periods": []})
        extra = {"substitute_teacher_id": TEACH["sindhu"]["id"], "substitute_name": TEACH["sindhu"]["name"], "assigned_at": S.now_iso()} \
            if sub == "assigned" else {"substitute_teacher_id": None, "substitute_name": None}
        _, new = await upsert("substitutions", {"institution_id": iid, "date": today.isoformat(), "class_name": "Grade 8", "section": "A", "period_no": pno, "absence_id": ab["id"]},
                              {"day": dow, "academic_year": AY, "subject": e["subject"],
                               "original_teacher_id": e["teacher_id"], "original_entry_id": e["id"], "status": sub,
                               "requested_teacher_ids": [], "responses": {}, "assigned_by": admin["id"], **extra})
        log += [f"cover {today} P{pno} {e['subject']}: {sub}"] if new else []

    # ---- attendance this month (absent/late days) — PAST days only, finalized. Today is left unmarked so teachers can test marking. ----
    special = {aarav["id"]: {3: "absent", 6: "late", 9: "absent", 12: "late"},
               anika["id"]: {5: "late", 8: "absent"}, ishaan["id"]: {6: "absent", 10: "late", 13: "late"}}
    for cls, sec, marker in (("Grade 8", "A", "lakshmi"), ("Grade 5", "A", "fathima")):
        roster = [s["id"] for s in await db.students.find({"institution_id": iid, "class_name": cls, "section": sec, "status": {"$ne": "inactive"}}, {"_id": 0, "id": 1}).to_list(100)]
        for day in range(1, today.day):
            dt = today.replace(day=day)
            if dt.weekday() == 6 or (dt.month == 10 and day == 2):
                continue
            ds = dt.isoformat()
            sh = await db.attendance.find_one({"institution_id": iid, "class_name": cls, "section": sec, "date": ds}, {"_id": 0})
            if not sh:
                sh = {"id": uid(), "institution_id": iid, "class_name": cls, "section": sec, "date": ds, "entries": {}, "finalized": True,
                      "marked_by": f"{marker}@sunrise-demo.in", "created_at": S.now_iso(), "updated_at": S.now_iso(), "seed": TAG}
                await db.attendance.insert_one(dict(sh))
            sets = {f"entries.{s}": special.get(s, {}).get(day, "present") for s in roster
                    if s not in sh["entries"] or (s in special and day in special[s])}
            if sets:
                await db.attendance.update_one({"id": sh["id"]}, {"$set": sets})
    log.append(f"attendance {today.strftime('%B')} 1–{today.day - 1} (past days) for Grade 8A + Grade 5A; today left unmarked")

    # ---- upcoming exam (next 10 days) + one published result ----
    units = {u["name"]: u["id"] for u in await db.academic_units.find({"institution_id": iid}, {"_id": 0}).to_list(10)}
    ex, new = await upsert("exams", {"institution_id": iid, "name": "Unit Test 2 — October 2026"},
                           {"academic_year": AY, "type": "unit", "status": "published", "created_by": admin["id"], "published_at": S.now_iso(),
                            "division_configs": [{"academic_unit_id": units[u], "date_start": d(4), "date_end": d(6),
                                                  "slots_per_day": [{"start": "09:30", "end": "11:00", "label": "Morning"}]} for u in units]})
    for cls, subj, day in (("Grade 8", "Mathematics", 4), ("Grade 8", "Science", 6), ("Grade 5", "English", 4), ("Grade 5", "Mathematics", 6)):
        unit = units["High School" if cls == "Grade 8" else "Primary"]
        await upsert("exam_entries", {"institution_id": iid, "exam_id": ex["id"], "class_name": cls, "subject": subj},
                     {"academic_year": AY, "academic_unit_id": unit, "section": "", "date": d(day), "slot_index": 0,
                      "start": "09:30", "end": "11:00", "room": "", "status": "scheduled", "original_date": None, "original_slot": None})
    log += [f"exam Unit Test 2 ({d(4)}–{d(6)})"] if new else []
    for cls, subj, scores in (("Grade 8", "Mathematics", {aarav["id"]: 42, anika["id"]: 45}), ("Grade 5", "English", {ishaan["id"]: 38})):
        a, new = await upsert("assessments", {"institution_id": iid, "name": f"Unit Test 1 — {subj}", "class_name": cls},
                              {"academic_year": AY, "subject": subj, "section": "", "max_marks": 50, "theory_max_marks": 50,
                               "practical_max_marks": 0, "has_practical": False, "status": "published", "exam_date": d(-9)})
        for sid, sc in scores.items():
            await upsert("marks", {"institution_id": iid, "assessment_id": a["id"], "student_id": sid},
                         {"score": float(sc), "status": "present", "updated_at": S.now_iso()})
        log += [f"result {cls} Unit Test 1 — {subj} (published)"] if new else []

    # ---- chat: class teacher Lakshmi -> Priya Menon, 2 messages (second unread) ----
    lk = TEACH["lakshmi"]
    t, new = await upsert("parent_threads", {"institution_id": iid, "parent_id": p1["id"], "student_id": aarav["id"], "subject": "Science project materials"},
                          {"parent_name": p1["name"], "student_name": "Aarav Menon", "class_name": "Grade 8", "section": "A",
                           "target": "class_teacher", "status": "open", "created_by": lk["id"]})
    if new:
        now = datetime.now(ZoneInfo("UTC"))
        m1_at, read_at, m2_at = (now - timedelta(hours=3)).isoformat(), (now - timedelta(hours=2)).isoformat(), (now - timedelta(minutes=20)).isoformat()
        msgs = [("Hello! Aarav needs two plastic bottles and some sand for Monday's science project.", m1_at),
                ("Also, please sign the permission slip in his diary for the field visit. Thank you!", m2_at)]
        for body, at in msgs:
            await db.parent_messages.insert_one({"id": uid(), "thread_id": t["id"], "institution_id": iid, "sender_id": lk["id"],
                                                 "sender_role": "staff", "sender_name": lk["name"], "sender_title": "Class teacher",
                                                 "body": body, "attachment": None, "hidden": False, "created_at": at, "seed": TAG})
        await db.parent_threads.update_one({"id": t["id"]}, {"$set": {"last_message_at": m2_at, "last_message_preview": msgs[1][0][:120],
                                                                      "last_sender_role": "staff", "reads": {lk["id"]: m2_at, p1["id"]: read_at}}})
        await S._notify(iid, p1["id"], "parent_message", "New message about Aarav Menon", f"{lk['name']}: {msgs[1][0][:80]}", t["id"])
        log.append("chat thread Lakshmi → Priya (1 unread)")

    # ---- clear login locks ----
    cleared = 0
    for u in (p1, p2):
        full = await db.users.find_one({"id": u["id"]}, {"_id": 0})
        cleared += (await db.login_attempts.delete_many({"identifier": {"$in": await S._account_lock_keys(full)}})).deleted_count
    log.append(f"login locks cleared: {cleared}")
    await S.audit(admin, "seed_mobile_test_data", "institution", iid, TAG, iid)
    print("\n".join(log) or "nothing new")


asyncio.run(main())
