"""Backpost existing sightings to Instagram.

Fetches sightings that have GCS media (images or videos) but no Instagram post
URLs yet, posts them to Instagram, and updates the MongoDB documents.

Usage:
    cd curator && .venv/bin/python backpost_instagram.py
"""

import asyncio
import os
import tempfile

import pymongo
import requests
from bov_data import Sighting
from bson.objectid import ObjectId
from dotenv import load_dotenv

from curator.instagram import post_sighting

_GCS_BASE = "https://storage.googleapis.com/birds_of_vinca"


def _to_https_url(path: str) -> str:
    """Convert a GCS blob path or gs:// URI to a public HTTPS URL."""
    if path.startswith("https://"):
        return path
    if path.startswith("gs://"):
        return path.replace("gs://", "https://storage.googleapis.com/", 1)
    return f"{_GCS_BASE}/{path}"


async def _load_sightings(mongo_client: pymongo.AsyncMongoClient) -> list[dict]:
    db = mongo_client.get_database()

    cursor = await db.sightings.aggregate(
        [
            {
                "$match": {
                    "media.instagram_images_post_url": {"$exists": False},
                    "media.instagram_video_post_url": {"$exists": False},
                }
            },
            {"$sample": {"size": 1}},
        ]
    )
    docs = await cursor.to_list()
    return docs


def _doc_to_sighting(doc: dict) -> tuple[ObjectId, Sighting]:
    original_id = doc["_id"]
    doc["_id"] = str(original_id)
    sighting = Sighting(**doc)
    return (original_id, sighting)


async def _post_sighting_to_instagram(sighting: Sighting) -> tuple[str | None, str | None]:
    image_urls = [_to_https_url(p) for p in (sighting.media.images if sighting.media else [])]

    tmp_path: str | None = None
    video_path: str | None = None
    try:
        if sighting.media and sighting.media.videos:
            video_url = _to_https_url(sighting.media.videos[0])
            print(f"  Downloading video: {video_url}")
            resp = requests.get(video_url, stream=True, timeout=60)
            resp.raise_for_status()
            with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
                for chunk in resp.iter_content(chunk_size=65536):
                    tmp.write(chunk)
                tmp_path = tmp.name
            video_path = tmp_path

        print("Posting to Instagram... ")
        try:
            image_permalink, video_permalink = await post_sighting(sighting, image_urls, video_path)
        except RuntimeError as e:
            print(e)
            raise

        return (image_permalink, video_permalink)

    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


async def _update_sighting_document(
    mongo_client: pymongo.AsyncMongoClient,
    id: ObjectId,
    image_permalink: str | None,
    video_permalink: str | None,
) -> None:
    await mongo_client.get_database().sightings.update_one(
        {"_id": id},
        {
            "$set": {
                "media.instagram_images_post_url": image_permalink,
                "media.instagram_video_post_url": video_permalink,
                "media.images": [],
                "media.videos": [],
            }
        },
    )


async def main() -> None:
    mongo_client: pymongo.AsyncMongoClient = pymongo.AsyncMongoClient(os.environ["MONGODB_URI"])
    docs = await _load_sightings(mongo_client)
    print(f"Found {len(docs)} sightings to backpost")

    for doc in docs:
        original_id, sighting = _doc_to_sighting(doc)
        print(f"\nSighting {sighting.bb_id} ({sighting.created_at})")

        image_permalink, video_permalink = await _post_sighting_to_instagram(sighting)
        print(f"  image post: {image_permalink}")
        print(f"  video post: {video_permalink}")

        await _update_sighting_document(mongo_client, original_id, image_permalink, video_permalink)
        print(f"  Updated document {original_id}")

    await mongo_client.close()


if __name__ == "__main__":
    load_dotenv()
    asyncio.run(main())
