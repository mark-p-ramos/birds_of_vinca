import asyncio
import os
from datetime import UTC, datetime, timedelta

from birdbuddy.client import BirdBuddy, PostcardSighting
from bov_data import DB, Media, MongoClient, Sighting, User
from dotenv import load_dotenv


def _to_sighting_props(bb_sighting: PostcardSighting) -> dict:
    species = list(
        set(
            [
                report_sighting.species.name
                for report_sighting in bb_sighting.report.sightings
                if report_sighting.is_recognized
            ]
        )
    )

    image_urls = [media.content_url for media in bb_sighting.medias]
    video_urls = [video.content_url for video in bb_sighting.video_media]

    return {
        "species": species,
        "media": Media(image_urls, video_urls),
    }


async def _poll_sightings(user: User) -> list[Sighting]:
    bb = BirdBuddy(user.bird_buddy_user, user.bird_buddy_password)

    bb_postcards = [
        bb_card
        for bb_card in await bb.refresh_feed(since=user.last_polled_at)
        if bb_card.get("__typename") == "FeedItemNewPostcard"
    ]

    coroutines = [bb.sighting_from_postcard(bb_card.get("id")) for bb_card in bb_postcards]
    bb_sightings = await asyncio.gather(*coroutines)

    return [
        Sighting(
            card_id=bb_card.data["id"],
            user_id=user._id,
            created_at=bb_card.created_at,
            feed_type=user.feed_type,
            **_to_sighting_props(bb_sightings[i]),
        )
        for i, bb_card in enumerate(bb_postcards)
    ]


def _get_db() -> DB:
    return MongoClient(os.getenv("MONGODB_URI"))


async def main():
    db = _get_db()
    users = db.fetch_users()
    for user in users:
        # debugging: remove this
        user.last_polled_at = datetime.now(UTC) - timedelta(hours=4)

        sightings = await _poll_sightings(user)
        for sighting in sightings:
            # TODO: create cloud task
            print(f"{sighting.species[0] if sighting.species else 'unknown'} {sighting.created_at}")


if __name__ == "__main__":
    load_dotenv()
    asyncio.run(main())
