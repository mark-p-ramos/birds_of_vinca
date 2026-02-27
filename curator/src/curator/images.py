from __future__ import annotations

import asyncio
import os

import httpx
from dotenv import load_dotenv
from openai import OpenAI
from openai.types.responses import EasyInputMessageParam, ResponseInputImageParam


async def curate_images(urls: list[str]) -> list[str]:
    if not urls:
        return []

    return await _curate_and_dedup(urls)


async def _curate_and_dedup(urls: list[str]) -> list[str]:
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    numbered_urls = "\n".join(f"{i + 1}. {url}" for i, url in enumerate(urls))
    image_contents: list[ResponseInputImageParam] = [
        {"type": "input_image", "detail": "auto", "image_url": url} for url in urls
    ]
    message: EasyInputMessageParam = {
        "role": "user",
        "content": [
            {
                "type": "input_text",
                "text": (
                    f"Here are the image URLs in order:\n{numbered_urls}\n\n"
                    "From this group of input images: "
                    "1. ignore images that are out of focus or do not clearly show a bird or squirrel "
                    "2. remove images that are very similar to each other "
                    "3. respond with a list of the remaining image urls from the list above, one per line"
                ),
            },
            *image_contents,
        ],
    }
    response = client.responses.create(
        model="gpt-5",
        input=[message],
    )

    return [
        line.strip()
        for line in response.output_text.splitlines()
        if line.strip().startswith("http")
    ]


async def main() -> None:
    # test URLs from bird buddy sighting
    result = await _curate_and_dedup(
        [
            "https://storage.googleapis.com/birds_of_vinca/images/25008423-63a1-4850-be20-97af3aa5c5c5.jpg",
            "https://storage.googleapis.com/birds_of_vinca/images/902227fa-1440-4fc7-b44a-96c4dfb74a31.jpg",
            "https://storage.googleapis.com/birds_of_vinca/images/a5ddeec0-54b9-41ae-8f5e-96011529f900.jpg",
            "https://storage.googleapis.com/birds_of_vinca/images/0f4fdc0a-157a-4d27-b1e8-821645c50671.jpg",
            "https://storage.googleapis.com/birds_of_vinca/images/c99da8d8-9471-40cd-9b6c-9ff3ac92020b.jpg",
        ]
    )
    print(result)


if __name__ == "__main__":
    load_dotenv()
    asyncio.run(main())
