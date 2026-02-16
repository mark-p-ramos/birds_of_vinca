import asyncio
import os
from datetime import UTC, datetime, timedelta

from birdbuddy.client import BirdBuddy
from bov_data import Media, Sighting
from dotenv import load_dotenv


async def fetch_sightings() -> list[Sighting]:
    bb_user = os.getenv("BIRD_BUDDY_USER")
    bb_password = os.getenv("BIRD_BUDDY_PASSWORD")
    bb = BirdBuddy(bb_user, bb_password)

    # get the last day
    sinceDate = datetime.now(UTC) - timedelta(hours=12)
    postcards = await bb.refresh_feed(since=sinceDate)

    output = []

    for card in postcards:
        if (
            card.get("__typename") == "FeedItemNewPostcard"
        ):  # what other cards are there? is this necessary?
            sighting = await bb.sighting_from_postcard(card.get("id"))

            species = list(
                set(
                    [
                        report_sighting.species.name
                        for report_sighting in sighting.report.sightings
                        if report_sighting.is_recognized
                    ]
                )
            )
            image_urls = [media.content_url for media in sighting.medias]
            video_urls = [video.content_url for video in sighting.video_media]

            output.append(
                Sighting(
                    card_id=card.data["id"],
                    created_at=card.created_at.isoformat(),
                    feed_type="TODO",
                    species=species,
                    media=Media(image_urls, video_urls),
                )
            )

    return output


async def main():
    sightings = await fetch_sightings()
    for sighting in sightings:
        print(f"{sighting.created_at} {sighting.species[0] if sighting.species else 'unknown'}")
    pass


if __name__ == "__main__":
    load_dotenv()
    asyncio.run(main())
