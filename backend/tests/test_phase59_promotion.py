"""Phase 59: promotion execute + dues carry-forward per-student details (throwaway school only — never LPGS)."""
import uuid

import pytest

from tests.test_phase58 import API, db, login
from tests.test_phase58 import ctx as _p58_ctx  # noqa: F401  (fixture reused via getfixturevalue)


@pytest.fixture(scope="module")
def c(request):
    return request.getfixturevalue("_p58_ctx")


def test_promotion_execute_and_carry_forward_details(c):
    iid, S = c["iid"], c["S"]
    assert db.institutions.find_one({"id": iid})["name"].startswith("P58 Throwaway")
    a = login(c["U"]["admin"]["email"])
    rid = str(uuid.uuid4())
    db.academic_years.insert_many([{"id": str(uuid.uuid4()), "institution_id": iid, "name": n} for n in ("2025-26", "2026-27")])
    plan = [("s8", "promote", "Grade 9", "A"), ("inv_all", "detain", None, None), ("inv_noemail", "transfer_out", None, None),
            ("s4", "graduate", None, None)]
    for key, dec, to_c, to_s in plan:
        s = S[key]
        db.enrollments.insert_one({"id": str(uuid.uuid4()), "institution_id": iid, "student_id": s["id"], "academic_year": "2025-26",
                                   "class_name": s["class_name"], "section": s["section"], "status": "active"})
        db.promotion_decisions.insert_one({"id": str(uuid.uuid4()), "run_id": rid, "institution_id": iid, "student_id": s["id"],
                                           "student_name": f"{s['first_name']} {s['last_name']}", "admission_no": s.get("admission_no"),
                                           "from_class": s["class_name"], "from_section": s["section"], "decision": dec,
                                           "to_class": to_c, "to_section": to_s})
    # one unpaid 2025-26 invoice for the promoted student → carried forward; the detained one has none
    db.fee_invoices.insert_one({"id": str(uuid.uuid4()), "institution_id": iid, "account_id": "acc-old", "structure_id": None,
                                "student_id": S["s8"]["id"], "student_name": "Kiran Rao", "academic_year": "2025-26", "period_label": "T3",
                                "items": [{"title": "Tuition", "amount": 500}], "subtotal": 500, "total": 500, "paid_amount": 0,
                                "discount_amount": 0, "fine_amount": 0, "due_date": "2026-03-10", "status": "overdue"})
    db.promotion_runs.insert_one({"id": rid, "institution_id": iid, "from_year": "2025-26", "to_year": "2026-27", "status": "preview",
                                  "created_at": "2026-10-14T00:00:00+00:00"})
    r = a.post(f"{API}/promotion/{rid}/execute").json()
    assert r["summary"] == {"promote": 1, "detain": 1, "transfer_out": 1, "graduate": 1}  # legacy field kept
    by = {i["id"]: i for i in r["items"]}
    assert by[S["s8"]["id"]]["reason"] == "Promoted to Grade 9 A (2026-27)" and by[S["s8"]["id"]]["fix"]["type"] == "open_student"
    assert by[S["inv_all"]["id"]]["reason"] == "Detained in Grade 8 A (2026-27)"
    assert by[S["s4"]["id"]]["reason"] == "Graduated — marked alumni"
    assert by[S["inv_noemail"]["id"]]["reason"].startswith("Transferred out")
    assert r["run_summary"]["created"] == 4 and r["run_summary"]["promote"] == 1
    run = a.get(f"{API}/bulk-runs/{r['run_id']}").json()
    assert run["kind"] == "promotion_execute" and run["ref_id"] == rid and len(run["items"]) == 4
    cf = r["dues_carry_forward"]
    assert cf["created"] == 1 and cf["amount"] == 500 and cf["arrears_invoice_ids"]  # legacy fields kept
    cby = {i["id"]: i for i in cf["items"]}
    assert cby[S["s8"]["id"]]["status"] == "created" and "₹500.00" in cby[S["s8"]["id"]]["reason"]
    assert cby[S["inv_all"]["id"]]["reason"] == "No unpaid dues in 2025-26"
    assert a.get(f"{API}/bulk-runs/{cf['run_id']}").json()["kind"] == "dues_carry_forward"
    # re-run carry-forward → idempotent, reason "already carried"
    r2 = a.post(f"{API}/fees/carry-forward", json={"run_id": rid}).json()
    assert r2["created"] == 0 and r2["already_carried"] == 1 and r2["summary"]["skipped"] == 2 and r2["run_id"]
    assert {i["id"]: i for i in r2["items"]}[S["s8"]["id"]]["reason"] == "Dues already carried forward to 2026-27"
    assert db.bulk_runs.count_documents({"institution_id": iid, "ref_id": rid}) == 3
    assert a.post(f"{API}/promotion/{rid}/execute").status_code == 409
