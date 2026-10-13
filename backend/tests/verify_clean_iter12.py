import os
from dotenv import dotenv_values
from pymongo import MongoClient

be = dotenv_values("/app/backend/.env")
db = MongoClient(be["MONGO_URL"])[be["DB_NAME"]]
print("TEST_ classes:", list(db.classes.find({"name": {"$regex": "TEST_"}}, {"_id": 0, "name": 1})))
print("sections Z:", list(db.sections.find({"class_name": {"$regex": "TEST_"}}, {"_id": 0, "name": 1})))
print("offerings TEST:", db.subject_offerings.count_documents({"class_name": {"$regex": "TEST_"}}))
print("assignments TEST:", db.teacher_assignments.count_documents({"class_name": {"$regex": "TEST_"}}))
print("tt entries:", list(db.timetable_entries.find({}, {"_id": 0, "class_name": 1, "section": 1, "day": 1, "period_no": 1, "subject": 1, "room": 1})))
print("tt configs:", list(db.timetable_configs.find({}, {"_id": 0, "academic_year": 1, "academic_unit_id": 1})))
print("notices:", list(db.notices.find({}, {"_id": 0, "title": 1, "audience": 1, "status": 1})))
print("portal users:", list(db.users.find({"role": "student"}, {"_id": 0, "email": 1})))
print("aarav has_portal_access:", db.students.find_one({"id": "9fa05e4b-3ec9-4e53-8fb2-8a69b517a4dc"}, {"_id": 0, "has_portal_access": 1}))
print("assessments:", list(db.assessments.find({}, {"_id": 0, "name": 1, "subject": 1, "status": 1})))
