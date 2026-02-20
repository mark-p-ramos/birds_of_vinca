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
    # -- test upload images --
    # urls = [
    #     "https://media.app-api-graphql.app-api.prod.aws.mybirdbuddy.com/media/feeder/348ec5f8-16b4-48f5-aa93-d8a054fa652e/media/fe1eb837-07b6-44ce-99d2-4fb669701958/CONTENT.jpg?maxWidth=640&Expires=1771686528&Key-Pair-Id=K1HE0EC9UCSK2V&Signature=MEYCIQCPfPe9wRpLUhbInJI8KiwOsJPaQqX3LNYOcRFO7-RIPgIhAMg6hgg8-zZwph6e4E%7EAufyB93MBGbeaxBGORoh6Yvxb",
    #     "https://media.app-api-graphql.app-api.prod.aws.mybirdbuddy.com/media/feeder/348ec5f8-16b4-48f5-aa93-d8a054fa652e/media/3513354a-fd72-4118-bd30-b45ab56bf101/CONTENT.jpg?maxWidth=640&Expires=1771686568&Key-Pair-Id=K1HE0EC9UCSK2V&Signature=MEYCIQDDWi-HOl8IdH-m17phgKn23mQ33jKBeoUHex6q2ovWYAIhAJc33UBGlKWfNhbOyNcVWKzUiKJ6g2KHjRPbCZ0MrRZi",
    # ]
    # new_urls = await _upload_images(urls)
    # print(new_urls)
    pass


if __name__ == "__main__":
    load_dotenv()
    asyncio.run(main())
