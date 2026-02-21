import asyncio
import os
from datetime import datetime, timezone

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

load_dotenv(override=False)
db: DB = MongoClient(os.getenv("MONGODB_URI"))


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

    if await db.exists_sighting(sighting.bb_id):
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
    from bov_data import BirdFeed, Media

    sighting = Sighting(
        bb_id="postcard-99ffc88b-56ce-46d9-ae0e-d11ab1148faf",
        user_id="699886b2e92d4786cc88ee34",
        bird_feed=BirdFeed(brand="3D Pet Products", product="Sizzle N' Heat"),
        location_zip="80027",
        species=["Squirrel"],
        media=Media(
            images=[
                "https://media.app-api-graphql.app-api.prod.aws.mybirdbuddy.com/media/feeder/348ec5f8-16b4-48f5-aa93-d8a054fa652e/media/26af79e2-fb16-40a5-9763-f177a4967688/CONTENT.jpg?Expires=1771719421&Key-Pair-Id=K1HE0EC9UCSK2V&Signature=MEUCIGbwNr3SekUHF9r-GlYKfZzVpQXCrT0zVWHFwePi39JXAiEAxCmkjO1RC15dFwxsX404un0EK9GGOaG-mVecFcbe7HY_",
                "https://media.app-api-graphql.app-api.prod.aws.mybirdbuddy.com/media/feeder/348ec5f8-16b4-48f5-aa93-d8a054fa652e/media/b9753802-120f-4081-91a1-7ec4190d754e/CONTENT.jpg?Expires=1771719421&Key-Pair-Id=K1HE0EC9UCSK2V&Signature=MEUCIFuNYHRNNpVlfRdUSTTnkmD7aEU4zzD-C6%7EDlmf3qs%7EfAiEAi3%7En5AEiadw2bRp1RRJc1dWhYuxeZBea-0ovBoP6Gxs_",
                "https://media.app-api-graphql.app-api.prod.aws.mybirdbuddy.com/media/feeder/348ec5f8-16b4-48f5-aa93-d8a054fa652e/media/3f86f3ae-e95f-417b-8c5b-444321f8ec7d/CONTENT.jpg?Expires=1771719421&Key-Pair-Id=K1HE0EC9UCSK2V&Signature=MEQCIC9yenrGH8Yd53JUR6X%7EMbgu5RfqafBGL39RM5DYKiU9AiBDIbldhOpGsRynhRAvdPCdNyQL21Q3qrvA4cv8VhBUVA__",
                "https://media.app-api-graphql.app-api.prod.aws.mybirdbuddy.com/media/feeder/348ec5f8-16b4-48f5-aa93-d8a054fa652e/media/9ae79c2e-b8b5-4db1-8c3d-e8543d4ec073/CONTENT.jpg?Expires=1771719421&Key-Pair-Id=K1HE0EC9UCSK2V&Signature=MEQCIBgfLNs-XLxelZdAC775YTdTKBwGBYdVwIjDDlOxS1ndAiAhLxvRJ0YuVaYBNgoj1lDasg5YmsseU5oMZdrAPVzRFw__",
                "https://media.app-api-graphql.app-api.prod.aws.mybirdbuddy.com/media/feeder/348ec5f8-16b4-48f5-aa93-d8a054fa652e/media/ddadfcfb-57f6-40e2-9df4-96c322a39c06/CONTENT.jpg?Expires=1771719421&Key-Pair-Id=K1HE0EC9UCSK2V&Signature=MEUCIQCIJOWMnGvRKFMtmtV0swynADILY7gjM1m-hQWrbSo2dAIgeVhD8wmvB0Reu-6WLoc3pwhY-o%7Evo%7ExLQomWP5V4a8Q_",
                "https://media.app-api-graphql.app-api.prod.aws.mybirdbuddy.com/media/feeder/348ec5f8-16b4-48f5-aa93-d8a054fa652e/media/e2e4541e-b3a7-4ecf-9243-e848a3a96a33/CONTENT.jpg?Expires=1771719421&Key-Pair-Id=K1HE0EC9UCSK2V&Signature=MEQCIDv3F6e1fEufD%7EOfRqhFIKcHY-HgEhccH8q9K9c1%7Exc%7EAiBx8WTTyv3A0cbPMbxMHooFx2UyXDGCeXj7PdOiWD6Ezg__",
                "https://media.app-api-graphql.app-api.prod.aws.mybirdbuddy.com/media/feeder/348ec5f8-16b4-48f5-aa93-d8a054fa652e/media/1d2e7bb1-8a7d-4dd0-879f-35782ec90104/CONTENT.jpg?Expires=1771719421&Key-Pair-Id=K1HE0EC9UCSK2V&Signature=MEQCIHdSJjK1mr1lKiDCZJ-a1BM6RaxItU-m6780sdphmNwhAiA-Azs1cuiK4oFoXMCQ7PBO0durnD8Nqsic7G5aUFpcAQ__",
            ],
            videos=[],
            # videos=[
            #     "https://media.app-api-graphql.app-api.prod.aws.mybirdbuddy.com/media/feeder/348ec5f8-16b4-48f5-aa93-d8a054fa652e/media/c0d29ef8-b7de-460f-a10d-e5d982e218f1/CONTENT.mp4?Expires=1771719421&Key-Pair-Id=K1HE0EC9UCSK2V&Signature=MEYCIQCBt4G-NMz74BW91adUXDQN8H4biNMFpdEujMQLpLl2IAIhAJ6HdmIzi%7E%7E59UKDKzOnk0FiEPoo944D%7E1OKk-70AbiR",
            # ],
        ),
        _id=None,
        weather=None,
        created_at=datetime(2026, 2, 20, 23, 52, 4, 664000, tzinfo=timezone.utc),
    )

    result = asyncio.run(main(sighting))
    print(result)
