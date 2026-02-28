import asyncio
import os
from datetime import datetime
from pathlib import Path

import httpx
from bov_data import BirdFeed, Media, Sighting, Weather
from dotenv import load_dotenv

_GRAPH_API_BASE = "https://graph.facebook.com/v21.0"
_MAX_CAROUSEL_ITEMS = 10
_VIDEO_POLL_INTERVAL_SECONDS = 5
_VIDEO_POLL_TIMEOUT_SECONDS = 120


async def post_sighting(
    sighting: Sighting, image_urls: list[str], video_path: str | None
) -> tuple[str | None, str | None]:
    """Post sighting to Instagram. Returns (image_post_url, video_post_url).

    Images and video are posted as separate posts when both are present.
    Images: single image post or carousel.
    Video: regular video post.
    """
    ig_user_id = os.environ["INSTAGRAM_ACCOUNT_ID"]
    token = os.environ["INSTAGRAM_ACCESS_TOKEN"]
    caption = _build_caption(sighting)

    async with httpx.AsyncClient(timeout=30.0) as client:
        image_permalink: str | None = None
        video_permalink: str | None = None

        if image_urls:
            if len(image_urls) == 1:
                media_id = await _post_single_image(
                    client, ig_user_id, token, image_urls[0], caption
                )
            else:
                media_id = await _post_carousel(
                    client, ig_user_id, token, image_urls[:_MAX_CAROUSEL_ITEMS], caption
                )
            image_permalink = await _get_permalink(client, token, media_id)

        if video_path is not None:
            media_id = await _post_reel(client, ig_user_id, token, video_path, caption)
            video_permalink = await _get_permalink(client, token, media_id)

    return image_permalink, video_permalink


def _build_caption(sighting: Sighting) -> str:
    species_str = ", ".join(sighting.species) if sighting.species else "Bird"
    hashtags = " ".join(f"#{s.replace(' ', '').replace('-', '')}" for s in sighting.species)

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
    container_id = await _upload_video_container(
        client, ig_user_id, token, video_path, media_type="REELS", caption=caption
    )
    return await _publish(client, ig_user_id, token, container_id)


async def _upload_video_container(
    client: httpx.AsyncClient,
    ig_user_id: str,
    token: str,
    video_path: str,
    media_type: str = "VIDEO",
    is_carousel_item: bool = False,
    caption: str = "",
) -> str:
    """Upload a video via resumable upload. Returns the container ID once FINISHED."""
    file_size = os.path.getsize(video_path)

    payload: dict = {"media_type": media_type, "upload_type": "resumable"}
    if is_carousel_item:
        payload["is_carousel_item"] = True
    if caption:
        payload["caption"] = caption

    resp = await client.post(
        f"{_GRAPH_API_BASE}/{ig_user_id}/media",
        params={"access_token": token},
        json=payload,
    )
    if resp.is_error:
        raise RuntimeError(f"media container creation failed ({resp.status_code}): {resp.text}")
    data = resp.json()
    container_id: str = data["id"]
    upload_uri: str = data["uri"]

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

    await _poll_until_finished(client, token, container_id)
    return container_id


async def _poll_until_finished(client: httpx.AsyncClient, token: str, container_id: str) -> None:
    """Poll a media container until its status_code is FINISHED."""
    elapsed = 0
    while elapsed < _VIDEO_POLL_TIMEOUT_SECONDS:
        await asyncio.sleep(_VIDEO_POLL_INTERVAL_SECONDS)
        elapsed += _VIDEO_POLL_INTERVAL_SECONDS

        status_resp = await client.get(
            f"{_GRAPH_API_BASE}/{container_id}",
            params={"fields": "status_code", "access_token": token},
        )
        status_resp.raise_for_status()
        status_code = status_resp.json().get("status_code")

        if status_code == "FINISHED":
            return
        if status_code == "ERROR":
            raise RuntimeError(f"Instagram media processing failed for container {container_id}")

    raise TimeoutError(
        f"Container {container_id} did not finish processing within "
        f"{_VIDEO_POLL_TIMEOUT_SECONDS}s"
    )


async def _publish(
    client: httpx.AsyncClient, ig_user_id: str, token: str, container_id: str
) -> str:
    resp = await client.post(
        f"{_GRAPH_API_BASE}/{ig_user_id}/media_publish",
        params={"access_token": token},
        json={"creation_id": container_id},
    )
    if resp.is_error:
        raise RuntimeError(f"media_publish failed ({resp.status_code}): {resp.text}")
    return str(resp.json()["id"])


async def _get_permalink(client: httpx.AsyncClient, token: str, media_id: str) -> str:
    resp = await client.get(
        f"{_GRAPH_API_BASE}/{media_id}",
        params={"fields": "permalink", "access_token": token},
    )
    resp.raise_for_status()
    return str(resp.json()["permalink"])


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
            videos=[
                str(Path(__file__).parent.parent.parent / "tests" / "videos" / "house-finch.mp4")
            ],
        ),
        weather=Weather(temperature_f=42.0, was_cloudy=True, was_precipitating=False),
        created_at=datetime(2026, 2, 26, 10, 30),
    )

    image_urls = sighting.media.images if sighting.media else []
    video_path = sighting.media.videos[0] if sighting.media and sighting.media.videos else None
    image_permalink, video_permalink = await post_sighting(
        sighting, image_urls, video_path=video_path
    )
    print(f"image post: {image_permalink}")
    print(f"video post: {video_permalink}")


if __name__ == "__main__":
    load_dotenv()
    asyncio.run(main())
