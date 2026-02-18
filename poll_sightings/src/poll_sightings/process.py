import asyncio
import os
from datetime import UTC, datetime, timedelta

from birdbuddy.client import BirdBuddy, FeedNodeType, PostcardSighting
from bov_data import DB, Media, MongoClient, Sighting, User
from dotenv import load_dotenv


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


async def _poll_feed(bb: BirdBuddy, since: datetime) -> list[dict]:
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


async def _poll_collections(bb: BirdBuddy, since: datetime) -> list[dict]:
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
    return (
        user.last_polled_at
        if user.last_polled_at is not None
        else datetime.now(UTC) - timedelta(days=7)
    )


async def _fetch_bb_items(bb: BirdBuddy, since: datetime) -> list[dict]:
    bb_postcards, bb_collections = await asyncio.gather(
        _poll_feed(bb, since), _poll_collections(bb, since)
    )

    bb_postcards.extend(bb_collections)
    return bb_postcards


def _dispatch_import_sighting(sighting: Sighting) -> None:
    # TODO: hit HTTP endpoint to create a google cloud task
    pass


async def main():
    db = _get_db()
    users = db.fetch_users()
    for user in users:
        bb = BirdBuddy(user.bird_buddy_user, user.bird_buddy_password)
        since = _last_updated_at(user)
        bb_items = await _fetch_bb_items(bb, since)

        for bb_item in bb_items:
            sighting = Sighting(
                bb_id=bb_item["bb_id"],
                user_id=user._id,
                feed_type=user.feed_type,
                species=bb_item["species"],
                media=Media(images=bb_item["image_urls"], videos=bb_item["video_urls"]),
                created_at=bb_item["created_at"],
            )

            _dispatch_import_sighting(sighting)

            since = max(since, sighting.created_at)

        db.update_user(user._id, last_polled_at=since)


if __name__ == "__main__":
    load_dotenv()
    asyncio.run(main())
