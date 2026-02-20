import asyncio
import os
from datetime import UTC, datetime, timedelta

import functions_framework
from bov_data import DB, MongoClient, Sighting, Weather
from dotenv import load_dotenv
from flask import Request
from markupsafe import escape

from curator.images import curate_images
from curator.videos import curate_videos
from curator.weather import get_historical_weather

db: DB | None = None


def db_connect() -> DB:
    global db
    db = db if db is not None else MongoClient(os.getenv("MONGODB_URI"))
    return db


@functions_framework.http
def import_sighting(request: Request):
    json = request.get_json(silent=True)
    if not json:
        return "request missing json body"

    sighting = Sighting(**json)
    return asyncio.run(main(sighting))


# TODO
# setup cloud storage
# increase runtime of cloud function to at least 10 minutes
# 3. curate images / upload to cloud storage
# 4. curate videos / upload to cloud storage
async def main(sighting: Sighting) -> str:
    db = db_connect()
    if await db.exists_sighting(sighting.bb_id):
        return f"sighting id: {escape(sighting.bb_id)} already imported"

    weather = await get_historical_weather(
        os.getenv("WEATHER_API_KEY"), "80027", sighting.created_at
    )
    sighting.weather = Weather(**weather)

    images, videos = await asyncio.gather(
        curate_images(sighting.media.images), curate_videos(sighting.media.videos)
    )
    sighting.media.images = images
    sighting.media.videos = videos

    created_id = db.create_sighting(sighting)
    return f"created sighting id: {created_id}"


async def test_main():
    db = db_connect()
    exists = await db.exists_sighting(sighting.bb_id)
    if exists:
        print("found it")
    else:
        print("not found")


if __name__ == "__main__":
    # this is for debugging only
    # perhaps remove it altogether for production
    load_dotenv()

    sighting = Sighting(
        **{
            "bb_id": "postcard-123",
            "user_id": "user_123",
            "bird_feed": {
                "brand": "Test Brand",
                "product": "Test Product",
            },
            "location_zip": "80027",
            "species": ["Northern Flicker"],
            "media": {"images": [], "videos": []},
            "created_at": datetime.now(UTC) - timedelta(minutes=15),
        }
    )

    asyncio.run(test_main())

    # result = asyncio.run(main(sighting))
    # print(result)
