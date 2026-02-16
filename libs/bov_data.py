from dataclasses import dataclass

# @dataclass
# class Weather:
#     temperature: float
#     is_precipitating: bool
#     sky_description: str


@dataclass
class Media:
    images: list[str]
    videos: list[str]


@dataclass
class Sighting:
    card_id: str
    created_at: str
    feed_type: str
    species: list[str]
    media: Media
