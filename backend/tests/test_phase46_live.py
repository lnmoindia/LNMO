"""
PHASE 46 LIVE smoke tests + DB cleanup. Uses TEST_P46_ prefix & 99900460xx phones only.
"""
import os, re, random, sys
import pytest, requests
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://lnmo-fees.preview.emergentagent.com").rstrip("/")
API = f"{BASE}/api"
MONGO = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
ADMIN_EMAIL = "admin@lpgs.com"; ADMIN_PASS = "admin123"

@pytest.fixture(scope="module")
def S():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS, "domain": "lpgs.com"}, timeout=20)
    assert r.status_code == 200, r.text[:200]
    return s

@pytest.fixture(scope="module", autouse=True)
def pre_cleanup():
    """Nuke any leftover TEST_P46_ data and 99900460xx parent users before starting."""
    _wipe_test_data()
    yield
    _wipe_test_data()

def _wipe_test_data():
    stu_ids = [s["id"] for s in MONGO.students.find({"first_name": {"$regex": "^TEST_P46_"}}, {"id": 1})]
    if stu_ids:
        MONGO.students.delete_many({"id": {"$in": stu_ids}})
    # parent users with synthetic p<phone>@lpgs.parent.invite where phone starts 999004600
    MONGO.users.delete_many({"email": {"$regex": r"^p999004(60[0-9]{2}|6010)@"}})
    MONGO.parent_invites.delete_many({"phone": {"$regex": "^99900460"}})
    MONGO.parent_setup_codes.delete_many({"student_id": {"$in": stu_ids}}) if stu_ids else None
    MONGO.messages.delete_many({"module": "parent_invite", "recipient_phone": {"$regex": "^99900460"}})

CREATED = []  # (sid, phone)
def _mk(S, phone, suffix, gname=None):
    body = {
        "first_name": f"TEST_P46_{suffix}", "last_name": "Live",
        "class_name": "Grade 7", "section": "A",
        "guardian_name": gname or f"TEST Guardian {suffix}",
        "guardian_phone": phone,
        "admission_no": f"TP46L{suffix}{random.randint(100,999)}",
        "enroll": True, "academic_year": "2026-27",
    }
    r = S.post(f"{API}/students/enroll", json=body, timeout=20)
    assert r.status_code in (200,201), f"{r.status_code} {r.text[:200]}"
    sid = r.json()["id"]
    CREATED.append((sid, phone))
    return sid

def _ids(d, key):
    out = set()
    for row in (d.get(key) or []):
        if isinstance(row, dict):
            out.add(row.get("student_id") or row.get("id"))
    return out


def test_01_ready_to_invite_and_bulk_invite(S):
    s1 = _mk(S, "9990046001", "A1", "TEST Shared Guardian")
    s2 = _mk(S, "9990046001", "A2", "TEST Shared Guardian")  # sibling same phone+gname
    s3 = _mk(S, "", "B1")  # no phone

    r = S.get(f"{API}/students/ready-to-invite", timeout=20)
    assert r.status_code == 200, r.text[:200]
    ready_ids = {row["student_id"] for row in r.json()["ready"]}
    assert s1 in ready_ids and s2 in ready_ids
    assert s3 not in ready_ids

    r = S.post(f"{API}/students/invite-parents",
               json={"class_names": ["Grade 7"], "channel": "whatsapp"}, timeout=30)
    assert r.status_code == 200, r.text[:300]
    data = r.json()
    inv = _ids(data, "invited"); linked = _ids(data, "already_linked"); skp = _ids(data, "skipped_no_phone")
    # s1 either invited (created) or linked_sibling in invited; s2 should be in invited as linked_sibling
    assert (s1 in inv) and (s2 in inv), f"both siblings should be processed; inv={inv} linked={linked}"
    assert s3 in skp

    # Idempotent re-run
    r2 = S.post(f"{API}/students/invite-parents",
                json={"class_names": ["Grade 7"], "channel": "whatsapp"}, timeout=30)
    assert r2.status_code == 200
    inv2 = _ids(r2.json(), "invited"); linked2 = _ids(r2.json(), "already_linked")
    assert s1 in linked2 and s2 in linked2
    assert s1 not in inv2 and s2 not in inv2

    # Verify stub message was sent exactly once (one account per phone)
    msgs = list(MONGO.messages.find({"module":"parent_invite", "recipient_phone":"9990046001"}))
    assert len(msgs) == 1, f"expected 1 stub message for 9990046001, got {len(msgs)}"
    assert msgs[0].get("provider") == "stub"


def test_02_phone_normalization(S):
    sA = _mk(S, "+91 99900 46002", "N1", "TEST Norm Guardian")
    sB = _mk(S, "9990046002", "N2", "TEST Norm Guardian")
    r = S.post(f"{API}/students/invite-parents",
               json={"class_names":["Grade 7"], "channel":"whatsapp"}, timeout=30)
    assert r.status_code == 200
    d = r.json()
    inv = _ids(d, "invited"); linked = _ids(d, "already_linked")
    # Both must appear in processed buckets, and NOT both as freshly 'created'
    all_bucket = inv | linked
    assert sA in all_bucket and sB in all_bucket
    # Count parent users with this normalized phone -> must be 1
    cnt = MONGO.users.count_documents({"phone": "9990046002", "role":"parent"})
    assert cnt == 1, f"expected single parent user for normalized phone, got {cnt}"


def test_03_setup_code_for_skipped(S):
    sid = _mk(S, "", "S1")
    r = S.post(f"{API}/students/{sid}/setup-code", timeout=20)
    assert r.status_code == 200, r.text[:300]
    j = r.json()
    code = j.get("code") or j.get("setup_code") or j.get("plain_code")
    assert code and re.fullmatch(r"\d{6}", str(code)), f"not 6-digit: {j}"
    # Verify stored hashed in parent_setup_codes
    doc = MONGO.parent_setup_codes.find_one({"student_id": sid})
    assert doc, "setup code row missing in DB"
    assert "code_hash" in doc or "hashed_code" in doc or doc.get("code") != code, \
        f"code appears stored in plaintext: {doc}"


def test_04_collision_review_dismiss(S):
    phone = "9990046010"
    s1 = _mk(S, phone, "R1", "Guardian Alpha")
    s2 = _mk(S, phone, "R2", "Guardian Beta")
    r = S.post(f"{API}/students/invite-parents",
               json={"class_names":["Grade 7"], "channel":"whatsapp"}, timeout=30)
    assert r.status_code == 200
    coll = _ids(r.json(), "collisions_for_review")
    assert s1 in coll and s2 in coll, f"collision bucket missing: {coll}"

    r = S.get(f"{API}/students/invite-review", timeout=20)
    assert r.status_code == 200
    groups = r.json() if isinstance(r.json(), list) else r.json().get("groups", r.json().get("review", []))
    norm = lambda p: re.sub(r"\D","", str(p))[-10:]
    found = False
    for g in groups:
        if not isinstance(g, dict): continue
        gphone = norm(g.get("phone", ""))
        if gphone == norm(phone):
            found = True; break
        sts = g.get("students", [])
        if any(norm(st.get("guardian_phone","")) == norm(phone) for st in sts):
            found = True; break
    assert found, f"review bucket missing collision for {phone}; got {groups}"

    r = S.post(f"{API}/students/invite-review/resolve",
               json={"phone": phone, "action":"dismiss", "student_ids":[s1,s2]}, timeout=20)
    assert r.status_code == 200, r.text[:300]

    r = S.get(f"{API}/students/invite-review", timeout=20)
    groups2 = r.json() if isinstance(r.json(), list) else r.json().get("groups", r.json().get("review", []))
    still = False
    for g in groups2:
        if not isinstance(g, dict): continue
        if norm(g.get("phone","")) == norm(phone):
            still = True; break
    assert not still, "dismissed collision should disappear"


def test_05_bad_single_invite(S):
    r = S.post(f"{API}/students/00000000-0000-0000-0000-000000000000/invite-parent",
               json={"channel":"whatsapp"}, timeout=20)
    assert r.status_code in (400, 403, 404), f"got {r.status_code}: {r.text[:200]}"


def test_06_public_setup_token_tampered():
    r = requests.get(f"{API}/public/parent-setup/not-a-real-token-xyz", timeout=20)
    assert r.status_code in (400, 404), f"expected 4xx got {r.status_code}: {r.text[:200]}"


def test_07_public_parent_register_wrong_code():
    r = requests.post(f"{API}/public/parent-register",
                      json={"admission_no":"NONEXISTENT","code":"000000","name":"X",
                            "phone":"9990000000","password":"Secret@2026"}, timeout=20)
    assert r.status_code in (400, 404), f"expected 4xx got {r.status_code}: {r.text[:200]}"
