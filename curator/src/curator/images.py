import asyncio
import os
from typing import List
from urllib.parse import unquote, urlparse

import httpx
from dotenv import load_dotenv
from openai import OpenAI

from curator.storage import GCS, unique_blob_name


async def curate_images(urls: list[str]) -> list[str]:
    check_images = [_is_bird_visible(url) for url in urls]
    images_analyzed = await asyncio.gather(*check_images)
    images_visible = [url for url, visible in zip(urls, images_analyzed) if visible]
    return await _upload_images(images_visible)

    # TODO: dedup highly similar images


async def _is_bird_visible(imageUrl: str) -> bool:
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    response = client.responses.create(
        model="gpt-5",
        input=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": "Is a bird or squirrel clearly visible showing most of the animal's body? Respond with 'Yes' or 'No'",
                    },
                    {"type": "input_image", "image_url": imageUrl},
                ],
            }
        ],
    )

    return response.output_text == "Yes"


def _filename_from_url(url: str) -> str:
    parsed = urlparse(url)
    filename = unquote(parsed.path.split("/")[-1])
    if not filename:
        raise ValueError(f"Could not determine filename from URL: {url}")
    return filename


async def _upload_single_image(
    client: httpx.AsyncClient,
    bucket,
    url: str,
    semaphore: asyncio.Semaphore,
):
    async with semaphore:
        filename = _filename_from_url(url)
        blob_path = unique_blob_name("images", filename)
        blob = bucket.blob(blob_path)

        response = await client.get(url)
        response.raise_for_status()

        content_type = response.headers.get("Content-Type")

        # GCS client is blocking → offload to thread
        await asyncio.to_thread(
            blob.upload_from_string,
            response.content,
            content_type=content_type,
        )

        return blob_path


async def _upload_images(urls: List[str]):
    bucket = GCS.bucket
    semaphore = asyncio.Semaphore(10)  # Safe default for Cloud Functions

    timeout = httpx.Timeout(10.0, connect=5.0)

    async with httpx.AsyncClient(timeout=timeout) as client:
        tasks = [_upload_single_image(client, bucket, url, semaphore) for url in urls]

        return await asyncio.gather(*tasks)


async def main():
    pass


if __name__ == "__main__":
    load_dotenv()
    asyncio.run(main())
