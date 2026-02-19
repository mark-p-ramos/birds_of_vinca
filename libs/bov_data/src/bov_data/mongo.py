from dataclasses import asdict
from typing import Optional

import pymongo
from bson.objectid import ObjectId

from bov_data.data import BirdBuddy, Sighting, User
from bov_data.db import DB


def _id_to_str(doc: dict) -> dict:
    doc["_id"] = str(doc["_id"])
    return doc


class MongoClient(DB):
    _mongo_client: pymongo.MongoClient
    _db: pymongo.database.Database

    def __init__(self, connection_uri: str):
        self._mongo_client = pymongo.MongoClient(connection_uri)
        self._db = self._mongo_client.get_database()

    def __del__(self):
        self._mongo_client.close()

    def fetch_users(self) -> list[User]:
        user_docs = self._db.users.find({"bird_buddy": {"$ne": None}})
        return [User(**_id_to_str(user)) for user in user_docs]

    def update_user(self, id: str, bird_buddy: Optional[BirdBuddy] = None) -> None:
        if bird_buddy is None:
            return

        self._db.users.update_one(
            {"_id": ObjectId(id)}, {"$set": {"bird_buddy": asdict(bird_buddy)}}
        )

    def create_sighting(self) -> str: ...

    def fetch_sightings(self, page: int = 0, per_page: int = 20) -> list[Sighting]: ...
