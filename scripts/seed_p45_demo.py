import os, uuid
from datetime import datetime, timezone, timedelta
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
IID = "82d1ec4e-db71-4578-903b-bc986f1ebd3d"
SID = "ad2e8293-475a-4db1-9f40-a36642544897"  # g8student
base = datetime(2026, 7, 1, tzinfo=timezone.utc)
plan = {"Mathematics": [72, 78, 85, 91], "Science": [60, 68, 75], "English": [80, 76, 88]}
n = 0
for subject, scores in plan.items():
    for i, sc in enumerate(scores):
        aid = str(uuid.uuid4())
        db.assessments.insert_one({
            "id": aid, "institution_id": IID, "class_name": "Grade 8", "section": "A",
            "subject": subject, "name": f"Test {i+1} — {subject}", "max_marks": 100,
            "status": "published", "created_at": (base + timedelta(days=30 * (i + 1))).isoformat(),
            "_p45_demo": True,
        })
        db.marks.insert_one({"id": str(uuid.uuid4()), "institution_id": IID, "assessment_id": aid,
                             "student_id": SID, "score": sc, "_p45_demo": True})
        n += 1
print("seeded demo assessments+marks:", n)
