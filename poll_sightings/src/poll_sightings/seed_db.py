import dataclasses
import os
from datetime import UTC, datetime

from bov_data import BirdBuddy, BirdFeed, User
from dotenv import load_dotenv
from pymongo import ASCENDING, DESCENDING, MongoClient


def main():
    print("connecting to mongo db...")
    mongo = MongoClient(os.getenv("MONGODB_URI"))
    db = mongo.get_database()
    print("dropping collections...")
    db.users.drop()
    db.sightings.drop()

    print("seeding users ...")
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

    print("seeding sightings ...")
    db.sightings.create_index([("bb_id", ASCENDING)], unique=True)
    print("created index on sightings.bb_id")

    db.sightings.create_index([("created_at", DESCENDING)])
    print("created index on sightings.created_at")

    mongo.close()


if __name__ == "__main__":
    load_dotenv()
    main()
