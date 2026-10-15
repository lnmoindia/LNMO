# Phase M3: mobile push notifications (Expo Push API) — a NEW real channel next to the STUB SMS/WhatsApp.
# * Tokens: db.push_tokens; per-user category preferences: db.push_preferences.
# * Hooked into the EXISTING in-app bell (server._notify → server._push("notify", ...)), so every event that already
#   rings the bell for a mobile role (parent / student / teacher) also pushes — no duplicated event logic.
#   Students + parents of a section get a push-only "cover today" alert from the substitution assign/cancel sites.
# * Sending is fire-and-forget (background tasks): API responses never wait on Expo.
# * Every push is logged in the existing message history (db.messages) with channel "push" + status.
import asyncio
import logging
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field

import server as S

api, db = S.api, S.db
log = logging.getLogger("lnmo.push")

EXPO_SEND_URL = "https://exp.host/--/api/v2/push/send"
EXPO_RECEIPTS_URL = "https://exp.host/--/api/v2/push/getReceipts"
RECEIPT_DELAY_S = 60          # Expo receipts are usually ready within a minute
CHAT_COLLAPSE_S = 60          # at most one chat push per thread per recipient per minute
BATCH = 100                   # Expo limit per request
RETRY_BASE_S = 1.0            # 429/5xx backoff: 1s, 2s, 4s
MOBILE_ROLES = ("parent", "student", "teacher")
TOKEN_RE = re.compile(r"^(ExponentPushToken|ExpoPushToken)\[[A-Za-z0-9_\-:.]{6,200}\]$")

CATEGORIES = {  # key → (label, roles that see the toggle)
    "messages": ("Messages", ("parent", "teacher")),
    "fees": ("Fees", ("parent",)),
    "homework": ("Homework", ("parent", "student")),
    "notices": ("Notices", ("parent", "student", "teacher")),
    "timetable": ("Timetable changes", ("parent", "student")),
    "teacher_covers": ("Cover requests", ("teacher",)),
}
TYPE_CATEGORY = {
    "parent_message": "messages",
    "fee_reminder": "fees", "fee_payment_proof": "fees",
    "notice_new": "notices",
    "homework_new": "homework", "assignment_new": "homework",
    "homework_redo": "homework", "assignment_redo": "homework", "homework_verified": "homework", "assignment_verified": "homework",
    "timetable_change": "timetable",
    "sub_requested": "teacher_covers", "sub_assigned": "teacher_covers", "sub_cancelled": "teacher_covers",
    "absence_approved": "teacher_covers", "absence_rejected": "teacher_covers", "absence_cancelled": "teacher_covers",
}
ANDROID_CHANNEL = {"messages": "messages", "fees": "fees", "homework": "school", "notices": "school",
                   "timetable": "school", "teacher_covers": "teacher", "test": "school"}

_tasks: set = set()


def _spawn(coro):
    t = asyncio.get_running_loop().create_task(coro)
    _tasks.add(t)
    t.add_done_callback(_tasks.discard)
    return t


async def drain():
    """Wait for in-flight push tasks (tests + graceful shutdown)."""
    while _tasks:
        await asyncio.gather(*list(_tasks), return_exceptions=True)


def _short(text, n):
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


# ---------------- Expo HTTP (retries on 429 / 5xx / network) ----------------
async def _http_post(url, payload):
    headers = {"Accept": "application/json", "Accept-Encoding": "gzip, deflate", "Content-Type": "application/json"}
    if os.environ.get("EXPO_ACCESS_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['EXPO_ACCESS_TOKEN']}"
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post(url, json=payload, headers=headers)
    try:
        body = r.json()
    except ValueError:
        body = {"errors": [{"code": "BAD_RESPONSE", "message": r.text[:200]}]}
    return r.status_code, body


async def _post_retry(url, payload, attempts=4):
    delay, last = RETRY_BASE_S, None
    for i in range(attempts):
        try:
            code, body = await _http_post(url, payload)
            if code != 429 and code < 500:
                return code, body
            last = f"HTTP {code}"
        except httpx.HTTPError as e:
            last = f"{type(e).__name__}: {e}"
        if i < attempts - 1:
            await asyncio.sleep(delay)
            delay *= 2
    return 0, {"errors": [{"code": "UNAVAILABLE", "message": last or "Expo push service unavailable"}]}


async def _deactivate(token, reason):
    await db.push_tokens.update_many({"token": token}, {"$set": {"active": False, "deactivated_reason": reason,
                                                                  "deactivated_at": S.now_iso()}})


async def send_messages(items):
    """items: [{"msg": expo message dict, "log": message-history doc}] → stores history, returns ticket statuses."""
    out, done = [], []
    for i in range(0, len(items), BATCH):
        chunk = items[i:i + BATCH]
        code, body = await _post_retry(EXPO_SEND_URL, [x["msg"] for x in chunk])
        tickets = body.get("data") if isinstance(body.get("data"), list) else None
        if not tickets and len(chunk) > 1:  # whole request rejected (e.g. mixed projects) → retry one by one
            done += [o for x in chunk for o in await send_messages([x])]
            continue
        req_err = None if tickets else ((body.get("errors") or [{}])[0].get("message") or f"HTTP {code}")
        for j, x in enumerate(chunk):
            t = (tickets[j] if tickets and j < len(tickets) else {"status": "error", "message": req_err})
            ok = t.get("status") == "ok"
            err_code = (t.get("details") or {}).get("error")
            doc, now = x["log"], S.now_iso()
            doc.update({"status": "sent" if ok else "failed", "error": None if ok else _short(t.get("message") or err_code, 300),
                        "status_history": [{"status": "queued", "at": doc["created_at"]}, {"status": "sent" if ok else "failed", "at": now}]})
            doc["meta"].update({"ticket_id": t.get("id"), "expo_error": err_code})
            await db.messages.insert_one(dict(doc))
            if err_code == "DeviceNotRegistered":
                await _deactivate(x["msg"]["to"], "DeviceNotRegistered")
            out.append({"message_id": doc["id"], "status": doc["status"], "error": doc["error"], "ticket_id": t.get("id"),
                        "_token": x["msg"]["to"]})
    pending = [o for o in out if o["ticket_id"]]
    if pending:
        _spawn(_check_receipts(pending))
    return [{k: v for k, v in o.items() if k != "_token"} for o in out] + done


async def _check_receipts(rows, delay=None):
    await asyncio.sleep(RECEIPT_DELAY_S if delay is None else delay)
    ids = [r["ticket_id"] for r in rows]
    code, body = await _post_retry(EXPO_RECEIPTS_URL, {"ids": ids})
    receipts = body.get("data") if isinstance(body.get("data"), dict) else {}
    for r in rows:
        rc = receipts.get(r["ticket_id"])
        if not rc:
            continue
        ok = rc.get("status") == "ok"
        err_code = (rc.get("details") or {}).get("error")
        st = "delivered" if ok else "failed"
        await db.messages.update_one({"id": r["message_id"]}, {
            "$set": {"status": st, "error": None if ok else _short(rc.get("message") or err_code, 300), "meta.receipt_error": err_code},
            "$push": {"status_history": {"status": st, "at": S.now_iso()}}})
        if err_code == "DeviceNotRegistered":
            await _deactivate(r["_token"], "DeviceNotRegistered")


# ---------------- preferences, routing, badge ----------------
async def get_prefs(uid):
    d = await db.push_preferences.find_one({"user_id": uid}, {"_id": 0}) or {}
    return {k: bool((d.get("prefs") or {}).get(k, True)) for k in CATEGORIES}


async def _route(user, ntype, related_id, extra):
    """Deep-link payload for the mobile app (expo-router paths), per recipient role."""
    role, rid, d = user["role"], related_id, {}
    if ntype == "parent_message":
        t = await db.parent_threads.find_one({"id": rid}, {"_id": 0, "student_id": 1}) or {}
        d = {"route": f"/thread/{rid}", "thread_id": rid, "student_id": t.get("student_id") if role == "parent" else None}
    elif ntype in ("fee_reminder", "fee_payment_proof"):
        inv = await db.fee_invoices.find_one({"id": rid}, {"_id": 0, "student_id": 1})
        iss = None if inv else await db.fee_issues.find_one({"id": rid}, {"_id": 0, "student_id": 1})
        d = {"route": f"/invoice/{rid}" if inv else (f"/issue/{rid}" if iss else "/fees"),
             "student_id": (inv or iss or {}).get("student_id")}
    elif ntype == "notice_new":
        d = {"route": "/more/notices", "notice_id": rid}
    elif ntype in ("homework_new", "assignment_new", "homework_redo", "assignment_redo", "homework_verified", "assignment_verified"):
        kind = ntype.split("_")[0]
        if role == "student":
            d = {"route": f"/student/work/{kind}/{rid}"}
        else:
            item = await db[kind if kind == "homework" else "assignments"].find_one({"id": rid}, {"_id": 0, "class_name": 1, "section": 1}) or {}
            kid = await db.students.find_one({"id": {"$in": user.get("student_ids") or []}, "class_name": item.get("class_name"),
                                              "section": item.get("section")}, {"_id": 0, "id": 1}) or {}
            d = {"route": "/more/homework", "student_id": kid.get("id")}
    elif ntype == "timetable_change":
        d = {"route": "/student/timetable" if role == "student" else "/timetable", "student_id": (extra or {}).get("student_id")}
    elif TYPE_CATEGORY.get(ntype) == "teacher_covers":
        d = {"route": "/teacher/more/substitutions", "substitution_id": rid}
    return {k: v for k, v in d.items() if v}


async def badge_for(user):
    n = await db.notifications.count_documents({"user_id": user["id"], "read": False, "type": {"$ne": "parent_message"}})
    if user["role"] in ("parent", "teacher"):
        try:
            import phase58
            n += (await phase58.chat_unread(user=user))["unread"]
        except Exception:  # never let the badge break a push
            pass
    return n


async def _collapse(uid, thread_id):
    """True if a chat push for this thread went to this user in the last CHAT_COLLAPSE_S seconds."""
    key, now = f"{uid}:{thread_id}", datetime.now(timezone.utc)
    cutoff = (now - timedelta(seconds=CHAT_COLLAPSE_S)).isoformat()
    r = await db.push_throttle.update_one({"key": key, "at": {"$lt": cutoff}}, {"$set": {"at": now.isoformat()}})
    if r.matched_count:
        return False
    try:
        await db.push_throttle.insert_one({"key": key, "at": now.isoformat()})
        return False
    except Exception:  # duplicate key → a recent push exists
        return True


async def deliver(iid, uid, ntype, title, body, related_id=None, extra=None, force_category=None):
    """Push one event to all active devices of one user (respects role, prefs, institution scope, chat collapse)."""
    try:
        category = force_category or TYPE_CATEGORY.get(ntype)
        if not category or not uid:
            return []
        user = await db.users.find_one({"id": uid, "institution_id": iid}, {"_id": 0, "password_hash": 0})
        if not user or (user["role"] not in MOBILE_ROLES and category != "test"):
            return []
        if category != "test" and not (await get_prefs(uid)).get(category, True):
            return []
        tokens = await db.push_tokens.find({"user_id": uid, "institution_id": iid, "active": True}, {"_id": 0}).to_list(20)
        if not tokens:
            return []
        if category == "messages" and related_id and await _collapse(uid, related_id):
            return []
        data = {"type": ntype, "category": category, **(await _route(user, ntype, related_id, extra) if category != "test" else {"route": ""})}
        badge = await badge_for(user)
        title, text = _short(title, 80), _short(body, 140)
        items = []
        for t in tokens:
            now = S.now_iso()
            msg = {"to": t["token"], "title": title, "body": text, "data": data, "sound": "default", "priority": "high",
                   "channelId": ANDROID_CHANNEL.get(category, "school"), "badge": badge}
            doc = {"id": str(uuid.uuid4()), "institution_id": iid, "channel": "push", "direction": "outbound", "provider": "expo",
                   "recipient_name": user.get("name"), "recipient_phone": None, "recipient_user_id": uid,
                   "body": f"{title}: {text}", "module": category, "status": "queued", "created_at": now,
                   "meta": {"type": ntype, "related_id": related_id, "route": data.get("route"), "platform": t.get("platform"),
                            "token_tail": t["token"][-9:-1]}}
            items.append({"msg": msg, "log": doc})
        return await send_messages(items)
    except Exception:
        log.exception("push deliver failed (%s → %s)", ntype, uid)
        return []


# ---------------- hooks called from server.py ----------------
async def _section_cover(iid, sub, kind):
    """Cover assigned / cancelled for TODAY → push-only to the section's students + parents (category timetable)."""
    today = (await S._sub_now(iid)).date().isoformat()
    if sub.get("date") != today:
        return
    who = f"P{sub.get('period_no')} {sub.get('subject') or ''}".strip()
    if kind == "assigned":
        title, body = "Substitute teacher today", f"{who}: {sub.get('substitute_name') or 'a substitute'} is covering"
    elif kind == "removed":
        title, body = "Timetable change today", f"{who}: substitute changed — cover is being arranged"
    else:
        title, body = "Timetable change today", f"{who}: cover cancelled — the regular teacher is back"
    students = await db.students.find({"institution_id": iid, "class_name": sub["class_name"], "section": sub.get("section"),
                                       "status": {"$ne": "inactive"}}, {"_id": 0, "id": 1}).to_list(500)
    sids = [s["id"] for s in students]
    for u in await db.users.find({"institution_id": iid, "role": "student", "student_id": {"$in": sids}}, {"_id": 0, "id": 1, "student_id": 1}).to_list(500):
        await deliver(iid, u["id"], "timetable_change", title, body, sub["id"], {"student_id": u.get("student_id")})
    for p in await db.users.find({"institution_id": iid, "role": "parent", "student_ids": {"$in": sids}}, {"_id": 0, "id": 1, "student_ids": 1}).to_list(1000):
        kid = next((s for s in p.get("student_ids") or [] if s in sids), None)
        await deliver(iid, p["id"], "timetable_change", title, body, sub["id"], {"student_id": kid})


def _hook(event, **kw):
    if event == "notify":
        if kw.get("ntype") in TYPE_CATEGORY:
            _spawn(deliver(kw["iid"], kw["user_id"], kw["ntype"], kw["title"], kw["body"], kw.get("related_id")))
    elif event == "section_cover":
        _spawn(_section_cover(kw["iid"], kw["sub"], kw["kind"]))


S._PUSH_HOOKS.append(_hook)


# ---------------- endpoints (any logged-in user, self only) ----------------
class PushRegister(BaseModel):
    token: str = Field(..., description="Expo push token, e.g. ExponentPushToken[xxxx]")
    platform: str = Field("", description="ios | android | web")
    device_name: Optional[str] = ""
    app_version: Optional[str] = ""


class PushUnregister(BaseModel):
    token: str


class PushPrefsBody(BaseModel):
    preferences: dict = Field(..., description="{category: bool} for messages, fees, homework, notices, timetable, teacher_covers")


@api.post("/push/register", tags=["push"])
async def push_register(body: PushRegister, user: dict = Depends(S.get_current_user)):
    tok = body.token.strip()
    if not TOKEN_RE.match(tok):
        raise HTTPException(status_code=400, detail="Not a valid Expo push token")
    now = S.now_iso()
    # a device belongs to one signed-in account at a time: re-registering moves it to the caller
    await db.push_tokens.update_one({"token": tok}, {
        "$set": {"user_id": user["id"], "institution_id": user.get("institution_id"), "role": user["role"],
                 "platform": (body.platform or "")[:10], "device_name": _short(body.device_name, 80),
                 "app_version": _short(body.app_version, 20), "last_seen": now, "active": True},
        "$unset": {"deactivated_reason": "", "deactivated_at": ""},
        "$setOnInsert": {"id": str(uuid.uuid4()), "token": tok, "created_at": now}}, upsert=True)
    return {"ok": True}


@api.post("/push/unregister", tags=["push"])
async def push_unregister(body: PushUnregister, user: dict = Depends(S.get_current_user)):
    r = await db.push_tokens.update_many({"token": body.token.strip(), "user_id": user["id"]},
                                         {"$set": {"active": False, "deactivated_reason": "signed_out", "deactivated_at": S.now_iso()}})
    return {"ok": True, "deactivated": r.modified_count}


@api.get("/push/preferences", tags=["push"])
async def push_get_prefs(user: dict = Depends(S.get_current_user)):
    prefs = await get_prefs(user["id"])
    cats = [{"key": k, "label": lbl, "enabled": prefs[k]} for k, (lbl, roles) in CATEGORIES.items() if user["role"] in roles]
    devices = await db.push_tokens.count_documents({"user_id": user["id"], "active": True})
    return {"preferences": prefs, "categories": cats, "devices": devices}


@api.put("/push/preferences", tags=["push"])
async def push_put_prefs(body: PushPrefsBody, user: dict = Depends(S.get_current_user)):
    clean = {k: bool(v) for k, v in (body.preferences or {}).items() if k in CATEGORIES}
    if not clean:
        raise HTTPException(status_code=400, detail="No known categories in preferences")
    await db.push_preferences.update_one({"user_id": user["id"]}, {
        "$set": {**{f"prefs.{k}": v for k, v in clean.items()}, "institution_id": user.get("institution_id"), "updated_at": S.now_iso()}},
        upsert=True)
    return await push_get_prefs(user=user)


@api.post("/push/test", tags=["push"])
async def push_test(user: dict = Depends(S.get_current_user)):
    n = await db.push_tokens.count_documents({"user_id": user["id"], "institution_id": user.get("institution_id"), "active": True})
    if not n:
        return {"ok": False, "devices": 0, "message": "No phone is registered for notifications on this account yet."}
    res = await deliver(user.get("institution_id"), user["id"], "test", "Test notification",
                        "Notifications are working on this phone.", None, force_category="test")
    return {"ok": any(r["status"] == "sent" for r in res), "devices": n, "results": res}


@api.get("/push/badge", tags=["push"])
async def push_badge(user: dict = Depends(S.get_current_user)):
    return {"badge": await badge_for(user)}


async def _indexes():
    try:
        await db.push_tokens.create_index("token", unique=True)
        await db.push_tokens.create_index([("user_id", 1), ("active", 1)])
        await db.push_throttle.create_index("key", unique=True)
    except Exception:
        log.exception("push index creation failed")


@S.app.on_event("startup")
async def _push_startup():
    await _indexes()
