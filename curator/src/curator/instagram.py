import asyncio
import json
import os

import httpx
from bov_data import Sighting

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
            image_permalink = await _post_sighting_image(
                client, ig_user_id, token, image_urls, caption
            )

        if video_path is not None:
            video_permalink = await _post_sighting_video(
                client, ig_user_id, token, video_path, caption
            )

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

    lines.append("")
    lines.append(f"#birding #birdwatching #backyardbirds #birdphotography {hashtags}")

    return "\n".join(lines)


def is_ig_spam(e: RuntimeError) -> bool:
    try:
        body = json.loads(str(e).split(": ", 1)[1])
        ig_error = body.get("error", {})
    except (ValueError, IndexError):
        return False

    return bool(ig_error.get("code") == 4 and ig_error.get("error_subcode") == 2207051)


async def _post_sighting_video(
    client: httpx.AsyncClient, ig_user_id: str, token: str, video_path: str, caption: str
) -> str:
    media_id = await _post_reel(client, ig_user_id, token, video_path, caption)
    return await _get_permalink(client, token, media_id)


async def _post_sighting_image(
    client: httpx.AsyncClient, ig_user_id: str, token: str, image_urls: list[str], caption: str
) -> str:
    if len(image_urls) == 1:
        media_id = await _post_single_image(client, ig_user_id, token, image_urls[0], caption)
    else:
        media_id = await _post_carousel(
            client, ig_user_id, token, image_urls[:_MAX_CAROUSEL_ITEMS], caption
        )
    return await _get_permalink(client, token, media_id)


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
    await _poll_until_finished(client, token, container_id)
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
