import asyncio
import os
from datetime import UTC, datetime, timedelta

import aiohttp
import functions_framework
import google.api_core.exceptions
import sentry_sdk
from birdbuddy.client import BirdBuddy as BirdBuddyClient
from birdbuddy.client import FeedNodeType, PostcardSighting
from bov_data import DB, Media, MongoClient, Sighting, User
from dotenv import load_dotenv
from flask import Request
from google.cloud import tasks_v2
from google.cloud.tasks_v2.types import HttpRequest, OidcToken, Task
from sentry_sdk.integrations.asyncio import enable_asyncio_integration
from sentry_sdk.integrations.gcp import GcpIntegration

if os.getenv("APP_ENV") == "prod":
    sentry_sdk.init(
        dsn="https://1192a22bf953b2327b2219cfad5f4a44@o4510925100941312.ingest.us.sentry.io/4510925123747840",
        integrations=[GcpIntegration()],
        # Add data like request headers and IP for users,
        # see https://docs.sentry.io/platforms/python/data-management/data-collected/ for more info
        send_default_pii=True,
    )


def _species_from_postcard(bb_sighting: PostcardSighting) -> list[str]:
    return list(
        set(
            [
                report_sighting.species.name
                for report_sighting in bb_sighting.report.sightings
                if report_sighting.is_recognized
            ]
        )
    )


async def _poll_feed(bb: BirdBuddyClient, since: datetime) -> list[dict]:
    MAX_FEED_SIZE = 100

    bb_feed = await bb.feed(first=MAX_FEED_SIZE)
    bb_postcards = bb_feed.filter(newer_than=since, of_type=FeedNodeType.NewPostcard)

    fetch_sightings = [bb.sighting_from_postcard(bb_card.node_id) for bb_card in bb_postcards]
    bb_sightings = await asyncio.gather(*fetch_sightings)

    return [
        {
            "bb_id": f"postcard-{bb_card.data['id']}",
            "created_at": bb_card.created_at,
            "species": _species_from_postcard(bb_sighting),
            "image_urls": [media.content_url for media in bb_sighting.medias],
            "video_urls": [video.content_url for video in bb_sighting.video_media],
        }
        for bb_card, bb_sighting in zip(bb_postcards, bb_sightings)
    ]


def _to_aware(dt: datetime) -> datetime:
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt


async def _poll_collections(bb: BirdBuddyClient, since: datetime) -> list[dict]:
    bb_collections = await bb.refresh_collections()
    bb_collections = [
        col
        for col in bb_collections.values()
        if _to_aware(datetime.fromisoformat(col.data["visitLastTime"])) > since
    ]

    fetch_media = [bb.collection(col.collection_id) for col in bb_collections]
    bb_media = await asyncio.gather(*fetch_media)

    return [
        {
            "bb_id": f"collection-{col.collection_id}",
            "created_at": _to_aware(datetime.fromisoformat(col.data["visitLastTime"])),
            "species": [col.bird_name],
            "image_urls": [m.content_url for m in media.values() if not m.is_video],
            "video_urls": [m.content_url for m in media.values() if m.is_video],
        }
        for col, media in zip(bb_collections, bb_media)
    ]


def _last_updated_at(user: User) -> datetime:
    last_polled = user.bird_buddy.last_polled_at if user.bird_buddy else None
    return last_polled if last_polled is not None else datetime.now(UTC) - timedelta(days=7)


async def _fetch_bb_items(bb: BirdBuddyClient, since: datetime) -> list[dict]:
    MAX_RETRIES = 4
    for attempt in range(MAX_RETRIES + 1):
        try:
            bb_postcards, bb_collections = await asyncio.gather(
                _poll_feed(bb, since), _poll_collections(bb, since)
            )
            return sorted(bb_postcards + bb_collections, key=lambda x: x["created_at"])
        except aiohttp.ContentTypeError:
            # Bird Buddy API intermittently returns this error
            # it doesn't appear to have anything to do with the request
            # and always resolve after a short time so retry before failing
            if attempt < MAX_RETRIES:
                print(f"fetch failed (attempt {attempt + 1}/{MAX_RETRIES + 1}), retrying in 5s...")
                await asyncio.sleep(5)
            else:
                raise


async def _dispatch_import_sighting(sighting: Sighting) -> None:
    PROJECT_ID = "birds-of-vinca"
    LOCATION_ID = "us-west3"
    QUEUE_ID = "sightings"
    SERVICE_ACCOUNT = "cloud-task-invoker@birds-of-vinca.iam.gserviceaccount.com"
    TARGET_URL = "https://import-sighting-eibels3rba-wm.a.run.app"

    client = tasks_v2.CloudTasksAsyncClient()

    http_request = HttpRequest(
        http_method="POST",
        url=TARGET_URL,
        headers={"Content-type": "application/json"},
        body=sighting.to_json().encode(),
        oidc_token=OidcToken(service_account_email=SERVICE_ACCOUNT),
    )

    task = Task(http_request=http_request)
    parent = client.queue_path(project=PROJECT_ID, location=LOCATION_ID, queue=QUEUE_ID)

    try:
        await client.create_task(request={"parent": parent, "task": task})
        print(f"dispatched sighting id: {sighting.bb_id}")
    except google.api_core.exceptions.AlreadyExists:
        pass


async def main():
    enable_asyncio_integration()

    db: DB = MongoClient(os.getenv("MONGODB_URI"))
    users = await db.fetch_users()

    for user in users:
        bb = BirdBuddyClient(user.bird_buddy.user, user.bird_buddy.password)
        since = _last_updated_at(user)
        bb_items = await _fetch_bb_items(bb, since)

        try:
            for bb_item in bb_items:
                sighting = Sighting(
                    bb_id=bb_item["bb_id"],
                    user_id=user._id,
                    bird_feed=user.bird_buddy.feed,
                    location_zip=user.bird_buddy.location_zip,
                    species=bb_item["species"],
                    media=Media(images=bb_item["image_urls"], videos=bb_item["video_urls"]),
                    created_at=bb_item["created_at"],
                )

                await _dispatch_import_sighting(sighting)

                since = sighting.created_at
        finally:
            user.bird_buddy.last_polled_at = since
            await db.update_user(user._id, bird_buddy=user.bird_buddy)


@functions_framework.http
def poll_sightings(request: Request):
    asyncio.run(main())
    return "OK"


if __name__ == "__main__":
    load_dotenv()
    asyncio.run(main())
