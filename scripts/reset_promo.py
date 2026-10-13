import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
runs = list(db.promotion_runs.find({"status": "preview"}))
for r in runs:
    db.promotion_decisions.delete_many({"run_id": r["id"]})
    db.promotion_runs.delete_one({"id": r["id"]})
# remove the auto-created, empty to-year row (no enrollments reference it yet)
enr = db.enrollments.count_documents({"academic_year": "2027-28"})
removed_year = False
if enr == 0:
    res = db.academic_years.delete_many({"name": "2027-28"})
    removed_year = res.deleted_count > 0
print("deleted_runs:", len(runs), "removed_2027-28_year:", removed_year,
      "remaining_preview_runs:", db.promotion_runs.count_documents({"status": "preview"}))
