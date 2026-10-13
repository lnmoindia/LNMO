"""Live API tests for Phase 51 — issues, collect date, principal scope, statement."""
import os, requests, datetime
BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://lnmo-fees.preview.emergentagent.com").rstrip("/")

def login(email, pwd, slug="p50demo"):
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login", json={"email": email, "password": pwd, "institution_slug": slug}, timeout=20)
    r.raise_for_status()
    return s

def main():
    admin = login("admin@feesdemo.test", "admin123")
    phs = login("principal.hs@feesdemo.test", "teach123")
    plp = login("principal.lp@feesdemo.test", "teach123")
    parent = login("parent@feesdemo.test", "parent123")
    print("logins OK")

    r = parent.get(f"{BASE}/api/parent/children", timeout=15)
    data = r.json()
    children = data if isinstance(data, list) else data.get("children", data.get("items", []))
    print(f"children: {len(children)}; sample={children[0] if children else None}")
    arjun = next((c for c in children if "Arjun" in str(c)), children[0])
    arjun_id = arjun.get("id") or arjun.get("student_id")
    print(f"Arjun id: {arjun_id}, name: {arjun.get('name') or arjun.get('full_name')}")

    r = parent.get(f"{BASE}/api/parent/child/{arjun_id}/fees", timeout=15)
    fees = r.json()
    invoices = fees.get("invoices", []) or fees.get("periods", [])
    print(f"fees payload keys: {list(fees.keys())[:10]}; invoices: {len(invoices)}")
    inv = next((i for i in invoices if i.get("status") in ("unpaid","partial","overdue")), None)
    print(f"issue target inv: {inv.get('id','?')[:12] if inv else None}, status={inv.get('status') if inv else None}")

    # Raise issue
    if inv:
        r = parent.post(f"{BASE}/api/parent/child/{arjun_id}/fees/invoices/{inv['id']}/issue",
                        json={"message": "I paid 10 Oct via UPI; please verify"}, timeout=15)
        print(f"raise issue → {r.status_code}; body={r.text[:120]}")

    # Admin list issues
    r = admin.get(f"{BASE}/api/fees/issues?status=open", timeout=15)
    print(f"admin open issues → {r.status_code}; count={len(r.json()) if r.ok else '?'}")

    # Future paid_on → 400
    future_date = (datetime.date.today() + datetime.timedelta(days=5)).isoformat()
    if inv:
        pay_payload = {
            "invoice_id": inv.get("id"),
            "account_id": inv.get("account_id"),
            "amount": 100, "method": "cash",
            "paid_on": future_date,
        }
        r = admin.post(f"{BASE}/api/fees/payments", json=pay_payload, timeout=15)
        print(f"POST /payments future paid_on → {r.status_code}; body={r.text[:150]}")

    # Pending proofs
    r = admin.get(f"{BASE}/api/fees/proofs?status=pending", timeout=15)
    pending = r.json() if r.ok else []
    print(f"admin pending proofs: {r.status_code}; count={len(pending) if isinstance(pending,list) else '?'}")

    # LP principal rejects HS proof → 403
    if isinstance(pending, list) and pending:
        pid = pending[0].get("id")
        r = plp.post(f"{BASE}/api/fees/proofs/{pid}/reject", json={"reason":"test"}, timeout=15)
        print(f"LP principal reject HS proof → {r.status_code}  (expect 403)")

    # Accounts list
    r = admin.get(f"{BASE}/api/fees/accounts", timeout=15)
    accts = r.json() if r.ok else []
    print(f"accounts: {r.status_code}; count={len(accts) if isinstance(accts,list) else '?'}")

    # HS principal pays Grade 4 (Farhan Ali) → 403
    if isinstance(accts, list):
        farhan = next((a for a in accts if "Farhan" in str(a)), None)
        if farhan:
            fid = farhan.get("id") or farhan.get("account_id")
            r = admin.get(f"{BASE}/api/fees/accounts/{fid}", timeout=15)
            lf = r.json() if r.ok else {}
            invs = lf.get("invoices", []) or lf.get("periods", [])
            unpaid = next((p for p in invs if p.get("status") in ("unpaid","partial","overdue")), None)
            if unpaid:
                payload = {"account_id": fid, "invoice_id": unpaid.get("id"),
                           "amount": 100, "method": "cash"}
                r = phs.post(f"{BASE}/api/fees/payments", json=payload, timeout=15)
                print(f"HS principal pays Grade 4 → {r.status_code}  (expect 403)")

    # Statement API comparison
    r1 = admin.get(f"{BASE}/api/fees/students/{arjun_id}/statement", timeout=15)
    print(f"statement JSON → {r1.status_code}; keys={list(r1.json().keys())[:10] if r1.ok else r1.text[:120]}")

    # Parent statement PDF
    r = parent.get(f"{BASE}/api/parent/child/{arjun_id}/fees/statement.pdf", timeout=20)
    print(f"parent own statement.pdf → {r.status_code}; ctype={r.headers.get('content-type','?')[:40]}; len={len(r.content)}")

    # Parent other-child statement → 403
    r = parent.get(f"{BASE}/api/parent/child/00000000-0000-0000-0000-000000000000/fees/statement.pdf", timeout=20)
    print(f"parent bogus-child statement.pdf → {r.status_code}  (expect 403/404)")

if __name__ == "__main__":
    main()
