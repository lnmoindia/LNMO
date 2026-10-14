from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

import os
import base64
import hmac
import json
import asyncio
from collections import defaultdict
import hashlib
import secrets
import ipaddress
import httpx
from html.parser import HTMLParser
from urllib.parse import urlparse
import re
import uuid
import logging
import bcrypt
import jwt
from datetime import datetime, timezone, timedelta
from urllib.parse import quote
from fastapi import FastAPI, APIRouter, Request, Response, HTTPException, Depends, Body, UploadFile, File, Form, Query
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from typing import Optional, List, Literal, Dict
from pydantic import BaseModel, Field as PField, EmailStr

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

JWT_SECRET = os.environ['JWT_SECRET']
ALGO = "HS256"

app = FastAPI(openapi_url="/api/openapi.json", docs_url="/api/docs", redoc_url="/api/redoc")
api = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("lnmo")


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def make_tokens(user):
    tv = user.get("tv", 0)  # session version: bumping it revokes every outstanding token
    access = jwt.encode({"sub": user["id"], "role": user["role"], "type": "access", "tv": tv,
                         "exp": datetime.now(timezone.utc) + timedelta(hours=24)}, JWT_SECRET, algorithm=ALGO)
    refresh = jwt.encode({"sub": user["id"], "type": "refresh", "tv": tv,
                          "exp": datetime.now(timezone.utc) + timedelta(days=7)}, JWT_SECRET, algorithm=ALGO)
    return access, refresh


def set_auth_cookies(response: Response, access: str, refresh: str):
    response.set_cookie("access_token", access, httponly=True, secure=True, samesite="none", max_age=86400, path="/")
    response.set_cookie("refresh_token", refresh, httponly=True, secure=True, samesite="none", max_age=604800, path="/")


async def public_user(user: dict) -> dict:
    u = {k: v for k, v in user.items() if k not in ("_id", "password_hash", "signature_path", "signature_type")}
    u["has_photo"] = bool(user.get("photo_path"))
    u["has_signature"] = bool(user.get("signature_path"))
    if u.get("institution_id"):
        inst = await db.institutions.find_one({"id": u["institution_id"]}, {"_id": 0, "name": 1})
        u["institution_name"] = inst["name"] if inst else None
    if user.get("role") == "teacher" and user.get("status") != "inactive":
        pa = await db.principal_assignments.find_one(
            {"user_id": user["id"], "institution_id": user.get("institution_id")}, {"_id": 0})
        if pa:
            u["is_principal"] = True
            u["principal"] = {"scope_type": pa["scope_type"], "unit_ids": pa.get("unit_ids") or [],
                              "designation": pa["designation"]}
    return u


async def get_current_user(request: Request) -> dict:
    token = request.cookies.get("access_token")
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[ALGO])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type")
    user = await db.users.find_one({"id": payload["sub"]})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    if payload.get("tv", 0) != user.get("tv", 0):
        raise HTTPException(status_code=401, detail="Session expired — please sign in again")
    if ENFORCE_PW_CHANGE and user.get("must_change_password") and request.url.path not in PW_CHANGE_ALLOWED:
        raise HTTPException(status_code=403, detail={"code": "PASSWORD_CHANGE_REQUIRED",
                                                     "msg": "Choose a new password before continuing."})
    return user


# While must_change_password is set, only these authenticated routes work (public routes don't use auth).
ENFORCE_PW_CHANGE = True  # only in-process legacy test harnesses flip this (tests/conftest.py); never env-driven
PW_CHANGE_ALLOWED = {"/api/auth/change-password", "/api/auth/me", "/api/auth/logout", "/api/platform/branding"}


def require_roles(*roles):
    async def dep(user: dict = Depends(get_current_user)):
        if user["role"] not in roles:
            raise HTTPException(status_code=403, detail="Access denied")
        return user
    return dep


# ---------------- Principal role (elevated teacher) ----------------
# DESIGN DECISION: A principal is NOT a separate account type. The user keeps role == "teacher"
# and gains a row in `principal_assignments`. This guarantees principals keep ALL existing teacher
# endpoints for free (combined portal, point 4), and revoking = deleting the assignment, which is
# re-evaluated on every request (point 8). Principal powers are layered on top via the helpers below.

PRINCIPAL_EXCLUDED_RESOURCES = {"academic_units", "academic_years"}
# Governance resources principals cannot MUTATE, but may READ (names aren't sensitive and the
# Class Hub / Timetable / Exams pages need them to render filters).
PRINCIPAL_READONLY_RESOURCES = {"academic_units", "academic_years"}
CLASS_SCOPED_RESOURCES = {"students", "sections", "subject_offerings", "enrollments",
                          "teacher_assignments", "assessments", "achievements"}


async def active_principal(user: dict):
    """Return the principal_assignment for an active elevated teacher, else None."""
    if not user or user.get("role") != "teacher" or not user.get("institution_id"):
        return None
    if user.get("status") == "inactive":
        return None
    return await db.principal_assignments.find_one(
        {"user_id": user["id"], "institution_id": user["institution_id"]}, {"_id": 0})


async def principal_scope(user: dict):
    """Resolve a principal's reach. None for non-principals; else a dict with
    whole_school flag, unit_ids and the derived class_names in scope."""
    pa = await active_principal(user)
    if not pa:
        return None
    if pa.get("scope_type") == "whole_school":
        return {"whole_school": True, "unit_ids": None, "class_names": None}
    unit_ids = pa.get("unit_ids") or []
    classes = await db.classes.find(
        {"institution_id": user["institution_id"], "academic_unit_id": {"$in": unit_ids}},
        {"_id": 0, "name": 1}).to_list(2000)
    return {"whole_school": False, "unit_ids": unit_ids,
            "class_names": [c["name"] for c in classes]}


async def require_admin_or_principal(user: dict = Depends(get_current_user)):
    """Allow institution_admin OR an active principal (elevated teacher)."""
    if user.get("role") == "institution_admin" and user.get("institution_id"):
        return user
    if await active_principal(user):
        return user
    raise HTTPException(status_code=403, detail="Access denied")


async def require_admin_or_whole_principal(user: dict = Depends(get_current_user)):
    """Allow institution_admin OR a WHOLE-SCHOOL principal (used for institution-wide teacher
    ACCOUNT management, which has no unit affinity)."""
    if user.get("role") == "institution_admin" and user.get("institution_id"):
        return user
    pa = await active_principal(user)
    if pa and pa.get("scope_type") == "whole_school":
        return user
    raise HTTPException(status_code=403, detail="Access denied")


def apply_principal_scope_query(resource: str, query: dict, scope: dict):
    """Narrow a Mongo query to a unit-scoped principal's reach (no-op for admins/whole-school)."""
    if not scope or scope["whole_school"]:
        return
    if resource == "classes":
        query["academic_unit_id"] = {"$in": scope["unit_ids"]}
    elif resource in CLASS_SCOPED_RESOURCES:
        query["class_name"] = {"$in": scope["class_names"] or ["__none__"]}
    # subjects / notices are institution-wide catalogs → intentionally no unit filter


def _doc_in_principal_scope(resource: str, doc: dict, scope: dict) -> bool:
    if not scope or scope["whole_school"]:
        return True
    if resource == "classes":
        return doc.get("academic_unit_id") in (scope["unit_ids"] or [])
    if resource in CLASS_SCOPED_RESOURCES:
        return doc.get("class_name") in (scope["class_names"] or [])
    return True  # institution-wide resource


async def guard_principal_class(user: dict, class_name):
    """Raise 403 if a unit-scoped principal reaches a class outside their scope."""
    scope = await principal_scope(user)
    if scope and not scope["whole_school"] and class_name not in (scope["class_names"] or []):
        raise HTTPException(status_code=403, detail="This class is outside your assigned scope")


SLUG_RE = re.compile(r"^[a-z0-9-]+$")


async def _normalize_and_check_slug(slug, exclude_id=None):
    """Normalize an institution slug (lowercase, url-safe) and enforce global uniqueness."""
    s = (slug or "").strip().lower()
    if not s:
        return ""
    if not SLUG_RE.match(s):
        raise HTTPException(status_code=400, detail="Slug may only contain lowercase letters, numbers and hyphens")
    q = {"slug": s}
    if exclude_id:
        q["id"] = {"$ne": exclude_id}
    if await db.institutions.find_one(q):
        raise HTTPException(status_code=400, detail="That slug is already taken by another institution")
    return s


async def audit(actor, action, resource, entity_id=None, entity_name=None, institution_id=None):
    await db.audit_logs.insert_one({
        "id": str(uuid.uuid4()), "actor_email": actor.get("email"), "actor_role": actor.get("role"),
        "action": action, "resource": resource, "entity_id": entity_id, "entity_name": entity_name,
        "institution_id": institution_id or actor.get("institution_id"), "timestamp": now_iso()})


# ---------------- Auth ----------------

LOCK_MAX = 5
LOCK_MINUTES = 15


def _login_phone(ident: str):
    """Canonical 10-digit mobile if the identifier is a phone number (+91/91/0 prefixes), else None."""
    if "@" in ident or not re.fullmatch(r"[\d\s\-+().]+", ident):
        return None
    d = re.sub(r"\D", "", ident)
    if len(d) == 12 and d.startswith("91"):
        d = d[2:]
    elif len(d) == 11 and d.startswith("0"):
        d = d[1:]
    return d if len(d) == 10 else None


async def _login_school(payload: dict):
    slug = (payload.get("slug") or "").strip().lower()
    domain = (payload.get("domain") or "").strip().lstrip("@").lower()
    if slug:
        inst = await db.institutions.find_one({"$or": [{"slug": slug}, {"code": slug.upper()}, {"domain": slug}]}, {"_id": 0, "id": 1})
        if inst:
            return inst["id"]
    if domain:
        inst = await db.institutions.find_one({"domain": domain}, {"_id": 0, "id": 1})
        if inst:
            return inst["id"]
    return None


async def _find_parent_by_login_phone(phone: str, payload: dict):
    active = {"role": "parent", "phone": phone, "status": {"$ne": "inactive"}}
    iid = await _login_school(payload)
    if iid:
        return await db.users.find_one({**active, "institution_id": iid})
    matches = await db.users.find(active).to_list(2)
    if len(matches) > 1:
        raise HTTPException(status_code=400, detail="This mobile number is registered at more than one school. Please use your school's login link.")
    return matches[0] if matches else None


async def _find_student_by_admission(iid: str, adm: str):
    s = await db.students.find_one(
        {"institution_id": iid, "admission_no": {"$regex": f"^\\s*{re.escape(adm.strip())}\\s*$", "$options": "i"}},
        {"_id": 0, "user_id": 1})
    if not s or not s.get("user_id"):
        return None
    return await db.users.find_one({"id": s["user_id"], "institution_id": iid, "role": "student"})


async def _account_lock_keys(u: dict):
    """Every login_attempts identifier that can belong to this account."""
    keys = [f"user:{u['id']}"]
    if u.get("email"):
        keys.append(u["email"].lower())
    p = _login_phone(u.get("phone") or "")
    if p:
        keys.append(f"phone:{p}")
    if u.get("role") == "student" and u.get("institution_id"):
        s = await db.students.find_one({"user_id": u["id"], "institution_id": u["institution_id"]}, {"_id": 0, "admission_no": 1})
        if s and s.get("admission_no"):
            keys.append(f"adm:{u['institution_id']}:{s['admission_no'].strip().lower()}")
    return keys


async def _active_lock(keys: list):
    """Latest active lock across keys → {locked_until, last_failed_at, count} or None."""
    now, best = datetime.now(timezone.utc), None
    async for a in db.login_attempts.find({"identifier": {"$in": keys}}, {"_id": 0}):
        last = datetime.fromisoformat(a["last_at"])
        until = last + timedelta(minutes=LOCK_MINUTES)
        if a.get("count", 0) >= LOCK_MAX and until > now and (not best or until > best["_until"]):
            best = {"_until": until, "locked_until": until.isoformat(), "last_failed_at": a["last_at"], "count": a["count"]}
    if best:
        best.pop("_until")
    return best


async def _record_login_failure(key: str, user: "dict | None" = None):
    a = await db.login_attempts.find_one({"identifier": key}, {"_id": 0})
    if a and datetime.now(timezone.utc) - datetime.fromisoformat(a["last_at"]) >= timedelta(minutes=LOCK_MINUTES):
        await db.login_attempts.delete_one({"identifier": key})
    r = await db.login_attempts.find_one_and_update(
        {"identifier": key}, {"$inc": {"count": 1}, "$set": {"last_at": now_iso()}}, upsert=True, return_document=True)
    if user and r and r.get("count") == LOCK_MAX:
        await audit(user, "account_locked", "user", user["id"], user.get("name"), institution_id=user.get("institution_id"))


@api.post("/auth/login")
async def login(response: Response, payload: dict = Body(...)):
    raw = (payload.get("email") or payload.get("identifier") or "").strip()
    password = payload.get("password") or ""
    if not raw or not password:
        raise HTTPException(status_code=400, detail="Email and password are required")
    phone = _login_phone(raw)
    if phone:
        ident, fail_msg = f"phone:{phone}", "Invalid mobile number or password"
        user = await _find_parent_by_login_phone(phone, payload)
    elif "@" in raw:
        ident, fail_msg = raw.lower(), "Invalid email or password"
        user = await db.users.find_one({"email": ident})
    else:
        iid = await _login_school(payload)
        if not iid:
            raise HTTPException(status_code=400, detail="Use your school's login link, or sign in with your email")
        ident, fail_msg = f"adm:{iid}:{raw.lower()}", "Invalid credentials"
        user = await _find_student_by_admission(iid, raw)
    keys = [ident] + (await _account_lock_keys(user) if user else [])
    if await _active_lock(keys):
        raise HTTPException(status_code=429, detail="Too many failed attempts. Try again in 15 minutes.")
    if not user or not user.get("password_hash") or not verify_password(password, user["password_hash"]):
        await _record_login_failure(f"user:{user['id']}" if user else ident, user)
        raise HTTPException(status_code=401, detail=fail_msg)
    if user.get("status") == "inactive":
        raise HTTPException(status_code=403, detail="Account is inactive. Contact your administrator.")
    await db.login_attempts.delete_many({"identifier": {"$in": keys}})
    access, refresh = make_tokens(user)
    set_auth_cookies(response, access, refresh)
    await audit(user, "login", "session")
    return await public_user(user)


async def _lock_target(actor: dict, uid: str):
    """Resolve a user (or student record id) the actor may unlock; 403 outside scope."""
    t = await db.users.find_one({"id": uid}, {"_id": 0, "password_hash": 0})
    if not t:
        s = await db.students.find_one({"id": uid}, {"_id": 0, "user_id": 1})
        if s and s.get("user_id"):
            t = await db.users.find_one({"id": s["user_id"]}, {"_id": 0, "password_hash": 0})
    if not t:
        raise HTTPException(status_code=404, detail="Account not found")
    role = actor.get("role")
    if role == "platform_admin":
        if t.get("role") == "institution_admin":
            return t
        raise HTTPException(status_code=403, detail="Access denied")
    if not actor.get("institution_id") or t.get("institution_id") != actor["institution_id"]:
        raise HTTPException(status_code=403, detail="Access denied")
    if role == "institution_admin" and t.get("role") != "platform_admin":
        return t
    scope = await principal_scope(actor) if role == "teacher" else None
    if scope and t["id"] != actor["id"]:
        if t.get("role") == "teacher" and await _absence_in_scope(actor, t["id"]):
            return t
        if t.get("role") == "student":
            s = await db.students.find_one({"user_id": t["id"], "institution_id": t["institution_id"]}, {"_id": 0, "class_name": 1})
            if scope["whole_school"] or (s and s.get("class_name") in (scope["class_names"] or [])):
                return t
    raise HTTPException(status_code=403, detail="Access denied")


@api.get("/account-locks")
async def list_account_locks(user: dict = Depends(get_current_user)):
    """Currently paused accounts the caller may unlock."""
    since = (datetime.now(timezone.utc) - timedelta(minutes=LOCK_MINUTES)).isoformat()
    out, seen = [], set()
    async for a in db.login_attempts.find({"count": {"$gte": LOCK_MAX}, "last_at": {"$gt": since}}, {"_id": 0}):
        k = a["identifier"]
        if k.startswith("user:"):
            u = await db.users.find_one({"id": k[5:]}, {"_id": 0, "id": 1})
        elif k.startswith("adm:"):
            _, iid, adm = k.split(":", 2)
            u = await _find_student_by_admission(iid, adm)
        elif k.startswith("phone:"):
            u = await db.users.find_one({"role": "parent", "phone": k[6:]}, {"_id": 0, "id": 1})
        else:
            u = await db.users.find_one({"email": k}, {"_id": 0, "id": 1})
        if not u or u["id"] in seen:
            continue
        try:
            t = await _lock_target(user, u["id"])
        except HTTPException:
            continue
        seen.add(t["id"])
        lock = await _active_lock(await _account_lock_keys(t))
        if lock:
            out.append({"user_id": t["id"], "name": t.get("name"), "role": t.get("role"), **lock})
    return {"locks": out}


@api.get("/account-locks/{uid}")
async def get_account_lock(uid: str, user: dict = Depends(get_current_user)):
    t = await _lock_target(user, uid)
    lock = await _active_lock(await _account_lock_keys(t))
    return {"user_id": t["id"], "locked": bool(lock), **(lock or {})}


@api.post("/account-locks/{uid}/unlock")
async def unlock_account(uid: str, user: dict = Depends(get_current_user)):
    t = await _lock_target(user, uid)
    r = await db.login_attempts.delete_many({"identifier": {"$in": await _account_lock_keys(t)}})
    await audit(user, "unlock_account", "user", t["id"], t.get("name"), institution_id=t.get("institution_id"))
    return {"ok": True, "user_id": t["id"], "cleared": r.deleted_count}


@api.post("/auth/logout")
async def logout(response: Response, user: dict = Depends(get_current_user)):
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")
    return {"message": "Logged out"}


@api.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    return await public_user(user)


@api.post("/auth/refresh")
async def refresh_token(request: Request, response: Response):
    token = request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(status_code=401, detail="No refresh token")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[ALGO])
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid token type")
    user = await db.users.find_one({"id": payload["sub"]})
    if not user or payload.get("tv", 0) != user.get("tv", 0):
        raise HTTPException(status_code=401, detail="Session expired — please sign in again")
    access, refresh = make_tokens(user)
    set_auth_cookies(response, access, refresh)
    return {"message": "refreshed"}


# ---------------- Generic resources ----------------

RESOURCES = {
    "institutions": {"scope": "platform", "search": ["name", "code", "city", "contact_email"]},
    "plans": {"scope": "platform", "search": ["name", "code"]},
    "students": {"scope": "institution", "search": ["first_name", "last_name", "admission_no", "email"]},
    "teachers": {"scope": "institution", "search": ["first_name", "last_name", "employee_id", "email"]},
    "classes": {"scope": "institution", "search": ["name", "grade_level"]},
    "sections": {"scope": "institution", "search": ["name", "class_name"]},
    "subjects": {"scope": "institution", "search": ["name", "code"]},
    "academic_years": {"scope": "institution", "search": ["name"]},
    "academic_units": {"scope": "institution", "search": ["name", "code"]},
    "subject_offerings": {"scope": "institution", "search": ["subject", "class_name", "section"]},
    "enrollments": {"scope": "institution", "search": ["student_name", "admission_no", "class_name", "section", "academic_year"]},
    "teacher_assignments": {"scope": "institution", "search": ["teacher_name", "teacher_email", "class_name", "section", "subject"]},
    "assessments": {"scope": "institution", "search": ["name", "subject", "class_name"]},
    "achievements": {"scope": "institution", "search": ["student_name", "title", "class_name"]},
    "notices": {"scope": "institution", "search": ["title", "audience"]},
}

PROTECTED_KEYS = {"id", "_id", "created_at", "institution_id"}


def resource_cfg(resource: str):
    cfg = RESOURCES.get(resource)
    if not cfg:
        raise HTTPException(status_code=404, detail="Unknown resource")
    return cfg


async def check_scope(resource: str, user: dict, write: bool = False):
    cfg = resource_cfg(resource)
    if cfg["scope"] == "platform" and user["role"] != "platform_admin":
        raise HTTPException(status_code=403, detail="Access denied")
    if cfg["scope"] == "institution":
        if not user.get("institution_id"):
            raise HTTPException(status_code=403, detail="Access denied")
        if user["role"] == "institution_admin":
            return cfg
        # Principals (elevated teachers) get admin powers on most institution resources,
        # but NEVER mutate the excluded governance resources. They MAY read the read-only ones.
        if await active_principal(user):
            if resource not in PRINCIPAL_EXCLUDED_RESOURCES:
                return cfg
            if not write and resource in PRINCIPAL_READONLY_RESOURCES:
                return cfg
        raise HTTPException(status_code=403, detail="Access denied")
    return cfg


async def _class_exists(iid, class_name):
    return bool(await db.classes.find_one({"institution_id": iid, "name": class_name}))


# Every collection that stores a class_name / section — kept exhaustive so renames never orphan.
CLASS_NAME_COLLECTIONS = ("students", "enrollments", "attendance", "marks", "assessments",
                          "teacher_assignments", "subject_offerings", "timetable_entries",
                          "achievements", "sections", "subject_requirements")
SECTION_COLLECTIONS = ("students", "enrollments", "attendance", "marks", "assessments",
                       "teacher_assignments", "subject_offerings", "timetable_entries", "achievements")


async def _cascade_class_rename(iid, old, new):
    if not old or old == new:
        return
    for col in CLASS_NAME_COLLECTIONS:
        await db[col].update_many({"institution_id": iid, "class_name": old}, {"$set": {"class_name": new}})


async def _cascade_section_rename(iid, class_name, old, new):
    if not old or old == new:
        return
    for col in SECTION_COLLECTIONS:
        await db[col].update_many({"institution_id": iid, "class_name": class_name, "section": old},
                                  {"$set": {"section": new}})
    async for r in db.subject_requirements.find({"institution_id": iid, "class_name": class_name,
                                                 f"section_teachers.{old}": {"$exists": True}}):
        st = r.get("section_teachers") or {}
        if old in st:
            st[new] = st.pop(old)
            await db.subject_requirements.update_one({"id": r["id"]}, {"$set": {"section_teachers": st}})


async def _delete_block_message(iid, class_name, section=None):
    """Return a human message if a class/section has dependent data (blocks delete), else None."""
    q = {"institution_id": iid, "class_name": class_name}
    label = class_name
    if section is not None:
        q["section"] = section
        label = f"{class_name} - {section}"
    students = await db.students.count_documents(q)
    att = await db.attendance.count_documents(q)
    assess = await db.assessments.count_documents(q)
    if students or att or assess:
        bits = []
        if students:
            bits.append(f"{students} student(s) enrolled")
        if att:
            bits.append(f"{att} attendance record(s)")
        if assess:
            bits.append(f"{assess} assessment(s)")
        return f"Cannot delete {label}: {', '.join(bits)} exist. Remove the students first."
    return None


async def _capacity_warning(iid, class_name, section):
    if not section:
        return None
    sec = await db.sections.find_one({"institution_id": iid, "class_name": class_name, "name": section})
    if not sec:
        return None
    try:
        cap = int(sec.get("capacity"))
    except (TypeError, ValueError):
        return None
    if cap <= 0:
        return None
    count = await db.students.count_documents({"institution_id": iid, "class_name": class_name, "section": section})
    if count >= cap:
        return f"{class_name} - {section} is at capacity ({count}/{cap})"
    return None


def _to_num(v, default):
    try:
        n = float(v)
        return int(n) if n == int(n) else n
    except (TypeError, ValueError):
        return default


def normalize_offering_marks(doc):
    """Derive theory/practical/total max marks on a subject offering (class-level curriculum)."""
    hp = doc.get("has_practical")
    if isinstance(hp, str):
        hp = hp in ("true", "True", "1", "yes")
    doc["has_practical"] = bool(hp)
    if doc["has_practical"]:
        theory = _to_num(doc.get("theory_max_marks"), 70)
        practical = _to_num(doc.get("practical_max_marks"), 30)
        doc["theory_max_marks"] = theory
        doc["practical_max_marks"] = practical
        doc["max_marks"] = theory + practical
    else:
        total = _to_num(doc.get("max_marks"), None)
        if total is None:
            total = _to_num(doc.get("theory_max_marks"), 100)
        doc["max_marks"] = total
        doc["theory_max_marks"] = total
        doc["practical_max_marks"] = 0


async def enrich_institution_doc(resource, doc, user):
    iid = user["institution_id"]
    if resource == "enrollments":
        if not doc.get("student_id"):
            raise HTTPException(status_code=400, detail="Select a student")
        student = await db.students.find_one({"id": doc["student_id"], "institution_id": iid})
        if not student:
            raise HTTPException(status_code=400, detail="Student not found")
        # Gate: cannot enroll before classes exist
        if await db.classes.count_documents({"institution_id": iid}) == 0:
            raise HTTPException(status_code=400, detail="Create at least one class before enrolling students")
        if doc.get("class_name") and not await _class_exists(iid, doc["class_name"]):
            raise HTTPException(status_code=400, detail="Selected class does not exist. Create the class first.")
        dup = await db.enrollments.find_one({"institution_id": iid, "student_id": doc["student_id"],
                                             "academic_year": doc.get("academic_year"), "id": {"$ne": doc.get("id")}})
        if dup:
            raise HTTPException(status_code=400, detail="Student is already enrolled for this academic year")
        doc["student_name"] = f"{student.get('first_name', '')} {student.get('last_name', '')}".strip()
        doc["admission_no"] = student.get("admission_no")
        await db.students.update_one({"id": student["id"]}, {"$set": {
            "class_name": doc.get("class_name"), "section": doc.get("section"),
            "academic_year": doc.get("academic_year"), "enrollment_status": "enrolled"}})
    elif resource == "teacher_assignments":
        if not doc.get("teacher_email"):
            raise HTTPException(status_code=400, detail="Select a teacher")
        # Gate: cannot assign teachers before classes exist
        if await db.classes.count_documents({"institution_id": iid}) == 0:
            raise HTTPException(status_code=400, detail="Create at least one class before assigning teachers")
        if doc.get("class_name") and not await _class_exists(iid, doc["class_name"]):
            raise HTTPException(status_code=400, detail="Selected class does not exist. Create the class first.")
        tu = await db.users.find_one({"email": doc["teacher_email"], "institution_id": iid})
        doc["teacher_name"] = tu["name"] if tu else doc["teacher_email"]
        doc["teacher_id"] = tu["id"] if tu else None
        dup = await db.teacher_assignments.find_one({
            "institution_id": iid, "teacher_email": doc["teacher_email"],
            "class_name": doc.get("class_name"), "section": doc.get("section", ""),
            "subject": doc.get("subject", ""), "id": {"$ne": doc.get("id")}})
        if dup:
            raise HTTPException(status_code=400, detail="This teacher is already assigned to this class/section/subject")
    elif resource == "academic_units":
        if doc.get("sort_order") in (None, ""):
            doc["sort_order"] = await db.academic_units.count_documents({"institution_id": iid})
        try:
            doc["sort_order"] = int(doc["sort_order"])
        except (TypeError, ValueError):
            doc["sort_order"] = 0
        for k in ("timetable_required", "has_lab"):
            doc[k] = bool(doc.get(k)) if not isinstance(doc.get(k), str) else doc.get(k) in ("true", "True", "1", "yes")
    elif resource == "subject_offerings":
        if not doc.get("subject") or not doc.get("class_name"):
            raise HTTPException(status_code=400, detail="Subject and class are required")
        if not await _class_exists(iid, doc["class_name"]):
            raise HTTPException(status_code=400, detail="Selected class does not exist")
        dup = await db.subject_offerings.find_one({"institution_id": iid, "class_name": doc["class_name"],
                                                   "section": doc.get("section", ""), "subject": doc["subject"],
                                                   "id": {"$ne": doc.get("id")}})
        if dup:
            raise HTTPException(status_code=400, detail="This subject is already offered for this class/section")
        normalize_offering_marks(doc)
    elif resource == "classes":
        if not doc.get("academic_unit_id"):
            raise HTTPException(status_code=400, detail="Select an academic unit for this class")
        u = await db.academic_units.find_one({"id": doc["academic_unit_id"], "institution_id": iid})
        if not u:
            raise HTTPException(status_code=400, detail="Selected academic unit does not exist")
        doc["academic_unit_name"] = u["name"]
    elif resource == "sections":
        if "class_teacher_id" in doc:
            tid = doc.get("class_teacher_id")
            if tid:
                t = await db.users.find_one({"id": tid, "institution_id": iid, "role": "teacher"})
                if not t:
                    raise HTTPException(status_code=400, detail="Selected teacher not found")
                doc["class_teacher"] = t["name"]
            else:
                doc["class_teacher"] = ""
        for id_key, name_key in (("class_leader_id", "class_leader"), ("second_leader_id", "second_leader")):
            if id_key in doc:
                sid = doc.get(id_key)
                if sid:
                    s = await db.students.find_one({"id": sid, "institution_id": iid})
                    if not s:
                        raise HTTPException(status_code=400, detail="Selected student not found")
                    if doc.get("class_name") and s.get("class_name") != doc["class_name"]:
                        raise HTTPException(status_code=400, detail="Student is not in this class")
                    doc[name_key] = f"{s.get('first_name', '')} {s.get('last_name', '')}".strip()
                else:
                    doc[name_key] = ""
    elif resource == "achievements":
        if not doc.get("student_id") or not str(doc.get("title") or "").strip():
            raise HTTPException(status_code=400, detail="Student and title are required")
        s = await db.students.find_one({"id": doc["student_id"], "institution_id": iid})
        if not s:
            raise HTTPException(status_code=400, detail="Student not found")
        doc["student_name"] = f"{s.get('first_name', '')} {s.get('last_name', '')}".strip()
        doc["class_name"] = s.get("class_name")
        doc["section"] = s.get("section")
        doc["title"] = str(doc["title"]).strip()
        if not doc.get("date"):
            doc["date"] = now_iso()[:10]
    elif resource == "notices":
        if not str(doc.get("title") or "").strip():
            raise HTTPException(status_code=400, detail="Notice title is required")
        doc["title"] = str(doc["title"]).strip()
        if doc.get("audience") not in ("all", "teachers", "students"):
            doc["audience"] = "all"
        if doc.get("status") not in ("published", "draft"):
            doc["status"] = "published"
        doc.setdefault("author_name", user.get("name"))
    elif resource == "subjects":
        if not (doc.get("code") or "").strip():
            words = [w for w in re.split(r"[^A-Za-z0-9]+", doc.get("name") or "") if w]
            base = ("".join(w[0] for w in words)[:4] if len(words) > 1 else (words[0][:4] if words else "SUB")).upper()
            code, n = base, 1
            while await db.subjects.find_one({"institution_id": iid, "code": code, "id": {"$ne": doc.get("id")}}):
                n += 1
                code = f"{base}{n}"
            doc["code"] = code
    elif resource == "students" and not doc.get("enrollment_status"):
        doc["enrollment_status"] = "not_enrolled"
    elif resource == "assessments" and not doc.get("status"):
        doc["status"] = "draft"


@api.get("/res/{resource}")
async def list_resource(resource: str, search: str = "", page: int = 1, limit: int = 20,
                        user: dict = Depends(get_current_user)):
    cfg = await check_scope(resource, user)
    query = {}
    if cfg["scope"] == "institution":
        query["institution_id"] = user["institution_id"]
        apply_principal_scope_query(resource, query, await principal_scope(user))
    if search:
        query["$or"] = [{f: {"$regex": search, "$options": "i"}} for f in cfg["search"]]
    total = await db[resource].count_documents(query)
    skip = max(page - 1, 0) * limit
    items = await db[resource].find(query, {"_id": 0}).sort("created_at", -1).skip(skip).to_list(limit)
    return {"items": items, "total": total, "page": page, "pages": max((total + limit - 1) // limit, 1)}


@api.post("/res/{resource}")
async def create_resource(resource: str, payload: dict = Body(...), user: dict = Depends(get_current_user)):
    cfg = await check_scope(resource, user, write=True)
    admin_email = payload.pop("admin_email", None)
    admin_password = payload.pop("admin_password", None)
    admin_name = payload.pop("admin_name", None)
    doc = {k: v for k, v in payload.items() if k not in PROTECTED_KEYS}
    if not (doc.get("name") or doc.get("first_name") or doc.get("student_id")
            or doc.get("teacher_email") or doc.get("subject") or doc.get("title")):
        raise HTTPException(status_code=400, detail="Name is required")
    doc["id"] = str(uuid.uuid4())
    doc["created_at"] = now_iso()
    if cfg["scope"] == "institution":
        doc["institution_id"] = user["institution_id"]
        await enrich_institution_doc(resource, doc, user)
        if resource == "students":
            await _assert_adm_unique(user["institution_id"], doc.get("admission_no"))
        if resource == "students" and not str(doc.get("admission_no") or "").strip():
            prefix, taken = await _adm_ctx(user["institution_id"])
            doc["admission_no"] = _next_adm(prefix, doc.get("class_name"), taken)
        if not _doc_in_principal_scope(resource, doc, await principal_scope(user)):
            raise HTTPException(status_code=403, detail="Outside your assigned scope")
        if resource == "sections" and await db.sections.find_one(
                {"institution_id": user["institution_id"], "class_name": doc.get("class_name"),
                 "name": doc.get("name"), "id": {"$ne": doc["id"]}}):
            raise HTTPException(status_code=400, detail="A section with that name already exists in this class")
    if resource == "institutions" and "slug" in doc:
        doc["slug"] = await _normalize_and_check_slug(doc.get("slug"))
    if resource == "institutions" and admin_email and admin_password:
        if await db.users.find_one({"email": admin_email.strip().lower()}):
            raise HTTPException(status_code=400, detail="Admin email already in use")
    await db[resource].insert_one(dict(doc))
    if resource == "institutions" and admin_email and admin_password:
        email = admin_email.strip().lower()
        await db.users.insert_one({
            "id": str(uuid.uuid4()), "name": admin_name or f"{doc.get('name')} Admin", "email": email,
            "password_hash": hash_password(admin_password), "role": "institution_admin",
            "institution_id": doc["id"], "status": "active", "created_at": now_iso()})
    name = doc.get("name") or doc.get("student_name") or doc.get("teacher_name") or f"{doc.get('first_name', '')} {doc.get('last_name', '')}".strip()
    await audit(user, "create", resource, doc["id"], name)
    doc.pop("_id", None)
    return doc


@api.put("/res/{resource}/{item_id}")
async def update_resource(resource: str, item_id: str, payload: dict = Body(...),
                          user: dict = Depends(get_current_user)):
    cfg = await check_scope(resource, user, write=True)
    query = {"id": item_id}
    if cfg["scope"] == "institution":
        query["institution_id"] = user["institution_id"]
    updates = {k: v for k, v in payload.items()
               if k not in PROTECTED_KEYS and k not in ("admin_email", "admin_password", "admin_name")}
    existing = await db[resource].find_one(query, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Not found")
    _scope = await principal_scope(user)
    if not (_doc_in_principal_scope(resource, existing, _scope)
            and _doc_in_principal_scope(resource, {**existing, **updates}, _scope)):
        raise HTTPException(status_code=403, detail="Outside your assigned scope")
    merged = {**existing, **updates}
    if resource == "students" and "admission_no" in updates and str(updates["admission_no"] or "").strip() != str(existing.get("admission_no") or "").strip():
        await _assert_adm_unique(user["institution_id"], updates["admission_no"], exclude_id=item_id)
    if resource == "subject_offerings":
        normalize_offering_marks(merged)
        for k in ("has_practical", "max_marks", "theory_max_marks", "practical_max_marks"):
            updates[k] = merged[k]
    if cfg["scope"] == "institution" and resource in ("enrollments", "teacher_assignments", "classes", "achievements", "sections", "notices"):
        await enrich_institution_doc(resource, merged, user)
        keys = ("student_name", "admission_no", "teacher_name", "teacher_id", "academic_unit_name",
                "class_teacher", "class_leader", "second_leader", "class_name", "section", "date", "title")
        for k in keys:
            if k in merged:
                updates[k] = merged[k]
    if resource == "institutions" and "slug" in updates:
        updates["slug"] = await _normalize_and_check_slug(updates.get("slug"), exclude_id=item_id)
    if resource == "classes" and "name" in updates and updates["name"] != existing.get("name"):
        if await db.classes.find_one({"institution_id": user["institution_id"], "name": updates["name"], "id": {"$ne": item_id}}):
            raise HTTPException(status_code=400, detail="A class with that name already exists")
        await _cascade_class_rename(user["institution_id"], existing.get("name"), updates["name"])
    if resource == "sections" and "name" in updates and updates["name"] != existing.get("name"):
        cn = existing.get("class_name")
        if await db.sections.find_one({"institution_id": user["institution_id"], "class_name": cn, "name": updates["name"], "id": {"$ne": item_id}}):
            raise HTTPException(status_code=400, detail="A section with that name already exists in this class")
        await _cascade_section_rename(user["institution_id"], cn, existing.get("name"), updates["name"])
    await db[resource].update_one(query, {"$set": updates})
    doc = await db[resource].find_one(query, {"_id": 0})
    name = doc.get("name") or doc.get("student_name") or doc.get("teacher_name") or f"{doc.get('first_name', '')} {doc.get('last_name', '')}".strip()
    await audit(user, "update", resource, item_id, name)
    return doc


@api.get("/res/{resource}/{item_id}")
async def get_resource(resource: str, item_id: str, user: dict = Depends(get_current_user)):
    cfg = RESOURCES.get(resource)
    if not cfg:
        raise HTTPException(status_code=404, detail="Unknown resource")
    if cfg["scope"] != "institution" and user["role"] != "platform_admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    q = {"id": item_id}
    if cfg["scope"] == "institution":
        q["institution_id"] = user["institution_id"]
    doc = await db[resource].find_one(q, {"_id": 0, "password_hash": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Not found")
    if not _doc_in_principal_scope(resource, doc, await principal_scope(user)):
        raise HTTPException(status_code=404, detail="Not found")
    return doc


@api.delete("/res/{resource}/{item_id}")
async def delete_resource(resource: str, item_id: str, user: dict = Depends(get_current_user)):
    cfg = await check_scope(resource, user, write=True)
    query = {"id": item_id}
    if cfg["scope"] == "institution":
        query["institution_id"] = user["institution_id"]
    doc = await db[resource].find_one(query, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Not found")
    if not _doc_in_principal_scope(resource, doc, await principal_scope(user)):
        raise HTTPException(status_code=403, detail="Outside your assigned scope")
    if resource == "classes":
        block = await _delete_block_message(user["institution_id"], doc.get("name"))
        if block:
            raise HTTPException(status_code=409, detail=block)
    if resource == "sections":
        block = await _delete_block_message(user["institution_id"], doc.get("class_name"), doc.get("name"))
        if block:
            raise HTTPException(status_code=409, detail=block)
    await db[resource].delete_one(query)
    if resource == "academic_units":
        await db.principal_assignments.update_many(
            {"institution_id": user["institution_id"], "unit_ids": item_id},
            {"$pull": {"unit_ids": item_id}})
        await db.principal_assignments.delete_many(
            {"institution_id": user["institution_id"], "scope_type": "units", "unit_ids": {"$size": 0}})
    if resource == "institutions":
        for col in ("users", "students", "teachers", "classes", "sections", "subjects",
                    "academic_years", "academic_units", "subject_offerings", "academic_configuration",
                    "enrollments", "teacher_assignments", "assessments", "attendance", "marks", "achievements",
                    "timetable_configs", "timetable_entries", "notices", "principal_assignments",
                    "subject_requirements", "absences", "substitutions", "notifications"):
            await db[col].delete_many({"institution_id": item_id})
    if resource == "assessments":
        await db.marks.delete_many({"assessment_id": item_id})
    if resource == "teacher_assignments":
        await db.timetable_entries.delete_many({"teacher_assignment_id": item_id})
    if resource == "sections" and doc:
        await db.timetable_entries.delete_many({"institution_id": doc.get("institution_id"),
                                                "class_name": doc.get("class_name"), "section": doc.get("name")})
    if resource == "subject_offerings":
        await db.timetable_entries.delete_many({"offering_id": item_id})
    if resource == "classes":
        await db.subject_requirements.delete_many({"institution_id": user["institution_id"], "class_name": doc.get("name")})
    if resource == "students":
        await db.enrollments.delete_many({"student_id": item_id})
        await db.marks.delete_many({"student_id": item_id})
        await db.achievements.delete_many({"student_id": item_id})
        await db.sections.update_many({"class_leader_id": item_id}, {"$set": {"class_leader_id": "", "class_leader": ""}})
        await db.sections.update_many({"second_leader_id": item_id}, {"$set": {"second_leader_id": "", "second_leader": ""}})
        await db.users.delete_many({"student_id": item_id, "institution_id": user["institution_id"]})
    if resource == "enrollments" and doc.get("student_id"):
        remaining = await db.enrollments.count_documents({"student_id": doc["student_id"]})
        if remaining == 0:
            await db.students.update_one(
                {"id": doc["student_id"], "institution_id": user["institution_id"]},
                {"$set": {"enrollment_status": "not_enrolled"}, "$unset": {"class_name": "", "section": "", "academic_year": ""}})
    name = doc.get("name") or doc.get("student_name") or doc.get("teacher_name") or f"{doc.get('first_name', '')} {doc.get('last_name', '')}".strip()
    await audit(user, "delete", resource, item_id, name)
    return {"message": "Deleted"}


# ---------------- Users management ----------------

USER_ROLES = {"institution_admin", "teacher", "student", "staff"}


@api.get("/users")
async def list_users(search: str = "", role: str = "", page: int = 1, limit: int = 20,
                     user: dict = Depends(require_roles("platform_admin", "institution_admin"))):
    query = {}
    if user["role"] == "institution_admin":
        query["institution_id"] = user["institution_id"]
    if role:
        query["role"] = role
    if search:
        query["$or"] = [{f: {"$regex": re.escape(search), "$options": "i"}} for f in ("name", "email", "role")]
    total = await db.users.count_documents(query)
    skip = max(page - 1, 0) * limit
    items = await db.users.find(query, {"_id": 0, "password_hash": 0}).sort("created_at", -1).skip(skip).to_list(limit)
    return {"items": items, "total": total, "page": page, "pages": max((total + limit - 1) // limit, 1)}


@api.post("/users")
async def create_user(payload: dict = Body(...),
                      user: dict = Depends(require_roles("institution_admin"))):
    email = (payload.get("email") or "").strip().lower()
    password = payload.get("password") or ""
    role = payload.get("role")
    if not email or not password or role not in USER_ROLES:
        raise HTTPException(status_code=400, detail="Name, email, password and a valid role are required")
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Email already in use")
    doc = {"id": str(uuid.uuid4()), "name": payload.get("name") or email, "email": email,
           "password_hash": hash_password(password), "role": role, "phone": payload.get("phone"),
           "institution_id": user["institution_id"], "status": "active", "created_at": now_iso()}
    await db.users.insert_one(dict(doc))
    await audit(user, "create", "users", doc["id"], doc["name"])
    doc.pop("password_hash")
    doc.pop("_id", None)
    return doc


@api.put("/users/{user_id}")
async def update_user(user_id: str, payload: dict = Body(...),
                      user: dict = Depends(require_roles("institution_admin"))):
    query = {"id": user_id, "institution_id": user["institution_id"]}
    updates = {}
    for k in ("name", "phone", "status"):
        if k in payload:
            updates[k] = payload[k]
    if payload.get("role") in USER_ROLES:
        updates["role"] = payload["role"]
    if payload.get("password"):
        updates["password_hash"] = hash_password(payload["password"])
    result = await db.users.update_one(query, {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    doc = await db.users.find_one(query, {"_id": 0, "password_hash": 0})
    await audit(user, "update", "users", user_id, doc.get("name"))
    return doc


@api.delete("/users/{user_id}")
async def delete_user(user_id: str, user: dict = Depends(require_roles("institution_admin"))):
    if user_id == user["id"]:
        raise HTTPException(status_code=400, detail="You cannot delete your own account")
    query = {"id": user_id, "institution_id": user["institution_id"]}
    doc = await db.users.find_one(query)
    if not doc:
        raise HTTPException(status_code=404, detail="User not found")
    await db.users.delete_one(query)
    await db.principal_assignments.delete_many({"user_id": user_id, "institution_id": user["institution_id"]})
    if doc.get("role") == "student" and doc.get("student_id"):
        await db.students.update_one({"id": doc["student_id"], "institution_id": user["institution_id"]},
                                     {"$set": {"has_portal_access": False}, "$unset": {"portal_email": "", "user_id": ""}})
    if doc.get("role") == "teacher":
        await db.sections.update_many({"class_teacher_id": user_id}, {"$set": {"class_teacher_id": "", "class_teacher": ""}})
        await db.subject_requirements.update_many(
            {"institution_id": user["institution_id"], "teacher_ids": user_id}, {"$pull": {"teacher_ids": user_id}})
        async for r in db.subject_requirements.find(
                {"institution_id": user["institution_id"]}, {"_id": 0, "id": 1, "section_teachers": 1}):
            st = r.get("section_teachers") or {}
            kept = {k: v for k, v in st.items() if v != user_id}
            if len(kept) != len(st):
                await db.subject_requirements.update_one({"id": r["id"]}, {"$set": {"section_teachers": kept}})
    await audit(user, "delete", "users", user_id, doc.get("name"))
    return {"message": "Deleted"}


# ---------------- Institution profile ----------------

@api.get("/institution/profile")
async def get_institution_profile(user: dict = Depends(require_roles("institution_admin"))):
    inst = await db.institutions.find_one({"id": user["institution_id"]}, {"_id": 0})
    if not inst:
        raise HTTPException(status_code=404, detail="Institution not found")
    return inst


@api.put("/institution/profile")
async def update_institution_profile(payload: dict = Body(...),
                                     user: dict = Depends(require_roles("institution_admin"))):
    updates = {k: v for k, v in payload.items() if k not in PROTECTED_KEYS}
    # slug is platform-owned; logo bytes are managed by the dedicated logo endpoints.
    for protected in ("slug", "logo_path", "logo_type"):
        updates.pop(protected, None)
    await db.institutions.update_one({"id": user["institution_id"]}, {"$set": updates})
    inst = await db.institutions.find_one({"id": user["institution_id"]}, {"_id": 0})
    await audit(user, "update", "institution_profile", user["institution_id"], inst.get("name"))
    return inst


# ---------------- Academic configuration & setup status ----------------

ACADEMIC_UNIT_PRESETS = {
    "k12": [
        {"name": "Lower Primary", "code": "LP", "attendance_model": "daily", "subject_model": "fixed",
         "assessment_model": "grades", "grading_model": "letter", "timetable_required": True, "has_lab": False},
        {"name": "Upper Primary", "code": "UP", "attendance_model": "daily", "subject_model": "fixed",
         "assessment_model": "marks", "grading_model": "percentage", "timetable_required": True, "has_lab": False},
        {"name": "High School", "code": "HS", "attendance_model": "period", "subject_model": "fixed",
         "assessment_model": "marks", "grading_model": "percentage", "timetable_required": True, "has_lab": True},
        {"name": "Higher Secondary", "code": "HSS", "attendance_model": "period", "subject_model": "stream",
         "assessment_model": "marks", "grading_model": "percentage", "timetable_required": True, "has_lab": True},
    ],
}


@api.get("/institution/academic-config")
async def get_academic_config(user: dict = Depends(require_roles("institution_admin"))):
    cfg = await db.academic_configuration.find_one({"institution_id": user["institution_id"]}, {"_id": 0})
    return cfg or {}


@api.put("/institution/academic-config")
async def update_academic_config(payload: dict = Body(...),
                                 user: dict = Depends(require_roles("institution_admin"))):
    iid = user["institution_id"]
    updates = {k: v for k, v in payload.items() if k not in PROTECTED_KEYS and k != "apply_presets"}
    updates["institution_id"] = iid
    updates["updated_at"] = now_iso()
    await db.academic_configuration.update_one({"institution_id": iid},
                                               {"$set": updates, "$setOnInsert": {"id": str(uuid.uuid4()),
                                                                                  "created_at": now_iso()}}, upsert=True)
    created = 0
    if payload.get("apply_presets") and await _setup_is_complete(iid):
        raise HTTPException(status_code=409, detail=PRESET_LOCKED)
    if payload.get("apply_presets"):
        preset = ACADEMIC_UNIT_PRESETS.get(payload.get("school_model"), [])
        existing = {u["code"] async for u in db.academic_units.find({"institution_id": iid}, {"code": 1})}
        for i, u in enumerate(preset):
            if u["code"] in existing:
                continue
            await db.academic_units.insert_one({**u, "id": str(uuid.uuid4()), "institution_id": iid,
                                                "sort_order": i, "status": "active", "created_at": now_iso()})
            created += 1
    await audit(user, "update", "academic_config", iid, payload.get("school_model"))
    cfg = await db.academic_configuration.find_one({"institution_id": iid}, {"_id": 0})
    return {"config": cfg, "units_created": created}


# Phase-5 structural presets: create academic units + grades (classes) + a default "A" section.
PHASE5_PRESETS = {
    "lp_up_hs_hss": [
        {"name": "LP", "code": "LP", "grades": [1, 2, 3, 4]},
        {"name": "UP", "code": "UP", "grades": [5, 6, 7]},
        {"name": "HS", "code": "HS", "grades": [8, 9, 10]},
        {"name": "HSS", "code": "HSS", "grades": [11, 12]},
    ],
    "k12": [
        {"name": "K-12", "code": "K12", "grades": list(range(1, 13))},
    ],
}


class ApplyPresetRequest(BaseModel):
    preset: Literal["lp_up_hs_hss", "k12"]


@api.post("/institution/apply-preset")
async def apply_academic_preset(body: ApplyPresetRequest,
                                user: dict = Depends(require_roles("institution_admin"))):
    """Merge a structural preset: create only missing units/grades/sections (case-insensitive
    match by unit name and class name). Never duplicates or deletes. Idempotent."""
    iid = user["institution_id"]
    if await _setup_is_complete(user["institution_id"]):
        raise HTTPException(status_code=409, detail=PRESET_LOCKED)
    spec = PHASE5_PRESETS[body.preset]

    ex_units = {}
    async for u in db.academic_units.find({"institution_id": iid}):
        ex_units[(u.get("name") or "").strip().lower()] = u
    ex_classes = {}
    async for c in db.classes.find({"institution_id": iid}):
        ex_classes[(c.get("name") or "").strip().lower()] = c
    ex_sections = set()
    async for s in db.sections.find({"institution_id": iid}):
        ex_sections.add(((s.get("class_name") or "").strip().lower(), (s.get("name") or "").strip().lower()))

    summary = {"units_created": 0, "units_skipped": 0, "classes_created": 0,
               "classes_skipped": 0, "sections_created": 0}

    for i, unit in enumerate(spec):
        uname = unit["name"]
        ukey = uname.strip().lower()
        udoc = ex_units.get(ukey)
        if udoc:
            uid = udoc["id"]
            summary["units_skipped"] += 1
        else:
            uid = str(uuid.uuid4())
            await db.academic_units.insert_one({"id": uid, "institution_id": iid, "name": uname,
                "code": unit["code"], "sort_order": i, "status": "active", "created_at": now_iso()})
            ex_units[ukey] = {"id": uid, "name": uname}
            summary["units_created"] += 1
        for grade in unit["grades"]:
            cname = f"Grade {grade}"
            ckey = cname.strip().lower()
            if ckey in ex_classes:
                summary["classes_skipped"] += 1
            else:
                await db.classes.insert_one({"id": str(uuid.uuid4()), "institution_id": iid, "name": cname,
                    "grade_level": str(grade), "academic_unit_id": uid, "academic_unit_name": uname,
                    "status": "active", "created_at": now_iso()})
                ex_classes[ckey] = {"name": cname}
                summary["classes_created"] += 1
            if (ckey, "a") not in ex_sections:
                await db.sections.insert_one({"id": str(uuid.uuid4()), "institution_id": iid, "name": "A",
                    "class_name": cname, "status": "active", "created_at": now_iso()})
                ex_sections.add((ckey, "a"))
                summary["sections_created"] += 1

    await audit(user, "apply_preset", "academic_config", iid, body.preset)
    return {"preset": body.preset, "summary": summary}


async def _setup_is_complete(iid):
    async def has(col):
        return await db[col].count_documents({"institution_id": iid}, limit=1) > 0
    inst = await db.institutions.find_one({"id": iid}, {"_id": 0, "contact_email": 1, "phone": 1}) or {}
    return bool(inst.get("contact_email") and inst.get("phone")) and await has("academic_configuration") \
        and all([await has(c) for c in ("academic_years", "academic_units", "classes", "sections", "subjects")])


PRESET_LOCKED = "Presets are only available while the setup wizard is in progress — add or edit academic units individually instead"


@api.get("/institution/setup-status")
async def setup_status(user: dict = Depends(require_roles("institution_admin"))):
    iid = user["institution_id"]
    inst = await db.institutions.find_one({"id": iid}, {"_id": 0}) or {}
    cfg = await db.academic_configuration.find_one({"institution_id": iid})

    async def cnt(col, q=None):
        return await db[col].count_documents({"institution_id": iid, **(q or {})})

    steps = {
        "profile": bool(inst.get("contact_email") and inst.get("phone")),
        "academic_config": bool(cfg),
        "academic_year": await cnt("academic_years") > 0,
        "academic_units": await cnt("academic_units") > 0,
        "classes": await cnt("classes") > 0,
        "sections": await cnt("sections") > 0,
        "subjects": await cnt("subjects") > 0,
        "teachers": await cnt("users", {"role": "teacher"}) > 0,
        "teacher_assignments": await cnt("teacher_assignments") > 0,
    }
    setup_complete = all(steps[k] for k in ("profile", "academic_config", "academic_year",
                                            "academic_units", "classes", "sections", "subjects"))
    operationally_ready = setup_complete and steps["teachers"] and steps["teacher_assignments"]
    return {
        "steps": steps,
        "setup_complete": setup_complete,
        "operationally_ready": operationally_ready,
        "migrated_general_unit": bool((inst.get("setup") or {}).get("migrated_general_unit")),
        "counts": {"classes": await cnt("classes"), "sections": await cnt("sections"),
                   "subjects": await cnt("subjects"), "academic_units": await cnt("academic_units"),
                   "teachers": await cnt("users", {"role": "teacher"})},
    }


# ---------------- Stats & audit ----------------

@api.get("/platform/stats")
async def platform_stats(user: dict = Depends(require_roles("platform_admin"))):
    stats = {}
    for col in ("institutions", "plans", "users"):
        stats[col] = await db[col].count_documents({})
    recent = await db.audit_logs.find({}, {"_id": 0}).sort("timestamp", -1).to_list(6)
    return {"counts": stats, "recent_activity": recent}


@api.get("/institution/stats")
async def institution_stats(user: dict = Depends(require_admin_or_principal)):
    iid = user["institution_id"]
    base = {"institution_id": iid}
    scope = await principal_scope(user)
    stats = {}
    if scope and not scope["whole_school"]:
        cns = scope["class_names"] or ["__none__"]
        stats["students"] = await db.students.count_documents({**base, "class_name": {"$in": cns}})
        stats["classes"] = await db.classes.count_documents({**base, "academic_unit_id": {"$in": scope["unit_ids"]}})
        stats["sections"] = await db.sections.count_documents({**base, "class_name": {"$in": cns}})
        stats["subjects"] = await db.subjects.count_documents(base)
        tas = await db.teacher_assignments.find({**base, "class_name": {"$in": cns}}, {"teacher_id": 1}).to_list(5000)
        stats["teachers"] = len({a.get("teacher_id") for a in tas if a.get("teacher_id")})
        stats["users"] = stats["teachers"]
    else:
        for col in ("students", "classes", "sections", "subjects", "users"):
            stats[col] = await db[col].count_documents(base)
        stats["teachers"] = await db.users.count_documents({**base, "role": "teacher"})
    recent = await db.audit_logs.find(base, {"_id": 0}).sort("timestamp", -1).to_list(6)
    return {"counts": stats, "recent_activity": recent}


@api.get("/audit")
async def list_audit(page: int = 1, limit: int = 25,
                     user: dict = Depends(get_current_user)):
    # Admins + platform admins, plus principals (institution-wide read within their institution).
    if user["role"] not in ("platform_admin", "institution_admin") and not await active_principal(user):
        raise HTTPException(status_code=403, detail="Access denied")
    query = {}
    if user["role"] != "platform_admin":
        query["institution_id"] = user["institution_id"]
    total = await db.audit_logs.count_documents(query)
    skip = max(page - 1, 0) * limit
    items = await db.audit_logs.find(query, {"_id": 0}).sort("timestamp", -1).skip(skip).to_list(limit)
    return {"items": items, "total": total, "page": page, "pages": max((total + limit - 1) // limit, 1)}


# ---------------- Student create + enroll ----------------

@api.post("/students/enroll")
async def create_student_with_enrollment(payload: dict = Body(...),
                                         user: dict = Depends(require_admin_or_principal)):
    iid = user["institution_id"]
    enroll = bool(payload.pop("enroll", False))
    _scope = await principal_scope(user)
    if _scope and not _scope["whole_school"]:
        if not enroll or not payload.get("class_name"):
            raise HTTPException(status_code=400, detail="Enroll the student into one of your assigned classes")
        if payload.get("class_name") not in (_scope["class_names"] or []):
            raise HTTPException(status_code=403, detail="This class is outside your assigned scope")
    year = payload.pop("academic_year", None)
    payload.pop("academic_unit_id", None)
    profile = {k: v for k, v in payload.items() if k not in PROTECTED_KEYS}
    if not profile.get("first_name"):
        raise HTTPException(status_code=400, detail="First name is required")
    class_name = profile.get("class_name")
    section = profile.get("section")
    student = {**profile, "id": str(uuid.uuid4()), "institution_id": iid, "created_at": now_iso()}
    await _assert_adm_unique(iid, student.get("admission_no"))
    if student.get("admission_no"):
        student["admission_no"] = str(student["admission_no"]).strip()
    if not str(student.get("admission_no") or "").strip():
        prefix, taken = await _adm_ctx(iid)
        student["admission_no"] = _next_adm(prefix, class_name if enroll else None, taken)
    if enroll:
        if not class_name:
            raise HTTPException(status_code=400, detail="Select a class to enroll the student")
        if not await _class_exists(iid, class_name):
            raise HTTPException(status_code=400, detail="Selected class does not exist")
        student.update({"enrollment_status": "enrolled", "academic_year": year,
                        "class_name": class_name, "section": section})
    else:
        student["enrollment_status"] = "not_enrolled"
        student.pop("class_name", None)
        student.pop("section", None)
    await db.students.insert_one(student)
    student.pop("_id", None)
    if enroll:
        await db.enrollments.insert_one({
            "id": str(uuid.uuid4()), "institution_id": iid, "student_id": student["id"],
            "student_name": f"{student.get('first_name', '')} {student.get('last_name', '')}".strip(),
            "admission_no": student.get("admission_no"), "academic_year": year,
            "class_name": class_name, "section": section, "created_at": now_iso()})
    await audit(user, "create", "students", student["id"], student.get("first_name"))
    if enroll:
        w = await _capacity_warning(iid, class_name, section)
        if w:
            student["warning"] = w
    return student


# ---------------- Bulk student import ----------------

@api.post("/students/bulk-enroll")
async def bulk_enroll_students(payload: dict = Body(...),
                               user: dict = Depends(require_admin_or_principal)):
    iid = user["institution_id"]
    class_name = payload.get("class_name")
    section = payload.get("section")
    year = payload.get("academic_year")
    rows = payload.get("students") or []
    if not class_name or not await _class_exists(iid, class_name):
        raise HTTPException(status_code=400, detail="Select a valid class to import into")
    await guard_principal_class(user, class_name)
    if not rows:
        raise HTTPException(status_code=400, detail="No student rows to import")
    if len(rows) > 2000:
        raise HTTPException(status_code=400, detail="Too many rows in one file — please split into batches of 2000 or fewer")
    existing = set()
    async for s in db.students.find({"institution_id": iid, "admission_no": {"$nin": [None, ""]}}, {"admission_no": 1}):
        existing.add(str(s.get("admission_no")).strip())
    fields = ("first_name", "last_name", "admission_no", "email", "date_of_birth",
              "gender", "guardian_name", "guardian_phone", "guardian_email", "address")
    created = 0
    skipped = []
    seen = set()
    students_docs = []
    enroll_docs = []
    adm_prefix, reserved = await _adm_ctx(iid)
    reserved |= {str(r.get("admission_no") or "").strip() for r in rows if str(r.get("admission_no") or "").strip()}
    for i, r in enumerate(rows):
        fn = str(r.get("first_name") or "").strip()
        adm = str(r.get("admission_no") or "").strip()
        if not fn:
            skipped.append({"row": i + 1, "reason": "Missing first name"})
            continue
        if adm and (adm in existing or adm in seen):
            skipped.append({"row": i + 1, "reason": f"Duplicate admission no '{adm}'"})
            continue
        if not adm:
            adm = _next_adm(adm_prefix, class_name, reserved)
        seen.add(adm)
        profile = {k: str(r.get(k) or "").strip() for k in fields}
        profile["admission_no"] = adm
        sid = str(uuid.uuid4())
        students_docs.append({**profile, "id": sid, "institution_id": iid, "created_at": now_iso(),
                              "enrollment_status": "enrolled", "academic_year": year,
                              "class_name": class_name, "section": section})
        enroll_docs.append({"id": str(uuid.uuid4()), "institution_id": iid, "student_id": sid,
                            "student_name": f"{fn} {profile.get('last_name', '')}".strip(),
                            "admission_no": adm or None, "academic_year": year,
                            "class_name": class_name, "section": section, "created_at": now_iso()})
        created += 1
    if students_docs:
        await db.students.insert_many(students_docs)
        await db.enrollments.insert_many(enroll_docs)
    await audit(user, "import", "students", class_name, f"{created} students into {class_name}")
    warning = await _capacity_warning(iid, class_name, section)
    bitems = [phase59.item(d["id"], f"{d.get('first_name', '')} {d.get('last_name', '')}".strip(), "created", "Student created and enrolled", "created",
                           f"{d.get('admission_no') or '—'} · {d.get('class_name') or ''} {d.get('section') or ''}".strip(), phase59.fix("open_student", d["id"]))
              for d in students_docs]
    bitems += [phase59.item(f"row-{k['row']}", f"Row {k['row']}", "skipped", k["reason"], "row_error", None, None) for k in skipped]
    run = await phase59.save_run(user, "student_import", f"Student import · {class_name}", bitems)
    return {"created": created, "skipped": skipped, "total": len(rows), **({"warning": warning} if warning else {}), "run_id": run["run_id"],
            "items": run["items"], "summary": run["summary"]}


@api.post("/subject-offerings/bulk")
async def bulk_offer_subject(payload: dict = Body(...),
                             user: dict = Depends(require_admin_or_principal)):
    iid = user["institution_id"]
    subject = str(payload.get("subject") or "").strip()
    class_names = payload.get("class_names") or []
    section = str(payload.get("section") or "").strip()
    if not subject:
        raise HTTPException(status_code=400, detail="Select a subject to offer")
    if not class_names:
        raise HTTPException(status_code=400, detail="Select at least one class")
    _scope = await principal_scope(user)
    if _scope and not _scope["whole_school"]:
        _bad = [c for c in class_names if c not in (_scope["class_names"] or [])]
        if _bad:
            raise HTTPException(status_code=403, detail="Outside your assigned scope: " + ", ".join(_bad))
    base = {"has_practical": payload.get("has_practical"),
            "theory_max_marks": payload.get("theory_max_marks"),
            "practical_max_marks": payload.get("practical_max_marks"),
            "max_marks": payload.get("max_marks")}
    created = 0
    skipped = []
    for cn in class_names:
        if not await _class_exists(iid, cn):
            skipped.append({"class": cn, "reason": "Class not found"})
            continue
        dup = await db.subject_offerings.find_one({"institution_id": iid, "class_name": cn,
                                                   "section": section, "subject": subject})
        if dup:
            skipped.append({"class": cn, "reason": "Already offered"})
            continue
        doc = {"id": str(uuid.uuid4()), "institution_id": iid, "created_at": now_iso(),
               "subject": subject, "class_name": cn, "section": section, **base}
        normalize_offering_marks(doc)
        await db.subject_offerings.insert_one(doc)
        created += 1
    await audit(user, "bulk_offer", "subject_offerings", subject, f"{subject} → {created} classes")
    return {"created": created, "skipped": skipped, "total": len(class_names)}


# ---------------- Bulk subject import ----------------

SUBJECT_TYPES = {"core", "elective", "language", "practical"}


def _subject_code_base(name):
    words = [w for w in re.split(r"[^A-Za-z0-9]+", name or "") if w]
    return ("".join(w[0] for w in words)[:4] if len(words) > 1 else (words[0][:4] if words else "SUB")).upper()


@api.post("/subjects/bulk-import")
async def bulk_import_subjects(payload: dict = Body(...),
                               user: dict = Depends(require_admin_or_principal)):
    iid = user["institution_id"]
    rows = payload.get("subjects") or []
    if not rows:
        raise HTTPException(status_code=400, detail="No subject rows to import")
    if len(rows) > 1000:
        raise HTTPException(status_code=400, detail="Too many rows in one file — please split into batches of 1000 or fewer")
    existing_names, existing_codes = set(), set()
    async for s in db.subjects.find({"institution_id": iid}, {"name": 1, "code": 1}):
        if s.get("name"):
            existing_names.add(str(s["name"]).strip().lower())
        if s.get("code"):
            existing_codes.add(str(s["code"]).strip().upper())
    docs, skipped = [], []
    for i, r in enumerate(rows):
        name = str(r.get("name") or "").strip()
        if not name:
            skipped.append({"row": i + 1, "reason": "Missing subject name"})
            continue
        key = name.lower()
        if key in existing_names:
            skipped.append({"row": i + 1, "reason": f"Subject '{name}' already exists"})
            continue
        code = str(r.get("code") or "").strip().upper()
        if code and code in existing_codes:
            skipped.append({"row": i + 1, "reason": f"Duplicate code '{code}'"})
            continue
        if not code:
            base = _subject_code_base(name)
            code, n = base, 1
            while code in existing_codes:
                n += 1
                code = f"{base}{n}"
        typ = str(r.get("type") or "core").strip().lower()
        if typ not in SUBJECT_TYPES:
            typ = "core"
        try:
            dmm = int(float(r.get("default_max_marks") or 100))
        except (TypeError, ValueError):
            dmm = 100
        existing_names.add(key)
        existing_codes.add(code)
        docs.append({"id": str(uuid.uuid4()), "institution_id": iid, "created_at": now_iso(),
                     "name": name, "code": code, "type": typ, "default_max_marks": dmm, "status": "active"})
    if docs:
        await db.subjects.insert_many(docs)
    await audit(user, "import", "subjects", None, f"{len(docs)} subjects imported")
    return {"created": len(docs), "skipped": skipped, "total": len(rows)}


# ---------------- Student utilities: admission no, filter, portal ----------------

async def _adm_ctx(iid):
    """School admission-no prefix (institution code, else name initials) + set of taken numbers."""
    inst = await db.institutions.find_one({"id": iid}, {"name": 1, "code": 1}) or {}
    prefix = re.sub(r"[^A-Z0-9]", "", (inst.get("code") or "").upper())
    if not prefix:
        words = [w for w in (inst.get("name") or "").split() if w]
        prefix = ("".join(w[0] for w in words)[:3].upper()) or "STU"
    taken = {str(a).strip() for a in await db.students.distinct("admission_no", {"institution_id": iid}) if a}
    return prefix, taken


def _next_adm(prefix, class_name, taken):
    """Next free {CODE}-G{grade}-{nnn} (e.g. LPGS-G8-003); reserves it in `taken`."""
    m = re.search(r"\d+", class_name or "")
    base = f"{prefix}-G{int(m.group())}" if m else f"{prefix}-GX"
    n = 1
    while f"{base}-{n:03d}" in taken:
        n += 1
    taken.add(f"{base}-{n:03d}")
    return f"{base}-{n:03d}"


async def _backfill_admission_nos(iid):
    """Idempotent: assign admission numbers only to students that have none."""
    prefix, taken = await _adm_ctx(iid)
    missing = await db.students.find({"institution_id": iid, "$or": [{"admission_no": {"$exists": False}},
                                      {"admission_no": None}, {"admission_no": ""}]},
                                     {"_id": 0, "id": 1, "class_name": 1, "created_at": 1}).to_list(50000)
    missing.sort(key=lambda s: (s.get("class_name") or "~", s.get("created_at") or ""))
    assigned = []
    for s in missing:
        adm = _next_adm(prefix, s.get("class_name"), taken)
        await db.students.update_one({"id": s["id"]}, {"$set": {"admission_no": adm}})
        await db.enrollments.update_many({"student_id": s["id"], "$or": [{"admission_no": None}, {"admission_no": ""},
                                          {"admission_no": {"$exists": False}}]}, {"$set": {"admission_no": adm}})
        assigned.append({"student_id": s["id"], "admission_no": adm})
    return assigned


@api.get("/students/next-admission-no")
async def next_admission_no(class_name: str = "", user: dict = Depends(require_admin_or_principal)):
    prefix, taken = await _adm_ctx(user["institution_id"])
    return {"admission_no": _next_adm(prefix, class_name, taken), "class_dependent": True,
            "provisional": not re.search(r"\d+", class_name or "")}


async def _assert_adm_unique(iid, adm, exclude_id=None):
    """Admission numbers are unique per institution (case-insensitive, trimmed)."""
    a = str(adm or "").strip()
    if not a:
        return
    q = {"institution_id": iid, "admission_no": {"$regex": f"^\\s*{re.escape(a)}\\s*$", "$options": "i"}}
    if exclude_id:
        q["id"] = {"$ne": exclude_id}
    if await db.students.find_one(q, {"_id": 1}):
        raise HTTPException(status_code=409, detail=f"Admission number {a} is already used by another student")


@api.post("/students/backfill-admission-nos")
async def backfill_admission_nos(user: dict = Depends(require_roles("institution_admin"))):
    assigned = await _backfill_admission_nos(user["institution_id"])
    await audit(user, "backfill_admission_nos", "students", None, f"{len(assigned)} assigned", user["institution_id"])
    return {"assigned": len(assigned), "items": assigned}


@api.get("/institution/generate-login")
async def generate_login(name: str = "", user: dict = Depends(require_admin_or_principal)):
    inst = await db.institutions.find_one({"id": user["institution_id"]}, {"domain": 1}) or {}
    domain = (inst.get("domain") or "").strip().lstrip("@").lower()
    if not domain:
        raise HTTPException(status_code=400, detail="Set the institution domain first (Platform Console → Institution → Domain & Access).")
    slug = re.sub(r"[^a-z0-9]+", ".", (name or "").strip().lower()).strip(".") or "user"
    email = f"{slug}@{domain}"
    n = 1
    while await db.users.find_one({"email": email}):
        n += 1
        email = f"{slug}{n}@{domain}"
    return {"email": email}


@api.get("/students/filter")
async def filter_students(class_name: str = "", section: str = "", subject: str = "",
                          search: str = "", status: str = "", page: int = 1, limit: int = 15,
                          user: dict = Depends(require_admin_or_principal)):
    iid = user["institution_id"]
    query = {"institution_id": iid}
    if status:
        query["enrollment_status"] = status
    if class_name:
        query["class_name"] = class_name
    if section:
        query["section"] = section
    if subject:
        offs = await db.subject_offerings.find({"institution_id": iid, "subject": subject}, {"class_name": 1}).to_list(500)
        subj_classes = {o["class_name"] for o in offs}
        if class_name:
            if class_name not in subj_classes:
                query["class_name"] = {"$in": []}
        else:
            query["class_name"] = {"$in": list(subj_classes)}
    if search:
        rx = {"$regex": re.escape(search), "$options": "i"}
        query["$or"] = [{"first_name": rx}, {"last_name": rx}, {"admission_no": rx}]
    _scope = await principal_scope(user)
    if _scope and not _scope["whole_school"]:
        _allowed = set(_scope["class_names"] or [])
        _cn = query.get("class_name")
        if isinstance(_cn, str):
            if _cn not in _allowed:
                query["class_name"] = {"$in": []}
        elif isinstance(_cn, dict) and "$in" in _cn:
            query["class_name"] = {"$in": [c for c in _cn["$in"] if c in _allowed]}
        else:
            query["class_name"] = {"$in": list(_allowed) or ["__none__"]}
    total = await db.students.count_documents(query)
    skip = (page - 1) * limit
    rows = await db.students.find(query, {"_id": 0, "password_hash": 0}).sort("first_name", 1).skip(skip).limit(limit).to_list(limit)
    pages = max(1, (total + limit - 1) // limit)
    return {"items": rows, "total": total, "page": page, "pages": pages}


@api.post("/students/{student_id}/portal-user")
async def create_student_portal_user(student_id: str, payload: dict = Body(...),
                                     user: dict = Depends(require_admin_or_principal)):
    iid = user["institution_id"]
    student = await db.students.find_one({"id": student_id, "institution_id": iid})
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    await guard_principal_class(user, student.get("class_name"))
    if student.get("has_portal_access"):
        raise HTTPException(status_code=400, detail="This student already has a portal login")
    email = (payload.get("email") or "").strip().lower()
    password = payload.get("password") or ""
    if not email or not password:
        raise HTTPException(status_code=400, detail="Email and password are required")
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Email already in use")
    uid = str(uuid.uuid4())
    name = f"{student.get('first_name', '')} {student.get('last_name', '')}".strip() or email
    await db.users.insert_one({"id": uid, "name": name, "email": email,
                               "password_hash": hash_password(password), "role": "student",
                               "student_id": student_id, "institution_id": iid,
                               "status": "active", "created_at": now_iso()})
    await db.students.update_one({"id": student_id}, {"$set": {"has_portal_access": True, "portal_email": email, "user_id": uid}})
    await audit(user, "create", "portal_user", uid, name)
    return {"id": uid, "email": email, "name": name}


@api.delete("/students/{student_id}/portal-user")
async def revoke_student_portal_user(student_id: str, user: dict = Depends(require_admin_or_principal)):
    iid = user["institution_id"]
    student = await db.students.find_one({"id": student_id, "institution_id": iid})
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    await guard_principal_class(user, student.get("class_name"))
    await db.users.delete_many({"student_id": student_id, "institution_id": iid})
    await db.students.update_one({"id": student_id},
                                 {"$set": {"has_portal_access": False}, "$unset": {"portal_email": "", "user_id": ""}})
    await audit(user, "delete", "portal_user", student_id, student.get("first_name"))
    return {"message": "Portal login revoked"}


def _slugify_email_part(val):
    import re
    s = re.sub(r"[^a-z0-9]+", "", (val or "").strip().lower())
    return s


async def _unique_portal_email(iid, first, last, domain, used):
    base = ".".join([p for p in (_slugify_email_part(first), _slugify_email_part(last)) if p]) or "student"
    cand = f"{base}@{domain}"
    n = 1
    while cand in used or await db.users.find_one({"email": cand}):
        n += 1
        cand = f"{base}{n}@{domain}"
    used.add(cand)
    return cand


class BulkPortalBody(BaseModel):
    password: str = "student123"
    class_name: Optional[str] = None
    section: Optional[str] = None
    clear_must_change: bool = True


@api.post("/students/bulk-portal-users")
async def bulk_create_portal_users(body: BulkPortalBody, user: dict = Depends(require_admin_or_principal)):
    """Create portal logins for every ENROLLED student (in scope) that lacks one.
    Returns the full roster incl. generated email + the shared password (for a credentials handout)."""
    iid = user["institution_id"]
    inst = await db.institutions.find_one({"id": iid}, {"_id": 0, "domain": 1})
    domain = (inst or {}).get("domain") or "school.local"
    q = {"institution_id": iid, "enrollment_status": "enrolled"}
    if body.class_name:
        q["class_name"] = body.class_name
    if body.section:
        q["section"] = body.section
    scope = await principal_scope(user)
    if scope and not scope.get("whole_school"):
        q["class_name"] = {"$in": scope.get("class_names") or ["__none__"]}
    students = await db.students.find(q, {"_id": 0}).to_list(20000)
    used = set()
    created, existing = [], []
    for s in sorted(students, key=lambda x: (x.get("class_name", ""), x.get("section", ""), x.get("first_name", ""))):
        name = f"{s.get('first_name','')} {s.get('last_name','')}".strip()
        cls = s.get("class_name") or ""
        sec = s.get("section") or ""
        if s.get("has_portal_access"):
            existing.append({"student_id": s["id"], "name": name, "class": cls, "section": sec,
                             "admission_no": s.get("admission_no"), "email": s.get("portal_email"), "status": "existing"})
            continue
        email = await _unique_portal_email(iid, s.get("first_name"), s.get("last_name"), domain, used)
        uid = str(uuid.uuid4())
        await db.users.insert_one({"id": uid, "name": name or email, "email": email,
                                   "password_hash": hash_password(body.password), "role": "student",
                                   "student_id": s["id"], "institution_id": iid, "status": "active",
                                   "must_change_password": not body.clear_must_change, "created_at": now_iso()})
        await db.students.update_one({"id": s["id"]}, {"$set": {"has_portal_access": True, "portal_email": email, "user_id": uid}})
        created.append({"student_id": s["id"], "name": name, "class": cls, "section": sec,
                        "admission_no": s.get("admission_no"), "email": email,
                        "password": body.password, "status": "created"})
    await audit(user, "bulk_create", "portal_user", None, f"{len(created)} logins created")
    return {"created_count": len(created), "existing_count": len(existing),
            "password": body.password, "created": created, "existing": existing}


@api.get("/students/portal-credentials")
async def student_portal_credentials(user: dict = Depends(require_admin_or_principal)):
    """Roster of students + their portal email (for a downloadable credentials list)."""
    iid = user["institution_id"]
    q = {"institution_id": iid, "enrollment_status": "enrolled"}
    scope = await principal_scope(user)
    if scope and not scope.get("whole_school"):
        q["class_name"] = {"$in": scope.get("class_names") or ["__none__"]}
    students = await db.students.find(q, {"_id": 0}).to_list(20000)
    rows = [{"name": f"{s.get('first_name','')} {s.get('last_name','')}".strip(),
             "admission_no": s.get("admission_no"), "class": s.get("class_name"),
             "section": s.get("section"), "email": s.get("portal_email") or "",
             "has_portal": bool(s.get("has_portal_access"))}
            for s in sorted(students, key=lambda x: (x.get("class_name", ""), x.get("section", ""), x.get("first_name", "")))]
    return {"students": rows, "total": len(rows),
            "with_portal": sum(1 for r in rows if r["has_portal"])}


@api.get("/portal/me")
async def portal_me(user: dict = Depends(require_roles("student"))):
    iid = user["institution_id"]
    sid = user.get("student_id")
    student = await db.students.find_one({"id": sid, "institution_id": iid}, {"_id": 0, "password_hash": 0}) if sid else None
    if not student:
        raise HTTPException(status_code=404, detail="No student profile linked to this account")
    results = []
    async for m in db.marks.find({"student_id": sid}):
        a = await db.assessments.find_one({"id": m["assessment_id"], "institution_id": iid}, {"_id": 0})
        if a and a.get("status") == "published":
            results.append({"assessment": a.get("name"), "subject": a.get("subject"),
                            "max_marks": a.get("max_marks"), "score": m.get("score"),
                            "date": a.get("exam_date") or a.get("date"), "created_at": a.get("created_at")})
    present, total = 0, 0
    history = []
    async for sh in db.attendance.find({"institution_id": iid, "class_name": student.get("class_name"), "section": student.get("section")}):
        ent = sh.get("entries") or {}
        if sid in ent:
            total += 1
            if str(ent[sid]).lower() in ("present", "p"):
                present += 1
            history.append({"date": sh.get("date"), "status": ent[sid]})
    history.sort(key=lambda x: x["date"] or "", reverse=True)
    pct = round(present / total * 100) if total else None
    achievements = await db.achievements.find({"institution_id": iid, "student_id": sid}, {"_id": 0}) \
        .sort([("date", -1), ("created_at", -1)]).to_list(200)
    leader_role = None
    sec = await db.sections.find_one({"institution_id": iid, "class_name": student.get("class_name"),
                                      "name": student.get("section")}, {"_id": 0})
    if sec:
        if sec.get("class_leader_id") == sid:
            leader_role = "class_leader"
        elif sec.get("second_leader_id") == sid:
            leader_role = "second_leader"
    inst = await db.institutions.find_one({"id": iid}, {"_id": 0, "name": 1, "portal_name": 1, "primary_color": 1, "logo_url": 1, "logo_path": 1, "domain": 1}) or {}
    subjects = []
    if student.get("class_name"):
        offs = await db.subject_offerings.find(
            {"institution_id": iid, "class_name": student["class_name"],
             "$or": [{"section": {"$in": [None, ""]}}, {"section": student.get("section")}]},
            {"_id": 0}).sort("subject", 1).to_list(100)
        for o in offs:
            asq = {"institution_id": iid, "class_name": student["class_name"], "subject": o["subject"],
                   "$or": [{"section": {"$in": [None, ""]}}, {"section": student.get("section")}]}
            asg = await db.teacher_assignments.find_one(asq, {"_id": 0})
            subjects.append({"subject": o["subject"], "type": o.get("type"), "max_marks": o.get("max_marks"),
                             "has_practical": bool(o.get("has_practical")),
                             "teacher_name": (asg or {}).get("teacher_name")})
    return {"student": student, "results": results,
            "attendance": {"present": present, "total": total, "pct": pct},
            "attendance_history": history[:30],
            "subjects": subjects,
            "achievements": achievements, "leader_role": leader_role,
            "branding": {"portal_name": inst.get("portal_name") or inst.get("name"),
                         "primary_color": inst.get("primary_color"), "logo_url": inst.get("logo_url"),
                         "has_logo": bool(inst.get("logo_path")), "domain": inst.get("domain")}}


@api.get("/public/branding")
async def public_branding(domain: str = "", slug: str = ""):
    q = None
    if slug.strip():
        q = {"slug": slug.strip().lower()}
    elif domain.strip():
        q = {"domain": domain.strip().lstrip("@").lower()}
    if not q:
        return {}
    inst = await db.institutions.find_one(
        q, {"_id": 0, "name": 1, "portal_name": 1, "primary_color": 1, "logo_url": 1,
            "logo_path": 1, "domain": 1, "slug": 1})
    if not inst:
        return {}
    return {"name": inst.get("portal_name") or inst.get("name"),
            "primary_color": inst.get("primary_color"),
            "logo_url": inst.get("logo_url"),
            "has_logo": bool(inst.get("logo_path")),
            "domain": inst.get("domain"), "slug": inst.get("slug")}


# ---------------- Timetable ----------------

TT_DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
TT_DAY_LABELS = {"mon": "Monday", "tue": "Tuesday", "wed": "Wednesday", "thu": "Thursday",
                 "fri": "Friday", "sat": "Saturday", "sun": "Sunday"}
# Phase 9: entries carry an additive `publish_state` ("draft"|"published"). Legacy entries have no
# field → treated as published. (We could NOT reuse `status`, which already means active/inactive.)
PUBLISHED_MATCH = {"publish_state": {"$in": [None, "published"]}}
DEFAULT_WORKING_DAYS = ["mon", "tue", "wed", "thu", "fri"]
DEFAULT_PERIODS = [
    {"label": "P1", "start": "09:00", "end": "09:45", "is_break": False},
    {"label": "P2", "start": "09:45", "end": "10:30", "is_break": False},
    {"label": "P3", "start": "10:30", "end": "11:15", "is_break": False},
    {"label": "Break", "start": "11:15", "end": "11:30", "is_break": True},
    {"label": "P4", "start": "11:30", "end": "12:15", "is_break": False},
    {"label": "P5", "start": "12:15", "end": "13:00", "is_break": False},
    {"label": "Lunch", "start": "13:00", "end": "13:45", "is_break": True},
    {"label": "P6", "start": "13:45", "end": "14:30", "is_break": False},
    {"label": "P7", "start": "14:30", "end": "15:15", "is_break": False},
]


async def effective_tt_config(iid: str, academic_year: str, academic_unit_id: str = None):
    cfg = None
    if academic_unit_id:
        cfg = await db.timetable_configs.find_one(
            {"institution_id": iid, "academic_year": academic_year, "academic_unit_id": academic_unit_id}, {"_id": 0})
    if not cfg:
        cfg = await db.timetable_configs.find_one(
            {"institution_id": iid, "academic_year": academic_year, "academic_unit_id": None}, {"_id": 0})
    if not cfg:
        cfg = {"academic_year": academic_year, "academic_unit_id": None,
               "working_days": DEFAULT_WORKING_DAYS, "periods": DEFAULT_PERIODS, "is_default": True}
    return cfg


@api.get("/timetable/config")
async def get_tt_config(academic_year: str, academic_unit_id: str = "",
                        user: dict = Depends(require_roles("institution_admin", "teacher"))):
    iid = user["institution_id"]
    explicit = await db.timetable_configs.find_one(
        {"institution_id": iid, "academic_year": academic_year, "academic_unit_id": academic_unit_id or None}, {"_id": 0})
    cfg = explicit or await effective_tt_config(iid, academic_year, academic_unit_id or None)
    overrides = await db.timetable_configs.distinct(
        "academic_unit_id", {"institution_id": iid, "academic_year": academic_year, "academic_unit_id": {"$ne": None}})
    return {"config": cfg, "explicit": explicit is not None, "unit_overrides": overrides}


@api.post("/timetable/config")
async def save_tt_config(payload: dict = Body(...), user: dict = Depends(require_roles("institution_admin"))):
    iid = user["institution_id"]
    ay = (payload.get("academic_year") or "").strip()
    if not ay or not await db.academic_years.find_one({"institution_id": iid, "name": ay}):
        raise HTTPException(status_code=400, detail="Select a valid academic year")
    unit_id = payload.get("academic_unit_id") or None
    if unit_id and not await db.academic_units.find_one({"id": unit_id, "institution_id": iid}):
        raise HTTPException(status_code=400, detail="Selected academic unit does not exist")
    days = [d for d in (payload.get("working_days") or []) if d in TT_DAYS]
    if not days:
        raise HTTPException(status_code=400, detail="Pick at least one working day")
    periods = payload.get("periods") or []
    clean = []
    for p in periods:
        label = str(p.get("label") or "").strip()
        if not label:
            raise HTTPException(status_code=400, detail="Every period needs a label")
        clean.append({"label": label, "start": str(p.get("start") or "").strip(),
                      "end": str(p.get("end") or "").strip(), "is_break": bool(p.get("is_break"))})
    if not any(not p["is_break"] for p in clean):
        raise HTTPException(status_code=400, detail="Add at least one teaching (non-break) period")
    doc = {"institution_id": iid, "academic_year": ay, "academic_unit_id": unit_id,
           "working_days": days, "periods": clean, "updated_at": now_iso()}
    existing = await db.timetable_configs.find_one({"institution_id": iid, "academic_year": ay, "academic_unit_id": unit_id})
    if existing:
        await db.timetable_configs.update_one({"id": existing["id"]}, {"$set": doc})
        doc["id"] = existing["id"]
    else:
        doc["id"] = str(uuid.uuid4())
        doc["created_at"] = now_iso()
        await db.timetable_configs.insert_one(dict(doc))
    doc.pop("_id", None)
    await audit(user, "save", "timetable_configs", doc["id"], f"{ay}{' / unit override' if unit_id else ''}")
    return doc


# ---------------- Weekly subject requirements (Phase 7: timetable config layer) ----------------
# DATA MODEL: requirements live in a sibling collection `subject_requirements`, keyed by
# (institution_id, class_name, subject) — a class+subject (grade) level concept, independent of the
# per-section `subject_offerings` curriculum rows and the `teacher_assignments`/`timetable_entries`
# used by the manual builder (all left untouched). Each doc carries periods_per_week, consecutive
# rules and the teacher pool + optional per-section teacher map. academic_year is stored for
# reference and used only to resolve the teaching-slot budget (which can be unit/year specific).

class SubjectRequirementItem(BaseModel):
    subject: str
    periods_per_week: int
    consecutive_periods: int = 1
    must_be_consecutive: bool = False
    teacher_ids: List[str] = PField(default_factory=list)
    section_teachers: Dict[str, str] = PField(default_factory=dict)
    flexible: Optional[bool] = None
    min_periods: Optional[int] = None
    max_periods: Optional[int] = None


# Phase 12 — Auto-Balance. Subjects whose weekly period count can be trimmed/topped-up by the
# optional balancer. These names are the default flexible set (case-insensitive); an admin can
# override per subject in Class Hub. The balancer NEVER mutates subject_requirements — it only
# adjusts the generated draft entries and reports every change in auto_adjustments[].
FLEXIBLE_DEFAULTS = {
    "physical education", "health education", "art education", "music", "work education",
    "vocational education", "general knowledge", "library", "library period", "life skills",
    "value education",
}


def _is_flexible_default(subject: str) -> bool:
    n = (subject or "").strip().lower()
    if "library" in n:
        return True
    return n in FLEXIBLE_DEFAULTS


def _req_flexible(r: dict) -> bool:
    v = r.get("flexible")
    return bool(v) if v is not None else _is_flexible_default(r.get("subject", ""))


def _req_min(r: dict) -> int:
    v = r.get("min_periods")
    return max(0, int(v)) if v is not None else 1


def _req_max(r: dict, ppw: int) -> int:
    v = r.get("max_periods")
    return int(v) if v is not None else ppw + 2


class RequirementsSaveRequest(BaseModel):
    academic_year: str
    class_name: str
    items: List[SubjectRequirementItem] = PField(default_factory=list)


async def _teaching_slots(iid: str, academic_year: str, academic_unit_id):
    cfg = await effective_tt_config(iid, academic_year, academic_unit_id)
    days = len(cfg.get("working_days") or [])
    per_day = len([p for p in (cfg.get("periods") or []) if not p.get("is_break")])
    return days * per_day, days, per_day, cfg


async def _build_requirements_payload(iid: str, academic_year: str, class_name: str):
    cls = await db.classes.find_one({"institution_id": iid, "name": class_name}, {"_id": 0})
    if not cls:
        raise HTTPException(status_code=404, detail="Class not found")
    slots, days, per_day, _cfg = await _teaching_slots(iid, academic_year, cls.get("academic_unit_id"))
    offered = await db.subject_offerings.find(
        {"institution_id": iid, "class_name": class_name}, {"_id": 0, "subject": 1}).to_list(500)
    subjects = sorted({o["subject"] for o in offered})
    reqs = {r["subject"]: r for r in await db.subject_requirements.find(
        {"institution_id": iid, "class_name": class_name}, {"_id": 0}).to_list(500)}
    sections = [s["name"] for s in await db.sections.find(
        {"institution_id": iid, "class_name": class_name}, {"_id": 0, "name": 1}).sort("name", 1).to_list(200)]
    teachers = [{"id": t["id"], "name": t.get("name"), "email": t.get("email")}
                for t in await db.users.find(
                    {"institution_id": iid, "role": "teacher", "status": {"$ne": "inactive"}},
                    {"_id": 0, "id": 1, "name": 1, "email": 1}).sort("name", 1).to_list(1000)]
    items, total = [], 0
    for subj in subjects:
        r = reqs.get(subj)
        ppw = int(r["periods_per_week"]) if r else 0
        total += ppw
        items.append({
            "subject": subj,
            "periods_per_week": ppw,
            "consecutive_periods": (r.get("consecutive_periods") if r else 1) or 1,
            "must_be_consecutive": bool(r.get("must_be_consecutive")) if r else False,
            "teacher_ids": (r.get("teacher_ids") if r else []) or [],
            "section_teachers": (r.get("section_teachers") if r else {}) or {},
            "flexible": _req_flexible(r) if r else _is_flexible_default(subj),
            "min_periods": _req_min(r) if r else 1,
            "max_periods": _req_max(r, ppw) if r else ppw + 2,
            "configured": r is not None,
        })
    return {
        "class_name": class_name, "academic_unit_id": cls.get("academic_unit_id"),
        "academic_unit_name": cls.get("academic_unit_name"), "academic_year": academic_year,
        "slots": {"total": slots, "days": days, "periods_per_day": per_day},
        "total_required": total, "sections": sections, "teachers": teachers, "items": items,
    }


@api.get("/timetable/requirements")
async def get_tt_requirements(academic_year: str, class_name: str = "",
                              user: dict = Depends(require_admin_or_principal)):
    iid = user["institution_id"]
    if class_name:
        await guard_principal_class(user, class_name)
        return await _build_requirements_payload(iid, academic_year, class_name)
    q = {"institution_id": iid}
    apply_principal_scope_query("classes", q, await principal_scope(user))
    classes = await db.classes.find(q, {"_id": 0, "name": 1}).sort("name", 1).to_list(2000)
    out = [await _build_requirements_payload(iid, academic_year, c["name"]) for c in classes]
    return {"academic_year": academic_year, "classes": out}


@api.put("/timetable/requirements")
async def save_tt_requirements(body: RequirementsSaveRequest,
                               user: dict = Depends(require_admin_or_principal)):
    iid = user["institution_id"]
    ay = (body.academic_year or "").strip()
    cn = (body.class_name or "").strip()
    cls = await db.classes.find_one({"institution_id": iid, "name": cn}, {"_id": 0})
    if not cls:
        raise HTTPException(status_code=400, detail="Selected class does not exist")
    await guard_principal_class(user, cn)
    if not ay or not await db.academic_years.find_one({"institution_id": iid, "name": ay}):
        raise HTTPException(status_code=400, detail="Select a valid academic year")
    slots, days, per_day, _cfg = await _teaching_slots(iid, ay, cls.get("academic_unit_id"))
    offered = {o["subject"] for o in await db.subject_offerings.find(
        {"institution_id": iid, "class_name": cn}, {"_id": 0, "subject": 1}).to_list(500)}
    sections = {s["name"] for s in await db.sections.find(
        {"institution_id": iid, "class_name": cn}, {"_id": 0, "name": 1}).to_list(200)}
    active_teacher_ids = {t["id"] for t in await db.users.find(
        {"institution_id": iid, "role": "teacher", "status": {"$ne": "inactive"}}, {"_id": 0, "id": 1}).to_list(2000)}
    total, cleaned = 0, []
    for it in body.items:
        subj = it.subject.strip()
        if subj not in offered:
            raise HTTPException(status_code=400, detail=f"'{subj}' is not offered for {cn}. Add the subject offering first.")
        if it.periods_per_week < 1:
            raise HTTPException(status_code=400, detail=f"{subj}: periods per week must be a whole number of at least 1")
        if it.consecutive_periods < 1 or it.consecutive_periods > 3:
            raise HTTPException(status_code=400, detail=f"{subj}: consecutive periods must be 1, 2 or 3")
        if it.consecutive_periods > it.periods_per_week:
            raise HTTPException(status_code=400, detail=f"{subj}: consecutive periods ({it.consecutive_periods}) cannot exceed periods per week ({it.periods_per_week})")
        if it.must_be_consecutive and it.consecutive_periods == 1:
            raise HTTPException(status_code=400, detail=f"{subj}: 'must be consecutive' only applies when consecutive periods is 2 or more")
        for tid in it.teacher_ids:
            if tid not in active_teacher_ids:
                raise HTTPException(status_code=400, detail=f"{subj}: a selected teacher is not an active teacher of this institution")
        for sec, tid in (it.section_teachers or {}).items():
            if sec not in sections:
                raise HTTPException(status_code=400, detail=f"{subj}: section '{sec}' does not exist in {cn}")
            if tid not in active_teacher_ids:
                raise HTTPException(status_code=400, detail=f"{subj}: section '{sec}' is mapped to someone who is not an active teacher")
            if tid not in it.teacher_ids:
                raise HTTPException(status_code=400, detail=f"{subj}: section '{sec}' teacher must be one of the subject's selected teachers")
        total += it.periods_per_week
        cleaned.append((subj, it))
    if total > slots:
        raise HTTPException(status_code=400,
                            detail=f"{cn} needs {total} periods/week but only {slots} teaching slots exist ({days} day(s) × {per_day} period(s)). Reduce by {total - slots}.")
    kept = set()
    for subj, it in cleaned:
        kept.add(subj)
        fields = {"periods_per_week": it.periods_per_week, "consecutive_periods": it.consecutive_periods,
                  "must_be_consecutive": bool(it.must_be_consecutive),
                  "teacher_ids": list(dict.fromkeys(it.teacher_ids)),
                  "section_teachers": dict(it.section_teachers or {}),
                  "flexible": it.flexible, "min_periods": it.min_periods, "max_periods": it.max_periods,
                  "academic_year": ay, "updated_at": now_iso()}
        existing = await db.subject_requirements.find_one({"institution_id": iid, "class_name": cn, "subject": subj})
        if existing:
            await db.subject_requirements.update_one({"id": existing["id"]}, {"$set": fields})
        else:
            fields.update({"id": str(uuid.uuid4()), "institution_id": iid, "class_name": cn,
                           "subject": subj, "created_at": now_iso()})
            await db.subject_requirements.insert_one(dict(fields))
    await db.subject_requirements.delete_many(
        {"institution_id": iid, "class_name": cn, "subject": {"$nin": list(kept)}})
    await audit(user, "save_requirements", "subject_requirements", cn,
                f"{cn} · {len(kept)} subjects / {total} periods per week")
    return await _build_requirements_payload(iid, ay, cn)


# ---- Class Hub: consolidated per-section Subjects & Teachers surface ----
# ONE screen per grade. Writes land in BOTH teacher_assignments (canonical teacher↔class↔subject
# link, per section) AND are mirrored into subject_requirements (section_teachers + teacher_ids +
# periods/consecutive) so the Timetable Requirements read and the generator stay in sync. No data
# is duplicated: both surfaces read/write these same two collections.

class SubjectStaffItem(BaseModel):
    subject: str
    section_teachers: Dict[str, str] = PField(default_factory=dict)  # section -> teacher_id ("" clears)
    periods_per_week: int | None = None
    consecutive_periods: int | None = None
    must_be_consecutive: bool | None = None
    flexible: bool | None = None
    min_periods: int | None = None
    max_periods: int | None = None


class SubjectStaffSave(BaseModel):
    academic_year: str
    items: List[SubjectStaffItem] = PField(default_factory=list)


async def _offered_sections_map(iid: str, class_name: str, sections: list):
    """subject -> sorted list of sections that offer it (a section="" offering counts for ALL sections)."""
    out: Dict[str, set] = {}
    async for o in db.subject_offerings.find({"institution_id": iid, "class_name": class_name}, {"_id": 0, "subject": 1, "section": 1}):
        sec = o.get("section") or ""
        s = out.setdefault(o["subject"], set())
        s.update(sections if sec == "" else [sec])
    return {k: sorted(v & set(sections)) for k, v in out.items()}


async def _build_subject_staff_payload(iid: str, academic_year: str, class_name: str):
    cls = await db.classes.find_one({"institution_id": iid, "name": class_name}, {"_id": 0})
    if not cls:
        raise HTTPException(status_code=404, detail="Class not found")
    sections = [s["name"] for s in await db.sections.find(
        {"institution_id": iid, "class_name": class_name}, {"_id": 0, "name": 1}).sort("name", 1).to_list(200)]
    offered = await _offered_sections_map(iid, class_name, sections)
    subjects = sorted(offered.keys())
    teachers = [{"id": t["id"], "name": t.get("name"), "email": t.get("email")}
                for t in await db.users.find(
                    {"institution_id": iid, "role": "teacher", "status": {"$ne": "inactive"}},
                    {"_id": 0, "id": 1, "name": 1, "email": 1}).sort("name", 1).to_list(2000)]
    catalog = [{"name": s["name"]} for s in await db.subjects.find(
        {"institution_id": iid}, {"_id": 0, "name": 1}).sort("name", 1).to_list(500)]
    asg_map: Dict[str, Dict[str, str]] = {}
    async for a in db.teacher_assignments.find({"institution_id": iid, "class_name": class_name}, {"_id": 0}):
        subj = a.get("subject")
        if not subj:
            continue
        asg_map.setdefault(subj, {})[a.get("section") or ""] = a.get("teacher_id")
    reqs = {r["subject"]: r for r in await db.subject_requirements.find(
        {"institution_id": iid, "class_name": class_name}, {"_id": 0}).to_list(500)}
    items = []
    for subj in subjects:
        r = reqs.get(subj)
        amap = asg_map.get(subj, {})
        rmap = (r.get("section_teachers") if r else {}) or {}
        osecs = offered.get(subj, [])
        st = {}
        for sec in osecs:
            tid = amap.get(sec) or amap.get("") or rmap.get(sec)
            if tid:
                st[sec] = tid
        items.append({
            "subject": subj, "offered_sections": osecs, "section_teachers": st,
            "periods_per_week": int(r["periods_per_week"]) if r else 0,
            "consecutive_periods": (r.get("consecutive_periods") if r else 1) or 1,
            "must_be_consecutive": bool(r.get("must_be_consecutive")) if r else False,
            "flexible": _req_flexible(r) if r else _is_flexible_default(subj),
            "min_periods": _req_min(r) if r else 1,
            "max_periods": _req_max(r, int(r["periods_per_week"]) if r else 0) if r else 2,
            "configured": r is not None,
        })
    return {"class_name": class_name, "academic_unit_name": cls.get("academic_unit_name"),
            "academic_year": academic_year, "sections": sections, "teachers": teachers,
            "catalog": catalog, "items": items}


async def _offering_delete_block(iid: str, class_name: str, section: str, subject: str):
    """Human message if a section+subject offering has dependent timetable/assessment data (blocks removal)."""
    tt = await db.timetable_entries.count_documents(
        {"institution_id": iid, "class_name": class_name, "section": section, "subject": subject})
    asmt = await db.assessments.count_documents(
        {"institution_id": iid, "class_name": class_name, "section": section, "subject": subject})
    if tt or asmt:
        bits = []
        if tt:
            bits.append(f"{tt} timetable period(s)")
        if asmt:
            bits.append(f"{asmt} assessment(s)")
        return (f"Cannot remove {subject} from {class_name} - {section}: {', '.join(bits)} reference it. "
                f"Clear those first.")
    return None


class OfferingRef(BaseModel):
    subject: str
    section: str


@api.post("/class-hub/{class_name}/offerings")
async def add_section_offering(class_name: str, body: OfferingRef,
                               user: dict = Depends(require_admin_or_principal)):
    iid = user["institution_id"]
    cn = class_name.strip()
    cls = await db.classes.find_one({"institution_id": iid, "name": cn}, {"_id": 0})
    if not cls:
        raise HTTPException(status_code=404, detail="Class not found")
    await guard_principal_class(user, cn)
    subj, sec = body.subject.strip(), body.section.strip()
    if not await db.sections.find_one({"institution_id": iid, "class_name": cn, "name": sec}):
        raise HTTPException(status_code=400, detail=f"Section '{sec}' does not exist in {cn}")
    if not await db.subjects.find_one({"institution_id": iid, "name": subj}):
        raise HTTPException(status_code=400, detail=f"'{subj}' is not in the subject catalog. Add it under Subjects first.")
    dup = await db.subject_offerings.find_one(
        {"institution_id": iid, "class_name": cn, "subject": subj,
         "section": {"$in": [sec, ""]}})
    if dup:
        raise HTTPException(status_code=400, detail=f"{subj} is already offered to {cn} - {sec}")
    doc = {"id": str(uuid.uuid4()), "institution_id": iid, "class_name": cn, "section": sec,
           "subject": subj, "max_marks": 100, "status": "active", "created_at": now_iso()}
    normalize_offering_marks(doc)
    await db.subject_offerings.insert_one(dict(doc))
    await audit(user, "add_offering", "subject_offerings", doc["id"], f"{cn} - {sec} · {subj}")
    return await _build_subject_staff_payload(iid, cls.get("academic_year", ""), cn)


@api.delete("/class-hub/{class_name}/offerings")
async def remove_section_offering(class_name: str, subject: str, section: str,
                                  user: dict = Depends(require_admin_or_principal)):
    iid = user["institution_id"]
    cn = class_name.strip()
    cls = await db.classes.find_one({"institution_id": iid, "name": cn}, {"_id": 0})
    if not cls:
        raise HTTPException(status_code=404, detail="Class not found")
    await guard_principal_class(user, cn)
    subj, sec = subject.strip(), section.strip()
    block = await _offering_delete_block(iid, cn, sec, subj)
    if block:
        raise HTTPException(status_code=409, detail=block)
    sections = [s["name"] for s in await db.sections.find(
        {"institution_id": iid, "class_name": cn}, {"_id": 0, "name": 1}).to_list(200)]
    # If a whole-class (section="") offering exists, we must materialise the OTHER sections as explicit
    # offerings before removing this one — otherwise the "" offering would still cover `sec`.
    whole = await db.subject_offerings.find_one({"institution_id": iid, "class_name": cn, "subject": subj, "section": ""})
    cascade = {"offering_removed": 0, "assignments_removed": 0, "requirement_removed": False,
               "section_teacher_cleared": False}
    if whole:
        for other in sections:
            if other != sec and not await db.subject_offerings.find_one(
                    {"institution_id": iid, "class_name": cn, "subject": subj, "section": other}):
                m = {"id": str(uuid.uuid4()), "institution_id": iid, "class_name": cn, "section": other,
                     "subject": subj, "status": "active", "created_at": now_iso()}
                for k in ("max_marks", "has_practical", "theory_max_marks", "practical_max_marks"):
                    if k in whole:
                        m[k] = whole[k]
                normalize_offering_marks(m)
                await db.subject_offerings.insert_one(dict(m))
        res0 = await db.subject_offerings.delete_many({"institution_id": iid, "class_name": cn, "subject": subj, "section": ""})
        cascade["offering_removed"] += res0.deleted_count
    res = await db.subject_offerings.delete_many({"institution_id": iid, "class_name": cn, "subject": subj, "section": sec})
    cascade["offering_removed"] += res.deleted_count
    # remove teacher assignments for this section+subject
    resa = await db.teacher_assignments.delete_many(
        {"institution_id": iid, "class_name": cn, "subject": subj, "section": sec})
    cascade["assignments_removed"] += resa.deleted_count
    # clear this section's teacher mapping from the requirement
    req = await db.subject_requirements.find_one({"institution_id": iid, "class_name": cn, "subject": subj})
    if req and sec in (req.get("section_teachers") or {}):
        st = dict(req["section_teachers"])
        st.pop(sec, None)
        await db.subject_requirements.update_one({"id": req["id"]}, {"$set": {"section_teachers": st}})
        cascade["section_teacher_cleared"] = True
    # if the subject is no longer offered to ANY section of the grade → drop requirement + any leftover assignments
    still = await db.subject_offerings.count_documents({"institution_id": iid, "class_name": cn, "subject": subj})
    if still == 0:
        rr = await db.subject_requirements.delete_many({"institution_id": iid, "class_name": cn, "subject": subj})
        cascade["requirement_removed"] = rr.deleted_count > 0
        ra = await db.teacher_assignments.delete_many({"institution_id": iid, "class_name": cn, "subject": subj})
        cascade["assignments_removed"] += ra.deleted_count
    await audit(user, "remove_offering", "subject_offerings", f"{cn}/{sec}/{subj}",
                f"{cn} - {sec} · {subj} (cascade: {cascade})")
    payload = await _build_subject_staff_payload(iid, cls.get("academic_year", ""), cn)
    payload["cascade"] = cascade
    return payload


@api.get("/class-hub/{class_name}/subject-staff")
async def get_subject_staff(class_name: str, academic_year: str = "",
                            user: dict = Depends(require_admin_or_principal)):
    iid = user["institution_id"]
    await guard_principal_class(user, class_name)
    return await _build_subject_staff_payload(iid, academic_year, class_name)


@api.put("/class-hub/{class_name}/subject-staff")
async def save_subject_staff(class_name: str, body: SubjectStaffSave,
                             user: dict = Depends(require_admin_or_principal)):
    iid = user["institution_id"]
    cn = class_name.strip()
    cls = await db.classes.find_one({"institution_id": iid, "name": cn}, {"_id": 0})
    if not cls:
        raise HTTPException(status_code=404, detail="Class not found")
    await guard_principal_class(user, cn)
    ay = (body.academic_year or "").strip()
    offered = {o["subject"] for o in await db.subject_offerings.find(
        {"institution_id": iid, "class_name": cn}, {"_id": 0, "subject": 1}).to_list(500)}
    sections = {s["name"] for s in await db.sections.find(
        {"institution_id": iid, "class_name": cn}, {"_id": 0, "name": 1}).to_list(200)}
    offered_map = await _offered_sections_map(iid, cn, list(sections))
    teacher_by_id = {t["id"]: t for t in await db.users.find(
        {"institution_id": iid, "role": "teacher", "status": {"$ne": "inactive"}},
        {"_id": 0, "id": 1, "name": 1, "email": 1}).to_list(2000)}
    touched = 0
    for it in body.items:
        subj = it.subject.strip()
        if subj not in offered:
            raise HTTPException(status_code=400, detail=f"'{subj}' is not offered for {cn}")
        ppw = it.periods_per_week
        if ppw is not None and ppw >= 1:
            cons = it.consecutive_periods or 1
            if cons < 1 or cons > 3:
                raise HTTPException(status_code=400, detail=f"{subj}: consecutive periods must be 1, 2 or 3")
            if cons > ppw:
                raise HTTPException(status_code=400, detail=f"{subj}: consecutive ({cons}) cannot exceed periods/week ({ppw})")
        # validate + sync teacher_assignments per section
        for sec, tid in (it.section_teachers or {}).items():
            if sec not in sections:
                raise HTTPException(status_code=400, detail=f"{subj}: section '{sec}' does not exist in {cn}")
            if tid and sec not in offered_map.get(subj, []):
                raise HTTPException(status_code=400, detail=f"{subj} is not offered to {cn} - {sec}. Add the offering first.")
            if tid and tid not in teacher_by_id:
                raise HTTPException(status_code=400, detail=f"{subj}: section '{sec}' teacher is not an active teacher")
            key = {"institution_id": iid, "class_name": cn, "section": sec, "subject": subj}
            if tid:
                tu = teacher_by_id[tid]
                ex = await db.teacher_assignments.find_one(key)
                if ex:
                    await db.teacher_assignments.update_one(
                        {"id": ex["id"]}, {"$set": {"teacher_id": tid, "teacher_email": tu.get("email"),
                                                    "teacher_name": tu.get("name"), "updated_at": now_iso()}})
                else:
                    await db.teacher_assignments.insert_one({
                        "id": str(uuid.uuid4()), "institution_id": iid, "class_name": cn, "section": sec,
                        "subject": subj, "teacher_id": tid, "teacher_email": tu.get("email"),
                        "teacher_name": tu.get("name"), "created_at": now_iso()})
                await db.teacher_assignments.delete_many({**key, "teacher_id": {"$ne": tid}})
            else:
                await db.teacher_assignments.delete_many(key)
            touched += 1
        # mirror into subject_requirements (keep timetable + generator in sync)
        section_clean = {s: t for s, t in (it.section_teachers or {}).items() if t}
        ex_req = await db.subject_requirements.find_one({"institution_id": iid, "class_name": cn, "subject": subj})
        pool = set(section_clean.values())
        if ex_req:
            pool |= set(ex_req.get("teacher_ids") or [])
        fields = {"section_teachers": section_clean, "teacher_ids": sorted(pool),
                  "academic_year": ay or (ex_req.get("academic_year") if ex_req else ""), "updated_at": now_iso()}
        if ppw is not None:
            fields["periods_per_week"] = ppw
        if it.consecutive_periods is not None:
            fields["consecutive_periods"] = it.consecutive_periods
        if it.must_be_consecutive is not None:
            fields["must_be_consecutive"] = bool(it.must_be_consecutive)
        if it.flexible is not None:
            fields["flexible"] = it.flexible
        if it.min_periods is not None:
            fields["min_periods"] = it.min_periods
        if it.max_periods is not None:
            fields["max_periods"] = it.max_periods
        if ex_req:
            await db.subject_requirements.update_one({"id": ex_req["id"]}, {"$set": fields})
        elif section_clean or (ppw is not None and ppw >= 1):
            fields.setdefault("periods_per_week", ppw or 0)
            fields.setdefault("consecutive_periods", 1)
            fields.setdefault("must_be_consecutive", False)
            fields.update({"id": str(uuid.uuid4()), "institution_id": iid, "class_name": cn,
                           "subject": subj, "created_at": now_iso()})
            await db.subject_requirements.insert_one(dict(fields))
    await audit(user, "save_subject_staff", "teacher_assignments", cn,
                f"{cn} · {len(body.items)} subjects · {touched} section-teacher slots")
    return await _build_subject_staff_payload(iid, ay, cn)



def _tt_ranges_overlap(a_from, a_to, b_from, b_to):
    return (a_from or "0000-01-01") <= (b_to or "9999-12-31") and (b_from or "0000-01-01") <= (a_to or "9999-12-31")


async def validate_tt_entry(iid: str, doc: dict, exclude_id: str = None):
    for f in ("academic_year", "class_name", "section", "day", "period_no", "offering_id", "teacher_assignment_id"):
        if not doc.get(f):
            raise HTTPException(status_code=400, detail=f"Missing field: {f}")
    if doc["day"] not in TT_DAYS:
        raise HTTPException(status_code=400, detail="Invalid day")
    cls = await db.classes.find_one({"institution_id": iid, "name": doc["class_name"]})
    if not cls:
        raise HTTPException(status_code=400, detail="Class not found")
    cfg = await effective_tt_config(iid, doc["academic_year"], cls.get("academic_unit_id"))
    if doc["day"] not in cfg["working_days"]:
        raise HTTPException(status_code=400, detail=f"{TT_DAY_LABELS[doc['day']]} is not a working day for this unit")
    try:
        pno = int(doc["period_no"])
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid period")
    if pno < 1 or pno > len(cfg["periods"]):
        raise HTTPException(status_code=400, detail="Period out of range for this unit's configuration")
    if cfg["periods"][pno - 1]["is_break"]:
        raise HTTPException(status_code=400, detail=f"Period {cfg['periods'][pno - 1]['label']} is a break — nothing can be scheduled there")
    doc["period_no"] = pno
    offering = await db.subject_offerings.find_one({"id": doc["offering_id"], "institution_id": iid})
    if not offering:
        raise HTTPException(status_code=400, detail="Subject offering not found")
    if offering.get("class_name") != doc["class_name"]:
        raise HTTPException(status_code=400, detail="That subject is not offered to this class")
    if offering.get("section") and offering["section"] != doc["section"]:
        raise HTTPException(status_code=400, detail=f"{offering['subject']} is offered to section {offering['section']} only")
    assignment = await db.teacher_assignments.find_one({"id": doc["teacher_assignment_id"], "institution_id": iid})
    if not assignment:
        raise HTTPException(status_code=400, detail="Teacher assignment not found")
    if assignment.get("class_name") != doc["class_name"] or assignment.get("subject") != offering["subject"] \
            or (assignment.get("section") and assignment["section"] != doc["section"]):
        raise HTTPException(status_code=400,
                            detail=f"{assignment.get('teacher_name') or 'This teacher'} is not assigned to teach {offering['subject']} for {doc['class_name']} {doc['section']}")
    doc["subject"] = offering["subject"]
    doc["teacher_id"] = assignment.get("teacher_id")
    doc["teacher_name"] = assignment.get("teacher_name")
    doc["room"] = str(doc.get("room") or "").strip()
    doc["type"] = doc.get("type") if doc.get("type") in ("regular", "lab") else "regular"
    doc["status"] = doc.get("status") if doc.get("status") in ("active", "inactive") else "active"
    ef, et = doc.get("effective_from") or "", doc.get("effective_to") or ""
    if ef and et and ef > et:
        raise HTTPException(status_code=400, detail="Effective-from date must be before effective-to")
    doc["effective_from"], doc["effective_to"] = ef, et
    if doc["status"] != "active":
        return doc
    base = {"institution_id": iid, "academic_year": doc["academic_year"], "day": doc["day"],
            "period_no": pno, "status": "active"}
    if exclude_id:
        base["id"] = {"$ne": exclude_id}
    slot = f"{TT_DAY_LABELS[doc['day']]} · {cfg['periods'][pno - 1]['label']}"
    async for e in db.timetable_entries.find({**base, "class_name": doc["class_name"], "section": doc["section"]}):
        if _tt_ranges_overlap(ef, et, e.get("effective_from"), e.get("effective_to")):
            raise HTTPException(status_code=409,
                                detail=f"Section conflict: {doc['class_name']} {doc['section']} already has {e['subject']} on {slot}")
    if doc["teacher_id"]:
        async for e in db.timetable_entries.find({**base, "teacher_id": doc["teacher_id"]}):
            if _tt_ranges_overlap(ef, et, e.get("effective_from"), e.get("effective_to")):
                raise HTTPException(status_code=409,
                                    detail=f"Teacher conflict: {doc['teacher_name']} already teaches {e['subject']} for {e['class_name']} {e['section']} on {slot}")
    if doc["room"]:
        async for e in db.timetable_entries.find({**base, "room": doc["room"]}):
            if _tt_ranges_overlap(ef, et, e.get("effective_from"), e.get("effective_to")):
                raise HTTPException(status_code=409,
                                    detail=f"Room conflict: {doc['room']} is already used by {e['class_name']} {e['section']} ({e['subject']}) on {slot}")
    return doc


@api.get("/timetable/grid")
async def tt_grid(academic_year: str, class_name: str, section: str, mode: str = "published", date: str = "",
                  user: dict = Depends(require_roles("institution_admin", "teacher"))):
    iid = user["institution_id"]
    cls = await db.classes.find_one({"institution_id": iid, "name": class_name}, {"_id": 0})
    if not cls:
        raise HTTPException(status_code=404, detail="Class not found")
    cfg = await effective_tt_config(iid, academic_year, cls.get("academic_unit_id"))
    draft_batch = await db.timetable_batches.find_one(
        {"institution_id": iid, "academic_year": academic_year, "class_name": class_name,
         "state": {"$in": ["generated", "approved"]}}, {"_id": 0}, sort=[("created_at", -1)])
    eq = {"institution_id": iid, "academic_year": academic_year, "class_name": class_name,
          "section": section, "status": "active"}
    if mode == "draft" and draft_batch:
        eq.update({"publish_state": "draft", "batch_id": draft_batch["id"]})
    else:
        eq.update(PUBLISHED_MATCH)
    entries = await db.timetable_entries.find(eq, {"_id": 0}).to_list(500)
    # date-aware substitution overlay (only for the date's weekday)
    if date:
        wd = _weekday_code(date)
        submap = {s["period_no"]: s for s in await _assigned_subs_for_date(iid, date, class_name=class_name)
                  if (s.get("section") or "") == section}
        for e in entries:
            s = submap.get(e["period_no"])
            if s and e["day"] == wd:
                e["substitution"] = {"substitute_teacher_id": s["substitute_teacher_id"],
                                     "substitute_name": s["substitute_name"],
                                     "original_teacher_name": e.get("teacher_name")}
    offerings = await db.subject_offerings.find(
        {"institution_id": iid, "class_name": class_name,
         "$or": [{"section": {"$in": [None, ""]}}, {"section": section}]}, {"_id": 0}).sort("subject", 1).to_list(300)
    assignments = await db.teacher_assignments.find(
        {"institution_id": iid, "class_name": class_name,
         "$or": [{"section": {"$in": [None, ""]}}, {"section": section}]}, {"_id": 0}).sort("teacher_name", 1).to_list(300)
    return {"config": cfg, "entries": entries, "offerings": offerings, "assignments": assignments,
            "mode": mode if (mode == "draft" and draft_batch) else "published",
            "draft_batch": draft_batch}


async def _active_year_name(iid: str):
    y = await db.academic_years.find_one({"institution_id": iid, "status": "active"}, {"_id": 0}) \
        or await db.academic_years.find_one({"institution_id": iid}, {"_id": 0})
    return y["name"] if y else None


def _tt_effective_now(e):
    today = now_iso()[:10]
    return (not e.get("effective_from") or e["effective_from"] <= today) and \
           (not e.get("effective_to") or e["effective_to"] >= today)


@api.get("/timetable/teacher-grid")
async def tt_teacher_grid(teacher_id: str = "", academic_year: str = "",
                          user: dict = Depends(require_roles("institution_admin", "teacher"))):
    iid = user["institution_id"]
    if user["role"] == "teacher":
        teacher_id = user["id"]
    if not teacher_id:
        raise HTTPException(status_code=400, detail="teacher_id required")
    academic_year = academic_year or await _active_year_name(iid)
    entries = await db.timetable_entries.find(
        {"institution_id": iid, "academic_year": academic_year, "teacher_id": teacher_id, "status": "active", **PUBLISHED_MATCH},
        {"_id": 0}).to_list(500)
    entries = [e for e in entries if _tt_effective_now(e)]
    unit_ids = set()
    for e in entries:
        cls = await db.classes.find_one({"institution_id": iid, "name": e["class_name"]}, {"academic_unit_id": 1})
        if cls:
            unit_ids.add(cls.get("academic_unit_id"))
    unit_id = unit_ids.pop() if len(unit_ids) == 1 else None
    cfg = await effective_tt_config(iid, academic_year, unit_id)
    return {"config": cfg, "entries": entries, "academic_year": academic_year}


@api.post("/timetable/entries")
async def create_tt_entry(payload: dict = Body(...), user: dict = Depends(require_admin_or_principal)):
    iid = user["institution_id"]
    doc = {k: v for k, v in payload.items() if k not in PROTECTED_KEYS}
    doc.update({"id": str(uuid.uuid4()), "institution_id": iid, "created_at": now_iso()})
    await guard_principal_class(user, doc.get("class_name"))
    await validate_tt_entry(iid, doc)
    await db.timetable_entries.insert_one(dict(doc))
    doc.pop("_id", None)
    await audit(user, "create", "timetable_entries", doc["id"],
                f"{doc['class_name']} {doc['section']} {doc['day']} P{doc['period_no']} {doc['subject']}")
    return doc


@api.put("/timetable/entries/{entry_id}")
async def update_tt_entry(entry_id: str, payload: dict = Body(...),
                          user: dict = Depends(require_admin_or_principal)):
    iid = user["institution_id"]
    existing = await db.timetable_entries.find_one({"id": entry_id, "institution_id": iid}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Timetable entry not found")
    await guard_principal_class(user, existing.get("class_name"))
    merged = {**existing, **{k: v for k, v in payload.items() if k not in PROTECTED_KEYS}}
    await guard_principal_class(user, merged.get("class_name"))
    await validate_tt_entry(iid, merged, exclude_id=entry_id)
    await db.timetable_entries.update_one({"id": entry_id}, {"$set": merged})
    await audit(user, "update", "timetable_entries", entry_id,
                f"{merged['class_name']} {merged['section']} {merged['day']} P{merged['period_no']} {merged['subject']}")
    return merged


@api.delete("/timetable/entries/{entry_id}")
async def delete_tt_entry(entry_id: str, user: dict = Depends(require_admin_or_principal)):
    iid = user["institution_id"]
    doc = await db.timetable_entries.find_one({"id": entry_id, "institution_id": iid})
    if not doc:
        raise HTTPException(status_code=404, detail="Timetable entry not found")
    await guard_principal_class(user, doc.get("class_name"))
    await db.timetable_entries.delete_one({"id": entry_id})
    await audit(user, "delete", "timetable_entries", entry_id,
                f"{doc['class_name']} {doc['section']} {doc['day']} P{doc['period_no']} {doc.get('subject')}")
    return {"message": "Deleted"}


# ---------------- Phase 8: Grade-grid views + manual editing with multi-conflict warnings ----------------
# Additive model: the grade grid places entries by {subject, teacher_id} directly. offering_id /
# teacher_assignment_id are resolved when available but no longer required (the strict manual builder
# POST /timetable/entries path is untouched). Entries gain an optional `conflict_flags` list so
# overridden cells can be flagged in the grid. Entry schema is otherwise unchanged.

class ConflictCheckRequest(BaseModel):
    academic_year: str
    class_name: str
    section: str
    day: str
    period_no: int
    subject: str
    teacher_id: Optional[str] = ""
    room: Optional[str] = ""
    entry_id: Optional[str] = None
    publish_state: Optional[str] = "published"
    batch_id: Optional[str] = None


class PlaceEntryRequest(BaseModel):
    academic_year: str
    class_name: str
    section: str
    day: str
    period_no: int
    subject: str
    teacher_id: Optional[str] = ""
    room: Optional[str] = ""
    type: Optional[str] = "regular"
    entry_id: Optional[str] = None
    publish_state: Optional[str] = "published"
    batch_id: Optional[str] = None
    override: bool = False


class MoveEntryRequest(BaseModel):
    entry_id: str
    to_day: str
    to_period_no: int
    override: bool = False


async def _cfg_for_class(iid: str, academic_year: str, class_name: str):
    cls = await db.classes.find_one({"institution_id": iid, "name": class_name}, {"_id": 0})
    if not cls:
        raise HTTPException(status_code=400, detail="Class not found")
    cfg = await effective_tt_config(iid, academic_year, cls.get("academic_unit_id"))
    return cls, cfg


async def _place_conflicts(iid: str, doc: dict, exclude_ids=None):
    """Return a list of ALL conflicts for a proposed placement (never raises). Each item:
    {type, message, severity}. severity 'hard' (double-book/section/room) vs 'soft' (pool/consecutive)."""
    conflicts = []
    ay, day, pno = doc["academic_year"], doc["day"], doc["period_no"]
    _cls, cfg = await _cfg_for_class(iid, ay, doc["class_name"])
    plabel = cfg["periods"][pno - 1]["label"] if 1 <= pno <= len(cfg["periods"]) else f"P{pno}"
    slot = f"{TT_DAY_LABELS.get(day, day)} · {plabel}"
    ef, et = doc.get("effective_from") or "", doc.get("effective_to") or ""
    pub = doc.get("publish_state", "published")
    bid = doc.get("batch_id")
    if pub == "draft":
        vis = {"$or": [{"batch_id": bid},
                       {**PUBLISHED_MATCH, "class_name": {"$ne": doc["class_name"]}}]}
        vis_same = {"batch_id": bid}
    else:
        vis = dict(PUBLISHED_MATCH)
        vis_same = dict(PUBLISHED_MATCH)
    base = {"institution_id": iid, "academic_year": ay, "day": day, "period_no": pno, "status": "active", **vis}
    if exclude_ids:
        base["id"] = {"$nin": list(exclude_ids)}
    # (b) section already occupied
    async for e in db.timetable_entries.find({**base, "class_name": doc["class_name"], "section": doc["section"]}):
        if _tt_ranges_overlap(ef, et, e.get("effective_from"), e.get("effective_to")):
            conflicts.append({"type": "section", "severity": "hard",
                              "message": f"{doc['class_name']} {doc['section']} already has {e['subject']} on {slot}"})
    # (a) teacher double-booked
    if doc.get("teacher_id"):
        async for e in db.timetable_entries.find({**base, "teacher_id": doc["teacher_id"]}):
            if e.get("class_name") == doc["class_name"] and e.get("section") == doc["section"]:
                continue
            if _tt_ranges_overlap(ef, et, e.get("effective_from"), e.get("effective_to")):
                conflicts.append({"type": "teacher", "severity": "hard",
                                  "message": f"{doc.get('teacher_name') or 'Teacher'} already teaches {e['subject']} for {e['class_name']} {e['section']} on {slot}"})
    # (e) room double-booked
    if doc.get("room"):
        async for e in db.timetable_entries.find({**base, "room": doc["room"]}):
            if _tt_ranges_overlap(ef, et, e.get("effective_from"), e.get("effective_to")):
                conflicts.append({"type": "room", "severity": "hard",
                                  "message": f"Room {doc['room']} already used by {e['class_name']} {e['section']} ({e['subject']}) on {slot}"})
    req = await db.subject_requirements.find_one(
        {"institution_id": iid, "class_name": doc["class_name"], "subject": doc["subject"]}, {"_id": 0})
    # (d) teacher not in the subject's pool (soft)
    if doc.get("teacher_id"):
        pool = set((req or {}).get("teacher_ids") or [])
        in_assign = await db.teacher_assignments.find_one(
            {"institution_id": iid, "class_name": doc["class_name"], "subject": doc["subject"], "teacher_id": doc["teacher_id"]})
        if doc["teacher_id"] not in pool and not in_assign:
            conflicts.append({"type": "pool", "severity": "soft",
                              "message": f"{doc.get('teacher_name') or 'This teacher'} is not in the {doc['subject']} teacher pool for {doc['class_name']}"})
    # (c) consecutive-period requirement broken (soft)
    if req and req.get("must_be_consecutive") and (req.get("consecutive_periods") or 1) > 1:
        others = set()
        q = {"institution_id": iid, "academic_year": ay, "day": day, "class_name": doc["class_name"],
             "section": doc["section"], "subject": doc["subject"], "status": "active", **vis_same}
        if exclude_ids:
            q["id"] = {"$nin": list(exclude_ids)}
        async for e in db.timetable_entries.find(q):
            others.add(e["period_no"])
        others.add(pno)
        teaching = [i + 1 for i, p in enumerate(cfg["periods"]) if not p.get("is_break")]
        if pno in teaching:
            idx = teaching.index(pno)
            neighbours = []
            if idx > 0:
                neighbours.append(teaching[idx - 1])
            if idx + 1 < len(teaching):
                neighbours.append(teaching[idx + 1])
            if not any(n in others for n in neighbours):
                conflicts.append({"type": "consecutive", "severity": "soft",
                                  "message": f"{doc['subject']} should sit in blocks of {req['consecutive_periods']} — this slot has no adjacent {doc['subject']} period"})
    # (f) class-teacher-first-period reservation (soft): P1 should hold the class teacher's subject
    teaching_f = [i + 1 for i, p in enumerate(cfg["periods"]) if not p.get("is_break")]
    if teaching_f and pno == teaching_f[0]:
        secd = await db.sections.find_one(
            {"institution_id": iid, "class_name": doc["class_name"], "name": doc["section"]},
            {"_id": 0, "class_teacher_first_period": 1, "class_teacher_id": 1, "class_teacher": 1})
        if secd and secd.get("class_teacher_first_period") and secd.get("class_teacher_id") \
                and doc.get("teacher_id") != secd.get("class_teacher_id"):
            ctn = secd.get("class_teacher")
            conflicts.append({"type": "first_period", "severity": "soft",
                              "message": f"{doc['class_name']} {doc['section']} Period 1 is reserved for the class teacher"
                                         + (f" ({ctn})" if ctn else "")})
    return conflicts, cfg


async def _build_place_doc(iid: str, body: PlaceEntryRequest):
    cls, cfg = await _cfg_for_class(iid, body.academic_year, body.class_name)
    if body.day not in TT_DAYS or body.day not in cfg["working_days"]:
        raise HTTPException(status_code=400, detail="That day is not a working day for this unit")
    pno = int(body.period_no)
    if pno < 1 or pno > len(cfg["periods"]):
        raise HTTPException(status_code=400, detail="Period out of range for this unit")
    if cfg["periods"][pno - 1]["is_break"]:
        raise HTTPException(status_code=400, detail=f"Period {cfg['periods'][pno - 1]['label']} is a break — nothing can be scheduled there")
    offering = await db.subject_offerings.find_one(
        {"institution_id": iid, "class_name": body.class_name, "subject": body.subject,
         "$or": [{"section": {"$in": [None, ""]}}, {"section": body.section}]}, {"_id": 0})
    if not offering:
        raise HTTPException(status_code=400, detail=f"{body.subject} is not offered to {body.class_name}. Add the offering in Class Hub first.")
    teacher = None
    if body.teacher_id:
        teacher = await db.users.find_one({"id": body.teacher_id, "institution_id": iid, "role": "teacher"}, {"_id": 0})
        if not teacher:
            raise HTTPException(status_code=400, detail="Selected teacher not found in this institution")
    assignment = None
    if body.teacher_id:
        assignment = await db.teacher_assignments.find_one(
            {"institution_id": iid, "class_name": body.class_name, "subject": body.subject, "teacher_id": body.teacher_id}, {"_id": 0})
    return {
        "institution_id": iid,
        "academic_year": body.academic_year, "class_name": body.class_name, "section": body.section,
        "day": body.day, "period_no": pno, "subject": body.subject,
        "teacher_id": body.teacher_id or None, "teacher_name": teacher["name"] if teacher else None,
        "room": str(body.room or "").strip(), "type": body.type if body.type in ("regular", "lab") else "regular",
        "status": "active", "offering_id": offering["id"],
        "teacher_assignment_id": assignment["id"] if assignment else None,
        "publish_state": body.publish_state or "published",
        "batch_id": body.batch_id,
        "effective_from": "", "effective_to": "",
    }


@api.post("/timetable/entries/check")
async def tt_check(body: ConflictCheckRequest, user: dict = Depends(require_admin_or_principal)):
    iid = user["institution_id"]
    await guard_principal_class(user, body.class_name)
    teacher = await db.users.find_one({"id": body.teacher_id, "institution_id": iid}, {"_id": 0, "name": 1}) if body.teacher_id else None
    doc = {"academic_year": body.academic_year, "class_name": body.class_name, "section": body.section,
           "day": body.day, "period_no": int(body.period_no), "subject": body.subject,
           "teacher_id": body.teacher_id or None, "teacher_name": teacher["name"] if teacher else None,
           "room": str(body.room or "").strip(), "effective_from": "", "effective_to": "",
           "publish_state": body.publish_state or "published", "batch_id": body.batch_id}
    exclude = [body.entry_id] if body.entry_id else None
    conflicts, _cfg = await _place_conflicts(iid, doc, exclude_ids=exclude)
    return {"conflicts": conflicts, "can_override": True}


@api.post("/timetable/place")
async def tt_place(body: PlaceEntryRequest, user: dict = Depends(require_admin_or_principal)):
    iid = user["institution_id"]
    await guard_principal_class(user, body.class_name)
    doc = await _build_place_doc(iid, body)
    existing = None
    if body.entry_id:
        existing = await db.timetable_entries.find_one({"id": body.entry_id, "institution_id": iid}, {"_id": 0})
    if not existing:
        cell_q = {"institution_id": iid, "academic_year": body.academic_year, "class_name": body.class_name,
                  "section": body.section, "day": body.day, "period_no": doc["period_no"], "status": "active"}
        if (body.publish_state or "published") == "draft":
            cell_q["batch_id"] = body.batch_id
        else:
            cell_q.update(PUBLISHED_MATCH)
        existing = await db.timetable_entries.find_one(cell_q, {"_id": 0})
    exclude = [existing["id"]] if existing else None
    conflicts, _cfg = await _place_conflicts(iid, doc, exclude_ids=exclude)
    if conflicts and not body.override:
        return {"ok": False, "conflicts": conflicts}
    doc["conflict_flags"] = conflicts
    overridden = bool(conflicts and body.override)
    if existing:
        doc["id"] = existing["id"]
        doc["created_at"] = existing.get("created_at") or now_iso()
        await db.timetable_entries.update_one({"id": existing["id"]}, {"$set": doc})
        eid = existing["id"]
    else:
        doc["id"] = str(uuid.uuid4())
        doc["created_at"] = now_iso()
        await db.timetable_entries.insert_one(dict(doc))
        eid = doc["id"]
    doc.pop("_id", None)
    await audit(user, "override" if overridden else ("update" if existing else "create"),
                "timetable_entries", eid,
                f"{doc['class_name']} {doc['section']} {doc['day']} P{doc['period_no']} {doc['subject']}"
                + (" [OVERRIDE]" if overridden else ""))
    return {"ok": True, "entry": doc, "conflicts": conflicts}


@api.post("/timetable/move")
async def tt_move(body: MoveEntryRequest, user: dict = Depends(require_admin_or_principal)):
    iid = user["institution_id"]
    entry = await db.timetable_entries.find_one({"id": body.entry_id, "institution_id": iid}, {"_id": 0})
    if not entry:
        raise HTTPException(status_code=404, detail="Timetable entry not found")
    await guard_principal_class(user, entry.get("class_name"))
    _cls, cfg = await _cfg_for_class(iid, entry["academic_year"], entry["class_name"])
    tp = int(body.to_period_no)
    if body.to_day not in cfg["working_days"]:
        raise HTTPException(status_code=400, detail="Target day is not a working day for this unit")
    if tp < 1 or tp > len(cfg["periods"]) or cfg["periods"][tp - 1]["is_break"]:
        raise HTTPException(status_code=400, detail="Target slot is a break or out of range")
    target = await db.timetable_entries.find_one(
        {"institution_id": iid, "academic_year": entry["academic_year"], "class_name": entry["class_name"],
         "section": entry["section"], "day": body.to_day, "period_no": tp, "status": "active",
         "id": {"$ne": entry["id"]}}, {"_id": 0})
    moved = {**entry, "day": body.to_day, "period_no": tp}
    exclude = [entry["id"]] + ([target["id"]] if target else [])
    conflicts, _ = await _place_conflicts(iid, moved, exclude_ids=exclude)
    swapped = None
    if target:
        swapped = {**target, "day": entry["day"], "period_no": entry["period_no"]}
        c2, _ = await _place_conflicts(iid, swapped, exclude_ids=exclude)
        seen = {c["message"] for c in conflicts}
        conflicts += [c for c in c2 if c["message"] not in seen]
    if conflicts and not body.override:
        return {"ok": False, "conflicts": conflicts, "swap": bool(target)}
    moved["conflict_flags"] = conflicts
    await db.timetable_entries.update_one({"id": entry["id"]}, {"$set": {"day": moved["day"], "period_no": moved["period_no"], "conflict_flags": conflicts}})
    if target:
        await db.timetable_entries.update_one({"id": target["id"]}, {"$set": {"day": swapped["day"], "period_no": swapped["period_no"]}})
    overridden = bool(conflicts and body.override)
    await audit(user, "override" if overridden else "move", "timetable_entries", entry["id"],
                f"{entry['class_name']} {entry['section']} → {body.to_day} P{tp}" + (" (swap)" if target else "") + (" [OVERRIDE]" if overridden else ""))
    return {"ok": True, "swap": bool(target), "conflicts": conflicts}


async def _assigned_subs_for_date(iid: str, date: str, class_name: str = None, teacher_id: str = None):
    q = {"institution_id": iid, "date": date, "status": "assigned"}
    if class_name:
        q["class_name"] = class_name
    if teacher_id:
        q["$or"] = [{"substitute_teacher_id": teacher_id}, {"original_teacher_id": teacher_id}]
    return await db.substitutions.find(q, {"_id": 0}).to_list(500)


async def _teacher_timetable(iid: str, teacher_id: str, academic_year: str, date: str = ""):
    teacher = await db.users.find_one({"id": teacher_id, "institution_id": iid}, {"_id": 0, "id": 1, "name": 1, "email": 1})
    entries = await db.timetable_entries.find(
        {"institution_id": iid, "academic_year": academic_year, "teacher_id": teacher_id, "status": "active", **PUBLISHED_MATCH}, {"_id": 0}).to_list(500)
    entries = [e for e in entries if _tt_effective_now(e)]
    unit_ids = set()
    for e in entries:
        c = await db.classes.find_one({"institution_id": iid, "name": e["class_name"]}, {"academic_unit_id": 1})
        if c:
            unit_ids.add(c.get("academic_unit_id"))
    cfg = await effective_tt_config(iid, academic_year, unit_ids.pop() if len(unit_ids) == 1 else None)
    by = {(e["day"], e["period_no"]): e for e in entries}
    # date-aware substitution overlay
    overlay_day = _weekday_code(date) if date else None
    cover_in, covered_out = {}, {}  # period_no -> sub info, for overlay_day only
    if date:
        for s in await _assigned_subs_for_date(iid, date, teacher_id=teacher_id):
            if s["substitute_teacher_id"] == teacher_id:
                cover_in[s["period_no"]] = s
            elif s["original_teacher_id"] == teacher_id:
                covered_out[s["period_no"]] = s
    schedule = []
    for d in cfg["working_days"]:
        rows = []
        for i, p in enumerate(cfg["periods"]):
            pno = i + 1
            e = by.get((d, pno))
            if date and d == overlay_day and pno in covered_out and e:
                e = {**e, "substitution": {"covered_by": covered_out[pno].get("substitute_name")}}
            if date and d == overlay_day and pno in cover_in:
                s = cover_in[pno]
                orig = await db.users.find_one({"id": s["original_teacher_id"]}, {"_id": 0, "name": 1})
                e = {"id": s["id"], "class_name": s["class_name"], "section": s.get("section"),
                     "subject": s["subject"], "teacher_id": teacher_id, "type": "regular", "room": "",
                     "is_substitution": True,
                     "substitution": {"covering_for": orig.get("name") if orig else None}}
            rows.append({"period_no": pno, "label": p["label"], "start": p["start"], "end": p["end"],
                         "is_break": p["is_break"], "free": (not p["is_break"] and not e), "entry": e})
        schedule.append({"day": d, "label": TT_DAY_LABELS[d], "periods": rows})
    return {"teacher": teacher, "academic_year": academic_year, "config": cfg, "date": date or None,
            "overlay_day": overlay_day, "schedule": schedule, "entries": entries}


@api.get("/timetable/teacher/{teacher_id}")
async def tt_teacher_view(teacher_id: str, academic_year: str = "", date: str = "", user: dict = Depends(get_current_user)):
    iid = user["institution_id"]
    academic_year = academic_year or await _active_year_name(iid)
    pa = await active_principal(user)
    if user["role"] == "teacher" and not pa:
        if teacher_id != user["id"]:
            raise HTTPException(status_code=403, detail="You can only view your own timetable")
    elif user["role"] == "institution_admin" or (pa and pa.get("scope_type") == "whole_school"):
        pass
    elif pa:
        if teacher_id != user["id"]:
            scope = await principal_scope(user)
            names = set(scope["class_names"] or [])
            teaches = await db.timetable_entries.find_one(
                {"institution_id": iid, "teacher_id": teacher_id, "class_name": {"$in": list(names)}}) if names else None
            assigned = await db.teacher_assignments.find_one(
                {"institution_id": iid, "teacher_id": teacher_id, "class_name": {"$in": list(names)}}) if names else None
            if not teaches and not assigned:
                raise HTTPException(status_code=403, detail="That teacher is outside your assigned scope")
    else:
        raise HTTPException(status_code=403, detail="Access denied")
    return await _teacher_timetable(iid, teacher_id, academic_year, date)


@api.get("/timetable/subject")
async def tt_subject_view(subject: str, academic_year: str = "", user: dict = Depends(require_admin_or_principal)):
    iid = user["institution_id"]
    academic_year = academic_year or await _active_year_name(iid)
    entries = await db.timetable_entries.find(
        {"institution_id": iid, "academic_year": academic_year, "subject": subject, "status": "active", **PUBLISHED_MATCH}, {"_id": 0}).to_list(1000)
    entries = [e for e in entries if _tt_effective_now(e)]
    scope = await principal_scope(user)
    if scope and not scope["whole_school"]:
        names = set(scope["class_names"] or [])
        entries = [e for e in entries if e["class_name"] in names]
    entries.sort(key=lambda e: (e["class_name"], e.get("section") or "", TT_DAYS.index(e["day"]) if e["day"] in TT_DAYS else 9, e["period_no"]))
    return {"subject": subject, "academic_year": academic_year, "entries": entries}


@api.get("/timetable/day")
async def tt_day_view(day: str, academic_year: str = "", user: dict = Depends(require_admin_or_principal)):
    iid = user["institution_id"]
    academic_year = academic_year or await _active_year_name(iid)
    if day not in TT_DAYS:
        raise HTTPException(status_code=400, detail="Invalid day")
    cq = {"institution_id": iid}
    apply_principal_scope_query("classes", cq, await principal_scope(user))
    classes = await db.classes.find(cq, {"_id": 0}).to_list(2000)
    cfg = await effective_tt_config(iid, academic_year, None)
    entries = await db.timetable_entries.find(
        {"institution_id": iid, "academic_year": academic_year, "day": day, "status": "active", **PUBLISHED_MATCH}, {"_id": 0}).to_list(2000)
    entries = [e for e in entries if _tt_effective_now(e)]
    rows = []
    for c in sorted(classes, key=lambda x: x["name"]):
        secs = await db.sections.find({"institution_id": iid, "class_name": c["name"]}, {"_id": 0, "name": 1}).sort("name", 1).to_list(100)
        for s in secs:
            cells = {e["period_no"]: e for e in entries if e["class_name"] == c["name"] and e.get("section") == s["name"]}
            rows.append({"class_name": c["name"], "section": s["name"],
                         "academic_unit_name": c.get("academic_unit_name"),
                         "cells": {str(k): v for k, v in cells.items()}})
    return {"day": day, "day_label": TT_DAY_LABELS[day], "academic_year": academic_year, "config": cfg, "rows": rows}


# ---------------- Phase 9: best-effort generation + review → approve → publish ----------------
# GENERATOR (greedy, best-effort — documented): for every section of a grade, read subject_requirements
# (periods/week, consecutive block size, must_be_consecutive, teacher pool, section→teacher map), the
# effective config (working days, teaching periods, breaks) and PUBLISHED entries of OTHER grades
# (teacher/room occupancy). Place must_be_consecutive subjects as adjacent blocks first, then spread the
# remaining single periods round-robin across days to avoid bunching. A teacher per slot = the section's
# mapped teacher, else the least-loaded free teacher from the pool. Hard conflicts (teacher double-book,
# section occupied) are NEVER created — slots that cannot be filled are skipped and reported as `unplaced`
# with a human reason. Output is a DRAFT batch (publish_state="draft") that never touches published entries.

class GenerateRequest(BaseModel):
    academic_year: str
    class_name: str
    auto_balance: bool = False


class BatchActionRequest(BaseModel):
    batch_id: str


class UnpublishRequest(BaseModel):
    class_name: str
    academic_year: Optional[str] = ""


async def _published_teacher_room_busy(iid: str, ay: str, class_name: str):
    tbusy, rbusy = set(), set()
    async for e in db.timetable_entries.find(
            {"institution_id": iid, "academic_year": ay, "status": "active", **PUBLISHED_MATCH,
             "class_name": {"$ne": class_name}},
            {"_id": 0, "teacher_id": 1, "room": 1, "day": 1, "period_no": 1}):
        if e.get("teacher_id"):
            tbusy.add((e["teacher_id"], e["day"], e["period_no"]))
        if e.get("room"):
            rbusy.add((e["room"], e["day"], e["period_no"]))
    return tbusy, rbusy


@api.post("/timetable/generate")
async def tt_generate(body: GenerateRequest, user: dict = Depends(require_admin_or_principal)):
    iid = user["institution_id"]
    cn, ay = body.class_name.strip(), body.academic_year.strip()
    cls = await db.classes.find_one({"institution_id": iid, "name": cn}, {"_id": 0})
    if not cls:
        raise HTTPException(status_code=400, detail="Class not found")
    await guard_principal_class(user, cn)
    class_id = cls["id"]
    href_subjects = f"/app/class-hub/{class_id}?tab=subjects"
    href_staff = f"/app/class-hub/{class_id}?tab=staff"
    href_req = "/app/timetable"
    cfg = await effective_tt_config(iid, ay, cls.get("academic_unit_id"))
    days = cfg["working_days"]
    teaching = [i + 1 for i, p in enumerate(cfg["periods"]) if not p.get("is_break")]
    sec_docs = await db.sections.find(
        {"institution_id": iid, "class_name": cn}, {"_id": 0}).sort("name", 1).to_list(100)
    sections = [s["name"] for s in sec_docs]
    offered_map = await _offered_sections_map(iid, cn, sections)
    reqs = await db.subject_requirements.find({"institution_id": iid, "class_name": cn}, {"_id": 0}).to_list(500)
    # wipe any existing draft/approved batch for this grade (never touches published)
    async for b in db.timetable_batches.find({"institution_id": iid, "academic_year": ay, "class_name": cn,
                                              "state": {"$in": ["generated", "approved"]}}, {"_id": 0, "id": 1}):
        await db.timetable_entries.delete_many({"batch_id": b["id"], "publish_state": "draft"})
        await db.timetable_batches.delete_one({"id": b["id"]})
    batch_id = str(uuid.uuid4())
    tbusy, _rbusy = await _published_teacher_room_busy(iid, ay, cn)
    tnames = {u["id"]: u["name"] for u in await db.users.find(
        {"institution_id": iid, "role": "teacher"}, {"_id": 0, "id": 1, "name": 1}).to_list(2000)}
    offer_id = {}
    for o in await db.subject_offerings.find({"institution_id": iid, "class_name": cn}, {"_id": 0}).to_list(500):
        offer_id[(o["subject"], o.get("section") or "")] = o["id"]
    load = {}
    placed_docs, unplaced, per_section, auto_adjustments = [], [], {}, []
    auto_balance = bool(body.auto_balance)
    capacity = len(days) * len(teaching)
    for sec_doc in sec_docs:
        section = sec_doc["name"]
        sec_busy = set()
        placed_here, required_here = 0, 0


        def mk(day, p, subj, t):
            return {"id": str(uuid.uuid4()), "institution_id": iid, "academic_year": ay, "class_name": cn,
                    "section": section, "day": day, "period_no": p, "subject": subj,
                    "teacher_id": t or None, "teacher_name": tnames.get(t) if t else None,
                    "room": "", "type": "regular", "status": "active",
                    "offering_id": offer_id.get((subj, section)) or offer_id.get((subj, "")),
                    "teacher_assignment_id": None, "publish_state": "draft", "batch_id": batch_id,
                    "conflict_flags": [], "effective_from": "", "effective_to": "", "created_at": now_iso()}

        # only subjects actually offered to THIS section
        sec_reqs = [r for r in reqs if section in offered_map.get(r["subject"], [])]
        # Phase 12 AUTO-BALANCE (trim): effective periods per subject for THIS section.
        # The requirements document is NEVER mutated — eff is a throwaway working copy and every
        # change is reported in auto_adjustments[]. When total demand exceeds the week's capacity,
        # trim FLEXIBLE subjects only (biggest first) down toward their min_periods.
        eff = {r["subject"]: int(r.get("periods_per_week") or 0) for r in sec_reqs}
        if auto_balance:
            demand = sum(eff.values())
            if demand > capacity:
                flex = sorted([r for r in sec_reqs if _req_flexible(r)], key=lambda r: -eff[r["subject"]])
                for r in flex:
                    if demand <= capacity:
                        break
                    s = r["subject"]
                    mn = _req_min(r)
                    orig = eff[s]
                    while eff[s] > mn and demand > capacity:
                        eff[s] -= 1
                        demand -= 1
                    if eff[s] < orig:
                        auto_adjustments.append({
                            "section": section, "subject": s, "type": "trim", "from": orig, "to": eff[s],
                            "detail": f"{s}: trimmed {orig - eff[s]} period(s) (floor min {mn}) so {cn} - {section} "
                                      f"fits the {capacity}-slot week."})
        # CLASS-TEACHER-FIRST-PERIOD rule: reserve P1 of each working day for the class teacher's subject
        preplaced = {}
        ct_id = sec_doc.get("class_teacher_id")
        if sec_doc.get("class_teacher_first_period") and ct_id and teaching:
            ct_reqs = [r for r in sec_reqs if (r.get("section_teachers") or {}).get(section) == ct_id]
            if not ct_reqs:
                unplaced.append({"section": section, "subject": "", "periods_short": 0,
                                 "cause": "ct_first_period_shortfall",
                                 "reason": f"'Class teacher takes Period 1' is on for {cn} - {section}, but the class "
                                           f"teacher teaches no subject offered to this section — rule skipped.",
                                 "suggestions": [
                                     {"label": "Assign the class teacher a subject here", "href": href_subjects},
                                     {"label": "Or turn off the Period 1 rule", "href": href_staff}]})
            else:
                # highest periods/week wins; ties → alphabetical by subject (documented)
                ct_reqs.sort(key=lambda r: (-(int(r.get("periods_per_week") or 0)), r["subject"]))
                chosen = ct_reqs[0]
                csubj = chosen["subject"]
                p1 = teaching[0]
                cap = min(int(chosen.get("periods_per_week") or 0), len(days))
                reserved, missed = 0, 0
                for day in days:
                    if reserved >= cap:
                        break
                    if (day, p1) in sec_busy:
                        continue
                    if (ct_id, day, p1) in tbusy:
                        missed += 1
                        continue
                    placed_docs.append(mk(day, p1, csubj, ct_id))
                    sec_busy.add((day, p1))
                    tbusy.add((ct_id, day, p1))
                    load[ct_id] = load.get(ct_id, 0) + 1
                    placed_here += 1
                    reserved += 1
                    preplaced[csubj] = preplaced.get(csubj, 0) + 1
                if missed:
                    unplaced.append({"section": section, "subject": csubj, "periods_short": missed,
                                     "cause": "ct_first_period_shortfall",
                                     "reason": f"{csubj}: class teacher's Period 1 could not be reserved on {missed} day(s) "
                                               f"— the class teacher is already teaching another grade at P1 then.",
                                     "suggestions": [
                                         {"label": "Pick a different class teacher", "href": href_staff},
                                         {"label": "Or accept partial Period 1 cover", "href": href_staff}]})

        ordered = sorted(sec_reqs, key=lambda r: (0 if (r.get("must_be_consecutive") and (r.get("consecutive_periods") or 1) > 1) else 1,
                                              -(r.get("periods_per_week") or 0)))
        for r in ordered:
            subj = r["subject"]
            orig_ppw = int(r.get("periods_per_week") or 0)
            ppw = eff.get(subj, orig_ppw)
            required_here += ppw
            C = int(r.get("consecutive_periods") or 1)
            must = bool(r.get("must_be_consecutive")) and C > 1
            pool = list(r.get("teacher_ids") or [])
            sec_teacher = (r.get("section_teachers") or {}).get(section)

            def pick(day, block):
                cands = [sec_teacher] if sec_teacher else sorted(pool, key=lambda t: load.get(t, 0))
                for t in cands:
                    if t and all((t, day, p) not in tbusy for p in block):
                        return t
                return None if (sec_teacher or pool) else ""

            need = ppw - preplaced.get(subj, 0)  # P1 reservations already count toward quota
            if ppw > 0 and not sec_teacher and not pool:
                unplaced.append({"section": section, "subject": subj, "periods_short": 0,
                                 "cause": "no_teacher",
                                 "reason": f"{subj}: offered to {cn} - {section} but no teacher is assigned — "
                                           f"periods were placed unstaffed.",
                                 "suggestions": [{"label": f"Assign a {subj} teacher for section {section}", "href": href_subjects}]})
            if must:
                blocks_needed = need // C
                teaching_set = set(teaching)
                passes = 0
                while blocks_needed > 0 and passes < len(days) * len(teaching):
                    progressed = False
                    for day in days:
                        if blocks_needed <= 0:
                            break
                        for start in teaching:
                            window = list(range(start, start + C))
                            if any(p not in teaching_set for p in window):
                                continue  # not truly adjacent (break in between / off the end)
                            if any((day, p) in sec_busy for p in window):
                                continue
                            t = pick(day, window)
                            if t is None:
                                continue
                            for p in window:
                                placed_docs.append(mk(day, p, subj, t))
                                sec_busy.add((day, p))
                                if t:
                                    tbusy.add((t, day, p))
                            if t:
                                load[t] = load.get(t, 0) + C
                            placed_here += C
                            need -= C
                            blocks_needed -= 1
                            progressed = True
                            break  # at most one block per day per pass → spreads across days
                    passes += 1
                    if not progressed:
                        break
            if need > 0 and must:
                is_flex = _req_flexible(r)
                if auto_balance and is_flex:
                    # AUTO-BALANCE (relax consecutive — last resort, flexible only): drop the
                    # all-in-a-row constraint and let the remaining periods land as singles below.
                    auto_adjustments.append({
                        "section": section, "subject": subj, "type": "relax_consecutive",
                        "from": f"{C}-in-a-row", "to": "singles allowed",
                        "detail": f"{subj}: relaxed the consecutive rule for {cn} - {section} — no run of "
                                  f"{C} free periods was available, so periods were placed singly."})
                    must = False
                else:
                    # brief: skip-and-report unmet consecutive BLOCKS rather than place violating singles.
                    remainder = ppw % C
                    unmet_blocks = need - remainder
                    if unmet_blocks > 0:
                        unplaced.append({"section": section, "subject": subj, "periods_short": unmet_blocks,
                                         "cause": "consecutive_unplaceable",
                                         "reason": f"{subj}: needed {unmet_blocks // C} more consecutive block(s) of {C}; "
                                                   f"no run of {C} open periods was free across {len(days)} day(s)",
                                         "suggestions": [
                                             {"label": "Set must-be-consecutive to No", "href": href_subjects},
                                             {"label": f"Reduce consecutive from {C} to {max(C - 1, 1)}", "href": href_subjects}]})
                    need = remainder  # only the sub-block remainder may be placed as singles
            di, guard = 0, 0
            while need > 0 and guard < len(days) * (len(teaching) + 1) + 5:
                day = days[di % len(days)]
                di += 1
                guard += 1
                slot = next((p for p in teaching if (day, p) not in sec_busy), None)
                if slot is None:
                    continue
                t = pick(day, [slot])
                if t is None:
                    continue
                placed_docs.append(mk(day, slot, subj, t))
                sec_busy.add((day, slot))
                if t:
                    tbusy.add((t, day, slot))
                    load[t] = load.get(t, 0) + 1
                placed_here += 1
                need -= 1
            if need > 0:
                if must:
                    unplaced.append({"section": section, "subject": subj, "periods_short": need,
                                     "cause": "consecutive_unplaceable",
                                     "reason": f"{subj}: needed {C} consecutive free periods for {max(need // C, 1)} more block(s); "
                                               f"no run of {C} open periods was free across {len(days)} day(s)",
                                     "suggestions": [
                                         {"label": "Set must-be-consecutive to No", "href": href_subjects},
                                         {"label": f"Reduce consecutive from {C} to {max(C - 1, 1)}", "href": href_subjects}]})
                else:
                    free_slots = len(days) * len(teaching) - len(sec_busy)
                    if free_slots <= 0:
                        used, total = len(sec_busy), len(days) * len(teaching)
                        unplaced.append({"section": section, "subject": subj, "periods_short": need,
                                         "cause": "slots_full",
                                         "reason": f"{subj}: {need} period(s) could not fit — {cn} - {section}'s week is "
                                                   f"full ({used}/{total} slots used). Total demand exceeds capacity.",
                                         "suggestions": [{"label": f"Reduce total weekly periods for {cn}", "href": href_req}]})
                    else:
                        unplaced.append({"section": section, "subject": subj, "periods_short": need,
                                         "cause": "pool_exhausted",
                                         "reason": f"{subj}: {need} period(s) could not fit — every {subj} teacher was "
                                                   f"already busy at the remaining {free_slots} free slot(s).",
                                         "suggestions": [
                                             {"label": f"Add another {subj} teacher to {cn}", "href": href_subjects},
                                             {"label": f"Reduce {subj} periods/week (now {ppw})", "href": href_subjects}]})
        # Phase 12 AUTO-BALANCE (top-up): fill leftover empty slots with FLEXIBLE subjects (that
        # have a teacher), up to each subject's max_periods. Only empty slots are used, so required
        # subjects are never displaced.
        if auto_balance:
            placed_cnt = {}
            for d in placed_docs:
                if d["section"] == section:
                    placed_cnt[d["subject"]] = placed_cnt.get(d["subject"], 0) + 1
            for r in sec_reqs:
                if not _req_flexible(r):
                    continue
                subj = r["subject"]
                sec_teacher = (r.get("section_teachers") or {}).get(section)
                pool = list(r.get("teacher_ids") or [])
                if not sec_teacher and not pool:
                    continue  # never top up an unstaffed subject
                mx = _req_max(r, int(r.get("periods_per_week") or 0))
                start_cnt = placed_cnt.get(subj, 0)
                cur = start_cnt

                def pick_topup(day, p):
                    cands = [sec_teacher] if sec_teacher else sorted(pool, key=lambda t: load.get(t, 0))
                    for t in cands:
                        if t and (t, day, p) not in tbusy:
                            return t
                    return None

                guard2 = 0
                while cur < mx and guard2 < len(days) + 2:
                    placed_any = False
                    for day in days:
                        if cur >= mx:
                            break
                        slot = next((p for p in teaching if (day, p) not in sec_busy), None)
                        if slot is None:
                            continue
                        t = pick_topup(day, slot)
                        if t is None:
                            continue
                        placed_docs.append(mk(day, slot, subj, t))
                        sec_busy.add((day, slot))
                        tbusy.add((t, day, slot))
                        load[t] = load.get(t, 0) + 1
                        placed_here += 1
                        cur += 1
                        placed_any = True
                    guard2 += 1
                    if not placed_any:
                        break
                if cur > start_cnt:
                    auto_adjustments.append({
                        "section": section, "subject": subj, "type": "topup", "from": start_cnt, "to": cur,
                        "detail": f"{subj}: added {cur - start_cnt} period(s) into empty slots (up to max {mx})."})
        per_section[section] = {"placed": placed_here, "required": required_here}
    if placed_docs:
        await db.timetable_entries.insert_many([dict(d) for d in placed_docs])
    summary = {"placed_count": len(placed_docs), "unplaced": unplaced, "soft_violations": [],
               "per_section_summary": per_section, "sections": sections,
               "auto_balance": auto_balance, "auto_adjustments": auto_adjustments}
    batch = {"id": batch_id, "institution_id": iid, "academic_year": ay, "class_name": cn,
             "state": "generated", "summary": summary, "created_by": user["id"], "created_at": now_iso()}
    await db.timetable_batches.insert_one(dict(batch))
    await audit(user, "generate", "timetable_batches", batch_id,
                f"{cn}: {len(placed_docs)} placed, {sum(u['periods_short'] for u in unplaced)} short"
                + (f", auto-balance {len(auto_adjustments)} adjustment(s)" if auto_balance else ""))
    return {"batch_id": batch_id, **summary}


@api.post("/timetable/approve")
async def tt_approve(body: BatchActionRequest, user: dict = Depends(require_admin_or_principal)):
    iid = user["institution_id"]
    batch = await db.timetable_batches.find_one({"id": body.batch_id, "institution_id": iid}, {"_id": 0})
    if not batch:
        raise HTTPException(status_code=404, detail="Draft batch not found")
    await guard_principal_class(user, batch["class_name"])
    await db.timetable_batches.update_one({"id": batch["id"]},
        {"$set": {"state": "approved", "approved_at": now_iso(), "approved_by": user["id"]}})
    await audit(user, "approve", "timetable_batches", batch["id"], batch["class_name"])
    return {"ok": True, "batch_id": batch["id"], "state": "approved"}


@api.post("/timetable/publish")
async def tt_publish(body: BatchActionRequest, user: dict = Depends(require_admin_or_principal)):
    iid = user["institution_id"]
    batch = await db.timetable_batches.find_one({"id": body.batch_id, "institution_id": iid}, {"_id": 0})
    if not batch:
        raise HTTPException(status_code=404, detail="Draft batch not found")
    cn, ay = batch["class_name"], batch["academic_year"]
    await guard_principal_class(user, cn)
    await db.timetable_entries.delete_many(
        {"institution_id": iid, "academic_year": ay, "class_name": cn, **PUBLISHED_MATCH})
    res = await db.timetable_entries.update_many(
        {"institution_id": iid, "batch_id": batch["id"], "publish_state": "draft"},
        {"$set": {"publish_state": "published", "published_at": now_iso(), "published_by": user["id"], "batch_id": None}})
    await db.timetable_batches.update_one({"id": batch["id"]},
        {"$set": {"state": "published", "published_at": now_iso(), "published_by": user["id"]}})
    await audit(user, "publish", "timetable_batches", batch["id"], f"{cn}: {res.modified_count} periods live")
    # notify teachers who teach this class + in-scope managers
    tids = await db.timetable_entries.distinct("teacher_id",
        {"institution_id": iid, "academic_year": ay, "class_name": cn, "publish_state": "published"})
    for tid in tids:
        if tid:
            await _notify(iid, tid, "timetable_published", "Timetable published",
                          f"The {cn} timetable is now live", batch["id"])
    await _notify_managers(iid, "timetable_published", "Timetable published",
                           f"{cn} timetable was published ({res.modified_count} periods)", batch["id"],
                           class_names=[cn], exclude=user["id"])
    return {"ok": True, "class_name": cn, "published": res.modified_count}


@api.post("/timetable/unpublish")
async def tt_unpublish(body: UnpublishRequest, user: dict = Depends(require_admin_or_principal)):
    iid = user["institution_id"]
    cn = body.class_name.strip()
    ay = (body.academic_year or "").strip() or await _active_year_name(iid)
    await guard_principal_class(user, cn)
    res = await db.timetable_entries.update_many(
        {"institution_id": iid, "academic_year": ay, "class_name": cn, **PUBLISHED_MATCH},
        {"$set": {"publish_state": "unpublished"}})
    await audit(user, "unpublish", "timetable_entries", cn, f"{cn}: {res.modified_count} periods pulled")
    return {"ok": True, "class_name": cn, "unpublished": res.modified_count}


# ================= Phase 10: teacher absence + substitution engine =================
# DATA MODEL (all additive, date-specific — never mutates the weekly published timetable):
#   absences:      {id, institution_id, teacher_id, teacher_name, date (YYYY-MM-DD), academic_year,
#                   reason, status (requested|approved|rejected|cancelled), requested_by, approved_by, ...}
#   substitutions: {id, institution_id, absence_id, date, day, period_no, academic_year, class_name,
#                   section, subject, original_teacher_id, original_entry_id,
#                   status (open|requested|assigned), substitute_teacher_id, substitute_name,
#                   requested_teacher_ids[], responses {tid: accepted|declined}, assigned_by, ...}
#   notifications: {id, institution_id, user_id, type, title, body, related_id, read, created_at}
# Affected periods are auto-detected from the teacher's PUBLISHED entries on the absence weekday and
# respect per-section offerings (each published entry already carries class_name+section+subject).


class AbsenceCreate(BaseModel):
    teacher_id: str
    date: str
    reason: Optional[str] = ""
    academic_year: Optional[str] = ""


class SubAssignRequest(BaseModel):
    teacher_id: str


class SubRequestRequest(BaseModel):
    teacher_ids: List[str] = PField(default_factory=list)


class SubRespondRequest(BaseModel):
    accept: bool


def _weekday_code(date_str: str):
    try:
        import datetime as _dt
        return TT_DAYS[_dt.date.fromisoformat(date_str).weekday()]
    except (ValueError, IndexError):
        raise HTTPException(status_code=400, detail="Date must be a valid YYYY-MM-DD")


async def _notify(iid, user_id, ntype, title, body, related_id=None):
    if not user_id:
        return
    await db.notifications.insert_one({
        "id": str(uuid.uuid4()), "institution_id": iid, "user_id": user_id, "type": ntype,
        "title": title, "body": body, "related_id": related_id, "read": False, "created_at": now_iso()})


async def _manager_recipients(iid, class_names=None, teacher_id=None):
    """User ids to notify for a management event: all institution admins + every principal whose
    scope covers the event (whole-school always; unit principals only if a class is in their units)."""
    recips = set()
    async for u in db.users.find({"institution_id": iid, "role": "institution_admin"}, {"_id": 0, "id": 1}):
        recips.add(u["id"])
    names = set(class_names or [])
    if teacher_id and not names:
        for a in await db.teacher_assignments.find({"institution_id": iid, "teacher_id": teacher_id}, {"_id": 0, "class_name": 1}).to_list(1000):
            if a.get("class_name"):
                names.add(a["class_name"])
        for e in await db.timetable_entries.find({"institution_id": iid, "teacher_id": teacher_id}, {"_id": 0, "class_name": 1}).to_list(1000):
            if e.get("class_name"):
                names.add(e["class_name"])
    async for pa in db.principal_assignments.find({"institution_id": iid}, {"_id": 0}):
        if pa.get("scope_type") == "whole_school":
            recips.add(pa["user_id"])
            continue
        pcls = {c["name"] for c in await db.classes.find(
            {"institution_id": iid, "academic_unit_id": {"$in": pa.get("unit_ids") or []}}, {"_id": 0, "name": 1}).to_list(2000)}
        if not names or (names & pcls):
            recips.add(pa["user_id"])
    return recips


async def _notify_managers(iid, ntype, title, body, related_id=None, class_names=None, teacher_id=None, exclude=None):
    for uid in await _manager_recipients(iid, class_names, teacher_id):
        if exclude and uid == exclude:
            continue
        await _notify(iid, uid, ntype, title, body, related_id)


async def _absence_in_scope(user, teacher_id):
    """A unit principal may act on a teacher only if that teacher has an assignment/timetable in scope."""
    scope = await principal_scope(user)
    if not scope or scope["whole_school"]:
        return True
    names = scope["class_names"] or []
    if not names:
        return False
    q = {"institution_id": user["institution_id"], "teacher_id": teacher_id, "class_name": {"$in": names}}
    return bool(await db.teacher_assignments.find_one(q) or await db.timetable_entries.find_one(q))


async def _detect_affected(iid, teacher_id, date, ay):
    day = _weekday_code(date)
    entries = await db.timetable_entries.find(
        {"institution_id": iid, "academic_year": ay, "teacher_id": teacher_id, "day": day,
         "status": "active", **PUBLISHED_MATCH}, {"_id": 0}).to_list(500)
    return day, [e for e in entries if _tt_effective_now(e)]


async def _create_subs_for_absence(iid, absence, user):
    """Create one OPEN substitution per affected published period, scoped for a unit principal."""
    day, affected = await _detect_affected(iid, absence["teacher_id"], absence["date"], absence["academic_year"])
    scope = await principal_scope(user)
    scoped_names = None if (not scope or scope["whole_school"]) else set(scope["class_names"] or [])
    created = 0
    for e in affected:
        if scoped_names is not None and e["class_name"] not in scoped_names:
            continue
        if await db.substitutions.find_one({"institution_id": iid, "absence_id": absence["id"],
                                            "original_entry_id": e["id"]}):
            continue
        await db.substitutions.insert_one({
            "id": str(uuid.uuid4()), "institution_id": iid, "absence_id": absence["id"],
            "date": absence["date"], "day": day, "period_no": e["period_no"],
            "academic_year": absence["academic_year"], "class_name": e["class_name"],
            "section": e.get("section"), "subject": e["subject"],
            "original_teacher_id": absence["teacher_id"], "original_entry_id": e["id"],
            "status": "open", "substitute_teacher_id": None, "substitute_name": None,
            "requested_teacher_ids": [], "responses": {}, "assigned_by": None, "created_at": now_iso()})
        created += 1
    return created


@api.post("/absences")
async def create_absence(body: AbsenceCreate, user: dict = Depends(get_current_user)):
    iid = user["institution_id"]
    if not iid:
        raise HTTPException(status_code=403, detail="Access denied")
    ay = (body.academic_year or "").strip() or await _active_year_name(iid)
    _weekday_code(body.date)
    teacher = await db.users.find_one({"id": body.teacher_id, "institution_id": iid, "role": "teacher"}, {"_id": 0})
    if not teacher:
        raise HTTPException(status_code=400, detail="Teacher not found")
    is_admin = user.get("role") == "institution_admin"
    pa = await active_principal(user)
    is_mgr = is_admin or bool(pa)
    if not is_mgr and body.teacher_id != user["id"]:
        raise HTTPException(status_code=403, detail="Teachers can only request their own absence")
    if is_mgr and not is_admin and not await _absence_in_scope(user, body.teacher_id):
        raise HTTPException(status_code=403, detail="That teacher is outside your assigned scope")
    if await db.absences.find_one({"institution_id": iid, "teacher_id": body.teacher_id, "date": body.date,
                                   "status": {"$in": ["requested", "approved"]}}):
        raise HTTPException(status_code=400, detail="An absence for this teacher on this date already exists")
    status = "approved" if is_mgr else "requested"
    doc = {"id": str(uuid.uuid4()), "institution_id": iid, "teacher_id": body.teacher_id,
           "teacher_name": teacher.get("name"), "date": body.date, "academic_year": ay,
           "reason": (body.reason or "").strip(), "status": status,
           "requested_by": user["id"], "approved_by": user["id"] if is_mgr else None,
           "created_at": now_iso()}
    await db.absences.insert_one(dict(doc))
    doc.pop("_id", None)
    subs_created = 0
    if is_mgr:
        subs_created = await _create_subs_for_absence(iid, doc, user)
    else:
        await _notify_managers(iid, "absence_request", "Absence requested",
                               f"{teacher.get('name')} requested leave on {body.date}", doc["id"],
                               teacher_id=body.teacher_id)
    await audit(user, "create_absence", "absences", doc["id"], f"{teacher.get('name')} · {body.date} · {status}")
    return {"absence": doc, "substitutions_created": subs_created}


@api.post("/absences/{absence_id}/approve")
async def approve_absence(absence_id: str, user: dict = Depends(require_admin_or_principal)):
    iid = user["institution_id"]
    ab = await db.absences.find_one({"id": absence_id, "institution_id": iid}, {"_id": 0})
    if not ab:
        raise HTTPException(status_code=404, detail="Absence not found")
    if user.get("role") != "institution_admin" and not await _absence_in_scope(user, ab["teacher_id"]):
        raise HTTPException(status_code=403, detail="Outside your assigned scope")
    if ab["status"] != "requested":
        raise HTTPException(status_code=400, detail=f"Absence is already {ab['status']}")
    await db.absences.update_one({"id": absence_id}, {"$set": {"status": "approved", "approved_by": user["id"]}})
    ab["status"] = "approved"
    subs = await _create_subs_for_absence(iid, ab, user)
    await _notify(iid, ab["teacher_id"], "absence_approved", "Absence approved",
                  f"Your leave on {ab['date']} was approved", absence_id)
    await audit(user, "approve_absence", "absences", absence_id, ab.get("teacher_name"))
    return {"ok": True, "substitutions_created": subs}


@api.post("/absences/{absence_id}/reject")
async def reject_absence(absence_id: str, user: dict = Depends(require_admin_or_principal)):
    iid = user["institution_id"]
    ab = await db.absences.find_one({"id": absence_id, "institution_id": iid}, {"_id": 0})
    if not ab:
        raise HTTPException(status_code=404, detail="Absence not found")
    if user.get("role") != "institution_admin" and not await _absence_in_scope(user, ab["teacher_id"]):
        raise HTTPException(status_code=403, detail="Outside your assigned scope")
    await db.absences.update_one({"id": absence_id}, {"$set": {"status": "rejected", "approved_by": user["id"]}})
    await _notify(iid, ab["teacher_id"], "absence_rejected", "Absence not approved",
                  f"Your leave request on {ab['date']} was not approved", absence_id)
    await audit(user, "reject_absence", "absences", absence_id, ab.get("teacher_name"))
    return {"ok": True}


# ---------------- Phase 52: cancel absence / remove single cover (past periods kept as history) ----------------

class CancelAbsenceRequest(BaseModel):
    reason: str = PField(..., min_length=3, max_length=300)


class RemoveCoverRequest(BaseModel):
    reason: Optional[str] = PField(default="", max_length=300)


async def _sub_now(iid):
    return datetime.now(await _inst_tz(iid))


async def _period_start_dt(iid, academic_year, class_name, date, period_no):
    """Start of a period on a date, in the institution timezone (date start if the bell has no time)."""
    import datetime as _dt
    tz = await _inst_tz(iid)
    cls = await db.classes.find_one({"institution_id": iid, "name": class_name}, {"_id": 0, "academic_unit_id": 1}) or {}
    cfg = await effective_tt_config(iid, academic_year, cls.get("academic_unit_id"))
    start = ""
    if 1 <= period_no <= len(cfg["periods"]):
        start = cfg["periods"][period_no - 1].get("start") or ""
    try:
        hh, mm = (int(x) for x in start.split(":")[:2])
    except ValueError:
        hh, mm = 0, 0
    return _dt.datetime.combine(_dt.date.fromisoformat(date), _dt.time(hh, mm), tzinfo=tz)


async def _sub_cancellable(iid, sub, now=None):
    now = now or await _sub_now(iid)
    return await _period_start_dt(iid, sub["academic_year"], sub["class_name"], sub["date"], sub["period_no"]) > now


async def _notify_and_stub(iid, uid, ntype, title, body, related_id, actor=None, module="substitution"):
    """In-app bell + one STUB/test-mode SMS via the comm engine (bell only when no phone or channel refused)."""
    await _notify(iid, uid, ntype, title, body, related_id)
    u = await db.users.find_one({"id": uid, "institution_id": iid}, {"_id": 0, "name": 1, "phone": 1})
    phone = _norm_phone((u or {}).get("phone"))
    if not phone:
        return "bell_only_no_phone"
    try:
        res = await send_message(iid, "sms", [{"name": u.get("name"), "phone": phone, "body": f"{title}: {body}"}],
                                 module=module, meta={"related_id": related_id}, actor=actor)
        return "sent" if res.get("sent") else "bell_only_failed"
    except HTTPException:
        return "bell_only_failed"


async def _period_label(iid, academic_year, class_name, period_no):
    """Bell label for a 1-based slot index (slots include breaks, e.g. slot 7 → "P5")."""
    cls = await db.classes.find_one({"institution_id": iid, "name": class_name}, {"_id": 0, "academic_unit_id": 1}) or {}
    periods = (await effective_tt_config(iid, academic_year, cls.get("academic_unit_id")))["periods"]
    return periods[period_no - 1].get("label") if 1 <= period_no <= len(periods) else f"P{period_no}"


async def _sub_label(s):
    return f"{s['class_name']} {s.get('section') or ''}".strip() + " " + await _period_label(s["institution_id"], s["academic_year"], s["class_name"], s["period_no"])


async def _absence_cancel_guard(user, ab):
    is_admin = user.get("role") == "institution_admin"
    pa = await active_principal(user)
    own = ab["teacher_id"] == user["id"]
    if is_admin:
        return
    if pa and (own or await _absence_in_scope(user, ab["teacher_id"])):
        return
    if pa and not own:
        raise HTTPException(status_code=403, detail="That teacher is outside your assigned scope")
    if not own:
        raise HTTPException(status_code=403, detail="Access denied")
    # a teacher may cancel their own leave only before it starts
    first = await _period_start_dt(user["institution_id"], ab["academic_year"], "", ab["date"], 1)
    if first <= await _sub_now(user["institution_id"]):
        raise HTTPException(status_code=400, detail="This leave has already started — ask your principal or admin")


async def _cancel_preview(iid, ab):
    now = await _sub_now(iid)
    subs = await db.substitutions.find({"institution_id": iid, "absence_id": ab["id"], "status": {"$ne": "cancelled"}},
                                       {"_id": 0}).sort("period_no", 1).to_list(200)
    rows = []
    for s in subs:
        rows.append({"id": s["id"], "period_no": s["period_no"], "class_name": s["class_name"], "section": s.get("section"),
                     "period_label": await _period_label(iid, s["academic_year"], s["class_name"], s["period_no"]),
                     "subject": s["subject"], "status": s["status"], "substitute_name": s.get("substitute_name"),
                     "asked": len(s.get("requested_teacher_ids") or []), "cancellable": await _sub_cancellable(iid, s, now)})
    canc = [r for r in rows if r["cancellable"]]
    return {"absence": ab, "periods": rows,
            "assigned_count": sum(1 for r in canc if r["status"] == "assigned"),
            "asked_count": sum(r["asked"] for r in canc if r["status"] == "requested"),
            "kept_periods": [r["period_no"] for r in rows if not r["cancellable"]]}


@api.get("/absences/{absence_id}/cancel-preview")
async def absence_cancel_preview(absence_id: str, user: dict = Depends(get_current_user)):
    iid = user["institution_id"]
    ab = await db.absences.find_one({"id": absence_id, "institution_id": iid}, {"_id": 0})
    if not ab:
        raise HTTPException(status_code=404, detail="Absence not found")
    await _absence_cancel_guard(user, ab)
    return await _cancel_preview(iid, ab)


@api.post("/absences/{absence_id}/cancel")
async def cancel_absence(absence_id: str, body: CancelAbsenceRequest, user: dict = Depends(get_current_user)):
    """Cancel an absence: future covers/asks → cancelled (never deleted), substitutes + original teacher
    notified (bell + STUB SMS). Periods that have already started stay as history."""
    iid = user["institution_id"]
    ab = await db.absences.find_one({"id": absence_id, "institution_id": iid}, {"_id": 0})
    if not ab:
        raise HTTPException(status_code=404, detail="Absence not found")
    await _absence_cancel_guard(user, ab)
    if ab["status"] not in ("requested", "approved"):
        raise HTTPException(status_code=400, detail=f"Absence is already {ab['status']}")
    reason = body.reason.strip()
    if len(reason) < 3:
        raise HTTPException(status_code=400, detail="Give a reason (3–300 characters)")
    prev = await _cancel_preview(iid, ab)
    tname = ab.get("teacher_name") or "The teacher"
    cancelled, notified = 0, 0
    for row in prev["periods"]:
        if not row["cancellable"]:
            continue
        s = await db.substitutions.find_one({"id": row["id"]}, {"_id": 0})
        msg = f"Cover for {await _sub_label(s)} on {s['date']} is cancelled — {tname} is back"
        targets = set(s.get("requested_teacher_ids") or [])
        if s.get("substitute_teacher_id"):
            targets.add(s["substitute_teacher_id"])
        for tid in targets:
            await _notify_and_stub(iid, tid, "sub_cancelled", "Cover cancelled", msg, s["id"], actor=user)
            notified += 1
        await db.substitutions.update_one({"id": s["id"]}, {"$set": {
            "status": "cancelled", "previous_status": s["status"], "cancelled_at": now_iso(), "cancelled_by": user["id"],
            "cancel_reason": reason, "updated_at": now_iso()}})
        cancelled += 1
    await db.absences.update_one({"id": absence_id}, {"$set": {
        "status": "cancelled", "cancelled_at": now_iso(), "cancelled_by": user["id"], "cancelled_by_name": user.get("name"),
        "cancel_reason": reason, "kept_periods": prev["kept_periods"]}})
    if ab["teacher_id"] != user["id"]:
        await _notify_and_stub(iid, ab["teacher_id"], "absence_cancelled", "Absence cancelled",
                               f"Your absence on {ab['date']} was cancelled — you are back on your timetable", absence_id, actor=user)
    await audit(user, "cancel_absence", "absences", absence_id,
                f"{tname} · {ab['date']} · {cancelled} cover(s) cancelled, {len(prev['kept_periods'])} kept · {reason}")
    return {"ok": True, "substitutions_cancelled": cancelled, "notified": notified, "kept_periods": prev["kept_periods"]}


@api.post("/substitutions/{sub_id}/remove-cover")
async def remove_cover(sub_id: str, body: RemoveCoverRequest = Body(default=RemoveCoverRequest()),
                       user: dict = Depends(require_admin_or_principal)):
    """Remove one period's substitute (or withdraw its asks): back to Needs cover; notifies only that substitute."""
    iid = user["institution_id"]
    s = await db.substitutions.find_one({"id": sub_id, "institution_id": iid}, {"_id": 0})
    if not s:
        raise HTTPException(status_code=404, detail="Substitution not found")
    await guard_principal_class(user, s["class_name"])
    if s["status"] not in ("assigned", "requested"):
        raise HTTPException(status_code=400, detail="This period has no cover to remove")
    if not await _sub_cancellable(iid, s):
        raise HTTPException(status_code=400, detail="This period has already started — it is kept as history")
    msg = f"Cover for {await _sub_label(s)} on {s['date']} is cancelled — you are no longer needed"
    targets = [s["substitute_teacher_id"]] if s["status"] == "assigned" and s.get("substitute_teacher_id") \
        else list(s.get("requested_teacher_ids") or [])
    for tid in targets:
        await _notify_and_stub(iid, tid, "sub_cancelled", "Cover cancelled", msg, s["id"], actor=user)
    hist = list(s.get("cover_history") or []) + [{"action": "removed", "status": s["status"], "teacher_id": s.get("substitute_teacher_id"),
                                                  "teacher_name": s.get("substitute_name"), "by": user["id"],
                                                  "reason": (body.reason or "").strip(), "at": now_iso()}]
    await db.substitutions.update_one({"id": sub_id}, {"$set": {
        "status": "open", "substitute_teacher_id": None, "substitute_name": None, "requested_teacher_ids": [],
        "responses": {}, "cover_history": hist, "updated_at": now_iso()}})
    await audit(user, "remove_cover", "substitutions", sub_id, f"{await _sub_label(s)} {s['date']} · {s.get('substitute_name') or 'asks withdrawn'}")
    return {"ok": True, "notified": len(targets)}


def _scope_sub_query(iid, scope):
    q = {"institution_id": iid}
    if scope and not scope["whole_school"]:
        q["class_name"] = {"$in": scope["class_names"] or ["__none__"]}
    return q


@api.get("/absences")
async def list_absences(date: str = "", status: str = "", user: dict = Depends(get_current_user)):
    iid = user["institution_id"]
    if not iid:
        raise HTTPException(status_code=403, detail="Access denied")
    is_admin = user.get("role") == "institution_admin"
    pa = await active_principal(user)
    q = {"institution_id": iid}
    if date:
        q["date"] = date
    if status:
        q["status"] = status
    rows = await db.absences.find(q, {"_id": 0}).sort([("date", -1), ("created_at", -1)]).to_list(1000)
    if not is_admin and not pa:
        rows = [a for a in rows if a["teacher_id"] == user["id"]]
    elif pa and not is_admin:
        scope = await principal_scope(user)
        if scope and not scope["whole_school"]:
            keep = []
            for a in rows:
                if a["teacher_id"] == user["id"] or await _absence_in_scope(user, a["teacher_id"]):
                    keep.append(a)
            rows = keep
    return {"absences": rows}


@api.get("/absences/{absence_id}")
async def absence_detail(absence_id: str, user: dict = Depends(require_admin_or_principal)):
    iid = user["institution_id"]
    ab = await db.absences.find_one({"id": absence_id, "institution_id": iid}, {"_id": 0})
    if not ab:
        raise HTTPException(status_code=404, detail="Absence not found")
    subs = await db.substitutions.find({"institution_id": iid, "absence_id": absence_id}, {"_id": 0}).sort("period_no", 1).to_list(200)
    scope = await principal_scope(user)
    if scope and not scope["whole_school"]:
        names = set(scope["class_names"] or [])
        subs = [s for s in subs if s["class_name"] in names]
    for s in subs:
        s["period_label"] = await _period_label(iid, s["academic_year"], s["class_name"], s["period_no"])
    return {"absence": ab, "substitutions": subs}


async def _busy_teacher_ids(iid, ay, day, period_no, date):
    """Teacher ids that CANNOT substitute at (day, period_no) on `date`: already teaching (published),
    already assigned another substitution that slot, or themselves absent that date."""
    busy = set()
    async for e in db.timetable_entries.find(
            {"institution_id": iid, "academic_year": ay, "day": day, "period_no": period_no,
             "status": "active", **PUBLISHED_MATCH}, {"_id": 0, "teacher_id": 1}):
        if e.get("teacher_id"):
            busy.add(e["teacher_id"])
    async for s in db.substitutions.find(
            {"institution_id": iid, "date": date, "period_no": period_no, "status": "assigned"},
            {"_id": 0, "substitute_teacher_id": 1}):
        if s.get("substitute_teacher_id"):
            busy.add(s["substitute_teacher_id"])
    async for a in db.absences.find({"institution_id": iid, "date": date, "status": "approved"},
                                    {"_id": 0, "teacher_id": 1}):
        busy.add(a["teacher_id"])
    return busy


@api.get("/substitutions/{sub_id}/suggestions")
async def sub_suggestions(sub_id: str, user: dict = Depends(require_admin_or_principal)):
    iid = user["institution_id"]
    sub = await db.substitutions.find_one({"id": sub_id, "institution_id": iid}, {"_id": 0})
    if not sub:
        raise HTTPException(status_code=404, detail="Substitution not found")
    await guard_principal_class(user, sub["class_name"])
    ay = sub["academic_year"]
    busy = await _busy_teacher_ids(iid, ay, sub["day"], sub["period_no"], sub["date"])
    busy.add(sub["original_teacher_id"])
    teachers = await db.users.find(
        {"institution_id": iid, "role": "teacher", "status": {"$ne": "inactive"}},
        {"_id": 0, "id": 1, "name": 1}).to_list(2000)
    # subject-match sets (respect per-section offerings)
    exact = {a["teacher_id"] for a in await db.teacher_assignments.find(
        {"institution_id": iid, "class_name": sub["class_name"], "section": sub.get("section"),
         "subject": sub["subject"], "teacher_id": {"$ne": None}}, {"_id": 0, "teacher_id": 1}).to_list(500)}
    same_subj = {a["teacher_id"] for a in await db.teacher_assignments.find(
        {"institution_id": iid, "subject": sub["subject"], "teacher_id": {"$ne": None}},
        {"_id": 0, "teacher_id": 1}).to_list(2000)}
    # daily workload (published periods that weekday) + substitution load that date
    day_load, sub_load = {}, {}
    async for e in db.timetable_entries.find(
            {"institution_id": iid, "academic_year": ay, "day": sub["day"], "status": "active", **PUBLISHED_MATCH},
            {"_id": 0, "teacher_id": 1}):
        if e.get("teacher_id"):
            day_load[e["teacher_id"]] = day_load.get(e["teacher_id"], 0) + 1
    async for s in db.substitutions.find({"institution_id": iid, "date": sub["date"], "status": "assigned"},
                                         {"_id": 0, "substitute_teacher_id": 1}):
        if s.get("substitute_teacher_id"):
            sub_load[s["substitute_teacher_id"]] = sub_load.get(s["substitute_teacher_id"], 0) + 1
    out = []
    for t in teachers:
        tid = t["id"]
        if tid in busy:
            continue
        if tid in exact:
            match, label = 2, "Teaches this subject to this section"
        elif tid in same_subj:
            match, label = 1, "Teaches this subject"
        else:
            match, label = 0, "Available (other subject)"
        out.append({"teacher_id": tid, "name": t["name"], "match": match, "match_label": label,
                    "day_periods": day_load.get(tid, 0), "subs_today": sub_load.get(tid, 0),
                    "requested": tid in (sub.get("requested_teacher_ids") or []),
                    "response": (sub.get("responses") or {}).get(tid)})
    out.sort(key=lambda x: (-x["match"], x["subs_today"], x["day_periods"], x["name"]))
    return {"substitution": sub, "suggestions": out}


async def _assign_sub(iid, sub, teacher, user):
    await db.substitutions.update_one({"id": sub["id"]}, {"$set": {
        "status": "assigned", "substitute_teacher_id": teacher["id"],
        "substitute_name": teacher.get("name"), "assigned_by": user["id"], "assigned_at": now_iso()}})
    await _notify(iid, teacher["id"], "sub_assigned", "Substitution assigned",
                  f"Cover {sub['class_name']} {sub.get('section') or ''} {sub['subject']} (P{sub['period_no']}) on {sub['date']}", sub["id"])


@api.post("/substitutions/{sub_id}/assign")
async def assign_substitution(sub_id: str, body: SubAssignRequest, user: dict = Depends(require_admin_or_principal)):
    iid = user["institution_id"]
    sub = await db.substitutions.find_one({"id": sub_id, "institution_id": iid}, {"_id": 0})
    if not sub:
        raise HTTPException(status_code=404, detail="Substitution not found")
    await guard_principal_class(user, sub["class_name"])
    teacher = await db.users.find_one({"id": body.teacher_id, "institution_id": iid, "role": "teacher"}, {"_id": 0})
    if not teacher:
        raise HTTPException(status_code=400, detail="Teacher not found")
    busy = await _busy_teacher_ids(iid, sub["academic_year"], sub["day"], sub["period_no"], sub["date"])
    if body.teacher_id in busy or body.teacher_id == sub["original_teacher_id"]:
        raise HTTPException(status_code=400, detail=f"{teacher.get('name')} is not free at that period (teaching, already substituting, or absent)")
    await _assign_sub(iid, sub, teacher, user)
    await audit(user, "assign_substitution", "substitutions", sub_id,
                f"{teacher.get('name')} → {sub['class_name']} {sub.get('section') or ''} P{sub['period_no']} {sub['date']}")
    return {"ok": True}


@api.post("/substitutions/{sub_id}/request")
async def request_substitution(sub_id: str, body: SubRequestRequest, user: dict = Depends(require_admin_or_principal)):
    iid = user["institution_id"]
    sub = await db.substitutions.find_one({"id": sub_id, "institution_id": iid}, {"_id": 0})
    if not sub:
        raise HTTPException(status_code=404, detail="Substitution not found")
    await guard_principal_class(user, sub["class_name"])
    if not body.teacher_ids:
        raise HTTPException(status_code=400, detail="Pick at least one teacher to request")
    reqd = list(dict.fromkeys(body.teacher_ids))
    await db.substitutions.update_one({"id": sub_id}, {"$set": {
        "status": "requested" if sub["status"] == "open" else sub["status"],
        "requested_teacher_ids": reqd}})
    for tid in reqd:
        await _notify(iid, tid, "sub_requested", "Substitution request",
                      f"Can you cover {sub['class_name']} {sub.get('section') or ''} {sub['subject']} (P{sub['period_no']}) on {sub['date']}?", sub_id)
    await audit(user, "request_substitution", "substitutions", sub_id, f"{len(reqd)} teacher(s) asked")
    return {"ok": True, "requested": len(reqd)}


@api.post("/substitutions/{sub_id}/respond")
async def respond_substitution(sub_id: str, body: SubRespondRequest, user: dict = Depends(get_current_user)):
    iid = user["institution_id"]
    sub = await db.substitutions.find_one({"id": sub_id, "institution_id": iid}, {"_id": 0})
    if not sub:
        raise HTTPException(status_code=404, detail="Substitution not found")
    if user["id"] not in (sub.get("requested_teacher_ids") or []):
        raise HTTPException(status_code=403, detail="You were not asked to cover this period")
    responses = dict(sub.get("responses") or {})
    responses[user["id"]] = "accepted" if body.accept else "declined"
    await db.substitutions.update_one({"id": sub_id}, {"$set": {"responses": responses}})
    # notify the in-scope managers (approver + principals of that class) via the trail
    verb = "accepted" if body.accept else "declined"
    await _notify_managers(iid, "sub_response", f"Cover {verb}",
                           f"{user.get('name')} {verb} {sub['class_name']} {sub.get('section') or ''} P{sub['period_no']} on {sub['date']}",
                           sub_id, class_names=[sub["class_name"]])
    await audit(user, "respond_substitution", "substitutions", sub_id, "accepted" if body.accept else "declined")
    return {"ok": True, "response": responses[user["id"]]}


@api.post("/substitutions/{sub_id}/clear")
async def clear_substitution(sub_id: str, user: dict = Depends(require_admin_or_principal)):
    iid = user["institution_id"]
    sub = await db.substitutions.find_one({"id": sub_id, "institution_id": iid}, {"_id": 0})
    if not sub:
        raise HTTPException(status_code=404, detail="Substitution not found")
    await guard_principal_class(user, sub["class_name"])
    await db.substitutions.update_one({"id": sub_id}, {"$set": {
        "status": "open", "substitute_teacher_id": None, "substitute_name": None,
        "requested_teacher_ids": [], "responses": {}}})
    await audit(user, "clear_substitution", "substitutions", sub_id, sub["class_name"])
    return {"ok": True}


@api.delete("/substitutions/{sub_id}")
async def delete_substitution(sub_id: str, user: dict = Depends(require_admin_or_principal)):
    """Hard delete (orphan cleanup). Admin + in-scope principal only; audit-logged."""
    iid = user["institution_id"]
    sub = await db.substitutions.find_one({"id": sub_id, "institution_id": iid}, {"_id": 0})
    if not sub:
        raise HTTPException(status_code=404, detail="Substitution not found")
    await guard_principal_class(user, sub["class_name"])
    await db.substitutions.delete_one({"id": sub_id})
    await audit(user, "delete_substitution", "substitutions", sub_id,
                f"{sub['class_name']} {sub.get('section') or ''} P{sub['period_no']} {sub['date']}")
    return {"ok": True}


@api.post("/absences/{absence_id}/auto-assign")
async def auto_assign_absence(absence_id: str, user: dict = Depends(require_admin_or_principal)):
    """Bulk: assign the best-ranked free teacher to every OPEN substitution of this absence."""
    iid = user["institution_id"]
    ab = await db.absences.find_one({"id": absence_id, "institution_id": iid}, {"_id": 0})
    if not ab:
        raise HTTPException(status_code=404, detail="Absence not found")
    subs = await db.substitutions.find({"institution_id": iid, "absence_id": absence_id, "status": "open"}, {"_id": 0}).to_list(200)
    scope = await principal_scope(user)
    assigned, skipped = 0, 0
    for sub in subs:
        if scope and not scope["whole_school"] and sub["class_name"] not in (scope["class_names"] or []):
            continue
        # recompute best candidate inline (same ranking as /suggestions)
        busy = await _busy_teacher_ids(iid, sub["academic_year"], sub["day"], sub["period_no"], sub["date"])
        busy.add(sub["original_teacher_id"])
        exact = {a["teacher_id"] for a in await db.teacher_assignments.find(
            {"institution_id": iid, "class_name": sub["class_name"], "section": sub.get("section"),
             "subject": sub["subject"], "teacher_id": {"$ne": None}}, {"_id": 0, "teacher_id": 1}).to_list(500)}
        same = {a["teacher_id"] for a in await db.teacher_assignments.find(
            {"institution_id": iid, "subject": sub["subject"], "teacher_id": {"$ne": None}}, {"_id": 0, "teacher_id": 1}).to_list(2000)}
        cands = [t for t in await db.users.find(
            {"institution_id": iid, "role": "teacher", "status": {"$ne": "inactive"}}, {"_id": 0, "id": 1, "name": 1}).to_list(2000)
            if t["id"] not in busy]
        if not cands:
            skipped += 1
            continue
        cands.sort(key=lambda t: (0 if t["id"] in exact else 1 if t["id"] in same else 2, t["name"]))
        best = cands[0]
        await _assign_sub(iid, sub, best, user)
        assigned += 1
    await audit(user, "auto_assign_absence", "absences", absence_id, f"{assigned} assigned, {skipped} unstaffed")
    return {"ok": True, "assigned": assigned, "skipped": skipped}


@api.get("/substitutions")
async def list_substitutions(date: str = "", status: str = "", user: dict = Depends(require_admin_or_principal)):
    iid = user["institution_id"]
    scope = await principal_scope(user)
    q = _scope_sub_query(iid, scope)
    if date:
        q["date"] = date
    if status:
        q["status"] = status
    else:
        q["status"] = {"$ne": "cancelled"}  # active lists hide cancelled; history via ?status=cancelled
    rows = await db.substitutions.find(q, {"_id": 0}).sort([("date", -1), ("period_no", 1)]).to_list(2000)
    return {"substitutions": rows}


@api.get("/substitutions/dashboard")
async def substitutions_dashboard(date: str = "", user: dict = Depends(require_admin_or_principal)):
    iid = user["institution_id"]
    import datetime as _dt
    date = date or _dt.date.today().isoformat()
    scope = await principal_scope(user)
    sq = _scope_sub_query(iid, scope)
    today_subs = await db.substitutions.find({**sq, "date": date}, {"_id": 0}).to_list(2000)
    open_n = sum(1 for s in today_subs if s["status"] == "open")
    req_n = sum(1 for s in today_subs if s["status"] == "requested")
    asg_n = sum(1 for s in today_subs if s["status"] == "assigned")
    # today's approved absences in scope
    abs_rows = await db.absences.find({"institution_id": iid, "date": date, "status": "approved"}, {"_id": 0}).to_list(1000)
    if scope and not scope["whole_school"]:
        keep = []
        for a in abs_rows:
            if await _absence_in_scope(user, a["teacher_id"]):
                keep.append(a)
        abs_rows = keep
    pending_abs = await db.absences.count_documents({"institution_id": iid, "status": "requested"})
    return {"date": date, "absent_today": len(abs_rows), "open": open_n, "requested": req_n,
            "assigned": asg_n, "pending_requests": pending_abs,
            "absences_today": abs_rows}


@api.get("/me/substitutions")
async def my_substitutions(user: dict = Depends(require_roles("institution_admin", "teacher"))):
    iid = user["institution_id"]
    assigned = await db.substitutions.find(
        {"institution_id": iid, "substitute_teacher_id": user["id"], "status": "assigned"}, {"_id": 0}).sort([("date", -1), ("period_no", 1)]).to_list(500)
    requests = await db.substitutions.find(
        {"institution_id": iid, "status": "requested", "requested_teacher_ids": user["id"]}, {"_id": 0}).sort([("date", 1), ("period_no", 1)]).to_list(500)
    return {"assigned": assigned, "requests": requests}


@api.get("/notifications")
async def list_notifications(limit: int = 20, skip: int = 0, user: dict = Depends(get_current_user)):
    iid = user["institution_id"]
    q = {"institution_id": iid, "user_id": user["id"]}
    total = await db.notifications.count_documents(q)
    unread = await db.notifications.count_documents({**q, "read": {"$ne": True}})
    rows = await db.notifications.find(q, {"_id": 0}).sort("created_at", -1).skip(max(skip, 0)).limit(min(max(limit, 1), 100)).to_list(100)
    return {"notifications": rows, "unread": unread, "total": total}


class MarkReadRequest(BaseModel):
    ids: List[str] = PField(default_factory=list)
    all: bool = False


@api.post("/notifications/mark-read")
async def mark_notifications_read(body: MarkReadRequest, user: dict = Depends(get_current_user)):
    iid = user["institution_id"]
    q = {"institution_id": iid, "user_id": user["id"]}
    if not body.all:
        if not body.ids:
            return {"ok": True, "modified": 0}
        q["id"] = {"$in": body.ids}
    r = await db.notifications.update_many(q, {"$set": {"read": True}})
    return {"ok": True, "modified": r.modified_count}


@api.post("/notifications/{nid}/read")
async def read_notification(nid: str, user: dict = Depends(get_current_user)):
    await db.notifications.update_one({"id": nid, "user_id": user["id"]}, {"$set": {"read": True}})
    return {"ok": True}



@api.get("/portal/timetable")
async def portal_timetable(user: dict = Depends(require_roles("student"))):
    iid = user["institution_id"]
    sid = user.get("student_id")
    student = await db.students.find_one({"id": sid, "institution_id": iid}, {"_id": 0, "password_hash": 0}) if sid else None
    if not student or not student.get("class_name"):
        return {"config": None, "entries": [], "academic_year": None}
    academic_year = await _active_year_name(iid)
    cls = await db.classes.find_one({"institution_id": iid, "name": student["class_name"]})
    cfg = await effective_tt_config(iid, academic_year, cls.get("academic_unit_id") if cls else None)
    entries = await db.timetable_entries.find(
        {"institution_id": iid, "academic_year": academic_year, "class_name": student["class_name"],
         "section": student.get("section"), "status": "active", **PUBLISHED_MATCH}, {"_id": 0}).to_list(500)
    entries = [e for e in entries if _tt_effective_now(e)]
    return {"config": cfg, "entries": entries, "academic_year": academic_year,
            "class_name": student["class_name"], "section": student.get("section"),
            "today_changes": await _section_cover_changes(iid, student["class_name"], student.get("section"))}


async def _section_cover_changes(iid, class_name, section):
    """Phase 52: today's (institution tz) cover state for ONE section — substitute display name only, never the reason."""
    today = (await _sub_now(iid)).date().isoformat()
    rows = await db.substitutions.find(
        {"institution_id": iid, "date": today, "class_name": class_name, "section": section,
         "status": {"$in": ["open", "requested", "assigned"]}},
        {"_id": 0, "absence_id": 1, "period_no": 1, "day": 1, "status": 1, "substitute_name": 1}).to_list(50)
    live = {a["id"] for a in await db.absences.find(
        {"institution_id": iid, "id": {"$in": [r["absence_id"] for r in rows]}, "status": "approved"}, {"_id": 0, "id": 1}).to_list(50)}
    ay = await _active_year_name(iid)
    items = [{"period_no": r["period_no"], "period_label": await _period_label(iid, ay, class_name, r["period_no"]),
              "kind": "substitute" if r["status"] == "assigned" else "absent",
              "substitute_name": r.get("substitute_name") if r["status"] == "assigned" else None}
             for r in sorted(rows, key=lambda r: r["period_no"]) if r["absence_id"] in live]
    return {"date": today, "day": _weekday_code(today), "items": items}


@api.get("/parent/child/{student_id}/timetable")
async def parent_child_timetable(student_id: str, user: dict = Depends(require_roles("parent"))):
    iid = user["institution_id"]
    if student_id not in (user.get("student_ids") or []):
        raise HTTPException(status_code=403, detail="This student is not linked to your account")
    st = await db.students.find_one({"id": student_id, "institution_id": iid}, {"_id": 0, "class_name": 1, "section": 1})
    if not st or not st.get("class_name"):
        return {"config": None, "entries": [], "academic_year": None, "today_changes": None}
    ay = await _active_year_name(iid)
    cls = await db.classes.find_one({"institution_id": iid, "name": st["class_name"]}, {"_id": 0, "academic_unit_id": 1}) or {}
    cfg = await effective_tt_config(iid, ay, cls.get("academic_unit_id"))
    entries = await db.timetable_entries.find(
        {"institution_id": iid, "academic_year": ay, "class_name": st["class_name"], "section": st.get("section"),
         "status": "active", **PUBLISHED_MATCH}, {"_id": 0, "id": 1, "day": 1, "period_no": 1, "subject": 1,
                                                  "teacher_name": 1, "room": 1, "type": 1, "effective_from": 1, "effective_to": 1}).to_list(500)
    entries = [e for e in entries if _tt_effective_now(e)]
    return {"config": cfg, "entries": entries, "academic_year": ay, "class_name": st["class_name"], "section": st.get("section"),
            "today_changes": await _section_cover_changes(iid, st["class_name"], st.get("section"))}


# ---------------- Phase 54: portal branding for any signed-in school user + monthly attendance calendar ----------------

@api.get("/me/branding")
async def my_school_branding(user: dict = Depends(get_current_user)):
    iid = user.get("institution_id")
    inst = await db.institutions.find_one({"id": iid}, {"_id": 0, "name": 1, "portal_name": 1, "slug": 1, "code": 1, "domain": 1, "logo_path": 1,
                                                        "logo_url": 1, "login_tagline": 1, "primary_color": 1}) if iid else None
    if not inst:
        raise HTTPException(status_code=404, detail="No school")
    b = _login_branding(inst)
    color = inst.get("primary_color") or (inst.get("logo_path") and _logo_accent(inst["logo_path"])) or None
    return {"name": b["name"], "logo_url": b["logo_url"], "tagline": b["tagline"], "primary_color": color}


_LOGO_ACCENT = {}


def _logo_accent(path):
    """Most saturated dominant colour of the logo (cached per object path); None if it can't be read."""
    if path in _LOGO_ACCENT:
        return _LOGO_ACCENT[path]
    import colorsys
    import io as _bio
    from PIL import Image
    color = None
    try:
        data, _ = _get_object(path)
        im = Image.open(_bio.BytesIO(data)).convert("RGB").resize((64, 64))
        best = 0
        for count, (r, g, b_) in im.getcolors(64 * 64) or []:
            h, l, sat = colorsys.rgb_to_hls(r / 255, g / 255, b_ / 255)
            if 0.2 < l < 0.6 and sat > 0.35 and count * sat > best:
                best, color = count * sat, "#%02x%02x%02x" % (r, g, b_)
    except Exception:
        color = None
    _LOGO_ACCENT[path] = color
    return color


async def _attendance_calendar(iid, student, month):
    import re as _re
    if not _re.fullmatch(r"\d{4}-\d{2}", month or ""):
        raise HTTPException(status_code=400, detail="month must be YYYY-MM")
    sid = student["id"]
    q = {"institution_id": iid, "class_name": student.get("class_name"), "section": student.get("section")}
    yr = await db.academic_years.find_one({"institution_id": iid, "status": "active"}, {"_id": 0, "start_date": 1, "end_date": 1}) or {}
    days, y_present, y_total = [], 0, 0
    async for sh in db.attendance.find(q, {"_id": 0, "date": 1, "entries": 1}):
        st = (sh.get("entries") or {}).get(sid)
        d = sh.get("date") or ""
        if st is None:
            continue
        st = str(st).lower()
        st = {"p": "present", "a": "absent", "l": "late"}.get(st, st)
        if (not yr.get("start_date") or d >= yr["start_date"]) and (not yr.get("end_date") or d <= yr["end_date"]):
            y_total += 1
            y_present += st == "present"  # same rule as /portal/me
        if d.startswith(month):
            days.append({"date": d, "status": st})
    days.sort(key=lambda x: x["date"])
    m_total = len(days)
    m_present = sum(1 for x in days if x["status"] == "present")
    cls = await db.classes.find_one({"institution_id": iid, "name": student.get("class_name")}, {"_id": 0, "academic_unit_id": 1}) or {}
    cfg = await effective_tt_config(iid, await _active_year_name(iid), cls.get("academic_unit_id"))
    return {"month": month, "days": days, "working_days": cfg.get("working_days") or [],
            "month_pct": round(m_present / m_total * 100) if m_total else None, "month_present": m_present, "month_total": m_total,
            "year_pct": round(y_present / y_total * 100) if y_total else None, "year_present": y_present, "year_total": y_total}


@api.get("/portal/attendance-calendar")
async def portal_attendance_calendar(month: str, user: dict = Depends(require_roles("student"))):
    iid = user["institution_id"]
    st = await db.students.find_one({"id": user.get("student_id"), "institution_id": iid}, {"_id": 0, "id": 1, "class_name": 1, "section": 1})
    if not st:
        raise HTTPException(status_code=404, detail="No student profile")
    return await _attendance_calendar(iid, st, month)


@api.get("/parent/child/{student_id}/attendance-calendar")
async def parent_attendance_calendar(student_id: str, month: str, user: dict = Depends(require_roles("parent"))):
    iid = user["institution_id"]
    if student_id not in (user.get("student_ids") or []):
        raise HTTPException(status_code=403, detail="This student is not linked to your account")
    st = await db.students.find_one({"id": student_id, "institution_id": iid}, {"_id": 0, "id": 1, "class_name": 1, "section": 1})
    if not st:
        raise HTTPException(status_code=404, detail="Student not found")
    return await _attendance_calendar(iid, st, month)


# ================= Phase 28 — NOTICES MODULE (communication-connected) =================
# Notices gain: target audience {scope: school|divisions|classes, division_ids[], classes[{class_name,section}]},
# attachments[] (object storage, authenticated read), bell fan-out on publish (respecting audience),
# and "send to parents" (WhatsApp media / SMS secure link). Senders: admin, scoped principals,
# and teachers for their OWN assigned classes only.

NOTICE_MAX_FILES = 3


def _notice_public(n):
    atts = [{"name": a.get("name"), "type": a.get("type"), "size": a.get("size")} for a in (n.get("attachments") or [])]
    return {"id": n["id"], "title": n.get("title"), "body": n.get("body"), "status": n.get("status"),
            "author_name": n.get("author_name"), "author_id": n.get("author_id"),
            "created_at": n.get("created_at"), "target": n.get("target") or {"scope": "school"},
            "audience": n.get("audience"), "attachments": atts, "attachment_count": len(atts)}


async def _class_name_to_unit(iid, class_name):
    c = await db.classes.find_one({"institution_id": iid, "name": class_name}, {"_id": 0, "academic_unit_id": 1})
    return (c or {}).get("academic_unit_id")


async def _notice_matches_student(iid, n, class_name, section):
    t = n.get("target")
    if not t:  # legacy notices: string audience, treated as school-wide for students
        return n.get("audience") in (None, "all", "students")
    scope = t.get("scope", "school")
    if scope == "school":
        return True
    if scope == "divisions":
        return (await _class_name_to_unit(iid, class_name)) in (t.get("division_ids") or [])
    if scope == "classes":
        for c in (t.get("classes") or []):
            if c.get("class_name") == class_name and (not c.get("section") or c.get("section") == section):
                return True
    return False


async def _teacher_allowed_classsections(iid, user):
    """(class_names set, (class,section) set) a teacher may address — from their assignments."""
    assigns = await db.teacher_assignments.find({"institution_id": iid, **_teacher_match(user)}, {"_id": 0}).to_list(500)
    cn_set, cs_set = set(), set()
    for a in assigns:
        cn = a.get("class_name")
        if not cn:
            continue
        cn_set.add(cn)
        if a.get("section"):
            cs_set.add((cn, a["section"]))
        else:
            for s in await db.sections.find({"institution_id": iid, "class_name": cn}, {"_id": 0, "name": 1}).to_list(50):
                cs_set.add((cn, s["name"]))
    return cn_set, cs_set


async def _notice_student_query(iid, n):
    """Mongo filter selecting ENROLLED students in a notice's audience."""
    q = {"institution_id": iid, "enrollment_status": "enrolled"}
    t = n.get("target")
    if not t or t.get("scope") == "school":
        return q
    scope = t.get("scope")
    if scope == "divisions":
        names = [c["name"] for c in await db.classes.find(
            {"institution_id": iid, "academic_unit_id": {"$in": t.get("division_ids") or []}}, {"_id": 0, "name": 1}).to_list(5000)]
        q["class_name"] = {"$in": names or ["__none__"]}
    elif scope == "classes":
        ors = []
        for c in (t.get("classes") or []):
            cond = {"class_name": c.get("class_name")}
            if c.get("section"):
                cond["section"] = c["section"]
            ors.append(cond)
        q["$or"] = ors or [{"class_name": "__none__"}]
    return q


async def _notice_fanout(iid, n):
    """Bell notifications to students + linked parents in the notice's audience."""
    students = await db.students.find(await _notice_student_query(iid, n), {"_id": 0, "id": 1}).to_list(20000)
    sids = [s["id"] for s in students]
    title = f"New notice: {n['title']}"
    body = (n.get("body") or "")[:120]
    users = await db.users.find({"institution_id": iid, "role": "student", "student_id": {"$in": sids}},
                                {"_id": 0, "id": 1}).to_list(20000)
    for su in users:
        await _notify(iid, su["id"], "notice_new", title, body, n["id"])
    for sid in sids:
        for pid in await _student_parent_ids(iid, sid):
            await _notify(iid, pid, "notice_new", title, body, n["id"])
    return len(sids)


async def _validate_notice_target(iid, user, target: dict):
    """Enforce sender scope. Returns a normalized target dict. Raises 403 on out-of-scope."""
    scope = (target or {}).get("scope") or "school"
    div = list((target or {}).get("division_ids") or [])
    classes = [{"class_name": c.get("class_name"), "section": (c.get("section") or None)}
               for c in ((target or {}).get("classes") or []) if c.get("class_name")]
    is_admin = user.get("role") == "institution_admin"
    pa = await active_principal(user)
    if is_admin:
        return {"scope": scope, "division_ids": div, "classes": classes}
    if pa:  # principal (teacher with elevation)
        sc = await principal_scope(user)
        if sc and not sc.get("whole_school"):
            allowed_names = set(sc.get("class_names") or [])
            allowed_units = set(sc.get("unit_ids") or [])
            if scope == "school":
                raise HTTPException(status_code=403, detail="Scope a notice to your divisions or classes")
            if scope == "divisions" and set(div) - allowed_units:
                raise HTTPException(status_code=403, detail="Some divisions are outside your scope")
            if scope == "classes":
                bad = [c["class_name"] for c in classes if c["class_name"] not in allowed_names]
                if bad:
                    raise HTTPException(status_code=403, detail=f"Out of scope: {', '.join(sorted(set(bad)))}")
        return {"scope": scope, "division_ids": div, "classes": classes}
    # plain teacher → only their own classes
    cn_set, cs_set = await _teacher_allowed_classsections(iid, user)
    if scope != "classes" or not classes:
        raise HTTPException(status_code=403, detail="Teachers can post notices only to their assigned classes")
    for c in classes:
        ok = (c["class_name"], c["section"]) in cs_set if c["section"] else (c["class_name"] in cn_set)
        if not ok:
            raise HTTPException(status_code=403, detail=f"You don't teach {c['class_name']}{(' ' + c['section']) if c['section'] else ''}")
    return {"scope": "classes", "division_ids": [], "classes": classes}


class NoticeCreate(BaseModel):
    title: str
    body: Optional[str] = ""
    target: Optional[dict] = None
    status: str = "published"


@api.get("/notices/feed")
async def notices_feed(user: dict = Depends(require_roles("institution_admin", "teacher", "student", "parent"))):
    iid = user["institution_id"]
    role = user["role"]
    rows = await db.notices.find({"institution_id": iid, "status": "published"},
                                 {"_id": 0}).sort("created_at", -1).to_list(100)
    out = []
    if role in ("student", "parent"):
        if role == "student":
            st = await db.students.find_one({"id": user.get("student_id"), "institution_id": iid}, {"_id": 0, "class_name": 1, "section": 1})
            kids = [st] if st else []
        else:
            kids = await db.students.find({"institution_id": iid, "id": {"$in": user.get("student_ids") or []}},
                                          {"_id": 0, "class_name": 1, "section": 1}).to_list(50)
        for n in rows:
            for k in kids:
                if await _notice_matches_student(iid, n, k.get("class_name"), k.get("section")):
                    out.append(_notice_public(n))
                    break
    elif role == "teacher":
        cn_set, _ = await _teacher_allowed_classsections(iid, user)
        pa = await active_principal(user)
        for n in rows:
            t = n.get("target")
            if not t:
                if n.get("audience") in ("all", "teachers", None):
                    out.append(_notice_public(n))
            elif pa or t.get("scope") == "school" or n.get("author_id") == user["id"] \
                    or any(c.get("class_name") in cn_set for c in (t.get("classes") or [])):
                out.append(_notice_public(n))
    else:  # admin
        out = [_notice_public(n) for n in rows]
    return {"notices": out[:30]}


@api.get("/notices")
async def list_notices(user: dict = Depends(require_roles("institution_admin", "teacher"))):
    """Management list: admin → all; principal → scoped; plain teacher → own."""
    iid = user["institution_id"]
    q = {"institution_id": iid}
    if user["role"] == "teacher":
        pa = await active_principal(user)
        if not pa:
            q["author_id"] = user["id"]
        else:
            sc = await principal_scope(user)
            if sc and not sc.get("whole_school"):
                names = sc.get("class_names") or []
                q["$or"] = [{"target.scope": "school"}, {"author_id": user["id"]},
                            {"target.classes.class_name": {"$in": names}}]
    rows = await db.notices.find(q, {"_id": 0}).sort("created_at", -1).to_list(200)
    return {"notices": [_notice_public(n) for n in rows]}


@api.post("/notices")
async def create_notice(body: NoticeCreate, user: dict = Depends(require_roles("institution_admin", "teacher"))):
    iid = user["institution_id"]
    if not body.title.strip():
        raise HTTPException(status_code=400, detail="Notice title is required")
    target = await _validate_notice_target(iid, user, body.target or {"scope": "school"})
    status = body.status if body.status in ("published", "draft") else "published"
    n = {"id": str(uuid.uuid4()), "institution_id": iid, "title": body.title.strip(),
         "body": (body.body or "").strip(), "target": target, "status": status,
         "attachments": [], "author_id": user["id"], "author_name": user.get("name"),
         "created_at": now_iso()}
    await db.notices.insert_one(dict(n))
    await audit(user, "create_notice", "notices", n["id"], n["title"])
    reached = await _notice_fanout(iid, n) if status == "published" else 0
    return {"notice": _notice_public(n), "notified_students": reached}


async def _get_manageable_notice(iid, notice_id, user):
    n = await db.notices.find_one({"id": notice_id, "institution_id": iid}, {"_id": 0})
    if not n:
        raise HTTPException(status_code=404, detail="Notice not found")
    if user["role"] == "institution_admin":
        return n
    if user["role"] == "teacher":
        if n.get("author_id") == user["id"]:
            return n
        if await active_principal(user):
            await _validate_notice_target(iid, user, n.get("target") or {"scope": "school"})
            return n
    raise HTTPException(status_code=403, detail="You can only manage your own notices")


@api.post("/notices/{notice_id}/attachments")
async def add_notice_attachments(notice_id: str, files: List[UploadFile] = File(...),
                                 user: dict = Depends(require_roles("institution_admin", "teacher"))):
    iid = user["institution_id"]
    n = await _get_manageable_notice(iid, notice_id, user)
    existing = n.get("attachments") or []
    if len(existing) + len(files) > NOTICE_MAX_FILES:
        raise HTTPException(status_code=400, detail=f"A notice can have at most {NOTICE_MAX_FILES} attachments")
    for f in files:
        if f.content_type not in HW_ATTACH_TYPES or HW_ATTACH_TYPES[f.content_type] in ("doc", "docx"):
            raise HTTPException(status_code=400, detail="Allowed: PDF or images (JPG/PNG/WebP)")
    added = await _store_hw_files(files, f"{notice_id}", base="notices")
    await db.notices.update_one({"id": notice_id}, {"$set": {"attachments": existing + added}})
    return {"attachments": [{"name": a["name"], "type": a["type"], "size": a["size"]} for a in existing + added]}


@api.get("/notices/attachment/{notice_id}/{idx}")
async def download_notice_attachment(notice_id: str, idx: int, user: dict = Depends(get_current_user)):
    iid = user["institution_id"]
    n = await db.notices.find_one({"id": notice_id, "institution_id": iid}, {"_id": 0})
    atts = (n or {}).get("attachments") or []
    if not n or idx < 0 or idx >= len(atts):
        raise HTTPException(status_code=404, detail="Attachment not found")
    role = user["role"]
    allowed = role == "institution_admin"
    if role == "teacher":
        allowed = n.get("author_id") == user["id"] or bool(await active_principal(user))
    elif role == "student":
        st = await db.students.find_one({"id": user.get("student_id"), "institution_id": iid}, {"_id": 0, "class_name": 1, "section": 1})
        allowed = bool(st) and await _notice_matches_student(iid, n, st.get("class_name"), st.get("section"))
    elif role == "parent":
        for k in await db.students.find({"institution_id": iid, "id": {"$in": user.get("student_ids") or []}}, {"_id": 0, "class_name": 1, "section": 1}).to_list(50):
            if await _notice_matches_student(iid, n, k.get("class_name"), k.get("section")):
                allowed = True
                break
    if not allowed:
        raise HTTPException(status_code=403, detail="Not allowed")
    data, ctype = _get_object(atts[idx]["path"])
    return Response(content=data, media_type=atts[idx].get("type") or ctype,
                    headers={"Content-Disposition": f'inline; filename="{atts[idx].get("name") or "attachment"}"'})


@api.delete("/notices/{notice_id}")
async def delete_notice(notice_id: str, user: dict = Depends(require_roles("institution_admin", "teacher"))):
    iid = user["institution_id"]
    n = await _get_manageable_notice(iid, notice_id, user)
    await db.notices.delete_one({"id": notice_id})
    await audit(user, "delete_notice", "notices", notice_id, n.get("title"))
    return {"ok": True}


class NoticeSendBody(BaseModel):
    channel: str = "whatsapp"
    dry_run: bool = False


@api.post("/notices/{notice_id}/send")
async def send_notice_as_message(notice_id: str, body: NoticeSendBody,
                                 user: dict = Depends(require_roles("institution_admin", "teacher"))):
    """Send the notice to parents: WhatsApp → attachment as media; SMS → secure link in text.
    Audience = the notice's target; sender scope enforced via _get_manageable_notice."""
    iid = user["institution_id"]
    channel = body.channel
    if channel not in COMM_CHANNELS:
        raise HTTPException(status_code=400, detail="channel must be 'whatsapp' or 'sms'")
    n = await _get_manageable_notice(iid, notice_id, user)
    school_name, comm = await _institution_comm(iid)
    # recipients = guardians of enrolled students in the notice audience
    students = await db.students.find(await _notice_student_query(iid, n), {"_id": 0}).to_list(20000)
    recipients, skipped = [], []
    link = None
    atts = n.get("attachments") or []
    if atts:
        link = _secure_link_url(iid, f"notice:{notice_id}", path=atts[0]["path"], ct=atts[0].get("type"))
    tpl = await db.comm_templates.find_one({"institution_id": None, "name": "Announcement"}, {"_id": 0})
    for s in students:
        sname = f"{s.get('first_name','')} {s.get('last_name','')}".strip()
        cls = s.get("class_name") + (f" {s.get('section')}" if s.get("section") else "")
        phone = str(s.get("guardian_phone") or "").strip()
        if not phone:
            skipped.append({"student_id": s.get("id"), "student_name": sname, "class": cls})
            continue
        vals = {"school_name": school_name or "", "student_name": sname,
                "parent_name": s.get("guardian_name") or "Parent", "class": cls}
        if channel == "whatsapp":
            rbody = _render_template(tpl["body"], vals) if tpl else f"{school_name}: {n['title']}"
        else:
            rbody = f"{school_name}: {n['title']}" + (f" — {link}" if link else "")
        recipients.append({"name": vals["parent_name"], "phone": phone, "student_id": s.get("id"),
                           "body": rbody, "vars": vals, "meta": {"student_name": sname, "class": cls, "notice_id": notice_id}})
    quota = comm["quota"][channel]
    remaining = max(0, quota["limit"] - quota["used"])
    if body.dry_run:
        return {"dry_run": True, "recipient_count": len(recipients), "skipped_count": len(skipped),
                "skipped": skipped[:50], "quota_remaining": remaining,
                "quota_after": max(0, remaining - len(recipients)),
                "has_attachment": bool(link), "channel": channel, "would_block": len(recipients) > remaining}
    if not recipients:
        return {"ok": False, "code": "no_recipients", "sent": 0, "skipped_count": len(skipped),
                "message": "No recipients with a guardian phone in this notice's audience"}
    if len(recipients) > remaining:
        raise HTTPException(status_code=400, detail=f"Insufficient {channel.upper()} quota: need {len(recipients)}, {remaining} remaining")
    media = link if (channel == "whatsapp" and link) else None
    result = await send_message(iid, channel, recipients,
                                template_id=(tpl["id"] if (channel == "whatsapp" and tpl) else None),
                                module="notice", media_url=media,
                                meta={"notice_id": notice_id}, actor=user)
    result["skipped_count"] = len(skipped)
    result["skipped"] = skipped[:50]
    result["has_attachment"] = bool(link)
    return result


GRADE_BANDS = [(90, "A+"), (80, "A"), (70, "B+"), (60, "B"), (50, "C"), (35, "D")]


def _grade(pct):
    for cut, g in GRADE_BANDS:
        if pct >= cut:
            return g
    return "F"


async def _vault_data_uri(path):
    """Fetch vault bytes SERVER-SIDE and return a base64 data-URI. None if absent/unreadable.
    Vault paths (lnmo/signatures, lnmo/seals) are NEVER returned to the client — only the bytes."""
    if not path:
        return None
    try:
        data, ctype = _get_object(path)
        return f"data:{ctype};base64,{base64.b64encode(data).decode()}"
    except Exception:  # noqa: BLE001
        logger.warning("Vault read failed during report-card composition")
        return None


async def _report_card_signers(student, iid):
    """Resolve the report-card signature row. Class teacher = section.class_teacher_id
    (fallback: any assigned teacher of the class). Principal precedence: whole-school > division
    (the class's academic unit) > none (blank line). Signature/seal embedded as base64 data-URIs."""
    cn = student.get("class_name")
    sec_name = student.get("section") or ""
    section = await db.sections.find_one(
        {"institution_id": iid, "class_name": cn, "name": sec_name}, {"_id": 0})
    ct_user, ct_fallback = None, False
    if section and section.get("class_teacher_id"):
        ct_user = await db.users.find_one({"id": section["class_teacher_id"]})
    if not ct_user:
        ta = await db.teacher_assignments.find_one({"institution_id": iid, "class_name": cn})
        if ta:
            ct_fallback = True
            ct_user = await db.users.find_one(
                {"institution_id": iid, "$or": [{"id": ta.get("teacher_id")}, {"email": ta.get("teacher_email")}]})
    class_teacher = {
        "name": (ct_user.get("name") if ct_user else None) or (section.get("class_teacher") if section else None),
        "signature": await _vault_data_uri(ct_user.get("signature_path")) if ct_user else None,
        "fallback": ct_fallback,
    }
    cls = await db.classes.find_one({"institution_id": iid, "name": cn}, {"_id": 0, "academic_unit_id": 1})
    unit_id = cls.get("academic_unit_id") if cls else None
    pa = await db.principal_assignments.find_one({"institution_id": iid, "scope_type": "whole_school"})
    precedence = "whole_school"
    if not pa:
        pa = await db.principal_assignments.find_one(
            {"institution_id": iid, "scope_type": "units", "unit_ids": unit_id}) if unit_id else None
        precedence = "division" if pa else "none"
    p_user = await db.users.find_one({"id": pa["user_id"]}) if pa else None
    principal = {
        "name": p_user.get("name") if p_user else None,
        "signature": await _vault_data_uri(p_user.get("signature_path")) if p_user else None,
        "title": (pa.get("designation") or "Principal").title() if pa else "Principal",
        "precedence": precedence,
    }
    inst = await db.institutions.find_one({"id": iid}, {"_id": 0, "seal_path": 1})
    seal = await _vault_data_uri(inst.get("seal_path")) if inst else None
    return {"class_teacher": class_teacher, "principal": principal, "seal": seal}


@api.get("/students/{student_id}/report-card")
async def student_report_card(student_id: str, user: dict = Depends(get_current_user)):
    iid = user["institution_id"]
    student = await db.students.find_one({"id": student_id, "institution_id": iid}, {"_id": 0, "password_hash": 0})
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    role = user["role"]
    if role == "student":
        if user.get("student_id") != student_id:
            raise HTTPException(status_code=403, detail="You can only view your own report card")
    elif role == "parent":
        if student_id not in (user.get("student_ids") or []):
            raise HTTPException(status_code=403, detail="This child is not linked to your account")
    elif role == "institution_admin":
        pass
    elif role == "teacher":
        await ensure_class_access(user, student.get("class_name"), student.get("section") or "")
    else:
        raise HTTPException(status_code=403, detail="Access denied")
    return await _report_card_data(student, iid)


async def _report_card_data(student, iid):
    student_id = student["id"]
    subjects = {}
    async for m in db.marks.find({"student_id": student_id}):
        a = await db.assessments.find_one({"id": m["assessment_id"], "institution_id": iid}, {"_id": 0})
        if not a or a.get("status") != "published":
            continue
        subj = a.get("subject") or "General"
        score = _to_num(m.get("score"), 0)
        max_marks = _to_num(a.get("max_marks"), 0)
        entry = subjects.setdefault(subj, {"subject": subj, "assessments": [], "total_score": 0, "total_max": 0})
        entry["assessments"].append({"name": a.get("name"), "score": score, "max_marks": max_marks})
        entry["total_score"] += score
        entry["total_max"] += max_marks
    rows = []
    for s in sorted(subjects.values(), key=lambda x: x["subject"]):
        pct = round(s["total_score"] / s["total_max"] * 100, 1) if s["total_max"] else 0
        rows.append({**s, "pct": pct, "grade": _grade(pct)})
    total_score = sum(r["total_score"] for r in rows)
    total_max = sum(r["total_max"] for r in rows)
    overall_pct = round(total_score / total_max * 100, 1) if total_max else 0
    present, total = 0, 0
    async for sh in db.attendance.find({"institution_id": iid, "class_name": student.get("class_name"), "section": student.get("section")}):
        ent = sh.get("entries") or {}
        if student_id in ent:
            total += 1
            if str(ent[student_id]).lower() in ("present", "p"):
                present += 1
    inst = await db.institutions.find_one({"id": iid}, {"_id": 0, "name": 1, "portal_name": 1, "primary_color": 1, "logo_url": 1, "logo_path": 1, "domain": 1}) or {}
    return {"student": student, "academic_year": await _active_year_name(iid), "subjects": rows,
            "overall": {"total_score": total_score, "total_max": total_max, "pct": overall_pct,
                        "grade": _grade(overall_pct) if total_max else None},
            "attendance": {"present": present, "total": total,
                           "pct": round(present / total * 100) if total else None},
            "institution": {"name": inst.get("name"), "portal_name": inst.get("portal_name"),
                            "primary_color": inst.get("primary_color"), "logo_url": inst.get("logo_url"),
                            "has_logo": bool(inst.get("logo_path")), "domain": inst.get("domain")},
            "signers": await _report_card_signers(student, iid),
            "assignment_scores": await _assignment_report_scores(iid, student_id)}


# ---------------- Object storage (profile photos) ----------------

import requests as _rq

STORAGE_BASE = (os.environ.get("INTEGRATION_PROXY_URL") or "").strip() or "https://integrations.emergentagent.com"
STORAGE_URL = STORAGE_BASE.rstrip("/") + "/objstore/api/v1/storage"
_storage_key = None


def init_storage(force: bool = False):
    global _storage_key
    if _storage_key and not force:
        return _storage_key
    r = _rq.post(f"{STORAGE_URL}/init", json={"emergent_key": os.environ.get("EMERGENT_LLM_KEY")}, timeout=30)
    r.raise_for_status()
    _storage_key = r.json()["storage_key"]
    return _storage_key


def _put_object(path, data, content_type):
    r = _rq.put(f"{STORAGE_URL}/objects/{path}",
                headers={"X-Storage-Key": init_storage(), "Content-Type": content_type}, data=data, timeout=120)
    if r.status_code == 404:
        r = _rq.put(f"{STORAGE_URL}/objects/{path}",
                    headers={"X-Storage-Key": init_storage(force=True), "Content-Type": content_type}, data=data, timeout=120)
    r.raise_for_status()
    return r.json()


def _get_object(path):
    r = _rq.get(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": init_storage()}, timeout=60)
    if r.status_code == 404:
        r = _rq.get(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": init_storage(force=True)}, timeout=60)
    r.raise_for_status()
    return r.content, r.headers.get("Content-Type", "application/octet-stream")


def _delete_object(path):
    """Best-effort permanent delete of a stored object. Returns True if removed."""
    r = _rq.delete(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": init_storage()}, timeout=60)
    if r.status_code == 404:
        r = _rq.delete(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": init_storage(force=True)}, timeout=60)
    if r.status_code == 404:
        return False
    r.raise_for_status()
    return True


PHOTO_TYPES = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}


@api.post("/students/{student_id}/photo")
async def upload_student_photo(student_id: str, file: UploadFile = File(...),
                               user: dict = Depends(require_roles("institution_admin", "student"))):
    iid = user["institution_id"]
    if user["role"] == "student" and user.get("student_id") != student_id:
        raise HTTPException(status_code=403, detail="You can only update your own photo")
    student = await db.students.find_one({"id": student_id, "institution_id": iid})
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    if file.content_type not in PHOTO_TYPES:
        raise HTTPException(status_code=400, detail="Please upload a JPG, PNG or WebP image")
    data = await file.read()
    if len(data) > 4 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Image must be under 4 MB")
    path = f"lnmo/photos/{student_id}/{uuid.uuid4()}.{PHOTO_TYPES[file.content_type]}"
    try:
        result = _put_object(path, data, file.content_type)
    except Exception:
        raise HTTPException(status_code=502, detail="Photo storage is unavailable right now — try again shortly")
    await db.students.update_one({"id": student_id}, {"$set": {"photo_path": result["path"], "photo_type": file.content_type}})
    await audit(user, "upload_photo", "students", student_id, student.get("first_name"))
    return {"message": "Photo updated"}


@api.get("/students/{student_id}/photo")
async def get_student_photo(student_id: str,
                            user: dict = Depends(require_roles("institution_admin", "teacher", "student", "parent"))):
    iid = user["institution_id"]
    if user["role"] == "student" and user.get("student_id") != student_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    if user["role"] == "parent" and student_id not in (user.get("student_ids") or []):
        raise HTTPException(status_code=403, detail="Forbidden")
    student = await db.students.find_one({"id": student_id, "institution_id": iid})
    if not student or not student.get("photo_path"):
        raise HTTPException(status_code=404, detail="No photo")
    try:
        data, ctype = _get_object(student["photo_path"])
    except Exception:
        raise HTTPException(status_code=404, detail="No photo")
    return Response(content=data, media_type=student.get("photo_type") or ctype,
                    headers={"Cache-Control": "private, max-age=300"})


# ---------------- Institution logo (object storage; public read for login pages) ----------------

@api.post("/institution/logo")
async def upload_institution_logo(file: UploadFile = File(...),
                                  user: dict = Depends(require_roles("institution_admin"))):
    iid = user["institution_id"]
    if file.content_type not in PHOTO_TYPES:
        raise HTTPException(status_code=400, detail="Please upload a JPG, PNG or WebP image")
    data = await file.read()
    if len(data) > 4 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Logo must be under 4 MB")
    path = f"lnmo/logos/{iid}/{uuid.uuid4()}.{PHOTO_TYPES[file.content_type]}"
    try:
        result = _put_object(path, data, file.content_type)
    except Exception:
        raise HTTPException(status_code=502, detail="Logo storage is unavailable right now — try again shortly")
    await db.institutions.update_one({"id": iid}, {"$set": {"logo_path": result["path"], "logo_type": file.content_type}})
    await audit(user, "upload_logo", "institution_profile", iid, None)
    return {"message": "Logo updated", "has_logo": True}


@api.delete("/institution/logo")
async def delete_institution_logo(user: dict = Depends(require_roles("institution_admin"))):
    iid = user["institution_id"]
    await db.institutions.update_one({"id": iid}, {"$unset": {"logo_path": "", "logo_type": ""}})
    await audit(user, "delete_logo", "institution_profile", iid, None)
    return {"message": "Logo removed", "has_logo": False}


@api.get("/institution/brand-lite")
async def institution_brand_lite(user: dict = Depends(require_admin_or_principal)):
    """Lightweight branding for print headers — available to admin AND principals (unlike the
    admin-only profile endpoint)."""
    inst = await db.institutions.find_one({"id": user["institution_id"]},
                                          {"_id": 0, "name": 1, "portal_name": 1, "slug": 1,
                                           "logo_url": 1, "logo_path": 1}) or {}
    return {"name": inst.get("portal_name") or inst.get("name") or "School",
            "slug": inst.get("slug"), "logo_url": inst.get("logo_url"),
            "has_logo": bool(inst.get("logo_path"))}


@api.get("/institution/logo-status")
async def institution_logo_status(user: dict = Depends(require_roles("institution_admin"))):
    inst = await db.institutions.find_one({"id": user["institution_id"]}, {"_id": 0, "logo_path": 1, "domain": 1, "slug": 1})
    return {"has_logo": bool((inst or {}).get("logo_path")), "domain": (inst or {}).get("domain"), "slug": (inst or {}).get("slug")}


@api.get("/institution/logo")
async def get_own_institution_logo(user: dict = Depends(require_roles("institution_admin"))):
    inst = await db.institutions.find_one({"id": user["institution_id"]}, {"_id": 0, "logo_path": 1, "logo_type": 1})
    if not inst or not inst.get("logo_path"):
        raise HTTPException(status_code=404, detail="No logo")
    try:
        data, ctype = _get_object(inst["logo_path"])
    except Exception:
        raise HTTPException(status_code=404, detail="No logo")
    return Response(content=data, media_type=inst.get("logo_type") or ctype,
                    headers={"Cache-Control": "private, max-age=60"})


@api.get("/public/docs/LNMO_Product_Guide.pdf")
async def public_product_guide():
    """Unauthenticated download of the product guide ONLY (fixed path, no listing). Falls back to object storage."""
    f = ROOT_DIR.parent / "docs" / "LNMO_Product_Guide.pdf"
    if f.is_file():
        data = f.read_bytes()
    else:
        try:
            data, _ = _get_object("lnmo/docs/LNMO_Product_Guide.pdf")
        except Exception:
            raise HTTPException(status_code=404, detail="Not found")
    return Response(content=data, media_type="application/pdf",
                    headers={"Content-Disposition": 'inline; filename="LNMO_Product_Guide.pdf"', "Cache-Control": "public, max-age=600"})


@api.get("/public/institution-logo")
async def public_institution_logo(domain: str = "", slug: str = ""):
    q = None
    if slug.strip():
        q = {"slug": slug.strip().lower()}
    elif domain.strip():
        q = {"domain": domain.strip().lstrip("@").lower()}
    if not q:
        raise HTTPException(status_code=404, detail="Not found")
    inst = await db.institutions.find_one(q, {"_id": 0, "logo_path": 1, "logo_type": 1})
    if not inst or not inst.get("logo_path"):
        raise HTTPException(status_code=404, detail="No logo")
    try:
        data, ctype = _get_object(inst["logo_path"])
    except Exception:
        raise HTTPException(status_code=404, detail="No logo")
    return Response(content=data, media_type=inst.get("logo_type") or ctype,
                    headers={"Cache-Control": "public, max-age=600"})


# ---------------- Phase 53: branded school login page (public: name, logo, tagline, background only) ----------------

LOGIN_BG_MAX = 5 * 1024 * 1024
LOGIN_DEFAULT_BG = ROOT_DIR / "static" / "login-default.jpg"


class LoginPageIn(BaseModel):
    tagline: str = PField(default="", max_length=80)


def _login_bg_compress(data: bytes) -> bytes:
    from PIL import Image, ImageOps
    import io as _bio
    try:
        im = Image.open(_bio.BytesIO(data))
        im = ImageOps.exif_transpose(im).convert("RGB")
    except Exception:
        raise HTTPException(status_code=400, detail="That file isn't a readable image")
    if im.width > 1920:
        im = im.resize((1920, round(im.height * 1920 / im.width)), Image.LANCZOS)
    out = _bio.BytesIO()
    im.save(out, "JPEG", quality=82, optimize=True, progressive=True)
    return out.getvalue()


def _login_branding(inst):
    from urllib.parse import quote
    slug = inst.get("slug") or (inst.get("code") or "").lower() or (inst.get("domain") or "")
    logo_q = f"slug={quote(inst['slug'])}" if inst.get("slug") else f"domain={quote(inst.get('domain') or '')}"
    logo = f"/api/public/institution-logo?{logo_q}" if inst.get("logo_path") else (inst.get("logo_url") or None)
    bg = (f"/api/public/institutions/{quote(slug)}/login-background?v={inst.get('login_bg_version') or 1}"
          if inst.get("login_bg_path") else "/api/public/login-default.jpg")
    return {"name": inst.get("portal_name") or inst.get("name"), "logo_url": logo,
            "tagline": inst.get("login_tagline") or "", "background_url": bg}


async def _inst_by_code(code):
    c = (code or "").strip()
    if not c:
        return None
    return await db.institutions.find_one({"$or": [{"slug": c.lower()}, {"code": c.upper()}, {"domain": c.lower()}]},
                                          {"_id": 0, "id": 1, "name": 1, "portal_name": 1, "slug": 1, "logo_path": 1, "logo_url": 1,
                                           "login_tagline": 1, "login_bg_path": 1, "login_bg_version": 1, "login_bg_type": 1, "domain": 1, "code": 1})


@api.get("/public/institutions/branding")
async def public_institution_branding_lookup(domain: str = "", code: str = ""):
    """Same minimal fields as /{code}/branding, resolved by ?domain= (login?domain=lpgs.com) or ?code=."""
    inst = await _inst_by_code(code or domain)
    if not inst:
        raise HTTPException(status_code=404, detail="Not found")
    return _login_branding(inst)


@api.get("/public/institutions/{code}/branding")
async def public_institution_branding(code: str):
    inst = await _inst_by_code(code)
    if not inst:
        raise HTTPException(status_code=404, detail="Not found")
    return _login_branding(inst)


@api.get("/public/institutions/{code}/login-background")
async def public_login_background(code: str):
    inst = await _inst_by_code(code)
    if not inst or not inst.get("login_bg_path"):
        raise HTTPException(status_code=404, detail="Not found")
    try:
        data, _ = _get_object(inst["login_bg_path"])
    except Exception:
        raise HTTPException(status_code=404, detail="Not found")
    return Response(content=data, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=86400"})


@api.get("/public/login-default.jpg")
async def public_login_default_bg():
    return Response(content=LOGIN_DEFAULT_BG.read_bytes(), media_type="image/jpeg",
                    headers={"Cache-Control": "public, max-age=86400"})


BRAND_DIR = ROOT_DIR / "static" / "brand"
BRAND_ASSETS = {p.name for p in BRAND_DIR.iterdir()} if BRAND_DIR.exists() else set()
BRAND_TYPES = {"image/png", "image/jpeg", "image/webp", "image/svg+xml"}
BRAND_MAX = 10 * 1024 * 1024
_brand_cache: dict = {}


def _brand_media(name: str) -> str:
    return {"svg": "image/svg+xml", "ico": "image/x-icon"}.get(name.rsplit(".", 1)[-1], "image/png")


async def _platform_branding():
    return await db.platform_settings.find_one({"id": "branding"}, {"_id": 0}) or {}


@api.get("/public/platform-brand/{name}")
async def public_platform_brand(name: str):
    """Current LNMO platform logo/icon asset (uploaded version, else the bundled default)."""
    if name not in BRAND_ASSETS:
        raise HTTPException(status_code=404, detail="Not found")
    s = await _platform_branding()
    path = (s.get("assets") or {}).get(name)
    data = None
    if path:
        key = (s.get("version"), name)
        data = _brand_cache.get(key)
        if data is None:
            try:
                data, _ = _get_object(path)
                _brand_cache[key] = data
            except Exception:
                data = None
    if data is None:
        data = (BRAND_DIR / name).read_bytes()
    return Response(content=data, media_type=_brand_media(name), headers={"Cache-Control": "public, max-age=300"})


def _branding_out(s: dict):
    v = s.get("version") or 0
    return {"version": v, "uploaded": bool(s.get("assets")), "updated_at": s.get("updated_at"),
            "updated_by": s.get("updated_by"), "original_name": s.get("original_name"),
            "assets": {n: f"/api/public/platform-brand/{n}?v={v}" for n in sorted(BRAND_ASSETS)}}


@api.get("/platform/branding")
async def get_platform_branding(user: dict = Depends(require_roles("platform_admin"))):
    return _branding_out(await _platform_branding())


@api.post("/platform/branding/logo")
async def upload_platform_logo(file: UploadFile = File(...), user: dict = Depends(require_roles("platform_admin"))):
    """Upload the LNMO logo; raster uploads are cleaned (transparent, trimmed) and the full icon set regenerated."""
    if file.content_type not in BRAND_TYPES:
        raise HTTPException(status_code=400, detail="Please upload a PNG, JPG, WebP or SVG image")
    data = await file.read(BRAND_MAX + 1)
    if len(data) > BRAND_MAX:
        raise HTTPException(status_code=400, detail="Logo must be 10 MB or smaller")
    ver = ((await _platform_branding()).get("version") or 0) + 1
    if file.content_type == "image/svg+xml":
        if b"<svg" not in data[:2048] or b"<script" in data.lower():
            raise HTTPException(status_code=400, detail="That SVG file can't be used")
        outputs = {"lnmo-mark.svg": data}
    else:
        from logo_processing import process_logo
        try:
            outputs = await asyncio.to_thread(process_logo, data)
        except Exception as e:
            logger.warning("platform logo processing failed: %s", e)
            raise HTTPException(status_code=400, detail="Couldn't process that image — try a PNG with the logo on a plain white background")
    try:
        ext = (file.filename or "logo.png").rsplit(".", 1)[-1].lower()[:5]
        _put_object(f"lnmo/platform-brand/v{ver}/original.{ext}", data, file.content_type)
        assets = {n: _put_object(f"lnmo/platform-brand/v{ver}/{n}", b, _brand_media(n))["path"] for n, b in outputs.items()}
    except Exception:
        raise HTTPException(status_code=502, detail="Logo storage is unavailable right now — try again shortly")
    prev = (await _platform_branding()).get("assets") or {}
    keep = {} if file.content_type != "image/svg+xml" else {k: v for k, v in prev.items() if k != "lnmo-mark.svg"}
    await db.platform_settings.update_one({"id": "branding"}, {"$set": {
        "id": "branding", "version": ver, "assets": {**keep, **assets}, "original_name": file.filename,
        "updated_at": now_iso(), "updated_by": user.get("email")}}, upsert=True)
    await audit(user, "platform_logo_upload", "platform_branding", "branding", f"v{ver} · {file.filename}")
    return _branding_out(await _platform_branding())


@api.delete("/platform/branding/logo")
async def reset_platform_logo(user: dict = Depends(require_roles("platform_admin"))):
    s = await _platform_branding()
    await db.platform_settings.update_one({"id": "branding"}, {"$set": {"id": "branding", "assets": {}, "version": (s.get("version") or 0) + 1,
                                                                        "updated_at": now_iso(), "updated_by": user.get("email")}}, upsert=True)
    await audit(user, "platform_logo_reset", "platform_branding", "branding", "default")
    return _branding_out(await _platform_branding())


@api.get("/institution/login-page")
async def get_login_page(user: dict = Depends(require_roles("institution_admin"))):
    inst = await db.institutions.find_one({"id": user["institution_id"]}, {"_id": 0}) or {}
    return {**_login_branding(inst), "slug": inst.get("slug") or (inst.get("code") or "").lower() or inst.get("domain"), "has_background": bool(inst.get("login_bg_path"))}


@api.put("/institution/login-page")
async def update_login_page(body: LoginPageIn, user: dict = Depends(require_roles("institution_admin"))):
    iid = user["institution_id"]
    tagline = body.tagline.strip()
    await db.institutions.update_one({"id": iid}, {"$set": {"login_tagline": tagline}})
    await audit(user, "login_page_tagline", "institution_profile", iid, tagline or "(cleared)")
    return await get_login_page(user)


@api.post("/institution/login-page/background")
async def upload_login_background(file: UploadFile = File(...), user: dict = Depends(require_roles("institution_admin"))):
    iid = user["institution_id"]
    if file.content_type not in PHOTO_TYPES:
        raise HTTPException(status_code=400, detail="Please upload a JPG, PNG or WebP image")
    data = await file.read(LOGIN_BG_MAX + 1)
    if len(data) > LOGIN_BG_MAX:
        raise HTTPException(status_code=400, detail="Background photo must be 5 MB or smaller")
    jpg = _login_bg_compress(data)
    path = f"lnmo/login-bg/{iid}/{uuid.uuid4()}.jpg"
    try:
        result = _put_object(path, jpg, "image/jpeg")
    except Exception:
        raise HTTPException(status_code=502, detail="Photo storage is unavailable right now — try again shortly")
    await db.institutions.update_one({"id": iid}, {"$set": {"login_bg_path": result["path"], "login_bg_type": "image/jpeg"},
                                                   "$inc": {"login_bg_version": 1}})
    await audit(user, "login_page_background_upload", "institution_profile", iid, f"{len(data)}→{len(jpg)} bytes")
    return await get_login_page(user)


@api.delete("/institution/login-page/background")
async def reset_login_background(user: dict = Depends(require_roles("institution_admin"))):
    iid = user["institution_id"]
    await db.institutions.update_one({"id": iid}, {"$unset": {"login_bg_path": "", "login_bg_type": ""}, "$inc": {"login_bg_version": 1}})
    await audit(user, "login_page_background_reset", "institution_profile", iid, "default background")
    return await get_login_page(user)


# ================= Phase 15 — PROFILES: photos + signature/seal SECURE VAULT =================
# Two access tiers over the existing object storage:
#   • Photos tier  → lnmo/photos/users/...  (authenticated-read; teacher photos are the public-ish face)
#   • VAULT tier   → lnmo/signatures/{user_id}/... and lnmo/seals/{institution_id}/...
#     NEVER exposed via any public URL. GET restricted to owner + admin + in-scope principal.
#     Phase 17 document generation fetches vault bytes SERVER-SIDE only (via _get_object).

# --- Pluggable verification-provider interface (Phase 16 will implement; NO OTP is built now) ---
class VerificationProvider:
    """Interface for OTP delivery. Phase 16 wires concrete providers (email/SMS). Design-only here."""
    channel = "none"

    async def send_code(self, destination: str, code: str, context: dict | None = None):
        raise NotImplementedError("OTP delivery is introduced in Phase 16")


# Registry with provider slots reserved now so Phase 16 only has to implement send_code().
VERIFICATION_PROVIDERS: dict = {
    "email": None,  # Phase 16 → Resend (Emergent-managed)
    "sms": None,    # future → Twilio (SMS-ready slot)
}


async def _teacher_in_scope(scope, target: dict) -> bool:
    """True if a principal's scope covers the target teacher (teaches / is class teacher of an in-scope class)."""
    if not scope:
        return False
    if scope["whole_school"]:
        return True
    cns = scope["class_names"] or []
    if not cns:
        return False
    iid = target.get("institution_id")
    if await db.teacher_assignments.find_one({"institution_id": iid, "class_name": {"$in": cns},
                                              "$or": [{"teacher_id": target["id"]}, {"teacher_email": target.get("email")}]}):
        return True
    return bool(await db.sections.find_one({"institution_id": iid, "class_name": {"$in": cns}, "class_teacher_id": target["id"]}))


async def _read_upload(file: UploadFile, max_mb: int):
    if file.content_type not in PHOTO_TYPES:
        raise HTTPException(status_code=400, detail="Please upload a JPG, PNG or WebP image")
    data = await file.read()
    if len(data) > max_mb * 1024 * 1024:
        raise HTTPException(status_code=400, detail=f"Image must be under {max_mb} MB")
    return data


# ---------------- Profile photos (teachers / parents / principals / admin) ----------------
@api.post("/profile/photo")
async def upload_profile_photo(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    if user["role"] == "student":
        raise HTTPException(status_code=400, detail="Students manage their photo from their student record")
    data = await _read_upload(file, 4)
    path = f"lnmo/photos/users/{user['id']}/{uuid.uuid4()}.{PHOTO_TYPES[file.content_type]}"
    try:
        result = _put_object(path, data, file.content_type)
    except Exception:
        raise HTTPException(status_code=502, detail="Photo storage is unavailable right now — try again shortly")
    await db.users.update_one({"id": user["id"]}, {"$set": {"photo_path": result["path"], "photo_type": file.content_type}})
    await audit(user, "upload_photo", "users", user["id"], user.get("name"))
    return {"message": "Photo updated", "has_photo": True}


@api.delete("/profile/photo")
async def delete_profile_photo(user: dict = Depends(get_current_user)):
    await db.users.update_one({"id": user["id"]}, {"$unset": {"photo_path": "", "photo_type": ""}})
    await audit(user, "delete_photo", "users", user["id"], user.get("name"))
    return {"message": "Photo removed", "has_photo": False}


@api.get("/users/{uid}/photo")
async def get_user_photo(uid: str, user: dict = Depends(get_current_user)):
    iid = user["institution_id"]
    target = await db.users.find_one({"id": uid, "institution_id": iid})
    if not target or not target.get("photo_path"):
        raise HTTPException(status_code=404, detail="No photo")
    allowed = (uid == user["id"] or user["role"] == "institution_admin")
    if not allowed:
        scope = await principal_scope(user)
        if scope:
            allowed = await _teacher_in_scope(scope, target)
        # teacher photos are the public-ish face — any member may view a TEACHER's photo
        if not allowed and target.get("role") == "teacher":
            allowed = True
    if not allowed:
        raise HTTPException(status_code=403, detail="Forbidden")
    try:
        data, ctype = _get_object(target["photo_path"])
    except Exception:
        raise HTTPException(status_code=404, detail="No photo")
    return Response(content=data, media_type=target.get("photo_type") or ctype,
                    headers={"Cache-Control": "private, max-age=300"})


# ---------------- Digital signatures — VAULT tier (teachers + principals only) ----------------
@api.post("/profile/signature")
async def upload_signature(file: UploadFile = File(...), user: dict = Depends(require_roles("teacher"))):
    data = await _read_upload(file, 2)
    path = f"lnmo/signatures/{user['id']}/{uuid.uuid4()}.{PHOTO_TYPES[file.content_type]}"
    try:
        result = _put_object(path, data, file.content_type)
    except Exception:
        raise HTTPException(status_code=502, detail="Signature storage is unavailable right now — try again shortly")
    await db.users.update_one({"id": user["id"]}, {"$set": {"signature_path": result["path"], "signature_type": file.content_type}})
    await audit(user, "upload_signature", "users", user["id"], user.get("name"))
    return {"message": "Signature saved", "has_signature": True}


@api.delete("/profile/signature")
async def delete_signature(user: dict = Depends(require_roles("teacher"))):
    await db.users.update_one({"id": user["id"]}, {"$unset": {"signature_path": "", "signature_type": ""}})
    await audit(user, "delete_signature", "users", user["id"], user.get("name"))
    return {"message": "Signature removed", "has_signature": False}


async def _serve_signature(target: dict):
    if not target or not target.get("signature_path"):
        raise HTTPException(status_code=404, detail="No signature")
    try:
        data, ctype = _get_object(target["signature_path"])
    except Exception:
        raise HTTPException(status_code=404, detail="No signature")
    return Response(content=data, media_type=target.get("signature_type") or ctype,
                    headers={"Cache-Control": "no-store"})


@api.get("/profile/signature")
async def get_own_signature(user: dict = Depends(require_roles("teacher"))):
    return await _serve_signature(user)


@api.get("/users/{uid}/signature")
async def get_user_signature(uid: str, user: dict = Depends(get_current_user)):
    # VAULT: owner, admin, or in-scope principal only. Students/parents NEVER.
    iid = user["institution_id"]
    target = await db.users.find_one({"id": uid, "institution_id": iid})
    if not target:
        raise HTTPException(status_code=404, detail="No signature")
    if uid == user["id"]:
        return await _serve_signature(target)
    if user["role"] not in ("institution_admin", "teacher"):
        raise HTTPException(status_code=403, detail="Forbidden")
    allowed = user["role"] == "institution_admin"
    if not allowed:
        scope = await principal_scope(user)
        allowed = bool(scope) and await _teacher_in_scope(scope, target)
    if not allowed:
        raise HTTPException(status_code=403, detail="Forbidden")
    return await _serve_signature(target)


# ---------------- School seal — VAULT tier (admin + any principal) ----------------
@api.post("/institution/seal")
async def upload_seal(file: UploadFile = File(...), user: dict = Depends(require_admin_or_principal)):
    iid = user["institution_id"]
    data = await _read_upload(file, 4)
    path = f"lnmo/seals/{iid}/{uuid.uuid4()}.{PHOTO_TYPES[file.content_type]}"
    try:
        result = _put_object(path, data, file.content_type)
    except Exception:
        raise HTTPException(status_code=502, detail="Seal storage is unavailable right now — try again shortly")
    await db.institutions.update_one({"id": iid}, {"$set": {"seal_path": result["path"], "seal_type": file.content_type}})
    await audit(user, "upload_seal", "institution_profile", iid, None)
    return {"message": "Seal saved", "has_seal": True}


@api.delete("/institution/seal")
async def delete_seal(user: dict = Depends(require_admin_or_principal)):
    await db.institutions.update_one({"id": user["institution_id"]}, {"$unset": {"seal_path": "", "seal_type": ""}})
    await audit(user, "delete_seal", "institution_profile", user["institution_id"], None)
    return {"message": "Seal removed", "has_seal": False}


@api.get("/institution/seal-status")
async def seal_status(user: dict = Depends(require_admin_or_principal)):
    inst = await db.institutions.find_one({"id": user["institution_id"]}, {"_id": 0, "seal_path": 1})
    return {"has_seal": bool((inst or {}).get("seal_path"))}


@api.get("/institution/seal")
async def get_seal(user: dict = Depends(require_admin_or_principal)):
    inst = await db.institutions.find_one({"id": user["institution_id"]}, {"_id": 0, "seal_path": 1, "seal_type": 1})
    if not inst or not inst.get("seal_path"):
        raise HTTPException(status_code=404, detail="No seal")
    try:
        data, ctype = _get_object(inst["seal_path"])
    except Exception:
        raise HTTPException(status_code=404, detail="No seal")
    return Response(content=data, media_type=inst.get("seal_type") or ctype,
                    headers={"Cache-Control": "no-store"})


# ---------------- Teacher profile with role-based field filtering ----------------
@api.get("/teachers/{tid}/profile")
async def teacher_profile_view(tid: str, user: dict = Depends(get_current_user)):
    iid = user["institution_id"]
    t = await db.users.find_one({"id": tid, "institution_id": iid, "role": "teacher"}, {"_id": 0, "password_hash": 0})
    if not t:
        raise HTTPException(status_code=404, detail="Teacher not found")
    assigns = await db.teacher_assignments.find(
        {"institution_id": iid, "$or": [{"teacher_id": tid}, {"teacher_email": t.get("email")}]}, {"_id": 0}).to_list(500)
    subjects = sorted({a.get("subject") for a in assigns if a.get("subject")})
    # privilege: self, admin, or in-scope principal → full; everyone else → limited
    privileged = (tid == user["id"] or user["role"] == "institution_admin")
    if not privileged and user["role"] == "teacher":
        scope = await principal_scope(user)
        privileged = bool(scope) and await _teacher_in_scope(scope, t)
    base = {"id": t["id"], "name": t.get("name"), "has_photo": bool(t.get("photo_path")),
            "subjects": subjects, "role": "teacher"}
    if not privileged:
        return {"profile": base, "full": False}
    homerooms = await db.sections.find({"institution_id": iid, "class_teacher_id": tid}, {"_id": 0}).to_list(100)
    # Principal block for the VIEWED teacher (sourced from principal_assignments, not /auth/me).
    pa = await db.principal_assignments.find_one({"institution_id": iid, "user_id": tid}, {"_id": 0})
    principal = None
    if pa:
        unit_ids = pa.get("unit_ids") or []
        units = await db.academic_units.find(
            {"institution_id": iid, "id": {"$in": unit_ids}}, {"_id": 0, "id": 1, "name": 1}).to_list(200)
        principal = {"designation": pa.get("designation") or "principal", "scope_type": pa.get("scope_type"),
                     "unit_ids": unit_ids, "unit_names": [u.get("name") for u in units]}
    base.update({"email": t.get("email"), "phone": t.get("phone"), "phone_verified": bool(t.get("phone_verified")),
                 "employee_id": t.get("employee_id"),
                 "specialization": t.get("specialization"), "status": t.get("status"),
                 "has_signature": bool(t.get("signature_path")),
                 "is_principal": bool(pa), "principal": principal,
                 "assignments": [{"class_name": a.get("class_name"), "section": a.get("section"), "subject": a.get("subject")} for a in assigns],
                 "homerooms": [{"class_name": h.get("class_name"), "section": h.get("name")} for h in homerooms]})
    return {"profile": base, "full": True}



# New collections: `exams` (header + per-division date/slot configs) and `exam_entries` (one row per
# scheduled paper, per class, optionally per section). Additive — never touches timetable_entries.
# Mark registers reuse the existing `assessments` collection (linked via exam_id) so the marks grid
# "just works". Principals are scoped to their divisions server-side.

class ExamSlot(BaseModel):
    start: str
    end: str
    label: Optional[str] = None


class DivisionConfig(BaseModel):
    academic_unit_id: str
    date_start: str
    date_end: str
    slots_per_day: List[ExamSlot] = PField(default_factory=list)


class ExamCreate(BaseModel):
    academic_year: Optional[str] = ""
    name: str
    type: str = "model"
    division_configs: List[DivisionConfig] = PField(default_factory=list)


class ExamUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    division_configs: Optional[List[DivisionConfig]] = None


class ExamGenerateRequest(BaseModel):
    create_registers: bool = True


class ExamEntryMove(BaseModel):
    date: str
    slot_index: int
    override: bool = False


class ExamEntryEdit(BaseModel):
    room: Optional[str] = None
    start: Optional[str] = None
    end: Optional[str] = None


EXAM_TYPES = {"model", "term", "unit", "other"}
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _d(s):
    return datetime.strptime(s, "%Y-%m-%d").date()


def _valid_time(s):
    return bool(re.match(r"^\d{2}:\d{2}$", s or ""))


def _date_range(start, end):
    a, b = _d(start), _d(end)
    out, cur = [], a
    while cur <= b:
        out.append(cur.isoformat())
        cur += timedelta(days=1)
    return out


async def _validate_division_configs(iid, configs, scope):
    if not configs:
        raise HTTPException(status_code=400, detail="Configure at least one division (date range + slots)")
    seen = set()
    for c in configs:
        unit = await db.academic_units.find_one({"id": c.academic_unit_id, "institution_id": iid}, {"_id": 0})
        if not unit:
            raise HTTPException(status_code=400, detail="A selected division does not exist")
        if c.academic_unit_id in seen:
            raise HTTPException(status_code=400, detail=f"Division {unit.get('name')} is configured more than once")
        seen.add(c.academic_unit_id)
        if scope and not scope["whole_school"] and c.academic_unit_id not in (scope["unit_ids"] or []):
            raise HTTPException(status_code=403, detail=f"Division {unit.get('name')} is outside your assigned scope")
        if not (_DATE_RE.match(c.date_start or "") and _DATE_RE.match(c.date_end or "")):
            raise HTTPException(status_code=400, detail=f"{unit.get('name')}: valid start and end dates are required")
        if _d(c.date_end) < _d(c.date_start):
            raise HTTPException(status_code=400, detail=f"{unit.get('name')}: end date must be on or after the start date")
        if not c.slots_per_day:
            raise HTTPException(status_code=400, detail=f"{unit.get('name')}: add at least one daily slot")
        for s in c.slots_per_day:
            if not (_valid_time(s.start) and _valid_time(s.end)):
                raise HTTPException(status_code=400, detail=f"{unit.get('name')}: each slot needs a start and end time (HH:MM)")
            if s.end <= s.start:
                raise HTTPException(status_code=400, detail=f"{unit.get('name')}: a slot's end time must be after its start time")


def _cfg_dicts(configs):
    return [{"academic_unit_id": c.academic_unit_id, "date_start": c.date_start, "date_end": c.date_end,
             "slots_per_day": [{"start": s.start, "end": s.end, "label": s.label} for s in c.slots_per_day]}
            for c in configs]


async def _exam_or_404(iid, exam_id):
    exam = await db.exams.find_one({"id": exam_id, "institution_id": iid}, {"_id": 0})
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")
    return exam


def _exam_touches_scope(exam, scope):
    if not scope or scope["whole_school"]:
        return True
    units = {dc["academic_unit_id"] for dc in exam.get("division_configs", [])}
    return bool(units & set(scope["unit_ids"] or []))


async def _guard_exam_edit(user, exam):
    """A unit principal may only create/edit exams that live ENTIRELY within their divisions."""
    scope = await principal_scope(user)
    if not scope or scope["whole_school"]:
        return
    units = {dc["academic_unit_id"] for dc in exam.get("division_configs", [])}
    if not units.issubset(set(scope["unit_ids"] or [])):
        raise HTTPException(status_code=403, detail="This exam spans divisions outside your scope — read-only for you")


@api.get("/exams")
async def list_exams(academic_year: str = "", user: dict = Depends(require_admin_or_principal)):
    iid = user["institution_id"]
    scope = await principal_scope(user)
    q = {"institution_id": iid}
    if academic_year:
        q["academic_year"] = academic_year
    units = {u["id"]: u["name"] for u in await db.academic_units.find({"institution_id": iid}, {"_id": 0, "id": 1, "name": 1}).to_list(500)}
    out = []
    for e in await db.exams.find(q, {"_id": 0}).sort("created_at", -1).to_list(500):
        # Show ALL institution exams. Unit principals get READ-ONLY on exams that aren't fully
        # within their divisions (editable=false), rather than hiding them.
        n_entries = await db.exam_entries.count_documents({"exam_id": e["id"]})
        e["division_names"] = [units.get(dc["academic_unit_id"], "?") for dc in e.get("division_configs", [])]
        e["entry_count"] = n_entries
        e["editable"] = (not scope or scope["whole_school"] or
                         {dc["academic_unit_id"] for dc in e.get("division_configs", [])}.issubset(set(scope["unit_ids"] or [])))
        out.append(e)
    return {"exams": out}


@api.post("/exams")
async def create_exam(body: ExamCreate, user: dict = Depends(require_admin_or_principal)):
    iid = user["institution_id"]
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Exam name is required")
    if body.type not in EXAM_TYPES:
        raise HTTPException(status_code=400, detail="Invalid exam type")
    scope = await principal_scope(user)
    await _validate_division_configs(iid, body.division_configs, scope)
    ay = (body.academic_year or "").strip() or await _active_year_name(iid)
    exam = {"id": str(uuid.uuid4()), "institution_id": iid, "academic_year": ay, "name": name,
            "type": body.type, "status": "draft", "division_configs": _cfg_dicts(body.division_configs),
            "created_by": user["id"], "created_at": now_iso()}
    await db.exams.insert_one(dict(exam))
    await audit(user, "create", "exams", exam["id"], f"{name} ({body.type}) · {len(body.division_configs)} division(s)")
    exam.pop("_id", None)
    return {"exam": exam}


async def _exam_detail_payload(iid, exam):
    units = {u["id"]: u["name"] for u in await db.academic_units.find({"institution_id": iid}, {"_id": 0, "id": 1, "name": 1}).to_list(500)}
    entries = await db.exam_entries.find({"exam_id": exam["id"]}, {"_id": 0}).to_list(5000)
    exam["division_names"] = [units.get(dc["academic_unit_id"], "?") for dc in exam.get("division_configs", [])]
    exam["unit_names"] = units
    return {"exam": exam, "entries": entries}


@api.get("/exams/{exam_id}")
async def get_exam(exam_id: str, user: dict = Depends(require_admin_or_principal)):
    iid = user["institution_id"]
    exam = await _exam_or_404(iid, exam_id)
    scope = await principal_scope(user)
    if not _exam_touches_scope(exam, scope):
        raise HTTPException(status_code=403, detail="This exam is outside your assigned scope")
    return await _exam_detail_payload(iid, exam)


@api.put("/exams/{exam_id}")
async def update_exam(exam_id: str, body: ExamUpdate, user: dict = Depends(require_admin_or_principal)):
    iid = user["institution_id"]
    exam = await _exam_or_404(iid, exam_id)
    await _guard_exam_edit(user, exam)
    patch = {}
    if body.name is not None:
        nm = body.name.strip()
        if not nm:
            raise HTTPException(status_code=400, detail="Exam name cannot be empty")
        patch["name"] = nm
    if body.type is not None:
        if body.type not in EXAM_TYPES:
            raise HTTPException(status_code=400, detail="Invalid exam type")
        patch["type"] = body.type
    if body.division_configs is not None:
        scope = await principal_scope(user)
        await _validate_division_configs(iid, body.division_configs, scope)
        patch["division_configs"] = _cfg_dicts(body.division_configs)
    if patch:
        patch["updated_at"] = now_iso()
        await db.exams.update_one({"id": exam_id}, {"$set": patch})
        await audit(user, "update", "exams", exam_id, exam["name"])
    return await _exam_detail_payload(iid, await _exam_or_404(iid, exam_id))


@api.delete("/exams/{exam_id}")
async def delete_exam(exam_id: str, user: dict = Depends(require_admin_or_principal)):
    iid = user["institution_id"]
    exam = await _exam_or_404(iid, exam_id)
    await _guard_exam_edit(user, exam)
    await db.exam_entries.delete_many({"exam_id": exam_id})
    await db.assessments.delete_many({"institution_id": iid, "exam_id": exam_id})
    await db.exams.delete_one({"id": exam_id})
    await audit(user, "delete", "exams", exam_id, exam["name"])
    return {"ok": True}


async def _create_exam_registers(iid, exam, entries):
    """Idempotently create a mark register (assessment) per class-subject(-section) linked by exam_id."""
    created = 0
    for e in entries:
        q = {"institution_id": iid, "exam_id": exam["id"], "class_name": e["class_name"],
             "subject": e["subject"], "section": e.get("section") or ""}
        if await db.assessments.find_one(q):
            continue
        off = await db.subject_offerings.find_one(
            {"institution_id": iid, "class_name": e["class_name"], "subject": e["subject"]}, {"_id": 0})
        mm = int(off.get("max_marks")) if off and off.get("max_marks") else 100
        await db.assessments.insert_one({
            "id": str(uuid.uuid4()), "institution_id": iid, "academic_year": exam.get("academic_year"),
            "name": f"{exam['name']} — {e['subject']}", "subject": e["subject"],
            "class_name": e["class_name"], "section": e.get("section") or "", "exam_id": exam["id"],
            "max_marks": mm, "theory_max_marks": mm, "practical_max_marks": 0, "has_practical": False,
            "status": "draft", "created_at": now_iso()})
        created += 1
    return created


@api.post("/exams/{exam_id}/generate")
async def generate_exam(exam_id: str, body: ExamGenerateRequest, user: dict = Depends(require_admin_or_principal)):
    iid = user["institution_id"]
    exam = await _exam_or_404(iid, exam_id)
    await _guard_exam_edit(user, exam)
    # wipe existing schedule for this exam (never touches published timetables / other exams)
    await db.exam_entries.delete_many({"exam_id": exam_id})
    placed, unplaced = [], []
    for dc in exam.get("division_configs", []):
        unit_id = dc["academic_unit_id"]
        unit = await db.academic_units.find_one({"id": unit_id, "institution_id": iid}, {"_id": 0}) or {}
        href_exam = f"/app/exams/{exam_id}"
        dates = _date_range(dc["date_start"], dc["date_end"])
        slots = dc.get("slots_per_day") or []
        slot_list = [(d, si) for d in dates for si in range(len(slots))]
        classes = await db.classes.find({"institution_id": iid, "academic_unit_id": unit_id}, {"_id": 0}).sort("name", 1).to_list(500)
        for cls in classes:
            cn = cls["name"]
            sec_docs = await db.sections.find({"institution_id": iid, "class_name": cn}, {"_id": 0, "name": 1}).sort("name", 1).to_list(100)
            sections = [s["name"] for s in sec_docs]
            if not sections:
                continue
            offered_map = await _offered_sections_map(iid, cn, sections)  # subject -> [sections]
            flex_reqs = {r["subject"]: r for r in await db.subject_requirements.find({"institution_id": iid, "class_name": cn}, {"_id": 0}).to_list(500)}

            # Build exam units. A subject offered to ALL sections → one whole-class paper (section="").
            # A subject offered to only some sections → one paper per offering section.
            units_to_place = []
            for subj in sorted(offered_map.keys()):
                osecs = offered_map[subj]
                if not osecs:
                    continue
                r = flex_reqs.get(subj)
                is_core = not (_req_flexible(r) if r else _is_flexible_default(subj))
                if len(osecs) == len(sections):
                    units_to_place.append({"subject": subj, "scope": "", "secs": list(sections), "core": is_core})
                else:
                    for sec in osecs:
                        units_to_place.append({"subject": subj, "scope": sec, "secs": [sec], "core": is_core})
            # core subjects first (better spacing), then alphabetical
            units_to_place.sort(key=lambda u: (0 if u["core"] else 1, u["subject"]))

            busy = set()          # (section, date, slot_index)
            core_dates = {}       # section -> set(dates with a core paper)

            def _adjacent(d, secs):
                dd = _d(d)
                for s in secs:
                    for cd in core_dates.get(s, set()):
                        if abs((dd - _d(cd)).days) == 1:
                            return True
                return False

            for u in units_to_place:
                secs = u["secs"]
                chosen = None
                # pass 1: honor best-effort spacing for core subjects
                for (d, si) in slot_list:
                    if any((s, d, si) in busy for s in secs):
                        continue
                    if u["core"] and _adjacent(d, secs):
                        continue
                    chosen = (d, si)
                    break
                if not chosen:  # pass 2: relax spacing
                    for (d, si) in slot_list:
                        if any((s, d, si) in busy for s in secs):
                            continue
                        chosen = (d, si)
                        break
                if not chosen:
                    cap = len(slot_list)
                    unplaced.append({
                        "class_name": cn, "section": u["scope"], "subject": u["subject"],
                        "cause": "slots_full",
                        "reason": f"{u['subject']}: no free slot for {cn}{(' - ' + u['scope']) if u['scope'] else ''} — "
                                  f"{unit.get('name')} has only {cap} exam slot(s) ({len(dates)} day(s) × {len(slots)} slot(s)) and they are all taken.",
                        "suggestions": [
                            {"label": f"Add more dates or daily slots to {unit.get('name')}", "href": href_exam},
                        ]})
                    continue
                d, si = chosen
                slot = slots[si]
                for s in secs:
                    busy.add((s, d, si))
                if u["core"]:
                    for s in secs:
                        core_dates.setdefault(s, set()).add(d)
                placed.append({
                    "id": str(uuid.uuid4()), "exam_id": exam_id, "institution_id": iid,
                    "academic_year": exam.get("academic_year"), "academic_unit_id": unit_id,
                    "class_name": cn, "section": u["scope"], "subject": u["subject"],
                    "date": d, "slot_index": si, "start": slot["start"], "end": slot["end"],
                    "room": "", "status": "scheduled", "original_date": None, "original_slot": None,
                    "created_at": now_iso()})
    if placed:
        await db.exam_entries.insert_many([dict(p) for p in placed])
    registers_created = 0
    if body.create_registers and placed:
        registers_created = await _create_exam_registers(iid, exam, placed)
    await audit(user, "generate", "exams", exam_id,
                f"{exam['name']}: {len(placed)} papers scheduled, {len(unplaced)} unplaced"
                + (f", {registers_created} registers" if registers_created else ""))
    return {"generated": len(placed), "unplaced": unplaced, "registers_created": registers_created}


@api.post("/exams/{exam_id}/registers")
async def create_exam_registers_endpoint(exam_id: str, user: dict = Depends(require_admin_or_principal)):
    iid = user["institution_id"]
    exam = await _exam_or_404(iid, exam_id)
    await _guard_exam_edit(user, exam)
    entries = await db.exam_entries.find({"exam_id": exam_id, "status": {"$ne": "cancelled"}}, {"_id": 0}).to_list(5000)
    created = await _create_exam_registers(iid, exam, entries)
    await audit(user, "create_registers", "exams", exam_id, f"{exam['name']}: {created} register(s)")
    return {"registers_created": created}


async def _exam_entry_or_404(iid, entry_id):
    e = await db.exam_entries.find_one({"id": entry_id, "institution_id": iid}, {"_id": 0})
    if not e:
        raise HTTPException(status_code=404, detail="Exam entry not found")
    return e


async def _exam_move_conflicts(iid, exam, entry, date, slot_index):
    conflicts = []
    dc = next((c for c in exam.get("division_configs", []) if c["academic_unit_id"] == entry.get("academic_unit_id")), None)
    if dc:
        if not (dc["date_start"] <= date <= dc["date_end"]):
            conflicts.append({"type": "date_out_of_range",
                              "message": f"{date} is outside this division's window ({dc['date_start']} → {dc['date_end']})"})
        if slot_index < 0 or slot_index >= len(dc.get("slots_per_day") or []):
            conflicts.append({"type": "slot_out_of_range",
                              "message": f"Slot {slot_index + 1} does not exist in this division's daily slots"})
    # class double-booking: a section of this paper already sits another paper at the target slot
    target_secs = set([entry.get("section")]) if entry.get("section") else None
    async for o in db.exam_entries.find({"exam_id": exam["id"], "class_name": entry["class_name"],
                                         "date": date, "slot_index": slot_index, "status": {"$ne": "cancelled"},
                                         "id": {"$ne": entry["id"]}}, {"_id": 0}):
        o_secs = set([o.get("section")]) if o.get("section") else None
        clash = (target_secs is None or o_secs is None or bool(target_secs & o_secs))
        if clash:
            conflicts.append({"type": "class_double_booked",
                              "message": f"{entry['class_name']}{(' - ' + entry['section']) if entry.get('section') else ''} already has {o['subject']} in this slot"})
    return conflicts


@api.post("/exam-entries/{entry_id}/move")
async def move_exam_entry(entry_id: str, body: ExamEntryMove, user: dict = Depends(require_admin_or_principal)):
    iid = user["institution_id"]
    entry = await _exam_entry_or_404(iid, entry_id)
    exam = await _exam_or_404(iid, entry["exam_id"])
    await _guard_exam_edit(user, exam)
    if not _DATE_RE.match(body.date or ""):
        raise HTTPException(status_code=400, detail="A valid target date is required")
    conflicts = await _exam_move_conflicts(iid, exam, entry, body.date, body.slot_index)
    if conflicts and not body.override:
        return {"ok": False, "conflicts": conflicts}
    dc = next((c for c in exam.get("division_configs", []) if c["academic_unit_id"] == entry.get("academic_unit_id")), None)
    slots = (dc.get("slots_per_day") if dc else []) or []
    start = slots[body.slot_index]["start"] if 0 <= body.slot_index < len(slots) else entry.get("start")
    end = slots[body.slot_index]["end"] if 0 <= body.slot_index < len(slots) else entry.get("end")
    patch = {"date": body.date, "slot_index": body.slot_index, "start": start, "end": end}
    orig_d, orig_s = entry.get("original_date"), entry.get("original_slot")
    moving_back = orig_d is not None and body.date == orig_d and body.slot_index == orig_s
    if moving_back:
        # restored to its original date/slot → clear the postponement trail
        patch["status"] = "scheduled"
        patch["original_date"] = None
        patch["original_slot"] = None
    else:
        patch["status"] = "postponed"
        if entry.get("original_date") is None:
            patch["original_date"] = entry["date"]
            patch["original_slot"] = entry["slot_index"]
    await db.exam_entries.update_one({"id": entry_id}, {"$set": patch})
    await audit(user, "override" if (conflicts and body.override) else ("restore" if moving_back else "postpone"),
                "exam_entries", entry_id,
                f"{entry['class_name']} {entry['subject']} → {body.date} slot {body.slot_index + 1}"
                + (" [OVERRIDE]" if (conflicts and body.override) else ("" if not moving_back else " [RESTORED]")))
    return {"ok": True, "conflicts": conflicts}


@api.put("/exam-entries/{entry_id}")
async def edit_exam_entry(entry_id: str, body: ExamEntryEdit, user: dict = Depends(require_admin_or_principal)):
    iid = user["institution_id"]
    entry = await _exam_entry_or_404(iid, entry_id)
    exam = await _exam_or_404(iid, entry["exam_id"])
    await _guard_exam_edit(user, exam)
    patch = {}
    if body.room is not None:
        patch["room"] = body.room.strip()
    if body.start is not None or body.end is not None:
        start = body.start if body.start is not None else entry.get("start")
        end = body.end if body.end is not None else entry.get("end")
        if not (_valid_time(start) and _valid_time(end)):
            raise HTTPException(status_code=400, detail="Times must be HH:MM")
        if end <= start:
            raise HTTPException(status_code=400, detail="End time must be after start time")
        patch["start"], patch["end"] = start, end
    if patch:
        await db.exam_entries.update_one({"id": entry_id}, {"$set": patch})
        await audit(user, "update", "exam_entries", entry_id, f"{entry['class_name']} {entry['subject']}")
    return {"ok": True}


@api.post("/exam-entries/{entry_id}/cancel")
async def cancel_exam_entry(entry_id: str, user: dict = Depends(require_admin_or_principal)):
    iid = user["institution_id"]
    entry = await _exam_entry_or_404(iid, entry_id)
    exam = await _exam_or_404(iid, entry["exam_id"])
    await _guard_exam_edit(user, exam)
    await db.exam_entries.update_one({"id": entry_id}, {"$set": {"status": "cancelled"}})
    await audit(user, "cancel", "exam_entries", entry_id, f"{entry['class_name']} {entry['subject']}")
    return {"ok": True}


@api.post("/exams/{exam_id}/publish")
async def publish_exam(exam_id: str, user: dict = Depends(require_admin_or_principal)):
    iid = user["institution_id"]
    exam = await _exam_or_404(iid, exam_id)
    await _guard_exam_edit(user, exam)
    await db.exams.update_one({"id": exam_id}, {"$set": {"status": "published", "published_at": now_iso()}})
    await audit(user, "publish", "exams", exam_id, exam["name"])
    return {"ok": True}


@api.post("/exams/{exam_id}/unpublish")
async def unpublish_exam(exam_id: str, user: dict = Depends(require_admin_or_principal)):
    iid = user["institution_id"]
    exam = await _exam_or_404(iid, exam_id)
    await _guard_exam_edit(user, exam)
    await db.exams.update_one({"id": exam_id}, {"$set": {"status": "draft"}})
    await audit(user, "unpublish", "exams", exam_id, exam["name"])
    return {"ok": True}


class ExamPublishResults(BaseModel):
    publish: bool = True
    class_name: Optional[str] = None


@api.post("/exams/{exam_id}/publish-results")
async def publish_exam_results(exam_id: str, body: ExamPublishResults,
                               user: dict = Depends(require_admin_or_principal)):
    """Bulk publish/unpublish every mark register linked to this exam (optionally one class).
    Admin anywhere; a unit principal only for in-scope classes (out-of-scope silently skipped,
    or 403 when an out-of-scope class is named explicitly). Teachers never reach here."""
    iid = user["institution_id"]
    exam = await _exam_or_404(iid, exam_id)
    if body.class_name and not await _is_privileged_marks(user, body.class_name):
        raise HTTPException(status_code=403, detail="This class is outside your assigned scope")
    q = {"institution_id": iid, "exam_id": exam_id}
    if body.class_name:
        q["class_name"] = body.class_name
    status = "published" if body.publish else "draft"
    updated, skipped = 0, 0
    async for a in db.assessments.find(q, {"_id": 0}):
        if not await _is_privileged_marks(user, a.get("class_name")):
            skipped += 1
            continue
        await db.assessments.update_one({"id": a["id"]}, {"$set": {"status": status}})
        updated += 1
    await audit(user, "publish_results" if body.publish else "unpublish_results", "exams", exam_id,
                f"{exam['name']}: {updated} register(s) {status}" + (f" ({skipped} out of scope)" if skipped else ""))
    return {"updated": updated, "skipped": skipped, "status": status}


@api.get("/portal/exams")
async def portal_exams(user: dict = Depends(require_roles("student"))):
    return await _student_exams(user["institution_id"], user.get("student_id"))


@api.get("/parent/child/{student_id}/exams")
async def parent_child_exams(student_id: str, user: dict = Depends(require_roles("parent"))):
    if student_id not in (user.get("student_ids") or []):
        raise HTTPException(status_code=403, detail="This student is not linked to your account")
    return await _student_exams(user["institution_id"], student_id)


async def _student_exams(iid, sid):
    """Published exam papers for the student's class/section (Phase 54: shared by student + parent portals)."""
    student = await db.students.find_one({"id": sid, "institution_id": iid}, {"_id": 0}) if sid else None
    if not student or not student.get("class_name"):
        return {"exams": []}
    cn, sec = student["class_name"], student.get("section")
    pub = {e["id"]: e for e in await db.exams.find({"institution_id": iid, "status": "published"}, {"_id": 0}).to_list(500)}
    rows = []
    async for e in db.exam_entries.find(
            {"institution_id": iid, "exam_id": {"$in": list(pub.keys())}, "class_name": cn,
             "status": {"$ne": "cancelled"},
             "$or": [{"section": {"$in": ["", None]}}, {"section": sec}]}, {"_id": 0}):
        ex = pub.get(e["exam_id"], {})
        rows.append({"exam_name": ex.get("name"), "subject": e["subject"], "date": e["date"],
                     "start": e["start"], "end": e["end"], "room": e.get("room") or "",
                     "status": e["status"]})
    rows.sort(key=lambda r: (r["date"], r["start"]))
    return {"exams": rows}



# ---------------- Parent portal ----------------

@api.post("/students/{student_id}/parent-user")
async def create_parent_user(student_id: str, payload: dict = Body(...),
                             user: dict = Depends(require_admin_or_principal)):
    iid = user["institution_id"]
    student = await db.students.find_one({"id": student_id, "institution_id": iid})
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    await guard_principal_class(user, student.get("class_name"))
    email = (payload.get("email") or "").strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="Email is required")
    existing = await db.users.find_one({"email": email})
    if existing:
        if existing.get("role") != "parent" or existing.get("institution_id") != iid:
            raise HTTPException(status_code=400, detail="Email already in use by a non-parent account")
        if student_id in (existing.get("student_ids") or []):
            raise HTTPException(status_code=400, detail="This parent is already linked to the student")
        await db.users.update_one({"id": existing["id"]}, {"$addToSet": {"student_ids": student_id}})
        await audit(user, "link_parent", "users", existing["id"], email)
        return {"message": f"Linked {email} to this student", "linked": True}
    password = payload.get("password") or ""
    if not password:
        raise HTTPException(status_code=400, detail="Password is required for a new parent account")
    name = (payload.get("name") or "").strip() or student.get("guardian_name") or email
    uid = str(uuid.uuid4())
    await db.users.insert_one({"id": uid, "name": name, "email": email,
                               "password_hash": hash_password(password), "role": "parent",
                               "student_ids": [student_id], "institution_id": iid,
                               "status": "active", "created_at": now_iso()})
    await audit(user, "create_parent", "users", uid, email)
    return {"message": f"Parent login created for {email}", "linked": False}


# ==================== PHASE 46: PHONE-KEYED PARENT INVITE SYSTEM ====================
def _norm_phone(p):
    d = re.sub(r"\D", "", str(p or ""))
    return d[-10:] if len(d) > 10 else d


def _gname_key(n):
    return re.sub(r"\s+", " ", str(n or "").strip().lower())


SETUP_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def _norm_setup_code(c):
    return re.sub(r"[^A-Z0-9]", "", str(c or "").upper())


async def _parent_by_phone(iid, phone):
    return await db.users.find_one({"institution_id": iid, "role": "parent", "phone": phone})


async def _linked_student_ids(iid):
    ids = set()
    async for u in db.users.find({"institution_id": iid, "role": "parent"}, {"_id": 0, "student_ids": 1}):
        ids.update(u.get("student_ids") or [])
    return ids


async def _send_parent_invite(iid, school_name, parent_uid, parent_name, phone, channel):
    tpl = await db.comm_templates.find_one({"institution_id": None, "name": "Parent invite"}, {"_id": 0})
    link = f"{os.environ['PUBLIC_BASE_URL']}/setup/parent/{_make_secure_link(iid, f'psetup:{parent_uid}', 72)}"
    vals = {"school_name": school_name or "", "parent_name": parent_name or "Parent", "secure_link": link}
    body = _render_template(tpl["body"], vals) if tpl else f"{school_name}: Set up your parent account — {link}"
    try:
        res = await send_message(iid, channel, [{"name": parent_name or "Parent", "phone": phone, "body": body, "vars": vals}],
                                 template_id=(tpl["id"] if tpl else None), module="parent_invite")
        return "sent" if res.get("sent") else "failed"
    except HTTPException:
        return "failed"


async def _run_parent_invites(iid, student_list, channel, actor):
    """Phone-keyed invite over a student list. Returns the four buckets; sends via comm engine.
    `channel` may be one channel or a list (Phase 58: whatsapp/sms/email)."""
    channels = [channel] if isinstance(channel, str) else list(channel)
    school = await db.institutions.find_one({"id": iid}, {"_id": 0, "name": 1, "slug": 1, "code": 1})
    school_name = (school or {}).get("name")
    slug = ((school or {}).get("slug") or (school or {}).get("code") or "sch").lower()
    # institution-wide phone groups for collision detection
    phone_groups = {}
    async for s in db.students.find({"institution_id": iid}, {"_id": 0, "id": 1, "guardian_phone": 1, "guardian_name": 1}):
        ph = _norm_phone(s.get("guardian_phone"))
        if ph:
            phone_groups.setdefault(ph, []).append(s)
    dismissed = {r["phone"] async for r in db.parent_invite_reviews.find({"institution_id": iid, "status": {"$in": ["dismissed", "resolved"]}}, {"_id": 0, "phone": 1})}
    invited, already_linked, skipped_no_phone, collisions = [], [], [], []
    created_cache = {}
    for s in student_list:
        sid = s["id"]
        sname = f"{s.get('first_name','')} {s.get('last_name','')}".strip()
        cls = (s.get("class_name") or "") + (f" {s.get('section')}" if s.get("section") else "")
        phone = _norm_phone(s.get("guardian_phone"))
        if not phone:
            skipped_no_phone.append({"student_id": sid, "student_name": sname, "class": cls, "admission_no": s.get("admission_no")})
            continue
        group = phone_groups.get(phone, [])
        names = {_gname_key(g.get("guardian_name")) for g in group if _gname_key(g.get("guardian_name"))}
        if len(names) > 1 and phone not in dismissed:
            collisions.append({"student_id": sid, "student_name": sname, "class": cls,
                               "phone": phone, "guardian_name": s.get("guardian_name")})
            continue
        existing = created_cache.get(phone) or await _parent_by_phone(iid, phone)
        if existing:
            if sid in (existing.get("student_ids") or []):
                already_linked.append({"student_id": sid, "student_name": sname, "class": cls})
            else:
                await db.users.update_one({"id": existing["id"]}, {"$addToSet": {"student_ids": sid}})
                existing.setdefault("student_ids", []).append(sid)
                await db.parent_invites.insert_one({"id": str(uuid.uuid4()), "institution_id": iid, "student_id": sid,
                                                    "parent_user_id": existing["id"], "phone": phone, "status": "linked",
                                                    "channel": ",".join(channels), "sent_at": now_iso()})
                invited.append({"student_id": sid, "student_name": sname, "class": cls, "phone": phone, "action": "linked_sibling"})
            continue
        uid = str(uuid.uuid4())
        login_email = f"p{phone}@{slug}.parent.invite"
        gmail = (s.get("guardian_email") or "").strip().lower()
        if gmail and re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", gmail) and not await db.users.find_one({"email": gmail}, {"_id": 1}):
            login_email = gmail
        pname = s.get("guardian_name") or f"Parent of {sname}"
        await db.users.insert_one({"id": uid, "name": pname, "email": login_email, "phone": phone,
                                   "password_hash": hash_password(secrets.token_urlsafe(10)), "role": "parent",
                                   "student_ids": [sid], "institution_id": iid, "status": "active",
                                   "must_change_password": True, "invited": True, "created_at": now_iso()})
        created_cache[phone] = await db.users.find_one({"id": uid})
        per = await phase58.send_invite_multi(iid, school_name, created_cache[phone], channels, [sname])
        status = phase58.overall(per)
        await db.parent_invites.insert_one({"id": str(uuid.uuid4()), "institution_id": iid, "student_id": sid,
                                            "parent_user_id": uid, "phone": phone, "status": status,
                                            "channel": ",".join(channels), "channels": per, "sent_at": now_iso()})
        invited.append({"student_id": sid, "student_name": sname, "class": cls, "phone": phone,
                        "action": "created", "delivery": status, "channels": per})
    if actor:
        await audit(actor, "invite_parents", "parent_invites", None, f"{len(invited)} invited, {len(collisions)} review", iid)
    return {"invited": invited, "already_linked": already_linked,
            "skipped_no_phone": skipped_no_phone, "collisions_for_review": collisions}


async def _invite_scope_students(iid, user, payload):
    allowed = await _comm_scope_class_names(user)
    if payload.get("all"):
        names = allowed  # None = whole school
    else:
        names = await _comm_resolve_classes(iid, {"class_ids": payload.get("class_ids") or [],
                                                   "class_names": payload.get("class_names") or []}, allowed)
    q = {"institution_id": iid, "enrollment_status": "enrolled"}
    if names is not None:
        q["class_name"] = {"$in": list(names)}
    return await db.students.find(q, {"_id": 0}).to_list(20000)


@api.post("/students/invite-parents")
async def invite_parents(payload: dict = Body(...), user: dict = Depends(require_admin_or_principal)):
    iid = user["institution_id"]
    channel = phase58.parse_channels(payload)
    students = await _invite_scope_students(iid, user, payload)
    res = await _run_parent_invites(iid, students, channel, user)
    run = await phase59.save_run(user, "parent_invite", "Parent invites", phase59.invite_items(res))
    return {**res, **run}


@api.post("/students/{student_id}/invite-parent")
async def invite_single_parent(student_id: str, payload: dict = Body(default={}), user: dict = Depends(require_admin_or_principal)):
    iid = user["institution_id"]
    channel = phase58.parse_channels(payload or {})
    s = await db.students.find_one({"id": student_id, "institution_id": iid}, {"_id": 0})
    if not s:
        raise HTTPException(status_code=404, detail="Student not found")
    await guard_principal_class(user, s.get("class_name"))
    return await _run_parent_invites(iid, [s], channel, user)


@api.get("/students/ready-to-invite")
async def ready_to_invite(user: dict = Depends(require_admin_or_principal)):
    """Enrolled students with a guardian phone but no linked parent account yet."""
    iid = user["institution_id"]
    allowed = await _comm_scope_class_names(user)
    linked = await _linked_student_ids(iid)
    q = {"institution_id": iid, "enrollment_status": "enrolled"}
    if allowed is not None:
        q["class_name"] = {"$in": list(allowed)}
    rows = []
    async for s in db.students.find(q, {"_id": 0}):
        if s["id"] in linked:
            continue
        if not _norm_phone(s.get("guardian_phone")):
            continue
        rows.append({"student_id": s["id"], "student_name": f"{s.get('first_name','')} {s.get('last_name','')}".strip(),
                     "class": (s.get("class_name") or "") + (f" {s.get('section')}" if s.get("section") else ""),
                     "guardian_name": s.get("guardian_name"), "phone": _norm_phone(s.get("guardian_phone")),
                     "has_email": bool((s.get("guardian_email") or "").strip())})
    return {"ready": rows}


@api.get("/students/invite-review")
async def invite_review(user: dict = Depends(require_admin_or_principal)):
    iid = user["institution_id"]
    phone_groups = {}
    async for s in db.students.find({"institution_id": iid, "enrollment_status": "enrolled"}, {"_id": 0}):
        ph = _norm_phone(s.get("guardian_phone"))
        if ph:
            phone_groups.setdefault(ph, []).append(s)
    dismissed = {r["phone"] async for r in db.parent_invite_reviews.find({"institution_id": iid, "status": {"$in": ["dismissed", "resolved"]}}, {"_id": 0, "phone": 1})}
    groups = []
    for ph, members in phone_groups.items():
        names = {_gname_key(m.get("guardian_name")) for m in members if _gname_key(m.get("guardian_name"))}
        if len(names) > 1 and ph not in dismissed:
            groups.append({"phone": ph, "students": [
                {"student_id": m["id"], "student_name": f"{m.get('first_name','')} {m.get('last_name','')}".strip(),
                 "class": (m.get("class_name") or "") + (f" {m.get('section')}" if m.get("section") else ""),
                 "guardian_name": m.get("guardian_name")} for m in members]})
    return {"review": groups}


@api.post("/students/invite-review/resolve")
async def resolve_invite_review(payload: dict = Body(...), user: dict = Depends(require_admin_or_principal)):
    iid = user["institution_id"]
    phone = _norm_phone(payload.get("phone"))
    action = payload.get("action")
    if not phone or action not in ("force_link", "dismiss"):
        raise HTTPException(status_code=400, detail="phone and a valid action are required")
    if action == "dismiss":
        await db.parent_invite_reviews.update_one({"institution_id": iid, "phone": phone},
                                                  {"$set": {"status": "dismissed", "by": user.get("email"), "at": now_iso()}}, upsert=True)
        await audit(user, "invite_review_dismiss", "parent_invite_reviews", phone, None, iid)
        return {"ok": True, "status": "dismissed"}
    sids = payload.get("student_ids") or []
    students = await db.students.find({"institution_id": iid, "id": {"$in": sids}}, {"_id": 0}).to_list(100)
    # bypass collision guard by pre-dismissing, run invites, then record resolved
    await db.parent_invite_reviews.update_one({"institution_id": iid, "phone": phone},
                                              {"$set": {"status": "dismissed", "by": user.get("email"), "at": now_iso()}}, upsert=True)
    res = await _run_parent_invites(iid, students, phase58.parse_channels(payload), user)
    await db.parent_invite_reviews.update_one({"institution_id": iid, "phone": phone}, {"$set": {"status": "resolved"}})
    return {"ok": True, "status": "force_linked", "result": res}


async def _issue_setup_code(iid, s, school_name, actor_email):
    """One live code per student: issuing a new one invalidates the previous unused code."""
    while True:  # globally unique among live codes (the code alone identifies the student)
        code = "".join(secrets.choice(SETUP_CODE_ALPHABET) for _ in range(8))
        if not await db.parent_setup_codes.find_one({"code_hash": _hash_code(code), "used": False}):
            break
    await db.parent_setup_codes.delete_many({"institution_id": iid, "student_id": s["id"], "used": False})
    await db.parent_setup_codes.insert_one({"id": str(uuid.uuid4()), "institution_id": iid, "student_id": s["id"],
                                            "code_hash": _hash_code(code), "used": False,
                                            "expires_at": (datetime.now(timezone.utc) + timedelta(days=14)).isoformat(),
                                            "created_by": actor_email, "created_at": now_iso()})
    return {"student_id": s["id"], "code": code, "student_name": f"{s.get('first_name','')} {s.get('last_name','')}".strip(),
            "admission_no": s.get("admission_no"), "class": (s.get("class_name") or "") + (f" {s.get('section')}" if s.get("section") else ""),
            "school_name": school_name, "expires_in_days": 14}


async def _school_logo_src(iid):
    inst = await db.institutions.find_one({"id": iid}, {"_id": 0, "logo_path": 1, "logo_url": 1, "slug": 1, "domain": 1}) or {}
    if inst.get("logo_path"):
        return (f"{os.environ['PUBLIC_BASE_URL']}/api/public/institution-logo"
                f"?slug={inst.get('slug') or ''}&domain={inst.get('domain') or ''}")
    return inst.get("logo_url")


@api.post("/students/{student_id}/setup-code")
async def create_setup_code(student_id: str, user: dict = Depends(require_admin_or_principal)):
    """Single-use, short-lived, hashed code for the printable paper invite."""
    iid = user["institution_id"]
    s = await db.students.find_one({"id": student_id, "institution_id": iid}, {"_id": 0})
    if not s:
        raise HTTPException(status_code=404, detail="Student not found")
    await guard_principal_class(user, s.get("class_name"))
    school = await db.institutions.find_one({"id": iid}, {"_id": 0, "name": 1})
    slip = await _issue_setup_code(iid, s, (school or {}).get("name"), user.get("email"))
    await audit(user, "parent_setup_code", "parent_setup_codes", student_id, None, iid)
    return {**slip, "logo_src": await _school_logo_src(iid)}


@api.post("/students/setup-codes/bulk")
async def bulk_setup_codes(payload: dict = Body(...), user: dict = Depends(require_admin_or_principal)):
    """Paper slips for every enrolled no-phone student (without a linked parent) in the chosen classes."""
    iid = user["institution_id"]
    students = await _invite_scope_students(iid, user, payload)
    linked = await _linked_student_ids(iid)
    targets = [s for s in students if not _norm_phone(s.get("guardian_phone")) and s["id"] not in linked]
    targets.sort(key=lambda s: (s.get("class_name") or "", s.get("section") or "", s.get("first_name") or ""))
    school = await db.institutions.find_one({"id": iid}, {"_id": 0, "name": 1})
    slips = [await _issue_setup_code(iid, s, (school or {}).get("name"), user.get("email")) for s in targets]
    await audit(user, "parent_setup_codes_bulk", "parent_setup_codes", None, f"{len(slips)} slips", iid)
    return {"slips": slips, "count": len(slips), "logo_src": await _school_logo_src(iid)}


async def _class_invite_state(iid, class_names):
    """Per-student onboarding state from invited (phone-keyed) accounts."""
    parents = await db.users.find({"institution_id": iid, "role": "parent"},
                                  {"_id": 0, "id": 1, "student_ids": 1, "invited": 1, "must_change_password": 1, "phone": 1, "name": 1}).to_list(50000)
    by_student = {}
    for p in parents:
        for sid in p.get("student_ids") or []:
            by_student.setdefault(sid, []).append(p)
    q = {"institution_id": iid, "enrollment_status": "enrolled", "class_name": {"$in": list(class_names)}}
    rows = []
    async for s in db.students.find(q, {"_id": 0, "id": 1, "class_name": 1, "guardian_phone": 1}):
        ps = by_student.get(s["id"], [])
        inv = [p for p in ps if p.get("invited")]
        if inv:
            state = "completed" if any(not p.get("must_change_password") for p in inv) else "pending"
        elif ps:
            state = "linked_other"
        elif _norm_phone(s.get("guardian_phone")):
            state = "not_invited"
        else:
            state = "no_phone"
        rows.append({"student_id": s["id"], "class_name": s["class_name"], "state": state, "invited_parents": inv})
    return rows


@api.get("/students/invite-progress")
async def invite_progress(user: dict = Depends(require_admin_or_principal)):
    iid = user["institution_id"]
    allowed = await _comm_scope_class_names(user)
    classes = await db.classes.find({"institution_id": iid}, {"_id": 0, "id": 1, "name": 1, "grade_level": 1}).to_list(5000)
    if allowed is not None:
        classes = [c for c in classes if c["name"] in allowed]
    rows = await _class_invite_state(iid, {c["name"] for c in classes})
    today = now_iso()[:10]
    sent_today = {r["class_id"] async for r in db.parent_invite_reminders.find({"institution_id": iid, "date": today}, {"_id": 0, "class_id": 1})}
    out = []
    for c in classes:
        mine = [r for r in rows if r["class_name"] == c["name"]]
        cnt = {k: sum(1 for r in mine if r["state"] == k) for k in ("completed", "pending", "not_invited", "no_phone", "linked_other")}
        out.append({"class_id": c["id"], "class_name": c["name"], "enrolled": len(mine),
                    "invited": cnt["completed"] + cnt["pending"], "setup_completed": cnt["completed"],
                    "pending": cnt["pending"], "not_invited": cnt["not_invited"], "no_phone": cnt["no_phone"],
                    "linked_other": cnt["linked_other"], "reminder_sent_today": c["id"] in sent_today})
    out.sort(key=lambda r: (int(re.search(r"\d+", r["class_name"]).group()) if re.search(r"\d+", r["class_name"]) else 999, r["class_name"]))
    return {"classes": out}


@api.post("/students/invite-reminder")
async def invite_reminder(payload: dict = Body(...), user: dict = Depends(require_admin_or_principal)):
    """Re-send the setup link to parents invited but not yet set up — once per class per day."""
    iid = user["institution_id"]
    cls = await db.classes.find_one({"institution_id": iid, "id": payload.get("class_id")}, {"_id": 0, "id": 1, "name": 1})
    if not cls:
        raise HTTPException(status_code=404, detail="Class not found")
    await guard_principal_class(user, cls["name"])
    channels = phase58.parse_channels(payload)
    today = now_iso()[:10]
    if await db.parent_invite_reminders.find_one({"institution_id": iid, "class_id": cls["id"], "date": today}):
        return {"ok": False, "code": "already_sent_today", "sent": 0,
                "message": f"A reminder was already sent to {cls['name']} today"}
    pending = {}
    for r in await _class_invite_state(iid, {cls["name"]}):
        if r["state"] == "pending":
            for p in r["invited_parents"]:
                pending[p["id"]] = p
    school = await db.institutions.find_one({"id": iid}, {"_id": 0, "name": 1})
    sent, results = 0, []
    for p in pending.values():
        full = await db.users.find_one({"id": p["id"]}, {"_id": 0, "password_hash": 0}) or p
        kids = [f"{k.get('first_name','')} {k.get('last_name','')}".strip() for k in
                await db.students.find({"institution_id": iid, "id": {"$in": full.get("student_ids") or []}}, {"_id": 0, "first_name": 1, "last_name": 1}).to_list(20)]
        per = await phase58.send_invite_multi(iid, (school or {}).get("name"), full, channels, kids)
        status = phase58.overall(per)
        sent += status == "sent"
        results.append({"parent_id": p["id"], "name": p.get("name"), "channels": per})
        await db.parent_invites.insert_one({"id": str(uuid.uuid4()), "institution_id": iid, "student_id": None,
                                            "parent_user_id": p["id"], "phone": p.get("phone"), "status": f"reminder_{status}",
                                            "channel": ",".join(channels), "channels": per, "sent_at": now_iso()})
    await db.parent_invite_reminders.insert_one({"id": str(uuid.uuid4()), "institution_id": iid, "class_id": cls["id"],
                                                 "class_name": cls["name"], "date": today, "sent": sent,
                                                 "pending_parents": len(pending), "by": user.get("email"), "at": now_iso()})
    await audit(user, "invite_reminder", "parent_invites", cls["id"], f"{sent} reminders · {cls['name']}", iid)
    ritems = []
    for r in results:
        per = r["channels"]
        st_ = phase58.overall(per)
        chan = ", ".join(f"{k}: {v.replace('skipped_', 'no ').replace('_', ' ')}" for k, v in per.items() if k in phase58.INVITE_CHANNELS)
        ritems.append(phase59.item(r["parent_id"], r["name"], {"sent": "sent", "failed": "failed"}.get(st_, "skipped"),
                                   f"Reminder {st_} ({chan})", st_, cls["name"], phase59.fix("open_parent", r["parent_id"])))
    run = await phase59.save_run(user, "invite_reminder", f"Invite reminders · {cls['name']}", ritems, ref_id=cls["id"])
    return {"ok": True, "sent": sent, "pending_parents": len(pending), "class_name": cls["name"], "results": results, **run}


# ---- Public (unauthenticated) parent onboarding ----
@api.get("/public/parent-setup/{token}")
async def public_parent_setup_resolve(token: str):
    data = _verify_secure_link(token)
    if not data or not str(data.get("ref", "")).startswith("psetup:"):
        raise HTTPException(status_code=400, detail="This invite link is invalid or has expired")
    uid = data["ref"].split("psetup:", 1)[1]
    u = await db.users.find_one({"id": uid, "role": "parent"}, {"_id": 0})
    if not u:
        raise HTTPException(status_code=404, detail="Account not found")
    school = await db.institutions.find_one({"id": u["institution_id"]}, {"_id": 0, "name": 1})
    kids = await db.students.find({"id": {"$in": u.get("student_ids") or []}}, {"_id": 0, "first_name": 1, "last_name": 1, "class_name": 1, "section": 1}).to_list(50)
    return {"school_name": (school or {}).get("name"), "parent_name": u.get("name"),
            "login_email": u.get("email"), "phone": u.get("phone"), "needs_password": bool(u.get("must_change_password")),
            "children": [{"name": f"{k.get('first_name','')} {k.get('last_name','')}".strip(),
                          "class": (k.get("class_name") or "") + (f" {k.get('section')}" if k.get("section") else "")} for k in kids]}


@api.post("/public/parent-setup/{token}")
async def public_parent_setup_complete(token: str, response: Response, payload: dict = Body(...)):
    data = _verify_secure_link(token)
    if not data or not str(data.get("ref", "")).startswith("psetup:"):
        raise HTTPException(status_code=400, detail="This invite link is invalid or has expired")
    uid = data["ref"].split("psetup:", 1)[1]
    u = await db.users.find_one({"id": uid, "role": "parent"})
    if not u:
        raise HTTPException(status_code=404, detail="Account not found")
    pw = payload.get("password") or ""
    if len(pw) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
    await db.users.update_one({"id": uid}, {"$set": {"password_hash": hash_password(pw), "must_change_password": False}})
    u["id"] = uid
    access, refresh = make_tokens(u)
    if response is not None:
        set_auth_cookies(response, access, refresh)
    return await public_user(u)


@api.post("/public/parent-register")
async def public_parent_register(request: Request, response: Response, payload: dict = Body(...)):
    """Paper-slip self-registration: the one-time code identifies the student; admission_no optional."""
    _rate_limit_ip(request)
    adm = (payload.get("admission_no") or "").strip()
    code = _norm_setup_code(payload.get("code"))
    phone = _norm_phone(payload.get("phone"))
    pw = payload.get("password") or ""
    if not (code and phone):
        raise HTTPException(status_code=400, detail="Setup code and phone are required")
    if len(pw) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
    rec = await db.parent_setup_codes.find_one({"code_hash": _hash_code(code), "used": False})
    student = rec and await db.students.find_one({"id": rec["student_id"], "institution_id": rec["institution_id"]}, {"_id": 0})
    if not student or (adm and adm.upper() != str(student.get("admission_no") or "").strip().upper()):
        raise HTTPException(status_code=400, detail="Please check the details and try again")
    iid = student["institution_id"]
    if datetime.now(timezone.utc) > datetime.fromisoformat(rec["expires_at"]):
        raise HTTPException(status_code=400, detail="This code has expired — ask the school for a new slip")
    school = await db.institutions.find_one({"id": iid}, {"_id": 0, "name": 1, "slug": 1, "code": 1})
    existing = await _parent_by_phone(iid, phone)
    if existing:
        await db.users.update_one({"id": existing["id"]}, {"$addToSet": {"student_ids": student["id"]}})
        uid = existing["id"]
        await db.users.update_one({"id": uid}, {"$set": {"password_hash": hash_password(pw), "must_change_password": False}})
        u = await db.users.find_one({"id": uid})
    else:
        uid = str(uuid.uuid4())
        login_email = f"p{phone}@{((school or {}).get('slug') or (school or {}).get('code') or 'sch').lower()}.parent.invite"
        await db.users.insert_one({"id": uid, "name": payload.get("name") or student.get("guardian_name") or "Parent",
                                   "email": login_email, "phone": phone, "password_hash": hash_password(pw),
                                   "role": "parent", "student_ids": [student["id"]], "institution_id": iid,
                                   "status": "active", "must_change_password": False, "invited": True, "created_at": now_iso()})
        u = await db.users.find_one({"id": uid})
    await db.parent_setup_codes.update_one({"id": rec["id"]}, {"$set": {"used": True, "used_at": now_iso()}})
    await db.parent_invites.insert_one({"id": str(uuid.uuid4()), "institution_id": iid, "student_id": student["id"],
                                        "parent_user_id": uid, "phone": phone, "status": "self_registered",
                                        "channel": "paper", "sent_at": now_iso()})
    access, refresh = make_tokens(u)
    if response is not None:
        set_auth_cookies(response, access, refresh)
    return await public_user(u)




async def _student_snapshot(iid, student):
    sid = student["id"]
    results = []
    async for m in db.marks.find({"student_id": sid}):
        a = await db.assessments.find_one({"id": m["assessment_id"], "institution_id": iid, "status": "published"}, {"_id": 0})
        if a:
            results.append({"assessment": a.get("name"), "subject": a.get("subject"),
                            "score": m.get("score"), "max_marks": a.get("max_marks"),
                            "date": a.get("exam_date") or a.get("date"), "created_at": a.get("created_at")})
    present, total, history = 0, 0, []
    async for sh in db.attendance.find({"institution_id": iid, "class_name": student.get("class_name"), "section": student.get("section")}):
        ent = sh.get("entries") or {}
        if sid in ent:
            total += 1
            if str(ent[sid]).lower() in ("present", "p"):
                present += 1
            history.append({"date": sh.get("date"), "status": ent[sid]})
    history.sort(key=lambda x: x["date"] or "", reverse=True)
    achievements = await db.achievements.find({"institution_id": iid, "student_id": sid}, {"_id": 0}) \
        .sort([("date", -1), ("created_at", -1)]).to_list(100)
    leader_role = None
    sec = await db.sections.find_one({"institution_id": iid, "class_name": student.get("class_name"), "name": student.get("section")})
    if sec:
        if sec.get("class_leader_id") == sid:
            leader_role = "class_leader"
        elif sec.get("second_leader_id") == sid:
            leader_role = "second_leader"
    return {"student": {k: v for k, v in student.items() if k != "_id"},
            "attendance": {"present": present, "total": total, "pct": round(present / total * 100) if total else None},
            "attendance_history": history[:30], "results": results,
            "achievements": achievements, "leader_role": leader_role}


@api.get("/parent/children")
async def parent_children(user: dict = Depends(require_roles("parent"))):
    iid = user["institution_id"]
    kids = await db.students.find({"institution_id": iid, "id": {"$in": user.get("student_ids") or []}}, {"_id": 0}).to_list(20)
    inst = await db.institutions.find_one({"id": iid}, {"_id": 0, "name": 1, "portal_name": 1, "primary_color": 1, "logo_url": 1, "logo_path": 1, "domain": 1}) or {}
    inst["has_logo"] = bool(inst.pop("logo_path", None))
    return {"children": kids, "branding": inst}


@api.get("/parent/child/{student_id}")
async def parent_child_detail(student_id: str, user: dict = Depends(require_roles("parent"))):
    if student_id not in (user.get("student_ids") or []):
        raise HTTPException(status_code=403, detail="This student is not linked to your account")
    student = await db.students.find_one({"id": student_id, "institution_id": user["institution_id"]}, {"_id": 0})
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    return await _student_snapshot(user["institution_id"], student)


# ================= Phase 16 — OTP VERIFICATION + PARENT-CHILD LINKING =================
# Email channel ACTIVE (Emergent-managed Resend); SMS (Twilio) remains a documented stub.
# Codes are 6 digits, HASHED at rest (sha256 + JWT_SECRET pepper), 10-min expiry, max 5 attempts,
# 60s resend cooldown. No code is ever returned in responses (except a documented test hook).

from html import escape as _html_escape  # noqa: E402

EMAIL_BASE_URL = "https://integrations.emergentagent.com"  # constant — survives deployment
EMAIL_KEY = os.environ.get("EMERGENT_EMAIL_KEY", "")
EMAIL_FROM_NAME = os.environ.get("EMAIL_FROM_NAME", "School")
OTP_TEST_MODE = os.environ.get("OTP_TEST_MODE") == "1"  # test-only: expose dev_code (never in prod)
OTP_TTL_SECONDS = 600
OTP_MAX_ATTEMPTS = 5
OTP_COOLDOWN_SECONDS = 60
_otp_ip_hits: dict = {}


class _EmailScan(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags, self.urls, self.anchors = set(), [], []
        self._href, self._text = None, []

    def handle_starttag(self, tag, attrs):
        self.tags.add(tag.lower())
        self.urls += [v for k, v in attrs if k.lower() in ("href", "src") and v]
        if tag.lower() == "a":
            self._href = dict((k.lower(), v) for k, v in attrs).get("href")
            self._text = []

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self._href is not None:
            self.anchors.append((self._href, "".join(self._text)))
            self._href, self._text = None, []


def _assert_safe_email(subject: str, html: str) -> None:
    scan = _EmailScan()
    scan.feed(html)
    if scan.tags & {"form", "input", "textarea", "select"}:
        raise ValueError("No forms or input fields in email (G2)")
    for url in scan.urls:
        low = url.strip().lower()
        if low.startswith(("mailto:", "tel:", "cid:", "#")):
            continue
        if not low.startswith("https://"):
            raise ValueError(f"Email links/assets must be absolute https: {url!r} (G3)")
        host = urlparse(low).hostname or ""
        try:
            ipaddress.ip_address(host)
            raise ValueError("numeric host")
        except ValueError:
            pass
        if not host or "xn--" in host or urlparse(low).username is not None:
            raise ValueError(f"Unsafe URL in email: {url!r} (G3)")


class EmailSendError(Exception):
    def __init__(self, reason: str):
        self.reason = reason  # "undeliverable" | "provider_error"


async def send_email(*, to: str, subject: str, html: str, from_name: str | None = None) -> str | None:
    _assert_safe_email(subject, html)
    if not EMAIL_KEY:
        logger.warning("EMERGENT_EMAIL_KEY not set — email not sent")
        return None
    payload = {"to": [to], "subject": subject, "html": html, "from_name": from_name or EMAIL_FROM_NAME}
    try:
        # Short timeout so an OTP request can never hang behind a slow provider (proxy would 5xx).
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(f"{EMAIL_BASE_URL}/api/v1/email/send",
                                     headers={"X-Email-Key": EMAIL_KEY}, json=payload)
        resp.raise_for_status()
        return resp.json().get("id")
    except httpx.HTTPStatusError as e:
        body = (e.response.text or "").lower()
        reason = ("undeliverable" if (e.response.status_code == 422 or "undeliver" in body)
                  else "rate_limited" if (e.response.status_code == 429 or "rate" in body) else "provider_error")
        logger.error("Email send failed (%s): %s", reason, body[:200])
        raise EmailSendError(reason)
    except Exception as e:  # noqa: BLE001
        logger.error("Email send failed: %s", e)
        raise EmailSendError("provider_error")


def _otp_code_html(code: str, reason: str) -> str:
    return (f'<table role="presentation" width="100%"><tr><td style="padding:24px;'
            f'font-family:Arial,sans-serif;color:#111">'
            f'<p>Your {_html_escape(EMAIL_FROM_NAME)} verification code for {_html_escape(reason)} is:</p>'
            f'<p style="font-size:30px;font-weight:bold;letter-spacing:6px;margin:12px 0">{_html_escape(code)}</p>'
            f'<p style="color:#555">This code expires in 10 minutes. If you didn\'t request it, ignore this email.</p>'
            f'<p style="font-size:12px;color:#888">Sent by {_html_escape(EMAIL_FROM_NAME)}. '
            f'We never ask for your password by email.</p></td></tr></table>')


def _hash_code(code: str) -> str:
    return hashlib.sha256(f"{code}:{os.environ['JWT_SECRET']}".encode()).hexdigest()


def _rate_limit_ip(request: Request):
    ip = (request.client.host if request.client else "unknown")
    now = datetime.now(timezone.utc).timestamp()
    hits = [t for t in _otp_ip_hits.get(ip, []) if now - t < 60]
    if len(hits) >= 20:
        raise HTTPException(status_code=429, detail="Too many requests — please slow down")
    hits.append(now)
    _otp_ip_hits[ip] = hits


class VerifyRequest(BaseModel):
    purpose: str  # phone_verify | parent_link
    phone: Optional[str] = None
    admission_no: Optional[str] = None
    delivery_email: Optional[EmailStr] = None  # optional personal email to send the code to


class VerifyConfirm(BaseModel):
    purpose: str
    code: str
    phone: Optional[str] = None
    admission_no: Optional[str] = None


class PhoneUpdate(BaseModel):
    phone: str


class PersonalEmailUpdate(BaseModel):
    personal_email: EmailStr


def _delivery_email(user) -> str:
    """Where OTP codes go: the saved personal_email if present, else the account/login email."""
    return (user.get("personal_email") or "").strip().lower() or user["email"]


async def _resolve_verify_target(user, body: VerifyRequest):
    """Returns (target_key, reason) or raises a GENERIC error (no enumeration leak)."""
    iid = user["institution_id"]
    if body.purpose == "phone_verify":
        phone = (body.phone or user.get("phone") or "").strip()
        if not phone:
            raise HTTPException(status_code=400, detail="Add a phone number first")
        return f"phone:{phone}", "phone verification"
    if body.purpose == "parent_link":
        if user["role"] != "parent":
            raise HTTPException(status_code=403, detail="Only a parent account can link a child")
        phone = (body.phone or "").strip()
        adm = (body.admission_no or "").strip()
        student = await db.students.find_one({"institution_id": iid, "admission_no": adm}, {"_id": 0}) if adm else None
        # generic failure for any mismatch — no info leak
        if not student or (str(student.get("guardian_phone") or "").strip() != phone) or not phone:
            raise HTTPException(status_code=400, detail="Please check the details and try again")
        return f"link:{student['id']}", "linking your child"
    raise HTTPException(status_code=400, detail="Unknown verification purpose")


@api.post("/profile/phone")
async def set_phone(body: PhoneUpdate, user: dict = Depends(require_roles("teacher"))):
    phone = (body.phone or "").strip()
    await db.users.update_one({"id": user["id"]}, {"$set": {"phone": phone, "phone_verified": False}})
    await audit(user, "update_phone", "users", user["id"], None)
    return {"message": "Phone saved — verify it to confirm", "phone": phone, "phone_verified": False}


@api.post("/profile/personal-email")
async def set_personal_email(body: PersonalEmailUpdate, user: dict = Depends(require_roles("teacher"))):
    email = str(body.personal_email).strip().lower()
    await db.users.update_one({"id": user["id"]}, {"$set": {"personal_email": email, "personal_email_verified": False}})
    await audit(user, "set_personal_email", "users", user["id"], email)
    return {"message": "Personal email saved — verify it to confirm", "personal_email": email, "personal_email_verified": False}


@api.post("/verify/request")
async def verify_request(body: VerifyRequest, request: Request, user: dict = Depends(get_current_user)):
    _rate_limit_ip(request)
    target, reason = await _resolve_verify_target(user, body)
    # Resolve delivery email: explicit override saves as (unverified) personal_email, else default.
    delivery = _delivery_email(user)
    if body.delivery_email:
        delivery = str(body.delivery_email).strip().lower()
        if delivery != (user.get("personal_email") or "").strip().lower():
            await db.users.update_one({"id": user["id"]},
                                      {"$set": {"personal_email": delivery, "personal_email_verified": False}})
            await audit(user, "set_personal_email", "users", user["id"], delivery)
    now = datetime.now(timezone.utc)
    prev = await db.otp_codes.find_one({"user_id": user["id"], "purpose": body.purpose, "target": target, "verified": False})
    if prev and prev.get("last_sent_at"):
        try:
            elapsed = (now - datetime.fromisoformat(prev["last_sent_at"])).total_seconds()
            if elapsed < OTP_COOLDOWN_SECONDS:
                raise HTTPException(status_code=429, detail=f"Please wait {int(OTP_COOLDOWN_SECONDS - elapsed)}s before requesting another code")
        except (ValueError, TypeError):
            pass
    code = f"{secrets.randbelow(1000000):06d}"
    doc = {"id": str(uuid.uuid4()), "institution_id": user["institution_id"], "user_id": user["id"],
           "purpose": body.purpose, "target": target, "code_hash": _hash_code(code), "delivery_email": delivery,
           "attempts": 0, "verified": False, "created_at": now.isoformat(),
           "expires_at": (now + timedelta(seconds=OTP_TTL_SECONDS)).isoformat(), "last_sent_at": now.isoformat()}
    await db.otp_codes.delete_many({"user_id": user["id"], "purpose": body.purpose, "target": target})
    await db.otp_codes.insert_one(dict(doc))
    try:
        await send_email(to=delivery, subject=f"Your {EMAIL_FROM_NAME} verification code", html=_otp_code_html(code, reason))
    except EmailSendError as e:
        # Never return 5xx (Cloudflare rewraps it into generic "Bad gateway" HTML). Drop the unsent
        # code and return a structured 200 the OTP dialog can show inline, keeping the field editable.
        await db.otp_codes.delete_many({"user_id": user["id"], "purpose": body.purpose, "target": target})
        return {"ok": False, "sent": False, "reason": e.reason,
                "message": "Couldn't send the code to that address — check it or use a different email"}
    await audit(user, "otp_request", "otp_codes", doc["id"], body.purpose)
    resp = {"ok": True, "sent": True, "message": f"We emailed a 6-digit code to {delivery}", "sent_to": delivery}
    if OTP_TEST_MODE:
        resp["dev_code"] = code
    return resp


@api.post("/verify/confirm")
async def verify_confirm(body: VerifyConfirm, request: Request, user: dict = Depends(get_current_user)):
    _rate_limit_ip(request)
    target, _ = await _resolve_verify_target(user, VerifyRequest(purpose=body.purpose, phone=body.phone, admission_no=body.admission_no))
    rec = await db.otp_codes.find_one({"user_id": user["id"], "purpose": body.purpose, "target": target, "verified": False})
    if not rec:
        raise HTTPException(status_code=400, detail="Request a code first")
    if datetime.now(timezone.utc) > datetime.fromisoformat(rec["expires_at"]):
        await db.otp_codes.delete_one({"id": rec["id"]})
        raise HTTPException(status_code=400, detail="That code has expired — request a new one")
    if rec["attempts"] >= OTP_MAX_ATTEMPTS:
        raise HTTPException(status_code=429, detail="Too many attempts — request a new code")
    if _hash_code(body.code.strip()) != rec["code_hash"]:
        await db.otp_codes.update_one({"id": rec["id"]}, {"$inc": {"attempts": 1}})
        raise HTTPException(status_code=400, detail="Incorrect code")
    await db.otp_codes.update_one({"id": rec["id"]}, {"$set": {"verified": True}})
    # If the code was delivered to a personal (non-login) email, that email is now verified.
    dmail = (rec.get("delivery_email") or "").strip().lower()
    if dmail and dmail != (user["email"] or "").strip().lower():
        await db.users.update_one({"id": user["id"]},
                                  {"$set": {"personal_email": dmail, "personal_email_verified": True}})
        await audit(user, "personal_email_verified", "users", user["id"], dmail)
    if body.purpose == "phone_verify":
        phone = target.split("phone:", 1)[1]
        await db.users.update_one({"id": user["id"]}, {"$set": {"phone": phone, "phone_verified": True}})
        await audit(user, "phone_verified", "users", user["id"], None)
        return {"message": "Phone verified", "phone_verified": True}
    if body.purpose == "parent_link":
        student_id = target.split("link:", 1)[1]
        if student_id in (user.get("student_ids") or []):
            raise HTTPException(status_code=400, detail="This child is already linked to your account")
        await db.users.update_one({"id": user["id"]}, {"$addToSet": {"student_ids": student_id}})
        await audit(user, "parent_self_link", "users", user["id"], student_id)
        return {"message": "Child linked", "linked": True}
    return {"message": "Verified"}


@api.post("/parent/unlink/{student_id}")
async def parent_self_unlink(student_id: str, user: dict = Depends(require_roles("parent"))):
    if student_id not in (user.get("student_ids") or []):
        raise HTTPException(status_code=404, detail="That child is not linked to your account")
    await db.users.update_one({"id": user["id"]}, {"$pull": {"student_ids": student_id}})
    await audit(user, "parent_self_unlink", "users", user["id"], student_id)
    return {"message": "Child unlinked"}


@api.post("/students/{student_id}/unlink-parent")
async def admin_unlink_parent(student_id: str, payload: dict = Body(...),
                              user: dict = Depends(require_admin_or_principal)):
    iid = user["institution_id"]
    student = await db.students.find_one({"id": student_id, "institution_id": iid})
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    await guard_principal_class(user, student.get("class_name"))
    email = (payload.get("email") or "").strip().lower()
    parent = await db.users.find_one({"email": email, "role": "parent", "institution_id": iid})
    if not parent or student_id not in (parent.get("student_ids") or []):
        raise HTTPException(status_code=404, detail="That parent is not linked to this student")
    await db.users.update_one({"id": parent["id"]}, {"$pull": {"student_ids": student_id}})
    await audit(user, "unlink_parent", "users", parent["id"], email)
    return {"message": f"Unlinked {email} from this student"}


@api.get("/students/{student_id}/parents")
async def list_student_parents(student_id: str, user: dict = Depends(require_admin_or_principal)):
    iid = user["institution_id"]
    student = await db.students.find_one({"id": student_id, "institution_id": iid})
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    await guard_principal_class(user, student.get("class_name"))
    parents = await db.users.find({"institution_id": iid, "role": "parent", "student_ids": student_id},
                                  {"_id": 0, "id": 1, "name": 1, "email": 1}).to_list(50)
    return {"parents": parents}


@api.get("/students/{student_id}/profile")
async def student_profile_view(student_id: str, user: dict = Depends(require_admin_or_principal)):
    """Full student profile for admin / in-scope unit principal (403 outside scope). Aggregates
    the snapshot (attendance/results/achievements) + linked parents + upcoming published exams +
    current enrollment so the UI needs a single call."""
    iid = user["institution_id"]
    student = await db.students.find_one({"id": student_id, "institution_id": iid}, {"_id": 0, "password_hash": 0})
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    await guard_principal_class(user, student.get("class_name"))  # unit principal scope → 403 outside
    snap = await _student_snapshot(iid, student)
    parents = await db.users.find({"institution_id": iid, "role": "parent", "student_ids": student_id},
                                  {"_id": 0, "id": 1, "name": 1, "email": 1}).to_list(50)
    cn, sec = student.get("class_name"), student.get("section")
    exams = []
    if cn:
        pub = {e["id"]: e for e in await db.exams.find({"institution_id": iid, "status": "published"}, {"_id": 0}).to_list(500)}
        async for e in db.exam_entries.find(
                {"institution_id": iid, "exam_id": {"$in": list(pub.keys())}, "class_name": cn,
                 "status": {"$ne": "cancelled"},
                 "$or": [{"section": {"$in": ["", None]}}, {"section": sec}]}, {"_id": 0}):
            ex = pub.get(e["exam_id"], {})
            exams.append({"exam_name": ex.get("name"), "subject": e["subject"], "date": e["date"],
                          "start": e["start"], "end": e["end"], "room": e.get("room") or "", "status": e["status"]})
        exams.sort(key=lambda r: (r["date"], r["start"]))
    enr = await db.enrollments.find_one(
        {"institution_id": iid, "student_id": student_id}, {"_id": 0}, sort=[("created_at", -1)])
    return {"student": student, "attendance": snap["attendance"], "attendance_history": snap["attendance_history"],
            "results": snap["results"], "achievements": snap["achievements"], "leader_role": snap["leader_role"],
            "parents": parents, "upcoming_exams": exams, "enrollment": enr}


# ================= Phase 21 — HOMEWORK MODULE (core loop) =================
# Collections: homework, homework_submissions. Attachments live in object storage under
# lnmo/homework/... (authenticated read). Clean timestamps/flags (late, status, version,
# submitted_at, verified_at) are captured so a FUTURE monthly report can aggregate them.

HW_ATTACH_TYPES = {
    "application/pdf": "pdf", "image/jpeg": "jpg", "image/png": "png", "image/webp": "webp",
    "application/msword": "doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
}
HW_MAX_MB = 10
HW_MAX_FILES = 5


class HomeworkCreate(BaseModel):
    class_name: str
    section: str
    subject: str
    title: str
    instructions: Optional[str] = ""
    due_date: str  # ISO date/datetime


class HomeworkUpdate(BaseModel):
    title: Optional[str] = None
    instructions: Optional[str] = None
    due_date: Optional[str] = None


class VerifyVerdict(BaseModel):
    verdict: str  # verified | redo
    feedback: Optional[str] = ""


async def _teaches_subject(iid, teacher_id, class_name, section, subject):
    """True if the teacher has an assignment for this class+subject (section-specific or all sections)."""
    q = {"institution_id": iid, "teacher_id": teacher_id, "class_name": class_name, "subject": subject}
    a = await db.teacher_assignments.find_one({**q, "$or": [{"section": section}, {"section": {"$in": ["", None]}}]})
    return bool(a)


async def _student_parent_ids(iid, student_id):
    return [u["id"] for u in await db.users.find(
        {"institution_id": iid, "role": "parent", "student_ids": student_id}, {"_id": 0, "id": 1}).to_list(50)]


async def _class_section_student_user_ids(iid, class_name, section):
    """(student_user_ids, student_ids) for enrolled students of a class+section."""
    students = await db.students.find(
        {"institution_id": iid, "class_name": class_name, "section": section, "enrollment_status": "enrolled"},
        {"_id": 0, "id": 1}).to_list(2000)
    sids = [s["id"] for s in students]
    users = await db.users.find({"institution_id": iid, "role": "student", "student_id": {"$in": sids}},
                                {"_id": 0, "id": 1, "student_id": 1}).to_list(2000)
    return users, sids


def _hw_public(hw):
    return {k: hw[k] for k in hw if k != "_id"}


@api.post("/homework")
async def create_homework(body: HomeworkCreate, user: dict = Depends(require_roles("teacher", "institution_admin"))):
    iid = user["institution_id"]
    if user["role"] == "teacher" and not await _teaches_subject(iid, user["id"], body.class_name, body.section, body.subject):
        raise HTTPException(status_code=403, detail="You can only set homework for a class & subject you are assigned to teach")
    if user["role"] == "institution_admin":
        await guard_principal_class(user, body.class_name)
    year = await _active_year_name(iid)
    hw = {"id": str(uuid.uuid4()), "institution_id": iid, "academic_year": year,
          "class_name": body.class_name, "section": body.section, "subject": body.subject,
          "teacher_id": user["id"], "title": body.title.strip(), "instructions": (body.instructions or "").strip(),
          "attachments": [], "due_date": body.due_date, "status": "open", "created_at": now_iso()}
    await db.homework.insert_one(dict(hw))
    await audit(user, "create_homework", "homework", hw["id"], hw["title"])
    # Bell: notify every enrolled student of the class+section + their linked parents.
    users, sids = await _class_section_student_user_ids(iid, body.class_name, body.section)
    title = f"New homework: {hw['title']}"
    body_txt = f"{body.subject} · {body.class_name} {body.section} · due {body.due_date[:10]}"
    for su in users:
        await _notify(iid, su["id"], "homework_new", title, body_txt, hw["id"])
    for sid in sids:
        for pid in await _student_parent_ids(iid, sid):
            await _notify(iid, pid, "homework_new", title, body_txt, hw["id"])
    return {"homework": _hw_public(hw)}


async def _get_own_homework(iid, hw_id, user):
    hw = await db.homework.find_one({"id": hw_id, "institution_id": iid}, {"_id": 0})
    if not hw:
        raise HTTPException(status_code=404, detail="Homework not found")
    if user["role"] != "institution_admin" and hw["teacher_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="You can only manage your own homework")
    if user["role"] == "institution_admin":
        await guard_principal_class(user, hw["class_name"])
    return hw


@api.put("/homework/{hw_id}")
async def update_homework(hw_id: str, body: HomeworkUpdate, user: dict = Depends(require_roles("teacher", "institution_admin"))):
    iid = user["institution_id"]
    hw = await _get_own_homework(iid, hw_id, user)
    if hw["status"] != "open":
        raise HTTPException(status_code=400, detail="Reopen the homework before editing it")
    upd = {k: v for k, v in body.dict().items() if v is not None}
    if upd:
        await db.homework.update_one({"id": hw_id}, {"$set": upd})
    await audit(user, "update_homework", "homework", hw_id, hw["title"])
    return {"message": "Homework updated"}


@api.delete("/homework/{hw_id}")
async def delete_homework(hw_id: str, user: dict = Depends(require_roles("teacher", "institution_admin"))):
    iid = user["institution_id"]
    hw = await _get_own_homework(iid, hw_id, user)
    if await db.homework_submissions.count_documents({"homework_id": hw_id}) > 0:
        raise HTTPException(status_code=409, detail="This homework already has submissions and can't be deleted")
    await db.homework.delete_one({"id": hw_id})
    await audit(user, "delete_homework", "homework", hw_id, hw["title"])
    return {"message": "Homework deleted"}


@api.post("/homework/{hw_id}/close")
async def close_homework(hw_id: str, user: dict = Depends(require_roles("teacher", "institution_admin"))):
    iid = user["institution_id"]
    hw = await _get_own_homework(iid, hw_id, user)
    await db.homework.update_one({"id": hw_id}, {"$set": {"status": "closed"}})
    await audit(user, "close_homework", "homework", hw_id, hw["title"])
    return {"message": "Homework closed — submissions are now blocked"}


@api.post("/homework/{hw_id}/reopen")
async def reopen_homework(hw_id: str, user: dict = Depends(require_roles("teacher", "institution_admin"))):
    iid = user["institution_id"]
    hw = await _get_own_homework(iid, hw_id, user)
    await db.homework.update_one({"id": hw_id}, {"$set": {"status": "open"}})
    await audit(user, "reopen_homework", "homework", hw_id, hw["title"])
    return {"message": "Homework reopened"}


async def _hw_counts(hw_id, class_section_total):
    subs = await db.homework_submissions.find({"homework_id": hw_id}, {"_id": 0, "status": 1, "late": 1}).to_list(5000)
    return {"total_students": class_section_total, "submitted": len(subs),
            "verified": sum(1 for s in subs if s["status"] == "verified"),
            "redo": sum(1 for s in subs if s["status"] == "redo"),
            "late": sum(1 for s in subs if s.get("late"))}


@api.get("/homework")
async def list_homework(status: str = "", class_name: str = "", subject: str = "",
                        date_from: str = "", date_to: str = "", user: dict = Depends(get_current_user)):
    iid = user["institution_id"]
    role = user["role"]
    q = {"institution_id": iid}
    if status:
        q["status"] = status
    if subject:
        q["subject"] = subject
    if date_from or date_to:
        q["due_date"] = {}
        if date_from:
            q["due_date"]["$gte"] = date_from
        if date_to:
            q["due_date"]["$lte"] = date_to

    my_sub_by_hw = {}
    if role == "teacher" and not await active_principal(user):
        q["teacher_id"] = user["id"]
    elif role == "student":
        sid = user.get("student_id")
        st = await db.students.find_one({"id": sid, "institution_id": iid}, {"_id": 0}) if sid else None
        if not st or not st.get("class_name"):
            return {"homework": []}
        q["class_name"] = st["class_name"]
        q["section"] = st.get("section")
        subs = await db.homework_submissions.find({"institution_id": iid, "student_id": sid}, {"_id": 0}).to_list(5000)
        my_sub_by_hw = {s["homework_id"]: s for s in subs}
    elif role == "parent":
        return await _parent_homework(user, user_student_id=None)

    if class_name and role != "parent":
        q["class_name"] = class_name

    scope = await principal_scope(user) if role in ("teacher", "institution_admin") else None
    out = []
    for hw in await db.homework.find(q, {"_id": 0}).sort("created_at", -1).to_list(500):
        if scope and not scope["whole_school"] and hw["class_name"] not in (scope["class_names"] or []):
            continue
        _, sids = await _class_section_student_user_ids(iid, hw["class_name"], hw["section"])
        hw["counts"] = await _hw_counts(hw["id"], len(sids))
        hw["can_edit"] = (role == "institution_admin" or hw["teacher_id"] == user["id"])
        if role == "student":
            s = my_sub_by_hw.get(hw["id"])
            hw["my_submission"] = s
        out.append(hw)
    return {"homework": out}


async def _parent_homework(user, user_student_id=None):
    iid = user["institution_id"]
    linked = user.get("student_ids") or []
    target = [user_student_id] if (user_student_id and user_student_id in linked) else linked
    out = []
    for sid in target:
        st = await db.students.find_one({"id": sid, "institution_id": iid}, {"_id": 0})
        if not st or not st.get("class_name"):
            continue
        subs = {s["homework_id"]: s for s in await db.homework_submissions.find(
            {"institution_id": iid, "student_id": sid}, {"_id": 0}).to_list(5000)}
        for hw in await db.homework.find(
                {"institution_id": iid, "class_name": st["class_name"], "section": st.get("section")},
                {"_id": 0}).sort("created_at", -1).to_list(500):
            hw["student_id"] = sid
            hw["my_submission"] = subs.get(hw["id"])
            out.append(hw)
    return {"homework": out}


@api.get("/parent/child/{student_id}/homework")
async def parent_child_homework(student_id: str, user: dict = Depends(require_roles("parent"))):
    if student_id not in (user.get("student_ids") or []):
        raise HTTPException(status_code=403, detail="This child is not linked to your account")
    return await _parent_homework(user, user_student_id=student_id)


@api.get("/homework/monitor")
async def homework_monitor(type: str = "homework",
                           from_: str = Query("", alias="from"), to: str = "",
                           user: dict = Depends(require_admin_or_principal)):
    if type not in _HW_SOURCES:
        raise HTTPException(status_code=400, detail="type must be 'homework' or 'assignment'")
    iid = user["institution_id"]
    d_from, d_to = _month_default_range()
    d_from, d_to = (from_ or d_from), (to or d_to)
    scope_classes = await _monitor_scope_classes(user)
    return await _monitor_data(iid, scope_classes, d_from, d_to, type)


@api.get("/homework/{hw_id}")
async def get_homework(hw_id: str, user: dict = Depends(get_current_user)):
    iid = user["institution_id"]
    hw = await db.homework.find_one({"id": hw_id, "institution_id": iid}, {"_id": 0})
    if not hw:
        raise HTTPException(status_code=404, detail="Homework not found")
    role = user["role"]
    if role == "student":
        if user.get("student_id"):
            st = await db.students.find_one({"id": user["student_id"]}, {"_id": 0})
            if not st or st.get("class_name") != hw["class_name"] or st.get("section") != hw["section"]:
                raise HTTPException(status_code=403, detail="Forbidden")
        hw["my_submission"] = await db.homework_submissions.find_one(
            {"homework_id": hw_id, "student_id": user["student_id"]}, {"_id": 0})
    elif role == "parent":
        linked = await db.students.find_one(
            {"id": {"$in": user.get("student_ids") or []}, "class_name": hw["class_name"], "section": hw["section"]}, {"_id": 0})
        if not linked:
            raise HTTPException(status_code=403, detail="Forbidden")
    elif role == "teacher" and not await active_principal(user) and hw["teacher_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Forbidden")
    elif role in ("teacher", "institution_admin"):
        await guard_principal_class(user, hw["class_name"])
    return {"homework": hw}


async def _store_hw_files(files, prefix, base="homework"):
    if not files:
        return []
    if len(files) > HW_MAX_FILES:
        raise HTTPException(status_code=400, detail=f"Attach at most {HW_MAX_FILES} files")
    out = []
    for f in files:
        if f.content_type not in HW_ATTACH_TYPES:
            raise HTTPException(status_code=400, detail="Allowed files: PDF, images (JPG/PNG/WebP) or Word docs")
        data = await f.read()
        if len(data) > HW_MAX_MB * 1024 * 1024:
            raise HTTPException(status_code=400, detail=f"Each file must be under {HW_MAX_MB} MB")
        path = f"lnmo/{base}/{prefix}/{uuid.uuid4()}.{HW_ATTACH_TYPES[f.content_type]}"
        try:
            res = _put_object(path, data, f.content_type)
        except Exception:
            raise HTTPException(status_code=502, detail="File storage is unavailable right now — try again shortly")
        out.append({"path": res["path"], "name": f.filename, "size": len(data), "type": f.content_type})
    return out


@api.post("/homework/{hw_id}/attachments")
async def add_homework_attachments(hw_id: str, files: List[UploadFile] = File(...),
                                   user: dict = Depends(require_roles("teacher", "institution_admin"))):
    iid = user["institution_id"]
    hw = await _get_own_homework(iid, hw_id, user)
    existing = hw.get("attachments") or []
    if len(existing) + len(files) > HW_MAX_FILES:
        raise HTTPException(status_code=400, detail=f"Homework can have at most {HW_MAX_FILES} attachments")
    added = await _store_hw_files(files, f"{hw_id}/task")
    await db.homework.update_one({"id": hw_id}, {"$set": {"attachments": existing + added}})
    return {"attachments": existing + added}


@api.post("/homework/{hw_id}/submit")
async def submit_homework(hw_id: str, note: str = Form(""),
                          files: List[UploadFile] = File(None), user: dict = Depends(require_roles("student"))):
    iid = user["institution_id"]
    sid = user.get("student_id")
    hw = await db.homework.find_one({"id": hw_id, "institution_id": iid}, {"_id": 0})
    if not hw:
        raise HTTPException(status_code=404, detail="Homework not found")
    st = await db.students.find_one({"id": sid, "institution_id": iid}, {"_id": 0}) if sid else None
    if not st or st.get("class_name") != hw["class_name"] or st.get("section") != hw["section"]:
        raise HTTPException(status_code=403, detail="This homework isn't for your class")
    if hw["status"] == "closed":
        raise HTTPException(status_code=400, detail="Submissions closed")
    attachments = await _store_hw_files([f for f in (files or []) if f], f"{hw_id}/sub/{sid}")
    late = now_iso() > hw["due_date"]
    existing = await db.homework_submissions.find_one({"homework_id": hw_id, "student_id": sid}, {"_id": 0})
    now = now_iso()
    if existing:
        version = existing.get("version", 1) + 1 if existing["status"] == "redo" else existing.get("version", 1)
        await db.homework_submissions.update_one(
            {"id": existing["id"]},
            {"$set": {"attachments": attachments, "note": note, "submitted_at": now, "late": late,
                      "status": "submitted", "version": version, "feedback": "", "verified_by": None, "verified_at": None}})
        sub_id = existing["id"]
    else:
        sub = {"id": str(uuid.uuid4()), "institution_id": iid, "homework_id": hw_id, "student_id": sid,
               "attachments": attachments, "note": note, "submitted_at": now, "late": late,
               "status": "submitted", "feedback": "", "verified_by": None, "verified_at": None, "version": 1}
        await db.homework_submissions.insert_one(dict(sub))
        sub_id = sub["id"]
    await audit(user, "submit_homework", "homework_submissions", sub_id, hw["title"])
    await _notify(iid, hw["teacher_id"], "homework_submitted",
                  f"Homework submitted: {hw['title']}",
                  f"{st.get('first_name','')} {st.get('last_name','')}".strip() + (" · Late" if late else ""), hw_id)
    saved = await db.homework_submissions.find_one({"id": sub_id}, {"_id": 0})
    return {"message": "Submitted" + (" (marked Late)" if late else ""), "late": late, "submission": saved}


@api.get("/homework/{hw_id}/submissions")
async def list_hw_submissions(hw_id: str, user: dict = Depends(get_current_user)):
    iid = user["institution_id"]
    hw = await db.homework.find_one({"id": hw_id, "institution_id": iid}, {"_id": 0})
    if not hw:
        raise HTTPException(status_code=404, detail="Homework not found")
    role = user["role"]
    if role == "teacher" and not await active_principal(user):
        if hw["teacher_id"] != user["id"]:
            raise HTTPException(status_code=403, detail="Forbidden")
    elif role in ("teacher", "institution_admin"):
        await guard_principal_class(user, hw["class_name"])
    else:
        raise HTTPException(status_code=403, detail="Forbidden")
    _, sids = await _class_section_student_user_ids(iid, hw["class_name"], hw["section"])
    names = {s["id"]: f"{s.get('first_name','')} {s.get('last_name','')}".strip()
             for s in await db.students.find({"id": {"$in": sids}}, {"_id": 0, "id": 1, "first_name": 1, "last_name": 1}).to_list(2000)}
    subs = await db.homework_submissions.find({"homework_id": hw_id}, {"_id": 0}).to_list(5000)
    for s in subs:
        s["student_name"] = names.get(s["student_id"], "—")
    submitted_ids = {s["student_id"] for s in subs}
    pending = [{"student_id": i, "student_name": names.get(i, "—")} for i in sids if i not in submitted_ids]
    return {"homework": hw, "submissions": subs, "pending": pending}


@api.post("/submissions/{sub_id}/verify")
async def verify_submission(sub_id: str, body: VerifyVerdict, user: dict = Depends(require_roles("teacher", "institution_admin"))):
    iid = user["institution_id"]
    sub = await db.homework_submissions.find_one({"id": sub_id, "institution_id": iid}, {"_id": 0})
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found")
    hw = await db.homework.find_one({"id": sub["homework_id"], "institution_id": iid}, {"_id": 0})
    if user["role"] == "teacher" and not await active_principal(user) and hw["teacher_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="You can only verify your own homework")
    if user["role"] == "institution_admin":
        await guard_principal_class(user, hw["class_name"])
    if body.verdict not in ("verified", "redo"):
        raise HTTPException(status_code=400, detail="Verdict must be 'verified' or 'redo'")
    if body.verdict == "redo" and not (body.feedback or "").strip():
        raise HTTPException(status_code=400, detail="Feedback is required when sending work back for redo")
    await db.homework_submissions.update_one(
        {"id": sub_id}, {"$set": {"status": body.verdict, "feedback": (body.feedback or "").strip(),
                                  "verified_by": user["id"], "verified_at": now_iso()}})
    await audit(user, f"homework_{body.verdict}", "homework_submissions", sub_id, hw["title"])
    # Bell: notify the student + their linked parents of the verdict.
    su = await db.users.find_one({"institution_id": iid, "role": "student", "student_id": sub["student_id"]}, {"_id": 0, "id": 1})
    label = "verified ✓" if body.verdict == "verified" else "needs redo"
    title = f"Homework {label}: {hw['title']}"
    if su:
        await _notify(iid, su["id"], f"homework_{body.verdict}", title, hw["subject"], hw["id"])
    for pid in await _student_parent_ids(iid, sub["student_id"]):
        await _notify(iid, pid, f"homework_{body.verdict}", title, hw["subject"], hw["id"])
    return {"message": "Verified" if body.verdict == "verified" else "Sent back for redo"}


@api.get("/homework/attachment/{sub_or_hw}/{idx}")
async def download_hw_attachment(sub_or_hw: str, idx: int, kind: str = "homework", user: dict = Depends(get_current_user)):
    """Authorized download: class members / assigning teacher / linked parents / scoped principal / admin."""
    iid = user["institution_id"]
    if kind == "submission":
        sub = await db.homework_submissions.find_one({"id": sub_or_hw, "institution_id": iid}, {"_id": 0})
        if not sub:
            raise HTTPException(status_code=404, detail="Not found")
        hw = await db.homework.find_one({"id": sub["homework_id"], "institution_id": iid}, {"_id": 0})
        atts = sub.get("attachments") or []
        owner_student = sub["student_id"]
    else:
        hw = await db.homework.find_one({"id": sub_or_hw, "institution_id": iid}, {"_id": 0})
        atts = (hw or {}).get("attachments") or []
        owner_student = None
    if not hw or idx < 0 or idx >= len(atts):
        raise HTTPException(status_code=404, detail="Attachment not found")
    role = user["role"]
    allowed = False
    if role == "institution_admin":
        allowed = True
    elif role == "teacher":
        allowed = hw["teacher_id"] == user["id"] or bool(await active_principal(user))
        if allowed and await active_principal(user) and role == "teacher":
            scope = await principal_scope(user)
            if scope and not scope["whole_school"] and hw["class_name"] not in (scope["class_names"] or []):
                allowed = hw["teacher_id"] == user["id"]
    elif role == "student":
        st = await db.students.find_one({"id": user.get("student_id")}, {"_id": 0})
        in_class = st and st.get("class_name") == hw["class_name"] and st.get("section") == hw["section"]
        allowed = bool(in_class) and (owner_student is None or owner_student == user.get("student_id"))
    elif role == "parent":
        if owner_student is None:
            allowed = bool(await db.students.find_one(
                {"id": {"$in": user.get("student_ids") or []}, "class_name": hw["class_name"], "section": hw["section"]}, {"_id": 0}))
        else:
            allowed = owner_student in (user.get("student_ids") or [])
    if not allowed:
        raise HTTPException(status_code=403, detail="Forbidden")
    att = atts[idx]
    try:
        data, ctype = _get_object(att["path"])
    except Exception:
        raise HTTPException(status_code=404, detail="File unavailable")
    return Response(content=data, media_type=att.get("type") or ctype,
                    headers={"Content-Disposition": f'inline; filename="{att.get("name","file")}"',
                             "Cache-Control": "private, max-age=120"})


@api.get("/students/{student_id}/homework-stats")
async def homework_stats(student_id: str, date_from: str = "", date_to: str = "",
                         user: dict = Depends(get_current_user)):
    """Per-student aggregates (assigned/submitted/late/verified/redo) — powers the FUTURE monthly report."""
    iid = user["institution_id"]
    student = await db.students.find_one({"id": student_id, "institution_id": iid}, {"_id": 0})
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    role = user["role"]
    if role == "student" and user.get("student_id") != student_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    if role == "parent" and student_id not in (user.get("student_ids") or []):
        raise HTTPException(status_code=403, detail="Forbidden")
    if role in ("teacher", "institution_admin") and not (role == "teacher" and not await active_principal(user)):
        await guard_principal_class(user, student.get("class_name"))
    hwq = {"institution_id": iid, "class_name": student.get("class_name"), "section": student.get("section")}
    if date_from or date_to:
        hwq["due_date"] = {}
        if date_from:
            hwq["due_date"]["$gte"] = date_from
        if date_to:
            hwq["due_date"]["$lte"] = date_to
    assigned = await db.homework.count_documents(hwq)
    hw_ids = [h["id"] for h in await db.homework.find(hwq, {"_id": 0, "id": 1}).to_list(5000)]
    subs = await db.homework_submissions.find(
        {"institution_id": iid, "student_id": student_id, "homework_id": {"$in": hw_ids}}, {"_id": 0}).to_list(5000)
    return {"student_id": student_id, "assigned": assigned, "submitted": len(subs),
            "late": sum(1 for s in subs if s.get("late")),
            "verified": sum(1 for s in subs if s["status"] == "verified"),
            "redo": sum(1 for s in subs if s["status"] == "redo"),
            "pending": max(0, assigned - len(subs))}


# ================= Phase 22 — ASSIGNMENTS MODULE (scored sibling of homework) =================
# Design: MIRRORED collections (assignments, assignment_submissions) rather than generalizing the
# Phase 21 homework engine — keeps homework behavior untouched. Shares helpers (_teaches_subject,
# _class_section_student_user_ids, _student_parent_ids, _store_hw_files, _notify). Differences vs
# homework: max_marks (int>=1), a per-submission score captured at verify (required for verdict
# "verified", 0..max_marks), and a counts_toward_report flag that surfaces verified scores on the
# report card. Attachments live under lnmo/assignments/... (authenticated read).


class AssignmentCreate(BaseModel):
    class_name: str
    section: str
    subject: str
    title: str
    instructions: Optional[str] = ""
    due_date: str
    max_marks: int = PField(ge=1)
    counts_toward_report: bool = False


class AssignmentUpdate(BaseModel):
    title: Optional[str] = None
    instructions: Optional[str] = None
    due_date: Optional[str] = None
    max_marks: Optional[int] = PField(default=None, ge=1)
    counts_toward_report: Optional[bool] = None


class VerifyScored(BaseModel):
    verdict: str  # verified | redo
    score: Optional[int] = None
    feedback: Optional[str] = ""


async def _asg_counts(asg_id, total_students):
    subs = await db.assignment_submissions.find({"assignment_id": asg_id}, {"_id": 0, "status": 1, "late": 1}).to_list(5000)
    return {"total_students": total_students, "submitted": len(subs),
            "verified": sum(1 for s in subs if s["status"] == "verified"),
            "redo": sum(1 for s in subs if s["status"] == "redo"),
            "late": sum(1 for s in subs if s.get("late"))}


def _asg_public(a):
    return {k: a[k] for k in a if k != "_id"}


@api.post("/assignments")
async def create_assignment(body: AssignmentCreate, user: dict = Depends(require_roles("teacher", "institution_admin"))):
    iid = user["institution_id"]
    if user["role"] == "teacher" and not await _teaches_subject(iid, user["id"], body.class_name, body.section, body.subject):
        raise HTTPException(status_code=403, detail="You can only set assignments for a class & subject you are assigned to teach")
    if user["role"] == "institution_admin":
        await guard_principal_class(user, body.class_name)
    year = await _active_year_name(iid)
    a = {"id": str(uuid.uuid4()), "institution_id": iid, "academic_year": year,
         "class_name": body.class_name, "section": body.section, "subject": body.subject,
         "teacher_id": user["id"], "title": body.title.strip(), "instructions": (body.instructions or "").strip(),
         "attachments": [], "due_date": body.due_date, "status": "open", "max_marks": body.max_marks,
         "counts_toward_report": bool(body.counts_toward_report), "created_at": now_iso()}
    await db.assignments.insert_one(dict(a))
    await audit(user, "create_assignment", "assignments", a["id"], a["title"])
    users, sids = await _class_section_student_user_ids(iid, body.class_name, body.section)
    title = f"New assignment: {a['title']}"
    body_txt = f"{body.subject} · {body.class_name} {body.section} · {body.max_marks} marks · due {body.due_date[:10]}"
    for su in users:
        await _notify(iid, su["id"], "assignment_new", title, body_txt, a["id"])
    for sid in sids:
        for pid in await _student_parent_ids(iid, sid):
            await _notify(iid, pid, "assignment_new", title, body_txt, a["id"])
    return {"assignment": _asg_public(a)}


async def _get_own_assignment(iid, asg_id, user):
    a = await db.assignments.find_one({"id": asg_id, "institution_id": iid}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Assignment not found")
    if user["role"] != "institution_admin" and a["teacher_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="You can only manage your own assignments")
    if user["role"] == "institution_admin":
        await guard_principal_class(user, a["class_name"])
    return a


@api.put("/assignments/{asg_id}")
async def update_assignment(asg_id: str, body: AssignmentUpdate, user: dict = Depends(require_roles("teacher", "institution_admin"))):
    iid = user["institution_id"]
    a = await _get_own_assignment(iid, asg_id, user)
    if a["status"] != "open":
        raise HTTPException(status_code=400, detail="Reopen the assignment before editing it")
    upd = {k: v for k, v in body.dict().items() if v is not None}
    if upd:
        await db.assignments.update_one({"id": asg_id}, {"$set": upd})
    await audit(user, "update_assignment", "assignments", asg_id, a["title"])
    return {"message": "Assignment updated"}


@api.delete("/assignments/{asg_id}")
async def delete_assignment(asg_id: str, user: dict = Depends(require_roles("teacher", "institution_admin"))):
    iid = user["institution_id"]
    a = await _get_own_assignment(iid, asg_id, user)
    if await db.assignment_submissions.count_documents({"assignment_id": asg_id}) > 0:
        raise HTTPException(status_code=409, detail="This assignment already has submissions and can't be deleted")
    await db.assignments.delete_one({"id": asg_id})
    await audit(user, "delete_assignment", "assignments", asg_id, a["title"])
    return {"message": "Assignment deleted"}


@api.post("/assignments/{asg_id}/close")
async def close_assignment(asg_id: str, user: dict = Depends(require_roles("teacher", "institution_admin"))):
    iid = user["institution_id"]
    a = await _get_own_assignment(iid, asg_id, user)
    await db.assignments.update_one({"id": asg_id}, {"$set": {"status": "closed"}})
    await audit(user, "close_assignment", "assignments", asg_id, a["title"])
    return {"message": "Assignment closed — submissions are now blocked"}


@api.post("/assignments/{asg_id}/reopen")
async def reopen_assignment(asg_id: str, user: dict = Depends(require_roles("teacher", "institution_admin"))):
    iid = user["institution_id"]
    a = await _get_own_assignment(iid, asg_id, user)
    await db.assignments.update_one({"id": asg_id}, {"$set": {"status": "open"}})
    await audit(user, "reopen_assignment", "assignments", asg_id, a["title"])
    return {"message": "Assignment reopened"}


@api.get("/assignments")
async def list_assignments(status: str = "", class_name: str = "", subject: str = "",
                           date_from: str = "", date_to: str = "", user: dict = Depends(get_current_user)):
    iid = user["institution_id"]
    role = user["role"]
    q = {"institution_id": iid}
    if status:
        q["status"] = status
    if subject:
        q["subject"] = subject
    if date_from or date_to:
        q["due_date"] = {}
        if date_from:
            q["due_date"]["$gte"] = date_from
        if date_to:
            q["due_date"]["$lte"] = date_to

    my_sub_by_asg = {}
    if role == "teacher" and not await active_principal(user):
        q["teacher_id"] = user["id"]
    elif role == "student":
        sid = user.get("student_id")
        st = await db.students.find_one({"id": sid, "institution_id": iid}, {"_id": 0}) if sid else None
        if not st or not st.get("class_name"):
            return {"assignments": []}
        q["class_name"] = st["class_name"]
        q["section"] = st.get("section")
        subs = await db.assignment_submissions.find({"institution_id": iid, "student_id": sid}, {"_id": 0}).to_list(5000)
        my_sub_by_asg = {s["assignment_id"]: s for s in subs}
    elif role == "parent":
        return await _parent_assignments(user, user_student_id=None)

    if class_name and role != "parent":
        q["class_name"] = class_name

    scope = await principal_scope(user) if role in ("teacher", "institution_admin") else None
    out = []
    for a in await db.assignments.find(q, {"_id": 0}).sort("created_at", -1).to_list(500):
        if scope and not scope["whole_school"] and a["class_name"] not in (scope["class_names"] or []):
            continue
        _, sids = await _class_section_student_user_ids(iid, a["class_name"], a["section"])
        a["counts"] = await _asg_counts(a["id"], len(sids))
        a["can_edit"] = (role == "institution_admin" or a["teacher_id"] == user["id"])
        if role == "student":
            a["my_submission"] = my_sub_by_asg.get(a["id"])
        out.append(a)
    return {"assignments": out}


async def _parent_assignments(user, user_student_id=None):
    iid = user["institution_id"]
    linked = user.get("student_ids") or []
    target = [user_student_id] if (user_student_id and user_student_id in linked) else linked
    out = []
    for sid in target:
        st = await db.students.find_one({"id": sid, "institution_id": iid}, {"_id": 0})
        if not st or not st.get("class_name"):
            continue
        subs = {s["assignment_id"]: s for s in await db.assignment_submissions.find(
            {"institution_id": iid, "student_id": sid}, {"_id": 0}).to_list(5000)}
        for a in await db.assignments.find(
                {"institution_id": iid, "class_name": st["class_name"], "section": st.get("section")},
                {"_id": 0}).sort("created_at", -1).to_list(500):
            a["student_id"] = sid
            a["my_submission"] = subs.get(a["id"])
            out.append(a)
    return {"assignments": out}


@api.get("/parent/child/{student_id}/assignments")
async def parent_child_assignments(student_id: str, user: dict = Depends(require_roles("parent"))):
    if student_id not in (user.get("student_ids") or []):
        raise HTTPException(status_code=403, detail="This child is not linked to your account")
    return await _parent_assignments(user, user_student_id=student_id)


@api.get("/assignments/{asg_id}")
async def get_assignment(asg_id: str, user: dict = Depends(get_current_user)):
    iid = user["institution_id"]
    a = await db.assignments.find_one({"id": asg_id, "institution_id": iid}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Assignment not found")
    role = user["role"]
    if role == "student":
        if user.get("student_id"):
            st = await db.students.find_one({"id": user["student_id"]}, {"_id": 0})
            if not st or st.get("class_name") != a["class_name"] or st.get("section") != a["section"]:
                raise HTTPException(status_code=403, detail="Forbidden")
        a["my_submission"] = await db.assignment_submissions.find_one(
            {"assignment_id": asg_id, "student_id": user["student_id"]}, {"_id": 0})
    elif role == "parent":
        linked = await db.students.find_one(
            {"id": {"$in": user.get("student_ids") or []}, "class_name": a["class_name"], "section": a["section"]}, {"_id": 0})
        if not linked:
            raise HTTPException(status_code=403, detail="Forbidden")
    elif role == "teacher" and not await active_principal(user) and a["teacher_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Forbidden")
    elif role in ("teacher", "institution_admin"):
        await guard_principal_class(user, a["class_name"])
    return {"assignment": a}


@api.post("/assignments/{asg_id}/attachments")
async def add_assignment_attachments(asg_id: str, files: List[UploadFile] = File(...),
                                     user: dict = Depends(require_roles("teacher", "institution_admin"))):
    iid = user["institution_id"]
    a = await _get_own_assignment(iid, asg_id, user)
    existing = a.get("attachments") or []
    if len(existing) + len(files) > HW_MAX_FILES:
        raise HTTPException(status_code=400, detail=f"Assignment can have at most {HW_MAX_FILES} attachments")
    added = await _store_hw_files(files, f"{asg_id}/task", base="assignments")
    await db.assignments.update_one({"id": asg_id}, {"$set": {"attachments": existing + added}})
    return {"attachments": existing + added}


@api.post("/assignments/{asg_id}/submit")
async def submit_assignment(asg_id: str, note: str = Form(""),
                            files: List[UploadFile] = File(None), user: dict = Depends(require_roles("student"))):
    iid = user["institution_id"]
    sid = user.get("student_id")
    a = await db.assignments.find_one({"id": asg_id, "institution_id": iid}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Assignment not found")
    st = await db.students.find_one({"id": sid, "institution_id": iid}, {"_id": 0}) if sid else None
    if not st or st.get("class_name") != a["class_name"] or st.get("section") != a["section"]:
        raise HTTPException(status_code=403, detail="This assignment isn't for your class")
    if a["status"] == "closed":
        raise HTTPException(status_code=400, detail="Submissions closed")
    attachments = await _store_hw_files([f for f in (files or []) if f], f"{asg_id}/sub/{sid}", base="assignments")
    late = now_iso() > a["due_date"]
    existing = await db.assignment_submissions.find_one({"assignment_id": asg_id, "student_id": sid}, {"_id": 0})
    now = now_iso()
    if existing:
        version = existing.get("version", 1) + 1 if existing["status"] == "redo" else existing.get("version", 1)
        await db.assignment_submissions.update_one(
            {"id": existing["id"]},
            {"$set": {"attachments": attachments, "note": note, "submitted_at": now, "late": late,
                      "status": "submitted", "version": version, "feedback": "", "score": None,
                      "verified_by": None, "verified_at": None}})
        sub_id = existing["id"]
    else:
        sub = {"id": str(uuid.uuid4()), "institution_id": iid, "assignment_id": asg_id, "student_id": sid,
               "attachments": attachments, "note": note, "submitted_at": now, "late": late,
               "status": "submitted", "feedback": "", "score": None, "verified_by": None,
               "verified_at": None, "version": 1}
        await db.assignment_submissions.insert_one(dict(sub))
        sub_id = sub["id"]
    await audit(user, "submit_assignment", "assignment_submissions", sub_id, a["title"])
    await _notify(iid, a["teacher_id"], "assignment_submitted",
                  f"Assignment submitted: {a['title']}",
                  f"{st.get('first_name','')} {st.get('last_name','')}".strip() + (" · Late" if late else ""), asg_id)
    saved = await db.assignment_submissions.find_one({"id": sub_id}, {"_id": 0})
    return {"message": "Submitted" + (" (marked Late)" if late else ""), "late": late, "submission": saved}


@api.get("/assignments/{asg_id}/submissions")
async def list_asg_submissions(asg_id: str, user: dict = Depends(get_current_user)):
    iid = user["institution_id"]
    a = await db.assignments.find_one({"id": asg_id, "institution_id": iid}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Assignment not found")
    role = user["role"]
    if role == "teacher" and not await active_principal(user):
        if a["teacher_id"] != user["id"]:
            raise HTTPException(status_code=403, detail="Forbidden")
    elif role in ("teacher", "institution_admin"):
        await guard_principal_class(user, a["class_name"])
    else:
        raise HTTPException(status_code=403, detail="Forbidden")
    _, sids = await _class_section_student_user_ids(iid, a["class_name"], a["section"])
    names = {s["id"]: f"{s.get('first_name','')} {s.get('last_name','')}".strip()
             for s in await db.students.find({"id": {"$in": sids}}, {"_id": 0, "id": 1, "first_name": 1, "last_name": 1}).to_list(2000)}
    subs = await db.assignment_submissions.find({"assignment_id": asg_id}, {"_id": 0}).to_list(5000)
    for s in subs:
        s["student_name"] = names.get(s["student_id"], "—")
    submitted_ids = {s["student_id"] for s in subs}
    pending = [{"student_id": i, "student_name": names.get(i, "—")} for i in sids if i not in submitted_ids]
    return {"assignment": a, "submissions": subs, "pending": pending}


@api.post("/assignment-submissions/{sub_id}/verify")
async def verify_assignment_submission(sub_id: str, body: VerifyScored, user: dict = Depends(require_roles("teacher", "institution_admin"))):
    iid = user["institution_id"]
    sub = await db.assignment_submissions.find_one({"id": sub_id, "institution_id": iid}, {"_id": 0})
    if not sub:
        raise HTTPException(status_code=404, detail="Submission not found")
    a = await db.assignments.find_one({"id": sub["assignment_id"], "institution_id": iid}, {"_id": 0})
    if user["role"] == "teacher" and not await active_principal(user) and a["teacher_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="You can only verify your own assignments")
    if user["role"] == "institution_admin":
        await guard_principal_class(user, a["class_name"])
    if body.verdict not in ("verified", "redo"):
        raise HTTPException(status_code=400, detail="Verdict must be 'verified' or 'redo'")
    max_marks = a.get("max_marks", 0)
    if body.verdict == "redo":
        if not (body.feedback or "").strip():
            raise HTTPException(status_code=400, detail="Feedback is required when sending work back for redo")
        set_fields = {"status": "redo", "feedback": body.feedback.strip(), "score": None,
                      "verified_by": user["id"], "verified_at": now_iso()}
    else:
        if body.score is None:
            raise HTTPException(status_code=400, detail="A score is required to mark an assignment verified")
        if body.score < 0 or body.score > max_marks:
            raise HTTPException(status_code=400, detail=f"Score must be between 0 and {max_marks}")
        set_fields = {"status": "verified", "score": body.score, "feedback": (body.feedback or "").strip(),
                      "verified_by": user["id"], "verified_at": now_iso()}
    await db.assignment_submissions.update_one({"id": sub_id}, {"$set": set_fields})
    await audit(user, f"assignment_{body.verdict}", "assignment_submissions", sub_id, a["title"])
    su = await db.users.find_one({"institution_id": iid, "role": "student", "student_id": sub["student_id"]}, {"_id": 0, "id": 1})
    if body.verdict == "verified":
        label = f"scored {body.score}/{max_marks}"
    else:
        label = "needs redo"
    title = f"Assignment {label}: {a['title']}"
    if su:
        await _notify(iid, su["id"], f"assignment_{body.verdict}", title, a["subject"], a["id"])
    for pid in await _student_parent_ids(iid, sub["student_id"]):
        await _notify(iid, pid, f"assignment_{body.verdict}", title, a["subject"], a["id"])
    return {"message": f"Scored {body.score}/{max_marks}" if body.verdict == "verified" else "Sent back for redo"}


@api.get("/assignments/attachment/{sub_or_asg}/{idx}")
async def download_asg_attachment(sub_or_asg: str, idx: int, kind: str = "assignment", user: dict = Depends(get_current_user)):
    iid = user["institution_id"]
    if kind == "submission":
        sub = await db.assignment_submissions.find_one({"id": sub_or_asg, "institution_id": iid}, {"_id": 0})
        if not sub:
            raise HTTPException(status_code=404, detail="Not found")
        a = await db.assignments.find_one({"id": sub["assignment_id"], "institution_id": iid}, {"_id": 0})
        atts = sub.get("attachments") or []
        owner_student = sub["student_id"]
    else:
        a = await db.assignments.find_one({"id": sub_or_asg, "institution_id": iid}, {"_id": 0})
        atts = (a or {}).get("attachments") or []
        owner_student = None
    if not a or idx < 0 or idx >= len(atts):
        raise HTTPException(status_code=404, detail="Attachment not found")
    role = user["role"]
    allowed = False
    if role == "institution_admin":
        allowed = True
    elif role == "teacher":
        allowed = a["teacher_id"] == user["id"] or bool(await active_principal(user))
        if allowed and await active_principal(user) and role == "teacher":
            scope = await principal_scope(user)
            if scope and not scope["whole_school"] and a["class_name"] not in (scope["class_names"] or []):
                allowed = a["teacher_id"] == user["id"]
    elif role == "student":
        st = await db.students.find_one({"id": user.get("student_id")}, {"_id": 0})
        in_class = st and st.get("class_name") == a["class_name"] and st.get("section") == a["section"]
        allowed = bool(in_class) and (owner_student is None or owner_student == user.get("student_id"))
    elif role == "parent":
        if owner_student is None:
            allowed = bool(await db.students.find_one(
                {"id": {"$in": user.get("student_ids") or []}, "class_name": a["class_name"], "section": a["section"]}, {"_id": 0}))
        else:
            allowed = owner_student in (user.get("student_ids") or [])
    if not allowed:
        raise HTTPException(status_code=403, detail="Forbidden")
    att = atts[idx]
    try:
        data, ctype = _get_object(att["path"])
    except Exception:
        raise HTTPException(status_code=404, detail="File unavailable")
    return Response(content=data, media_type=att.get("type") or ctype,
                    headers={"Content-Disposition": f'inline; filename="{att.get("name","file")}"',
                             "Cache-Control": "private, max-age=120"})


@api.get("/students/{student_id}/assignment-stats")
async def assignment_stats(student_id: str, date_from: str = "", date_to: str = "",
                           user: dict = Depends(get_current_user)):
    """Per-student assignment aggregates incl. average score of verified items — feeds the FUTURE monthly report."""
    iid = user["institution_id"]
    student = await db.students.find_one({"id": student_id, "institution_id": iid}, {"_id": 0})
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    role = user["role"]
    if role == "student" and user.get("student_id") != student_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    if role == "parent" and student_id not in (user.get("student_ids") or []):
        raise HTTPException(status_code=403, detail="Forbidden")
    if role in ("teacher", "institution_admin") and not (role == "teacher" and not await active_principal(user)):
        await guard_principal_class(user, student.get("class_name"))
    aq = {"institution_id": iid, "class_name": student.get("class_name"), "section": student.get("section")}
    if date_from or date_to:
        aq["due_date"] = {}
        if date_from:
            aq["due_date"]["$gte"] = date_from
        if date_to:
            aq["due_date"]["$lte"] = date_to
    assigned = await db.assignments.count_documents(aq)
    asg_ids = [h["id"] for h in await db.assignments.find(aq, {"_id": 0, "id": 1}).to_list(5000)]
    subs = await db.assignment_submissions.find(
        {"institution_id": iid, "student_id": student_id, "assignment_id": {"$in": asg_ids}}, {"_id": 0}).to_list(5000)
    scores = [s["score"] for s in subs if s["status"] == "verified" and s.get("score") is not None]
    return {"student_id": student_id, "assigned": assigned, "submitted": len(subs),
            "late": sum(1 for s in subs if s.get("late")),
            "verified": sum(1 for s in subs if s["status"] == "verified"),
            "redo": sum(1 for s in subs if s["status"] == "redo"),
            "pending": max(0, assigned - len(subs)),
            "avg_score": round(sum(scores) / len(scores), 1) if scores else None,
            "scored_count": len(scores)}


async def _assignment_report_scores(iid, student_id):
    """Report-card block: verified scores of assignments flagged counts_toward_report, grouped by subject.
    Simple list (no weighting this phase — weighting can be layered on later)."""
    subs = await db.assignment_submissions.find(
        {"institution_id": iid, "student_id": student_id, "status": "verified"}, {"_id": 0}).to_list(5000)
    by_subject = {}
    for s in subs:
        a = await db.assignments.find_one({"id": s["assignment_id"], "institution_id": iid}, {"_id": 0})
        if not a or not a.get("counts_toward_report"):
            continue
        by_subject.setdefault(a["subject"], []).append(
            {"title": a["title"], "score": s.get("score"), "max_marks": a.get("max_marks")})
    return [{"subject": k, "items": v} for k, v in sorted(by_subject.items())]


# ================= Phase 23 — MONITORING DASHBOARDS + DUE REMINDERS =================
# READ-ONLY oversight for admin (all) + principals (their divisions only, server-side).
# The SAME aggregation powers both homework and assignments via a `kind` toggle.

_HW_SOURCES = {
    "homework": (lambda: db.homework, lambda: db.homework_submissions, "homework_id"),
    "assignment": (lambda: db.assignments, lambda: db.assignment_submissions, "assignment_id"),
}


def _month_default_range():
    now = datetime.now(timezone.utc)
    return now.replace(day=1).date().isoformat(), now.date().isoformat()


async def _monitor_scope_classes(user):
    """None → admin (all classes). Otherwise the principal's in-scope class names (whole-school → None)."""
    if user.get("role") == "institution_admin":
        return None
    scope = await principal_scope(user)
    if scope and scope["whole_school"]:
        return None
    return scope["class_names"] if scope else []


async def _monitor_data(iid, scope_classes, date_from, date_to, kind):
    items_col_fn, subs_col_fn, fk = _HW_SOURCES[kind]
    items_col, subs_col = items_col_fn(), subs_col_fn()
    q = {"institution_id": iid, "created_at": {"$gte": date_from, "$lte": date_to + "T23:59:59"}}
    items = await items_col.find(q, {"_id": 0}).to_list(5000)
    if scope_classes is not None:
        items = [it for it in items if it["class_name"] in scope_classes]
    item_ids = [it["id"] for it in items]
    item_by_id = {it["id"]: it for it in items}
    subs = await subs_col.find({"institution_id": iid, fk: {"$in": item_ids}}, {"_id": 0}).to_list(50000)
    subs_by_item = defaultdict(list)
    for s in subs:
        subs_by_item[s[fk]].append(s)

    # enrolled counts per class+section (cached)
    enroll_cache = {}

    async def enrolled(cn, sec):
        key = (cn, sec)
        if key not in enroll_cache:
            _, sids = await _class_section_student_user_ids(iid, cn, sec)
            enroll_cache[key] = sids
        return enroll_cache[key]

    # teacher names
    tids = list({it["teacher_id"] for it in items})
    tnames = {u["id"]: u.get("name") for u in await db.users.find({"id": {"$in": tids}}, {"_id": 0, "id": 1, "name": 1}).to_list(2000)}

    teachers_agg = defaultdict(lambda: {"items_created": 0, "submissions_received": 0, "verified": 0, "pending": 0})
    classes_agg = defaultdict(lambda: {"expected": 0, "submitted": 0, "late": 0, "redo": 0, "items": 0})
    total_expected = total_submitted = total_late = pending_verifications = active = 0
    pending_queue = []
    now = datetime.now(timezone.utc)

    for it in items:
        cn, sec = it["class_name"], it["section"]
        exp = len(await enrolled(cn, sec))
        its = subs_by_item.get(it["id"], [])
        verified = sum(1 for s in its if s["status"] == "verified")
        redo = sum(1 for s in its if s["status"] == "redo")
        pend = sum(1 for s in its if s["status"] == "submitted")
        late = sum(1 for s in its if s.get("late"))
        if it["status"] == "open":
            active += 1
        ta = teachers_agg[it["teacher_id"]]
        ta["items_created"] += 1
        ta["submissions_received"] += len(its)
        ta["verified"] += verified
        ta["pending"] += pend
        ca = classes_agg[(cn, sec)]
        ca["expected"] += exp
        ca["submitted"] += len(its)
        ca["late"] += late
        ca["redo"] += redo
        ca["items"] += 1
        total_expected += exp
        total_submitted += len(its)
        total_late += late
        pending_verifications += pend

    # pending verifications queue (oldest first)
    pend_subs = [s for s in subs if s["status"] == "submitted"]
    pend_subs.sort(key=lambda s: s.get("submitted_at") or "")
    stu_ids = list({s["student_id"] for s in pend_subs})
    snames = {st["id"]: f"{st.get('first_name','')} {st.get('last_name','')}".strip()
              for st in await db.students.find({"id": {"$in": stu_ids}}, {"_id": 0, "id": 1, "first_name": 1, "last_name": 1}).to_list(5000)}
    for s in pend_subs[:100]:
        it = item_by_id.get(s[fk])
        if not it:
            continue
        try:
            age = (now - datetime.fromisoformat(s["submitted_at"])).days
        except Exception:
            age = 0
        pending_queue.append({"submission_id": s["id"], "title": it["title"], "subject": it["subject"],
                              "class_name": it["class_name"], "section": it["section"],
                              "teacher_name": tnames.get(it["teacher_id"]) or "—",
                              "student_name": snames.get(s["student_id"]) or "—", "age_days": age})

    def pct(a, b):
        return round(a / b * 100, 1) if b else 0.0

    return {
        "range": {"from": date_from, "to": date_to}, "type": kind,
        "stats": {"active": active, "submission_rate": pct(total_submitted, total_expected),
                  "pending_verifications": pending_verifications, "late_rate": pct(total_late, total_submitted)},
        "teachers": sorted([{"teacher_id": tid, "teacher_name": tnames.get(tid) or "—", **v}
                            for tid, v in teachers_agg.items()], key=lambda x: -x["items_created"]),
        "classes": sorted([{"class_name": cn, "section": sec, "items": v["items"], "assigned": v["expected"],
                            "submitted": v["submitted"], "submitted_pct": pct(v["submitted"], v["expected"]),
                            "late_pct": pct(v["late"], v["submitted"]), "redo": v["redo"]}
                           for (cn, sec), v in classes_agg.items()], key=lambda x: (x["class_name"], x["section"])),
        "pending": pending_queue,
    }


# ---------------- Due reminders (bell) ----------------
async def _send_due_reminder(iid, kind, it, day):
    """Fan-out a 'due tomorrow' bell to the item's class+section students + linked parents. Idempotent per item+day."""
    key = f"{kind}:{it['id']}:{day}"
    existing = await db.reminders_sent.update_one(
        {"key": key}, {"$setOnInsert": {"key": key, "institution_id": iid, "sent_at": now_iso()}}, upsert=True)
    if existing.matched_count:  # already sent today
        return 0
    users, sids = await _class_section_student_user_ids(iid, it["class_name"], it["section"])
    label = "homework" if kind == "homework" else "assignment"
    title = f"Due tomorrow: {it['title']}"
    body = f"{it['subject']} {label} · {it['class_name']} {it['section']}"
    n = 0
    for su in users:
        await _notify(iid, su["id"], f"{kind}_due_soon", title, body, it["id"]); n += 1
    for sid in sids:
        for pid in await _student_parent_ids(iid, sid):
            await _notify(iid, pid, f"{kind}_due_soon", title, body, it["id"]); n += 1
    return n


async def _due_reminder_sweep():
    """Find open homework + assignments due TOMORROW and send one bell reminder per item (deduped)."""
    day = (datetime.now(timezone.utc).date() + timedelta(days=1)).isoformat()
    total = 0
    for kind in ("homework", "assignment"):
        col = _HW_SOURCES[kind][0]()
        async for it in col.find({"status": "open", "due_date": {"$gte": day, "$lte": day + "T23:59:59"}}, {"_id": 0}):
            total += await _send_due_reminder(it["institution_id"], kind, it, day)
    return total


async def _reminder_loop():
    while True:
        try:
            await _due_reminder_sweep()
        except Exception:
            logger.exception("due-reminder sweep failed")
        await asyncio.sleep(3600)


async def _remind_item(kind, item_id, user):
    iid = user["institution_id"]
    col = _HW_SOURCES[kind][0]()
    it = await col.find_one({"id": item_id, "institution_id": iid}, {"_id": 0})
    if not it:
        raise HTTPException(status_code=404, detail="Not found")
    if user["role"] != "institution_admin" and it["teacher_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="You can only remind for your own items")
    if it["status"] != "open":
        raise HTTPException(status_code=400, detail="This item is closed")
    day = datetime.now(timezone.utc).date().isoformat()  # manual dedupe = once per item per day
    sent = await _send_due_reminder(iid, kind, it, f"manual:{day}")
    await audit(user, f"{kind}_remind", kind, item_id, it["title"])
    if sent == 0:
        return {"message": "A reminder was already sent today", "sent": 0}
    return {"message": "Reminder sent", "sent": sent}


@api.post("/homework/{item_id}/remind")
async def remind_homework(item_id: str, user: dict = Depends(require_roles("teacher", "institution_admin"))):
    return await _remind_item("homework", item_id, user)


@api.post("/assignments/{item_id}/remind")
async def remind_assignment(item_id: str, user: dict = Depends(require_roles("teacher", "institution_admin"))):
    return await _remind_item("assignment", item_id, user)


# ---------------- Class detail ----------------

class ClassUpdateRequest(BaseModel):
    name: Optional[str] = None
    grade_level: Optional[str] = None
    academic_unit_id: Optional[str] = None


class SectionUpdateRequest(BaseModel):
    name: Optional[str] = None
    capacity: Optional[int] = None
    room: Optional[str] = None


class AddSectionRequest(BaseModel):
    name: str
    capacity: Optional[int] = None
    room: Optional[str] = None


@api.put("/classes/{class_id}")
async def rename_class(class_id: str, body: ClassUpdateRequest, user: dict = Depends(get_current_user)):
    """Rename/edit a class with cascade to all referencing collections (scope-guarded)."""
    payload = {k: v for k, v in body.model_dump().items() if v is not None}
    return await update_resource("classes", class_id, payload, user)


@api.delete("/classes/{class_id}")
async def remove_class(class_id: str, user: dict = Depends(get_current_user)):
    return await delete_resource("classes", class_id, user)


@api.post("/classes/{class_id}/sections")
async def add_class_section(class_id: str, body: AddSectionRequest, user: dict = Depends(get_current_user)):
    iid = user["institution_id"]
    cls = await db.classes.find_one({"id": class_id, "institution_id": iid}, {"_id": 0})
    if not cls:
        raise HTTPException(status_code=404, detail="Class not found")
    payload = {"name": body.name, "class_name": cls["name"], "status": "active"}
    if body.capacity is not None:
        payload["capacity"] = body.capacity
    if body.room is not None:
        payload["room"] = body.room
    return await create_resource("sections", payload, user)


@api.put("/sections/{section_id}")
async def rename_section(section_id: str, body: SectionUpdateRequest, user: dict = Depends(get_current_user)):
    """Rename/edit a section with cascade of the section name to referencing collections."""
    payload = {k: v for k, v in body.model_dump().items() if v is not None}
    return await update_resource("sections", section_id, payload, user)


@api.delete("/sections/{section_id}")
async def remove_section(section_id: str, user: dict = Depends(get_current_user)):
    return await delete_resource("sections", section_id, user)


def _month_bounds(month):
    """'YYYY-MM' → (start_iso, next_month_start_iso) for lexicographic due_date filtering."""
    y, m = int(month[:4]), int(month[5:7])
    start = f"{y:04d}-{m:02d}-01"
    ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
    return start, f"{ny:04d}-{nm:02d}-01"


def _hw_agg(items_count, subs):
    submitted = len(subs)
    return {"assigned": items_count, "submitted": submitted,
            "late": sum(1 for s in subs if s.get("late")),
            "verified": sum(1 for s in subs if s["status"] == "verified"),
            "redo": sum(1 for s in subs if s["status"] == "redo"),
            "pending": max(0, items_count - submitted)}


def _asg_agg(items_count, subs):
    submitted = len(subs)
    scores = [s["score"] for s in subs if s["status"] == "verified" and s.get("score") is not None]
    return {"assigned": items_count, "submitted": submitted,
            "late": sum(1 for s in subs if s.get("late")),
            "verified": sum(1 for s in subs if s["status"] == "verified"),
            "redo": sum(1 for s in subs if s["status"] == "redo"),
            "pending": max(0, items_count - submitted),
            "avg_score": round(sum(scores) / len(scores), 1) if scores else None,
            "scored_count": len(scores)}


@api.get("/classes/{class_id}/monthly-report")
async def class_monthly_report(class_id: str, month: str = "", user: dict = Depends(get_current_user)):
    """Class-teacher monthly roll-up of homework + assignment activity (items DUE in the month),
    grouped by section. Top-level blocks are extensible — attendance/grades can be appended later."""
    iid = user["institution_id"]
    cls = await db.classes.find_one({"id": class_id, "institution_id": iid}, {"_id": 0})
    if not cls:
        raise HTTPException(status_code=404, detail="Class not found")
    cn = cls["name"]
    role = user["role"]
    if role == "institution_admin":
        pass
    elif await active_principal(user):
        await guard_principal_class(user, cn)
    elif role == "teacher":
        if not await db.sections.find_one({"institution_id": iid, "class_name": cn, "class_teacher_id": user["id"]}):
            raise HTTPException(status_code=403, detail="Only the class teacher of this class can view its monthly report")
    else:
        raise HTTPException(status_code=403, detail="Access denied")

    if not month:
        month = datetime.now(timezone.utc).strftime("%Y-%m")
    start, end = _month_bounds(month)
    due_range = {"$gte": start, "$lt": end}

    sections = await db.sections.find({"institution_id": iid, "class_name": cn}, {"_id": 0}).sort("name", 1).to_list(200)
    out_sections = []
    for sec in sections:
        secname = sec["name"]
        hw_items = await db.homework.find({"institution_id": iid, "class_name": cn, "section": secname, "due_date": due_range}, {"_id": 0, "id": 1}).to_list(2000)
        asg_items = await db.assignments.find({"institution_id": iid, "class_name": cn, "section": secname, "due_date": due_range}, {"_id": 0, "id": 1}).to_list(2000)
        hw_ids = [h["id"] for h in hw_items]
        asg_ids = [a["id"] for a in asg_items]
        students = await db.students.find({"institution_id": iid, "class_name": cn, "section": secname, "enrollment_status": "enrolled"}, {"_id": 0}).sort("first_name", 1).to_list(2000)
        hw_subs = await db.homework_submissions.find({"institution_id": iid, "homework_id": {"$in": hw_ids}}, {"_id": 0}).to_list(50000)
        asg_subs = await db.assignment_submissions.find({"institution_id": iid, "assignment_id": {"$in": asg_ids}}, {"_id": 0}).to_list(50000)
        hw_by_stu = defaultdict(list)
        for s in hw_subs:
            hw_by_stu[s["student_id"]].append(s)
        asg_by_stu = defaultdict(list)
        for s in asg_subs:
            asg_by_stu[s["student_id"]].append(s)
        ct_name = sec.get("class_teacher") or ""
        if sec.get("class_teacher_id"):
            ctu = await db.users.find_one({"id": sec["class_teacher_id"]}, {"_id": 0, "name": 1})
            if ctu:
                ct_name = ctu.get("name") or ct_name
        rows = []
        for st in students:
            rows.append({
                "student_id": st["id"],
                "name": f"{st.get('first_name','')} {st.get('last_name','')}".strip(),
                "admission_no": st.get("admission_no"),
                "homework": _hw_agg(len(hw_items), hw_by_stu.get(st["id"], [])),
                "assignments": _asg_agg(len(asg_items), asg_by_stu.get(st["id"], [])),
            })
        out_sections.append({"section": secname, "class_teacher": ct_name,
                             "homework_count": len(hw_items), "assignment_count": len(asg_items),
                             "students": rows})

    signers = await _report_card_signers({"class_name": cn, "section": sections[0]["name"]}, iid) if sections else {}
    inst = await db.institutions.find_one({"id": iid}, {"_id": 0, "name": 1, "portal_name": 1, "primary_color": 1, "logo_url": 1, "logo_path": 1, "domain": 1}) or {}
    return {
        "class": {"id": class_id, "name": cn, "academic_unit_name": cls.get("academic_unit_name")},
        "month": month, "sections": out_sections, "signers": signers,
        "institution": {"name": inst.get("name"), "portal_name": inst.get("portal_name"),
                        "primary_color": inst.get("primary_color"), "logo_url": inst.get("logo_url"),
                        "has_logo": bool(inst.get("logo_path")), "domain": inst.get("domain")},
    }


@api.get("/classes/{class_id}/detail")
async def class_detail(class_id: str, user: dict = Depends(require_admin_or_principal)):
    iid = user["institution_id"]
    cls = await db.classes.find_one({"id": class_id, "institution_id": iid}, {"_id": 0})
    if not cls:
        raise HTTPException(status_code=404, detail="Class not found")
    if not _doc_in_principal_scope("classes", cls, await principal_scope(user)):
        raise HTTPException(status_code=403, detail="This class is outside your assigned scope")
    cn = cls["name"]
    sections = await db.sections.find({"institution_id": iid, "class_name": cn}, {"_id": 0}).sort("name", 1).to_list(200)
    offerings = await db.subject_offerings.find({"institution_id": iid, "class_name": cn}, {"_id": 0}).sort("subject", 1).to_list(300)
    students = await db.students.find({"institution_id": iid, "class_name": cn}, {"_id": 0}).sort("first_name", 1).to_list(1000)
    sids = [s["id"] for s in students]
    achievements = await db.achievements.find({"institution_id": iid, "student_id": {"$in": sids}}, {"_id": 0}).sort([("date", -1), ("created_at", -1)]).to_list(1000)
    unit = await db.academic_units.find_one({"id": cls.get("academic_unit_id"), "institution_id": iid},
                                            {"_id": 0, "name": 1, "attendance_model": 1, "timetable_required": 1})
    return {"class": cls, "unit": unit, "sections": sections, "offerings": offerings,
            "students": students, "achievements": achievements}


# ---------------- Lookups ----------------

@api.get("/lookup/{kind}")
async def lookup(kind: str, class_name: str = "", user: dict = Depends(require_roles("institution_admin", "teacher"))):
    iid = user["institution_id"]
    if kind == "students":
        _sq = {"institution_id": iid}
        _sc = await principal_scope(user)
        if _sc and not _sc["whole_school"]:
            _sq["class_name"] = {"$in": _sc["class_names"] or ["__none__"]}
        rows = await db.students.find(_sq, {"_id": 0}).sort("first_name", 1).to_list(1000)
        return [{"value": r["id"], "label": f"{r.get('first_name', '')} {r.get('last_name', '')}".strip()
                 + (f" · {r['admission_no']}" if r.get("admission_no") else "")} for r in rows]
    if kind == "classes":
        _cq = {"institution_id": iid}
        _sc = await principal_scope(user)
        if _sc and not _sc["whole_school"]:
            _cq["academic_unit_id"] = {"$in": _sc["unit_ids"]}
        rows = await db.classes.find(_cq, {"_id": 0}).sort("name", 1).to_list(500)
        return [{"value": r["name"], "label": r["name"]} for r in rows]
    if kind == "sections":
        q = {"institution_id": iid}
        if class_name:
            q["class_name"] = class_name
        _sc = await principal_scope(user)
        if _sc and not _sc["whole_school"]:
            _al = _sc["class_names"] or ["__none__"]
            if class_name and class_name not in _al:
                q["class_name"] = {"$in": []}
            elif not class_name:
                q["class_name"] = {"$in": _al}
        rows = await db.sections.find(q, {"_id": 0}).sort("name", 1).to_list(500)
        seen, out = set(), []
        for r in rows:
            if r["name"] in seen:
                continue
            seen.add(r["name"])
            out.append({"value": r["name"], "label": r["name"]})
        return out
    if kind == "subjects":
        rows = await db.subjects.find({"institution_id": iid}, {"_id": 0}).sort("name", 1).to_list(500)
        return [{"value": r["name"], "label": r["name"]} for r in rows]
    if kind == "academic_years":
        rows = await db.academic_years.find({"institution_id": iid}, {"_id": 0}).sort("name", -1).to_list(100)
        return [{"value": r["name"], "label": r["name"]} for r in rows]
    if kind == "offered_subjects":
        q = {"institution_id": iid}
        if class_name:
            q["class_name"] = class_name
        names = sorted(await db.subject_offerings.distinct("subject", q))
        return [{"value": n, "label": n} for n in names]
    if kind == "teachers_by_id":
        rows = await db.users.find({"institution_id": iid, "role": "teacher"}, {"_id": 0, "password_hash": 0}).sort("name", 1).to_list(500)
        return [{"value": r["id"], "label": f"{r['name']} ({r['email']})"} for r in rows]
    if kind == "teacher_users":
        rows = await db.users.find({"institution_id": iid, "role": "teacher"}, {"_id": 0, "password_hash": 0}).sort("name", 1).to_list(500)
        return [{"value": r["email"], "label": f"{r['name']} ({r['email']})"} for r in rows]
    if kind == "academic_units":
        rows = await db.academic_units.find({"institution_id": iid}, {"_id": 0}).sort("sort_order", 1).to_list(200)
        return [{"value": r["id"], "label": r["name"] + (f" ({r['code']})" if r.get("code") else "")} for r in rows]
    raise HTTPException(status_code=404, detail="Unknown lookup")


# ---------------- Attendance ----------------

ATT_STATUSES = {"present", "absent", "late"}


def _teacher_match(user):
    return {"$or": [{"teacher_id": user["id"]}, {"teacher_email": user["email"]}]}


async def ensure_class_access(user, class_name, section):
    if user["role"] == "institution_admin":
        return
    _scope = await principal_scope(user)
    if _scope and (_scope["whole_school"] or class_name in (_scope["class_names"] or [])):
        return
    q = {"institution_id": user["institution_id"], "class_name": class_name, **_teacher_match(user)}
    a = await db.teacher_assignments.find_one({**q, "section": section})
    if not a and section:
        a = await db.teacher_assignments.find_one({**q, "section": ""})
    if not a:
        sq = {"institution_id": user["institution_id"], "class_name": class_name, "class_teacher_id": user["id"]}
        if section:
            sq["name"] = section
        a = await db.sections.find_one(sq)
    if not a:
        raise HTTPException(status_code=403, detail="You are not assigned to this class")


async def _is_privileged_marks(user, class_name):
    """Admin or an in-scope principal — the only roles allowed to correct published marks/publish results."""
    if user["role"] == "institution_admin":
        return True
    scope = await principal_scope(user)
    return bool(scope and (scope["whole_school"] or class_name in (scope["class_names"] or [])))


async def ensure_marks_access(user, assessment):
    """Phase 14 marks scope: admin, in-scope principal, the assigned SUBJECT teacher for this
    class+section+subject, or the CLASS TEACHER of the section. Everyone else → 403."""
    cn = assessment.get("class_name")
    asec = assessment.get("section") or ""
    if await _is_privileged_marks(user, cn):
        return
    if user["role"] != "teacher":
        raise HTTPException(status_code=403, detail="You are not allowed to access these marks")
    iid = user["institution_id"]
    # (a) assigned subject teacher — assignment section "" covers all sections; assessment "" = whole class
    async for ta in db.teacher_assignments.find({"institution_id": iid, "class_name": cn,
                                                 "subject": assessment.get("subject"), **_teacher_match(user)}):
        tsec = ta.get("section") or ""
        if asec == "" or tsec == "" or tsec == asec:
            return
    # (b) class teacher of the section
    async for s in db.sections.find({"institution_id": iid, "class_name": cn, "class_teacher_id": user["id"]}):
        if asec == "" or (s.get("name") or "") == asec:
            return
    raise HTTPException(status_code=403, detail="Only the subject teacher, class teacher, principal or admin can access these marks")


@api.get("/attendance/sheet")
async def attendance_sheet(class_name: str, section: str = "", date: str = "",
                           user: dict = Depends(require_roles("institution_admin", "teacher"))):
    await ensure_class_access(user, class_name, section)
    q = {"institution_id": user["institution_id"], "class_name": class_name}
    if section:
        q["section"] = section
    students = await db.students.find(q, {"_id": 0}).sort("first_name", 1).to_list(500)
    record = await db.attendance.find_one({"institution_id": user["institution_id"], "class_name": class_name,
                                           "section": section, "date": date}, {"_id": 0})
    return {"students": students, "record": record}


@api.post("/attendance/sheet")
async def save_attendance(payload: dict = Body(...),
                          user: dict = Depends(require_roles("institution_admin", "teacher"))):
    class_name, section, date = payload.get("class_name"), payload.get("section", ""), payload.get("date")
    if not class_name or not date:
        raise HTTPException(status_code=400, detail="Class and date are required")
    await ensure_class_access(user, class_name, section)
    entries = {k: v for k, v in (payload.get("entries") or {}).items() if v in ATT_STATUSES}
    key = {"institution_id": user["institution_id"], "class_name": class_name, "section": section, "date": date}
    existing = await db.attendance.find_one(key)
    if existing and existing.get("finalized") and user["role"] == "teacher":
        raise HTTPException(status_code=403, detail="Attendance is finalized. Ask an administrator to make corrections.")
    await db.attendance.update_one(key, {"$set": {**key, "entries": entries,
                                                  "finalized": bool(payload.get("finalized")),
                                                  "marked_by": user["email"], "updated_at": now_iso()},
                                         "$setOnInsert": {"id": str(uuid.uuid4()), "created_at": now_iso()}}, upsert=True)
    await audit(user, "update", "attendance", None, f"{class_name} {section} · {date}".replace("  ", " "))
    return await db.attendance.find_one(key, {"_id": 0})


@api.get("/attendance/records")
async def attendance_records(page: int = 1, limit: int = 20,
                             user: dict = Depends(require_roles("institution_admin", "teacher"))):
    query = {"institution_id": user["institution_id"]}
    if user["role"] == "teacher":
        scope = await principal_scope(user)
        if scope and scope["whole_school"]:
            pass
        elif scope:
            query["class_name"] = {"$in": scope["class_names"] or ["__none__"]}
        else:
            assigns = await db.teacher_assignments.find({"institution_id": user["institution_id"],
                                                         **_teacher_match(user)}).to_list(200)
            pairs = [{"class_name": a["class_name"], "section": a.get("section", "")} for a in assigns]
            if not pairs:
                return {"items": [], "total": 0, "page": 1, "pages": 1}
            query["$or"] = pairs
    total = await db.attendance.count_documents(query)
    skip = max(page - 1, 0) * limit
    items = await db.attendance.find(query, {"_id": 0}).sort("date", -1).skip(skip).to_list(limit)
    for it in items:
        entries = it.pop("entries", {}) or {}
        for st in ATT_STATUSES:
            it[st] = sum(1 for v in entries.values() if v == st)
    return {"items": items, "total": total, "page": page, "pages": max((total + limit - 1) // limit, 1)}


# ---------------- Marks ----------------

@api.get("/assessments/{aid}/marks")
async def get_marks(aid: str, user: dict = Depends(require_roles("institution_admin", "teacher"))):
    assessment = await db.assessments.find_one({"id": aid, "institution_id": user["institution_id"]}, {"_id": 0})
    if not assessment:
        raise HTTPException(status_code=404, detail="Assessment not found")
    await ensure_marks_access(user, assessment)
    q = {"institution_id": user["institution_id"]}
    if assessment.get("class_name"):
        q["class_name"] = assessment["class_name"]
    if assessment.get("section"):
        q["section"] = assessment["section"]
    students = await db.students.find(q, {"_id": 0}).sort("first_name", 1).to_list(500)
    marks = await db.marks.find({"assessment_id": aid}, {"_id": 0}).to_list(1000)
    can_correct = await _is_privileged_marks(user, assessment.get("class_name"))
    return {"assessment": assessment, "students": students, "marks": marks,
            "can_correct": can_correct, "locked": assessment.get("status") == "published" and not can_correct}


@api.post("/assessments/{aid}/marks")
async def save_marks(aid: str, payload: dict = Body(...),
                     user: dict = Depends(require_roles("institution_admin", "teacher"))):
    assessment = await db.assessments.find_one({"id": aid, "institution_id": user["institution_id"]})
    if not assessment:
        raise HTTPException(status_code=404, detail="Assessment not found")
    await ensure_marks_access(user, assessment)
    privileged = await _is_privileged_marks(user, assessment.get("class_name"))
    published = assessment.get("status") == "published"
    # After publish, teachers are locked out — only a principal/admin may CORRECT marks.
    if published and not privileged:
        raise HTTPException(status_code=403, detail="Results are published — only a principal or admin can correct marks.")
    try:
        max_marks = float(assessment.get("max_marks") or 100)
    except (TypeError, ValueError):
        max_marks = 100.0
    cleaned = []
    for e in payload.get("entries", []):
        status = e.get("status") if e.get("status") in ("present", "absent", "exempt") else "present"
        score = e.get("score")
        if status != "present" or score in (None, ""):
            score = None
        else:
            try:
                score = float(score)
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail="Scores must be numbers")
            if score < 0 or score > max_marks:
                raise HTTPException(status_code=400, detail=f"Scores must be between 0 and {max_marks:g}")
        cleaned.append({"student_id": e.get("student_id"), "score": score, "status": status})
    existing = {m["student_id"]: m for m in await db.marks.find({"assessment_id": aid}, {"_id": 0}).to_list(1000)}
    changes = 0
    for c in cleaned:
        prev = existing.get(c["student_id"])
        old_score = prev.get("score") if prev else None
        old_status = prev.get("status") if prev else None
        if prev is not None and old_score == c["score"] and old_status == c["status"]:
            continue  # unchanged
        await db.marks.update_one({"assessment_id": aid, "student_id": c["student_id"]},
                                  {"$set": {"assessment_id": aid, "student_id": c["student_id"],
                                            "score": c["score"], "status": c["status"],
                                            "institution_id": user["institution_id"], "updated_at": now_iso()},
                                   "$setOnInsert": {"id": str(uuid.uuid4())}}, upsert=True)
        # correction = editing a value that already existed, OR any edit on a published assessment
        is_correction = (prev is not None and prev.get("score") is not None) or published
        await db.mark_changes.insert_one({
            "id": str(uuid.uuid4()), "institution_id": user["institution_id"], "assessment_id": aid,
            "student_id": c["student_id"], "old_score": old_score, "new_score": c["score"],
            "old_status": old_status, "new_status": c["status"], "is_correction": bool(is_correction),
            "editor_id": user["id"], "editor_email": user.get("email"), "editor_role": user.get("role"),
            "timestamp": now_iso()})
        changes += 1
    await audit(user, "correct" if published else "update", "marks", aid,
                f"{assessment.get('name')} · {changes} change(s)" + (" [CORRECTION]" if published else ""))
    return {"message": "Marks saved", "changes": changes}


@api.get("/assessments/{aid}/history")
async def marks_history(aid: str, user: dict = Depends(require_roles("institution_admin", "teacher"))):
    assessment = await db.assessments.find_one({"id": aid, "institution_id": user["institution_id"]}, {"_id": 0})
    if not assessment:
        raise HTTPException(status_code=404, detail="Assessment not found")
    await ensure_marks_access(user, assessment)
    names = {s["id"]: f"{s.get('first_name', '')} {s.get('last_name', '')}".strip()
             for s in await db.students.find({"institution_id": user["institution_id"]}, {"_id": 0, "id": 1, "first_name": 1, "last_name": 1}).to_list(2000)}
    rows = await db.mark_changes.find({"assessment_id": aid}, {"_id": 0}).sort("timestamp", -1).to_list(2000)
    for r in rows:
        r["student_name"] = names.get(r["student_id"], "—")
    return {"history": rows, "assessment": {"name": assessment.get("name"), "subject": assessment.get("subject")}}


@api.post("/assessments/{aid}/publish")
async def publish_assessment(aid: str, payload: dict = Body(...),
                             user: dict = Depends(require_admin_or_principal)):
    a = await db.assessments.find_one({"id": aid, "institution_id": user["institution_id"]}, {"_id": 0})
    if not a:
        raise HTTPException(status_code=404, detail="Assessment not found")
    await guard_principal_class(user, a.get("class_name"))
    publish = bool(payload.get("publish"))
    status = "published" if publish else "draft"
    await db.assessments.update_one({"id": aid, "institution_id": user["institution_id"]},
                                    {"$set": {"status": status}})
    await audit(user, "update", "assessments", aid, f"marked {status}")
    return {"status": status}


# ---------------- Teacher workspace ----------------

@api.get("/teacher/overview")
async def teacher_overview(user: dict = Depends(require_roles("teacher"))):
    assigns = await db.teacher_assignments.find({"institution_id": user["institution_id"],
                                                 **_teacher_match(user)}, {"_id": 0}).to_list(200)
    pairs = {(a["class_name"], a.get("section", "")) for a in assigns}
    total_students = 0
    for cn, sec in pairs:
        q = {"institution_id": user["institution_id"], "class_name": cn}
        if sec:
            q["section"] = sec
        total_students += await db.students.count_documents(q)
    return {"assignments": assigns,
            "stats": {"classes": len(pairs),
                      "subjects": len({a.get("subject") for a in assigns if a.get("subject")}),
                      "students": total_students}}


@api.get("/teacher/students")
async def teacher_students(class_name: str, section: str = "",
                           user: dict = Depends(require_roles("teacher"))):
    await ensure_class_access(user, class_name, section)
    q = {"institution_id": user["institution_id"], "class_name": class_name}
    if section:
        q["section"] = section
    students = await db.students.find(q, {"_id": 0}).sort("first_name", 1).to_list(500)
    return {"students": students}


async def _attendance_counts(iid, class_name, section):
    counts = {}
    q = {"institution_id": iid, "class_name": class_name}
    if section:
        q["section"] = section
    async for sh in db.attendance.find(q):
        for stid, st in (sh.get("entries") or {}).items():
            c = counts.setdefault(stid, [0, 0])
            c[1] += 1
            if str(st).lower() in ("present", "p"):
                c[0] += 1
    return counts


@api.get("/teacher/my-class")
async def teacher_my_class(user: dict = Depends(require_roles("teacher"))):
    homerooms = await db.sections.find(
        {"institution_id": user["institution_id"], "class_teacher_id": user["id"]},
        {"_id": 0}).sort([("class_name", 1), ("name", 1)]).to_list(50)
    return {"homerooms": homerooms}


@api.get("/teacher/my-class/{section_id}")
async def teacher_my_class_detail(section_id: str, user: dict = Depends(require_roles("teacher"))):
    iid = user["institution_id"]
    sec = await db.sections.find_one({"id": section_id, "institution_id": iid, "class_teacher_id": user["id"]}, {"_id": 0})
    if not sec:
        raise HTTPException(status_code=403, detail="You are not the class teacher of this section")
    students = await db.students.find(
        {"institution_id": iid, "class_name": sec["class_name"], "section": sec["name"]},
        {"_id": 0}).sort("first_name", 1).to_list(500)
    counts = await _attendance_counts(iid, sec["class_name"], sec["name"])
    sids = [s["id"] for s in students]
    achievements = await db.achievements.find({"institution_id": iid, "student_id": {"$in": sids}}, {"_id": 0}) \
        .sort([("date", -1), ("created_at", -1)]).to_list(500)
    ach_counts = {}
    for a in achievements:
        ach_counts[a["student_id"]] = ach_counts.get(a["student_id"], 0) + 1
    out = []
    for s in students:
        p, t = counts.get(s["id"], [0, 0])
        out.append({**s, "attendance_pct": round(p / t * 100) if t else None,
                    "attendance_present": p, "attendance_total": t,
                    "achievements_count": ach_counts.get(s["id"], 0)})
    return {"section": sec, "students": out, "achievements": achievements}


async def _ensure_homeroom_student(user, student_id):
    iid = user["institution_id"]
    student = await db.students.find_one({"id": student_id, "institution_id": iid})
    if not student:
        raise HTTPException(status_code=400, detail="Student not found")
    sec = await db.sections.find_one({"institution_id": iid, "class_name": student.get("class_name"),
                                      "name": student.get("section"), "class_teacher_id": user["id"]})
    if not sec:
        raise HTTPException(status_code=403, detail="This student is not in your homeroom section")
    return student


@api.post("/teacher/achievements")
async def teacher_add_achievement(payload: dict = Body(...), user: dict = Depends(require_roles("teacher"))):
    iid = user["institution_id"]
    if not str(payload.get("title") or "").strip() or not payload.get("student_id"):
        raise HTTPException(status_code=400, detail="Student and title are required")
    student = await _ensure_homeroom_student(user, payload["student_id"])
    doc = {"id": str(uuid.uuid4()), "institution_id": iid, "created_at": now_iso(),
           "student_id": student["id"],
           "student_name": f"{student.get('first_name', '')} {student.get('last_name', '')}".strip(),
           "class_name": student.get("class_name"), "section": student.get("section"),
           "title": str(payload["title"]).strip(),
           "description": str(payload.get("description") or "").strip(),
           "date": payload.get("date") or now_iso()[:10],
           "awarded_by": user.get("name")}
    await db.achievements.insert_one(dict(doc))
    doc.pop("_id", None)
    await audit(user, "create", "achievements", doc["id"], doc["title"])
    return doc


@api.delete("/teacher/achievements/{ach_id}")
async def teacher_delete_achievement(ach_id: str, user: dict = Depends(require_roles("teacher"))):
    a = await db.achievements.find_one({"id": ach_id, "institution_id": user["institution_id"]})
    if not a:
        raise HTTPException(status_code=404, detail="Achievement not found")
    await _ensure_homeroom_student(user, a["student_id"])
    await db.achievements.delete_one({"id": ach_id})
    await audit(user, "delete", "achievements", ach_id, a.get("title"))
    return {"message": "Deleted"}


@api.get("/teacher/profile")
async def teacher_profile(user: dict = Depends(require_roles("teacher"))):
    iid = user["institution_id"]
    me = await db.users.find_one({"id": user["id"]}, {"_id": 0, "password_hash": 0})
    assigns = await db.teacher_assignments.find({"institution_id": iid, **_teacher_match(user)}, {"_id": 0}) \
        .sort([("class_name", 1), ("subject", 1)]).to_list(200)
    homerooms = await db.sections.find({"institution_id": iid, "class_teacher_id": user["id"]}, {"_id": 0}) \
        .sort([("class_name", 1), ("name", 1)]).to_list(50)
    student_ids = set()
    pairs = {(a["class_name"], a.get("section") or "") for a in assigns} | {(h["class_name"], h["name"]) for h in homerooms}
    for cn, sec in pairs:
        q = {"institution_id": iid, "class_name": cn}
        if sec:
            q["section"] = sec
        async for st in db.students.find(q, {"id": 1}):
            student_ids.add(st["id"])
    inst = await db.institutions.find_one({"id": iid}, {"_id": 0, "name": 1}) or {}
    return {"user": me, "assignments": assigns, "homerooms": homerooms,
            "total_students": len(student_ids),
            "subjects": sorted({a.get("subject") for a in assigns if a.get("subject")}),
            "institution_name": inst.get("name")}


@api.get("/teacher/assessments")
async def teacher_assessments(user: dict = Depends(require_roles("teacher"))):
    iid = user["institution_id"]
    assigns = await db.teacher_assignments.find({"institution_id": iid, **_teacher_match(user)}, {"_id": 0}).to_list(200)
    ors = []
    for a in assigns:
        c = {"class_name": a["class_name"]}
        if a.get("subject"):
            c["subject"] = a["subject"]
        if a.get("section"):
            c["$or"] = [{"section": a["section"]}, {"section": {"$in": [None, ""]}}]
        ors.append(c)
    if not ors:
        return {"assessments": []}
    rows = await db.assessments.find({"institution_id": iid, "$or": ors}, {"_id": 0}) \
        .sort("created_at", -1).to_list(200)
    return {"assessments": rows}


@api.get("/teacher/teaching-options")
async def teacher_teaching_options(user: dict = Depends(require_roles("teacher"))):
    """Distinct class+section+subject the teacher is assigned to — powers the homework/assignment
    create form. Only surfaces sections that actually have enrolled students, so teachers can't
    create homework/assignments into an empty section that no one would ever receive."""
    iid = user["institution_id"]
    assigns = await db.teacher_assignments.find({"institution_id": iid, **_teacher_match(user)}, {"_id": 0}).to_list(200)
    opts, seen = [], set()
    roster_cache = {}

    async def enrolled_count(cn, sec):
        key = (cn, sec)
        if key not in roster_cache:
            roster_cache[key] = await db.students.count_documents(
                {"institution_id": iid, "class_name": cn, "section": sec, "enrollment_status": "enrolled"})
        return roster_cache[key]

    async def add(cn, sec, subj):
        key = (cn, sec, subj)
        if not (sec and subj) or key in seen:
            return
        n = await enrolled_count(cn, sec)
        if n == 0:
            return  # skip empty sections — nothing to receive the work
        seen.add(key)
        opts.append({"class_name": cn, "section": sec, "subject": subj, "student_count": n})
    for a in assigns:
        subj = a.get("subject") or ""
        if a.get("section"):
            await add(a["class_name"], a["section"], subj)
        else:
            for s in await db.sections.find({"institution_id": iid, "class_name": a["class_name"]}, {"_id": 0, "name": 1}).to_list(50):
                await add(a["class_name"], s["name"], subj)
    return {"options": opts}


# ---------------- Teachers (unified account) ----------------
@api.post("/teachers")
async def create_teacher(payload: dict = Body(...), user: dict = Depends(require_admin_or_whole_principal)):
    iid = user["institution_id"]
    email = (payload.get("email") or "").strip().lower()
    if not payload.get("name") or not email or not payload.get("password"):
        raise HTTPException(status_code=400, detail="Name, email and a temporary password are required")
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Email already in use")
    uid = str(uuid.uuid4())
    doc = {"id": uid, "name": payload["name"], "email": email,
           "password_hash": hash_password(payload["password"]), "role": "teacher",
           "employee_id": payload.get("employee_id"), "gender": payload.get("gender"),
           "phone": payload.get("phone"), "specialization": payload.get("specialization"),
           "institution_id": iid, "status": payload.get("status") or "invited",
           "must_change_password": True, "created_at": now_iso()}
    await db.users.insert_one(dict(doc))
    await audit(user, "create", "teachers", uid, doc["name"])
    doc.pop("password_hash"); doc.pop("_id", None)
    return doc


@api.get("/teachers")
async def list_teachers(search: str = "", page: int = 1, limit: int = 20,
                        user: dict = Depends(require_admin_or_principal)):
    iid = user["institution_id"]
    query = {"institution_id": iid, "role": "teacher"}
    if search:
        rx = {"$regex": re.escape(search), "$options": "i"}
        query["$or"] = [{"name": rx}, {"email": rx}, {"employee_id": rx}]
    scope = await principal_scope(user)
    if scope and not scope["whole_school"]:
        cns = scope["class_names"] or ["__none__"]
        tas = await db.teacher_assignments.find({"institution_id": iid, "class_name": {"$in": cns}},
                                                {"teacher_id": 1, "teacher_email": 1}).to_list(5000)
        hrs = await db.sections.find({"institution_id": iid, "class_name": {"$in": cns}},
                                     {"class_teacher_id": 1}).to_list(5000)
        tids = [a["teacher_id"] for a in tas if a.get("teacher_id")] + [h["class_teacher_id"] for h in hrs if h.get("class_teacher_id")]
        emails = [a["teacher_email"] for a in tas if a.get("teacher_email")]
        query = {"$and": [query, {"$or": [{"id": {"$in": tids}}, {"email": {"$in": emails}}]}]}
    total = await db.users.count_documents(query)
    skip = (page - 1) * limit
    rows = await db.users.find(query, {"_id": 0, "password_hash": 0}).sort("name", 1).skip(skip).limit(limit).to_list(limit)
    for r in rows:
        assigns = await db.teacher_assignments.find(
            {"institution_id": iid, "$or": [{"teacher_id": r["id"]}, {"teacher_email": r["email"]}]}, {"_id": 0}).to_list(200)
        r["classes_count"] = len({(a["class_name"], a.get("section", "")) for a in assigns})
        r["subjects_count"] = len({a.get("subject") for a in assigns if a.get("subject")})
        r["is_class_teacher"] = await db.classes.count_documents({"institution_id": iid, "class_teacher": r["name"]}) > 0
    return {"items": rows, "total": total, "page": page, "pages": max((total + limit - 1) // limit, 1)}


@api.put("/teachers/{tid}")
async def update_teacher(tid: str, payload: dict = Body(...), user: dict = Depends(require_admin_or_whole_principal)):
    q = {"id": tid, "institution_id": user["institution_id"], "role": "teacher"}
    updates = {k: payload[k] for k in ("name", "employee_id", "gender", "phone", "specialization", "status") if k in payload}
    if payload.get("password"):
        updates["password_hash"] = hash_password(payload["password"])
        updates["must_change_password"] = True
    r = await db.users.update_one(q, {"$set": updates})
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Teacher not found")
    doc = await db.users.find_one(q, {"_id": 0, "password_hash": 0})
    await audit(user, "update", "teachers", tid, doc.get("name"))
    return doc


@api.delete("/teachers/{tid}")
async def delete_teacher(tid: str, user: dict = Depends(require_admin_or_whole_principal)):
    iid = user["institution_id"]
    q = {"id": tid, "institution_id": iid, "role": "teacher"}
    doc = await db.users.find_one(q)
    if not doc:
        raise HTTPException(status_code=404, detail="Teacher not found")
    await db.users.delete_one(q)
    await db.teacher_assignments.delete_many({"institution_id": iid, "$or": [{"teacher_id": tid}, {"teacher_email": doc["email"]}]})
    await db.principal_assignments.delete_many({"user_id": tid, "institution_id": iid})
    await audit(user, "delete", "teachers", tid, doc.get("name"))
    return {"message": "Deleted"}


# ---------------- Principal assignment management (institution_admin only) ----------------

class PrincipalAssignRequest(BaseModel):
    teacher_id: str
    scope_type: Literal["whole_school", "units"]
    unit_ids: List[str] = PField(default_factory=list)
    designation: Optional[Literal["principal", "assistant_principal"]] = None


class PrincipalUpdateRequest(BaseModel):
    scope_type: Optional[Literal["whole_school", "units"]] = None
    unit_ids: Optional[List[str]] = None
    designation: Optional[Literal["principal", "assistant_principal"]] = None


async def _validate_principal_units(iid: str, unit_ids: List[str]):
    if not unit_ids:
        raise HTTPException(status_code=400, detail="Select at least one academic unit (division)")
    found = await db.academic_units.find({"institution_id": iid, "id": {"$in": unit_ids}}, {"id": 1}).to_list(2000)
    if len({f["id"] for f in found}) != len(set(unit_ids)):
        raise HTTPException(status_code=400, detail="One or more selected academic units do not exist")


async def _scope_has_principal_title(iid, scope_type, unit_ids, exclude_user_id=None):
    """Is there already a designation='principal' assignment covering this scope?"""
    q = {"institution_id": iid, "designation": "principal"}
    if exclude_user_id:
        q["user_id"] = {"$ne": exclude_user_id}
    if scope_type == "whole_school":
        q["scope_type"] = "whole_school"
    else:
        q["scope_type"] = "units"
        q["unit_ids"] = {"$in": unit_ids}
    return await db.principal_assignments.find_one(q) is not None


async def _enrich_principal(pa: dict, iid: str) -> dict:
    t = await db.users.find_one({"id": pa["user_id"], "institution_id": iid},
                                {"_id": 0, "name": 1, "email": 1, "status": 1})
    units = []
    if pa.get("scope_type") == "units":
        units = await db.academic_units.find(
            {"institution_id": iid, "id": {"$in": pa.get("unit_ids") or []}},
            {"_id": 0, "id": 1, "name": 1, "code": 1}).to_list(2000)
    return {**pa, "teacher_name": (t or {}).get("name"), "teacher_email": (t or {}).get("email"),
            "teacher_status": (t or {}).get("status"), "units": units}


@api.get("/principals")
async def list_principals(user: dict = Depends(require_roles("institution_admin"))):
    iid = user["institution_id"]
    rows = await db.principal_assignments.find({"institution_id": iid}, {"_id": 0}).sort("created_at", -1).to_list(500)
    return {"items": [await _enrich_principal(r, iid) for r in rows]}


@api.post("/principals")
async def assign_principal(body: PrincipalAssignRequest,
                           user: dict = Depends(require_roles("institution_admin"))):
    iid = user["institution_id"]
    teacher = await db.users.find_one({"id": body.teacher_id, "institution_id": iid, "role": "teacher"})
    if not teacher:
        raise HTTPException(status_code=400, detail="Selected teacher not found in this institution")
    if await db.principal_assignments.find_one({"user_id": body.teacher_id, "institution_id": iid}):
        raise HTTPException(status_code=400,
                            detail="This teacher is already a principal. Update or revoke the existing assignment.")
    unit_ids = []
    if body.scope_type == "units":
        unit_ids = list(dict.fromkeys(body.unit_ids))
        await _validate_principal_units(iid, unit_ids)
    conflict = await _scope_has_principal_title(iid, body.scope_type, unit_ids)
    if body.designation == "principal" and conflict:
        raise HTTPException(status_code=400,
                            detail="A principal already holds this scope. Assign as assistant_principal or revoke the current principal first.")
    designation = body.designation or ("assistant_principal" if conflict else "principal")
    doc = {"id": str(uuid.uuid4()), "user_id": body.teacher_id, "institution_id": iid,
           "scope_type": body.scope_type, "unit_ids": unit_ids, "designation": designation,
           "assigned_by": user["email"], "created_at": now_iso()}
    await db.principal_assignments.insert_one(dict(doc))
    doc.pop("_id", None)
    await audit(user, "assign_principal", "principals", doc["id"], teacher.get("name"))
    return await _enrich_principal(doc, iid)


@api.put("/principals/{pid}")
async def update_principal(pid: str, body: PrincipalUpdateRequest,
                           user: dict = Depends(require_roles("institution_admin"))):
    iid = user["institution_id"]
    pa = await db.principal_assignments.find_one({"id": pid, "institution_id": iid}, {"_id": 0})
    if not pa:
        raise HTTPException(status_code=404, detail="Principal assignment not found")
    scope_type = body.scope_type or pa["scope_type"]
    unit_ids = pa.get("unit_ids") or []
    if body.unit_ids is not None:
        unit_ids = list(dict.fromkeys(body.unit_ids))
    if scope_type == "units":
        await _validate_principal_units(iid, unit_ids)
    else:
        unit_ids = []
    designation = body.designation or pa["designation"]
    conflict = await _scope_has_principal_title(iid, scope_type, unit_ids, exclude_user_id=pa["user_id"])
    if designation == "principal" and conflict:
        raise HTTPException(status_code=400, detail="A principal already holds this scope.")
    updates = {"scope_type": scope_type, "unit_ids": unit_ids, "designation": designation, "updated_at": now_iso()}
    await db.principal_assignments.update_one({"id": pid, "institution_id": iid}, {"$set": updates})
    doc = await db.principal_assignments.find_one({"id": pid, "institution_id": iid}, {"_id": 0})
    await audit(user, "update_principal", "principals", pid, pa.get("user_id"))
    return await _enrich_principal(doc, iid)


@api.delete("/principals/{pid}")
async def revoke_principal(pid: str, user: dict = Depends(require_roles("institution_admin"))):
    iid = user["institution_id"]
    pa = await db.principal_assignments.find_one({"id": pid, "institution_id": iid})
    if not pa:
        raise HTTPException(status_code=404, detail="Principal assignment not found")
    await db.principal_assignments.delete_one({"id": pid, "institution_id": iid})
    await audit(user, "revoke_principal", "principals", pid, pa.get("user_id"))
    return {"message": "Principal access revoked"}


@api.post("/auth/change-password")
async def change_password(payload: dict = Body(...), user: dict = Depends(get_current_user)):
    new = payload.get("new_password") or ""
    if user.get("pw_set_by_staff"):
        if not _pw_strong(new):
            raise HTTPException(status_code=400, detail=PW_RULE)
        if verify_password(new, user.get("password_hash") or ""):
            raise HTTPException(status_code=400, detail="Choose a new password — not the one the school gave you")
    if len(new) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
    await db.users.update_one({"id": user["id"]}, {"$set": {"password_hash": hash_password(new), "must_change_password": False,
                                                            "password_changed_at": now_iso()}, "$unset": {"pw_set_by_staff": ""}})
    if user.get("pw_set_by_staff"):
        await audit(user, "password_changed_after_reset", "users", user["id"], user.get("name"))
    return {"message": "Password updated"}


# ---------------- Global search ----------------

@api.get("/search")
async def global_search(q: str = "", user: dict = Depends(get_current_user)):
    if len(q.strip()) < 2:
        return {"groups": []}
    rx = {"$regex": q.strip(), "$options": "i"}
    groups = []

    def person(r):
        return f"{r.get('first_name', '')} {r.get('last_name', '')}".strip()

    def named(r):
        return r.get("name", "")

    async def collect(col, fields, label, path, name_fn):
        query = {"$or": [{f: rx} for f in fields]}
        if user["role"] != "platform_admin":
            query["institution_id"] = user["institution_id"]
        rows = await db[col].find(query, {"_id": 0, "password_hash": 0}).to_list(5)
        if rows:
            groups.append({"label": label, "items": [
                {"id": r["id"], "label": name_fn(r),
                 "sub": r.get("admission_no") or r.get("email") or r.get("code") or r.get("city") or "",
                 "path": f"{path}?q={quote(name_fn(r))}"} for r in rows]})

    if user["role"] == "platform_admin":
        await collect("institutions", ["name", "code", "city"], "Institutions", "/platform/institutions", named)
        await collect("plans", ["name", "code"], "Plans", "/platform/plans", named)
    elif user["role"] == "institution_admin":
        await collect("students", ["first_name", "last_name", "admission_no"], "Students", "/app/students", person)
        await collect("teachers", ["first_name", "last_name", "employee_id"], "Teachers", "/app/teachers", person)
        await collect("users", ["name", "email"], "Users", "/app/users", named)
        await collect("classes", ["name"], "Classes", "/app/classes", named)
        await collect("subjects", ["name", "code"], "Subjects", "/app/subjects", named)
        await collect("assessments", ["name"], "Assessments", "/app/assessments", named)
    elif user["role"] == "teacher":
        assigns = await db.teacher_assignments.find({"institution_id": user["institution_id"],
                                                     **_teacher_match(user)}).to_list(200)
        classes = list({a["class_name"] for a in assigns})
        if classes:
            rows = await db.students.find({"institution_id": user["institution_id"],
                                           "class_name": {"$in": classes},
                                           "$or": [{"first_name": rx}, {"last_name": rx}, {"admission_no": rx}]},
                                          {"_id": 0}).to_list(8)
            if rows:
                groups.append({"label": "My students", "items": [
                    {"id": r["id"], "label": person(r),
                     "sub": f"{r.get('class_name', '')} {r.get('section', '')}".strip(),
                     "path": "/teacher/students"} for r in rows]})
    return {"groups": groups}


@api.get("/")
async def root():
    return {"message": "LNMO API", "status": "ok"}


# ================= Phase 25 — COMMUNICATION SYSTEM (foundation) =================
# Provider-abstracted messaging engine. ALL future modules call send_message(...).
# TEST MODE: StubProvider logs to `messages` and simulates queued→sent→delivered.
# When real Twilio creds are saved, TwilioProvider is selected; absent creds → "not_configured".
# SECURITY: Twilio SID/token/secrets are NEVER returned to any client — masked only.

COMM_CHANNELS = ("whatsapp", "sms")
COMM_DEFAULT_QUOTA_WHATSAPP = 1000
COMM_DEFAULT_QUOTA_SMS = 100


def _mask_secret(val):
    if not val:
        return ""
    s = str(val)
    return ("•" * max(0, len(s) - 4)) + s[-4:] if len(s) > 4 else "••••"


async def _platform_config():
    cfg = await db.platform_config.find_one({"id": "singleton"}, {"_id": 0})
    if not cfg:
        cfg = {"id": "singleton",
               "twilio": {"account_sid": "", "auth_token": "", "whatsapp_sender": "", "sms_sender": ""},
               "channels": {"sms_enabled": True, "whatsapp_enabled": True},
               "active_provider": "stub", "updated_at": now_iso()}
        await db.platform_config.insert_one(dict(cfg))
    else:
        cfg.setdefault("twilio", {"account_sid": "", "auth_token": "", "whatsapp_sender": "", "sms_sender": ""})
        cfg.setdefault("channels", {"sms_enabled": True, "whatsapp_enabled": True})
        cfg.setdefault("active_provider", "stub")
    return cfg


def _mask_twilio(tw):
    tw = tw or {}
    return {"account_sid": _mask_secret(tw.get("account_sid")),
            "auth_token": _mask_secret(tw.get("auth_token")),
            "whatsapp_sender": tw.get("whatsapp_sender") or "",
            "sms_sender": tw.get("sms_sender") or "",
            "configured": bool(tw.get("account_sid") and tw.get("auth_token"))}


def _default_comm():
    return {"sender_mode": "lnmo",
            "own_twilio": {"account_sid": "", "auth_token": "", "whatsapp_sender": "", "sms_sender": ""},
            "quota": {"whatsapp": {"limit": COMM_DEFAULT_QUOTA_WHATSAPP, "used": 0},
                      "sms": {"limit": COMM_DEFAULT_QUOTA_SMS, "used": 0}},
            "cycle_start": now_iso()[:10]}


async def _institution_comm(iid):
    inst = await db.institutions.find_one({"id": iid}, {"_id": 0, "comm": 1, "name": 1})
    if not inst:
        raise HTTPException(status_code=404, detail="Institution not found")
    comm = inst.get("comm")
    if not comm:
        comm = _default_comm()
        await db.institutions.update_one({"id": iid}, {"$set": {"comm": comm}})
    else:
        # lazy-heal missing keys
        base = _default_comm()
        for k, v in base.items():
            comm.setdefault(k, v)
        for ch in COMM_CHANNELS:
            comm["quota"].setdefault(ch, {"limit": COMM_DEFAULT_QUOTA_WHATSAPP if ch == "whatsapp" else COMM_DEFAULT_QUOTA_SMS, "used": 0})
    return inst.get("name"), comm


# ---- Provider layer ----
class CommProvider:
    name = "base"

    async def deliver(self, channel, to_phone, body):
        raise NotImplementedError


class StubProvider(CommProvider):
    """TEST MODE provider — never calls a network. Reports queued and the caller simulates progression."""
    name = "stub"

    async def deliver(self, channel, to_phone, body):
        return {"ok": True, "status": "queued", "provider": "stub"}


class TwilioProvider(CommProvider):
    name = "twilio"

    def __init__(self, twilio_cfg):
        self.cfg = twilio_cfg or {}

    def _ready(self, channel):
        if not (self.cfg.get("account_sid") and self.cfg.get("auth_token")):
            return False
        return bool(self.cfg.get("whatsapp_sender") if channel == "whatsapp" else self.cfg.get("sms_sender"))

    async def deliver(self, channel, to_phone, body):
        if not self._ready(channel):
            return {"ok": False, "status": "not_configured", "provider": "twilio",
                    "error": "Twilio sender for this channel is not configured yet"}
        # Real Twilio REST send happens here once creds are live (Phase 25 ships TEST MODE default).
        return {"ok": True, "status": "queued", "provider": "twilio"}


async def _select_provider(comm, pcfg):
    """Own-sender school → TwilioProvider(own creds). Otherwise platform active_provider."""
    if comm.get("sender_mode") == "own":
        return TwilioProvider(comm.get("own_twilio"))
    if pcfg.get("active_provider") == "twilio":
        return TwilioProvider(pcfg.get("twilio"))
    return StubProvider()


async def send_message(institution_id, channel, recipients, body=None, template_id=None,
                       vars=None, module="manual", meta=None, actor=None, media_url=None):
    """Central messaging entry point every module uses. Enforces channel-enabled + quota,
    logs each message to `messages`, and (TEST MODE) simulates delivery progression.
    recipients: list of {name, phone}. Returns a per-batch summary."""
    if channel not in COMM_CHANNELS:
        raise HTTPException(status_code=400, detail="channel must be 'whatsapp' or 'sms'")
    pcfg = await _platform_config()
    ch_enabled = pcfg["channels"].get(f"{channel}_enabled", True)
    if not ch_enabled:
        return {"ok": False, "code": "channel_disabled", "sent": 0,
                "message": f"{channel.upper()} is disabled by the platform"}
    _, comm = await _institution_comm(institution_id)
    provider = await _select_provider(comm, pcfg)
    quota = comm["quota"][channel]
    remaining = max(0, quota["limit"] - quota["used"])
    results, sent = [], 0
    for r in (recipients or []):
        if remaining <= 0:
            results.append({"recipient_phone": r.get("phone"), "status": "rejected", "code": "quota_exceeded"})
            continue
        r_body = r.get("body") or body or template_id or ""
        res = await provider.deliver(channel, r.get("phone"), r_body)
        now = now_iso()
        status = res.get("status", "queued")
        history = [{"status": status, "at": now}]
        doc = {"id": str(uuid.uuid4()), "institution_id": institution_id, "channel": channel,
               "direction": "outbound",
               "sender_mode": comm.get("sender_mode"), "provider": res.get("provider"),
               "recipient_name": r.get("name"), "recipient_phone": r.get("phone"),
               "recipient_student_id": r.get("student_id"),
               "body": r.get("body") or body, "template_id": template_id,
               "media_url": media_url, "has_media": bool(media_url),
               "vars": r.get("vars") or vars or {}, "module": module,
               "status": status, "error": res.get("error"), "meta": {**(meta or {}), **(r.get("meta") or {})},
               "created_at": now, "status_history": history}
        if res.get("ok"):
            # TEST MODE / optimistic progression: queued → sent → delivered
            for nxt in ("sent", "delivered"):
                history.append({"status": nxt, "at": now_iso()})
            doc["status"] = "delivered"
            doc["status_history"] = history
            quota["used"] += 1
            remaining -= 1
            sent += 1
        await db.messages.insert_one(dict(doc))
        results.append({"message_id": doc["id"], "recipient_phone": r.get("phone"),
                        "status": doc["status"], "code": res.get("code")})
    await db.institutions.update_one({"id": institution_id}, {"$set": {f"comm.quota.{channel}.used": quota["used"]}})
    if actor:
        await audit(actor, f"comm_send_{channel}", "messages", None, f"{sent} sent via {module}", institution_id)
    return {"ok": True, "sent": sent, "requested": len(recipients or []),
            "remaining": remaining, "results": results}


# ---- Platform console endpoints ----
@api.get("/platform/comm-config")
async def get_platform_comm_config(user: dict = Depends(require_roles("platform_admin"))):
    cfg = await _platform_config()
    return {"twilio": _mask_twilio(cfg.get("twilio")), "channels": cfg.get("channels"),
            "active_provider": cfg.get("active_provider"), "updated_at": cfg.get("updated_at")}


class PlatformCommUpdate(BaseModel):
    account_sid: Optional[str] = None
    auth_token: Optional[str] = None
    whatsapp_sender: Optional[str] = None
    sms_sender: Optional[str] = None
    sms_enabled: Optional[bool] = None
    whatsapp_enabled: Optional[bool] = None
    active_provider: Optional[str] = None  # stub | twilio


@api.put("/platform/comm-config")
async def update_platform_comm_config(body: PlatformCommUpdate, user: dict = Depends(require_roles("platform_admin"))):
    cfg = await _platform_config()
    tw = cfg.get("twilio") or {}
    # only overwrite secret fields when a non-masked, non-empty value is supplied
    for f in ("account_sid", "auth_token", "whatsapp_sender", "sms_sender"):
        v = getattr(body, f)
        if v is not None and v != "" and "•" not in v:
            tw[f] = v.strip()
    ch = cfg.get("channels") or {}
    if body.sms_enabled is not None:
        ch["sms_enabled"] = body.sms_enabled
    if body.whatsapp_enabled is not None:
        ch["whatsapp_enabled"] = body.whatsapp_enabled
    ap = cfg.get("active_provider", "stub")
    if body.active_provider in ("stub", "twilio"):
        ap = body.active_provider
    await db.platform_config.update_one({"id": "singleton"},
                                        {"$set": {"twilio": tw, "channels": ch, "active_provider": ap, "updated_at": now_iso()}})
    await audit(user, "update_comm_config", "platform_config", "singleton", "comm config")
    return await get_platform_comm_config(user)


@api.post("/platform/comm-test")
async def platform_comm_test(body: dict = Body(...), user: dict = Depends(require_roles("platform_admin"))):
    channel = body.get("channel", "whatsapp")
    phone = (body.get("phone") or "").strip()
    if not phone:
        raise HTTPException(status_code=400, detail="A test phone number is required")
    if channel not in COMM_CHANNELS:
        raise HTTPException(status_code=400, detail="channel must be 'whatsapp' or 'sms'")
    pcfg = await _platform_config()
    provider = TwilioProvider(pcfg.get("twilio")) if pcfg.get("active_provider") == "twilio" else StubProvider()
    res = await provider.deliver(channel, phone, body.get("body") or "LNMO test message")
    await audit(user, "comm_test", "messages", None, f"{channel} test via {provider.name}")
    return {"provider": provider.name, "status": res.get("status"), "ok": res.get("ok"),
            "error": res.get("error"), "test_mode": provider.name == "stub"}


@api.get("/platform/comm/schools")
async def platform_comm_schools(user: dict = Depends(require_roles("platform_admin"))):
    out = []
    for inst in await db.institutions.find({}, {"_id": 0, "id": 1, "name": 1, "comm": 1}).to_list(2000):
        comm = inst.get("comm") or _default_comm()
        out.append({"id": inst["id"], "name": inst.get("name"),
                    "sender_mode": comm.get("sender_mode", "lnmo"),
                    "quota": comm.get("quota", _default_comm()["quota"])})
    return {"schools": out}


class SchoolCommUpdate(BaseModel):
    whatsapp_limit: Optional[int] = PField(default=None, ge=0)
    sms_limit: Optional[int] = PField(default=None, ge=0)
    sender_mode: Optional[str] = None  # lnmo | own


@api.put("/platform/comm/schools/{iid}")
async def platform_update_school_comm(iid: str, body: SchoolCommUpdate, user: dict = Depends(require_roles("platform_admin"))):
    _, comm = await _institution_comm(iid)
    if body.whatsapp_limit is not None:
        comm["quota"]["whatsapp"]["limit"] = body.whatsapp_limit
    if body.sms_limit is not None:
        comm["quota"]["sms"]["limit"] = body.sms_limit
    if body.sender_mode in ("lnmo", "own"):
        comm["sender_mode"] = body.sender_mode
    await db.institutions.update_one({"id": iid}, {"$set": {"comm": comm}})
    await audit(user, "update_school_comm", "institutions", iid, "comm quota/mode", iid)
    return {"id": iid, "sender_mode": comm["sender_mode"], "quota": comm["quota"]}


@api.get("/platform/comm/requests")
async def platform_comm_requests(status: str = "pending", user: dict = Depends(require_roles("platform_admin"))):
    q = {} if status == "all" else {"status": status}
    reqs = await db.credit_requests.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)
    names = {i["id"]: i.get("name") for i in await db.institutions.find({}, {"_id": 0, "id": 1, "name": 1}).to_list(2000)}
    for r in reqs:
        r["institution_name"] = names.get(r["institution_id"])
    return {"requests": reqs}


@api.post("/platform/comm/requests/{req_id}/approve")
async def platform_approve_request(req_id: str, user: dict = Depends(require_roles("platform_admin"))):
    req = await db.credit_requests.find_one({"id": req_id}, {"_id": 0})
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    if req["status"] != "pending":
        raise HTTPException(status_code=400, detail="Request already decided")
    _, comm = await _institution_comm(req["institution_id"])
    ch = req["channel"]
    comm["quota"][ch]["limit"] = comm["quota"][ch]["limit"] + req["requested_additional"]
    await db.institutions.update_one({"id": req["institution_id"]}, {"$set": {f"comm.quota.{ch}.limit": comm['quota'][ch]['limit']}})
    await db.credit_requests.update_one({"id": req_id}, {"$set": {"status": "approved", "decided_by": user.get("email"), "decided_at": now_iso()}})
    await audit(user, "approve_credit", "credit_requests", req_id, f"+{req['requested_additional']} {ch}", req["institution_id"])
    return {"id": req_id, "status": "approved", "new_limit": comm["quota"][ch]["limit"]}


@api.post("/platform/comm/requests/{req_id}/reject")
async def platform_reject_request(req_id: str, user: dict = Depends(require_roles("platform_admin"))):
    req = await db.credit_requests.find_one({"id": req_id}, {"_id": 0})
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    if req["status"] != "pending":
        raise HTTPException(status_code=400, detail="Request already decided")
    await db.credit_requests.update_one({"id": req_id}, {"$set": {"status": "rejected", "decided_by": user.get("email"), "decided_at": now_iso()}})
    await audit(user, "reject_credit", "credit_requests", req_id, req["channel"], req["institution_id"])
    return {"id": req_id, "status": "rejected"}


# ---- School console endpoints ----
@api.get("/comm/status")
async def comm_status(user: dict = Depends(require_admin_or_principal)):
    iid = user["institution_id"]
    name, comm = await _institution_comm(iid)
    pcfg = await _platform_config()
    def chan(ch):
        q = comm["quota"][ch]
        rem = max(0, q["limit"] - q["used"])
        return {"limit": q["limit"], "used": q["used"], "remaining": rem,
                "warn": q["limit"] > 0 and q["used"] / q["limit"] >= 0.8}
    if comm.get("sender_mode") == "own":
        own = comm.get("own_twilio") or {}
        connected = bool(own.get("account_sid") and own.get("auth_token"))
        conn = {"mode": "own", "connected": connected,
                "label": "Your Twilio sender" + (" · Connected" if connected else " · Not connected"),
                "own_twilio": {"account_sid": _mask_secret(own.get("account_sid")),
                               "whatsapp_sender": own.get("whatsapp_sender") or "",
                               "sms_sender": own.get("sms_sender") or ""}}
    else:
        test_mode = pcfg.get("active_provider") != "twilio"
        conn = {"mode": "lnmo", "connected": True,
                "label": "LNMO WhatsApp/SMS — " + ("Connected (Test Mode)" if test_mode else "Connected"),
                "test_mode": test_mode}
    return {"institution": name, "connection": conn,
            "channels": pcfg.get("channels"),
            "whatsapp": chan("whatsapp"), "sms": chan("sms")}


class CreditRequestBody(BaseModel):
    channel: str
    amount: int = PField(ge=1)
    note: Optional[str] = ""


@api.post("/comm/request-credit")
async def comm_request_credit(body: CreditRequestBody, user: dict = Depends(require_admin_or_principal)):
    if body.channel not in COMM_CHANNELS:
        raise HTTPException(status_code=400, detail="channel must be 'whatsapp' or 'sms'")
    iid = user["institution_id"]
    _, comm = await _institution_comm(iid)
    q = comm["quota"][body.channel]
    req = {"id": str(uuid.uuid4()), "institution_id": iid, "channel": body.channel,
           "current_limit": q["limit"], "current_used": q["used"], "requested_additional": body.amount,
           "note": (body.note or "").strip(), "status": "pending", "requested_by": user.get("email"),
           "decided_by": None, "decided_at": None, "created_at": now_iso()}
    await db.credit_requests.insert_one(dict(req))
    await audit(user, "request_credit", "credit_requests", req["id"], f"+{body.amount} {body.channel}", iid)
    return {k: v for k, v in req.items() if k != "_id"}


@api.get("/comm/history")
async def comm_history(page: int = 1, limit: int = 20, direction: str = None, user: dict = Depends(require_admin_or_principal)):
    iid = user["institution_id"]
    q = {"institution_id": iid}
    if direction in ("inbound", "outbound"):
        q["direction"] = direction
    total = await db.messages.count_documents(q)
    skip = max(0, (page - 1) * limit)
    msgs = await db.messages.find(q, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    return {"messages": msgs, "total": total, "page": page, "limit": limit}


class SenderModeBody(BaseModel):
    sender_mode: str  # lnmo | own
    account_sid: Optional[str] = None
    auth_token: Optional[str] = None
    whatsapp_sender: Optional[str] = None
    sms_sender: Optional[str] = None


@api.put("/comm/sender-mode")
async def comm_sender_mode(body: SenderModeBody, user: dict = Depends(require_admin_or_principal)):
    if body.sender_mode not in ("lnmo", "own"):
        raise HTTPException(status_code=400, detail="sender_mode must be 'lnmo' or 'own'")
    iid = user["institution_id"]
    _, comm = await _institution_comm(iid)
    comm["sender_mode"] = body.sender_mode
    if body.sender_mode == "own":
        own = comm.get("own_twilio") or {}
        for f in ("account_sid", "auth_token", "whatsapp_sender", "sms_sender"):
            v = getattr(body, f)
            if v is not None and v != "" and "•" not in v:
                own[f] = v.strip()
        comm["own_twilio"] = own
    await db.institutions.update_one({"id": iid}, {"$set": {"comm": comm}})
    await audit(user, "set_sender_mode", "institutions", iid, body.sender_mode, iid)
    return await comm_status(user)


# ==========================================================================
# PHASE 26 — Communication part 2: templates, send flows, delivery webhooks
# ==========================================================================
COMM_ALLOWED_VARS = ("school_name", "student_name", "parent_name", "class", "exam_name",
                     "exam_date", "homework_title", "due_date", "amount", "secure_link")
COMM_TEMPLATE_CATEGORIES = ("announcement", "exam", "homework", "fee", "attendance", "general")
COMM_SEED_TEMPLATES = [
    {"name": "Announcement", "category": "announcement", "channel": "both",
     "body": "Dear {{parent_name}}, {{school_name}} has a new announcement for {{class}}. Please open the school app for details."},
    {"name": "Exam Alert", "category": "exam", "channel": "both",
     "body": "Dear {{parent_name}}, {{exam_name}} for {{class}} is scheduled on {{exam_date}}. — {{school_name}}"},
    {"name": "Homework Alert", "category": "homework", "channel": "both",
     "body": "Dear {{parent_name}}, new homework '{{homework_title}}' for {{student_name}} ({{class}}) is due {{due_date}}. — {{school_name}}"},
    {"name": "Fee Reminder", "category": "fee", "channel": "both",
     "body": "Dear {{parent_name}}, a fee of {{amount}} for {{student_name}} is due on {{due_date}}. View: {{secure_link}} — {{school_name}}"},
    {"name": "Report Card", "category": "general", "channel": "both",
     "body": "Dear {{parent_name}}, the report card for {{student_name}} ({{class}}) is ready. {{secure_link}} — {{school_name}}"},
    {"name": "Parent invite", "category": "general", "channel": "both",
     "body": "Dear {{parent_name}}, welcome to {{school_name}} on the school app. Set up your parent account here (valid 72h): {{secure_link}}"},
]


def _render_template(body: str, values: dict) -> str:
    """Substitute ONLY whitelisted {{var}} tokens. Unknown tokens are left untouched
    (no eval, no arbitrary key substitution → injection-safe)."""
    out = body or ""
    for key in COMM_ALLOWED_VARS:
        out = out.replace("{{" + key + "}}", str(values.get(key, "")))
    return out


def _make_secure_link(institution_id: str, ref: str, ttl_hours: int = 72, path: str = None, ct: str = None) -> str:
    exp = int((datetime.now(timezone.utc) + timedelta(hours=ttl_hours)).timestamp())
    body = {"iid": institution_id, "ref": ref, "exp": exp}
    if path:
        body["path"] = path
        body["ct"] = ct or "application/octet-stream"
    payload = json.dumps(body, separators=(",", ":"))
    raw = base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")
    sig = hmac.new(JWT_SECRET.encode(), raw.encode(), hashlib.sha256).hexdigest()[:16]
    return f"{raw}.{sig}"


def _secure_link_url(institution_id, ref, path=None, ct=None, ttl_hours=72):
    api_base = os.environ.get("PUBLIC_BASE_URL") or os.environ.get("REACT_APP_BACKEND_URL", "")
    return f"{api_base}/api/comm/dl/{_make_secure_link(institution_id, ref, ttl_hours, path, ct)}"


def _verify_secure_link(token: str):
    try:
        raw, sig = token.rsplit(".", 1)
        expect = hmac.new(JWT_SECRET.encode(), raw.encode(), hashlib.sha256).hexdigest()[:16]
        if not hmac.compare_digest(sig, expect):
            return None
        pad = "=" * (-len(raw) % 4)
        data = json.loads(base64.urlsafe_b64decode((raw + pad).encode()).decode())
        if data.get("exp", 0) < int(datetime.now(timezone.utc).timestamp()):
            return None
        return data
    except Exception:
        return None


async def _comm_scope_class_names(user):
    """Class names this admin/principal may message. None = whole institution."""
    scope = await principal_scope(user)
    if not scope or scope.get("whole_school"):
        return None
    return set(scope.get("class_names") or [])


async def _comm_resolve_classes(iid, target: dict, allowed: set):
    """Resolve a target spec to a set of in-scope class names. Raises 403 on out-of-scope."""
    names = set()
    if target.get("all"):
        q = {"institution_id": iid}
        for c in await db.classes.find(q, {"_id": 0, "name": 1}).to_list(5000):
            names.add(c["name"])
    else:
        unit_ids = target.get("division_ids") or []
        if unit_ids:
            for c in await db.classes.find({"institution_id": iid, "academic_unit_id": {"$in": unit_ids}},
                                           {"_id": 0, "name": 1}).to_list(5000):
                names.add(c["name"])
        class_ids = target.get("class_ids") or []
        if class_ids:
            for c in await db.classes.find({"institution_id": iid, "id": {"$in": class_ids}},
                                           {"_id": 0, "name": 1}).to_list(5000):
                names.add(c["name"])
        for n in (target.get("class_names") or []):
            names.add(n)
    if allowed is not None:
        bad = names - allowed
        if bad:
            raise HTTPException(status_code=403, detail=f"Out of scope: {', '.join(sorted(bad))}")
        names &= allowed
    return names


async def _comm_resolve_recipients(iid, school_name, class_names, base_vars):
    """Guardians of enrolled students in the given classes. Students without a
    guardian_phone are returned as skipped[]."""
    recipients, skipped = [], []
    if not class_names:
        return recipients, skipped
    cur = db.students.find({"institution_id": iid, "class_name": {"$in": list(class_names)},
                            "enrollment_status": "enrolled"}, {"_id": 0})
    for s in await cur.to_list(20000):
        sname = f"{s.get('first_name', '')} {s.get('last_name', '')}".strip()
        cls = s.get("class_name") + (f" {s.get('section')}" if s.get("section") else "")
        phone = str(s.get("guardian_phone") or "").strip()
        if not phone:
            skipped.append({"student_id": s.get("id"), "student_name": sname, "class": cls})
            continue
        vrs = dict(base_vars)
        vrs.update({"school_name": school_name or "", "student_name": sname,
                    "parent_name": s.get("guardian_name") or "Parent", "class": cls})
        recipients.append({"name": s.get("guardian_name") or "Parent", "phone": phone,
                           "student_id": s.get("id"), "vars": vrs,
                           "meta": {"student_name": sname, "class": cls}})
    return recipients, skipped


async def _comm_get_template(iid, template_id):
    """A school can use its own templates or LNMO global ones."""
    t = await db.comm_templates.find_one(
        {"id": template_id, "$or": [{"institution_id": iid}, {"institution_id": None}]}, {"_id": 0})
    return t


# ---- Template endpoints (school) ----
class TemplateBody(BaseModel):
    name: str
    category: str
    channel: str  # whatsapp | sms | both
    body: str


@api.get("/comm/templates")
async def comm_templates(user: dict = Depends(require_admin_or_principal)):
    iid = user["institution_id"]
    rows = await db.comm_templates.find(
        {"$or": [{"institution_id": iid}, {"institution_id": None}]}, {"_id": 0}).sort("name", 1).to_list(500)
    for r in rows:
        r["scope"] = "global" if r.get("institution_id") is None else "school"
    return {"templates": rows, "variables": list(COMM_ALLOWED_VARS)}


@api.post("/comm/templates/{template_id}/clone")
async def comm_clone_template(template_id: str, user: dict = Depends(require_admin_or_principal)):
    iid = user["institution_id"]
    src = await db.comm_templates.find_one({"id": template_id, "institution_id": None}, {"_id": 0})
    if not src:
        raise HTTPException(status_code=404, detail="Global template not found")
    doc = {"id": str(uuid.uuid4()), "institution_id": iid, "name": src["name"] + " (copy)",
           "category": src["category"], "channel": src["channel"], "body": src["body"],
           "status": "approved", "cloned_from": template_id, "created_by": user.get("email"),
           "created_at": now_iso()}
    await db.comm_templates.insert_one(dict(doc))
    await audit(user, "clone_template", "comm_templates", doc["id"], src["name"], iid)
    doc.pop("_id", None)
    return doc


# ---- Template endpoints (platform / global) ----
@api.get("/platform/comm/templates")
async def platform_templates(user: dict = Depends(require_roles("platform_admin"))):
    rows = await db.comm_templates.find({"institution_id": None}, {"_id": 0}).sort("name", 1).to_list(500)
    return {"templates": rows}


@api.post("/platform/comm/templates")
async def platform_create_template(body: TemplateBody, user: dict = Depends(require_roles("platform_admin"))):
    if body.category not in COMM_TEMPLATE_CATEGORIES:
        raise HTTPException(status_code=400, detail="Invalid category")
    if body.channel not in ("whatsapp", "sms", "both"):
        raise HTTPException(status_code=400, detail="Invalid channel")
    doc = {"id": str(uuid.uuid4()), "institution_id": None, "name": body.name.strip(),
           "category": body.category, "channel": body.channel, "body": body.body,
           "status": "approved", "created_by": user.get("email"), "created_at": now_iso()}
    await db.comm_templates.insert_one(dict(doc))
    await audit(user, "create_global_template", "comm_templates", doc["id"], body.name)
    doc.pop("_id", None)
    return doc


class TemplateStatusBody(BaseModel):
    status: str  # approved | pending | disabled


@api.put("/platform/comm/templates/{template_id}")
async def platform_update_template(template_id: str, body: TemplateStatusBody,
                                   user: dict = Depends(require_roles("platform_admin"))):
    if body.status not in ("approved", "pending", "disabled"):
        raise HTTPException(status_code=400, detail="Invalid status")
    r = await db.comm_templates.update_one({"id": template_id, "institution_id": None},
                                           {"$set": {"status": body.status}})
    if not r.matched_count:
        raise HTTPException(status_code=404, detail="Template not found")
    await audit(user, "update_global_template", "comm_templates", template_id, body.status)
    return {"id": template_id, "status": body.status}


# ---- Audiences (target picker) ----
@api.get("/comm/audiences")
async def comm_audiences(user: dict = Depends(require_admin_or_principal)):
    iid = user["institution_id"]
    allowed = await _comm_scope_class_names(user)
    q = {"institution_id": iid}
    classes = await db.classes.find(q, {"_id": 0, "id": 1, "name": 1, "academic_unit_id": 1,
                                        "academic_unit_name": 1}).sort("name", 1).to_list(5000)
    out_classes, divisions = [], {}
    for c in classes:
        if allowed is not None and c["name"] not in allowed:
            continue
        cnt = await db.students.count_documents({"institution_id": iid, "class_name": c["name"],
                                                 "enrollment_status": "enrolled"})
        out_classes.append({"id": c["id"], "name": c["name"], "student_count": cnt,
                            "division_id": c.get("academic_unit_id"),
                            "division_name": c.get("academic_unit_name")})
        if c.get("academic_unit_id"):
            divisions.setdefault(c["academic_unit_id"],
                                 {"id": c["academic_unit_id"], "name": c.get("academic_unit_name"), "student_count": 0})
            divisions[c["academic_unit_id"]]["student_count"] += cnt
    return {"classes": out_classes, "divisions": list(divisions.values())}


# ---- Compose + send ----
class CommSendBody(BaseModel):
    channel: str                       # whatsapp | sms
    template_id: Optional[str] = None
    body: Optional[str] = None         # free-text (SMS only)
    target: dict                       # {class_ids[]|division_ids[]|all}
    vars: Optional[dict] = {}
    module: str = "manual"
    dry_run: bool = False


@api.post("/comm/send")
async def comm_send(body: CommSendBody, user: dict = Depends(require_admin_or_principal)):
    iid = user["institution_id"]
    channel = body.channel
    if channel not in COMM_CHANNELS:
        raise HTTPException(status_code=400, detail="channel must be 'whatsapp' or 'sms'")
    school_name, comm = await _institution_comm(iid)

    template = None
    msg_body = (body.body or "").strip()
    if body.template_id:
        template = await _comm_get_template(iid, body.template_id)
        if not template:
            raise HTTPException(status_code=404, detail="Template not found")
        if template.get("channel") not in ("both", channel):
            raise HTTPException(status_code=400, detail=f"Template not allowed on {channel}")
        msg_body = template["body"]

    # WhatsApp rule: approved template only (Meta 24h / template policy). SMS allows free-text.
    if channel == "whatsapp":
        if not template:
            raise HTTPException(status_code=400,
                                detail="WhatsApp requires an approved template (free-text is not allowed outside the 24h session window).")
        if template.get("status") != "approved":
            raise HTTPException(status_code=400,
                                detail="This template is not approved for WhatsApp. Use SMS or an approved template.")
    else:  # sms
        if not template and not msg_body:
            raise HTTPException(status_code=400, detail="Provide a message body or a template")

    # secure-link convenience: mint one if the body references it and none supplied
    base_vars = dict(body.vars or {})
    if "{{secure_link}}" in (msg_body or "") and not base_vars.get("secure_link"):
        api_base = os.environ.get("PUBLIC_BASE_URL") or os.environ.get("REACT_APP_BACKEND_URL", "")
        token = _make_secure_link(iid, f"{body.module}:{now_iso()}")
        base_vars["secure_link"] = f"{api_base}/api/comm/dl/{token}"

    allowed = await _comm_scope_class_names(user)
    class_names = await _comm_resolve_classes(iid, body.target, allowed)
    recipients, skipped = await _comm_resolve_recipients(iid, school_name, class_names, base_vars)

    # render per-recipient body
    for r in recipients:
        r["body"] = _render_template(msg_body, r["vars"])

    quota = comm["quota"][channel]
    remaining = max(0, quota["limit"] - quota["used"])
    recipient_count = len(recipients)
    preview = _render_template(msg_body, {**base_vars, "school_name": school_name,
                                          "parent_name": "Parent", "student_name": "Student", "class": "Class"})

    if body.dry_run:
        return {"dry_run": True, "recipient_count": recipient_count, "skipped_count": len(skipped),
                "skipped": skipped[:50], "quota_remaining": remaining,
                "quota_after": max(0, remaining - recipient_count), "preview": preview,
                "channel": channel, "would_block": recipient_count > remaining}

    if recipient_count == 0:
        return {"ok": False, "code": "no_recipients", "sent": 0, "skipped_count": len(skipped),
                "skipped": skipped[:50], "message": "No recipients with a guardian phone in the selected target"}
    if recipient_count > remaining:
        raise HTTPException(status_code=400,
                            detail=f"Insufficient {channel.upper()} quota: need {recipient_count}, {remaining} remaining")

    result = await send_message(iid, channel, recipients, template_id=body.template_id,
                                vars=base_vars, module=body.module,
                                meta={"target": body.target}, actor=user)
    result["skipped_count"] = len(skipped)
    result["skipped"] = skipped[:50]
    result["preview"] = preview
    return result


# ---- Delivery status webhook ----
@api.post("/comm/webhook/twilio")
async def comm_webhook_twilio(request: Request):
    """Twilio status callback. Accepts JSON {message_id,status,error} or Twilio form
    (MessageSid/MessageStatus/ErrorCode). Idempotent: a repeated status is ignored.
    Signature is validated only when real Twilio creds are live."""
    ctype = request.headers.get("content-type", "")
    if "application/json" in ctype:
        data = await request.json()
    else:
        form = await request.form()
        data = dict(form)

    msg_id = data.get("message_id") or data.get("MessageSid")
    status = (data.get("status") or data.get("MessageStatus") or "").lower()
    error = data.get("error") or data.get("ErrorCode")
    valid = {"queued", "sent", "delivered", "read", "failed", "undelivered"}
    if not msg_id or status not in valid:
        raise HTTPException(status_code=400, detail="message_id and a valid status are required")

    pcfg = await _platform_config()
    if pcfg.get("active_provider") == "twilio" and (pcfg.get("twilio") or {}).get("auth_token"):
        # signature required in production
        if not request.headers.get("X-Twilio-Signature"):
            raise HTTPException(status_code=403, detail="Missing Twilio signature")

    msg = await db.messages.find_one({"$or": [{"id": msg_id}, {"provider_sid": msg_id}]}, {"_id": 0})
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    if msg.get("status") == status:
        return {"ok": True, "idempotent": True, "status": status}  # repeated callback → no-op

    hist = msg.get("status_history") or []
    hist.append({"status": status, "at": now_iso()})
    upd = {"status": status, "status_history": hist}
    if error:
        upd["error"] = str(error)
    await db.messages.update_one({"id": msg["id"]}, {"$set": upd})
    return {"ok": True, "status": status}


# ---- Secure download link — serves a stored file (HMAC-signed, expiring, token is the only auth) ----
@api.get("/comm/dl/{token}")
async def comm_secure_dl(token: str):
    data = _verify_secure_link(token)
    if not data:
        raise HTTPException(status_code=410, detail="This link is invalid or has expired")
    path = data.get("path")
    if not path:
        return {"ok": True, "ref": data.get("ref"),
                "note": "Secure link validated (no file attached)."}
    try:
        content, ctype = _get_object(path)
    except Exception:
        raise HTTPException(status_code=404, detail="The document is no longer available")
    return Response(content=content, media_type=data.get("ct") or ctype,
                    headers={"Content-Disposition": f'inline; filename="{os.path.basename(path)}"'})


# ---- Inbound WhatsApp/SMS webhook — foundation for conversational/AI replies ----
async def _match_inbound_school(to_number: str):
    """Resolve the institution a message was sent TO. LNMO-managed sender → platform number;
    school-own sender → that school's own number."""
    to = (to_number or "").replace("whatsapp:", "").strip()
    pcfg = await _platform_config()
    tw = pcfg.get("twilio") or {}
    if to and to in (tw.get("whatsapp_sender"), tw.get("sms_sender")):
        return None, "lnmo"  # LNMO-managed → school identified via contact match below
    inst = await db.institutions.find_one(
        {"$or": [{"comm.own_twilio.whatsapp_sender": to}, {"comm.own_twilio.sms_sender": to}]},
        {"_id": 0, "id": 1})
    if inst:
        return inst["id"], "own"
    return None, "lnmo"


async def _match_contact(phone: str, iid: str = None):
    """Match an inbound sender phone to a known guardian (student) or staff user."""
    p = (phone or "").replace("whatsapp:", "").strip()
    if not p:
        return None
    sq = {"guardian_phone": p}
    if iid:
        sq["institution_id"] = iid
    st = await db.students.find_one(sq, {"_id": 0, "id": 1, "first_name": 1, "last_name": 1, "institution_id": 1, "guardian_name": 1})
    if st:
        return {"type": "guardian", "institution_id": st["institution_id"], "student_id": st["id"],
                "name": st.get("guardian_name") or f"{st.get('first_name','')} {st.get('last_name','')}".strip()}
    uq = {"phone": p}
    if iid:
        uq["institution_id"] = iid
    u = await db.users.find_one(uq, {"_id": 0, "id": 1, "name": 1, "role": 1, "institution_id": 1})
    if u:
        return {"type": "staff", "institution_id": u["institution_id"], "user_id": u["id"],
                "name": u.get("name"), "role": u.get("role")}
    return None


@api.post("/comm/webhook/inbound")
async def comm_webhook_inbound(request: Request):
    """Twilio inbound message callback. Identifies the school by the receiving number,
    matches the sender to a guardian/staff contact, and logs an inbound message row.
    This is the foundation for future conversational / AI auto-reply features."""
    ctype = request.headers.get("content-type", "")
    data = await request.json() if "application/json" in ctype else dict(await request.form())
    from_phone = (data.get("from") or data.get("From") or "").replace("whatsapp:", "").strip()
    to_phone = (data.get("to") or data.get("To") or "").replace("whatsapp:", "").strip()
    body_text = data.get("body") or data.get("Body") or ""
    channel = "whatsapp" if "whatsapp:" in (data.get("From") or data.get("from") or "") else (data.get("channel") or "sms")
    if not from_phone:
        raise HTTPException(status_code=400, detail="from number is required")

    pcfg = await _platform_config()
    if pcfg.get("active_provider") == "twilio" and (pcfg.get("twilio") or {}).get("auth_token"):
        if not request.headers.get("X-Twilio-Signature"):
            raise HTTPException(status_code=403, detail="Missing Twilio signature")

    iid, sender_mode = await _match_inbound_school(to_phone)
    contact = await _match_contact(from_phone, iid)
    if not iid and contact:
        iid = contact["institution_id"]  # LNMO-managed sender → school inferred from the contact
    if not iid:
        # Unknown number on an unknown school → park it unassigned (never dropped)
        await db.messages.insert_one({"id": str(uuid.uuid4()), "institution_id": None, "channel": channel,
                                      "direction": "inbound", "from_phone": from_phone, "to_phone": to_phone,
                                      "body": body_text, "matched_contact": None, "status": "received",
                                      "module": "inbound", "created_at": now_iso(), "status_history": []})
        return {"ok": True, "matched": False, "institution_id": None}

    doc = {"id": str(uuid.uuid4()), "institution_id": iid, "channel": channel, "direction": "inbound",
           "sender_mode": sender_mode, "from_phone": from_phone, "to_phone": to_phone,
           "recipient_name": contact.get("name") if contact else None,
           "recipient_student_id": contact.get("student_id") if contact else None,
           "body": body_text, "matched_contact": contact, "status": "received",
           "module": "inbound", "created_at": now_iso(), "status_history": [{"status": "received", "at": now_iso()}]}
    await db.messages.insert_one(dict(doc))
    return {"ok": True, "matched": bool(contact), "institution_id": iid, "contact": contact}


# ---- Report card delivery: generate PDF → store → WhatsApp media / SMS secure link ----
def _report_card_pdf(data: dict) -> bytes:
    """Render a simple, clean report-card PDF from the report-card payload."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas
    import io
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4
    st = data.get("student") or {}
    inst = data.get("institution") or {}
    name = f"{st.get('first_name','')} {st.get('last_name','')}".strip()
    y = h - 25 * mm
    c.setFont("Helvetica-Bold", 16)
    c.drawString(20 * mm, y, inst.get("name") or "Report Card")
    c.setFont("Helvetica", 11); y -= 8 * mm
    c.drawString(20 * mm, y, f"Report Card — {data.get('academic_year') or ''}")
    y -= 10 * mm
    c.setFont("Helvetica-Bold", 12)
    c.drawString(20 * mm, y, name)
    c.setFont("Helvetica", 10)
    c.drawString(120 * mm, y, f"{st.get('class_name','')} {st.get('section','') or ''}".strip())
    y -= 6 * mm
    if st.get("admission_no"):
        c.drawString(20 * mm, y, f"Admission No: {st.get('admission_no')}"); y -= 6 * mm
    y -= 4 * mm
    c.setFont("Helvetica-Bold", 10)
    c.drawString(20 * mm, y, "Subject"); c.drawString(110 * mm, y, "Marks"); c.drawString(140 * mm, y, "%"); c.drawString(165 * mm, y, "Grade")
    y -= 2 * mm
    c.line(20 * mm, y, 190 * mm, y); y -= 6 * mm
    c.setFont("Helvetica", 10)
    for row in (data.get("subjects") or []):
        c.drawString(20 * mm, y, str(row.get("subject"))[:40])
        c.drawString(110 * mm, y, f"{row.get('total_score')}/{row.get('total_max')}")
        c.drawString(140 * mm, y, str(row.get("pct")))
        c.drawString(165 * mm, y, str(row.get("grade") or "-"))
        y -= 6 * mm
        if y < 30 * mm:
            c.showPage(); y = h - 25 * mm; c.setFont("Helvetica", 10)
    y -= 2 * mm; c.line(20 * mm, y, 190 * mm, y); y -= 7 * mm
    ov = data.get("overall") or {}
    c.setFont("Helvetica-Bold", 11)
    c.drawString(20 * mm, y, f"Overall: {ov.get('total_score')}/{ov.get('total_max')}  ({ov.get('pct')}%)  Grade {ov.get('grade') or '-'}")
    y -= 7 * mm
    att = data.get("attendance") or {}
    if att.get("total"):
        c.setFont("Helvetica", 10)
        c.drawString(20 * mm, y, f"Attendance: {att.get('present')}/{att.get('total')} ({att.get('pct')}%)")
    c.showPage(); c.save()
    return buf.getvalue()


class ReportCardSendBody(BaseModel):
    student_id: str
    channel: str = "whatsapp"  # whatsapp (media) | sms (secure link)


@api.post("/comm/send-report-card")
async def comm_send_report_card(body: ReportCardSendBody, user: dict = Depends(require_admin_or_principal)):
    iid = user["institution_id"]
    channel = body.channel
    if channel not in COMM_CHANNELS:
        raise HTTPException(status_code=400, detail="channel must be 'whatsapp' or 'sms'")
    student = await db.students.find_one({"id": body.student_id, "institution_id": iid}, {"_id": 0, "password_hash": 0})
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    allowed = await _comm_scope_class_names(user)
    if allowed is not None and student.get("class_name") not in allowed:
        raise HTTPException(status_code=403, detail="This student's class is out of your scope")
    phone = str(student.get("guardian_phone") or "").strip()
    if not phone:
        raise HTTPException(status_code=400, detail="This student has no guardian phone on file")

    school_name, _ = await _institution_comm(iid)
    rc = await _report_card_data(student, iid)
    pdf = _report_card_pdf(rc)
    path = f"lnmo/reportcards/{body.student_id}/{uuid.uuid4()}.pdf"
    try:
        _put_object(path, pdf, "application/pdf")
    except Exception:
        raise HTTPException(status_code=502, detail="Document storage is unavailable right now — try again shortly")
    link = _secure_link_url(iid, f"reportcard:{body.student_id}", path=path, ct="application/pdf")

    tpl = await db.comm_templates.find_one({"institution_id": None, "name": "Report Card"}, {"_id": 0})
    sname = f"{student.get('first_name','')} {student.get('last_name','')}".strip()
    cls = student.get("class_name") + (f" {student.get('section')}" if student.get("section") else "")
    vals = {"school_name": school_name or "", "student_name": sname,
            "parent_name": student.get("guardian_name") or "Parent", "class": cls, "secure_link": link}
    tbody = tpl["body"] if tpl else "Dear {{parent_name}}, the report card for {{student_name}} ({{class}}) is ready: {{secure_link}} — {{school_name}}"
    rendered = _render_template(tbody, vals)
    media = link if channel == "whatsapp" else None  # SMS always uses the secure link in-text, never media

    recipients = [{"name": vals["parent_name"], "phone": phone, "student_id": body.student_id,
                   "body": rendered, "vars": vals, "meta": {"student_name": sname, "class": cls, "doc": "report_card"}}]
    result = await send_message(iid, channel, recipients, template_id=(tpl["id"] if tpl else None),
                                vars=vals, module="report_card", media_url=media,
                                meta={"doc": "report_card", "secure_link": link}, actor=user)
    result["secure_link"] = link
    result["student_name"] = sname
    return result


# ==========================================================================
# AI LAYER — Phase 1: AI TUTOR (Phase 29) — shared curriculum knowledge base
# Namespaced + modular so future AI modules (ELSA, Risk Detection, Insights…) slot in
# without rework. NO AI chat here (Phase 30). All routes under /api/ai/...
# INVARIANT: institution + academic_year + class_name + subject = ONE curriculum (unique index).
# ==========================================================================

AI_FILE_TYPES = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "text/plain": "txt", "image/jpeg": "jpg", "image/png": "png",
}
AI_ITEM_TYPES = {"chapter", "topic", "syllabus", "textbook", "notes", "question_paper", "worksheet",
                 "examples", "practice_questions", "reference", "previous_year", "other"}
# material types MUST be attached to a chapter (textbook/syllabus/chapter/topic are structural/root)
AI_MATERIAL_TYPES = {"notes", "question_paper", "worksheet", "examples",
                     "practice_questions", "reference", "previous_year", "other"}
AI_MAX_MB = 10
AI_TEXT_LIMIT = 200000


def _ai_extract_text(data: bytes, mime: str, filename: str) -> str:
    """Extract text from pdf/docx/txt for Phase 30 retrieval. Images are NOT parsed."""
    fn = (filename or "").lower()
    try:
        if mime == "application/pdf" or fn.endswith(".pdf"):
            import pypdf
            import io as _io
            reader = pypdf.PdfReader(_io.BytesIO(data))
            return "\n".join((p.extract_text() or "") for p in reader.pages)[:AI_TEXT_LIMIT]
        if fn.endswith(".docx") or "wordprocessingml" in (mime or ""):
            import docx
            import io as _io
            d = docx.Document(_io.BytesIO(data))
            return "\n".join(p.text for p in d.paragraphs)[:AI_TEXT_LIMIT]
        if (mime or "").startswith("text/") or fn.endswith(".txt"):
            return data.decode("utf-8", "ignore")[:AI_TEXT_LIMIT]
    except Exception:
        return ""
    return ""  # images / unknown → not parsed


async def _teaches_grade_subject(iid, user, class_name, subject):
    """Grade-level assignment check (ignores section) — teacher may contribute to this curriculum."""
    return bool(await db.teacher_assignments.find_one(
        {"institution_id": iid, "class_name": class_name, "subject": subject, **_teacher_match(user)}))


async def _ai_scope_guard(user, class_name):
    """Unit principals may only touch curricula whose grade is in their divisions. Admin/whole-school ok."""
    if user.get("role") == "institution_admin":
        return
    scope = await principal_scope(user)
    if scope and not scope.get("whole_school") and class_name not in (scope.get("class_names") or []):
        raise HTTPException(status_code=403, detail="This grade is outside your assigned scope")


async def _ai_can_review(user, c) -> bool:
    """Admins and in-scope principals may review/comment on a curriculum."""
    if user.get("role") == "institution_admin":
        return True
    if user.get("role") == "teacher" and await active_principal(user):
        scope = await principal_scope(user)
        if not scope:
            return False
        return bool(scope.get("whole_school")) or c["class_name"] in (scope.get("class_names") or [])
    return False


async def _ai_can_contribute_b(user, c) -> bool:
    """Whether this user may add/contribute to the curriculum (drives UI)."""
    if await _ai_can_review(user, c):
        return True
    if user.get("role") == "teacher":
        if c.get("created_by") == user["id"]:
            return True
        return await _teaches_grade_subject(user["institution_id"], user, c["class_name"], c["subject"])
    return False


def _ai_comment_public(x):
    return {k: x.get(k) for k in ("id", "curriculum_id", "item_id", "author_id", "author_name",
                                  "author_role", "text", "status", "reply", "created_at",
                                  "resolved_by", "resolved_by_name", "resolved_at", "target_id", "target_name",
                                  "mentions", "mention_names")}


def _ai_curriculum_public(c):
    return {k: c[k] for k in c if k not in ("_id",)}


def _ai_item_public(it, with_text=False):
    out = {"id": it["id"], "curriculum_id": it["curriculum_id"], "item_type": it["item_type"],
           "chapter": it.get("chapter"), "topic": it.get("topic"), "title": it.get("title"),
           "description": it.get("description"), "text_content": it.get("text_content"),
           "status": it.get("status"), "version": it.get("version", 1), "supersedes": it.get("supersedes"),
           "active": it.get("active", True), "contributed_by": it.get("contributed_by"),
           "contributor_name": it.get("contributor_name"), "contributed_at": it.get("contributed_at"),
           "reviewed_by": it.get("reviewed_by"), "reviewed_at": it.get("reviewed_at"),
           "review_note": it.get("review_note"), "file_name": it.get("file_name"),
           "mime": it.get("mime"), "has_file": bool(it.get("file_path")),
           "source": it.get("source"), "library_id": it.get("library_id"),
           "order": it.get("order", 0),
           "has_extracted_text": bool(it.get("extracted_text"))}
    if with_text:
        out["extracted_text"] = it.get("extracted_text")
    return out


class AIItemIn(BaseModel):
    item_type: str
    chapter: Optional[str] = ""
    topic: Optional[str] = ""
    title: Optional[str] = ""
    description: Optional[str] = ""
    text_content: Optional[str] = ""


class AICurriculumCreate(BaseModel):
    academic_year: str
    class_name: str
    subject: str
    name: str
    syllabus_text: Optional[str] = ""
    chapters: List[dict] = PField(default_factory=list)   # [{chapter, topics:[...]}]
    items: List[AIItemIn] = PField(default_factory=list)
    submit: bool = False


class AICurriculumUpdate(BaseModel):
    name: Optional[str] = None
    syllabus_text: Optional[str] = None


class AIReview(BaseModel):
    action: str                    # approve | reject | changes
    note: Optional[str] = ""


class AIEnableBody(BaseModel):
    enabled: bool


def _ai_new_item(cur, data: dict, user, status="pending"):
    now = now_iso()
    return {"id": str(uuid.uuid4()), "curriculum_id": cur["id"], "institution_id": cur["institution_id"],
            "item_type": data.get("item_type"), "chapter": (data.get("chapter") or "").strip(),
            "topic": (data.get("topic") or "").strip(), "title": (data.get("title") or "").strip(),
            "description": (data.get("description") or "").strip(),
            "text_content": (data.get("text_content") or "").strip(),
            "extracted_text": data.get("extracted_text") or "",
            "file_path": data.get("file_path"), "file_name": data.get("file_name"), "mime": data.get("mime"),
            "status": status, "version": data.get("version", 1), "supersedes": data.get("supersedes"),
            "active": True, "contributed_by": user["id"], "contributor_name": user.get("name"),
            "source": data.get("source"), "library_id": data.get("library_id"),
            "order": data.get("order", 0),
            "contributed_at": now, "reviewed_by": None, "reviewed_at": None, "review_note": None}


# ---------------- Teacher: teaching subjects for the picker ----------------
async def _ai_layer_enabled(iid):
    """Phase 34: the platform-level master switch. AI Tutor is OFF unless the platform enables the AI Layer."""
    inst = await db.institutions.find_one({"id": iid}, {"_id": 0, "features": 1})
    return bool(((inst or {}).get("features") or {}).get("ai_layer_enabled", False))


class FeaturesBody(BaseModel):
    ai_layer_enabled: bool


@api.get("/platform/institutions/{iid}/ai")
async def platform_institution_ai(iid: str, user: dict = Depends(require_roles("platform_admin"))):
    """Platform console — AI Layer master switch state + read-only AI usage summary for one school."""
    inst = await db.institutions.find_one({"id": iid}, {"_id": 0, "features": 1, "name": 1})
    if not inst:
        raise HTTPException(status_code=404, detail="Institution not found")
    feats = inst.get("features") or {}
    base = {"institution_id": iid, "is_deleted": {"$ne": True}}
    curricula = await db.curricula.count_documents(base)
    ai_on = await db.curricula.count_documents({**base, "status": "published", "ai_enabled": True})
    month_start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
    tutor_msgs = await db.tutor_messages.count_documents({"institution_id": iid, "role": "user", "created_at": {"$gte": month_start}})
    return {"name": inst.get("name"),
            "features": {"ai_layer_enabled": bool(feats.get("ai_layer_enabled", False))},
            "summary": {"curricula": curricula, "ai_enabled_curricula": ai_on, "tutor_messages_month": tutor_msgs}}


@api.put("/platform/institutions/{iid}/features")
async def platform_update_features(iid: str, body: FeaturesBody, user: dict = Depends(require_roles("platform_admin"))):
    """Platform admin ONLY. First control of the centralized AI Layer (features{} grows with future capabilities)."""
    inst = await db.institutions.find_one({"id": iid}, {"_id": 0, "name": 1})
    if not inst:
        raise HTTPException(status_code=404, detail="Institution not found")
    await db.institutions.update_one({"id": iid}, {"$set": {"features.ai_layer_enabled": body.ai_layer_enabled}})
    await audit(user, "platform_update_features", "institutions", iid,
                f"ai_layer_enabled={body.ai_layer_enabled}", iid)
    return {"ok": True, "features": {"ai_layer_enabled": body.ai_layer_enabled}}


@api.get("/ai/layer-status")
async def ai_layer_status(user: dict = Depends(require_roles("institution_admin", "teacher", "student"))):
    """Lightweight flag so AI Tutor surfaces can show a 'Disabled by LNMO Platform' banner."""
    return {"ai_layer_enabled": await _ai_layer_enabled(user["institution_id"])}


@api.get("/ai/teaching-subjects")
async def ai_teaching_subjects(user: dict = Depends(require_roles("teacher"))):
    iid = user["institution_id"]
    assigns = await db.teacher_assignments.find({"institution_id": iid, **_teacher_match(user)}, {"_id": 0}).to_list(500)
    seen, out = set(), []
    for a in assigns:
        key = (a.get("class_name"), a.get("subject"))
        if all(key) and key not in seen:
            seen.add(key)
            out.append({"class_name": a["class_name"], "subject": a["subject"]})
    year = await _active_year_name(iid)
    return {"subjects": out, "academic_year": year, "ai_layer_enabled": await _ai_layer_enabled(iid)}


# ---------------- Lookup / list ----------------
@api.get("/ai/curriculum")
async def ai_get_curriculum(academic_year: str, class_name: str, subject: str,
                            user: dict = Depends(require_roles("institution_admin", "teacher"))):
    """Resolve the ONE shared curriculum for year+grade+subject (enforces the invariant on read)."""
    iid = user["institution_id"]
    c = await db.curricula.find_one({"institution_id": iid, "academic_year": academic_year,
                                     "class_name": class_name, "subject": subject,
                                     "is_deleted": {"$ne": True}}, {"_id": 0})
    if not c:
        can_create = user["role"] == "institution_admin" or await active_principal(user) \
            or await _teaches_grade_subject(iid, user, class_name, subject)
        return {"exists": False, "can_create": bool(can_create)}
    items = await db.curriculum_items.find({"curriculum_id": c["id"], "status": {"$ne": "deleted"}}, {"_id": 0}).sort([("order", 1), ("contributed_at", 1)]).to_list(5000)
    can_contribute = user["role"] == "institution_admin" or bool(await active_principal(user)) \
        or await _teaches_grade_subject(iid, user, class_name, subject)
    return {"exists": True, "curriculum": _ai_curriculum_public(c),
            "items": [_ai_item_public(i) for i in items], "can_contribute": bool(can_contribute)}


@api.get("/ai/curricula")
async def ai_list_curricula(user: dict = Depends(require_roles("institution_admin", "teacher"))):
    iid = user["institution_id"]
    q = {"institution_id": iid, "is_deleted": {"$ne": True}}
    role = user["role"]
    if role == "teacher" and not await active_principal(user):
        # plain teacher → curricula they created OR cover a subject they teach
        assigns = await db.teacher_assignments.find({"institution_id": iid, **_teacher_match(user)}, {"_id": 0}).to_list(500)
        ors = [{"class_name": a.get("class_name"), "subject": a.get("subject")} for a in assigns if a.get("class_name") and a.get("subject")]
        q["$or"] = [{"created_by": user["id"]}] + (ors or [])
    else:
        scope = await principal_scope(user)
        if scope and not scope.get("whole_school"):
            q["class_name"] = {"$in": scope.get("class_names") or ["__none__"]}
    rows = await db.curricula.find(q, {"_id": 0}).sort([("class_name", 1), ("subject", 1)]).to_list(2000)
    return {"curricula": [_ai_curriculum_public(c) for c in rows]}


@api.get("/ai/curriculum/{cid}")
async def ai_curriculum_detail(cid: str, user: dict = Depends(require_roles("institution_admin", "teacher"))):
    iid = user["institution_id"]
    c = await db.curricula.find_one({"id": cid, "institution_id": iid}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Curriculum not found")
    if user["role"] == "teacher" and await active_principal(user):
        await _ai_scope_guard(user, c["class_name"])
    items = await db.curriculum_items.find({"curriculum_id": cid, "status": {"$ne": "deleted"}}, {"_id": 0}).sort([("order", 1), ("contributed_at", 1)]).to_list(5000)
    comments = await db.curriculum_comments.find({"curriculum_id": cid}, {"_id": 0}).sort("created_at", 1).to_list(2000)
    can_review = await _ai_can_review(user, c)
    can_contribute = await _ai_can_contribute_b(user, c)
    open_count = sum(1 for x in comments if x.get("status") == "open")
    return {"curriculum": _ai_curriculum_public(c), "items": [_ai_item_public(i) for i in items],
            "comments": [_ai_comment_public(x) for x in comments], "open_comment_count": open_count,
            "can_review": can_review, "can_comment": can_review, "can_contribute": can_contribute,
            "is_admin": user["role"] == "institution_admin"}


# ---------------- Create / edit / submit ----------------
@api.post("/ai/curriculum")
async def ai_create_curriculum(body: AICurriculumCreate, user: dict = Depends(require_roles("institution_admin", "teacher"))):
    iid = user["institution_id"]
    is_mgr = user["role"] == "institution_admin" or bool(await active_principal(user))
    if not is_mgr and not await _teaches_grade_subject(iid, user, body.class_name, body.subject):
        raise HTTPException(status_code=403, detail="You can only create a curriculum for a grade & subject you teach")
    await _ai_scope_guard(user, body.class_name)
    dup = await db.curricula.find_one({"institution_id": iid, "academic_year": body.academic_year,
                                       "class_name": body.class_name, "subject": body.subject,
                                       "is_deleted": {"$ne": True}}, {"_id": 0})
    if dup:
        raise HTTPException(status_code=409, detail={"message": "A curriculum already exists — contribute to it instead",
                                                     "curriculum_id": dup["id"]})
    now = now_iso()
    status = "pending" if body.submit else "draft"
    if body.submit:
        btypes = {it.item_type for it in (body.items or [])}
        has_ch = any((ch.get("chapter") or "").strip() for ch in (body.chapters or []))
        miss = []
        if "textbook" not in btypes:
            miss.append("a textbook/reference upload")
        if not has_ch:
            miss.append("at least one chapter")
        if miss:
            raise HTTPException(status_code=400, detail="Add " + " and ".join(miss) + " before submitting")
    cur = {"id": str(uuid.uuid4()), "institution_id": iid, "academic_year": body.academic_year,
           "class_name": body.class_name, "subject": body.subject, "name": body.name.strip(),
           "syllabus_text": (body.syllabus_text or "").strip(), "status": status, "ai_enabled": False,
           "is_deleted": False,
           "created_by": user["id"], "created_by_name": user.get("name"), "created_at": now,
           "submitted_at": now if body.submit else None, "reviewed_by": None, "reviewed_at": None, "review_note": None}
    try:
        await db.curricula.insert_one(dict(cur))
    except Exception:
        raise HTTPException(status_code=409, detail="A curriculum already exists for this grade & subject")
    item_docs = []
    for ch in (body.chapters or []):
        cname = (ch.get("chapter") or "").strip()
        if cname:
            item_docs.append(_ai_new_item(cur, {"item_type": "chapter", "chapter": cname, "title": cname}, user))
            for tp in (ch.get("topics") or []):
                if str(tp).strip():
                    item_docs.append(_ai_new_item(cur, {"item_type": "topic", "chapter": cname, "topic": str(tp).strip(), "title": str(tp).strip()}, user))
    for it in (body.items or []):
        if it.item_type not in AI_ITEM_TYPES:
            continue
        item_docs.append(_ai_new_item(cur, it.dict(), user))
    if item_docs:
        await db.curriculum_items.insert_many([dict(d) for d in item_docs])
    await audit(user, "ai_create_curriculum", "curricula", cur["id"], f"{body.class_name} {body.subject}", iid)
    return {"curriculum": _ai_curriculum_public(cur), "item_count": len(item_docs)}


@api.put("/ai/curriculum/{cid}")
async def ai_update_curriculum(cid: str, body: AICurriculumUpdate, user: dict = Depends(require_roles("institution_admin", "teacher"))):
    iid = user["institution_id"]
    c = await db.curricula.find_one({"id": cid, "institution_id": iid}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Curriculum not found")
    is_mgr = user["role"] == "institution_admin" or bool(await active_principal(user))
    if not is_mgr and c["created_by"] != user["id"]:
        raise HTTPException(status_code=403, detail="You can only edit your own curriculum")
    if not is_mgr and c["status"] not in ("draft", "changes_requested"):
        raise HTTPException(status_code=400, detail="Only draft or changes-requested curricula can be edited")
    upd = {}
    if body.name is not None:
        upd["name"] = body.name.strip()
    if body.syllabus_text is not None:
        upd["syllabus_text"] = body.syllabus_text.strip()
    if upd:
        await db.curricula.update_one({"id": cid}, {"$set": upd})
    return {"ok": True}


@api.post("/ai/curriculum/{cid}/submit")
async def ai_submit_curriculum(cid: str, user: dict = Depends(require_roles("institution_admin", "teacher"))):
    iid = user["institution_id"]
    c = await db.curricula.find_one({"id": cid, "institution_id": iid}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Curriculum not found")
    if user["role"] == "teacher" and not await active_principal(user) and c["created_by"] != user["id"]:
        raise HTTPException(status_code=403, detail="You can only submit your own curriculum")
    if c["status"] not in ("draft", "changes_requested"):
        raise HTTPException(status_code=400, detail="Curriculum is not in a submittable state")
    missing = await _ai_submit_missing(cid)
    if missing:
        raise HTTPException(status_code=400, detail="Add " + " and ".join(missing) + " before submitting")
    await db.curricula.update_one({"id": cid}, {"$set": {"status": "pending", "submitted_at": now_iso()}})
    await audit(user, "ai_submit_curriculum", "curricula", cid, c["name"], iid)
    return {"ok": True, "status": "pending"}


async def _ai_submit_missing(cid):
    """Phase 33: a curriculum needs >=1 textbook/reference upload AND >=1 chapter before submission."""
    items = await db.curriculum_items.find(
        {"curriculum_id": cid, "status": {"$ne": "deleted"}}, {"_id": 0, "item_type": 1}).to_list(5000)
    types = {i["item_type"] for i in items}
    missing = []
    if "textbook" not in types:
        missing.append("a textbook/reference upload")
    if "chapter" not in types:
        missing.append("at least one chapter")
    return missing


# ---------------- Contribute materials (versioned) ----------------
@api.post("/ai/curriculum/{cid}/items")
async def ai_contribute_item(cid: str, item_type: str = Form(...), chapter: str = Form(""),
                             topic: str = Form(""), title: str = Form(""), description: str = Form(""),
                             text_content: str = Form(""), supersedes: str = Form(None),
                             file: UploadFile = File(None),
                             user: dict = Depends(require_roles("institution_admin", "teacher"))):
    iid = user["institution_id"]
    c = await db.curricula.find_one({"id": cid, "institution_id": iid}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Curriculum not found")
    if item_type not in AI_ITEM_TYPES:
        raise HTTPException(status_code=400, detail="Invalid material type")
    if item_type in AI_MATERIAL_TYPES and not (chapter or "").strip():
        raise HTTPException(status_code=400, detail="Choose a chapter for this material")
    is_mgr = user["role"] == "institution_admin" or bool(await active_principal(user))
    is_owner = c["created_by"] == user["id"]
    if not is_mgr:
        if not await _teaches_grade_subject(iid, user, c["class_name"], c["subject"]):
            raise HTTPException(status_code=403, detail="You can only contribute to a grade & subject you teach")
        # others may only contribute to a published (shared) curriculum; the owner may add while building
        if c["status"] != "published" and not is_owner:
            raise HTTPException(status_code=400, detail="This curriculum isn't published yet")
    else:
        await _ai_scope_guard(user, c["class_name"])
    data = {"item_type": item_type, "chapter": chapter, "topic": topic, "title": title,
            "description": description, "text_content": text_content}
    if supersedes:
        old = await db.curriculum_items.find_one({"id": supersedes, "curriculum_id": cid}, {"_id": 0})
        if not old:
            raise HTTPException(status_code=404, detail="The material being replaced was not found")
        data["version"] = old.get("version", 1) + 1
        data["supersedes"] = supersedes
    if file is not None:
        if file.content_type not in AI_FILE_TYPES:
            raise HTTPException(status_code=400, detail="Allowed files: PDF, DOCX, TXT, JPG, PNG")
        content = await file.read()
        if len(content) > AI_MAX_MB * 1024 * 1024:
            raise HTTPException(status_code=400, detail=f"Each file must be under {AI_MAX_MB} MB")
        path = f"lnmo/curriculum/{cid}/{uuid.uuid4()}.{AI_FILE_TYPES[file.content_type]}"
        try:
            _put_object(path, content, file.content_type)
        except Exception:
            raise HTTPException(status_code=502, detail="File storage is unavailable right now — try again shortly")
        data["file_path"] = path
        data["file_name"] = file.filename
        data["mime"] = file.content_type
        data["extracted_text"] = _ai_extract_text(content, file.content_type, file.filename or "")
    item = _ai_new_item(c, data, user)
    await db.curriculum_items.insert_one(dict(item))
    await audit(user, "ai_contribute_item", "curriculum_items", item["id"], f"{item_type} · {c['class_name']} {c['subject']}", iid)
    return {"item": _ai_item_public(item)}


@api.put("/ai/items/{item_id}")
async def ai_edit_item(item_id: str, body: AIItemIn, user: dict = Depends(require_roles("institution_admin", "teacher"))):
    iid = user["institution_id"]
    it = await db.curriculum_items.find_one({"id": item_id, "institution_id": iid}, {"_id": 0})
    if not it:
        raise HTTPException(status_code=404, detail="Material not found")
    is_mgr = user["role"] == "institution_admin" or bool(await active_principal(user))
    if not is_mgr and (it["contributed_by"] != user["id"] or it["status"] != "pending"):
        raise HTTPException(status_code=403, detail="You can only edit your own pending contributions")
    await db.curriculum_items.update_one({"id": item_id}, {"$set": {
        "item_type": body.item_type if body.item_type in AI_ITEM_TYPES else it["item_type"],
        "chapter": (body.chapter or "").strip(), "topic": (body.topic or "").strip(),
        "title": (body.title or "").strip(), "description": (body.description or "").strip(),
        "text_content": (body.text_content or "").strip()}})
    return {"ok": True}


class ReorderChaptersBody(BaseModel):
    chapters: List[str]


@api.post("/ai/curriculum/{cid}/chapters/reorder")
async def ai_reorder_chapters(cid: str, body: ReorderChaptersBody,
                              user: dict = Depends(require_roles("institution_admin", "teacher"))):
    """Phase 37 (Feature B): persist chapter display order; all items of a chapter inherit its index."""
    iid = user["institution_id"]
    c = await db.curricula.find_one({"id": cid, "institution_id": iid}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Curriculum not found")
    if not await _ai_can_contribute_b(user, c):
        raise HTTPException(status_code=403, detail="You can't edit this curriculum")
    for idx, title in enumerate(body.chapters):
        await db.curriculum_items.update_many(
            {"curriculum_id": cid, "chapter": (title or "").strip(), "status": {"$ne": "deleted"}},
            {"$set": {"order": idx}})
    await audit(user, "ai_reorder_chapters", "curricula", cid, " > ".join(body.chapters[:8]), iid)
    return {"ok": True}


class MoveItemBody(BaseModel):
    chapter: str


@api.post("/ai/items/{item_id}/move")
async def ai_move_item(item_id: str, body: MoveItemBody,
                       user: dict = Depends(require_roles("institution_admin", "teacher"))):
    """Phase 37 (Feature B): reassign a learning material to a different chapter."""
    iid = user["institution_id"]
    it = await db.curriculum_items.find_one({"id": item_id, "institution_id": iid, "status": {"$ne": "deleted"}}, {"_id": 0})
    if not it:
        raise HTTPException(status_code=404, detail="Material not found")
    if it["item_type"] in ("chapter", "topic", "textbook"):
        raise HTTPException(status_code=400, detail="Only learning materials can be moved between chapters")
    c = await db.curricula.find_one({"id": it["curriculum_id"], "institution_id": iid}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Curriculum not found")
    if not await _ai_can_contribute_b(user, c):
        raise HTTPException(status_code=403, detail="You can't edit this curriculum")
    newch = (body.chapter or "").strip()
    if not newch:
        raise HTTPException(status_code=400, detail="Choose a target chapter")
    chit = await db.curriculum_items.find_one(
        {"curriculum_id": it["curriculum_id"], "item_type": "chapter", "chapter": newch,
         "status": {"$ne": "deleted"}}, {"_id": 0})
    order = chit.get("order", 0) if chit else it.get("order", 0)
    await db.curriculum_items.update_one({"id": item_id}, {"$set": {"chapter": newch, "order": order}})
    await audit(user, "ai_move_item", "curriculum_items", item_id, f"→ {newch}", iid)
    return {"ok": True}


@api.get("/ai/my-contributions")
async def ai_my_contributions(user: dict = Depends(require_roles("teacher"))):
    iid = user["institution_id"]
    items = await db.curriculum_items.find({"institution_id": iid, "contributed_by": user["id"]},
                                           {"_id": 0}).sort("contributed_at", -1).to_list(2000)
    return {"items": [_ai_item_public(i) for i in items]}


# ---------------- File download ----------------
@api.get("/ai/items/{item_id}/file")
async def ai_download_item_file(item_id: str, user: dict = Depends(get_current_user)):
    iid = user["institution_id"]
    it = await db.curriculum_items.find_one({"id": item_id, "institution_id": iid}, {"_id": 0})
    if not it or not it.get("file_path"):
        raise HTTPException(status_code=404, detail="File not found")
    c = await db.curricula.find_one({"id": it["curriculum_id"], "institution_id": iid}, {"_id": 0})
    role = user["role"]
    allowed = role == "institution_admin"
    if role == "teacher":
        if await active_principal(user):
            await _ai_scope_guard(user, c["class_name"])
            allowed = True
        else:
            allowed = it["contributed_by"] == user["id"] or await _teaches_grade_subject(iid, user, c["class_name"], c["subject"])
    elif role == "student":
        # students may only download APPROVED+active items from their own grade's published+ai_enabled curriculum
        st = await db.students.find_one({"id": user.get("student_id"), "institution_id": iid}, {"_id": 0, "class_name": 1})
        allowed = bool(st) and it.get("status") == "approved" and it.get("active") \
            and c.get("status") == "published" and c.get("ai_enabled") and c.get("class_name") == (st or {}).get("class_name")
    if not allowed:
        raise HTTPException(status_code=403, detail="Not allowed")
    data, ctype = _get_object(it["file_path"])
    return Response(content=data, media_type=it.get("mime") or ctype,
                    headers={"Content-Disposition": f'inline; filename="{it.get("file_name") or "file"}"'})


# ---------------- Approvals ----------------
@api.get("/ai/approvals/curricula")
async def ai_pending_curricula(user: dict = Depends(require_admin_or_principal)):
    iid = user["institution_id"]
    q = {"institution_id": iid, "status": "pending"}
    scope = await principal_scope(user)
    if scope and not scope.get("whole_school"):
        q["class_name"] = {"$in": scope.get("class_names") or ["__none__"]}
    rows = await db.curricula.find(q, {"_id": 0}).sort("submitted_at", 1).to_list(500)
    out = []
    for c in rows:
        pub = _ai_curriculum_public(c)
        pub["open_comment_count"] = await db.curriculum_comments.count_documents({"curriculum_id": c["id"], "status": "open"})
        out.append(pub)
    return {"curricula": out}


@api.post("/ai/curriculum/{cid}/review")
async def ai_review_curriculum(cid: str, body: AIReview, user: dict = Depends(require_admin_or_principal)):
    iid = user["institution_id"]
    c = await db.curricula.find_one({"id": cid, "institution_id": iid}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Curriculum not found")
    await _ai_scope_guard(user, c["class_name"])
    if c["status"] != "pending":
        raise HTTPException(status_code=400, detail="Only pending curricula can be reviewed")
    now = now_iso()
    new_status = {"approve": "published", "reject": "rejected", "changes": "changes_requested"}.get(body.action)
    if not new_status:
        raise HTTPException(status_code=400, detail="action must be approve|reject|changes")
    await db.curricula.update_one({"id": cid}, {"$set": {"status": new_status, "reviewed_by": user["id"],
                                                         "reviewed_at": now, "review_note": (body.note or "").strip()}})
    approved_items = 0
    if body.action == "approve":
        # publishing approves the creator's INITIAL pending materials; later contributions stay per-item pending
        res = await db.curriculum_items.update_many(
            {"curriculum_id": cid, "status": "pending", "contributed_by": c["created_by"]},
            {"$set": {"status": "approved", "active": True, "reviewed_by": user["id"], "reviewed_at": now}})
        approved_items = res.modified_count
    await audit(user, f"ai_curriculum_{body.action}", "curricula", cid, c["name"], iid)
    return {"ok": True, "status": new_status, "approved_items": approved_items}


@api.get("/ai/approvals/items")
async def ai_pending_items(user: dict = Depends(require_admin_or_principal)):
    """Pending contributions grouped by curriculum (published curricula only), in scope."""
    iid = user["institution_id"]
    cq = {"institution_id": iid, "status": "published"}
    scope = await principal_scope(user)
    if scope and not scope.get("whole_school"):
        cq["class_name"] = {"$in": scope.get("class_names") or ["__none__"]}
    curs = await db.curricula.find(cq, {"_id": 0}).to_list(2000)
    by_id = {c["id"]: c for c in curs}
    if not by_id:
        return {"groups": []}
    items = await db.curriculum_items.find(
        {"curriculum_id": {"$in": list(by_id)}, "status": "pending"}, {"_id": 0}).sort("contributed_at", 1).to_list(5000)
    groups = {}
    for it in items:
        g = groups.setdefault(it["curriculum_id"], [])
        g.append(_ai_item_public(it))
    out = [{"curriculum": _ai_curriculum_public(by_id[cid]), "items": its} for cid, its in groups.items()]
    return {"groups": out}


@api.post("/ai/items/{item_id}/review")
async def ai_review_item(item_id: str, body: AIReview, user: dict = Depends(require_admin_or_principal)):
    iid = user["institution_id"]
    it = await db.curriculum_items.find_one({"id": item_id, "institution_id": iid}, {"_id": 0})
    if not it:
        raise HTTPException(status_code=404, detail="Material not found")
    c = await db.curricula.find_one({"id": it["curriculum_id"], "institution_id": iid}, {"_id": 0})
    await _ai_scope_guard(user, c["class_name"])
    if it["status"] != "pending":
        raise HTTPException(status_code=400, detail="Only pending materials can be reviewed")
    now = now_iso()
    new_status = {"approve": "approved", "reject": "rejected", "changes": "changes_requested"}.get(body.action)
    if not new_status:
        raise HTTPException(status_code=400, detail="action must be approve|reject|changes")
    await db.curriculum_items.update_one({"id": item_id}, {"$set": {
        "status": new_status, "active": new_status == "approved", "reviewed_by": user["id"],
        "reviewed_at": now, "review_note": (body.note or "").strip()}})
    # on approval of a replacement, retire the superseded item (kept forever, just inactive)
    if body.action == "approve" and it.get("supersedes"):
        await db.curriculum_items.update_one({"id": it["supersedes"]}, {"$set": {"active": False}})
    await audit(user, f"ai_item_{body.action}", "curriculum_items", item_id, it.get("title") or it["item_type"], iid)
    return {"ok": True, "status": new_status}


# ---------------- Enable / disable the tutor per curriculum ----------------
@api.put("/ai/curriculum/{cid}/ai-enabled")
async def ai_toggle_enabled(cid: str, body: AIEnableBody, user: dict = Depends(require_admin_or_principal)):
    iid = user["institution_id"]
    c = await db.curricula.find_one({"id": cid, "institution_id": iid}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Curriculum not found")
    await _ai_scope_guard(user, c["class_name"])
    if c["status"] != "published":
        raise HTTPException(status_code=400, detail="Only a published curriculum can have the AI Tutor enabled")
    await db.curricula.update_one({"id": cid}, {"$set": {"ai_enabled": bool(body.enabled)}})
    await audit(user, "ai_toggle_enabled", "curricula", cid, f"ai_enabled={body.enabled}", iid)
    return {"ok": True, "ai_enabled": bool(body.enabled)}


# ---------------- Version / contribution history ----------------
@api.get("/ai/curriculum/{cid}/history")
async def ai_curriculum_history(cid: str, user: dict = Depends(require_admin_or_principal)):
    iid = user["institution_id"]
    c = await db.curricula.find_one({"id": cid, "institution_id": iid}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Curriculum not found")
    await _ai_scope_guard(user, c["class_name"])
    items = await db.curriculum_items.find({"curriculum_id": cid}, {"_id": 0}).sort([("contributed_at", -1)]).to_list(5000)
    return {"curriculum": _ai_curriculum_public(c), "history": [_ai_item_public(i) for i in items]}


# ---------------- Review comments & resolution (Phase 31) ----------------
class AICommentIn(BaseModel):
    text: str
    item_id: Optional[str] = None
    mentions: Optional[list] = None  # Phase 35: teacher user ids to @mention


class AIResolveIn(BaseModel):
    reply: Optional[str] = ""


async def _ai_mention_map(iid, c):
    """Phase 35: id→name of teachers a reviewer may @mention (contributors + assigned subject teachers),
    resolving any missing display names from the users collection."""
    ids = {}
    if c.get("created_by"):
        ids[c["created_by"]] = c.get("created_by_name")
    for it in await db.curriculum_items.find({"curriculum_id": c["id"], "status": {"$ne": "deleted"}},
                                             {"_id": 0, "contributed_by": 1, "contributor_name": 1}).to_list(5000):
        if it.get("contributed_by"):
            ids.setdefault(it["contributed_by"], it.get("contributor_name"))
    for ta in await db.teacher_assignments.find({"institution_id": iid, "class_name": c["class_name"], "subject": c["subject"]},
                                                {"_id": 0, "teacher_id": 1, "teacher_name": 1}).to_list(500):
        if ta.get("teacher_id"):
            ids.setdefault(ta["teacher_id"], ta.get("teacher_name"))
    missing = [k for k, v in ids.items() if not v]
    if missing:
        for u in await db.users.find({"id": {"$in": missing}}, {"_id": 0, "id": 1, "name": 1}).to_list(500):
            ids[u["id"]] = u.get("name")
    return ids


@api.get("/ai/curriculum/{cid}/mention-candidates")
async def ai_mention_candidates(cid: str, user: dict = Depends(require_admin_or_principal)):
    """Phase 35: teachers a reviewer can @mention — the curriculum's contributors + assigned subject teachers."""
    iid = user["institution_id"]
    c = await db.curricula.find_one({"id": cid, "institution_id": iid}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Curriculum not found")
    if not await _ai_can_review(user, c):
        raise HTTPException(status_code=403, detail="This curriculum is outside your scope")
    ids = await _ai_mention_map(iid, c)
    return {"candidates": [{"id": k, "name": v or "Teacher"} for k, v in ids.items() if k != user["id"]]}


@api.get("/ai/curriculum/{cid}/comments")
async def ai_list_comments(cid: str, user: dict = Depends(require_roles("institution_admin", "teacher"))):
    iid = user["institution_id"]
    c = await db.curricula.find_one({"id": cid, "institution_id": iid}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Curriculum not found")
    if not await _ai_can_contribute_b(user, c):
        raise HTTPException(status_code=403, detail="Not allowed to view these comments")
    rows = await db.curriculum_comments.find({"curriculum_id": cid}, {"_id": 0}).sort("created_at", 1).to_list(2000)
    return {"comments": [_ai_comment_public(x) for x in rows]}


@api.post("/ai/curriculum/{cid}/comments")
async def ai_add_comment(cid: str, body: AICommentIn, user: dict = Depends(require_admin_or_principal)):
    iid = user["institution_id"]
    c = await db.curricula.find_one({"id": cid, "institution_id": iid}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Curriculum not found")
    if not await _ai_can_review(user, c):
        raise HTTPException(status_code=403, detail="This curriculum is outside your scope")
    text = (body.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Comment cannot be empty")
    # resolve the teacher to notify (item contributor, else curriculum creator)
    target_id, target_name = c.get("created_by"), c.get("created_by_name")
    item_id = None
    if body.item_id:
        it = await db.curriculum_items.find_one({"id": body.item_id, "curriculum_id": cid}, {"_id": 0})
        if not it:
            raise HTTPException(status_code=404, detail="Material not found on this curriculum")
        item_id = it["id"]
        target_id, target_name = it.get("contributed_by"), it.get("contributor_name")
    now = now_iso()
    # Phase 35: validate @mentions against allowed candidates (contributors + assigned subject teachers)
    mention_ids, mention_names = [], []
    if body.mentions:
        allowed = await _ai_mention_map(iid, c)
        for mid in body.mentions:
            if mid in allowed and mid not in mention_ids:
                mention_ids.append(mid)
                mention_names.append(allowed[mid] or "Teacher")
    doc = {"id": str(uuid.uuid4()), "institution_id": iid, "curriculum_id": cid, "item_id": item_id,
           "author_id": user["id"], "author_name": user.get("name"), "author_role": user["role"],
           "text": text, "status": "open", "reply": None, "created_at": now,
           "target_id": target_id, "target_name": target_name,
           "mentions": mention_ids, "mention_names": mention_names,
           "resolved_by": None, "resolved_by_name": None, "resolved_at": None}
    await db.curriculum_comments.insert_one(dict(doc))
    await _notify(iid, target_id, "ai_curriculum_comment",
                  f"Review comment · {c['class_name']} {c['subject']}",
                  text[:200], cid)
    # Phase 35: ping each mentioned teacher (besides the primary target) with a deep link
    where = f" — {it['chapter']}" if (item_id and it.get("chapter")) else ""
    for mid in mention_ids:
        if mid != target_id:
            await _notify(iid, mid, "ai_comment_mention",
                          f"You were mentioned · {c['class_name']} {c['subject']}{where}",
                          text[:200], cid)
    await audit(user, "ai_add_comment", "curriculum_comments", doc["id"], c["name"], iid)
    return {"comment": _ai_comment_public(doc)}


@api.post("/ai/comments/{comment_id}/resolve")
async def ai_resolve_comment(comment_id: str, body: AIResolveIn, user: dict = Depends(require_roles("institution_admin", "teacher"))):
    iid = user["institution_id"]
    cm = await db.curriculum_comments.find_one({"id": comment_id, "institution_id": iid}, {"_id": 0})
    if not cm:
        raise HTTPException(status_code=404, detail="Comment not found")
    c = await db.curricula.find_one({"id": cm["curriculum_id"], "institution_id": iid}, {"_id": 0})
    is_target = cm.get("target_id") == user["id"]
    is_reviewer = await _ai_can_review(user, c) if c else False
    if not (is_target or is_reviewer):
        raise HTTPException(status_code=403, detail="You can only resolve comments addressed to you")
    if cm.get("status") == "resolved":
        raise HTTPException(status_code=400, detail="This comment is already resolved")
    now = now_iso()
    reply = (body.reply or "").strip()
    await db.curriculum_comments.update_one({"id": comment_id}, {"$set": {
        "status": "resolved", "reply": reply or None, "resolved_by": user["id"],
        "resolved_by_name": user.get("name"), "resolved_at": now}})
    # notify the reviewer who raised the comment
    await _notify(iid, cm.get("author_id"), "ai_comment_resolved",
                  f"Comment resolved · {c['class_name'] if c else ''} {c['subject'] if c else ''}".strip(),
                  (reply or "The contributor marked your comment as resolved.")[:200], cm["curriculum_id"])
    await audit(user, "ai_resolve_comment", "curriculum_comments", comment_id, c["name"] if c else "", iid)
    return {"ok": True}


# ---------------- Principal/admin delete (soft-delete) (Phase 31.5) ----------------
class AICurriculumDelete(BaseModel):
    confirm_name: Optional[str] = None


@api.delete("/ai/items/{item_id}")
async def ai_delete_item(item_id: str, user: dict = Depends(require_roles("institution_admin", "teacher"))):
    """In-scope principals / admin SOFT-delete a curriculum item (chapters cascade).
    The owning teacher may HARD-delete their OWN items on an unsubmitted draft/changes_requested
    (uploaded files are cleaned up best-effort; shared LNMO Library files are never deleted)."""
    iid = user["institution_id"]
    it = await db.curriculum_items.find_one({"id": item_id, "institution_id": iid}, {"_id": 0})
    if not it or it.get("status") == "deleted":
        raise HTTPException(status_code=404, detail="Material not found")
    c = await db.curricula.find_one({"id": it["curriculum_id"], "institution_id": iid}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Curriculum not found")
    is_mgr = user["role"] == "institution_admin" or bool(await active_principal(user))
    if not is_mgr:
        if it.get("contributed_by") != user["id"] and c.get("created_by") != user["id"]:
            raise HTTPException(status_code=403, detail="You can only edit your own curriculum")
        if c.get("status") not in ("draft", "changes_requested"):
            raise HTTPException(status_code=409, detail="Only items in an unsubmitted draft can be removed")
    else:
        await _ai_scope_guard(user, c["class_name"])
    now = now_iso()
    targets = [it]
    # a chapter cascades to its topics + materials in the same curriculum
    if it["item_type"] == "chapter" and it.get("chapter"):
        children = await db.curriculum_items.find(
            {"curriculum_id": it["curriculum_id"], "chapter": it["chapter"],
             "id": {"$ne": item_id}, "status": {"$ne": "deleted"}}, {"_id": 0}).to_list(5000)
        targets += children
    ids = [t["id"] for t in targets]
    if is_mgr:
        await db.curriculum_items.update_many({"id": {"$in": ids}}, {"$set": {
            "status": "deleted", "active": False, "deleted_by": user["id"], "deleted_at": now}})
        notified = set()
        for t in targets:
            tgt = t.get("contributed_by")
            if tgt and tgt not in notified and tgt != user["id"]:
                notified.add(tgt)
                await _notify(iid, tgt, "ai_item_deleted",
                              f"Material removed · {c['class_name']} {c['subject']}",
                              f"\"{t.get('title') or t.get('topic') or t.get('chapter') or t['item_type']}\" was removed by a principal.", c["id"])
    else:
        # teacher hard-deletes own draft items; clean up uploaded files only (never the shared library file)
        for t in targets:
            if t.get("file_path") and t.get("source") != "lnmo_library":
                try:
                    _delete_object(t["file_path"])
                except Exception:
                    pass
        await db.curriculum_items.delete_many({"id": {"$in": ids}})
    await audit(user, "ai_delete_item", "curriculum_items", item_id,
                f"{it.get('title') or it['item_type']} (+{len(targets) - 1} children)", iid)
    return {"ok": True, "deleted": len(targets)}


@api.delete("/ai/curriculum/{cid}")
async def ai_delete_curriculum(cid: str, body: AICurriculumDelete = None,
                               user: dict = Depends(require_roles("institution_admin", "teacher"))):
    """Admin → HARD delete (docs + stored files). In-scope principal → SOFT delete.
    Owning teacher → HARD delete of their OWN unsubmitted draft/changes_requested only."""
    import logging
    iid = user["institution_id"]
    c = await db.curricula.find_one({"id": cid, "institution_id": iid, "is_deleted": {"$ne": True}}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Curriculum not found")
    is_mgr = user["role"] == "institution_admin" or bool(await active_principal(user))
    if not is_mgr:
        # plain teacher: may hard-delete only their OWN unsubmitted draft
        if c.get("created_by") != user["id"]:
            raise HTTPException(status_code=403, detail="You can only delete your own curriculum")
        if c.get("status") not in ("draft", "changes_requested"):
            raise HTTPException(status_code=409, detail="Only an unsubmitted draft can be deleted — submitted curricula follow the review process")
    else:
        await _ai_scope_guard(user, c["class_name"])
        if body and body.confirm_name is not None and body.confirm_name.strip() != (c.get("name") or "").strip():
            raise HTTPException(status_code=400, detail="The typed name does not match the curriculum name")
    now = now_iso()
    is_admin = user["role"] == "institution_admin"
    do_hard = is_admin or (not is_mgr)
    # notify each distinct contributing teacher before removal
    live_items = await db.curriculum_items.find(
        {"curriculum_id": cid, "status": {"$ne": "deleted"}}, {"_id": 0}).to_list(5000)
    notified = set()
    for t in live_items:
        tgt = t.get("contributed_by")
        if tgt and tgt not in notified and tgt != user["id"]:
            notified.add(tgt)
            await _notify(iid, tgt, "ai_item_deleted",
                          f"Curriculum removed · {c['class_name']} {c['subject']}",
                          f"The {c['class_name']} {c['subject']} curriculum was removed.", None)

    if do_hard:
        # HARD delete: wipe stored files (best-effort), then the items + curriculum docs
        all_items = await db.curriculum_items.find({"curriculum_id": cid}, {"_id": 0}).to_list(10000)
        item_count = len(all_items)
        deleted_files, failed_files = 0, 0
        for it in all_items:
            if it.get("file_path"):
                try:
                    if _delete_object(it["file_path"]):
                        deleted_files += 1
                except Exception as e:
                    failed_files += 1
                    logging.getLogger("ai").warning("ai hard-delete: file cleanup failed for %s: %s", it.get("file_path"), e)
        await db.curriculum_items.delete_many({"curriculum_id": cid})
        await db.curricula.delete_one({"id": cid})
        await db.curriculum_comments.delete_many({"curriculum_id": cid})
        await audit(user, "ai_hard_delete_curriculum", "curricula", cid,
                    f"{c['name']} · {c['class_name']} {c['subject']} · {item_count} items · files removed {deleted_files}/{deleted_files + failed_files}", iid)
        return {"ok": True, "hard": True, "deleted_items": item_count, "deleted_files": deleted_files, "failed_files": failed_files}

    # principal → SOFT delete (retained internally)
    await db.curricula.update_one({"id": cid}, {"$set": {
        "is_deleted": True, "status": "deleted", "ai_enabled": False,
        "deleted_by": user["id"], "deleted_at": now}})
    await db.curriculum_items.update_many({"curriculum_id": cid, "status": {"$ne": "deleted"}},
                                          {"$set": {"status": "deleted", "active": False, "deleted_by": user["id"], "deleted_at": now}})
    await audit(user, "ai_delete_curriculum", "curricula", cid,
                f"{c['name']} · {c['class_name']} {c['subject']} · {len(live_items)} items (soft)", iid)
    return {"ok": True, "hard": False, "deleted_items": len(live_items)}



# ==========================================================================
# AI LAYER — Phase 2 (Phase 30): AI TUTOR CHAT + STUDENT RESOURCE LIBRARY
# Model: Gemini 3 Flash via Emergent universal key. Academic-only, bilingual (EN/ML).
# Retrieval = keyword/metadata scoring over APPROVED+active curriculum items (no embeddings).
# ==========================================================================
AI_TUTOR_MODEL = ("gemini", "gemini-3-flash-preview")
import ai_response_engine as reng  # noqa: E402  Phase 32 — independent response-structuring engine
AI_TUTOR_DAILY_CAP = 50
_AI_MEMORY_SYNC = False  # tests set True to await memory extraction inline (prod = async create_task)
AI_RETRIEVAL_TOP_K = 4
AI_CONTEXT_CHAR_BUDGET = 3500
_AI_STOPWORDS = {"the", "a", "an", "is", "are", "of", "to", "in", "and", "or", "for", "what",
                 "how", "why", "explain", "me", "please", "simply", "simple", "can", "you",
                 "about", "tell", "give", "with", "on", "do", "does", "this", "that", "my"}


def _ai_tokens(text):
    import re
    return {w for w in re.findall(r"[a-zA-Z\u0d00-\u0d7f]{3,}", (text or "").lower()) if w not in _AI_STOPWORDS}


async def _ai_retrieve(curriculum_id, message):
    """Rank APPROVED + active items by keyword overlap over chapter/topic/title/description/extracted_text."""
    items = await db.curriculum_items.find(
        {"curriculum_id": curriculum_id, "status": "approved", "active": True}, {"_id": 0}).to_list(5000)
    qtok = _ai_tokens(message)
    scored = []
    for it in items:
        if it["item_type"] in ("chapter", "topic"):
            continue  # organizational nodes carry no teaching content
        hay = " ".join([it.get("chapter") or "", it.get("topic") or "", it.get("title") or "",
                        it.get("description") or "", it.get("text_content") or "", it.get("extracted_text") or ""])
        htok = _ai_tokens(hay)
        if not htok:
            continue
        overlap = len(qtok & htok)
        # light boost for title/topic/chapter matches
        boost = len(qtok & _ai_tokens(" ".join([it.get("title") or "", it.get("topic") or "", it.get("chapter") or ""]))) * 2
        score = overlap + boost
        if score > 0:
            scored.append((score, it))
    scored.sort(key=lambda x: (-x[0], x[1].get("order", 0), x[1].get("contributed_at") or ""))
    return [it for _, it in scored[:AI_RETRIEVAL_TOP_K]]


def _ai_build_context(items):
    parts, used, total = [], [], 0
    for it in items:
        body = (it.get("text_content") or "").strip() or (it.get("extracted_text") or "").strip()
        label = it.get("title") or it.get("topic") or it.get("item_type")
        chap = f" ({it.get('chapter')})" if it.get("chapter") else ""
        by = f" — {it.get('contributor_name')}" if it.get("contributor_name") else ""
        snippet = body[:1200].strip()
        block = f"[{label}{chap}{by}]\n{snippet}" if snippet else f"[{label}{chap}{by}] (file material: {it.get('file_name') or 'attachment'})"
        if total + len(block) > AI_CONTEXT_CHAR_BUDGET and used:
            break
        parts.append(block)
        total += len(block)
        used.append(it)
    return "\n\n".join(parts), used


def _ai_system_prompt(class_name, subject, context_text):
    grounded = bool(context_text.strip())
    base = (
        f"You are a friendly, patient AI Tutor for a {class_name} student studying {subject}. "
        "Explain at a level appropriate for this grade, with clear steps and small examples. "
        "LANGUAGE: Detect the language of the student's message and reply in THAT language. "
        "Support English and Malayalam (reply fully in Malayalam if the student writes in Malayalam). "
        "SCOPE: Only help with academic learning for this subject and closely related school topics. "
        "If the student asks something non-academic (games, gossip, personal/other chit-chat, anything "
        "unrelated to studies), politely decline in one short sentence and steer them back to the subject. "
    )
    if grounded:
        base += (
            "The following are the SCHOOL'S APPROVED MATERIALS for this subject. PRIORITISE and base your "
            "answer on them; refer to them naturally.\n\n=== SCHOOL APPROVED MATERIALS ===\n"
            + context_text + "\n=== END MATERIALS ===")
    else:
        base += (
            "No specific approved school material matched this question. You may still give a helpful, correct "
            "general explanation for the subject, but make clear it is a general explanation, not from the "
            "school's own materials.")
    return base


async def _ai_llm_generate(system_message, user_text, session_id):
    """Single-turn Gemini 3 Flash completion. Isolated so unit tests can monkeypatch it (no network)."""
    from emergentintegrations.llm.chat import LlmChat, UserMessage
    chat = LlmChat(api_key=os.environ["EMERGENT_LLM_KEY"], session_id=session_id,
                   system_message=system_message).with_model(*AI_TUTOR_MODEL)
    resp = await chat.send_message(UserMessage(text=user_text))
    return resp if isinstance(resp, str) else getattr(resp, "content", str(resp))


async def _ai_student_grade(user):
    st = await db.students.find_one({"id": user.get("student_id"), "institution_id": user["institution_id"]},
                                    {"_id": 0, "class_name": 1, "section": 1})
    if not st:
        raise HTTPException(status_code=404, detail="Student record not found")
    return st["class_name"], st.get("section")


# ---- Phase 32: intent classify + student learning memory (LLM calls isolated for tests) ----
async def _ai_classify_intent(message, has_history):
    """Rule pass first; only call the cheap LLM classifier when rules are unsure."""
    intent, confident = reng.detect_intent_rule(message, has_history)
    if confident:
        return intent, False
    try:
        raw = await _ai_llm_generate(reng.classify_instruction(), message, f"classify-{uuid.uuid4()}")
        picked = reng.parse_classified_intent(raw)
        if picked:
            return picked, True
    except Exception:
        pass
    return intent, False


async def _ai_get_memory(student_id, subject):
    doc = await db.student_memory.find_one({"student_id": student_id, "subject": subject}, {"_id": 0})
    return (doc or {}).get("entries", [])


async def _ai_update_memory(student_id, iid, subject, topic, student_msg, tutor_msg):
    """Post-response: extract durable learning signals and upsert them (conservative, de-duped, capped)."""
    try:
        exchange = f"Student: {student_msg}\nTutor: {tutor_msg}"
        raw = await _ai_llm_generate(reng.memory_extraction_instruction(subject), exchange, f"mem-{uuid.uuid4()}")
        new_entries = reng.parse_memory_extraction(raw, topic=topic)
        if not new_entries:
            return 0
        now = now_iso()
        for e in new_entries:
            e["updated_at"] = now
        doc = await db.student_memory.find_one({"student_id": student_id, "subject": subject}, {"_id": 0})
        merged = reng.merge_memory(doc.get("entries", []) if doc else [], new_entries)
        await db.student_memory.update_one(
            {"student_id": student_id, "subject": subject},
            {"$set": {"entries": merged, "institution_id": iid, "updated_at": now},
             "$setOnInsert": {"id": str(uuid.uuid4())}}, upsert=True)
        return len(new_entries)
    except Exception:
        return 0


class TutorChatBody(BaseModel):
    subject: str
    message: str
    curriculum_id: Optional[str] = None
    chat_id: Optional[str] = None


@api.post("/ai/tutor/chat")
async def ai_tutor_chat(body: TutorChatBody, user: dict = Depends(require_roles("student"))):
    iid = user["institution_id"]
    if not await _ai_layer_enabled(iid):
        raise HTTPException(status_code=403, detail="AI Tutor is not available for your school")
    if not body.message.strip():
        raise HTTPException(status_code=400, detail="Type a question")
    class_name, _ = await _ai_student_grade(user)
    year = await _active_year_name(iid)
    cur = await db.curricula.find_one({"institution_id": iid, "academic_year": year,
                                       "class_name": class_name, "subject": body.subject}, {"_id": 0})
    if not cur:
        raise HTTPException(status_code=403, detail="AI Tutor is not enabled for this subject")
    if cur["status"] != "published" or not cur.get("ai_enabled"):
        raise HTTPException(status_code=403, detail="AI Tutor is not enabled for this subject")

    # per-student daily rate limit (user turns only)
    since = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    todays = await db.tutor_messages.count_documents({"student_id": user["id"], "role": "user", "created_at": {"$gte": since}})
    if todays >= AI_TUTOR_DAILY_CAP:
        raise HTTPException(status_code=429, detail=f"You've reached today's limit of {AI_TUTOR_DAILY_CAP} tutor messages. Please come back tomorrow!")

    chat_id = body.chat_id or str(uuid.uuid4())
    import asyncio
    msg = body.message.strip()
    # within-chat continuity + learning-check carry-over (fresh chat = empty history; memory still persists)
    history = await db.tutor_messages.find({"chat_id": chat_id, "student_id": user["id"]},
                                           {"_id": 0}).sort("created_at", 1).to_list(50)
    chat_history = [{"role": m["role"], "content": m["content"]} for m in history]
    pending_check = None
    for m in reversed(history):
        if m["role"] == "assistant":
            pending_check = m.get("check_question")
            break

    intent, _used_llm = await _ai_classify_intent(msg, bool(history))
    strategy = reng.strategy_for(intent)
    matches = await _ai_retrieve(cur["id"], msg)
    context_text, used = _ai_build_context(matches)
    used_ids = [u["id"] for u in used]
    used_titles = [{"title": u.get("title") or u.get("topic") or u["item_type"], "chapter": u.get("chapter"),
                    "contributor_name": u.get("contributor_name")} for u in used]
    memory = await _ai_get_memory(user["id"], body.subject)
    system = reng.build_system_prompt(class_name, body.subject, context_text, intent,
                                      memory_entries=memory, chat_history=chat_history, pending_check=pending_check)
    now = now_iso()
    await db.tutor_messages.insert_one({"id": str(uuid.uuid4()), "chat_id": chat_id, "student_id": user["id"],
                                        "institution_id": iid, "curriculum_id": cur["id"], "subject": body.subject,
                                        "role": "user", "content": msg, "used_item_ids": [],
                                        "intent": intent, "created_at": now})
    try:
        answer = await _ai_llm_generate(system, msg, chat_id)
    except Exception:
        raise HTTPException(status_code=502, detail="The AI Tutor is busy right now — please try again in a moment")
    grounded = bool(used_ids)
    check_q = reng.extract_check_question(answer)
    await db.tutor_messages.insert_one({"id": str(uuid.uuid4()), "chat_id": chat_id, "student_id": user["id"],
                                        "institution_id": iid, "curriculum_id": cur["id"], "subject": body.subject,
                                        "role": "assistant", "content": answer, "used_item_ids": used_ids,
                                        "grounded": grounded, "intent": intent, "strategy": strategy,
                                        "memory_used": bool(memory), "check_question": check_q,
                                        "created_at": now_iso()})
    # async post-response memory update (don't slow the reply)
    topic = used[0].get("chapter") if used else None
    if _AI_MEMORY_SYNC:
        await _ai_update_memory(user["id"], iid, body.subject, topic, msg, answer)
    else:
        asyncio.create_task(_ai_update_memory(user["id"], iid, body.subject, topic, msg, answer))
    return {"chat_id": chat_id, "answer": answer, "grounded": grounded, "used_item_titles": used_titles}


@api.get("/ai/tutor/subjects")
async def ai_tutor_subjects(user: dict = Depends(require_roles("student"))):
    """The student's subjects, each flagged whether the AI Tutor is enabled."""
    iid = user["institution_id"]
    class_name, section = await _ai_student_grade(user)
    year = await _active_year_name(iid)
    offerings = await db.subject_offerings.find({"institution_id": iid, "class_name": class_name}, {"_id": 0, "subject": 1}).to_list(200)
    subjects = sorted({o["subject"] for o in offerings if o.get("subject")})
    layer = await _ai_layer_enabled(iid)
    curs = await db.curricula.find({"institution_id": iid, "academic_year": year, "class_name": class_name}, {"_id": 0}).to_list(500)
    enabled = {c["subject"] for c in curs if c["status"] == "published" and c.get("ai_enabled")} if layer else set()
    if not subjects:  # fall back to curricula subjects if no offerings configured
        subjects = sorted({c["subject"] for c in curs})
    return {"class_name": class_name, "ai_layer_enabled": layer,
            "subjects": [{"subject": s, "enabled": s in enabled} for s in subjects]}


@api.get("/ai/tutor/chats")
async def ai_tutor_chats(subject: str, user: dict = Depends(require_roles("student"))):
    msgs = await db.tutor_messages.find({"student_id": user["id"], "subject": subject}, {"_id": 0}).sort("created_at", 1).to_list(5000)
    chats = {}
    for m in msgs:
        c = chats.setdefault(m["chat_id"], {"chat_id": m["chat_id"], "subject": m["subject"], "started_at": m["created_at"], "preview": None})
        if m["role"] == "user" and not c["preview"]:
            c["preview"] = m["content"][:60]
        c["last_at"] = m["created_at"]
    return {"chats": sorted(chats.values(), key=lambda x: x["last_at"], reverse=True)}


@api.get("/ai/tutor/chat/{chat_id}")
async def ai_tutor_chat_messages(chat_id: str, user: dict = Depends(require_roles("student"))):
    msgs = await db.tutor_messages.find({"chat_id": chat_id, "student_id": user["id"]}, {"_id": 0}).sort("created_at", 1).to_list(5000)
    out = []
    for m in msgs:
        titles = []
        if m["role"] == "assistant" and m.get("used_item_ids"):
            for it in await db.curriculum_items.find({"id": {"$in": m["used_item_ids"]}}, {"_id": 0}).to_list(20):
                titles.append({"title": it.get("title") or it.get("topic"), "chapter": it.get("chapter"), "contributor_name": it.get("contributor_name")})
        out.append({"role": m["role"], "content": m["content"], "grounded": m.get("grounded", bool(m.get("used_item_ids"))),
                    "used_item_titles": titles, "created_at": m["created_at"]})
    return {"chat_id": chat_id, "messages": out}


@api.get("/ai/tutor/debug/{chat_id}")
async def ai_tutor_debug(chat_id: str, user: dict = Depends(require_admin_or_principal)):
    """Observability (admin/principal, NEVER shown to students): per-message engine metadata."""
    iid = user["institution_id"]
    msgs = await db.tutor_messages.find({"chat_id": chat_id, "institution_id": iid}, {"_id": 0}).sort("created_at", 1).to_list(5000)
    return {"chat_id": chat_id, "messages": [{
        "role": m["role"], "intent": m.get("intent"), "strategy": m.get("strategy"),
        "memory_used": m.get("memory_used"), "grounded": m.get("grounded"),
        "used_item_ids": m.get("used_item_ids", []), "check_question": m.get("check_question"),
        "created_at": m["created_at"]} for m in msgs]}


@api.get("/ai/library")
async def ai_library(user: dict = Depends(require_roles("student"))):
    """Student's grade published+ai_enabled curricula with ONLY approved+active items, grouped."""
    iid = user["institution_id"]
    if not await _ai_layer_enabled(iid):
        raise HTTPException(status_code=403, detail="AI Tutor is not available for your school")
    class_name, _ = await _ai_student_grade(user)
    year = await _active_year_name(iid)
    curs = await db.curricula.find({"institution_id": iid, "academic_year": year, "class_name": class_name,
                                    "status": "published", "ai_enabled": True}, {"_id": 0}).to_list(500)
    out = []
    for c in curs:
        # query-level exclusion: only approved + active items ever leave the DB
        items = await db.curriculum_items.find(
            {"curriculum_id": c["id"], "status": "approved", "active": True}, {"_id": 0}).sort([("order", 1), ("contributed_at", 1)]).to_list(5000)
        chapters = {}
        for it in items:
            if it["item_type"] in ("chapter", "topic"):
                continue
            ch = it.get("chapter") or "General"
            chapters.setdefault(ch, []).append({
                "id": it["id"], "item_type": it["item_type"], "topic": it.get("topic"),
                "title": it.get("title"), "description": it.get("description"),
                "text_content": it.get("text_content"), "has_file": bool(it.get("file_path")),
                "file_name": it.get("file_name"), "contributor_name": it.get("contributor_name")})
        out.append({"curriculum_id": c["id"], "subject": c["subject"], "name": c["name"],
                    "chapters": [{"chapter": k, "materials": v} for k, v in chapters.items()]})
    return {"class_name": class_name, "subjects": out}


# ========================= Phase 36 — LNMO Central Library =========================
AI_LIB_MAX_MB = 60
AI_LIB_FILE_TYPES = {"application/pdf": "pdf",
                     "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
                     "text/plain": "txt"}
LIB_MATERIAL_TYPES = {"textbook", "notes", "question_paper", "worksheet", "reference", "other"}
LIB_BOARD = "kerala_scert"

# Kerala SCERT Class 8 chapter templates (editable by platform admin; sourced from SCERT textbook lists)
PHASE36_SCERT_TEMPLATES = [
    {"board": LIB_BOARD, "grade": "Grade 8", "subject": "Mathematics", "chapters": [
        {"title": "Equal Triangles", "topics": []},
        {"title": "Equations", "topics": []},
        {"title": "Polygons", "topics": []},
        {"title": "Identities", "topics": []},
        {"title": "Money Maths", "topics": []},
        {"title": "Construction of Quadrilaterals", "topics": []},
        {"title": "Ratio", "topics": []},
        {"title": "Area of Quadrilaterals", "topics": []},
        {"title": "Negative Numbers", "topics": []},
        {"title": "Statistics", "topics": []},
    ]},
    {"board": LIB_BOARD, "grade": "Grade 8", "subject": "Basic Science", "chapters": [
        {"title": "Measurement and Units", "topics": []},
        {"title": "Motion and Force", "topics": []},
        {"title": "Pressure", "topics": []},
        {"title": "Chemistry of Changes", "topics": []},
        {"title": "Elements and Compounds", "topics": []},
        {"title": "Metals and Non-Metals", "topics": []},
        {"title": "Let's Cultivate and Reap Goodness", "topics": []},
        {"title": "Origin of Life, Origin of Living Things", "topics": []},
        {"title": "Cells and Cell Clusters", "topics": []},
        {"title": "Static Electricity", "topics": []},
        {"title": "Magnetism and Electricity", "topics": []},
        {"title": "Spherical Mirrors", "topics": []},
        {"title": "Acids, Bases, Salts", "topics": []},
        {"title": "Water", "topics": []},
        {"title": "Chemistry of Matter", "topics": []},
        {"title": "Tree of Life", "topics": []},
        {"title": "The Beauty of Diversity", "topics": []},
        {"title": "Cells that Become Daughter Cells", "topics": []},
    ]},
]


def _lib_extract_bg(lib_id, content, mime, filename):
    """Background text extraction for large uploads — sync pymongo, independent of the event loop."""
    try:
        text = _ai_extract_text(content, mime, filename)
    except Exception:
        text = ""
    try:
        from pymongo import MongoClient as _MC
        _MC(mongo_url)[os.environ['DB_NAME']].platform_library.update_one(
            {"id": lib_id}, {"$set": {"extracted_text": text, "processing": False}})
    except Exception:
        pass


def _lib_public(x):
    return {k: x.get(k) for k in ("id", "board", "grade", "subject", "academic_year", "material_type", "title", "description",
                                  "file_name", "mime", "size", "status", "source", "submitted_by_school",
                                  "submitted_by_school_name", "processing", "created_at", "created_by_name")} | {
        "has_file": bool(x.get("file_path")), "has_text": bool(x.get("extracted_text"))}


@api.post("/platform/library")
async def platform_library_upload(board: str = Form(LIB_BOARD), grade: str = Form(...), subject: str = Form(...),
                                  material_type: str = Form(...), title: str = Form(...),
                                  description: str = Form(""), academic_year: str = Form(""),
                                  file: UploadFile = File(None),
                                  user: dict = Depends(require_roles("platform_admin"))):
    if material_type not in LIB_MATERIAL_TYPES:
        raise HTTPException(status_code=400, detail="Invalid material type")
    now = now_iso()
    lid = str(uuid.uuid4())
    doc = {"id": lid, "board": board or LIB_BOARD, "grade": grade.strip(), "subject": subject.strip(),
           "academic_year": (academic_year or "").strip(),
           "material_type": material_type, "title": title.strip(), "description": (description or "").strip(),
           "file_path": None, "file_name": None, "mime": None, "size": 0, "extracted_text": "",
           "status": "published", "source": "platform", "submitted_by_school": None,
           "processing": False, "created_at": now, "created_by": user["id"], "created_by_name": user.get("name")}
    if file is not None:
        if file.content_type not in AI_LIB_FILE_TYPES:
            raise HTTPException(status_code=400, detail="Allowed files: PDF, DOCX, TXT")
        content = await file.read()
        if len(content) > AI_LIB_MAX_MB * 1024 * 1024:
            raise HTTPException(status_code=400, detail=f"File must be under {AI_LIB_MAX_MB} MB")
        path = f"lnmo/library/{lid}/{uuid.uuid4()}.{AI_LIB_FILE_TYPES[file.content_type]}"
        try:
            _put_object(path, content, file.content_type)
        except Exception:
            raise HTTPException(status_code=502, detail="File storage is unavailable right now — try again shortly")
        doc.update({"file_path": path, "file_name": file.filename, "mime": file.content_type,
                    "size": len(content), "processing": True})
    await db.platform_library.insert_one(dict(doc))
    if doc.get("processing"):
        import threading
        threading.Thread(target=_lib_extract_bg, args=(lid, content, file.content_type, file.filename or ""),
                         daemon=True).start()
    await audit(user, "platform_library_upload", "platform_library", lid, f"{grade} {subject} · {title}", None)
    return {"item": _lib_public(doc)}


@api.post("/platform/library/bulk")
async def platform_library_bulk(meta: str = Form(...), board: str = Form(LIB_BOARD),
                                files: List[UploadFile] = File(...),
                                user: dict = Depends(require_roles("platform_admin"))):
    """Phase 37 (Feature A): upload many files at once; `meta` is a JSON list (one per file) with
    per-row {grade, subject, material_type, title?}. Text extraction runs in the background per file."""
    import json as _json
    import threading
    try:
        metas = _json.loads(meta)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid meta payload")
    if not isinstance(metas, list) or len(metas) != len(files):
        raise HTTPException(status_code=400, detail="meta must be a JSON list matching the number of files")
    created = []
    for m, f in zip(metas, files):
        if f.content_type not in AI_LIB_FILE_TYPES:
            raise HTTPException(status_code=400, detail=f"{f.filename}: allowed files are PDF, DOCX, TXT")
        content = await f.read()
        if len(content) > AI_LIB_MAX_MB * 1024 * 1024:
            raise HTTPException(status_code=400, detail=f"{f.filename}: must be under {AI_LIB_MAX_MB} MB")
        mt = (m.get("material_type") or "other").strip()
        if mt not in LIB_MATERIAL_TYPES:
            mt = "other"
        if not (m.get("grade") or "").strip() or not (m.get("subject") or "").strip():
            raise HTTPException(status_code=400, detail=f"{f.filename}: grade and subject are required")
        lid = str(uuid.uuid4())
        path = f"lnmo/library/{lid}/{uuid.uuid4()}.{AI_LIB_FILE_TYPES[f.content_type]}"
        try:
            _put_object(path, content, f.content_type)
        except Exception:
            raise HTTPException(status_code=502, detail="File storage is unavailable right now — try again shortly")
        title = (m.get("title") or "").strip() or (f.filename or "Untitled")
        doc = {"id": lid, "board": board or LIB_BOARD, "grade": m["grade"].strip(), "subject": m["subject"].strip(),
               "academic_year": (m.get("academic_year") or "").strip(),
               "material_type": mt, "title": title, "description": (m.get("description") or "").strip(),
               "file_path": path, "file_name": f.filename, "mime": f.content_type, "size": len(content),
               "extracted_text": "", "status": "published", "source": "platform", "submitted_by_school": None,
               "processing": True, "created_at": now_iso(), "created_by": user["id"], "created_by_name": user.get("name")}
        await db.platform_library.insert_one(dict(doc))
        threading.Thread(target=_lib_extract_bg, args=(lid, content, f.content_type, f.filename or ""), daemon=True).start()
        created.append(_lib_public(doc))
    await audit(user, "platform_library_bulk_upload", "platform_library", "-", f"{len(created)} files", None)
    return {"items": created, "count": len(created)}


@api.get("/platform/library")
async def platform_library_list(grade: str = "", subject: str = "", material_type: str = "",
                                status: str = "", board: str = "", q: str = "",
                                user: dict = Depends(require_roles("platform_admin"))):
    query = {}
    for k, v in (("grade", grade), ("subject", subject), ("material_type", material_type),
                 ("status", status), ("board", board)):
        if v:
            query[k] = v
    if q:
        query["title"] = {"$regex": q, "$options": "i"}
    rows = await db.platform_library.find(query, {"_id": 0}).sort("created_at", -1).to_list(2000)
    return {"items": [_lib_public(r) for r in rows]}


@api.post("/platform/library/{lid}/approve")
async def platform_library_approve(lid: str, user: dict = Depends(require_roles("platform_admin"))):
    r = await db.platform_library.find_one({"id": lid}, {"_id": 0})
    if not r:
        raise HTTPException(status_code=404, detail="Library item not found")
    await db.platform_library.update_one({"id": lid}, {"$set": {"status": "published"}})
    await audit(user, "platform_library_approve", "platform_library", lid, r.get("title"), None)
    return {"ok": True, "status": "published"}


@api.delete("/platform/library/{lid}")
async def platform_library_delete(lid: str, user: dict = Depends(require_roles("platform_admin"))):
    r = await db.platform_library.find_one({"id": lid}, {"_id": 0})
    if not r:
        raise HTTPException(status_code=404, detail="Library item not found")
    # Guard: block deletion while schools still reference this library item (reference-only attach).
    refs = await db.curriculum_items.find(
        {"library_id": lid, "status": {"$ne": "deleted"}}, {"_id": 0, "institution_id": 1}).to_list(5000)
    if refs:
        iids = list({x.get("institution_id") for x in refs if x.get("institution_id")})
        insts = await db.institutions.find({"id": {"$in": iids}}, {"_id": 0, "id": 1, "name": 1}).to_list(1000)
        names = [i.get("name") for i in insts] or iids
        raise HTTPException(status_code=409, detail={
            "message": f"This item is attached by {len(iids)} school(s). Ask them to detach it before deleting.",
            "reference_count": len(refs), "schools": names})
    if r.get("file_path"):
        try:
            _delete_object(r["file_path"])
        except Exception:
            pass
    await db.platform_library.delete_one({"id": lid})
    await audit(user, "platform_library_delete", "platform_library", lid, r.get("title"), None)
    return {"ok": True}


# ---- Chapter templates (platform-managed) ----
class TemplateBody(BaseModel):
    board: str = LIB_BOARD
    grade: str
    subject: str
    chapters: list  # [{title, topics: []}]


@api.get("/platform/curriculum-templates")
async def platform_templates_list(board: str = "", grade: str = "", subject: str = "",
                                   user: dict = Depends(require_roles("platform_admin"))):
    query = {k: v for k, v in (("board", board), ("grade", grade), ("subject", subject)) if v}
    rows = await db.platform_curriculum_templates.find(query, {"_id": 0}).sort([("grade", 1), ("subject", 1)]).to_list(1000)
    return {"templates": rows}


@api.post("/platform/curriculum-templates")
async def platform_template_upsert(body: TemplateBody, user: dict = Depends(require_roles("platform_admin"))):
    key = {"board": body.board or LIB_BOARD, "grade": body.grade.strip(), "subject": body.subject.strip()}
    existing = await db.platform_curriculum_templates.find_one(key, {"_id": 0})
    chapters = [{"title": (c.get("title") or "").strip(), "topics": c.get("topics") or []}
                for c in body.chapters if (c.get("title") or "").strip()]
    if existing:
        await db.platform_curriculum_templates.update_one(key, {"$set": {"chapters": chapters}})
        tid = existing["id"]
    else:
        tid = str(uuid.uuid4())
        await db.platform_curriculum_templates.insert_one({**key, "id": tid, "chapters": chapters, "created_at": now_iso()})
    await audit(user, "platform_template_upsert", "platform_curriculum_templates", tid, f"{body.grade} {body.subject}", None)
    return {"ok": True, "id": tid, "chapters": chapters}


# ---- School side: browse / import / submit / template prefill ----
@api.get("/ai/central-library")
async def ai_central_library(grade: str = "", subject: str = "", material_type: str = "", q: str = "",
                             user: dict = Depends(require_roles("institution_admin", "teacher"))):
    """Published LNMO Library items (shared, platform-governed). Schools browse to import."""
    query = {"status": "published"}
    for k, v in (("grade", grade), ("subject", subject), ("material_type", material_type)):
        if v:
            query[k] = v
    if q.strip():
        rx = {"$regex": re.escape(q.strip()), "$options": "i"}
        query["$or"] = [{"title": rx}, {"description": rx}]
    rows = await db.platform_library.find(query, {"_id": 0}).sort("created_at", -1).to_list(2000)
    return {"items": [_lib_public(r) for r in rows]}


@api.get("/ai/central-library/{lid}")
async def ai_central_library_detail(lid: str, user: dict = Depends(require_roles("institution_admin", "teacher"))):
    """Full detail incl. extracted text — used for the in-app preview before attaching."""
    r = await db.platform_library.find_one({"id": lid, "status": "published"}, {"_id": 0})
    if not r:
        raise HTTPException(status_code=404, detail="Library item not found")
    out = _lib_public(r)
    out["extracted_text"] = r.get("extracted_text") or ""
    return out


@api.get("/ai/central-library/{lid}/file")
async def ai_central_library_file(lid: str, user: dict = Depends(require_roles("institution_admin", "teacher"))):
    """Stream the single stored library file for in-app preview. Teachers/admins of ANY school
    may preview the shared catalogue; students have no access to this route (they only see
    imported + approved content via their curriculum)."""
    r = await db.platform_library.find_one({"id": lid, "status": "published"}, {"_id": 0})
    if not r or not r.get("file_path"):
        raise HTTPException(status_code=404, detail="File not found")
    data, ctype = _get_object(r["file_path"])
    return Response(content=data, media_type=r.get("mime") or ctype,
                    headers={"Content-Disposition": f'inline; filename="{r.get("file_name") or "file"}"'})


@api.get("/ai/curriculum-template")
async def ai_curriculum_template(board: str = LIB_BOARD, grade: str = "", subject: str = "",
                                 user: dict = Depends(require_roles("institution_admin", "teacher"))):
    t = await db.platform_curriculum_templates.find_one(
        {"board": board or LIB_BOARD, "grade": grade, "subject": subject}, {"_id": 0})
    return {"template": t}


class ImportLibraryBody(BaseModel):
    library_id: str
    chapter: Optional[str] = None


@api.post("/ai/curriculum/{cid}/import-library")
async def ai_import_library(cid: str, body: ImportLibraryBody,
                            user: dict = Depends(require_roles("institution_admin", "teacher"))):
    iid = user["institution_id"]
    c = await db.curricula.find_one({"id": cid, "institution_id": iid, "is_deleted": {"$ne": True}}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Curriculum not found")
    if not await _ai_can_contribute_b(user, c):
        raise HTTPException(status_code=403, detail="You can't contribute to this curriculum")
    lib = await db.platform_library.find_one({"id": body.library_id, "status": "published"}, {"_id": 0})
    if not lib:
        raise HTTPException(status_code=404, detail="Library item not found")
    if lib["material_type"] in AI_MATERIAL_TYPES and not (body.chapter or "").strip():
        raise HTTPException(status_code=400, detail="Choose a chapter for this material")
    data = {"item_type": lib["material_type"], "chapter": (body.chapter or "").strip(),
            "title": lib["title"], "description": lib.get("description"),
            "file_path": lib.get("file_path"), "file_name": lib.get("file_name"), "mime": lib.get("mime"),
            "extracted_text": lib.get("extracted_text") or "",
            "source": "lnmo_library", "library_id": lib["id"]}
    item = _ai_new_item(c, data, user)
    await db.curriculum_items.insert_one(dict(item))
    await audit(user, "ai_import_library", "curriculum_items", item["id"], f"{lib['title']} → {c['class_name']} {c['subject']}", iid)
    return {"item": _ai_item_public(item)}


class SubmitLibraryBody(BaseModel):
    item_id: str


@api.post("/ai/curriculum/{cid}/submit-to-library")
async def ai_submit_to_library(cid: str, body: SubmitLibraryBody,
                               user: dict = Depends(require_roles("institution_admin", "teacher"))):
    iid = user["institution_id"]
    c = await db.curricula.find_one({"id": cid, "institution_id": iid, "is_deleted": {"$ne": True}}, {"_id": 0})
    if not c:
        raise HTTPException(status_code=404, detail="Curriculum not found")
    if not await _ai_can_contribute_b(user, c):
        raise HTTPException(status_code=403, detail="You can't submit from this curriculum")
    it = await db.curriculum_items.find_one({"id": body.item_id, "curriculum_id": cid, "status": {"$ne": "deleted"}}, {"_id": 0})
    if not it:
        raise HTTPException(status_code=404, detail="Material not found")
    mtype = it["item_type"] if it["item_type"] in LIB_MATERIAL_TYPES else "other"
    inst = await db.institutions.find_one({"id": iid}, {"_id": 0, "name": 1})
    lid = str(uuid.uuid4())
    doc = {"id": lid, "board": LIB_BOARD, "grade": c["class_name"], "subject": c["subject"],
           "material_type": mtype, "title": it.get("title") or it.get("topic") or it["item_type"],
           "description": it.get("description") or "", "file_path": it.get("file_path"),
           "file_name": it.get("file_name"), "mime": it.get("mime"), "size": 0,
           "extracted_text": it.get("extracted_text") or "", "status": "pending", "source": "school",
           "submitted_by_school": iid, "submitted_by_school_name": (inst or {}).get("name"),
           "processing": False, "created_at": now_iso(), "created_by": user["id"], "created_by_name": user.get("name")}
    await db.platform_library.insert_one(dict(doc))
    await audit(user, "ai_submit_to_library", "platform_library", lid, doc["title"], iid)
    return {"ok": True, "status": "pending"}

# ==================== PHASE 41: PROMOTION & ACADEMIC-YEAR ROLLOVER ====================
# Data-model note: in this schema academic_units, classes and sections are institution-scoped and
# span academic years (no academic_year field). Only academic_years records plus enrollments/
# timetable/marks/attendance are year-keyed. "Auto-clone structure" therefore means: ensure the
# to_year academic_years row exists; classes/sections are already shared and need no duplication.
TERMINAL_GRADE = 12


def _grade_num(class_name):
    m = re.search(r"(\d+)", class_name or "")
    return int(m.group(1)) if m else None


async def _promo_division_map(iid):
    rows = await db.classes.find({"institution_id": iid}, {"_id": 0, "name": 1, "academic_unit_name": 1}).to_list(2000)
    return {c["name"]: c.get("academic_unit_name") for c in rows}


def _promo_counts(decisions):
    out = {"promote": 0, "detain": 0, "transfer_out": 0, "graduate": 0}
    for d in decisions:
        out[d.get("decision", "promote")] = out.get(d.get("decision", "promote"), 0) + 1
    return out


async def _promo_run_or_404(iid, run_id):
    run = await db.promotion_runs.find_one({"id": run_id, "institution_id": iid}, {"_id": 0})
    if not run:
        raise HTTPException(status_code=404, detail="Promotion run not found")
    return run


@api.post("/promotion/preview")
async def promotion_preview(payload: dict = Body(...), user: dict = Depends(require_admin_or_whole_principal)):
    """Dry-run: compute per-student promotion mapping for from_year→to_year and persist a
    preview run + default decisions. Never mutates students/enrollments. Auto-creates the
    to_year academic_years row if missing (reported)."""
    iid = user["institution_id"]
    from_year = (payload.get("from_year") or "").strip()
    to_year = (payload.get("to_year") or "").strip()
    if not from_year or not to_year:
        raise HTTPException(status_code=400, detail="from_year and to_year are required")
    if from_year == to_year:
        raise HTTPException(status_code=400, detail="from_year and to_year must differ")
    if not await db.academic_years.find_one({"institution_id": iid, "name": from_year}):
        raise HTTPException(status_code=400, detail="The from-year does not exist")
    cloned = {"academic_year_created": False,
              "note": "Classes, sections and divisions are shared across years in this system — no cloning needed."}
    if not await db.academic_years.find_one({"institution_id": iid, "name": to_year}):
        await db.academic_years.insert_one({"id": str(uuid.uuid4()), "institution_id": iid,
                                            "name": to_year, "status": "upcoming", "created_at": now_iso()})
        cloned["academic_year_created"] = True
    enrs = await db.enrollments.find({"institution_id": iid, "academic_year": from_year,
                                      "status": {"$ne": "completed"}}, {"_id": 0}).to_list(50000)
    if not enrs:
        raise HTTPException(status_code=400, detail="No active enrollments found in the from-year")
    # replace any existing (un-executed) preview for the same year pair
    async for o in db.promotion_runs.find({"institution_id": iid, "from_year": from_year,
                                           "to_year": to_year, "status": "preview"}, {"_id": 0, "id": 1}):
        await db.promotion_decisions.delete_many({"run_id": o["id"]})
        await db.promotion_runs.delete_one({"id": o["id"]})
    run_id = str(uuid.uuid4())
    div_map = await _promo_division_map(iid)
    decisions = []
    for e in enrs:
        fc = e.get("class_name")
        fs = e.get("section")
        n = _grade_num(fc)
        if n is not None and n >= TERMINAL_GRADE:
            decision, to_class, to_section = "graduate", None, None
        else:
            decision = "promote"
            to_class = f"Grade {n + 1}" if n is not None else fc
            to_section = fs
        decisions.append({
            "id": str(uuid.uuid4()), "run_id": run_id, "institution_id": iid,
            "student_id": e.get("student_id"), "student_name": e.get("student_name"),
            "admission_no": e.get("admission_no"), "from_class": fc, "from_section": fs,
            "from_year": from_year, "to_year": to_year, "division": div_map.get(fc),
            "to_class": to_class, "to_section": to_section, "decision": decision,
            "teacher_recommendation": None, "recommendation_note": "", "recommended_by": None,
            "confirmed_by": None, "created_at": now_iso()})
    run = {"id": run_id, "institution_id": iid, "from_year": from_year, "to_year": to_year,
           "status": "preview", "created_by": user["id"], "created_by_name": user.get("name"),
           "created_at": now_iso(), "student_count": len(decisions)}
    await db.promotion_runs.insert_one(dict(run))
    if decisions:
        await db.promotion_decisions.insert_many([dict(d) for d in decisions])
    await audit(user, "promotion_preview", "promotion_runs", run_id, f"{from_year} → {to_year}", iid)
    for d in decisions:
        d.pop("_id", None)
    return {"run": run, "decisions": decisions, "summary": _promo_counts(decisions), "structure": cloned,
            **await _promo_dues(iid, decisions)}


@api.get("/promotion/runs")
async def promotion_list_runs(user: dict = Depends(require_admin_or_principal)):
    iid = user["institution_id"]
    runs = await db.promotion_runs.find({"institution_id": iid}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return {"runs": runs}


@api.get("/promotion/{run_id}")
async def promotion_get_run(run_id: str, user: dict = Depends(require_admin_or_principal)):
    iid = user["institution_id"]
    run = await _promo_run_or_404(iid, run_id)
    decs = await db.promotion_decisions.find({"run_id": run_id}, {"_id": 0}).sort("student_name", 1).to_list(50000)
    scope = await principal_scope(user)
    if scope and not scope["whole_school"]:
        allowed = set(scope["class_names"] or [])
        decs = [d for d in decs if d.get("from_class") in allowed]
    return {"run": run, "decisions": decs, "summary": _promo_counts(decs), **await _promo_dues(iid, decs)}


async def _promo_decision_or_404(iid, did):
    d = await db.promotion_decisions.find_one({"id": did, "institution_id": iid}, {"_id": 0})
    if not d:
        raise HTTPException(status_code=404, detail="Decision not found")
    run = await _promo_run_or_404(iid, d["run_id"])
    if run["status"] != "preview":
        raise HTTPException(status_code=409, detail="This promotion run is no longer editable")
    return d, run


@api.put("/promotion/decisions/{did}/recommend")
async def promotion_recommend(did: str, payload: dict = Body(...), user: dict = Depends(get_current_user)):
    """Class teacher of the student's section (or admin / in-scope principal) records a
    promote|detain recommendation. A recommendation alone never detains — it must be confirmed."""
    iid = user.get("institution_id")
    if not iid:
        raise HTTPException(status_code=403, detail="Access denied")
    d, run = await _promo_decision_or_404(iid, did)
    rec = payload.get("recommendation")
    if rec not in ("promote", "detain"):
        raise HTTPException(status_code=400, detail="recommendation must be 'promote' or 'detain'")
    is_admin = user["role"] == "institution_admin"
    scope = await principal_scope(user)
    is_scoped_principal = scope is not None and (scope["whole_school"] or d.get("from_class") in set(scope["class_names"] or []))
    sec = await db.sections.find_one({"institution_id": iid, "class_name": d.get("from_class"),
                                      "name": d.get("from_section")}, {"_id": 0})
    is_class_teacher = sec is not None and sec.get("class_teacher_id") == user["id"]
    if not (is_admin or is_scoped_principal or is_class_teacher):
        raise HTTPException(status_code=403, detail="Only the class teacher or a principal/admin can recommend")
    await db.promotion_decisions.update_one({"id": did}, {"$set": {
        "teacher_recommendation": rec, "recommendation_note": (payload.get("note") or "").strip(),
        "recommended_by": user.get("name") or user.get("email")}})
    await audit(user, "promotion_recommend", "promotion_decisions", did, f"{d.get('student_name')}: {rec}", iid)
    return await db.promotion_decisions.find_one({"id": did}, {"_id": 0})


@api.put("/promotion/{run_id}/recommend-bulk")
async def promotion_recommend_bulk(run_id: str, payload: dict = Body(...), user: dict = Depends(get_current_user)):
    """Apply one promote|detain recommendation to every student in a section (class_name+section).
    Rule: rows that already carry an individual recommendation are SKIPPED unless override=true.
    Recommendations still require principal/admin confirmation to become decisions."""
    iid = user.get("institution_id")
    if not iid:
        raise HTTPException(status_code=403, detail="Access denied")
    run = await _promo_run_or_404(iid, run_id)
    if run["status"] != "preview":
        raise HTTPException(status_code=409, detail="This promotion run is no longer editable")
    rec = payload.get("recommendation")
    if rec not in ("promote", "detain"):
        raise HTTPException(status_code=400, detail="recommendation must be 'promote' or 'detain'")
    section = (payload.get("section") or "").strip()
    class_name = (payload.get("class_name") or "").strip()
    if not section:
        raise HTTPException(status_code=400, detail="section is required")
    override = bool(payload.get("override"))
    note = (payload.get("note") or "").strip()
    q = {"run_id": run_id, "institution_id": iid, "from_section": section}
    if class_name:
        q["from_class"] = class_name
    decs = await db.promotion_decisions.find(q, {"_id": 0}).to_list(50000)
    if not decs:
        return {"applied": 0, "skipped": 0}
    target_classes = {d["from_class"] for d in decs}
    is_admin = user["role"] == "institution_admin"
    scope = await principal_scope(user)
    is_scoped_principal = scope is not None and (scope["whole_school"] or target_classes <= set(scope["class_names"] or []))
    if not (is_admin or is_scoped_principal):
        ok = True
        for cn in target_classes:
            sec = await db.sections.find_one({"institution_id": iid, "class_name": cn, "name": section})
            if not sec or sec.get("class_teacher_id") != user["id"]:
                ok = False
                break
        if not ok:
            raise HTTPException(status_code=403, detail="Only the class teacher, an in-scope principal or an admin can bulk-recommend this section")
    applied, skipped = 0, 0
    for d in decs:
        if d.get("teacher_recommendation") and not override:
            skipped += 1
            continue
        await db.promotion_decisions.update_one({"id": d["id"]}, {"$set": {
            "teacher_recommendation": rec, "recommendation_note": note,
            "recommended_by": user.get("name") or user.get("email")}})
        applied += 1
    await audit(user, "promotion_recommend_bulk", "promotion_runs", run_id,
                f"{class_name or ''} {section}: {rec} ×{applied}", iid)
    return {"applied": applied, "skipped": skipped}


@api.put("/promotion/decisions/{did}")
async def promotion_decide(did: str, payload: dict = Body(...), user: dict = Depends(require_admin_or_principal)):
    """Admin / in-scope principal sets the final decision and optional to_section override."""
    iid = user["institution_id"]
    d, run = await _promo_decision_or_404(iid, did)
    scope = await principal_scope(user)
    if scope and not scope["whole_school"] and d.get("from_class") not in set(scope["class_names"] or []):
        raise HTTPException(status_code=403, detail="This class is outside your assigned scope")
    decision = payload.get("decision", d.get("decision"))
    if decision not in ("promote", "detain", "transfer_out", "graduate"):
        raise HTTPException(status_code=400, detail="Invalid decision")
    updates = {"decision": decision, "confirmed_by": user.get("name") or user.get("email")}
    n = _grade_num(d.get("from_class"))
    if decision == "promote":
        updates["to_class"] = f"Grade {n + 1}" if n is not None else d.get("from_class")
        updates["to_section"] = (payload.get("to_section") or d.get("to_section") or d.get("from_section"))
    elif decision == "detain":
        updates["to_class"] = d.get("from_class")
        updates["to_section"] = (payload.get("to_section") or d.get("from_section"))
    else:  # graduate / transfer_out
        updates["to_class"] = None
        updates["to_section"] = None
    await db.promotion_decisions.update_one({"id": did}, {"$set": updates})
    await audit(user, "promotion_decide", "promotion_decisions", did, f"{d.get('student_name')}: {decision}", iid)
    return await db.promotion_decisions.find_one({"id": did}, {"_id": 0})


@api.post("/promotion/{run_id}/execute")
async def promotion_execute(run_id: str, user: dict = Depends(require_roles("institution_admin"))):
    """Apply the confirmed decisions. Creates new to_year enrollments, completes old ones,
    updates student placement, marks graduates alumni, disables transferred-out logins."""
    iid = user["institution_id"]
    run = await _promo_run_or_404(iid, run_id)
    if run["status"] == "executed":
        raise HTTPException(status_code=409, detail="This run has already been executed")
    if run["status"] != "preview":
        raise HTTPException(status_code=409, detail="Only a preview run can be executed")
    from_year, to_year = run["from_year"], run["to_year"]
    if not await db.enrollments.find_one({"institution_id": iid, "academic_year": from_year,
                                          "status": {"$ne": "completed"}}):
        raise HTTPException(status_code=400, detail="No active enrollments remain in the from-year")
    decs = await db.promotion_decisions.find({"run_id": run_id}, {"_id": 0}).to_list(50000)
    counts = {"promote": 0, "detain": 0, "transfer_out": 0, "graduate": 0}
    run_items = []
    for d in decs:
        sid = d["student_id"]
        dec = d.get("decision", "promote")
        sub = f"{d.get('admission_no') or '—'} · {d.get('from_class') or ''} {d.get('from_section') or ''}".strip()
        try:
            reason = await _promo_apply_one(iid, run_id, d, sid, dec, from_year, to_year)
        except Exception as e:  # noqa: BLE001
            run_items.append(phase59.item(sid, d.get("student_name"), "failed", f"Could not apply '{dec}': {e}", "error", sub,
                                          phase59.fix("open_student", sid)))
            continue
        run_items.append(phase59.item(sid, d.get("student_name"), "created", reason, dec, sub, phase59.fix("open_student", sid)))
        counts[dec] = counts.get(dec, 0) + 1
    await db.promotion_runs.update_one({"id": run_id}, {"$set": {
        "status": "executed", "executed_by": user.get("name") or user.get("email"), "executed_at": now_iso()}})
    await audit(user, "promotion_execute", "promotion_runs", run_id, f"{from_year} → {to_year}", iid)
    prun = await phase59.save_run(user, "promotion_execute", f"Promotion {from_year} → {to_year}", run_items, ref_id=run_id, extra=dict(counts))
    carry = await _carry_forward_dues(iid, from_year, to_year, [d["student_id"] for d in decs
                                      if d.get("decision", "promote") in ("promote", "detain")], user, run_id)
    crun = await phase59.save_run(user, "dues_carry_forward", f"Dues carry-forward {from_year} → {to_year}", carry["items"], ref_id=run_id,
                                  extra={"amount": carry["amount"]})
    carry.update(run_id=crun["run_id"], summary=crun["summary"])
    return {"ok": True, "status": "executed", "summary": counts, "dues_carry_forward": carry,
            "run_id": prun["run_id"], "items": prun["items"], "run_summary": prun["summary"]}


async def _promo_apply_one(iid, run_id, d, sid, dec, from_year, to_year):
    """Apply one promotion decision; returns the human-readable outcome."""
    if dec in ("promote", "detain"):
        to_class = d.get("to_class") or d.get("from_class")
        to_section = d.get("to_section") or d.get("from_section")
        if to_section and not await db.sections.find_one({"institution_id": iid, "class_name": to_class, "name": to_section}):
            await db.sections.insert_one({"id": str(uuid.uuid4()), "institution_id": iid, "name": to_section,
                                          "class_name": to_class, "status": "active", "created_at": now_iso()})
        await db.enrollments.update_many({"institution_id": iid, "student_id": sid, "academic_year": from_year},
                                         {"$set": {"status": "completed", "completed_by_run": run_id}})
        await db.enrollments.insert_one({"id": str(uuid.uuid4()), "institution_id": iid, "student_id": sid,
                                         "student_name": d.get("student_name"), "admission_no": d.get("admission_no"),
                                         "academic_year": to_year, "class_name": to_class, "section": to_section,
                                         "status": "active", "promotion_run_id": run_id, "created_at": now_iso()})
        await db.students.update_one({"id": sid, "institution_id": iid}, {"$set": {
            "class_name": to_class, "section": to_section, "academic_year": to_year,
            "enrollment_status": "enrolled"}})
    elif dec == "graduate":
        await db.enrollments.update_many({"institution_id": iid, "student_id": sid, "academic_year": from_year},
                                         {"$set": {"status": "completed", "completed_by_run": run_id}})
        await db.students.update_one({"id": sid, "institution_id": iid}, {"$set": {
            "enrollment_status": "alumni", "graduated_year": from_year, "promotion_run_id": run_id}})
    elif dec == "transfer_out":
        await db.enrollments.update_many({"institution_id": iid, "student_id": sid, "academic_year": from_year},
                                         {"$set": {"status": "completed", "completed_by_run": run_id}})
        await db.students.update_one({"id": sid, "institution_id": iid}, {"$set": {
            "enrollment_status": "transferred", "promotion_run_id": run_id}})
        st = await db.students.find_one({"id": sid, "institution_id": iid}, {"_id": 0, "user_id": 1})
        if st and st.get("user_id"):
            await db.users.update_one({"id": st["user_id"]}, {"$set": {"status": "inactive", "disabled_by_run": run_id}})
    else:
        raise ValueError(f"unknown decision {dec}")
    if dec == "promote":
        return f"Promoted to {to_class}{' ' + to_section if to_section else ''} ({to_year})"
    if dec == "detain":
        return f"Detained in {to_class}{' ' + to_section if to_section else ''} ({to_year})"
    if dec == "graduate":
        return "Graduated — marked alumni"
    return "Transferred out — portal login disabled" if st and st.get("user_id") else "Transferred out"


@api.post("/promotion/{run_id}/rollback")
async def promotion_rollback(run_id: str, user: dict = Depends(require_roles("institution_admin"))):
    """Reverse an executed run. Blocked if year-scoped academic data (timetable / assessments /
    attendance) already exists under the to_year."""
    iid = user["institution_id"]
    run = await _promo_run_or_404(iid, run_id)
    if run["status"] != "executed":
        raise HTTPException(status_code=409, detail="Only an executed run can be rolled back")
    to_year = run["to_year"]
    blockers = []
    if await db.timetable_entries.find_one({"institution_id": iid, "academic_year": to_year}):
        blockers.append("timetable")
    if await db.assessments.find_one({"institution_id": iid, "academic_year": to_year}):
        blockers.append("assessments/marks")
    if await db.attendance.find_one({"institution_id": iid, "academic_year": to_year}):
        blockers.append("attendance")
    if blockers:
        raise HTTPException(status_code=409, detail=f"Cannot roll back — {to_year} already has {', '.join(blockers)} data. Clear it first.")
    decs = await db.promotion_decisions.find({"run_id": run_id}, {"_id": 0}).to_list(50000)
    for d in decs:
        sid = d["student_id"]
        await db.students.update_one({"id": sid, "institution_id": iid}, {"$set": {
            "class_name": d.get("from_class"), "section": d.get("from_section"),
            "academic_year": d.get("from_year"), "enrollment_status": "enrolled"},
            "$unset": {"graduated_year": "", "promotion_run_id": ""}})
    await db.enrollments.delete_many({"institution_id": iid, "promotion_run_id": run_id})
    await db.enrollments.update_many({"institution_id": iid, "completed_by_run": run_id},
                                     {"$set": {"status": "active"}, "$unset": {"completed_by_run": ""}})
    await db.users.update_many({"disabled_by_run": run_id},
                               {"$set": {"status": "active"}, "$unset": {"disabled_by_run": ""}})
    await db.promotion_runs.update_one({"id": run_id}, {"$set": {
        "status": "rolled_back", "rolled_back_by": user.get("name") or user.get("email"), "rolled_back_at": now_iso()}})
    await audit(user, "promotion_rollback", "promotion_runs", run_id, f"{run['from_year']} → {to_year}", iid)
    return {"ok": True, "status": "rolled_back"}




# ==================== PHASE 43: CRASH ANALYTICS + ISSUE REPORTING ====================
import time as _time
SUPPORT_IMG_TYPES = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
CRASH_RATE_MAX = 60      # max crash posts per IP per window (abuse guard; monkeypatchable in tests)
ISSUE_RATE_MAX = 20      # max issue reports per user per window
RATE_WINDOW = 60
_rate_buckets = {}


def _rate_ok(name, key, max_n, window):
    now = _time.monotonic()
    bucket = _rate_buckets.setdefault(name, {})
    arr = [t for t in bucket.get(key, []) if now - t < window]
    if len(arr) >= max_n:
        bucket[key] = arr
        return False
    arr.append(now)
    bucket[key] = arr
    return True


async def _optional_user(request: Request):
    try:
        return await get_current_user(request)
    except HTTPException:
        return None


def _issue_public(doc):
    return {k: v for k, v in doc.items() if k != "_id"}


@api.post("/support/crash")
async def report_crash(request: Request, payload: dict = Body(...)):
    """Open (optionally authenticated) crash sink. Dedupes by error_signature (same signature →
    occurrence_count++, no new row). IP rate-limited as an abuse guard."""
    ip = request.client.host if request.client else "unknown"
    if not _rate_ok("crash", ip, CRASH_RATE_MAX, RATE_WINDOW):
        raise HTTPException(status_code=429, detail="Too many reports — slow down")
    user = await _optional_user(request)
    msg = (payload.get("message") or "Unknown error").strip()[:2000]
    stack = (payload.get("stack") or "")[:8000]
    first_frame = next((ln.strip() for ln in stack.splitlines() if ln.strip()), "")
    sig = hashlib.sha256(f"{msg}|{first_frame}".encode()).hexdigest()[:16]
    now = now_iso()
    iid = user.get("institution_id") if user else None
    existing = await db.issues.find_one({"type": "crash", "error_signature": sig, "institution_id": iid})
    if existing:
        await db.issues.update_one({"id": existing["id"]},
                                   {"$inc": {"occurrence_count": 1}, "$set": {"last_seen": now}})
        return {"ok": True, "id": existing["id"], "deduped": True,
                "occurrence_count": existing.get("occurrence_count", 1) + 1}
    doc = {"id": str(uuid.uuid4()), "institution_id": iid,
           "user_id": user.get("id") if user else None,
           "user_name": (user.get("name") if user else None) or "Anonymous",
           "role": user.get("role") if user else "anonymous",
           "type": "crash", "title": msg[:140], "description": "", "category": None,
           "page_url": payload.get("page_url"), "route": payload.get("route"),
           "user_agent": (payload.get("user_agent") or request.headers.get("user-agent", ""))[:400],
           "app_version": payload.get("app_version"), "error_message": msg, "error_stack": stack,
           "error_signature": sig, "occurrence_count": 1, "first_seen": now, "last_seen": now,
           "status": "open", "platform_note": "", "created_at": now}
    await db.issues.insert_one(dict(doc))
    return {"ok": True, "id": doc["id"], "deduped": False}


@api.post("/support/issues")
async def create_issue(request: Request, title: str = Form(...), description: str = Form(""),
                       category: str = Form("bug"), page_url: str = Form(""), route: str = Form(""),
                       screenshot: UploadFile = File(None), user: dict = Depends(get_current_user)):
    """Any authenticated user (incl. parent/student) files an issue, with an optional screenshot."""
    if not _rate_ok("issue", user["id"], ISSUE_RATE_MAX, RATE_WINDOW):
        raise HTTPException(status_code=429, detail="Too many reports — please wait a minute")
    if category not in ("bug", "question", "suggestion"):
        raise HTTPException(status_code=400, detail="Invalid category")
    if not (title or "").strip():
        raise HTTPException(status_code=400, detail="A short title is required")
    screenshot_path = None
    if screenshot is not None:
        if screenshot.content_type not in SUPPORT_IMG_TYPES:
            raise HTTPException(status_code=400, detail="Screenshot must be a JPG, PNG or WebP image")
        data = await screenshot.read()
        if len(data) > 5 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="Screenshot must be under 5 MB")
        path = f"lnmo/support/{user['id']}/{uuid.uuid4()}.{SUPPORT_IMG_TYPES[screenshot.content_type]}"
        try:
            res = _put_object(path, data, screenshot.content_type)
        except Exception:
            raise HTTPException(status_code=502, detail="Screenshot storage is unavailable right now — try again shortly")
        screenshot_path = res["path"]
    now = now_iso()
    doc = {"id": str(uuid.uuid4()), "institution_id": user.get("institution_id"),
           "user_id": user["id"], "user_name": user.get("name") or user.get("email"),
           "role": user["role"], "type": "report", "title": title.strip()[:200],
           "description": (description or "").strip(), "category": category,
           "screenshot_path": screenshot_path, "page_url": page_url, "route": route,
           "user_agent": request.headers.get("user-agent", "")[:400], "app_version": None,
           "error_message": None, "error_stack": None, "error_signature": None,
           "occurrence_count": 1, "first_seen": now, "last_seen": now, "status": "open",
           "platform_note": "", "created_at": now}
    await db.issues.insert_one(dict(doc))
    await audit(user, "support_issue", "issues", doc["id"], doc["title"], user.get("institution_id"))
    return {"ok": True, "id": doc["id"], "status": "open"}


def _days_ago_iso(n):
    return (datetime.now(timezone.utc) - timedelta(days=n)).isoformat()


@api.get("/support/issues/stats")
async def issues_stats(user: dict = Depends(require_roles("platform_admin"))):
    open_issues = await db.issues.count_documents({"status": {"$in": ["open", "in_progress"]}})
    crashes_7d = await db.issues.count_documents({"type": "crash", "last_seen": {"$gte": _days_ago_iso(7)}})
    schools = await db.issues.distinct("institution_id", {"institution_id": {"$ne": None}})
    return {"open_issues": open_issues, "crashes_7d": crashes_7d, "schools_affected": len(schools)}


@api.get("/support/issues")
async def list_issues(type: str = "", status: str = "", institution_id: str = "",
                      user: dict = Depends(require_roles("platform_admin"))):
    q = {}
    if type:
        q["type"] = type
    if status:
        q["status"] = status
    if institution_id:
        q["institution_id"] = institution_id
    rows = await db.issues.find(q, {"_id": 0}).sort("last_seen", -1).to_list(2000)
    # attach school names
    iids = {r["institution_id"] for r in rows if r.get("institution_id")}
    names = {i["id"]: i.get("name") async for i in db.institutions.find({"id": {"$in": list(iids)}}, {"id": 1, "name": 1})}
    for r in rows:
        r["institution_name"] = names.get(r.get("institution_id"))
    return {"issues": rows}


@api.get("/support/my-school-issues")
async def my_school_issues(user: dict = Depends(require_admin_or_principal)):
    """School admin / in-scope principal read-only view of their OWN school's reported issues (not crashes)."""
    rows = await db.issues.find({"institution_id": user["institution_id"], "type": "report"},
                                {"_id": 0, "error_stack": 0}).sort("last_seen", -1).to_list(1000)
    return {"issues": rows}


@api.get("/support/issues/{issue_id}")
async def get_issue(issue_id: str, user: dict = Depends(require_roles("platform_admin"))):
    doc = await db.issues.find_one({"id": issue_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Issue not found")
    if doc.get("institution_id"):
        inst = await db.institutions.find_one({"id": doc["institution_id"]}, {"_id": 0, "name": 1})
        doc["institution_name"] = (inst or {}).get("name")
    return doc


@api.put("/support/issues/{issue_id}")
async def update_issue(issue_id: str, payload: dict = Body(...),
                       user: dict = Depends(require_roles("platform_admin"))):
    doc = await db.issues.find_one({"id": issue_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Issue not found")
    updates = {}
    if "status" in payload:
        if payload["status"] not in ("open", "in_progress", "resolved", "closed"):
            raise HTTPException(status_code=400, detail="Invalid status")
        updates["status"] = payload["status"]
        if payload["status"] in ("resolved", "closed"):
            updates["resolved_by"] = user.get("name") or user.get("email")
            updates["resolved_at"] = now_iso()
    if "platform_note" in payload:
        updates["platform_note"] = (payload.get("platform_note") or "").strip()
    if not updates:
        raise HTTPException(status_code=400, detail="Nothing to update")
    await db.issues.update_one({"id": issue_id}, {"$set": updates})
    await audit(user, "support_update", "issues", issue_id, updates.get("status") or "note")
    return await db.issues.find_one({"id": issue_id}, {"_id": 0})


@api.get("/support/issues/{issue_id}/screenshot")
async def get_issue_screenshot(issue_id: str, user: dict = Depends(get_current_user)):
    doc = await db.issues.find_one({"id": issue_id}, {"_id": 0})
    if not doc or not doc.get("screenshot_path"):
        raise HTTPException(status_code=404, detail="No screenshot")
    # platform admin sees all; institution admin only their own school's issue
    if user["role"] == "platform_admin":
        pass
    elif user["role"] == "institution_admin" and doc.get("institution_id") == user.get("institution_id"):
        pass
    else:
        raise HTTPException(status_code=403, detail="Forbidden")
    try:
        data, ctype = _get_object(doc["screenshot_path"])
    except Exception:
        raise HTTPException(status_code=404, detail="No screenshot")
    return Response(content=data, media_type=ctype, headers={"Cache-Control": "private, max-age=300"})




# ==================== PHASE 48: FEES MODULE (core, offline collection) ====================
# Money safety: amounts rounded to paise; payments are append-only (reversal = flag + credit note,
# never delete); paid_amount updated with an atomic guard that makes overpayment impossible even
# under concurrent collection; receipt numbers come from an atomic per-institution+year counter.
from typing import Literal, List as _List  # noqa: E402
from pydantic import BaseModel as _BM, Field as _F  # noqa: E402
from pymongo import ReturnDocument  # noqa: E402
from pymongo.errors import DuplicateKeyError  # noqa: E402

FeeFreq = Literal["annual", "term", "monthly", "one_time"]


class FeeHeadIn(_BM):
    id: Optional[str] = None
    title: str = _F(min_length=1, max_length=80)
    amount: float = _F(ge=0, le=10_000_000)
    frequency: FeeFreq
    optional: bool = False


class LateFeeIn(_BM):
    enabled: bool = False
    type: Literal["flat", "percent"] = "flat"
    value: float = _F(default=0, ge=0, le=1_000_000)
    grace_days: int = _F(default=0, ge=0, le=365)


class FeeStructureIn(_BM):
    name: str = _F(min_length=1, max_length=120)
    academic_year_id: Optional[str] = _F(default=None, max_length=60)
    academic_year: Optional[str] = _F(default=None, max_length=20)  # legacy text; resolved to an id when unambiguous
    academic_unit_id: Optional[str] = None
    class_name: Optional[str] = None
    heads: _List[FeeHeadIn] = _F(min_length=1, max_length=40)
    late_fee: LateFeeIn = LateFeeIn()
    active: bool = True


class FeeDiscountIn(_BM):
    type: Literal["flat", "percent"]
    value: float = _F(gt=0, le=10_000_000)
    reason: Optional[str] = _F(default=None, max_length=200)


class FeeAccountPatch(_BM):
    included_head_ids: Optional[_List[str]] = None
    discount: Optional[FeeDiscountIn] = None
    clear_discount: bool = False


class FeePeriodIn(_BM):
    label: str = _F(min_length=1, max_length=40)
    due_date: str = _F(pattern=r"^\d{4}-\d{2}-\d{2}$")


class FeeGenerateIn(_BM):
    frequency: FeeFreq
    periods: _List[FeePeriodIn] = _F(min_length=1, max_length=12)
    class_name: Optional[str] = None


class FeePaymentIn(_BM):
    invoice_id: str
    amount: float = _F(gt=0, le=10_000_000)
    method: Literal["cash", "upi", "cheque", "bank", "other"]
    reference: Optional[str] = _F(default=None, max_length=80)
    note: Optional[str] = _F(default=None, max_length=300)
    paid_on: Optional[str] = _F(default=None, max_length=10)  # Phase 51: payment date (institution tz); default today


class FeeReverseIn(_BM):
    reason: str = _F(min_length=3, max_length=300)


require_fee_admin = require_roles("institution_admin")


def _r2(x):
    return round(float(x or 0) + 1e-9, 2)


def _today():
    return datetime.now(timezone.utc).date().isoformat()


async def _fee_scope(user):
    """None = whole school; else (class_names, unit_ids) for a unit principal."""
    sc = await principal_scope(user)
    if not sc or sc.get("whole_school"):
        return None
    return set(sc.get("class_names") or []), set(sc.get("unit_ids") or [])


def _struct_in_scope(st, scope):
    return scope is None or st.get("class_name") in scope[0] or st.get("academic_unit_id") in scope[1]


async def _struct_class_names(iid, st):
    if st.get("class_name"):
        return [st["class_name"]]
    return [c["name"] for c in await db.classes.find({"institution_id": iid, "academic_unit_id": st.get("academic_unit_id")},
                                                     {"_id": 0, "name": 1}).to_list(500)]


def _fine_for(inv, late, today):
    """Late fine owed today: 0 if disabled, already applied, fully paid, or within due_date + grace_days."""
    if inv.get("fine_applied") or not (late or {}).get("enabled") or not inv.get("due_date"):
        return 0.0
    if _r2(inv.get("paid_amount")) >= _r2(inv["total"]):
        return 0.0
    limit = (datetime.strptime(inv["due_date"], "%Y-%m-%d").date() + timedelta(days=int(late.get("grace_days") or 0))).isoformat()
    if today <= limit:
        return 0.0
    v = float(late.get("value") or 0)
    return _r2(v if late.get("type") == "flat" else inv["total"] * v / 100)


def _invoice_view(inv, late, today=None):
    today = today or _today()
    projected = _fine_for(inv, late, today)
    fine = _r2(inv.get("fine_amount", 0) + projected)
    due = _r2(inv["total"] + fine)
    paid = _r2(inv.get("paid_amount", 0))
    bal = _r2(due - paid)
    if bal <= 0:
        status = "paid"
    elif inv.get("due_date") and inv["due_date"] < today:
        status = "overdue"
    elif paid > 0:
        status = "partial"
    else:
        status = "pending"
    if inv.get("carried_forward_to"):  # Phase 50: balance moved to a next-year arrears invoice
        bal, status = 0.0, "carried_forward"
    out = {k: v for k, v in inv.items() if k != "_id"}
    out.update({"fine_amount": fine, "fine_projected": projected, "amount_due": due, "paid_amount": paid,
                "balance": max(bal, 0.0), "status": status})
    return out


async def _late_map(structure_ids):
    return {s["id"]: s.get("late_fee") async for s in db.fee_structures.find({"id": {"$in": list(structure_ids)}}, {"_id": 0, "id": 1, "late_fee": 1})}


def _summarize(views):
    open_ = [v for v in views if v["balance"] > 0]
    return {"total": _r2(sum(v["amount_due"] for v in views)), "paid": _r2(sum(v["paid_amount"] for v in views)),
            "balance": _r2(sum(v["balance"] for v in views)),
            "next_due": min((v["due_date"] for v in open_ if v.get("due_date")), default=None),
            "overdue": sum(1 for v in views if v["status"] == "overdue"), "invoices": len(views)}


async def _validate_structure(iid, body: FeeStructureIn):
    if bool(body.academic_unit_id) == bool(body.class_name):
        raise HTTPException(status_code=400, detail="Pick exactly one target: an academic unit OR a class")
    if body.academic_unit_id and not await db.academic_units.find_one({"id": body.academic_unit_id, "institution_id": iid}):
        raise HTTPException(status_code=400, detail="Academic unit not found")
    if body.class_name and not await _class_exists(iid, body.class_name):
        raise HTTPException(status_code=400, detail="Class not found")
    titles = [h.title.strip().lower() for h in body.heads]
    if len(set(titles)) != len(titles):
        raise HTTPException(status_code=400, detail="Fee head titles must be unique within a structure")
    if body.late_fee.enabled and body.late_fee.type == "percent" and body.late_fee.value > 100:
        raise HTTPException(status_code=400, detail="Late fee percent cannot exceed 100")
    heads = []
    for h in body.heads:
        d = h.model_dump()
        d["title"] = d["title"].strip()
        d["amount"] = _r2(d["amount"])
        d["id"] = d.get("id") or str(uuid.uuid4())
        heads.append(d)
    return heads


async def _get_structure(iid, sid, user=None):
    st = await db.fee_structures.find_one({"id": sid, "institution_id": iid, "deleted": {"$ne": True}}, {"_id": 0})
    if not st:
        raise HTTPException(status_code=404, detail="Fee structure not found")
    if user is not None and not _struct_in_scope(st, await _fee_scope(user)):
        raise HTTPException(status_code=403, detail="Outside your assigned scope")
    return st


@api.get("/fees/structures")
async def list_fee_structures(user: dict = Depends(require_admin_or_principal)):
    iid = user["institution_id"]
    scope = await _fee_scope(user)
    units = {u["id"]: u.get("name") async for u in db.academic_units.find({"institution_id": iid}, {"_id": 0, "id": 1, "name": 1})}
    rows = []
    legacy = await _legacy_year_ids(iid)
    async for st in db.fee_structures.find({"institution_id": iid, "deleted": {"$ne": True}}, {"_id": 0}).sort("created_at", -1):
        if not _struct_in_scope(st, scope):
            continue
        st["unit_name"] = units.get(st.get("academic_unit_id"))
        st["archived"] = st.get("status") == "archived"
        if not st.get("academic_year_id"):
            st["academic_year_id"] = legacy.get(st.get("academic_year"))
        st["usage"] = await _structure_usage(st["id"])
        st["last_apply"] = await phase59.last_run(iid, "fee_apply", st["id"])
        st["account_count"] = await db.fee_accounts.count_documents({"structure_id": st["id"], "status": "active"})
        st["invoice_count"] = await db.fee_invoices.count_documents({"structure_id": st["id"]})
        rows.append(st)
    return {"structures": rows}


CLOSED_YEAR_STATES = ("closed", "archived")


async def _resolve_structure_year(iid, body, keep_year_id=None):
    """Phase 53: the structure's year must be one of this institution's academic years (stored by id)."""
    if body.academic_year_id:
        y = await db.academic_years.find_one({"id": body.academic_year_id, "institution_id": iid}, {"_id": 0, "id": 1, "name": 1, "status": 1})
        if not y:
            raise HTTPException(status_code=404, detail="Academic year not found in this institution")
    elif body.academic_year:
        ys = await db.academic_years.find({"institution_id": iid, "name": body.academic_year.strip()}, {"_id": 0, "id": 1, "name": 1, "status": 1}).to_list(3)
        if len(ys) != 1:
            raise HTTPException(status_code=400, detail="Pick one of your academic years")
        y = ys[0]
    else:
        raise HTTPException(status_code=400, detail="Pick an academic year")
    if y.get("status") in CLOSED_YEAR_STATES and y["id"] != keep_year_id:
        raise HTTPException(status_code=400, detail=f"Academic year {y['name']} is {y['status']} — pick a current or upcoming year")
    body.academic_year_id, body.academic_year = y["id"], y["name"]


async def _legacy_year_ids(iid):
    """Read-time mapping of legacy free-text years → id, only when the name matches exactly one year (no writes)."""
    by_name = {}
    async for y in db.academic_years.find({"institution_id": iid}, {"_id": 0, "id": 1, "name": 1}):
        by_name.setdefault(y["name"], []).append(y["id"])
    return {n: ids[0] for n, ids in by_name.items() if len(ids) == 1}


@api.post("/fees/structures")
async def create_fee_structure(body: FeeStructureIn, user: dict = Depends(require_fee_admin)):
    iid = user["institution_id"]
    await _resolve_structure_year(iid, body)
    heads = await _validate_structure(iid, body)
    doc = {**body.model_dump(), "heads": heads, "id": str(uuid.uuid4()), "institution_id": iid,
           "created_by": user.get("email"), "created_at": now_iso()}
    await db.fee_structures.insert_one(dict(doc))
    await audit(user, "fee_structure_create", "fee_structures", doc["id"], doc["name"], iid)
    doc.pop("_id", None)
    return doc


@api.put("/fees/structures/{sid}")
async def update_fee_structure(sid: str, body: FeeStructureIn, user: dict = Depends(require_fee_admin)):
    iid = user["institution_id"]
    cur = await _get_structure(iid, sid)
    if await db.fee_invoices.count_documents({"structure_id": sid}):
        raise HTTPException(status_code=409, detail="Invoices were already generated from this structure — clone it to make changes")
    keep = cur.get("academic_year_id") or (await _legacy_year_ids(iid)).get(cur.get("academic_year"))
    await _resolve_structure_year(iid, body, keep_year_id=keep)
    heads = await _validate_structure(iid, body)
    await db.fee_structures.update_one({"id": sid}, {"$set": {**body.model_dump(), "heads": heads, "updated_at": now_iso()}})
    await audit(user, "fee_structure_update", "fee_structures", sid, body.name, iid)
    return await _get_structure(iid, sid)


@api.post("/fees/structures/{sid}/clone")
async def clone_fee_structure(sid: str, user: dict = Depends(require_fee_admin)):
    iid = user["institution_id"]
    st = await _get_structure(iid, sid)
    for k in ("status", "archived_at", "archived_by", "archived_by_name", "unarchived_at", "updated_at"):
        st.pop(k, None)
    doc = {**st, "id": str(uuid.uuid4()), "name": f"{st['name']} (copy)", "cloned_from": sid,
           "heads": [{**h, "id": str(uuid.uuid4())} for h in st["heads"]],
           "created_by": user.get("email"), "created_at": now_iso()}
    await db.fee_structures.insert_one(dict(doc))
    await audit(user, "fee_structure_clone", "fee_structures", doc["id"], doc["name"], iid)
    return doc


async def _structure_usage(sid):
    acc_ids = await db.fee_accounts.distinct("id", {"structure_id": sid})
    inv_ids = await db.fee_invoices.distinct("id", {"structure_id": sid})
    students = await db.fee_accounts.distinct("student_id", {"structure_id": sid})
    payments = await db.fee_payments.count_documents(
        {"$or": [{"account_id": {"$in": acc_ids}}, {"invoice_id": {"$in": inv_ids}}, {"structure_id": sid}]})
    return {"students": len(students), "accounts": len(acc_ids), "invoices": len(inv_ids), "payments": payments,
            "used": bool(acc_ids or inv_ids or payments)}


def _usage_msg(u):
    return f"Used by {u['students']} student(s) / {u['invoices']} invoice(s) — archive instead"


def _require_not_archived(st, action):
    if st.get("status") == "archived":
        raise HTTPException(status_code=409, detail=f"“{st['name']}” is archived — unarchive it to {action}")


@api.delete("/fees/structures/{sid}")
async def delete_fee_structure(sid: str, user: dict = Depends(require_roles("institution_admin"))):
    """Soft delete — only when nothing references it. Mark first, re-check, roll back on a race."""
    iid = user["institution_id"]
    st = await _get_structure(iid, sid)
    u = await _structure_usage(sid)
    if u["used"]:
        raise HTTPException(status_code=409, detail=_usage_msg(u))
    r = await db.fee_structures.update_one({"id": sid, "institution_id": iid, "deleted": {"$ne": True}},
                                           {"$set": {"deleted": True, "deleted_by": user["id"], "deleted_by_name": user.get("name"),
                                                     "deleted_at": now_iso()}})
    if not r.modified_count:
        raise HTTPException(status_code=404, detail="Fee structure not found")
    u = await _structure_usage(sid)
    if u["used"]:
        await db.fee_structures.update_one({"id": sid}, {"$set": {"deleted": False}, "$unset": {"deleted_by": "", "deleted_by_name": "", "deleted_at": ""}})
        raise HTTPException(status_code=409, detail=_usage_msg(u))
    await audit(user, "fee_structure_delete", "fee_structures", sid, st["name"], iid)
    return {"ok": True}


@api.post("/fees/structures/{sid}/archive")
async def archive_fee_structure(sid: str, user: dict = Depends(require_roles("institution_admin"))):
    iid = user["institution_id"]
    st = await _get_structure(iid, sid)
    if st.get("status") == "archived":
        raise HTTPException(status_code=400, detail="Already archived")
    await db.fee_structures.update_one({"id": sid}, {"$set": {"status": "archived", "archived_at": now_iso(), "archived_by": user["id"],
                                                              "archived_by_name": user.get("name")}})
    await audit(user, "fee_structure_archive", "fee_structures", sid, st["name"], iid)
    return await _get_structure(iid, sid)


@api.post("/fees/structures/{sid}/unarchive")
async def unarchive_fee_structure(sid: str, user: dict = Depends(require_roles("institution_admin"))):
    iid = user["institution_id"]
    st = await _get_structure(iid, sid)
    if st.get("status") != "archived":
        raise HTTPException(status_code=400, detail="This structure isn't archived")
    await db.fee_structures.update_one({"id": sid}, {"$set": {"status": "active", "unarchived_at": now_iso()},
                                                      "$unset": {"archived_at": "", "archived_by": "", "archived_by_name": ""}})
    await audit(user, "fee_structure_unarchive", "fee_structures", sid, st["name"], iid)
    return await _get_structure(iid, sid)


@api.post("/fees/structures/{sid}/apply")
async def apply_fee_structure(sid: str, user: dict = Depends(require_fee_admin)):
    """Create a fee account for every enrolled student in the structure's unit/class (idempotent)."""
    iid = user["institution_id"]
    st = await _get_structure(iid, sid)
    _require_not_archived(st, "apply it to students")
    if not st.get("active"):
        raise HTTPException(status_code=400, detail="Activate the structure before applying it")
    names = await _struct_class_names(iid, st)
    optional_ids = [h["id"] for h in st["heads"] if h.get("optional")]
    created, skipped, items = 0, [], []
    B, yr = phase59, st["academic_year"]
    snames = {x["id"]: x["name"] async for x in db.fee_structures.find({"institution_id": iid}, {"_id": 0, "id": 1, "name": 1})}
    async for s in db.students.find({"institution_id": iid, "class_name": {"$in": names}}, {"_id": 0}).sort([("class_name", 1), ("first_name", 1)]):
        sname = f"{s.get('first_name', '')} {s.get('last_name', '')}".strip()
        sub = f"{s.get('admission_no') or '—'} · {s.get('class_name') or ''} {s.get('section') or ''}".strip()

        def skip(code, reason, fx):
            skipped.append({"student_name": sname, "reason": reason, "reason_code": code})
            items.append(B.item(s["id"], sname, "skipped", reason, code, sub, fx))
        if s.get("status") == "inactive":
            skip("inactive", "Student inactive", B.fix("open_student", s["id"]))
            continue
        if s.get("enrollment_status") != "enrolled":
            skip("not_enrolled", f"Not enrolled in a class covered by this structure (status: {(s.get('enrollment_status') or 'not enrolled').replace('_', ' ')})",
                 B.fix("enrol_student", s["id"]))
            continue
        mine = await db.fee_accounts.find_one({"structure_id": sid, "student_id": s["id"]}, {"_id": 0, "id": 1})
        if mine:
            skip("already_applied", f"Already has an account for {yr} under '{st['name']}'", B.fix("open_ledger", mine["id"]))
            continue
        other = await db.fee_accounts.find_one({"institution_id": iid, "student_id": s["id"], "academic_year": yr,
                                                "status": "active"}, {"_id": 0, "id": 1, "structure_id": 1})
        if other:
            skip("other_structure", f"Already has an account for {yr} under '{snames.get(other['structure_id'], 'another structure')}'",
                 B.fix("open_ledger", other["id"]))
            continue
        aid = str(uuid.uuid4())
        try:
            await db.fee_accounts.insert_one({
                "id": aid, "institution_id": iid, "student_id": s["id"], "student_name": sname,
                "admission_no": s.get("admission_no"), "class_name": s.get("class_name"), "section": s.get("section"),
                "academic_year": yr, "structure_id": sid, "included_head_ids": list(optional_ids),
                "discount": None, "discount_used": 0.0, "status": "active", "created_at": now_iso()})
            created += 1
            items.append(B.item(s["id"], sname, "created", "Fee account created", "created", sub, B.fix("open_ledger", aid)))
        except DuplicateKeyError:
            skip("already_applied", f"Already has an account for {yr} under '{st['name']}'", B.fix("open_student", s["id"]))
        except Exception as e:  # noqa: BLE001
            items.append(B.item(s["id"], sname, "failed", f"Could not create the account: {e}", "error", sub, B.fix("open_student", s["id"])))
    await audit(user, "fee_structure_apply", "fee_accounts", sid, f"{created} accounts · {len(skipped)} skipped · {st['name']}", iid)
    run = await B.save_run(user, "fee_apply", f"Apply '{st['name']}' to students", items, ref_id=sid)
    return {"created": created, "skipped": skipped, **run}


@api.post("/fees/structures/{sid}/generate")
async def generate_fee_invoices(sid: str, body: FeeGenerateIn, user: dict = Depends(require_fee_admin)):
    """One invoice per account per period for heads of the chosen frequency. Idempotent per period."""
    iid = user["institution_id"]
    st = await _get_structure(iid, sid)
    _require_not_archived(st, "generate new invoices")
    heads = [h for h in st["heads"] if h["frequency"] == body.frequency]
    if not heads:
        raise HTTPException(status_code=400, detail=f"This structure has no {body.frequency.replace('_', '-')} fee heads")
    if body.frequency in ("annual", "one_time") and len(body.periods) != 1:
        raise HTTPException(status_code=400, detail="Annual and one-time fees take exactly one period")
    labels = [p.label.strip() for p in body.periods]
    if len(set(labels)) != len(labels):
        raise HTTPException(status_code=400, detail="Period labels must be unique")
    for p in body.periods:
        try:
            datetime.strptime(p.due_date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid due date for {p.label}")
    q = {"structure_id": sid, "status": "active"}
    if body.class_name:
        q["class_name"] = body.class_name
    created, skipped, run_items = 0, 0, []
    async for acc in db.fee_accounts.find(q, {"_id": 0}):
        inc = set(acc.get("included_head_ids") or [])
        items = [{"head_id": h["id"], "title": h["title"], "amount": _r2(h["amount"])}
                 for h in heads if not h.get("optional") or h["id"] in inc]
        sub = f"{acc.get('admission_no') or '—'} · {acc.get('class_name') or ''} {acc.get('section') or ''}".strip()
        if not items:
            run_items.append(phase59.item(acc["id"], acc.get("student_name"), "skipped", f"No {body.frequency.replace('_', '-')} heads apply (optional heads not included)",
                                          "no_heads", sub, phase59.fix("open_ledger", acc["id"])))
            continue
        c0, s0 = created, skipped
        subtotal = _r2(sum(i["amount"] for i in items))
        for p in body.periods:
            key = {"account_id": acc["id"], "frequency": body.frequency, "period_label": p.label.strip()}
            if await db.fee_invoices.find_one(key):
                skipped += 1
                continue
            d, disc = acc.get("discount"), 0.0
            if d and d["type"] == "percent":
                disc = _r2(subtotal * min(d["value"], 100) / 100)
            elif d and d["type"] == "flat":
                disc = _r2(min(max(d["value"] - acc.get("discount_used", 0), 0), subtotal))
            total = _r2(subtotal - disc)
            try:
                await db.fee_invoices.insert_one({
                    **key, "id": str(uuid.uuid4()), "institution_id": iid, "structure_id": sid,
                    "student_id": acc["student_id"], "student_name": acc.get("student_name"),
                    "class_name": acc.get("class_name"), "section": acc.get("section"),
                    "academic_year": acc["academic_year"], "items": items, "subtotal": subtotal,
                    "discount_amount": disc, "fine_amount": 0.0, "fine_applied": False, "total": total,
                    "paid_amount": 0.0, "due_date": p.due_date, "status": "paid" if total == 0 else "pending",
                    "generated_at": now_iso(), "generated_by": user.get("email")})
            except DuplicateKeyError:
                skipped += 1
                continue
            if disc and d["type"] == "flat":
                acc["discount_used"] = _r2(acc.get("discount_used", 0) + disc)
                await db.fee_accounts.update_one({"id": acc["id"]}, {"$set": {"discount_used": acc["discount_used"]}})
            created += 1
        nc, ns = created - c0, skipped - s0
        run_items.append(phase59.item(acc["id"], acc.get("student_name"), "created" if nc else "skipped",
                                      f"{nc} invoice(s) created" + (f", {ns} period(s) already invoiced" if ns else "") if nc else "All selected periods already invoiced",
                                      "created" if nc else "already_invoiced", sub, phase59.fix("open_ledger", acc["id"])))
    await audit(user, "fee_invoices_generate", "fee_invoices", sid, f"{created} {body.frequency} invoices · {st['name']}", iid)
    run = await phase59.save_run(user, "fee_generate", f"Generate {body.frequency.replace('_', '-')} invoices · {st['name']}", run_items, ref_id=sid,
                                 extra={"invoices_created": created, "invoices_skipped": skipped})
    return {"created": created, "skipped_existing": skipped, **run}


async def _account_rows(iid, accounts):
    ids = [a["id"] for a in accounts]
    late = await _late_map({a["structure_id"] for a in accounts})
    by_acc = {}
    async for inv in db.fee_invoices.find({"account_id": {"$in": ids}}, {"_id": 0}):
        by_acc.setdefault(inv["account_id"], []).append(_invoice_view(inv, late.get(inv["structure_id"])))
    keymap = {(a["student_id"], a.get("academic_year")): a["id"] for a in accounts if a.get("status") == "active"}
    if keymap:  # Phase 50: arrears invoices attach to the student's account for that year
        async for inv in db.fee_invoices.find({"institution_id": iid, "is_arrears": True,
                                               "student_id": {"$in": list({k[0] for k in keymap})}}, {"_id": 0}):
            aid = keymap.get((inv["student_id"], inv.get("academic_year")))
            if aid:
                by_acc.setdefault(aid, []).append(_invoice_view(inv, None))
    return [{**a, "summary": _summarize(by_acc.get(a["id"], []))} for a in accounts]


@api.get("/fees/accounts")
async def list_fee_accounts(structure_id: str = "", class_name: str = "", q: str = "",
                            user: dict = Depends(require_admin_or_principal)):
    iid = user["institution_id"]
    scope = await _fee_scope(user)
    f = {"institution_id": iid}
    if structure_id:
        f["structure_id"] = structure_id
    if class_name:
        f["class_name"] = class_name
    if q.strip():
        rx = {"$regex": re.escape(q.strip()), "$options": "i"}
        f["$or"] = [{"student_name": rx}, {"admission_no": rx}]
    accs = await db.fee_accounts.find(f, {"_id": 0}).sort([("class_name", 1), ("student_name", 1)]).to_list(5000)
    if scope is not None:
        accs = [a for a in accs if a.get("class_name") in scope[0]]
    return {"accounts": await _account_rows(iid, accs)}


async def _get_account(iid, aid, user):
    acc = await db.fee_accounts.find_one({"id": aid, "institution_id": iid}, {"_id": 0})
    if not acc:
        raise HTTPException(status_code=404, detail="Fee account not found")
    scope = await _fee_scope(user)
    if scope is not None and acc.get("class_name") not in scope[0]:
        raise HTTPException(status_code=403, detail="Outside your assigned scope")
    return acc


@api.get("/fees/accounts/{aid}")
async def fee_account_ledger(aid: str, user: dict = Depends(require_admin_or_principal)):
    iid = user["institution_id"]
    acc = await _get_account(iid, aid, user)
    st = await _get_structure(iid, acc["structure_id"])
    arr = await db.fee_invoices.find({"institution_id": iid, "is_arrears": True, "student_id": acc["student_id"],
                                      "academic_year": acc["academic_year"]}, {"_id": 0}).to_list(50)
    invs = [_invoice_view(i, None) for i in arr] + \
        [_invoice_view(i, st.get("late_fee")) for i in await db.fee_invoices.find({"account_id": aid}, {"_id": 0}).sort("due_date", 1).to_list(500)]
    pays = await db.fee_payments.find({"$or": [{"account_id": aid}, {"invoice_id": {"$in": [a["id"] for a in arr]}}]},
                                      {"_id": 0}).sort("collected_at", 1).to_list(1000)
    return {"account": acc, "structure": st, "invoices": invs, "payments": pays, "summary": _summarize(invs)}


@api.put("/fees/accounts/{aid}")
async def update_fee_account(aid: str, body: FeeAccountPatch, user: dict = Depends(require_fee_admin)):
    """Optional-head toggles and discounts apply to invoices generated AFTER the change."""
    iid = user["institution_id"]
    acc = await _get_account(iid, aid, user)
    st = await _get_structure(iid, acc["structure_id"])
    upd = {}
    if body.included_head_ids is not None:
        optional = {h["id"] for h in st["heads"] if h.get("optional")}
        if set(body.included_head_ids) - optional:
            raise HTTPException(status_code=400, detail="Only optional fee heads can be toggled")
        upd["included_head_ids"] = list(body.included_head_ids)
    if body.clear_discount:
        upd["discount"] = None
    elif body.discount:
        if body.discount.type == "percent" and body.discount.value > 100:
            raise HTTPException(status_code=400, detail="Discount percent cannot exceed 100")
        upd["discount"] = {**body.discount.model_dump(), "value": _r2(body.discount.value),
                           "set_by": user.get("email"), "set_at": now_iso()}
    if upd:
        await db.fee_accounts.update_one({"id": aid}, {"$set": upd})
        await audit(user, "fee_account_update", "fee_accounts", aid,
                    f"{acc.get('student_name')} · {', '.join(upd)}", iid)
    return await db.fee_accounts.find_one({"id": aid}, {"_id": 0})


async def _receipt_prefix(iid):
    inst = await db.institutions.find_one({"id": iid}, {"_id": 0, "code": 1, "name": 1}) or {}
    p = re.sub(r"[^A-Z0-9]", "", (inst.get("code") or "").upper())
    return p or ("".join(w[0] for w in (inst.get("name") or "S").split())[:4].upper())


async def _next_receipt_no(iid, academic_year):
    m = re.search(r"\d{4}", academic_year or "")
    year = m.group() if m else now_iso()[:4]
    c = await db.fee_counters.find_one_and_update({"institution_id": iid, "year": year}, {"$inc": {"seq": 1}},
                                                  upsert=True, return_document=ReturnDocument.AFTER)
    return f"{await _receipt_prefix(iid)}-{year}-{c['seq']:06d}"


async def _refresh_invoice_status(inv_id, late):
    inv = await db.fee_invoices.find_one({"id": inv_id}, {"_id": 0})
    view = _invoice_view(inv, late)
    await db.fee_invoices.update_one({"id": inv_id}, {"$set": {"status": view["status"]}})
    return view


@api.post("/fees/payments")
async def record_fee_payment(body: FeePaymentIn, user: dict = Depends(require_admin_or_principal)):
    """Offline collection — admin, or a principal for students in their divisions (Phase 51)."""
    return await _create_fee_payment(user, body.invoice_id, body.amount, body.method, body.reference, body.note, body.paid_on)


async def _inst_tz(iid):
    from zoneinfo import ZoneInfo
    inst = await db.institutions.find_one({"id": iid}, {"_id": 0, "timezone": 1}) or {}
    try:
        return ZoneInfo(inst.get("timezone") or "Asia/Kolkata")
    except Exception:
        return ZoneInfo("Asia/Kolkata")


async def _require_collect_scope(user, class_name):
    if user.get("role") == "institution_admin":
        return
    if not await active_principal(user):
        raise HTTPException(status_code=403, detail="Only the school office or a principal can do this")
    sc = await _fee_scope(user)
    if sc is not None and class_name not in sc[0]:
        raise HTTPException(status_code=403, detail="This student is outside your divisions")


async def _validate_paid_on(iid, inv, paid_on):
    today = await _inst_today(iid)
    d = (paid_on or "").strip() or today
    try:
        datetime.strptime(d, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Payment date must be YYYY-MM-DD")
    if d > today:
        raise HTTPException(status_code=400, detail="Payment date cannot be in the future")
    ay = await db.academic_years.find_one({"institution_id": iid, "name": inv.get("academic_year")}, {"_id": 0, "start_date": 1})
    start = (ay or {}).get("start_date")
    if start and d < start and d != today:  # today is always allowed (advance payment for a year not yet started)
        raise HTTPException(status_code=400, detail=f"Payment date cannot be before the academic year start ({start})")
    return d, today


async def _create_fee_payment(user, invoice_id, amount, method, reference=None, note=None, paid_on=None, extra=None):
    """The ONE payment path (counter collection, approved UPI proofs, issue resolutions)."""
    iid = user["institution_id"]
    inv = await db.fee_invoices.find_one({"id": invoice_id, "institution_id": iid}, {"_id": 0})
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    await _require_collect_scope(user, inv.get("class_name"))
    if inv.get("carried_forward_to"):
        raise HTTPException(status_code=409, detail="This balance was carried forward to the next year — collect it against the 'Previous dues' invoice")
    paid_on, today = await _validate_paid_on(iid, inv, paid_on)
    late = None if inv.get("is_arrears") else (await _get_structure(iid, inv["structure_id"])).get("late_fee")
    fine = _fine_for(inv, late, _today())
    if fine > 0:  # late fine is fixed onto the invoice (once) when a payment is recorded after grace
        await db.fee_invoices.update_one({"id": inv["id"], "fine_applied": False},
                                         {"$set": {"fine_applied": True, "fine_applied_at": now_iso()}, "$inc": {"fine_amount": fine}})
        inv = await db.fee_invoices.find_one({"id": inv["id"]}, {"_id": 0})
    due = _r2(inv["total"] + inv.get("fine_amount", 0))
    amount = _r2(amount)
    balance = _r2(due - inv.get("paid_amount", 0))
    if balance <= 0:
        raise HTTPException(status_code=400, detail="This invoice is already fully paid")
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be more than zero")
    if amount > balance:
        raise HTTPException(status_code=400, detail=f"Amount exceeds the balance due (₹{balance:,.2f})")
    guard = await db.fee_invoices.find_one_and_update(
        {"id": inv["id"], "paid_amount": {"$lte": _r2(due - amount) + 0.001}}, {"$inc": {"paid_amount": amount}},
        return_document=ReturnDocument.AFTER)
    if not guard:
        raise HTTPException(status_code=409, detail="The invoice changed while recording — refresh and try again")
    now = now_iso()
    backdated = paid_on != today
    collected_at = now if not backdated else \
        datetime.strptime(paid_on + " 12:00", "%Y-%m-%d %H:%M").replace(tzinfo=await _inst_tz(iid)).astimezone(timezone.utc).isoformat()
    pay = {"id": str(uuid.uuid4()), "institution_id": iid, "invoice_id": inv["id"], "account_id": inv["account_id"],
           "student_id": inv["student_id"], "student_name": inv.get("student_name"), "class_name": inv.get("class_name"),
           "section": inv.get("section"), "period_label": inv.get("period_label"), "academic_year": inv.get("academic_year"),
           "items": inv.get("items"), "amount": amount, "method": method, "reference": reference, "note": note,
           "receipt_no": await _next_receipt_no(iid, inv.get("academic_year")),
           "collected_by": user.get("name") or user.get("email"), "collected_by_email": user.get("email"),
           "collected_by_role": "principal" if user.get("role") != "institution_admin" else "admin",
           "collected_at": collected_at, "paid_on": paid_on, "recorded_at": now, "backdated": backdated,
           "reversed": False, **(extra or {})}
    await db.fee_payments.insert_one(dict(pay))
    view = await _refresh_invoice_status(inv["id"], late)
    await audit(user, "fee_payment", "fee_payments", pay["id"],
                f"{pay['receipt_no']} · ₹{amount:,.2f} {method} · {pay['student_name']}"
                + (f" · BACKDATED payment date {paid_on}, recorded {now[:10]}" if backdated else ""), iid)
    pay.pop("_id", None)
    return {"payment": pay, "invoice": view}


@api.post("/fees/payments/{pid}/reverse")
async def reverse_fee_payment(pid: str, body: FeeReverseIn, user: dict = Depends(require_admin_or_principal)):
    """Credit-note style reversal: the payment is flagged (never deleted) and the invoice balance restored."""
    iid = user["institution_id"]
    p = await db.fee_payments.find_one({"id": pid, "institution_id": iid}, {"_id": 0})
    if not p:
        raise HTTPException(status_code=404, detail="Payment not found")
    await _require_collect_scope(user, p.get("class_name"))
    res = await db.fee_payments.update_one({"id": pid, "reversed": False}, {"$set": {
        "reversed": True, "reversed_by": user.get("email"), "reversed_at": now_iso(),
        "reverse_reason": body.reason.strip(), "credit_note_no": f"CN-{p['receipt_no']}"}})
    if not res.modified_count:
        raise HTTPException(status_code=400, detail="This payment was already reversed")
    await db.fee_invoices.update_one({"id": p["invoice_id"]}, {"$inc": {"paid_amount": -p["amount"]}})
    inv = await db.fee_invoices.find_one({"id": p["invoice_id"]}, {"_id": 0, "structure_id": 1})
    late = (await _late_map({inv["structure_id"]})).get(inv["structure_id"])
    view = await _refresh_invoice_status(p["invoice_id"], late)
    await audit(user, "fee_payment_reverse", "fee_payments", pid,
                f"{p['receipt_no']} · ₹{p['amount']:,.2f} · {body.reason.strip()}", iid)
    return {"payment": await db.fee_payments.find_one({"id": pid}, {"_id": 0}), "invoice": view}


@api.get("/fees/payments")
async def list_fee_payments(q: str = "", user: dict = Depends(require_admin_or_principal)):
    iid = user["institution_id"]
    scope = await _fee_scope(user)
    f = {"institution_id": iid}
    if q.strip():
        rx = {"$regex": re.escape(q.strip()), "$options": "i"}
        f["$or"] = [{"receipt_no": rx}, {"student_name": rx}, {"reference": rx}]
    if scope is not None:
        f["class_name"] = {"$in": list(scope[0])}
    rows = await db.fee_payments.find(f, {"_id": 0}).sort("collected_at", -1).to_list(300)
    return {"payments": rows}


async def _receipt_payload(pid: str, user: dict):
    """Receipt data with ownership rules: parent → own children, student → self, admin, in-scope principal."""
    p = await db.fee_payments.find_one({"id": pid, "institution_id": user.get("institution_id")}, {"_id": 0})
    if not p:
        raise HTTPException(status_code=404, detail="Receipt not found")
    role = user.get("role")
    if role == "parent":
        ok = p["student_id"] in (user.get("student_ids") or [])
    elif role == "student":
        ok = p["student_id"] == user.get("student_id")
    elif role == "institution_admin":
        ok = True
    else:
        scope = await _fee_scope(user) if await active_principal(user) else False
        ok = scope is None or (scope and p.get("class_name") in scope[0])
    if not ok:
        raise HTTPException(status_code=403, detail="Access denied")
    iid = p["institution_id"]
    inst = await db.institutions.find_one({"id": iid}, {"_id": 0, "name": 1, "address": 1, "phone": 1, "email": 1}) or {}
    inv = await db.fee_invoices.find_one({"id": p["invoice_id"]}, {"_id": 0})
    late = (await _late_map({inv["structure_id"]})).get(inv["structure_id"])
    stu = await db.students.find_one({"id": p["student_id"]}, {"_id": 0, "admission_no": 1})
    return {"payment": p, "invoice": _invoice_view(inv, late), "admission_no": (stu or {}).get("admission_no"),
            "school": {**inst, "logo_src": await _school_logo_src(iid)}}


@api.get("/fees/payments/{pid}/receipt")
async def fee_receipt(pid: str, user: dict = Depends(get_current_user)):
    return await _receipt_payload(pid, user)


_ONES = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten", "Eleven", "Twelve",
         "Thirteen", "Fourteen", "Fifteen", "Sixteen", "Seventeen", "Eighteen", "Nineteen"]
_TENS = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]


def _words_99(n):
    return _ONES[n] if n < 20 else (_TENS[n // 10] + (f" {_ONES[n % 10]}" if n % 10 else ""))


def _words_999(n):
    h, r = divmod(n, 100)
    return " ".join(x for x in [f"{_ONES[h]} Hundred" if h else "", _words_99(r) if r else ""] if x)


def _amount_in_words(amount):
    """Indian numbering (crore/lakh/thousand) — e.g. 5000 → 'Rupees Five Thousand Only'."""
    rupees, paise = divmod(int(round(float(amount) * 100)), 100)
    if rupees == 0 and paise == 0:
        return "Rupees Zero Only"
    parts, n = [], rupees
    for div, label in ((10_000_000, "Crore"), (100_000, "Lakh"), (1000, "Thousand")):
        q, n = divmod(n, div)
        if q:
            parts.append(f"{_words_999(q) if q < 1000 else _amount_in_words(q).replace('Rupees ', '').replace(' Only', '')} {label}")
    if n:
        parts.append(_words_999(n))
    out = "Rupees " + (" ".join(parts) if parts else "Zero")
    if paise:
        out += f" and {_words_99(paise)} Paise"
    return out + " Only"


_FEE_FONT_DIR = ROOT_DIR / "assets" / "fonts"


def _inr(n):
    """₹ + Indian digit grouping, always 2 decimals — e.g. 123456 → '₹1,23,456.00' (same format as the print views)."""
    v = round(float(n or 0), 2)
    whole, dec = f"{abs(v):.2f}".split(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        head = ",".join([head[max(0, i - 2):i] for i in range(len(head), 0, -2)][::-1])
        whole = f"{head},{tail}"
    return f"{'−' if v < 0 else ''}₹{whole}.{dec}"


def _receipt_fonts():
    """FreeSans (bundled, has the ₹ glyph, tabular digits) → fallback Helvetica with 'Rs.'."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    try:
        for name, f in (("FeeSans", "FreeSans.ttf"), ("FeeSans-Bold", "FreeSansBold.ttf"), ("FeeSans-Oblique", "FreeSansOblique.ttf")):
            if name not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont(name, str(_FEE_FONT_DIR / f)))
        return "FeeSans", "FeeSans-Bold", "FeeSans-Oblique", _inr
    except Exception:
        return "Helvetica", "Helvetica-Bold", "Helvetica-Oblique", lambda n: _inr(n).replace("₹", "Rs. ").replace("−", "-")


def _receipt_pdf(d, logo_bytes=None) -> bytes:
    from reportlab.lib.pagesizes import A5, landscape
    from reportlab.lib.units import mm
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas
    import io
    R, B, I, money = _receipt_fonts()
    SZ = 9  # one size for every amount row (totals only switch to bold)
    p, inv, school = d["payment"], d["invoice"], d["school"]
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=landscape(A5))
    w, h = landscape(A5)
    x0, y = 14 * mm, h - 16 * mm
    if logo_bytes:
        try:
            c.drawImage(ImageReader(io.BytesIO(logo_bytes)), x0, y - 10 * mm, 16 * mm, 16 * mm, preserveAspectRatio=True, mask="auto")
        except Exception:
            pass
    tx = x0 + (19 * mm if logo_bytes else 0)
    c.setFont(B, 14); c.drawString(tx, y, (school.get("name") or "").strip()[:60])
    c.setFont(R, 8.5); c.drawString(tx, y - 5 * mm, (school.get("address") or "")[:90])
    c.setFont(B, 12); c.drawRightString(w - x0, y, "FEE RECEIPT")
    c.setFont(R, SZ); c.drawRightString(w - x0, y - 5 * mm, f"No. {p['receipt_no']}")
    c.drawRightString(w - x0, y - 9.5 * mm, f"Date: {p.get('paid_on') or (p.get('collected_at') or '')[:10]}")
    y -= 14 * mm; c.line(x0, y, w - x0, y); y -= 7 * mm
    c.setFont(R, SZ)
    cls = f"{p.get('class_name') or ''} {p.get('section') or ''}".strip()
    c.drawString(x0, y, f"Student: {p.get('student_name')}"); c.drawString(w / 2, y, f"Admission no.: {d.get('admission_no') or '-'}"); y -= 5.5 * mm
    c.drawString(x0, y, f"Class: {cls}"); c.drawString(w / 2, y, f"Period: {p.get('period_label')} ({p.get('academic_year') or ''})"); y -= 8 * mm
    c.setFont(B, SZ); c.drawString(x0, y, "Fee head"); c.drawRightString(w - x0, y, "Amount"); y -= 2 * mm
    c.line(x0, y, w - x0, y); y -= 5 * mm

    def row(label, amount, bold=False):
        nonlocal y
        c.setFont(B if bold else R, SZ)
        c.drawString(x0, y, str(label)[:70]); c.drawRightString(w - x0, y, money(amount)); y -= 5 * mm
    for i in inv.get("items") or []:
        row(i["title"], i["amount"])
    if inv.get("discount_amount"):
        row("Concession / discount", -inv["discount_amount"])
    if inv.get("fine_amount"):
        row("Late fee", inv["fine_amount"])
    c.line(x0, y + 2 * mm, w - x0, y + 2 * mm); y -= 1 * mm
    row("Invoice total", inv["amount_due"], bold=True)
    row(f"Amount received ({p['method'].upper()}{' · ' + p['reference'] if p.get('reference') else ''})", p["amount"], bold=True)
    row("Balance remaining on this invoice", inv["balance"])
    c.setFont(I, SZ); c.drawString(x0, y, f"Received: {_amount_in_words(p['amount'])}"); y -= 5.5 * mm
    if p.get("reversed"):
        c.setFillColorRGB(0.75, 0.1, 0.1); c.setFont(R, SZ)
        c.drawString(x0, y, f"REVERSED {(p.get('reversed_at') or '')[:10]} · credit note {p.get('credit_note_no')} · {p.get('reverse_reason') or ''}"[:110])
        c.setFillColorRGB(0, 0, 0)
    c.line(x0, 18 * mm, x0 + 55 * mm, 18 * mm); c.line(w - x0 - 55 * mm, 18 * mm, w - x0, 18 * mm)
    c.setFont(R, 8.5)
    c.drawString(x0, 14 * mm, f"Collected by: {p.get('collected_by') or ''}"[:50])
    c.drawRightString(w - x0, 14 * mm, "Authorised signatory")
    c.setFont(R, 7); c.drawString(x0, 8 * mm, "System-generated receipt.")
    c.showPage(); c.save()
    return buf.getvalue()


@api.get("/fees/payments/{pid}/receipt.pdf")
async def fee_receipt_pdf(pid: str, user: dict = Depends(get_current_user)):
    d = await _receipt_payload(pid, user)
    inst = await db.institutions.find_one({"id": d["payment"]["institution_id"]}, {"_id": 0, "logo_path": 1})
    logo = None
    if (inst or {}).get("logo_path"):
        try:
            logo, _ = _get_object(inst["logo_path"])
        except Exception:
            logo = None
    pdf = _receipt_pdf(d, logo)
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="receipt-{d["payment"]["receipt_no"]}.pdf"'})


# ---- Phase 49: fee reminders (auto cadence + manual) ----
FEE_REMINDER_DEFAULTS = {"enabled": True, "before_days": 3, "overdue_after_days": 1, "repeat_every_days": 7, "channel": "whatsapp"}


class FeeReminderSettingsIn(_BM):
    enabled: bool = True
    before_days: int = _F(default=3, ge=0, le=30)
    overdue_after_days: int = _F(default=1, ge=0, le=30)
    repeat_every_days: int = _F(default=7, ge=1, le=60)
    channel: Literal["whatsapp", "sms"] = "whatsapp"


def _fee_reminder_type(due_date, today, cfg):
    """before_due on due−before_days; overdue on due+overdue_after_days; overdue_repeat every repeat_every_days after."""
    d = (datetime.strptime(due_date, "%Y-%m-%d").date() - datetime.strptime(today, "%Y-%m-%d").date()).days
    if d == cfg["before_days"] and d > 0:
        return "before_due"
    late = -d
    first = cfg["overdue_after_days"]
    if late == first:
        return "overdue"
    if late > first and (late - first) % cfg["repeat_every_days"] == 0:
        return "overdue_repeat"
    return None


async def _fee_reminder_cfg(iid):
    inst = await db.institutions.find_one({"id": iid}, {"_id": 0, "fee_reminders": 1}) or {}
    return {**FEE_REMINDER_DEFAULTS, **(inst.get("fee_reminders") or {})}


async def _send_fee_reminder(inv, rtype, source, today, cfg, actor=None):
    """One reminder per invoice per day from ANY source (reminders_sent key). Bell to linked parents always;
    WhatsApp/SMS to the guardian phone via the comm engine; channel failure → bell only."""
    iid = inv["institution_id"]
    late = (await _late_map({inv["structure_id"]})).get(inv["structure_id"])
    view = _invoice_view(inv, late, today)
    if view["balance"] <= 0:
        return {"invoice_id": inv["id"], "status": "paid"}
    key = f"fee:stu:{inv['student_id']}:{today}"  # Phase 50: max 1 fee reminder per student per day, any source
    r = await db.reminders_sent.update_one({"key": key}, {"$setOnInsert": {"key": key, "institution_id": iid, "type": rtype,
                                                                            "source": source, "sent_at": now_iso()}}, upsert=True)
    if r.matched_count:
        return {"invoice_id": inv["id"], "student_name": inv.get("student_name"), "status": "deduped"}
    stu = await db.students.find_one({"id": inv["student_id"]}, {"_id": 0}) or {}
    parents = await db.users.find({"institution_id": iid, "role": "parent", "student_ids": inv["student_id"]},
                                  {"_id": 0, "id": 1, "phone": 1, "name": 1}).to_list(10)
    sname = inv.get("student_name") or f"{stu.get('first_name', '')} {stu.get('last_name', '')}".strip()
    amount = f"Rs. {view['balance']:,.2f}"
    title = ("Fee overdue: " if view["status"] == "overdue" else "Fee due: ") + f"{sname} · {inv['period_label']}"
    body = f"{amount} due on {inv['due_date']}"
    for p in parents:
        await _notify(iid, p["id"], "fee_reminder", title, body, inv["id"])
    phone = _norm_phone(stu.get("guardian_phone")) or next((p["phone"] for p in parents if p.get("phone")), None)
    status = "bell_only_no_phone"
    if phone:
        school = await db.institutions.find_one({"id": iid}, {"_id": 0, "name": 1})
        tpl = await db.comm_templates.find_one({"institution_id": None, "name": "Fee Reminder"}, {"_id": 0})
        token = _make_secure_link(iid, "feeinv:" + inv["id"], 24 * 14)
        link = f"{os.environ['PUBLIC_BASE_URL']}/fees/invoice/{token}"
        vals = {"school_name": (school or {}).get("name") or "", "student_name": sname,
                "parent_name": stu.get("guardian_name") or "Parent", "amount": amount, "due_date": inv["due_date"], "secure_link": link}
        text = _render_template(tpl["body"] if tpl else "Dear {{parent_name}}, {{amount}} is due for {{student_name}} on {{due_date}}: {{secure_link}} — {{school_name}}", vals)
        try:
            res = await send_message(iid, cfg["channel"], [{"name": vals["parent_name"], "phone": phone, "student_id": inv["student_id"],
                                                            "body": text, "vars": vals}],
                                     template_id=(tpl or {}).get("id"), module="fee_reminder", actor=actor)
            status = "sent" if res.get("sent") else "bell_only_failed"
        except HTTPException:
            status = "bell_only_failed"
    await db.fee_reminders.insert_one({"id": str(uuid.uuid4()), "institution_id": iid, "invoice_id": inv["id"],
                                       "student_id": inv["student_id"], "type": rtype, "source": source, "channel": cfg["channel"],
                                       "phone": phone, "status": status, "bells": len(parents), "date": today, "at": now_iso()})
    return {"invoice_id": inv["id"], "student_name": sname, "status": status, "type": rtype}


async def _inst_today(iid):
    """Calendar date in the institution's timezone (fallback Asia/Kolkata) — the fee-reminder day boundary."""
    return datetime.now(await _inst_tz(iid)).date().isoformat()


async def _fee_reminder_sweep(today=None, only_iid=None):
    out, cfgs, days = [], {}, {}
    q = {"status": {"$in": ["pending", "partial", "overdue"]}}
    if only_iid:
        q["institution_id"] = only_iid
    async for inv in db.fee_invoices.find(q, {"_id": 0}):
        iid = inv["institution_id"]
        if iid not in cfgs:
            cfgs[iid] = await _fee_reminder_cfg(iid)
            days[iid] = today or await _inst_today(iid)
        cfg, day = cfgs[iid], days[iid]
        if not cfg["enabled"] or not inv.get("due_date"):
            continue
        rtype = _fee_reminder_type(inv["due_date"], day, cfg)
        if rtype:
            out.append(await _send_fee_reminder(inv, rtype, "auto", day, cfg))
    return out


async def _fee_reminder_loop():
    while True:
        try:
            await _fee_reminder_sweep()
        except Exception:
            logger.exception("fee-reminder sweep failed")
        await asyncio.sleep(3600)


@api.get("/fees/reminder-settings")
async def get_fee_reminder_settings(user: dict = Depends(require_admin_or_principal)):
    return await _fee_reminder_cfg(user["institution_id"])


@api.put("/fees/reminder-settings")
async def put_fee_reminder_settings(body: FeeReminderSettingsIn, user: dict = Depends(require_fee_admin)):
    await db.institutions.update_one({"id": user["institution_id"]}, {"$set": {"fee_reminders": body.model_dump()}})
    await audit(user, "fee_reminder_settings", "institutions", user["institution_id"], str(body.model_dump()), user["institution_id"])
    return body.model_dump()


@api.post("/fees/reminders/run")
async def run_fee_reminders(payload: dict = Body(default={}), user: dict = Depends(require_fee_admin)):
    """Run the auto-reminder rules now for this school (optionally 'as_of' a date, for checks/testing)."""
    as_of = (payload or {}).get("as_of") or await _inst_today(user["institution_id"])
    try:
        datetime.strptime(as_of, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="as_of must be YYYY-MM-DD")
    res = await _fee_reminder_sweep(as_of, user["institution_id"])
    await audit(user, "fee_reminders_run", "fee_reminders", None, f"{as_of}: {len(res)} due", user["institution_id"])
    run = await phase59.save_run(user, "fee_reminders_run", f"Fee reminders run · {as_of}", await phase59.reminder_items(res))
    return {"as_of": as_of, "results": res, "sent": sum(1 for r in res if r["status"] == "sent"), **run}


@api.post("/fees/invoices/{inv_id}/remind")
async def remind_fee_invoice(inv_id: str, user: dict = Depends(require_fee_admin)):
    iid = user["institution_id"]
    inv = await db.fee_invoices.find_one({"id": inv_id, "institution_id": iid}, {"_id": 0})
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    res = await _send_fee_reminder(inv, "manual", "manual", await _inst_today(iid), await _fee_reminder_cfg(iid), actor=user)
    if res["status"] == "paid":
        raise HTTPException(status_code=400, detail="This invoice is already fully paid")
    await audit(user, "fee_remind", "fee_invoices", inv_id, f"{inv.get('student_name')} · {inv['period_label']} · {res['status']}", iid)
    return res


@api.post("/fees/reminders/class")
async def remind_fee_class(payload: dict = Body(...), user: dict = Depends(require_fee_admin)):
    """Remind every student in a class who owes money — one reminder each, for their earliest open invoice."""
    iid = user["institution_id"]
    cn = (payload.get("class_name") or "").strip()
    if not cn:
        raise HTTPException(status_code=400, detail="class_name is required")
    today, cfg = await _inst_today(iid), await _fee_reminder_cfg(iid)
    invs = await db.fee_invoices.find({"institution_id": iid, "class_name": cn, "status": {"$in": ["pending", "partial", "overdue"]}},
                                      {"_id": 0}).sort("due_date", 1).to_list(5000)
    seen, results = set(), []
    for inv in invs:
        if inv["student_id"] in seen:
            continue
        r = await _send_fee_reminder(inv, "manual", "manual", today, cfg, actor=user)
        if r["status"] != "paid":
            seen.add(inv["student_id"])
            results.append(r)
    summary = {k: sum(1 for r in results if r["status"] == k) for k in ("sent", "deduped", "bell_only_no_phone", "bell_only_failed")}
    await audit(user, "fee_remind_class", "fee_invoices", None, f"{cn}: {summary}", iid)
    run = await phase59.save_run(user, "fee_remind_class", f"Fee reminders · {cn}", await phase59.reminder_items(results), ref_id=cn)
    return {"class_name": cn, "results": results, **summary, "run_id": run["run_id"], "items": run["items"], "run_summary": run["summary"]}


@api.get("/public/fee-link/{token}")
async def public_fee_link(token: str):
    """Resolve a reminder link → which child/invoice to open. No money data; the portal requires parent sign-in."""
    data = _verify_secure_link(token)
    if not data or not str(data.get("ref", "")).startswith("feeinv:"):
        raise HTTPException(status_code=400, detail="This link is invalid or has expired")
    inv = await db.fee_invoices.find_one({"id": data["ref"].split(":", 1)[1]}, {"_id": 0, "id": 1, "student_id": 1})
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return {"student_id": inv["student_id"], "invoice_id": inv["id"]}


# ---- Phase 49: day book ----
@api.get("/fees/day-book")
async def fee_day_book(date: str = "", user: dict = Depends(require_admin_or_principal)):
    iid = user["institution_id"]
    day = date or await _inst_today(iid)
    try:
        datetime.strptime(day, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD")
    f = {"institution_id": iid, "paid_on": day}  # Phase 51: payment date in the institution timezone
    scope = await _fee_scope(user)
    if scope is not None:
        f["class_name"] = {"$in": list(scope[0])}
    rows = await db.fee_payments.find(f, {"_id": 0, "items": 0}).sort("collected_at", 1).to_list(5000)
    tz = await _inst_tz(iid)
    for p in rows:
        p["time_local"] = None if p.get("backdated") else datetime.fromisoformat(p["collected_at"]).astimezone(tz).strftime("%H:%M")
    live = [p for p in rows if not p.get("reversed")]
    rev = [p for p in rows if p.get("reversed")]

    def group(key):
        g = {}
        for p in live:
            k = p.get(key) or "—"
            e = g.setdefault(k, {"key": k, "total": 0.0, "count": 0})
            e["total"] = _r2(e["total"] + p["amount"]); e["count"] += 1
        return sorted(g.values(), key=lambda e: -e["total"])
    by_class = group("class_name")
    by_class.sort(key=lambda e: (int(re.search(r"\d+", e["key"]).group()) if re.search(r"\d+", e["key"]) else 999, e["key"]))
    school = await db.institutions.find_one({"id": iid}, {"_id": 0, "name": 1})
    return {"date": day, "timezone": str(tz), "school": {"name": (school or {}).get("name"), "logo_src": await _school_logo_src(iid)},
            "summary": {"total": _r2(sum(p["amount"] for p in live)), "count": len(live),
                        "reversed_count": len(rev), "reversed_amount": _r2(sum(p["amount"] for p in rev))},
            "by_method": group("method"), "by_collector": group("collected_by"), "by_class": by_class,
            "payments": live, "reversed": rev}


async def _student_fees(iid, sid):
    invs = await db.fee_invoices.find({"institution_id": iid, "student_id": sid}, {"_id": 0}).sort("due_date", 1).to_list(500)
    late = await _late_map({i["structure_id"] for i in invs if i.get("structure_id")})
    views = [_invoice_view(i, late.get(i.get("structure_id"))) for i in invs]
    pays = await db.fee_payments.find({"institution_id": iid, "student_id": sid, "reversed": False},
                                      {"_id": 0, "id": 1, "receipt_no": 1, "amount": 1, "method": 1, "period_label": 1,
                                       "collected_at": 1, "paid_on": 1}).sort("collected_at", -1).to_list(500)
    upi = await _upi_cfg(iid)
    stu = await db.students.find_one({"id": sid}, {"_id": 0, "admission_no": 1}) or {}
    for v in views:  # Phase 51: QR always encodes the CURRENT balance
        v["upi"] = _upi_block(upi, v, stu.get("admission_no"))
    proofs = await db.fee_payment_proofs.find({"institution_id": iid, "student_id": sid}, {"_id": 0}).sort("submitted_at", -1).to_list(200)
    issues = await db.fee_issues.find({"institution_id": iid, "student_id": sid}, {"_id": 0}).sort("updated_at", -1).to_list(100)
    return {"summary": _summarize(views), "invoices": views, "payments": pays, "proofs": proofs, "issues": issues,
            "upi_enabled": bool(upi.get("enabled"))}


@api.get("/parent/child/{student_id}/fees")
async def parent_child_fees(student_id: str, user: dict = Depends(require_roles("parent"))):
    if student_id not in (user.get("student_ids") or []):
        raise HTTPException(status_code=403, detail="This student is not linked to your account")
    return await _student_fees(user["institution_id"], student_id)


@api.get("/portal/fees")
async def portal_fees(user: dict = Depends(require_roles("student"))):
    if not user.get("student_id"):
        raise HTTPException(status_code=404, detail="No student profile linked to this account")
    return await _student_fees(user["institution_id"], user["student_id"])


# ==================== PHASE 50: FEES PART C (defaulters, dues carry-forward, monthly summary) ====================
# Money rules: balances always come from _invoice_view (concessions already net out of `total`, late fine
# projected, carried-forward invoices = 0) so every figure reconciles with the student account ledger.
import csv as _csv  # noqa: E402
import io as _io  # noqa: E402

AGE_BUCKETS = {"1-30": (1, 30), "31-60": (31, 60), "60+": (61, 10 ** 6)}


async def _fee_view_scope(user):
    """('admin', None) | ('principal', class_names|None=whole school) | ('teacher', {(class, section)}) — else 403."""
    if user.get("role") == "institution_admin" and user.get("institution_id"):
        return "admin", None
    if await active_principal(user):
        sc = await _fee_scope(user)
        return "principal", (None if sc is None else sc[0])
    if user.get("role") == "teacher" and user.get("institution_id") and user.get("status") != "inactive":
        homes = await db.sections.find({"institution_id": user["institution_id"], "class_teacher_id": user["id"]},
                                       {"_id": 0, "class_name": 1, "name": 1}).to_list(100)
        if homes:
            return "teacher", {(h["class_name"], h["name"]) for h in homes}
    raise HTTPException(status_code=403, detail="Access denied")


def _stu_in_scope(kind, scope, s):
    if scope is None:
        return True
    if kind == "principal":
        return s.get("class_name") in scope
    return (s.get("class_name"), s.get("section")) in scope


async def _open_views_by_student(iid, student_ids, today=None):
    today = today or _today()
    invs = await db.fee_invoices.find({"institution_id": iid, "student_id": {"$in": list(student_ids)},
                                       "status": {"$ne": "paid"}}, {"_id": 0}).sort("due_date", 1).to_list(100000)
    late = await _late_map({i["structure_id"] for i in invs if i.get("structure_id")})
    out = {}
    for i in invs:
        v = _invoice_view(i, late.get(i.get("structure_id")), today)
        if v["balance"] > 0:
            out.setdefault(i["student_id"], []).append(v)
    return out


async def _promo_dues(iid, decisions):
    views = await _open_views_by_student(iid, {d["student_id"] for d in decisions if d.get("student_id")})
    dues = {sid: _r2(sum(v["balance"] for v in vs)) for sid, vs in views.items()}
    return {"dues": dues, "dues_summary": {"students": len(dues), "total": _r2(sum(dues.values()))}}


async def _defaulter_rows(user, academic_unit_id="", class_name="", section="", today=None):
    kind, scope = await _fee_view_scope(user)
    iid = user["institution_id"]
    today = today or await _inst_today(iid)
    owing = await db.fee_invoices.distinct("student_id", {"institution_id": iid, "status": {"$ne": "paid"}})
    sq = {"institution_id": iid, "id": {"$in": owing}}
    names = None
    if academic_unit_id:
        names = {c["name"] for c in await db.classes.find({"institution_id": iid, "academic_unit_id": academic_unit_id},
                                                          {"_id": 0, "name": 1}).to_list(500)}
    if class_name:
        names = {class_name} if names is None else names & {class_name}
    if names is not None:
        sq["class_name"] = {"$in": list(names)}
    if section:
        sq["section"] = section
    studs = {s["id"]: s for s in await db.students.find(sq, {"_id": 0, "id": 1, "first_name": 1, "last_name": 1, "admission_no": 1,
                                                             "class_name": 1, "section": 1, "guardian_name": 1, "guardian_phone": 1,
                                                             "enrollment_status": 1}).to_list(50000) if _stu_in_scope(kind, scope, s)}
    views = await _open_views_by_student(iid, studs.keys(), today)
    parents = {}
    async for p in db.users.find({"institution_id": iid, "role": "parent", "student_ids": {"$in": list(views)}},
                                 {"_id": 0, "name": 1, "phone": 1, "student_ids": 1}):
        for sid in p.get("student_ids") or []:
            parents.setdefault(sid, p)
    last = {r["_id"]: r async for r in db.fee_reminders.aggregate([
        {"$match": {"institution_id": iid, "student_id": {"$in": list(views)}}}, {"$sort": {"at": -1}},
        {"$group": {"_id": "$student_id", "at": {"$first": "$at"}, "status": {"$first": "$status"}}}])}
    tday = datetime.strptime(today, "%Y-%m-%d").date()
    rows = []
    for sid, vs in views.items():
        od = [v for v in vs if v.get("due_date") and v["due_date"] < today]
        if not od:
            continue
        s, p = studs[sid], parents.get(sid) or {}
        oldest = min(v["due_date"] for v in od)
        days = (tday - datetime.strptime(oldest, "%Y-%m-%d").date()).days
        rows.append({
            "student_id": sid, "student_name": f"{s.get('first_name', '')} {s.get('last_name', '')}".strip(),
            "admission_no": s.get("admission_no"), "class_name": s.get("class_name"), "section": s.get("section"),
            "enrollment_status": s.get("enrollment_status"),
            "parent_name": s.get("guardian_name") or p.get("name"),
            "parent_phone": _norm_phone(s.get("guardian_phone")) or p.get("phone"),
            "overdue_amount": _r2(sum(v["balance"] for v in od)), "total_outstanding": _r2(sum(v["balance"] for v in vs)),
            "overdue_invoices": len(od), "oldest_due_date": oldest, "days_late": days,
            "bucket": next(k for k, (lo, hi) in AGE_BUCKETS.items() if lo <= days <= hi),
            "last_reminder_at": (last.get(sid) or {}).get("at"), "last_reminder_status": (last.get(sid) or {}).get("status")})
    upcoming = [v for vs in views.values() for v in vs if not v.get("due_date") or v["due_date"] >= today]
    open_info = {"as_of": today, "not_yet_due_invoices": len(upcoming),
                 "not_yet_due_amount": _r2(sum(v["balance"] for v in upcoming)),
                 "next_due_date": min((v["due_date"] for v in upcoming if v.get("due_date")), default=None)}
    return kind, scope, rows, open_info


def _defaulter_filter(rows, bucket, min_amount, sort):
    if bucket and bucket not in AGE_BUCKETS:
        raise HTTPException(status_code=400, detail="bucket must be one of 1-30, 31-60, 60+")
    if sort not in ("amount", "days_late"):
        raise HTTPException(status_code=400, detail="sort must be 'amount' or 'days_late'")
    rows = [r for r in rows if r["overdue_amount"] >= (min_amount or 0)]
    buckets = {k: sum(1 for r in rows if r["bucket"] == k) for k in AGE_BUCKETS}
    if bucket:
        rows = [r for r in rows if r["bucket"] == bucket]
    key = (lambda r: (-r["days_late"], -r["overdue_amount"], r["student_name"])) if sort == "days_late" \
        else (lambda r: (-r["overdue_amount"], -r["days_late"], r["student_name"]))
    return sorted(rows, key=key), buckets


async def _defaulter_filters(iid, kind, scope):
    if kind == "teacher":
        return {"units": [], "classes": sorted({c for c, _ in scope}), "sections": sorted({s for _, s in scope})}
    q = {"institution_id": iid} if scope is None else {"institution_id": iid, "name": {"$in": list(scope)}}
    classes = await db.classes.find(q, {"_id": 0, "name": 1, "academic_unit_id": 1}).to_list(2000)
    uids = {c.get("academic_unit_id") for c in classes}
    units = await db.academic_units.find({"institution_id": iid, "id": {"$in": list(uids)}}, {"_id": 0, "id": 1, "name": 1}).to_list(200)
    secs = await db.sections.distinct("name", {"institution_id": iid, "class_name": {"$in": [c["name"] for c in classes]}})
    return {"units": units, "classes": sorted({c["name"] for c in classes}, key=lambda n: (_grade_num(n) or 999, n)),
            "sections": sorted(secs)}


@api.get("/fees/defaulters")
async def fee_defaulters(academic_unit_id: str = "", class_name: str = "", section: str = "", bucket: str = "",
                         min_amount: float = Query(0, ge=0), sort: str = "amount",
                         page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=1000),
                         user: dict = Depends(get_current_user)):
    """Students with invoices past due date and balance > 0 (partial payments → remaining balance; concessions excluded)."""
    iid = user.get("institution_id")
    kind, scope, rows, open_info = await _defaulter_rows(user, academic_unit_id, class_name, section)
    rows, buckets = _defaulter_filter(rows, bucket, min_amount, sort)
    school = await db.institutions.find_one({"id": iid}, {"_id": 0, "name": 1})
    return {"as_of": open_info["as_of"], "upcoming": open_info, "scope": kind, "can_remind": kind != "teacher", "total": len(rows), "page": page,
            "page_size": page_size, "rows": rows[(page - 1) * page_size: page * page_size], "buckets": buckets,
            "totals": {"students": len(rows), "overdue": _r2(sum(r["overdue_amount"] for r in rows)),
                       "outstanding": _r2(sum(r["total_outstanding"] for r in rows))},
            "filters": await _defaulter_filters(iid, kind, scope),
            "school": {"name": (school or {}).get("name"), "logo_src": await _school_logo_src(iid)}}


@api.get("/fees/defaulters/export.csv")
async def fee_defaulters_csv(academic_unit_id: str = "", class_name: str = "", section: str = "", bucket: str = "",
                             min_amount: float = Query(0, ge=0), sort: str = "amount", user: dict = Depends(get_current_user)):
    _, _, rows, _ = await _defaulter_rows(user, academic_unit_id, class_name, section)
    rows, _ = _defaulter_filter(rows, bucket, min_amount, sort)
    buf = _io.StringIO()
    w = _csv.writer(buf)
    w.writerow(["Student", "Admission no", "Class", "Section", "Parent", "Phone", "Overdue amount", "Total outstanding",
                "Oldest due date", "Days late", "Ageing", "Last reminder at"])
    for r in rows:
        w.writerow([r["student_name"], r["admission_no"] or "", r["class_name"] or "", r["section"] or "", r["parent_name"] or "",
                    r["parent_phone"] or "", f"{r['overdue_amount']:.2f}", f"{r['total_outstanding']:.2f}", r["oldest_due_date"],
                    r["days_late"], r["bucket"], (r["last_reminder_at"] or "")[:16]])
    await audit(user, "fee_defaulters_export", "fee_invoices", None, f"{len(rows)} rows", user["institution_id"])
    return Response(content=buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="fee-defaulters-{_today()}.csv"'})


class DefaulterRemindIn(_BM):
    student_ids: _List[str] = _F(min_length=1, max_length=500)


_REMIND_STATUS = {"sent": "sent", "deduped": "skipped_throttled", "bell_only_no_phone": "no_contact",
                  "bell_only_failed": "failed", "paid": "no_dues"}


@api.post("/fees/defaulters/remind")
async def fee_defaulters_remind(body: DefaulterRemindIn, user: dict = Depends(require_admin_or_principal)):
    """One-tap reminders via the Phase 49 pipeline. Throttle: 1 fee reminder per student per day (shared with auto)."""
    iid = user["institution_id"]
    kind, scope = await _fee_view_scope(user)
    today, cfg = await _inst_today(iid), await _fee_reminder_cfg(iid)
    results = []
    for sid in dict.fromkeys(body.student_ids):
        s = await db.students.find_one({"id": sid, "institution_id": iid}, {"_id": 0, "class_name": 1, "section": 1,
                                                                            "first_name": 1, "last_name": 1})
        if not s or not _stu_in_scope(kind, scope, s):
            results.append({"student_id": sid, "status": "not_found" if not s else "out_of_scope"})
            continue
        name = f"{s.get('first_name', '')} {s.get('last_name', '')}".strip()
        vs = (await _open_views_by_student(iid, [sid], today)).get(sid, [])
        if not vs:
            results.append({"student_id": sid, "student_name": name, "status": "no_dues"})
            continue
        target = next((v for v in vs if v.get("due_date") and v["due_date"] < today), vs[0])
        inv = await db.fee_invoices.find_one({"id": target["id"]}, {"_id": 0})
        r = await _send_fee_reminder(inv, "manual", "defaulter", today, cfg, actor=user)
        results.append({"student_id": sid, "student_name": name, "invoice_id": inv["id"],
                        "status": _REMIND_STATUS.get(r["status"], r["status"]), "detail": r["status"]})
    summary = {k: sum(1 for r in results if r["status"] == k) for k in ("sent", "skipped_throttled", "no_contact", "failed")}
    await audit(user, "fee_defaulters_remind", "fee_reminders", None, f"{len(results)} students: {summary}", iid)
    run = await phase59.save_run(user, "fee_defaulters_remind", "Defaulter reminders", await phase59.reminder_items(results))
    return {"results": results, **summary, "run_id": run["run_id"], "items": run["items"], "run_summary": run["summary"]}


async def _carry_forward_dues(iid, from_year, to_year, student_ids, actor, run_id=None):
    """Additive + idempotent: one 'Previous dues' arrears invoice per student per from→to year, linked to the source
    invoices (which are only FLAGGED carried_forward_to — amounts/payments are never touched)."""
    today = _today()
    out = {"created": 0, "already_carried": 0, "amount": 0.0, "arrears_invoice_ids": [], "items": []}
    names = {x["id"]: x async for x in db.students.find({"institution_id": iid, "id": {"$in": list(student_ids)}},
                                                        {"_id": 0, "id": 1, "first_name": 1, "last_name": 1, "admission_no": 1,
                                                         "class_name": 1, "section": 1})}

    def add(sid, status, reason, code):
        x = names.get(sid, {})
        out["items"].append(phase59.item(sid, f"{x.get('first_name', '')} {x.get('last_name', '')}".strip() or sid, status, reason, code,
                                         f"{x.get('admission_no') or '—'} · {x.get('class_name') or ''} {x.get('section') or ''}".strip(),
                                         phase59.fix("open_student", sid)))
    for sid in dict.fromkeys(student_ids):
        key = f"{sid}:{from_year}>{to_year}"
        if await db.fee_invoices.find_one({"institution_id": iid, "arrears_key": key}, {"_id": 1}):
            out["already_carried"] += 1
            add(sid, "skipped", f"Dues already carried forward to {to_year}", "already_carried")
            continue
        src = await db.fee_invoices.find({"institution_id": iid, "student_id": sid, "academic_year": from_year,
                                          "carried_forward_to": {"$exists": False}, "status": {"$ne": "paid"}},
                                         {"_id": 0}).sort("due_date", 1).to_list(500)
        late = await _late_map({i["structure_id"] for i in src if i.get("structure_id")})
        open_ = [(i, v) for i in src for v in [_invoice_view(i, late.get(i.get("structure_id")), today)] if v["balance"] > 0]
        if not open_:
            add(sid, "skipped", f"No unpaid dues in {from_year}", "no_dues")
            continue
        stu = await db.students.find_one({"id": sid, "institution_id": iid}, {"_id": 0}) or {}
        items = [{"head_id": None, "title": f"Previous dues {from_year} · {i.get('period_label')}", "amount": v["balance"],
                  "source_invoice_id": i["id"]} for i, v in open_]
        total = _r2(sum(x["amount"] for x in items))
        due = min((i.get("due_date") for i, _ in open_ if i.get("due_date")), default=today)
        doc = {"id": str(uuid.uuid4()), "institution_id": iid, "account_id": f"arrears:{sid}:{to_year}", "structure_id": None,
               "frequency": "arrears", "period_label": f"Previous dues {from_year}", "student_id": sid,
               "student_name": f"{stu.get('first_name', '')} {stu.get('last_name', '')}".strip() or open_[0][0].get("student_name"),
               "class_name": stu.get("class_name"), "section": stu.get("section"), "academic_year": to_year,
               "items": items, "subtotal": total, "discount_amount": 0.0, "fine_amount": 0.0, "fine_applied": True,
               "total": total, "paid_amount": 0.0, "due_date": due, "status": "overdue" if due < today else "pending",
               "is_arrears": True, "arrears_key": key, "from_year": from_year, "source_invoice_ids": [i["id"] for i, _ in open_],
               "promotion_run_id": run_id, "generated_at": now_iso(), "generated_by": (actor or {}).get("email")}
        try:
            await db.fee_invoices.insert_one(dict(doc))
        except DuplicateKeyError:
            out["already_carried"] += 1
            add(sid, "skipped", f"Dues already carried forward to {to_year}", "already_carried")
            continue
        for i, v in open_:
            await db.fee_invoices.update_one({"id": i["id"], "carried_forward_to": {"$exists": False}}, {"$set": {
                "carried_forward_to": doc["id"], "carried_forward_amount": v["balance"], "carried_forward_at": now_iso(),
                "carried_forward_year": to_year}})
        await audit(actor, "fee_dues_carry_forward", "fee_invoices", doc["id"],
                    f"{doc['student_name']} · ₹{total:,.2f} · {from_year} → {to_year} · {len(items)} invoice(s)", iid)
        out["created"] += 1
        out["amount"] = _r2(out["amount"] + total)
        out["arrears_invoice_ids"].append(doc["id"])
        add(sid, "created", f"₹{total:,.2f} carried forward from {len(items)} invoice(s)", "created")
    return out


@api.post("/fees/carry-forward")
async def fee_carry_forward(payload: dict = Body(...), user: dict = Depends(require_fee_admin)):
    """Re-run (idempotent) the dues carry-forward for an executed promotion run."""
    iid = user["institution_id"]
    run = await _promo_run_or_404(iid, (payload or {}).get("run_id") or "")
    if run["status"] != "executed":
        raise HTTPException(status_code=409, detail="Only an executed promotion run can carry dues forward")
    decs = await db.promotion_decisions.find({"run_id": run["id"], "decision": {"$in": ["promote", "detain"]}},
                                             {"_id": 0, "student_id": 1}).to_list(50000)
    out = await _carry_forward_dues(iid, run["from_year"], run["to_year"], [d["student_id"] for d in decs], user, run["id"])
    crun = await phase59.save_run(user, "dues_carry_forward", f"Dues carry-forward {run['from_year']} → {run['to_year']}", out["items"],
                                  ref_id=run["id"], extra={"amount": out["amount"]})
    return {**out, "run_id": crun["run_id"], "summary": crun["summary"]}


@api.get("/fees/monthly-summary")
async def fee_monthly_summary(month: str = "", user: dict = Depends(require_admin_or_principal)):
    """Per class: billed = invoices due in the month (net of concessions), collected = payments received in the month
    (same rule as the Day Book), outstanding = remaining balance of the month's invoices."""
    iid = user["institution_id"]
    m = month or (await _inst_today(iid))[:7]
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", m):
        raise HTTPException(status_code=400, detail="month must be YYYY-MM")
    scope = await _fee_scope(user)
    iq = {"institution_id": iid, "due_date": {"$gte": f"{m}-01", "$lte": f"{m}-31"}, "is_arrears": {"$ne": True}}
    pq = {"institution_id": iid, "paid_on": {"$gte": f"{m}-01", "$lte": f"{m}-31"}}
    if scope is not None:
        iq["class_name"] = pq["class_name"] = {"$in": list(scope[0])}
    rows = {}

    def row(cn):
        k = cn or "—"
        return rows.setdefault(k, {"class_name": k, "invoices": 0, "gross": 0.0, "concession": 0.0, "billed": 0.0,
                                   "outstanding": 0.0, "carried_forward": 0.0, "collected": 0.0, "prev_dues_collected": 0.0,
                                   "receipts": 0})
    invs = await db.fee_invoices.find(iq, {"_id": 0}).to_list(100000)
    late = await _late_map({i["structure_id"] for i in invs if i.get("structure_id")})
    for i in invs:
        v, r = _invoice_view(i, late.get(i.get("structure_id"))), row(i.get("class_name"))
        r["invoices"] += 1
        r["gross"] = _r2(r["gross"] + float(i.get("subtotal") or 0) + v["fine_amount"])
        r["concession"] = _r2(r["concession"] + float(i.get("discount_amount") or 0))
        r["billed"] = _r2(r["billed"] + v["amount_due"])
        if i.get("carried_forward_to"):
            r["carried_forward"] = _r2(r["carried_forward"] + float(i.get("carried_forward_amount") or 0))
        else:
            r["outstanding"] = _r2(r["outstanding"] + v["balance"])
    pays = await db.fee_payments.find(pq, {"_id": 0, "items": 0}).to_list(100000)
    live = [p for p in pays if not p.get("reversed")]
    rev = [p for p in pays if p.get("reversed")]
    methods, daily = {}, {}
    inv_meta = {i["id"]: i async for i in db.fee_invoices.find({"id": {"$in": list({p["invoice_id"] for p in live})}},
                                                                {"_id": 0, "id": 1, "due_date": 1, "is_arrears": 1})}
    for p in live:
        r = row(p.get("class_name"))
        r["collected"] = _r2(r["collected"] + p["amount"]); r["receipts"] += 1
        src = inv_meta.get(p["invoice_id"]) or {}
        if src.get("is_arrears") or (src.get("due_date") or "9999") < f"{m}-01":
            r["prev_dues_collected"] = _r2(r["prev_dues_collected"] + p["amount"])
        e = methods.setdefault(p["method"], {"key": p["method"], "total": 0.0, "count": 0})
        e["total"] = _r2(e["total"] + p["amount"]); e["count"] += 1
        d = daily.setdefault(p["paid_on"], {"date": p["paid_on"], "total": 0.0, "count": 0})
        d["total"] = _r2(d["total"] + p["amount"]); d["count"] += 1

    def pct(r):
        return round((r["billed"] - r["outstanding"] - r["carried_forward"]) / r["billed"] * 100, 1) if r["billed"] else None
    out_rows = sorted(rows.values(), key=lambda r: (_grade_num(r["class_name"]) or 999, r["class_name"]))
    for r in out_rows:
        r["collection_pct"] = pct(r)
    totals = {k: _r2(sum(r[k] for r in out_rows)) for k in ("gross", "concession", "billed", "outstanding", "carried_forward",
                                                            "collected", "prev_dues_collected")}
    totals.update({"invoices": sum(r["invoices"] for r in out_rows), "receipts": sum(r["receipts"] for r in out_rows)})
    totals["collection_pct"] = pct(totals)
    school = await db.institutions.find_one({"id": iid}, {"_id": 0, "name": 1})
    return {"month": m, "as_of": _today(), "school": {"name": (school or {}).get("name"), "logo_src": await _school_logo_src(iid)},
            "rows": out_rows, "totals": totals, "by_method": sorted(methods.values(), key=lambda e: -e["total"]),
            "daily": sorted(daily.values(), key=lambda d: d["date"]),
            "reversed": {"count": len(rev), "amount": _r2(sum(p["amount"] for p in rev))}}


# ==================== PHASE 51: UPI QR, payment proofs, fee issues, statements (offline only — no gateway) ====================
from urllib.parse import quote as _urlquote  # noqa: E402
import segno as _segno  # noqa: E402

UPI_VPA_RX = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.\-_]{1,255}@[A-Za-z][A-Za-z0-9.\-]{1,63}$")
PROOF_TYPES = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "image/heic": "heic", "image/heif": "heif"}
PROOF_EXT = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp", "heic": "image/heic", "heif": "image/heif"}
PROOF_MAX = 5 * 1024 * 1024


class UpiSettingsIn(_BM):
    enabled: bool = False
    vpa: str = _F(default="", max_length=320)
    payee_name: str = _F(default="", max_length=60)
    instructions: str = _F(default="", max_length=400)


async def _upi_cfg(iid):
    inst = await db.institutions.find_one({"id": iid}, {"_id": 0, "upi": 1}) or {}
    return inst.get("upi") or {}


def _upi_block(cfg, inv, admission_no):
    """Standard upi://pay URI + QR for the invoice's CURRENT balance; None when disabled/paid/carried forward."""
    if not (cfg or {}).get("enabled") or not cfg.get("vpa") or inv.get("balance", 0) <= 0 or inv.get("carried_forward_to"):
        return None
    ref = inv["id"].replace("-", "")[:8].upper()
    adm = re.sub(r"[^A-Za-z0-9\-/]", "", admission_no or "")
    note = f"Fee {adm} {ref}".replace("  ", " ").strip()[:50]
    tr = re.sub(r"[^A-Za-z0-9]", "", f"{adm}{ref}")[:35]
    amount = f"{inv['balance']:.2f}"
    params = [("pa", cfg["vpa"]), ("pn", cfg.get("payee_name") or ""), ("am", amount), ("cu", "INR"), ("tn", note), ("tr", tr)]
    uri = "upi://pay?" + "&".join(f"{k}={_urlquote(v, safe='@.-_')}" for k, v in params)
    return {"uri": uri, "qr": _segno.make(uri, error="m").png_data_uri(scale=6, border=2), "amount": inv["balance"],
            "vpa": cfg["vpa"], "payee_name": cfg.get("payee_name"), "instructions": cfg.get("instructions") or "",
            "note": note, "ref": ref}


@api.get("/fees/upi-settings")
async def get_upi_settings(user: dict = Depends(require_admin_or_principal)):
    return {"enabled": False, "vpa": "", "payee_name": "", "instructions": "", **(await _upi_cfg(user["institution_id"]))}


@api.put("/fees/upi-settings")
async def put_upi_settings(body: UpiSettingsIn, user: dict = Depends(require_fee_admin)):
    iid = user["institution_id"]
    vpa, payee = body.vpa.strip(), body.payee_name.strip()
    if vpa and not UPI_VPA_RX.match(vpa):
        raise HTTPException(status_code=400, detail="UPI ID must look like name@bank")
    if body.enabled and (not vpa or not payee):
        raise HTTPException(status_code=400, detail="UPI ID and payee name are required to enable UPI payments")
    before = await _upi_cfg(iid)
    new = {"enabled": body.enabled, "vpa": vpa, "payee_name": payee, "instructions": body.instructions.strip(),
           "updated_by": user.get("email"), "updated_at": now_iso()}
    await db.institutions.update_one({"id": iid}, {"$set": {"upi": new}})
    await audit(user, "fee_upi_settings", "institutions", iid,
                f"{before.get('enabled')}/{before.get('vpa')} → {new['enabled']}/{new['vpa']} · payee {payee}", iid)
    return new


async def _invoice_for(user, inv_id):
    """Invoice + view with access rules: parent own child, student self, admin, principal in scope."""
    iid = user.get("institution_id")
    inv = await db.fee_invoices.find_one({"id": inv_id, "institution_id": iid}, {"_id": 0})
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    role = user.get("role")
    if role == "parent":
        if inv["student_id"] not in (user.get("student_ids") or []):
            raise HTTPException(status_code=403, detail="This student is not linked to your account")
    elif role == "student":
        if inv["student_id"] != user.get("student_id"):
            raise HTTPException(status_code=403, detail="Access denied")
    else:
        await _require_collect_scope(user, inv.get("class_name"))
    late = None if not inv.get("structure_id") else (await _late_map({inv["structure_id"]})).get(inv["structure_id"])
    return inv, _invoice_view(inv, late)


@api.get("/fees/invoices/{inv_id}/pay-info")
async def fee_invoice_pay_info(inv_id: str, user: dict = Depends(get_current_user)):
    """Invoice print/pay view: current balance + UPI QR (when enabled) + any pending proof."""
    inv, view = await _invoice_for(user, inv_id)
    iid = inv["institution_id"]
    stu = await db.students.find_one({"id": inv["student_id"]}, {"_id": 0, "admission_no": 1}) or {}
    inst = await db.institutions.find_one({"id": iid}, {"_id": 0, "name": 1, "address": 1}) or {}
    pending = await db.fee_payment_proofs.find_one({"invoice_id": inv_id, "status": "pending"}, {"_id": 0, "file_path": 0})
    return {"invoice": view, "admission_no": stu.get("admission_no"), "upi": _upi_block(await _upi_cfg(iid), view, stu.get("admission_no")),
            "pending_proof": pending, "school": {**inst, "logo_src": await _school_logo_src(iid)}}


async def _utr_usage(iid, utr, exclude_proof=None):
    if not utr:
        return []
    rx = {"$regex": f"^{re.escape(utr)}$", "$options": "i"}
    hits = [{"kind": "payment", "receipt_no": p["receipt_no"], "student_name": p.get("student_name")}
            async for p in db.fee_payments.find({"institution_id": iid, "reference": rx, "reversed": False},
                                                {"_id": 0, "receipt_no": 1, "student_name": 1})]
    hits += [{"kind": "proof", "status": p["status"], "student_name": p.get("student_name")}
             async for p in db.fee_payment_proofs.find({"institution_id": iid, "utr": rx, "status": {"$ne": "rejected"},
                                                        "id": {"$ne": exclude_proof}}, {"_id": 0, "status": 1, "student_name": 1})]
    return hits


async def _read_proof_file(file):
    ext = (file.filename or "").rsplit(".", 1)[-1].lower() if "." in (file.filename or "") else ""
    ctype = file.content_type if file.content_type in PROOF_TYPES else PROOF_EXT.get(ext)
    if not ctype:
        raise HTTPException(status_code=400, detail="Please upload a JPG, PNG, HEIC or WEBP image")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="The file is empty")
    if len(data) > PROOF_MAX:
        raise HTTPException(status_code=400, detail="Image must be 5 MB or smaller")
    return data, ctype


def _store_fee_file(iid, key, data, ctype):
    path = f"lnmo/fee-proofs/{iid}/{key}.{PROOF_TYPES[ctype]}"
    try:
        return _put_object(path, data, ctype)["path"]
    except Exception:
        raise HTTPException(status_code=502, detail="File storage is unavailable right now — try again shortly")


async def _fee_parent_notify(iid, student_id, title, text, related_id, actor=None):
    """Bell to linked parents + WhatsApp/SMS via the comm engine (STUB mode in this environment)."""
    parents = await db.users.find({"institution_id": iid, "role": "parent", "student_ids": student_id},
                                  {"_id": 0, "id": 1, "phone": 1, "name": 1}).to_list(10)
    for p in parents:
        await _notify(iid, p["id"], "fee_payment_proof", title, text, related_id)
    stu = await db.students.find_one({"id": student_id}, {"_id": 0, "guardian_phone": 1, "guardian_name": 1}) or {}
    phone = _norm_phone(stu.get("guardian_phone")) or next((p["phone"] for p in parents if p.get("phone")), None)
    if phone:
        cfg = await _fee_reminder_cfg(iid)
        try:
            await send_message(iid, cfg["channel"], [{"name": stu.get("guardian_name") or "Parent", "phone": phone,
                                                      "student_id": student_id, "body": f"{title}. {text}"}],
                               body=f"{title}. {text}", module="fee_proof", actor=actor)
        except HTTPException:
            pass


@api.post("/parent/fees/invoices/{inv_id}/proofs")
async def submit_fee_proof(inv_id: str, file: UploadFile = File(...), amount: float = Form(...), paid_on: str = Form(...),
                           utr: str = Form(""), note: str = Form(""), user: dict = Depends(require_roles("parent"))):
    inv, view = await _invoice_for(user, inv_id)
    iid = inv["institution_id"]
    if view["balance"] <= 0:
        raise HTTPException(status_code=400, detail="This invoice has no balance due")
    amount = _r2(amount)
    if amount <= 0 or amount > view["balance"]:
        raise HTTPException(status_code=400, detail=f"Amount must be more than 0 and at most the balance (₹{view['balance']:,.2f})")
    try:
        datetime.strptime(paid_on, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Payment date must be YYYY-MM-DD")
    if paid_on > await _inst_today(iid):
        raise HTTPException(status_code=400, detail="Payment date cannot be in the future")
    utr = re.sub(r"\s", "", utr or "")
    if utr and not re.fullmatch(r"[A-Za-z0-9\-]{6,40}", utr):
        raise HTTPException(status_code=400, detail="UTR / transaction ID should be 6–40 letters or digits")
    if await db.fee_payment_proofs.find_one({"invoice_id": inv_id, "status": {"$in": ["pending", "approving"]}}, {"_id": 1}):
        raise HTTPException(status_code=409, detail="A payment proof for this invoice is already awaiting verification")
    data, ctype = await _read_proof_file(file)
    dup = await _utr_usage(iid, utr)
    pid = str(uuid.uuid4())
    doc = {"id": pid, "institution_id": iid, "invoice_id": inv_id, "account_id": inv.get("account_id"), "student_id": inv["student_id"],
           "student_name": inv.get("student_name"), "class_name": inv.get("class_name"), "section": inv.get("section"),
           "period_label": inv.get("period_label"), "academic_year": inv.get("academic_year"), "amount": amount, "utr": utr or None,
           "paid_on": paid_on, "note": (note or "").strip()[:300] or None,
           "file_path": _store_fee_file(iid, pid, data, ctype), "file_type": ctype, "file_size": len(data),
           "status": "pending", "utr_duplicate": dup, "submitted_by": user["id"], "submitted_by_name": user.get("name"),
           "submitted_at": now_iso()}
    try:
        await db.fee_payment_proofs.insert_one(dict(doc))
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail="A payment proof for this invoice is already awaiting verification")
    await _notify_managers(iid, "fee_payment_proof", f"Payment proof: {doc['student_name']}",
                           f"₹{amount:,.2f} · {doc['period_label']} · UTR {utr or '—'}", pid, class_names=[inv.get("class_name")])
    await audit(user, "fee_proof_submit", "fee_payment_proofs", pid, f"{doc['student_name']} · ₹{amount:,.2f} · UTR {utr or '—'}", iid)
    doc.pop("file_path")
    return {"proof": doc, "utr_warning": dup}


def _proof_out(p):
    return {k: v for k, v in p.items() if k not in ("_id", "file_path")}


async def _scoped_q(user, q):
    sc = await _fee_scope(user)
    if sc is not None:
        q["class_name"] = {"$in": list(sc[0])}
    return q


@api.get("/fees/proofs")
async def list_fee_proofs(status: str = "pending", q: str = "", user: dict = Depends(require_admin_or_principal)):
    f = await _scoped_q(user, {"institution_id": user["institution_id"]})
    if status != "all":
        f["status"] = "pending" if status == "pending" else status
    if q.strip():
        rx = {"$regex": re.escape(q.strip()), "$options": "i"}
        f["$or"] = [{"student_name": rx}, {"utr": rx}, {"receipt_no": rx}]
    rows = await db.fee_payment_proofs.find(f, {"_id": 0, "file_path": 0}).sort("submitted_at", -1).to_list(300)
    invs = {i["id"]: i for i in await db.fee_invoices.find({"id": {"$in": [r["invoice_id"] for r in rows]}}, {"_id": 0}).to_list(300)}
    late = await _late_map({i["structure_id"] for i in invs.values() if i.get("structure_id")})
    for r in rows:
        i = invs.get(r["invoice_id"])
        r["invoice_balance"] = _invoice_view(i, late.get(i.get("structure_id")))["balance"] if i else None
        if r["status"] == "pending":
            r["utr_duplicate"] = await _utr_usage(user["institution_id"], r.get("utr"), exclude_proof=r["id"])
    return {"proofs": rows}


@api.get("/fees/proofs/stats")
async def fee_proof_stats(user: dict = Depends(require_admin_or_principal)):
    base = {"institution_id": user["institution_id"]}
    p = await db.fee_payment_proofs.count_documents(await _scoped_q(user, {**base, "status": "pending"}))
    i = await db.fee_issues.count_documents(await _scoped_q(user, {**base, "status": "open"}))
    return {"pending_proofs": p, "open_issues": i, "total": p + i}


async def _fee_file_access(user, rec):
    if user.get("role") == "parent":
        if rec["student_id"] not in (user.get("student_ids") or []):
            raise HTTPException(status_code=403, detail="Access denied")
    else:
        await _require_collect_scope(user, rec.get("class_name"))


@api.get("/fees/proofs/{pid}/file")
async def fee_proof_file(pid: str, user: dict = Depends(get_current_user)):
    p = await db.fee_payment_proofs.find_one({"id": pid, "institution_id": user.get("institution_id")}, {"_id": 0})
    if not p:
        raise HTTPException(status_code=404, detail="Proof not found")
    await _fee_file_access(user, p)
    try:
        data, _ = _get_object(p["file_path"])
    except Exception:
        raise HTTPException(status_code=404, detail="File not available")
    return Response(content=data, media_type=p["file_type"], headers={"Cache-Control": "private, max-age=300"})


class ProofApproveIn(_BM):
    amount: Optional[float] = _F(default=None, gt=0, le=10_000_000)
    utr: Optional[str] = _F(default=None, max_length=40)
    paid_on: Optional[str] = _F(default=None, max_length=10)
    note: Optional[str] = _F(default=None, max_length=300)


class ProofRejectIn(_BM):
    reason: str = _F(min_length=3, max_length=300)


async def _proof_for_staff(user, pid):
    p = await db.fee_payment_proofs.find_one({"id": pid, "institution_id": user["institution_id"]}, {"_id": 0})
    if not p:
        raise HTTPException(status_code=404, detail="Proof not found")
    await _require_collect_scope(user, p.get("class_name"))
    return p


@api.post("/fees/proofs/{pid}/approve")
async def approve_fee_proof(pid: str, body: ProofApproveIn = Body(default=ProofApproveIn()), user: dict = Depends(require_admin_or_principal)):
    """Approve → a normal fee payment through the shared payment path (method UPI, reference UTR, date = proof date)."""
    p = await _proof_for_staff(user, pid)
    if not await db.fee_payment_proofs.find_one_and_update({"id": pid, "status": "pending"}, {"$set": {"status": "approving"}}):
        raise HTTPException(status_code=409, detail=f"This proof is already {p['status']}")
    utr = (body.utr if body.utr is not None else p.get("utr")) or None
    try:
        res = await _create_fee_payment(user, p["invoice_id"], body.amount or p["amount"], "upi", utr,
                                        body.note or (f"Parent proof {pid[:8]}" + (f" · {p['note']}" if p.get("note") else "")),
                                        body.paid_on or p["paid_on"], extra={"proof_id": pid})
    except HTTPException:
        await db.fee_payment_proofs.update_one({"id": pid, "status": "approving"}, {"$set": {"status": "pending"}})
        raise
    pay = res["payment"]
    await db.fee_payment_proofs.update_one({"id": pid}, {"$set": {
        "status": "approved", "reviewed_by": user.get("name") or user.get("email"), "reviewed_at": now_iso(),
        "payment_id": pay["id"], "receipt_no": pay["receipt_no"], "approved_amount": pay["amount"], "approved_utr": utr,
        "approved_paid_on": pay["paid_on"]}})
    await _fee_parent_notify(user["institution_id"], p["student_id"], f"Payment verified: {p.get('student_name')}",
                             f"₹{pay['amount']:,.2f} received for {p.get('period_label')} · receipt {pay['receipt_no']}", p["invoice_id"], actor=user)
    await audit(user, "fee_proof_approve", "fee_payment_proofs", pid, f"{pay['receipt_no']} · ₹{pay['amount']:,.2f} · UTR {utr or '—'}",
                user["institution_id"])
    return {"proof": _proof_out(await db.fee_payment_proofs.find_one({"id": pid})), **res}


@api.post("/fees/proofs/{pid}/reject")
async def reject_fee_proof(pid: str, body: ProofRejectIn, user: dict = Depends(require_admin_or_principal)):
    p = await _proof_for_staff(user, pid)
    reason = body.reason.strip()
    r = await db.fee_payment_proofs.update_one({"id": pid, "status": "pending"}, {"$set": {
        "status": "rejected", "reject_reason": reason, "reviewed_by": user.get("name") or user.get("email"), "reviewed_at": now_iso()}})
    if not r.modified_count:
        raise HTTPException(status_code=409, detail=f"This proof is already {p['status']}")
    await _fee_parent_notify(user["institution_id"], p["student_id"], f"Payment proof not accepted: {p.get('student_name')}",
                             f"{p.get('period_label')}: {reason}. You can upload a new proof in the parent portal.", p["invoice_id"], actor=user)
    await audit(user, "fee_proof_reject", "fee_payment_proofs", pid, f"{p.get('student_name')} · {reason}", user["institution_id"])
    return {"proof": _proof_out(await db.fee_payment_proofs.find_one({"id": pid}))}


# ---- fee issues ("I have already paid") — a simple message thread, open|resolved ----
async def _issue_msg(user, by, text, file=None, iid=None, key=None):
    m = {"id": str(uuid.uuid4()), "by": by, "by_name": user.get("name") or user.get("email"), "text": text.strip()[:1000], "at": now_iso()}
    if file is not None and (file.filename or ""):
        data, ctype = await _read_proof_file(file)
        m.update({"file_path": _store_fee_file(iid, f"issue-{key}-{m['id']}", data, ctype), "file_type": ctype})
    return m


def _issue_out(i):
    return {**{k: v for k, v in i.items() if k != "_id"},
            "messages": [{**{k: v for k, v in m.items() if k != "file_path"}, "has_file": bool(m.get("file_path"))} for m in i.get("messages", [])]}


@api.post("/parent/fees/invoices/{inv_id}/issues")
async def raise_fee_issue(inv_id: str, message: str = Form(...), file: Optional[UploadFile] = File(None),
                          user: dict = Depends(require_roles("parent"))):
    inv, view = await _invoice_for(user, inv_id)
    iid = inv["institution_id"]
    if len(message.strip()) < 3:
        raise HTTPException(status_code=400, detail="Please describe the issue")
    last = await db.fee_payment_proofs.find_one({"invoice_id": inv_id}, {"_id": 0, "status": 1, "submitted_at": 1}, sort=[("submitted_at", -1)])
    stale = last and last["status"] == "pending" and last["submitted_at"] < (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    if not (view["balance"] > 0 or (last and last["status"] == "rejected") or stale):
        raise HTTPException(status_code=400, detail="This invoice is fully paid")
    if await db.fee_issues.find_one({"invoice_id": inv_id, "status": "open"}, {"_id": 1}):
        raise HTTPException(status_code=409, detail="An issue is already open for this invoice — add a message to it")
    iss_id = str(uuid.uuid4())
    doc = {"id": iss_id, "institution_id": iid, "invoice_id": inv_id, "student_id": inv["student_id"], "student_name": inv.get("student_name"),
           "class_name": inv.get("class_name"), "section": inv.get("section"), "period_label": inv.get("period_label"),
           "status": "open", "raised_by": user["id"], "raised_by_name": user.get("name"), "created_at": now_iso(), "updated_at": now_iso(),
           "last_proof_status": (last or {}).get("status"), "messages": [await _issue_msg(user, "parent", message, file, iid, iss_id)]}
    await db.fee_issues.insert_one(dict(doc))
    await _notify_managers(iid, "fee_issue", f"Fee issue: {doc['student_name']}", message.strip()[:120], iss_id, class_names=[inv.get("class_name")])
    await audit(user, "fee_issue_open", "fee_issues", iss_id, f"{doc['student_name']} · {doc['period_label']}", iid)
    return _issue_out(doc)


@api.post("/parent/fees/issues/{iss_id}/messages")
async def parent_fee_issue_message(iss_id: str, message: str = Form(...), file: Optional[UploadFile] = File(None),
                                   user: dict = Depends(require_roles("parent"))):
    i = await db.fee_issues.find_one({"id": iss_id, "institution_id": user["institution_id"]}, {"_id": 0})
    if not i or i["student_id"] not in (user.get("student_ids") or []):
        raise HTTPException(status_code=404, detail="Issue not found")
    m = await _issue_msg(user, "parent", message, file, i["institution_id"], iss_id)
    await db.fee_issues.update_one({"id": iss_id}, {"$push": {"messages": m}, "$set": {"status": "open", "updated_at": now_iso()}})
    return _issue_out(await db.fee_issues.find_one({"id": iss_id}))


@api.get("/fees/issues")
async def list_fee_issues(status: str = "open", user: dict = Depends(require_admin_or_principal)):
    f = await _scoped_q(user, {"institution_id": user["institution_id"]})
    if status != "all":
        f["status"] = status
    return {"issues": [_issue_out(i) for i in await db.fee_issues.find(f, {"_id": 0}).sort("updated_at", -1).to_list(300)]}


async def _issue_for_staff(user, iss_id):
    i = await db.fee_issues.find_one({"id": iss_id, "institution_id": user["institution_id"]}, {"_id": 0})
    if not i:
        raise HTTPException(status_code=404, detail="Issue not found")
    await _require_collect_scope(user, i.get("class_name"))
    return i


class IssueReplyIn(_BM):
    text: str = _F(min_length=1, max_length=1000)
    resolve: bool = False


@api.post("/fees/issues/{iss_id}/reply")
async def staff_fee_issue_reply(iss_id: str, body: IssueReplyIn, user: dict = Depends(require_admin_or_principal)):
    i = await _issue_for_staff(user, iss_id)
    m = await _issue_msg(user, "staff", body.text)
    await db.fee_issues.update_one({"id": iss_id}, {"$push": {"messages": m}, "$set": {
        "updated_at": now_iso(), **({"status": "resolved", "resolved_by": m["by_name"], "resolved_at": now_iso()} if body.resolve else {})}})
    await _fee_parent_notify(user["institution_id"], i["student_id"], f"School replied about fees: {i.get('student_name')}", body.text[:200], iss_id, actor=user)
    return _issue_out(await db.fee_issues.find_one({"id": iss_id}))


@api.post("/fees/issues/{iss_id}/status")
async def staff_fee_issue_status(iss_id: str, payload: dict = Body(...), user: dict = Depends(require_admin_or_principal)):
    i = await _issue_for_staff(user, iss_id)
    st = (payload or {}).get("status")
    if st not in ("open", "resolved"):
        raise HTTPException(status_code=400, detail="status must be open or resolved")
    await db.fee_issues.update_one({"id": iss_id}, {"$set": {"status": st, "updated_at": now_iso(),
                                                             **({"resolved_by": user.get("name"), "resolved_at": now_iso()} if st == "resolved" else {})}})
    await audit(user, "fee_issue_status", "fee_issues", iss_id, f"{i.get('student_name')} → {st}", user["institution_id"])
    return _issue_out(await db.fee_issues.find_one({"id": iss_id}))


@api.post("/fees/issues/{iss_id}/record-payment")
async def staff_fee_issue_payment(iss_id: str, body: ProofApproveIn, user: dict = Depends(require_admin_or_principal)):
    """Staff confirmed the money arrived → record it (shared payment path, method UPI) and resolve the issue."""
    i = await _issue_for_staff(user, iss_id)
    if not body.amount:
        raise HTTPException(status_code=400, detail="amount is required")
    res = await _create_fee_payment(user, i["invoice_id"], body.amount, "upi", body.utr or None,
                                    body.note or f"Resolved fee issue {iss_id[:8]}", body.paid_on, extra={"issue_id": iss_id})
    pay = res["payment"]
    m = await _issue_msg(user, "staff", f"Payment recorded: receipt {pay['receipt_no']} · ₹{pay['amount']:,.2f}")
    await db.fee_issues.update_one({"id": iss_id}, {"$push": {"messages": m}, "$set": {
        "status": "resolved", "resolved_by": m["by_name"], "resolved_at": now_iso(), "updated_at": now_iso(), "payment_id": pay["id"]}})
    await _fee_parent_notify(user["institution_id"], i["student_id"], f"Payment verified: {i.get('student_name')}",
                             f"₹{pay['amount']:,.2f} · receipt {pay['receipt_no']}", iss_id, actor=user)
    return {"issue": _issue_out(await db.fee_issues.find_one({"id": iss_id})), **res}


@api.get("/fees/issues/{iss_id}/messages/{mid}/file")
async def fee_issue_file(iss_id: str, mid: str, user: dict = Depends(get_current_user)):
    i = await db.fee_issues.find_one({"id": iss_id, "institution_id": user.get("institution_id")}, {"_id": 0})
    if not i:
        raise HTTPException(status_code=404, detail="Issue not found")
    await _fee_file_access(user, i)
    m = next((m for m in i.get("messages", []) if m["id"] == mid and m.get("file_path")), None)
    if not m:
        raise HTTPException(status_code=404, detail="No attachment")
    try:
        data, _ = _get_object(m["file_path"])
    except Exception:
        raise HTTPException(status_code=404, detail="File not available")
    return Response(content=data, media_type=m["file_type"], headers={"Cache-Control": "private, max-age=300"})


# ---- student fee statement ----
async def _statement_data(iid, sid, academic_year=None):
    stu = await db.students.find_one({"id": sid, "institution_id": iid}, {"_id": 0})
    if not stu:
        raise HTTPException(status_code=404, detail="Student not found")
    q = {"institution_id": iid, "student_id": sid, **({"academic_year": academic_year} if academic_year else {})}
    invs = await db.fee_invoices.find(q, {"_id": 0}).sort("due_date", 1).to_list(500)
    late = await _late_map({i["structure_id"] for i in invs if i.get("structure_id")})
    views = [_invoice_view(i, late.get(i.get("structure_id"))) for i in invs]
    pays = await db.fee_payments.find({"institution_id": iid, "invoice_id": {"$in": [i["id"] for i in invs]}},
                                      {"_id": 0, "items": 0}).sort([("paid_on", 1), ("collected_at", 1)]).to_list(2000)
    rows = [{"period_label": v["period_label"], "academic_year": v.get("academic_year"), "due_date": v.get("due_date"),
             "amount": _r2(float(v.get("subtotal") or 0) + v["fine_amount"]), "concession": _r2(v.get("discount_amount") or 0),
             "paid": v["paid_amount"], "balance": v["balance"], "status": v["status"]} for v in views]
    tot = {k: _r2(sum(r[k] for r in rows)) for k in ("amount", "concession", "paid", "balance")}
    live = [p for p in pays if not p.get("reversed")]
    inst = await db.institutions.find_one({"id": iid}, {"_id": 0, "name": 1, "address": 1, "phone": 1}) or {}
    return {"student": {"id": sid, "name": f"{stu.get('first_name', '')} {stu.get('last_name', '')}".strip(),
                        "admission_no": stu.get("admission_no"), "class_name": stu.get("class_name"), "section": stu.get("section"),
                        "guardian_name": stu.get("guardian_name")},
            "academic_year": academic_year or "All years", "invoices": rows, "totals": tot,
            "payments": [{"date": p.get("paid_on") or p["collected_at"][:10], "receipt_no": p["receipt_no"], "method": p["method"],
                          "reference": p.get("reference"), "amount": p["amount"], "reversed": bool(p.get("reversed")),
                          "credit_note_no": p.get("credit_note_no")} for p in pays],
            "payments_total": _r2(sum(p["amount"] for p in live)), "reversed_total": _r2(sum(p["amount"] for p in pays if p.get("reversed"))),
            "closing_balance": tot["balance"], "carried_forward": _r2(sum(float(i.get("carried_forward_amount") or 0) for i in invs if i.get("carried_forward_to"))),
            "generated_on": datetime.now(await _inst_tz(iid)).strftime("%Y-%m-%d %H:%M"), "school": inst}


def _statement_pdf(d, logo_bytes=None) -> bytes:
    import io
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
    R, B, I, money = _receipt_fonts()
    SZ = 8.5
    st = ParagraphStyle("s", fontName=R, fontSize=SZ, leading=SZ + 2.5)
    stR = ParagraphStyle("r", parent=st, alignment=2)
    h1 = ParagraphStyle("h1", fontName=B, fontSize=15, leading=18)
    h2 = ParagraphStyle("h2", fontName=B, fontSize=10, leading=13, spaceBefore=8, spaceAfter=4)
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=14 * mm, rightMargin=14 * mm, topMargin=12 * mm, bottomMargin=14 * mm,
                            title=f"Fee statement {d['student']['name']}")
    W = A4[0] - 28 * mm
    s, sch = d["student"], d["school"]
    head = [[Paragraph(sch.get("name") or "", h1), Paragraph("<b>FEE STATEMENT</b>", ParagraphStyle("t", parent=stR, fontName=B, fontSize=11))],
            [Paragraph(sch.get("address") or "", st), Paragraph(f"Academic year: {d['academic_year']}", stR)]]
    if logo_bytes:
        try:
            head[0].insert(0, Image(io.BytesIO(logo_bytes), 14 * mm, 14 * mm)); head[1].insert(0, "")
        except Exception:
            pass
    cols = [16 * mm, W - 16 * mm - 60 * mm, 60 * mm] if len(head[0]) == 3 else [W - 60 * mm, 60 * mm]
    ht = Table(head, colWidths=cols)
    ht.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LINEBELOW", (0, -1), (-1, -1), 0.8, colors.black),
                            ("BOTTOMPADDING", (0, -1), (-1, -1), 6)] + ([("SPAN", (0, 0), (0, 1))] if len(cols) == 3 else [])))
    info = Table([[Paragraph(f"Student: <b>{s['name']}</b>", st), Paragraph(f"Admission no.: {s.get('admission_no') or '—'}", st)],
                  [Paragraph(f"Class: {s.get('class_name') or ''} {s.get('section') or ''}", st), Paragraph(f"Guardian: {s.get('guardian_name') or '—'}", st)]],
                 colWidths=[W / 2, W / 2])
    base = [("FONTNAME", (0, 0), (-1, -1), R), ("FONTSIZE", (0, 0), (-1, -1), SZ), ("FONTNAME", (0, 0), (-1, 0), B),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef2f7")), ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]
    inv_rows = [["Period", "Due date", "Amount", "Concession", "Paid", "Balance", "Status"]]
    for r in d["invoices"]:
        inv_rows.append([r["period_label"], r.get("due_date") or "—", money(r["amount"]), money(-r["concession"]) if r["concession"] else money(0),
                         money(r["paid"]), money(r["balance"]), r["status"].replace("_", " ").title()])
    t = d["totals"]
    inv_rows.append(["Total", "", money(t["amount"]), money(-t["concession"]) if t["concession"] else money(0), money(t["paid"]), money(t["balance"]), ""])
    it = Table(inv_rows, colWidths=[W * x for x in (0.22, 0.12, 0.14, 0.14, 0.13, 0.13, 0.12)], repeatRows=1)
    it.setStyle(TableStyle(base + [("ALIGN", (2, 0), (5, -1), "RIGHT"), ("FONTNAME", (0, -1), (-1, -1), B),
                                   ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#f8fafc"))]))
    pay_rows = [["Date", "Receipt no.", "Method", "Reference", "Amount"]]
    for p in d["payments"]:
        amt = money(p["amount"])
        pay_rows.append([p["date"], p["receipt_no"] + (" (REVERSED)" if p["reversed"] else ""), p["method"].upper(), p.get("reference") or "—",
                         Paragraph(f"<strike>{amt}</strike>", stR) if p["reversed"] else amt])
    pay_rows.append(["Total received", "", "", "", money(d["payments_total"])])
    pt = Table(pay_rows, colWidths=[W * x for x in (0.14, 0.30, 0.12, 0.26, 0.18)], repeatRows=1)
    pt.setStyle(TableStyle(base + [("ALIGN", (4, 0), (4, -1), "RIGHT"), ("FONTNAME", (0, -1), (-1, -1), B),
                                   ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#f8fafc"))]
                           + [("TEXTCOLOR", (0, i), (3, i), colors.HexColor("#b91c1c")) for i, p in enumerate(d["payments"], 1) if p["reversed"]]))
    summ = Table([["Total billed (after concessions)", money(_r2(t["amount"] - t["concession"]))], ["Total paid", money(t["paid"])],
                  ["Closing balance", money(d["closing_balance"])]], colWidths=[W - 45 * mm, 45 * mm], hAlign="RIGHT")
    summ.setStyle(TableStyle([("FONTNAME", (0, 0), (-1, -1), R), ("FONTSIZE", (0, 0), (-1, -1), SZ), ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                              ("FONTNAME", (0, -1), (-1, -1), B), ("LINEABOVE", (0, -1), (-1, -1), 0.8, colors.black)]))
    story = [ht, Spacer(1, 4 * mm), info, Paragraph("Invoices", h2), it, Paragraph("Payments", h2), pt, Spacer(1, 4 * mm), summ]
    if d.get("reversed_total"):
        story.append(Paragraph(f"Reversed receipts (struck through) are excluded from totals: {money(d['reversed_total'])}.", st))
    if d.get("carried_forward"):
        story.append(Paragraph(f"Carried forward to the next academic year as Previous dues: {money(d['carried_forward'])}.", st))

    def foot(c, _doc):
        c.setFont(I, 7.5)
        c.drawString(14 * mm, 8 * mm, f"Generated on {d['generated_on']} · system-generated statement")
        c.drawRightString(A4[0] - 14 * mm, 8 * mm, f"Page {c.getPageNumber()}")
    doc.build(story, onFirstPage=foot, onLaterPages=foot)
    return buf.getvalue()


async def _statement_response(iid, sid, academic_year):
    d = await _statement_data(iid, sid, academic_year or None)
    logo = None
    inst = await db.institutions.find_one({"id": iid}, {"_id": 0, "logo_path": 1})
    if (inst or {}).get("logo_path"):
        try:
            logo, _ = _get_object(inst["logo_path"])
        except Exception:
            logo = None
    name = re.sub(r"[^A-Za-z0-9]+", "-", d["student"]["name"]).strip("-") or "student"
    return Response(content=_statement_pdf(d, logo), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="fee-statement-{name}.pdf"'})


async def _student_for_staff(user, sid):
    s = await db.students.find_one({"id": sid, "institution_id": user["institution_id"]}, {"_id": 0, "class_name": 1})
    if not s:
        raise HTTPException(status_code=404, detail="Student not found")
    await _require_collect_scope(user, s.get("class_name"))


@api.get("/fees/students/{sid}/statement")
async def fee_statement_json(sid: str, academic_year: str = "", user: dict = Depends(require_admin_or_principal)):
    await _student_for_staff(user, sid)
    return await _statement_data(user["institution_id"], sid, academic_year or None)


@api.get("/fees/students/{sid}/statement.pdf")
async def fee_statement_pdf(sid: str, academic_year: str = "", user: dict = Depends(require_admin_or_principal)):
    await _student_for_staff(user, sid)
    return await _statement_response(user["institution_id"], sid, academic_year)


@api.get("/parent/child/{sid}/fees/statement.pdf")
async def parent_fee_statement_pdf(sid: str, academic_year: str = "", user: dict = Depends(require_roles("parent"))):
    if sid not in (user.get("student_ids") or []):
        raise HTTPException(status_code=403, detail="This student is not linked to your account")
    return await _statement_response(user["institution_id"], sid, academic_year)


@app.on_event("startup")
async def _fees_51_setup():
    await db.fee_payment_proofs.create_index("invoice_id", unique=True, name="one_pending_proof_per_invoice",
                                             partialFilterExpression={"status": "pending"})
    await db.fee_payment_proofs.create_index([("institution_id", 1), ("status", 1), ("submitted_at", -1)])
    await db.fee_issues.create_index([("institution_id", 1), ("status", 1), ("updated_at", -1)])
    await db.fee_payments.create_index([("institution_id", 1), ("paid_on", 1)])
    tzs = {}  # additive backfill: payment date in the institution timezone (collected_at itself is never modified)
    async for p in db.fee_payments.find({"paid_on": {"$exists": False}}, {"_id": 0, "id": 1, "institution_id": 1, "collected_at": 1}):
        if p["institution_id"] not in tzs:
            tzs[p["institution_id"]] = await _inst_tz(p["institution_id"])
        local = datetime.fromisoformat(p["collected_at"]).astimezone(tzs[p["institution_id"]]).date().isoformat()
        await db.fee_payments.update_one({"id": p["id"], "paid_on": {"$exists": False}},
                                         {"$set": {"paid_on": local, "recorded_at": p["collected_at"], "backdated": False, "paid_on_backfilled": True}})


@app.on_event("startup")
async def _fees_c_indexes():
    await db.fee_invoices.create_index("arrears_key", unique=True, partialFilterExpression={"arrears_key": {"$exists": True}})
    await db.fee_invoices.create_index([("institution_id", 1), ("student_id", 1), ("status", 1)])
    await db.fee_reminders.create_index([("institution_id", 1), ("student_id", 1), ("at", -1)])


@app.on_event("startup")
async def _fees_indexes():
    await db.fee_invoices.create_index([("account_id", 1), ("frequency", 1), ("period_label", 1)], unique=True)
    await db.fee_payments.create_index([("institution_id", 1), ("receipt_no", 1)], unique=True)
    await db.fee_accounts.create_index([("structure_id", 1), ("student_id", 1)], unique=True)
    await db.fee_counters.create_index([("institution_id", 1), ("year", 1)], unique=True)
    await db.comm_templates.update_one(  # migrate the untouched seeded body to include {{due_date}}
        {"institution_id": None, "name": "Fee Reminder",
         "body": "Dear {{parent_name}}, a fee of {{amount}} is due for {{student_name}}. Details: {{secure_link}} — {{school_name}}"},
        {"$set": {"body": "Dear {{parent_name}}, a fee of {{amount}} for {{student_name}} is due on {{due_date}}. View: {{secure_link}} — {{school_name}}"}})
    asyncio.create_task(_fee_reminder_loop())


# ---------------- Phase 56: Platform Manager institution console ----------------
RESET_TTL_HOURS = 24
PW_RULE = "Use at least 8 characters with an uppercase letter, a lowercase letter and a number."
SUPPORT_FROM = "LNMO Support"
INST_STATUSES = ("active", "suspended", "inactive")


def _pw_strong(p: str) -> bool:
    return 8 <= len(p or "") <= 128 and bool(re.search(r"[A-Z]", p) and re.search(r"[a-z]", p) and re.search(r"\d", p))


def _iso_days_ago(n: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=n)).isoformat()


def _month_start() -> str:
    return datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()


def _support_contact() -> str:
    return os.environ.get("SUPPORT_EMAIL") or os.environ.get("PLATFORM_ADMIN_EMAIL") or "LNMO Support"


async def _plat_inst(iid: str) -> dict:
    inst = await db.institutions.find_one({"id": iid}, {"_id": 0})
    if not inst:
        raise HTTPException(status_code=404, detail="Institution not found")
    return inst


async def _plan_info(inst: dict) -> dict:
    plan = await db.plans.find_one({"id": inst["plan_id"]}, {"_id": 0}) if inst.get("plan_id") else None
    ov = inst.get("plan_overrides") or {}
    q = (inst.get("comm") or {}).get("quota") or {}
    return {
        "plan": plan, "overrides": ov, "status": inst.get("status") or "active", "expires_at": inst.get("plan_expires_at"),
        "limits": {"students": ov.get("max_students") or (plan or {}).get("max_students"),
                   "whatsapp": (q.get("whatsapp") or {}).get("limit"), "sms": (q.get("sms") or {}).get("limit"),
                   "ai_messages_month": ov.get("ai_messages_month")},
        "quota_used": {"whatsapp": (q.get("whatsapp") or {}).get("used", 0), "sms": (q.get("sms") or {}).get("used", 0)},
        "cycle_start": (inst.get("comm") or {}).get("cycle_start"),
    }


async def _logins_by_day(match: dict, days: int = 30) -> list:
    rows = await db.audit_logs.aggregate([
        {"$match": {**match, "action": "login", "timestamp": {"$gte": _iso_days_ago(days)}}},
        {"$group": {"_id": {"$substr": ["$timestamp", 0, 10]}, "n": {"$sum": 1}, "u": {"$addToSet": "$actor_email"}}},
    ]).to_list(400)
    by = {r["_id"]: r for r in rows}
    out = []
    for i in range(days - 1, -1, -1):
        d = (datetime.now(timezone.utc) - timedelta(days=i)).date().isoformat()
        out.append({"date": d, "logins": by.get(d, {}).get("n", 0), "users": len(by.get(d, {}).get("u", []))})
    return out


async def _active_users(match: dict, days: int) -> int:
    return len(await db.audit_logs.distinct("actor_email", {**match, "action": "login", "timestamp": {"$gte": _iso_days_ago(days)},
                                                           "actor_role": {"$ne": "platform_admin"}}))


@api.get("/platform/summary")
async def platform_summary(user: dict = Depends(require_roles("platform_admin"))):
    ms = _month_start()
    return {
        "schools": await db.institutions.count_documents({}),
        "active_schools": await db.institutions.count_documents({"status": {"$in": ["active", None]}}),
        "students": await db.students.count_documents({}),
        "teachers": await db.users.count_documents({"role": "teacher"}),
        "active_users_7d": await _active_users({}, 7),
        "open_issues": await db.issues.count_documents({"status": "open"}),
        "messages_month": await db.messages.count_documents({"created_at": {"$gte": ms}}),
        "logins_trend": await _logins_by_day({"actor_role": {"$ne": "platform_admin"}}, 30),
        "recent_activity": await db.audit_logs.find({}, {"_id": 0}).sort("timestamp", -1).to_list(6),
    }


@api.get("/platform/institutions-list")
async def platform_institutions_list(user: dict = Depends(require_roles("platform_admin"))):
    plans = {p["id"]: p for p in await db.plans.find({}, {"_id": 0}).to_list(100)}
    stu = {r["_id"]: r["n"] for r in await db.students.aggregate([{"$group": {"_id": "$institution_id", "n": {"$sum": 1}}}]).to_list(1000)}
    tch = {r["_id"]: r["n"] for r in await db.users.aggregate([{"$match": {"role": "teacher"}}, {"$group": {"_id": "$institution_id", "n": {"$sum": 1}}}]).to_list(1000)}
    out = []
    async for i in db.institutions.find({}, {"_id": 0}):
        p = plans.get(i.get("plan_id")) or {}
        out.append({"id": i["id"], "name": i.get("name"), "code": i.get("code"), "city": i.get("city"), "domain": i.get("domain"),
                    "status": i.get("status") or "active", "plan_id": i.get("plan_id"), "plan_name": p.get("name"),
                    "students": stu.get(i["id"], 0), "teachers": tch.get(i["id"], 0), "created_at": i.get("created_at"),
                    "logo_url": _login_branding(i)["logo_url"], "is_demo": bool(i.get("is_demo"))})
    return {"items": out, "plans": [{"id": p["id"], "name": p.get("name")} for p in plans.values()]}


@api.get("/platform/institutions/{iid}/overview")
async def platform_inst_overview(iid: str, user: dict = Depends(require_roles("platform_admin"))):
    inst = await _plat_inst(iid)

    async def cnt(col, q=None):
        return await db[col].count_documents({"institution_id": iid, **(q or {})})
    ay = await db.academic_years.find_one({"institution_id": iid, "status": "active"}, {"_id": 0, "name": 1, "start_date": 1, "end_date": 1}) \
        or await db.academic_years.find_one({"institution_id": iid}, {"_id": 0, "name": 1, "start_date": 1, "end_date": 1}, sort=[("start_date", -1)])
    units = await db.academic_units.find({"institution_id": iid}, {"_id": 0, "name": 1, "code": 1}).to_list(50)
    counts = {c: await cnt(c) for c in ("classes", "sections", "subjects", "students", "fee_structures", "timetable_entries", "teacher_assignments")}
    counts["teachers"] = await cnt("users", {"role": "teacher"})
    counts["parents"] = await cnt("users", {"role": "parent"})
    steps = [("School profile (contact email + phone)", bool(inst.get("contact_email") and inst.get("phone"))),
             ("Academic configuration", bool(await db.academic_configuration.find_one({"institution_id": iid}, {"_id": 1}))),
             ("Academic year", bool(ay)), ("Divisions", bool(units)), ("Classes", counts["classes"] > 0),
             ("Sections", counts["sections"] > 0), ("Subjects", counts["subjects"] > 0), ("Teachers", counts["teachers"] > 0),
             ("Teacher assignments", counts["teacher_assignments"] > 0), ("Students", counts["students"] > 0),
             ("Fee structures", counts["fee_structures"] > 0), ("Timetable", counts["timetable_entries"] > 0)]
    plan = await _plan_info(inst)
    return {
        "institution": {k: inst.get(k) for k in ("id", "name", "code", "slug", "domain", "city", "address", "contact_email", "phone",
                                                 "created_at", "is_demo", "portal_name")},
        "branding": _login_branding(inst), "status": plan["status"],
        "plan": {"id": (plan["plan"] or {}).get("id"), "name": (plan["plan"] or {}).get("name"), "expires_at": plan["expires_at"]},
        "academic_year": ay, "divisions": units, "counts": counts,
        "login_key": inst.get("slug") or (inst.get("code") or "").lower() or inst.get("domain"),
        "setup": {"steps": [{"label": a, "done": b} for a, b in steps], "done": sum(1 for _, b in steps if b), "total": len(steps)},
    }


@api.get("/platform/institutions/{iid}/analytics")
async def platform_inst_analytics(iid: str, user: dict = Depends(require_roles("platform_admin"))):
    inst = await _plat_inst(iid)
    ms, m = _month_start(), {"institution_id": iid}
    roles = {r["_id"]: r["n"] for r in await db.users.aggregate([{"$match": m}, {"$group": {"_id": "$role", "n": {"$sum": 1}}}]).to_list(20)}
    pay = await db.fee_payments.aggregate([{"$match": {**m, "reversed": {"$ne": True}, "recorded_at": {"$gte": ms}}},
                                           {"$group": {"_id": None, "n": {"$sum": 1}, "amt": {"$sum": "$amount"}}}]).to_list(1)
    msgs = await db.messages.aggregate([{"$match": {**m, "created_at": {"$gte": ms}}},
                                        {"$group": {"_id": {"c": "$channel", "s": "$status"}, "n": {"$sum": 1}}}]).to_list(50)
    by_ch: dict = {}
    for r in msgs:
        ch = by_ch.setdefault(r["_id"].get("c") or "other", {"total": 0, "by_status": {}})
        ch["total"] += r["n"]
        ch["by_status"][r["_id"].get("s") or "unknown"] = r["n"]
    plan = await _plan_info(inst)
    provider = ((await db.platform_config.find_one({"id": "singleton"}, {"_id": 0, "active_provider": 1})) or {}).get("active_provider", "stub")
    return {
        "people": {"students": await db.students.count_documents(m), "teachers": roles.get("teacher", 0),
                   "parents": roles.get("parent", 0), "admins": roles.get("institution_admin", 0), "student_logins": roles.get("student", 0)},
        "active_users": {"d7": await _active_users(m, 7), "d30": await _active_users(m, 30)},
        "logins_trend": await _logins_by_day(m, 30),
        "modules": {
            "attendance_days_month": len(await db.attendance.distinct("date", {**m, "date": {"$gte": ms[:10]}})),
            "attendance_registers_month": await db.attendance.count_documents({**m, "date": {"$gte": ms[:10]}}),
            "homework_month": await db.homework.count_documents({**m, "created_at": {"$gte": ms}}),
            "homework_total": await db.homework.count_documents(m),
            "exams_published": await db.exams.count_documents({**m, "published_at": {"$nin": [None, ""]}}),
            "exams_total": await db.exams.count_documents(m),
            "fee_collections_month": {"count": pay[0]["n"] if pay else 0, "amount": pay[0]["amt"] if pay else 0},
            "ai_tutor_questions_month": await db.tutor_messages.count_documents({**m, "role": "user", "created_at": {"$gte": ms}}),
            "ai_tutor_students_month": len(await db.tutor_messages.distinct("student_id", {**m, "role": "user", "created_at": {"$gte": ms}})),
            "ai_tokens": None,
            "storage_bytes": None,
        },
        "messages": {"month": by_ch, "quota_limits": {"whatsapp": plan["limits"]["whatsapp"], "sms": plan["limits"]["sms"]},
                     "quota_used": plan["quota_used"], "cycle_start": plan["cycle_start"], "provider": provider},
        "not_tracked": ["ai_tokens", "storage_bytes"],
    }


@api.get("/platform/institutions/{iid}/plan")
async def platform_inst_plan(iid: str, user: dict = Depends(require_roles("platform_admin"))):
    inst = await _plat_inst(iid)
    info = await _plan_info(inst)
    ms = _month_start()
    info["usage"] = {"students": await db.students.count_documents({"institution_id": iid}), **info.pop("quota_used"),
                     "ai_messages_month": await db.tutor_messages.count_documents({"institution_id": iid, "role": "user", "created_at": {"$gte": ms}})}
    info["plans"] = await db.plans.find({}, {"_id": 0}).to_list(100)
    return info


class PlanUpdate(BaseModel):
    plan_id: Optional[str] = None
    max_students: Optional[int] = PField(None, ge=0)
    whatsapp_limit: Optional[int] = PField(None, ge=0)
    sms_limit: Optional[int] = PField(None, ge=0)
    ai_messages_month: Optional[int] = PField(None, ge=0)
    status: Optional[Literal["active", "suspended", "inactive"]] = None
    expires_at: Optional[str] = None


@api.put("/platform/institutions/{iid}/plan")
async def platform_inst_plan_update(iid: str, body: PlanUpdate, user: dict = Depends(require_roles("platform_admin"))):
    inst = await _plat_inst(iid)
    if body.plan_id and not await db.plans.find_one({"id": body.plan_id}, {"_id": 1}):
        raise HTTPException(status_code=400, detail="Unknown plan")
    if body.expires_at:
        try:
            datetime.fromisoformat(body.expires_at[:10])
        except ValueError:
            raise HTTPException(status_code=400, detail="Expiry must be a date (YYYY-MM-DD)")
    sets = {"plan_id": body.plan_id or None, "plan_expires_at": (body.expires_at or "")[:10] or None,
            "plan_overrides": {"max_students": body.max_students, "ai_messages_month": body.ai_messages_month}}
    if body.status:
        sets["status"] = body.status
    q = (inst.get("comm") or {}).get("quota") or {}
    for ch, v in (("whatsapp", body.whatsapp_limit), ("sms", body.sms_limit)):
        if v is not None:
            sets[f"comm.quota.{ch}.limit"] = v
            sets.setdefault(f"comm.quota.{ch}.used", (q.get(ch) or {}).get("used", 0))
    await db.institutions.update_one({"id": iid}, {"$set": sets})
    plan = await db.plans.find_one({"id": body.plan_id}, {"_id": 0, "name": 1}) if body.plan_id else None
    await audit(user, "platform_plan_update", "institutions", iid,
                f"{inst.get('name')} · plan={(plan or {}).get('name') or 'none'} · status={body.status or inst.get('status')} · "
                f"expires={sets['plan_expires_at'] or '—'} · students={body.max_students or 'plan'} · wa={body.whatsapp_limit} · "
                f"sms={body.sms_limit} · ai={body.ai_messages_month}", institution_id=iid)
    return await platform_inst_plan(iid, user)


async def _inst_admin(iid: str, uid: str) -> dict:
    u = await db.users.find_one({"id": uid, "institution_id": iid, "role": "institution_admin"}, {"_id": 0, "password_hash": 0})
    if not u:
        raise HTTPException(status_code=404, detail="School admin not found")
    return u


@api.get("/platform/institutions/{iid}/admins")
async def platform_inst_admins(iid: str, user: dict = Depends(require_roles("platform_admin"))):
    await _plat_inst(iid)
    out = []
    async for u in db.users.find({"institution_id": iid, "role": "institution_admin"}, {"_id": 0, "password_hash": 0}).sort("name", 1):
        last = await db.audit_logs.find_one({"actor_email": u.get("email"), "action": "login"}, {"_id": 0, "timestamp": 1}, sort=[("timestamp", -1)])
        reset = await db.password_resets.find_one({"user_id": u["id"], "used_at": None, "invalidated_at": None,
                                                   "expires_at": {"$gt": now_iso()}}, {"_id": 0, "expires_at": 1, "created_at": 1})
        out.append({"id": u["id"], "name": u.get("name"), "email": u.get("email"), "status": u.get("status") or "active",
                    "created_at": u.get("created_at"), "last_login": (last or {}).get("timestamp"),
                    "lock": await _active_lock(await _account_lock_keys(u)), "pending_reset": reset})
    return {"admins": out}


async def _support_send(to: str, subject: str, html: str) -> str | None:
    """LNMO Support email; retries briefly (2s, 6s) when the provider throttles us."""
    for delay in (2, 6, None):
        try:
            return await send_email(to=to, subject=subject, html=html, from_name=SUPPORT_FROM)
        except EmailSendError as e:
            if e.reason != "rate_limited" or delay is None:
                raise
            await asyncio.sleep(delay)


EMAIL_ERR_COPY = {"rate_limited": "the email provider is throttling us, try again in a minute",
                  "undeliverable": "the address can't receive email", "email_not_configured": "email isn't configured",
                  "provider_error": "the email provider returned an error"}


def _support_email_html(title: str, lines: list, cta: tuple | None = None) -> str:
    body = "".join(f'<p style="margin:0 0 12px">{x}</p>' for x in lines)
    btn = (f'<p style="margin:20px 0"><a href="{_html_escape(cta[1])}" style="background:#4338ca;color:#fff;padding:12px 20px;'
           f'border-radius:8px;text-decoration:none;font-weight:bold">{_html_escape(cta[0])}</a></p>'
           f'<p style="font-size:12px;color:#666;word-break:break-all">Or paste this link into your browser: {_html_escape(cta[1])}</p>') if cta else ""
    return (f'<table role="presentation" width="100%"><tr><td style="padding:24px;font-family:Arial,sans-serif;color:#111;font-size:14px;line-height:1.5">'
            f'<h2 style="margin:0 0 16px;font-size:18px">{_html_escape(title)}</h2>{body}{btn}'
            f'<p style="font-size:12px;color:#888;margin-top:24px">Sent by {SUPPORT_FROM}. Questions? Contact {_html_escape(_support_contact())}.</p>'
            f'</td></tr></table>')


@api.post("/platform/institutions/{iid}/admins/{uid}/password-reset")
async def platform_admin_password_reset(iid: str, uid: str, user: dict = Depends(require_roles("platform_admin"))):
    inst = await _plat_inst(iid)
    target = await _inst_admin(iid, uid)
    base = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")
    if not base.startswith("https://"):
        raise HTTPException(status_code=500, detail="PUBLIC_BASE_URL is not configured — can't build the reset link")
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    await db.password_resets.update_many({"user_id": uid, "used_at": None, "invalidated_at": None}, {"$set": {"invalidated_at": now.isoformat()}})
    doc = {"id": str(uuid.uuid4()), "user_id": uid, "institution_id": iid, "token_hash": hashlib.sha256(token.encode()).hexdigest(),
           "created_at": now.isoformat(), "expires_at": (now + timedelta(hours=RESET_TTL_HOURS)).isoformat(),
           "created_by": user.get("email"), "used_at": None, "invalidated_at": None, "message_id": None}
    await db.password_resets.insert_one(doc)
    link = f"{base}/reset-password/{token}"
    html = _support_email_html("Reset your LNMO password", [
        f"Hello {_html_escape(target.get('name') or '')},",
        f"LNMO Support has sent you a link to set a new password for your {_html_escape(inst.get('name') or '')} admin account "
        f"({_html_escape(target['email'])}).",
        f"The link works once and expires in {RESET_TTL_HOURS} hours. Setting a new password signs you out on all devices.",
        "If you didn't expect this, you can ignore this email — your current password keeps working."], ("Set a new password", link))
    try:
        mid = await _support_send(target["email"], "Reset your LNMO password", html)
    except EmailSendError as e:
        mid, err = None, e.reason
    else:
        err = None if mid else "email_not_configured"
    if not mid:
        await db.password_resets.update_one({"id": doc["id"]}, {"$set": {"invalidated_at": now_iso(), "send_error": err}})
        await audit(user, "password_reset_email_failed", "users", uid, f"{target['email']} · {err}", institution_id=iid)
        raise HTTPException(status_code=502, detail=f"The reset email could not be sent: {EMAIL_ERR_COPY.get(err, err)}. No link is active — nothing was sent.")
    await db.password_resets.update_one({"id": doc["id"]}, {"$set": {"message_id": mid}})
    await audit(user, "password_reset_sent", "users", uid, f"{target['email']} · message {mid}", institution_id=iid)
    return {"ok": True, "sent_to": target["email"], "message_id": mid, "expires_at": doc["expires_at"]}


class EmailChange(BaseModel):
    email: EmailStr


@api.post("/platform/institutions/{iid}/admins/{uid}/email")
async def platform_admin_change_email(iid: str, uid: str, body: EmailChange, user: dict = Depends(require_roles("platform_admin"))):
    await _plat_inst(iid)
    target = await _inst_admin(iid, uid)
    old, new = (target.get("email") or "").lower(), str(body.email).strip().lower()
    if new == old:
        raise HTTPException(status_code=400, detail="That's already the login email")
    if await db.users.find_one({"email": new}, {"_id": 1}):
        raise HTTPException(status_code=409, detail="That email is already used by another account")
    try:
        await db.users.update_one({"id": uid}, {"$set": {"email": new, "email_changed_at": now_iso()}})
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail="That email is already used by another account")
    await db.login_attempts.delete_many({"identifier": old})
    html = _support_email_html("Your LNMO login email was changed", [
        f"Your LNMO login email was changed from <b>{_html_escape(old)}</b> to <b>{_html_escape(new)}</b> by LNMO Support.",
        "Use the new address to sign in from now on. Your password hasn't changed.",
        f"If this wasn't expected, contact {_html_escape(_support_contact())} straight away."])
    results = {}
    for addr in dict.fromkeys([old, new]):
        try:
            mid = await _support_send(addr, "Your LNMO login email was changed", html)
            results[addr] = {"message_id": mid} if mid else {"error": "email_not_configured"}
        except EmailSendError as e:
            results[addr] = {"error": e.reason}
    await audit(user, "admin_email_change", "users", uid,
                f"{old} → {new} · " + ", ".join(f"{a}: {r.get('message_id') or r.get('error')}" for a, r in results.items()), institution_id=iid)
    return {"ok": True, "email": new, "notifications": results}


@api.get("/platform/institutions/{iid}/activity")
async def platform_inst_activity(iid: str, platform_only: bool = False, limit: int = 50,
                                 user: dict = Depends(require_roles("platform_admin"))):
    await _plat_inst(iid)
    q: dict = {"$or": [{"institution_id": iid}, {"entity_id": iid}]}
    if platform_only:
        q["actor_role"] = "platform_admin"
    items = await db.audit_logs.find(q, {"_id": 0}).sort("timestamp", -1).to_list(min(max(limit, 1), 200))
    return {"items": items}


async def _reset_doc(token: str, consume: bool = False):
    h = hashlib.sha256((token or "").encode()).hexdigest()
    if consume:
        d = await db.password_resets.find_one_and_update(
            {"token_hash": h, "used_at": None, "invalidated_at": None, "expires_at": {"$gt": now_iso()}},
            {"$set": {"used_at": now_iso()}}, return_document=True)
        if d:
            return d
    d = await db.password_resets.find_one({"token_hash": h}, {"_id": 0})
    if not d or d.get("invalidated_at"):
        raise HTTPException(status_code=410, detail="This reset link is no longer valid. Ask LNMO Support to send a new one.")
    if d.get("used_at"):
        raise HTTPException(status_code=410, detail="This reset link has already been used. Ask LNMO Support for a new one if you still need it.")
    if d["expires_at"] <= now_iso():
        raise HTTPException(status_code=410, detail="This reset link has expired (links last 24 hours). Ask LNMO Support for a new one.")
    if consume:
        raise HTTPException(status_code=410, detail="This reset link is no longer valid.")
    return d


@api.get("/public/password-reset/{token}")
async def public_password_reset_info(token: str):
    d = await _reset_doc(token)
    u = await db.users.find_one({"id": d["user_id"]}, {"_id": 0, "name": 1, "email": 1})
    inst = await db.institutions.find_one({"id": d["institution_id"]}, {"_id": 0}) or {}
    em = (u or {}).get("email") or ""
    masked = (em[:2] + "•••" + em[em.find("@"):]) if "@" in em else ""
    b = _login_branding(inst) if inst else {}
    return {"name": ((u or {}).get("name") or "").split(" ")[0], "email_masked": masked, "expires_at": d["expires_at"],
            "school": {"name": b.get("name"), "logo_url": b.get("logo_url"), "primary_color": inst.get("primary_color")},
            "login_key": inst.get("slug") or (inst.get("code") or "").lower() or inst.get("domain"), "rule": PW_RULE}


class ResetBody(BaseModel):
    password: str


@api.post("/public/password-reset/{token}")
async def public_password_reset(token: str, body: ResetBody):
    if not _pw_strong(body.password):
        await _reset_doc(token)  # surface link errors first
        raise HTTPException(status_code=400, detail=PW_RULE)
    d = await _reset_doc(token, consume=True)
    u = await db.users.find_one({"id": d["user_id"]})
    if not u:
        raise HTTPException(status_code=410, detail="This reset link is no longer valid.")
    await db.users.update_one({"id": u["id"]}, {"$set": {"password_hash": hash_password(body.password), "must_change_password": False,
                                                         "password_changed_at": now_iso()}, "$inc": {"tv": 1}, "$unset": {"pw_set_by_staff": ""}})
    await db.login_attempts.delete_many({"identifier": {"$in": await _account_lock_keys(u)}})
    await db.password_resets.update_many({"user_id": u["id"], "used_at": None, "invalidated_at": None}, {"$set": {"invalidated_at": now_iso()}})
    await audit(u, "password_reset_completed", "users", u["id"], u.get("email"), institution_id=u.get("institution_id"))
    inst = await db.institutions.find_one({"id": u.get("institution_id")}, {"_id": 0, "slug": 1, "code": 1, "domain": 1}) or {}
    return {"ok": True, "login_key": inst.get("slug") or (inst.get("code") or "").lower() or inst.get("domain")}


# ---------------- Phase 57: production factory reset (platform manager, preview-blocked) ----------------
import data_reset as _dr  # noqa: E402

PREVIEW_DB_NAME = "test_database"  # the preview environment's DB_NAME at build time; production uses a different name
RESET_PHRASE = "RESET PRODUCTION"
RESET_WINDOW_MIN = 10
RESET_BLOCKED_HOSTS = ("preview.emergentagent.com", "localhost", "127.0.0.1")
_reset_tasks: dict = {}


def reset_guard(request: Request) -> dict:
    """Refuses on preview hosts or the preview database. Tests override this dependency explicitly."""
    hosts = [(request.headers.get(h) or "").lower() for h in ("host", "x-forwarded-host", "origin", "referer")]
    db_name = os.environ.get("DB_NAME", "")
    if any(b in h for h in hosts for b in RESET_BLOCKED_HOSTS) or db_name == PREVIEW_DB_NAME:
        raise HTTPException(status_code=409, detail="Reset is disabled on preview")
    return {"host": hosts[0], "db": db_name}


def _plan_public(plan):
    return [{k: v for k, v in p.items() if k != "filter"} for p in plan]


async def _reset_last_job():
    return await db.platform_events.find_one({"type": "reset_job"}, {"_id": 0}, sort=[("started_at", -1)])


@api.get("/platform/reset/preview")
async def reset_preview(env: dict = Depends(reset_guard), user: dict = Depends(require_roles("platform_admin"))):
    plan = await _dr.build_plan(db)
    last = await db.platform_events.find_one({"type": "reset_job", "status": "completed"}, {"_id": 0}, sort=[("finished_at", -1)])
    nxt = (datetime.fromisoformat(last["finished_at"]) + timedelta(hours=1)).isoformat() if last else None
    return {"db": env["db"], "host": env["host"], "phrase": RESET_PHRASE, "plan": _plan_public(plan),
            "totals": {"delete": sum(p["delete"] for p in plan), "keep": sum(p["total"] - p["delete"] for p in plan)},
            "unclassified": [p["collection"] for p in plan if p["action"] == "unclassified"],
            "last_job": await _reset_last_job(), "next_allowed_at": nxt if nxt and nxt > now_iso() else None}


@api.post("/platform/reset/backup")
async def reset_backup(env: dict = Depends(reset_guard), user: dict = Depends(require_roles("platform_admin"))):
    plan = await _dr.build_plan(db)
    blob, counts, paths = await _dr.build_backup(db, plan)
    bid = str(uuid.uuid4())
    path = f"lnmo/resets/{bid}.json.gz"
    try:
        await asyncio.to_thread(_put_object, path, blob, "application/gzip")
    except Exception as e:
        logger.error("reset backup upload failed: %s", e)
        raise HTTPException(status_code=502, detail="Backup could not be stored — nothing was deleted. Try again.")
    doc = {"type": "reset_backup", "id": bid, "path": path, "size": len(blob), "counts": counts, "storage_refs": len(paths),
           "db": env["db"], "created_by": user["id"], "created_by_email": user.get("email"), "created_at": now_iso(), "used": False}
    await db.platform_events.insert_one(dict(doc))
    doc.pop("_id", None)
    return {**doc, "download_url": f"/api/platform/reset/backups/{bid}/download",
            "valid_until": (datetime.now(timezone.utc) + timedelta(minutes=RESET_WINDOW_MIN)).isoformat()}


@api.get("/platform/reset/backups/{bid}/download")
async def reset_backup_download(bid: str, user: dict = Depends(require_roles("platform_admin"))):
    b = await db.platform_events.find_one({"type": "reset_backup", "id": bid}, {"_id": 0})
    if not b:
        raise HTTPException(status_code=404, detail="Backup not found")
    data, _ = await asyncio.to_thread(_get_object, b["path"])
    return Response(content=data, media_type="application/gzip",
                    headers={"Content-Disposition": f'attachment; filename="lnmo-backup-{b["created_at"][:10]}-{bid[:8]}.json.gz"'})


class ResetRun(BaseModel):
    password: str
    phrase: str
    backup_id: str


async def _reset_job(job_id: str):
    job = await db.platform_events.find_one({"type": "reset_job", "id": job_id})
    try:
        if not job.get("final_backup_id"):
            await db.platform_events.update_one({"id": job_id}, {"$set": {"stage": "backup", "heartbeat": now_iso()}})
            plan = await _dr.build_plan(db)
            blob, counts, paths = await _dr.build_backup(db, plan)
            fid = str(uuid.uuid4())
            await asyncio.to_thread(_put_object, f"lnmo/resets/{fid}.json.gz", blob, "application/gzip")
            await db.platform_events.insert_one({"type": "reset_backup", "id": fid, "path": f"lnmo/resets/{fid}.json.gz", "size": len(blob),
                                                 "counts": counts, "storage_refs": len(paths), "final_for_job": job_id,
                                                 "created_by": job["started_by"], "created_at": now_iso(), "used": True})
            await db.platform_events.update_one({"id": job_id}, {"$set": {"final_backup_id": fid, "storage_orphans": len(paths)}})
        plan = await _dr.build_plan(db)
        await db.platform_events.update_one({"id": job_id}, {"$set": {"stage": "deleting", "total_steps": len(plan)}})
        for p in plan:
            key = f"steps.{p['collection']}"
            if p["delete"]:
                n = await _dr.delete_step(db, p)
                await db.platform_events.update_one({"id": job_id}, {"$inc": {f"{key}.deleted": n}, "$set": {
                    f"{key}.action": p["action"], f"{key}.done": True, "heartbeat": now_iso()}})
            else:
                await db.platform_events.update_one({"id": job_id}, {"$set": {f"{key}.action": p["action"], f"{key}.done": True}})
        final = await db.platform_events.find_one({"id": job_id}, {"_id": 0})
        deleted = {c: s.get("deleted", 0) for c, s in (final.get("steps") or {}).items() if s.get("deleted")}
        await db.platform_events.update_one({"id": job_id}, {"$set": {"status": "completed", "stage": "done", "finished_at": now_iso(),
                                                                     "deleted_counts": deleted, "deleted_total": sum(deleted.values())}})
        await db.platform_events.insert_one({"type": "reset_completed", "id": str(uuid.uuid4()), "job_id": job_id, "by": final["started_by_email"],
                                             "at": now_iso(), "deleted_counts": deleted, "backup_id": final.get("backup_id"),
                                             "final_backup_id": final.get("final_backup_id"), "storage_orphans": final.get("storage_orphans", 0)})
        logger.warning("FACTORY RESET completed by %s: %s docs deleted", final["started_by_email"], sum(deleted.values()))
    except Exception as e:
        logger.exception("factory reset job %s failed", job_id)
        await db.platform_events.update_one({"id": job_id}, {"$set": {"status": "failed", "error": str(e)[:300], "failed_at": now_iso()}})
    finally:
        _reset_tasks.pop(job_id, None)


@api.post("/platform/reset/run", status_code=202)
async def reset_run(body: ResetRun, env: dict = Depends(reset_guard), user: dict = Depends(require_roles("platform_admin"))):
    if body.phrase.strip() != RESET_PHRASE:
        raise HTTPException(status_code=400, detail=f'Type the exact phrase "{RESET_PHRASE}"')
    fresh = await db.users.find_one({"id": user["id"]})
    if not fresh or not verify_password(body.password, fresh["password_hash"]):
        raise HTTPException(status_code=403, detail="Password is incorrect")
    last = await _reset_last_job()
    if last and last.get("status") in ("running", "failed"):  # resume an interrupted job
        stale_cut = (datetime.now(timezone.utc) - timedelta(seconds=90)).isoformat()
        if last["id"] in _reset_tasks or (last.get("status") == "running" and last.get("heartbeat", "") > stale_cut):
            raise HTTPException(status_code=409, detail="A reset is already running")
        await db.platform_events.update_one({"id": last["id"]}, {"$set": {"status": "running", "resumed_at": now_iso(), "heartbeat": now_iso()},
                                                                 "$inc": {"resume_count": 1}})
        _reset_tasks[last["id"]] = asyncio.create_task(_reset_job(last["id"]))
        return {"job_id": last["id"], "resumed": True}
    done = await db.platform_events.find_one({"type": "reset_job", "status": "completed",
                                              "finished_at": {"$gt": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()}}, {"_id": 0})
    if done:
        raise HTTPException(status_code=429, detail="Only one reset per hour — try again later")
    since = (datetime.now(timezone.utc) - timedelta(minutes=RESET_WINDOW_MIN)).isoformat()
    b = await db.platform_events.find_one_and_update(
        {"type": "reset_backup", "id": body.backup_id, "created_by": user["id"], "used": False, "created_at": {"$gt": since}},
        {"$set": {"used": True, "used_at": now_iso()}})
    if not b:
        raise HTTPException(status_code=400, detail=f"Create a fresh backup first — a backup can be used once, within {RESET_WINDOW_MIN} minutes")
    job = {"type": "reset_job", "id": str(uuid.uuid4()), "status": "running", "stage": "queued", "started_by": user["id"],
           "started_by_email": user.get("email"), "started_at": now_iso(), "heartbeat": now_iso(), "backup_id": body.backup_id,
           "db": env["db"], "host": env["host"], "steps": {}}
    await db.platform_events.insert_one(dict(job))
    _reset_tasks[job["id"]] = asyncio.create_task(_reset_job(job["id"]))
    return {"job_id": job["id"], "resumed": False}


@api.get("/platform/reset/status")
async def reset_status(user: dict = Depends(require_roles("platform_admin"))):
    return {"job": await _reset_last_job(),
            "completed": await db.platform_events.find({"type": "reset_completed"}, {"_id": 0}).sort("at", -1).to_list(5)}


import phase58  # noqa: E402,F401  (Phase 58 routes register on `api`)
import phase59  # noqa: E402,F401  (Phase 59 routes register on `api`)

app.include_router(api)


_cors_list = [o.strip().rstrip("/") for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip() and o.strip() != "*"]
if os.environ.get("PUBLIC_BASE_URL"):
    _cors_list.append(os.environ["PUBLIC_BASE_URL"].rstrip("/"))
# Credentialed CORS never answers "*": explicit origins + the Emergent preview/deploy domains (regex echoes the exact origin).
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=_cors_list,
    allow_origin_regex=os.environ.get("CORS_ORIGIN_REGEX") or None,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    await db.users.create_index("email", unique=True)
    await db.password_resets.create_index("token_hash")
    await db.users.create_index("institution_id")
    await db.login_attempts.create_index("identifier")
    await db.principal_assignments.create_index([("user_id", 1), ("institution_id", 1)])
    await db.principal_assignments.create_index("institution_id")
    await db.institutions.create_index("slug", unique=True, sparse=True)
    await db.audit_logs.create_index([("timestamp", -1)])
    for col in ("students", "teachers", "classes", "sections", "subjects",
                "academic_years", "academic_units", "subject_offerings",
                "enrollments", "teacher_assignments", "assessments"):
        await db[col].create_index("institution_id")
    await db.attendance.create_index([("institution_id", 1), ("class_name", 1), ("section", 1), ("date", 1)])
    await db.marks.create_index([("assessment_id", 1), ("student_id", 1)])
    await db.timetable_entries.create_index([("institution_id", 1), ("academic_year", 1), ("day", 1), ("period_no", 1)])
    await db.timetable_configs.create_index([("institution_id", 1), ("academic_year", 1)])
    await db.subject_requirements.create_index([("institution_id", 1), ("class_name", 1), ("subject", 1)])
    await db.timetable_batches.create_index([("institution_id", 1), ("class_name", 1), ("state", 1)])
    await db.timetable_entries.update_many({"publish_state": {"$exists": False}}, {"$set": {"publish_state": "published"}})
    # Migrate existing institutions: classes without an academic unit → default "General" unit
    async for inst in db.institutions.find({}, {"id": 1, "setup": 1}):
        iid = inst["id"]
        if (inst.get("setup") or {}).get("migrated_general_unit"):
            continue
        has_classes = await db.classes.count_documents({"institution_id": iid}) > 0
        no_units = await db.academic_units.count_documents({"institution_id": iid}) == 0
        if has_classes and no_units:
            unit_id = str(uuid.uuid4())
            await db.academic_units.insert_one({
                "id": unit_id, "institution_id": iid, "name": "General", "code": "GEN",
                "sort_order": 0, "attendance_model": "daily", "subject_model": "fixed",
                "assessment_model": "marks", "grading_model": "percentage",
                "timetable_required": False, "has_lab": False, "status": "active", "created_at": now_iso()})
            await db.classes.update_many({"institution_id": iid, "academic_unit_id": {"$exists": False}},
                                         {"$set": {"academic_unit_id": unit_id, "academic_unit_name": "General"}})
            await db.institutions.update_one({"id": iid}, {"$set": {"setup.migrated_general_unit": True}})
            logger.info("Migrated institution %s classes into General unit", iid)
        else:
            await db.institutions.update_one({"id": iid}, {"$set": {"setup.migrated_general_unit": False}})
    # Backfill academic_unit_name on any class that has a unit id but no denormalised name
    async for cl in db.classes.find({"academic_unit_id": {"$exists": True}, "academic_unit_name": {"$exists": False}},
                                    {"id": 1, "academic_unit_id": 1}):
        u = await db.academic_units.find_one({"id": cl["academic_unit_id"]})
        await db.classes.update_one({"id": cl["id"]}, {"$set": {"academic_unit_name": u["name"] if u else None}})
    # Backfill enrollment_status on students created before the field existed
    async for st in db.students.find({"enrollment_status": {"$exists": False}}, {"id": 1}):
        has = await db.enrollments.count_documents({"student_id": st["id"]}) > 0
        await db.students.update_one({"id": st["id"]}, {"$set": {"enrollment_status": "enrolled" if has else "not_enrolled"}})
    # Backfill teacher_id on assignments (match by email)
    async for a in db.teacher_assignments.find({"teacher_id": {"$exists": False}, "teacher_email": {"$nin": [None, ""]}}, {"id": 1, "teacher_email": 1, "institution_id": 1}):
        tu = await db.users.find_one({"email": a["teacher_email"], "institution_id": a["institution_id"]}, {"id": 1})
        await db.teacher_assignments.update_one({"id": a["id"]}, {"$set": {"teacher_id": tu["id"] if tu else None}})
    # Backfill practical/marks fields on subject offerings created before the field existed
    async for off in db.subject_offerings.find({"has_practical": {"$exists": False}}, {"id": 1, "max_marks": 1}):
        total = off.get("max_marks")
        try:
            total = int(float(total)) if total not in (None, "") and float(total) == int(float(total)) else (float(total) if total not in (None, "") else 100)
        except (TypeError, ValueError):
            total = 100
        await db.subject_offerings.update_one({"id": off["id"]}, {"$set": {
            "has_practical": False, "max_marks": total, "theory_max_marks": total, "practical_max_marks": 0}})
    # Migrate class-level teacher/leadership → per-section (teacher copied to sections without one), then unset on classes
    async for cl in db.classes.find({"$or": [{"class_teacher_id": {"$nin": [None, ""]}},
                                             {"class_leader_id": {"$exists": True}},
                                             {"second_leader_id": {"$exists": True}},
                                             {"class_teacher": {"$nin": [None, ""]}}]},
                                    {"id": 1, "name": 1, "institution_id": 1, "class_teacher_id": 1, "class_teacher": 1}):
        if cl.get("class_teacher_id"):
            await db.sections.update_many(
                {"institution_id": cl["institution_id"], "class_name": cl["name"],
                 "$or": [{"class_teacher_id": {"$exists": False}}, {"class_teacher_id": {"$in": [None, ""]}}]},
                {"$set": {"class_teacher_id": cl["class_teacher_id"], "class_teacher": cl.get("class_teacher", "")}})
        await db.classes.update_one({"id": cl["id"]}, {"$unset": {
            "class_teacher_id": "", "class_teacher": "", "class_leader_id": "", "class_leader": "",
            "second_leader_id": "", "second_leader": ""}})
        logger.info("Migrated class-level leadership to sections for class %s", cl["name"])
    admin_email = os.environ["PLATFORM_ADMIN_EMAIL"].lower()
    try:
        init_storage()
        logger.info("Object storage initialized")
    except Exception as e:
        logger.error("Object storage init failed: %s", e)
    admin_password = os.environ["PLATFORM_ADMIN_PASSWORD"]
    existing = await db.users.find_one({"email": admin_email})
    if existing is None:
        await db.users.insert_one({"id": str(uuid.uuid4()), "name": "LNMO Platform Admin", "email": admin_email,
                                   "password_hash": hash_password(admin_password), "role": "platform_admin",
                                   "institution_id": None, "status": "active", "created_at": now_iso()})
        logger.info("Seeded platform admin %s", admin_email)
    elif not verify_password(admin_password, existing["password_hash"]):
        await db.users.update_one({"email": admin_email},
                                  {"$set": {"password_hash": hash_password(admin_password)}})
    await db.reminders_sent.create_index("key", unique=True)
    await db.messages.create_index([("institution_id", 1), ("created_at", -1)])
    await db.comm_templates.create_index([("institution_id", 1), ("name", 1)])
    await db.curricula.update_many({"is_deleted": {"$exists": False}}, {"$set": {"is_deleted": False}})
    try:
        await db.curricula.drop_index("institution_id_1_academic_year_1_class_name_1_subject_1")
    except Exception:
        pass
    await db.curricula.create_index(
        [("institution_id", 1), ("academic_year", 1), ("class_name", 1), ("subject", 1)],
        unique=True, name="uniq_live_curriculum", partialFilterExpression={"is_deleted": False})
    await db.curriculum_items.create_index([("curriculum_id", 1), ("status", 1)])
    await db.curriculum_comments.create_index([("curriculum_id", 1), ("status", 1)])
    await db.curriculum_comments.create_index([("target_id", 1), ("status", 1)])
    await db.student_memory.create_index([("student_id", 1), ("subject", 1)], unique=True)
    await db.tutor_messages.create_index([("chat_id", 1), ("created_at", 1)])
    await db.platform_library.create_index([("board", 1), ("grade", 1), ("subject", 1), ("status", 1)])
    await db.platform_curriculum_templates.create_index([("board", 1), ("grade", 1), ("subject", 1)], unique=True)
    for _tpl in PHASE36_SCERT_TEMPLATES:
        if not await db.platform_curriculum_templates.find_one({"board": _tpl["board"], "grade": _tpl["grade"], "subject": _tpl["subject"]}):
            await db.platform_curriculum_templates.insert_one({**_tpl, "id": str(uuid.uuid4()), "created_at": now_iso()})
    # Seed LNMO global communication templates (idempotent by name)
    for t in COMM_SEED_TEMPLATES:
        exists = await db.comm_templates.find_one({"institution_id": None, "name": t["name"]})
        if not exists:
            await db.comm_templates.insert_one({
                "id": str(uuid.uuid4()), "institution_id": None, "name": t["name"],
                "category": t["category"], "channel": t["channel"], "body": t["body"],
                "status": "approved", "created_by": "system", "created_at": now_iso()})
    # Background due-reminder sweep (hourly): bells items due TOMORROW, once per item/day.
    asyncio.create_task(_reminder_loop())


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
