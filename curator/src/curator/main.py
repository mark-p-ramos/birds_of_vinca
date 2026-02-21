import asyncio
import os

import functions_framework
import sentry_sdk
from bov_data import DB, MongoClient, Sighting, Weather
from dotenv import load_dotenv
from flask import Request
from markupsafe import escape
from sentry_sdk.integrations.asyncio import enable_asyncio_integration
from sentry_sdk.integrations.gcp import GcpIntegration

from curator.images import curate_images
from curator.videos import curate_videos
from curator.weather import get_historical_weather

sentry_sdk.init(
    dsn="https://1192a22bf953b2327b2219cfad5f4a44@o4510925100941312.ingest.us.sentry.io/4510925123747840",
    integrations=[GcpIntegration(timeout_warning=True)],
    # Add data like request headers and IP for users,
    # see https://docs.sentry.io/platforms/python/data-management/data-collected/ for more info
    send_default_pii=True,
)


@functions_framework.http
def import_sighting(request: Request):
    json = request.get_json(silent=True)
    if not json:
        return "request missing json body"

    sentry_sdk.set_context("sighting", json)
    sighting = Sighting(**json)
    return asyncio.run(main(sighting))


async def main(sighting: Sighting) -> str:
    enable_asyncio_integration()
    db: DB = MongoClient(os.getenv("MONGODB_URI"))

    sighting_exists = await db.exists_sighting(sighting.bb_id)
    if sighting_exists:
        return f"sighting id: {escape(sighting.bb_id)} already imported"

    weather = await get_historical_weather(
        os.getenv("WEATHER_API_KEY"), "80027", sighting.created_at
    )
    sighting.weather = Weather(**weather)

    images, videos = await asyncio.gather(
        curate_images(sighting.media.images), curate_videos(sighting.media.videos)
    )

    if not images and not videos:
        return "sighting not imported: no media"

    sighting.media.images = images
    sighting.media.videos = videos
    created_id = await db.create_sighting(sighting)
    return f"created sighting id: {created_id}"


if __name__ == "__main__":
    load_dotenv()
    pass
