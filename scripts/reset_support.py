import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
res = db.issues.delete_many({"$or": [
    {"title": {"$regex": "^TEST_"}},
    {"title": {"$regex": "^E2E-TEST"}},
    {"title": {"$regex": "CRASHTEST"}},
    {"error_message": {"$regex": "CRASHTEST"}},
]})
print("deleted_test_issues:", res.deleted_count, "remaining_issues:", db.issues.count_documents({}))
