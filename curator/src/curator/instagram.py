import asyncio
import os
from datetime import datetime

import httpx
from bov_data import Sighting, BirdFeed, Media, Weather
from dotenv import load_dotenv

_GRAPH_API_BASE = "https://graph.facebook.com/v21.0"
_RUPLOAD_BASE = "https://rupload.facebook.com/video-upload/v21.0"
_MAX_CAROUSEL_IMAGES = 10
_REEL_POLL_INTERVAL_SECONDS = 5
_REEL_POLL_TIMEOUT_SECONDS = 120


async def post_sighting(
    sighting: Sighting, image_urls: list[str], video_path: str | None
) -> str:
    """Post sighting to Instagram. Returns the post permalink URL."""
    ig_user_id = os.environ["INSTAGRAM_ACCOUNT_ID"]
    token = os.environ["INSTAGRAM_ACCESS_TOKEN"]
    caption = _build_caption(sighting)

    async with httpx.AsyncClient() as client:
        if video_path is not None:
            media_id = await _post_reel(client, ig_user_id, token, video_path, caption)
        elif len(image_urls) == 1:
            media_id = await _post_single_image(client, ig_user_id, token, image_urls[0], caption)
        else:
            media_id = await _post_carousel(
                client, ig_user_id, token, image_urls[:_MAX_CAROUSEL_IMAGES], caption
            )

        return await _get_permalink(client, token, media_id)


def _build_caption(sighting: Sighting) -> str:
    species_str = ", ".join(sighting.species) if sighting.species else "Bird"
    hashtags = " ".join(
        f"#{s.replace(' ', '').replace('-', '')}" for s in sighting.species
    )

    lines = [f"{species_str} at the feeder! \U0001f426"]
    lines.append(f"Eating: {sighting.bird_feed.product} by {sighting.bird_feed.brand}")

    if sighting.weather:
        weather_parts = [f"{sighting.weather.temperature_f:.0f}\u00b0F"]
        if sighting.weather.was_cloudy:
            weather_parts.append("cloudy")
        if sighting.weather.was_precipitating:
            weather_parts.append("precipitation")
        lines.append(f"Weather: {', '.join(weather_parts)}")

    if sighting.created_at:
        lines.append(sighting.created_at.strftime("%-m/%-d/%Y"))

    lines.append("")
    lines.append(f"#birding #birdwatching #backyardbirds #birdphotography {hashtags}")

    return "\n".join(lines)


async def _post_single_image(
    client: httpx.AsyncClient, ig_user_id: str, token: str, image_url: str, caption: str
) -> str:
    resp = await client.post(
        f"{_GRAPH_API_BASE}/{ig_user_id}/media",
        params={"access_token": token},
        json={"image_url": image_url, "caption": caption},
    )
    resp.raise_for_status()
    container_id = resp.json()["id"]
    return await _publish(client, ig_user_id, token, container_id)


async def _post_carousel(
    client: httpx.AsyncClient,
    ig_user_id: str,
    token: str,
    image_urls: list[str],
    caption: str,
) -> str:
    child_ids = []
    for url in image_urls:
        resp = await client.post(
            f"{_GRAPH_API_BASE}/{ig_user_id}/media",
            params={"access_token": token},
            json={"image_url": url, "is_carousel_item": True},
        )
        resp.raise_for_status()
        child_ids.append(resp.json()["id"])

    resp = await client.post(
        f"{_GRAPH_API_BASE}/{ig_user_id}/media",
        params={"access_token": token},
        json={
            "media_type": "CAROUSEL",
            "caption": caption,
            "children": ",".join(child_ids),
        },
    )
    resp.raise_for_status()
    container_id = resp.json()["id"]
    return await _publish(client, ig_user_id, token, container_id)


async def _post_reel(
    client: httpx.AsyncClient,
    ig_user_id: str,
    token: str,
    video_path: str,
    caption: str,
) -> str:
    file_size = os.path.getsize(video_path)

    # Step 1: Initialize resumable upload session
    resp = await client.post(
        f"{_GRAPH_API_BASE}/{ig_user_id}/media",
        params={"access_token": token},
        json={"media_type": "REELS", "caption": caption, "upload_type": "resumable"},
    )
    resp.raise_for_status()
    data = resp.json()
    container_id = data["id"]
    upload_uri = data["uri"]

    # Step 2: Upload the video file
    with open(video_path, "rb") as f:
        video_bytes = f.read()

    upload_resp = await client.post(
        upload_uri,
        headers={
            "Authorization": f"OAuth {token}",
            "offset": "0",
            "file_size": str(file_size),
            "Content-Type": "video/mp4",
        },
        content=video_bytes,
    )
    upload_resp.raise_for_status()

    # Step 3: Poll until the container finishes processing
    elapsed = 0
    while elapsed < _REEL_POLL_TIMEOUT_SECONDS:
        await asyncio.sleep(_REEL_POLL_INTERVAL_SECONDS)
        elapsed += _REEL_POLL_INTERVAL_SECONDS

        status_resp = await client.get(
            f"{_GRAPH_API_BASE}/{container_id}",
            params={"fields": "status_code", "access_token": token},
        )
        status_resp.raise_for_status()
        status_code = status_resp.json().get("status_code")

        if status_code == "FINISHED":
            break
        if status_code == "ERROR":
            raise RuntimeError(f"Instagram reel processing failed for container {container_id}")

    else:
        raise TimeoutError(
            f"Reel container {container_id} did not finish processing within "
            f"{_REEL_POLL_TIMEOUT_SECONDS}s"
        )

    return await _publish(client, ig_user_id, token, container_id)


async def _publish(
    client: httpx.AsyncClient, ig_user_id: str, token: str, container_id: str
) -> str:
    resp = await client.post(
        f"{_GRAPH_API_BASE}/{ig_user_id}/media_publish",
        params={"access_token": token},
        json={"creation_id": container_id},
    )
    resp.raise_for_status()
    return resp.json()["id"]


async def _get_permalink(client: httpx.AsyncClient, token: str, media_id: str) -> str:
    resp = await client.get(
        f"{_GRAPH_API_BASE}/{media_id}",
        params={"fields": "permalink", "access_token": token},
    )
    resp.raise_for_status()
    return resp.json()["permalink"]


async def main() -> None:
    sighting = Sighting(
        bb_id="test-bb-id",
        user_id="test-user-id",
        bird_feed=BirdFeed(brand="3D Pet Products", product="Sizzle N' Heat"),
        location_zip="12345",
        species=["Black-capped Chickadee"],
        media=Media(
            images=[
                "https://storage.googleapis.com/birds_of_vinca/images/25008423-63a1-4850-be20-97af3aa5c5c5.jpg",
                "https://storage.googleapis.com/birds_of_vinca/images/902227fa-1440-4fc7-b44a-96c4dfb74a31.jpg",
            ],
            videos=[],
        ),
        weather=Weather(temperature_f=42.0, was_cloudy=True, was_precipitating=False),
        created_at=datetime(2026, 2, 26, 10, 30),
    )

    image_urls = sighting.media.images if sighting.media else []
    permalink = await post_sighting(sighting, image_urls, video_path=None)
    print(permalink)


if __name__ == "__main__":
    load_dotenv()
    asyncio.run(main())
