import asyncio
import os

from dotenv import load_dotenv
from openai import OpenAI


async def is_animal_visible(imageUrl: str) -> bool:
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


async def main():
    # dark finch in the seeds
    # image_url = "https://media.app-api-graphql.app-api.prod.aws.mybirdbuddy.com/media/feeder/348ec5f8-16b4-48f5-aa93-d8a054fa652e/media/c009d425-21e9-4407-be42-85b29a70ad01/CONTENT.jpg?maxWidth=640&Expires=1771183767&Key-Pair-Id=K1HE0EC9UCSK2V&Signature=MEYCIQDEwMMtQJ-6Q64DicpKd5rCqFZ3bhuntrdMpkcOG-MbsQIhAJOPxcRalovOVGcrnXxi37qT9yhkEUEzAmf0P-kBuxzl"

    # partial face of finch
    # image_url = "https://media.app-api-graphql.app-api.prod.aws.mybirdbuddy.com/media/feeder/348ec5f8-16b4-48f5-aa93-d8a054fa652e/media/a837bf01-ceb6-4fff-a1b9-f310233f2870/CONTENT.jpg?maxWidth=640&Expires=1771184014&Key-Pair-Id=K1HE0EC9UCSK2V&Signature=MEYCIQCjs-JqeDOkIbKLxM7E-MHgev46GEbtS4t0WD9ODcuKHAIhAP6DkJChrdT3C-dXO4lgV6hOuCDdRRNblrD-KLReSR9Q"

    # flicker frontal with beak off the screen
    image_url = "https://media.app-api-graphql.app-api.prod.aws.mybirdbuddy.com/media/feeder/348ec5f8-16b4-48f5-aa93-d8a054fa652e/media/bc4921d0-93e7-46bf-90e2-a736b678b95c/CONTENT.jpg?maxWidth=640&Expires=1771184057&Key-Pair-Id=K1HE0EC9UCSK2V&Signature=MEYCIQCCj3eTZJwpzgDjZmi1T2e5sydYzteqQib6V9E9sb3CSgIhAM7POt5xHrZB5MNByvTN37SLSKCfW6sOTJSuHIS7AXX0"
    result = await is_animal_visible(image_url)
    print(result)
    pass


if __name__ == "__main__":
    load_dotenv()
    asyncio.run(main())
