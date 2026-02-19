import dataclasses
import os
from datetime import UTC, datetime

from bov_data import BirdBuddy, BirdFeed, User
from dotenv import load_dotenv
from pymongo import MongoClient


def main():
    print("connecting to mongo db...")
    mongo = MongoClient(os.getenv("MONGODB_URI"))
    db = mongo.get_database()
    print("dropping collections...")
    db.users.drop()
    print("seeding ...")
    doc = dataclasses.asdict(
        User(
            email="mark.p.ramos@gmail.com",
            bird_buddy=BirdBuddy(
                user="mark.p.ramos+birdbud@gmail.com",
                password="uq7I&15G!Bt1oLfH",
                location_zip="80027",
                feed=BirdFeed(brand="3D Pet Products", product="Sizzle N' Heat"),
            ),
            created_at=datetime.now(UTC),
        )
    )

    del doc["_id"]
    result = db.users.insert_one(doc)
    print(f"created user_id: {result.inserted_id}")
    mongo.close()


if __name__ == "__main__":
    load_dotenv()
    main()
