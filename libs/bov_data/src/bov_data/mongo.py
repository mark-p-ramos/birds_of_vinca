from typing import Optional

import pymongo
from bson.objectid import ObjectId

from bov_data.data import Sighting, User
from bov_data.db import DB


class MongoClient(DB):
    _mongo_client: pymongo.MongoClient
    _db: pymongo.database.Database

    def __init__(self, connection_uri: str):
        self._mongo_client = pymongo.MongoClient(connection_uri)
        self._db = self._mongo_client.get_database()

    def __del__(self):
        self._mongo_client.close()

    def fetch_users(self) -> list[User]:
        user_docs = self._db.users.find()
        return [User(**user) for user in user_docs]

    def update_user(
        self, id: str, feed_type: Optional[str] = None, last_polled_at: Optional[str] = None
    ) -> None:
        if feed_type is None and last_polled_at is None:
            return

        fields = {}
        if feed_type is not None:
            fields["feed_type"] = feed_type
        if last_polled_at is not None:
            fields["last_polled_at"] = last_polled_at

        self._db.users.update_one({"_id": ObjectId(id)}, {"$set": fields})

    def create_sighting(self) -> str: ...

    def fetch_sightings(self, page: int = 0, per_page: int = 20) -> list[Sighting]: ...
