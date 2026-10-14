"""Production factory reset: explicit collection classification, backup export and resumable deletion."""
import gzip
import re

from bson import json_util

PLATFORM_ROLES = ["platform_admin", "super_admin"]

KEEP = {
    "plans": "Subscription plans",
    "platform_config": "Messaging provider config",
    "platform_settings": "Platform branding / LNMO logo",
    "platform_curriculum_templates": "Platform curriculum templates (SCERT)",
    "platform_events": "Reset audit trail (kept)",
}

# Collections where only some documents are school data: filter = docs to DELETE.
PARTIAL = {
    "users": ({"role": {"$nin": PLATFORM_ROLES}}, "Keeps platform manager accounts only"),
    "comm_templates": ({"institution_id": {"$ne": None}}, "Keeps LNMO global templates (institution_id null)"),
    "platform_library": ({"submitted_by_school": {"$nin": [None, "", False]}}, "Keeps platform-owned library items"),
}

DELETE = {
    "institutions": "Schools", "academic_configuration": "Academic config", "academic_units": "Divisions",
    "academic_years": "Academic years", "classes": "Classes", "sections": "Sections", "subjects": "Subjects",
    "subject_offerings": "Subject offerings", "subject_requirements": "Subject requirements", "enrollments": "Enrollments",
    "students": "Students", "teachers": "Legacy teacher records", "teacher_assignments": "Teacher assignments",
    "principal_assignments": "Principal assignments", "timetable_entries": "Timetable", "timetable_configs": "Timetable configs",
    "timetable_batches": "Timetable batches", "absences": "Teacher absences", "substitutions": "Substitutions",
    "attendance": "Attendance", "homework": "Homework", "homework_submissions": "Homework submissions",
    "assignments": "Assignments", "assignment_submissions": "Assignment submissions", "assessments": "Assessments",
    "exams": "Exams", "exam_entries": "Exam entries", "marks": "Marks", "mark_changes": "Mark history",
    "achievements": "Achievements", "notices": "Notices", "notifications": "In-app notifications",
    "curricula": "School curricula", "curriculum_items": "Curriculum items", "curriculum_comments": "Curriculum comments",
    "tutor_messages": "AI tutor chats", "student_memory": "AI tutor memory", "promotion_runs": "Promotion runs",
    "promotion_decisions": "Promotion decisions", "fee_structures": "Fee structures", "fee_accounts": "Fee accounts",
    "fee_invoices": "Invoices", "fee_payments": "Payments", "fee_payment_proofs": "Payment proofs", "fee_issues": "Fee issues",
    "fee_counters": "Receipt counters", "fee_reminders": "Fee reminders", "reminders_sent": "Reminder de-dup keys",
    "messages": "Communication history", "credit_requests": "Message credit requests", "parent_invites": "Parent invites",
    "parent_invite_reminders": "Invite reminders", "parent_invite_reviews": "Invite reviews", "parent_setup_codes": "Parent setup codes",
    "otp_codes": "OTP codes", "password_resets": "Password reset links", "login_attempts": "Login lockouts",
    "audit_logs": "Audit logs", "issues": "Support tickets & crash reports",
}

CLASSIFIED = set(KEEP) | set(PARTIAL) | set(DELETE)
STORAGE_PATH = re.compile(r"^[a-z0-9_-]+/(?!platform-brand/|resets/)[^\s]+\.[a-z0-9]{2,5}$", re.I)


async def build_plan(db) -> list:
    names = sorted(n for n in await db.list_collection_names() if not n.startswith("system."))
    out = []
    for n in sorted(set(names) | CLASSIFIED):
        total = await db[n].count_documents({}) if n in names else 0
        if n in KEEP:
            out.append({"collection": n, "action": "keep", "note": KEEP[n], "total": total, "delete": 0, "filter": None})
        elif n in PARTIAL:
            f, note = PARTIAL[n]
            out.append({"collection": n, "action": "partial", "note": note, "total": total,
                        "delete": await db[n].count_documents(f) if total else 0, "filter": f})
        elif n in DELETE:
            out.append({"collection": n, "action": "delete", "note": DELETE[n], "total": total, "delete": total, "filter": {}})
        else:
            f = {"institution_id": {"$exists": True}}
            out.append({"collection": n, "action": "unclassified", "total": total, "filter": f,
                        "note": "Unknown collection: only documents with institution_id are deleted",
                        "delete": await db[n].count_documents(f)})
    return out


def _walk_paths(v, acc):
    if isinstance(v, dict):
        for x in v.values():
            _walk_paths(x, acc)
    elif isinstance(v, list):
        for x in v:
            _walk_paths(x, acc)
    elif isinstance(v, str) and STORAGE_PATH.match(v):
        acc.add(v)


async def build_backup(db, plan: list):
    """Gzipped Extended-JSON of every document that the reset would delete → (bytes, counts, storage_paths)."""
    data, counts, paths = {}, {}, set()
    for p in plan:
        if not p["delete"]:
            continue
        docs = await db[p["collection"]].find(p["filter"]).to_list(None)
        data[p["collection"]] = docs
        counts[p["collection"]] = len(docs)
        for d in docs:
            _walk_paths(d, paths)
    raw = json_util.dumps({"format": "lnmo-reset-backup-v1", "collections": data}, json_options=json_util.RELAXED_JSON_OPTIONS)
    return gzip.compress(raw.encode()), counts, sorted(paths)


async def delete_step(db, p: dict) -> int:
    r = await db[p["collection"]].delete_many(p["filter"])
    return r.deleted_count
