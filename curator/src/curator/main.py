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


@functions_framework.http
def import_sighting(request: Request):
    json = request.get_json(silent=True)
    if not json:
        return "request missing json body"

    sighting = Sighting(**json)
    return asyncio.run(main(sighting))


def _get_db() -> DB:
    return MongoClient(os.getenv("MONGODB_URI"))


# TODO
# setup cloud storage
# increase runtime of cloud function to at least 10 minutes
# 3. curate images / upload to cloud storage
# 4. curate videos / upload to cloud storage
async def main(sighting: Sighting) -> str:
    db = _get_db()
    if await db.exists_sighting(sighting.bb_id):
        return f"sighting id: {escape(sighting.bb_id)} already imported"

    weather = await get_historical_weather(
        os.getenv("WEATHER_API_KEY"), "80027", sighting.created_at
    )
    sighting.weather = Weather(**weather)

    sighting.media.images = curate_images(sighting.media.images)
    sighting.media.videos = curate_videos(sighting.media.videos)

    created_id = db.create_sighting(sighting)
    return f"created sighting id: {created_id}"


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

    result = asyncio.run(main(sighting))
    print(result)
