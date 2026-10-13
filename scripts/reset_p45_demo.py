import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
a = db.assessments.delete_many({"_p45_demo": True})
m = db.marks.delete_many({"_p45_demo": True})
print("deleted demo assessments:", a.deleted_count, "marks:", m.deleted_count)
