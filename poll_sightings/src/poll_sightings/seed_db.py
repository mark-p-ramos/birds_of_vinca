import dataclasses
import os
from datetime import UTC, datetime

from bov_data import User
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()
print("connecting to mongo db...")
mongo = MongoClient(os.getenv("MONGODB_URI"))
db = mongo.get_database()
print("seeding ...")
doc = dataclasses.asdict(
    User(
        email="mark.p.ramos@gmail.com",
        bird_buddy_user="mark.p.ramos+birdbud@gmail.com",
        bird_buddy_password="uq7I&15G!Bt1oLfH",
    )
)
doc["created_at"] = datetime.now(UTC)
result = db.users.insert_one(doc)
print(f"created user_id: {result.inserted_id}")
mongo.close()
