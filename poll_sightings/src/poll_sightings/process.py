import asyncio
import os
from datetime import UTC, datetime, timedelta

from birdbuddy.client import BirdBuddy as BirdBuddyClient
from birdbuddy.client import FeedNodeType, PostcardSighting
from bov_data import DB, Media, MongoClient, Sighting, User
from dotenv import load_dotenv
from google.cloud import tasks_v2
from google.cloud.tasks_v2.types import HttpRequest, OidcToken, Task


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


async def _poll_collections(bb: BirdBuddyClient, since: datetime) -> list[dict]:
    bb_collections = await bb.refresh_collections()
    bb_collections = [
        col
        for col in bb_collections.values()
        if datetime.fromisoformat(col.data["visitLastTime"]) > since
    ]

    fetch_media = [bb.collection(col.collection_id) for col in bb_collections]
    bb_media = await asyncio.gather(*fetch_media)

    return [
        {
            "bb_id": f"collection-{col.collection_id}",
            "created_at": datetime.fromisoformat(col.data["visitLastTime"]),
            "species": [col.bird_name],
            "image_urls": [m.content_url for m in media.values() if not m.is_video],
            "video_urls": [m.content_url for m in media.values() if m.is_video],
        }
        for col, media in zip(bb_collections, bb_media)
    ]


def _get_db() -> DB:
    return MongoClient(os.getenv("MONGODB_URI"))


def _last_updated_at(user: User) -> datetime:
    last_polled = user.bird_buddy.last_polled_at if user.bird_buddy else None
    return last_polled if last_polled is not None else datetime.now(UTC) - timedelta(days=7)


async def _fetch_bb_items(bb: BirdBuddyClient, since: datetime) -> list[dict]:
    bb_postcards, bb_collections = await asyncio.gather(
        _poll_feed(bb, since), _poll_collections(bb, since)
    )

    bb_postcards.extend(bb_collections)
    return bb_postcards


def _dispatch_import_sighting(sighting: Sighting) -> None:
    client = tasks_v2.CloudTasksClient()
    parent = client.queue_path(project="birds-of-vinca", location="us-west3", queue="sightings")
    service_account_email = "cloud-task-invoker@birds-of-vinca.iam.gserviceaccount.com"
    cloud_function_url = "https://import-sighting-560240933279.us-west3.run.app"
    http_request = HttpRequest(
        http_method="POST",
        url=cloud_function_url,
        headers={"Content-type": "application/json"},
        body=sighting.to_json().encode(),
        oidc_token=OidcToken(service_account_email=service_account_email),
    )
    task = Task(http_request=http_request)
    client.create_task(request={"parent": parent, "task": task})


async def main():
    db = _get_db()
    users = db.fetch_users()
    for user in users:
        bb = BirdBuddyClient(user.bird_buddy.user, user.bird_buddy.password)
        since = _last_updated_at(user)
        bb_items = await _fetch_bb_items(bb, since)

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

            _dispatch_import_sighting(sighting)

            since = max(since, sighting.created_at)

        user.bird_buddy.last_polled_at = since
        db.update_user(user._id, bird_buddy=user.bird_buddy)


if __name__ == "__main__":
    load_dotenv()
    asyncio.run(main())
