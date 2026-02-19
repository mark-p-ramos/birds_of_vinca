from dataclasses import asdict
from typing import Optional

import pymongo
from bson.objectid import ObjectId

from bov_data.data import BirdBuddy, User
from bov_data.db import DB


def _id_to_str(doc: dict) -> dict:
    doc["_id"] = str(doc["_id"])
    return doc


class MongoClient(DB):
    _mongo_client: pymongo.AsyncMongoClient
    _db: pymongo.database.Database

    def __init__(self, connection_uri: str):
        self._mongo_client = pymongo.MongoClient(connection_uri)
        self._db = self._mongo_client.get_database()

    def __del__(self):
        self._mongo_client.close()

    async def fetch_users(self) -> list[User]:
        docs = await self._db.users.find({"bird_buddy": {"$ne": None}})
        return [User(**_id_to_str(user)) for user in docs]

    async def update_user(self, id: str, bird_buddy: Optional[BirdBuddy] = None) -> None:
        if bird_buddy is None:
            return

        await self._db.users.update_one(
            {"_id": ObjectId(id)}, {"$set": {"bird_buddy": asdict(bird_buddy)}}
        )

    async def create_sighting(self) -> str: ...

    async def exists_sighting(self, bb_id: str) -> bool:
        doc = await self._db.find_one({"bb_id": bb_id})
        return doc is not None
