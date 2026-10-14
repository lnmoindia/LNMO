"""Phase 60 follow-up: verify (2) channel reason reads 'sms: no phone' not 'sms: no no phone'."""
import os
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE}/api"
STUDENT_ID = "9526f756-ecb9-4923-82c6-64838eaa0c7c"
ADMIN_EMAIL = "admin@feesdemo.test"
ADMIN_PASS = "admin123"


def _login():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS, "domain": "p50demo"})
    assert r.status_code == 200, r.text
    return s


def test_invite_sms_reason_no_phone():
    s = _login()
    r = s.post(f"{API}/students/{STUDENT_ID}/invite-parent", json={"channels": ["sms"]})
    assert r.status_code == 200, r.text
    data = r.json()
    print("INVITE RESPONSE:", data)
    run_id = data.get("run_id") or data.get("bulk_run_id") or data.get("id")
    assert run_id, data
    br = s.get(f"{API}/bulk-runs/{run_id}").json()
    print("BULK RUN:", br)
    items = br.get("items") or []
    text_blob = " | ".join(str(i.get("reason", "")) for i in items)
    print("REASONS:", text_blob)
    assert "no no" not in text_blob.lower(), f"Found 'no no' in reasons: {text_blob}"
    # at least one item mentions 'no phone' / 'No phone'
    assert ("no phone" in text_blob.lower()) or ("No phone" in text_blob), text_blob


if __name__ == "__main__":
    test_invite_sms_reason_no_phone()
    print("OK")
