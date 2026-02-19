import json
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Optional


@dataclass
class BirdFeed:
    brand: str
    product: str


@dataclass
class BirdBuddy:
    user: str
    password: str
    location_zip: str
    feed: BirdFeed
    last_polled_at: Optional[datetime] = None

    def __post_init__(self):
        if isinstance(self.feed, dict):
            self.feed = BirdFeed(**self.feed)


@dataclass
class User:
    email: str
    _id: Optional[str] = None
    bird_buddy: Optional[BirdBuddy] = None
    created_at: Optional[datetime] = None

    def __post_init__(self):
        if isinstance(self.bird_buddy, dict):
            self.bird_buddy = BirdBuddy(**self.bird_buddy)

        if isinstance(self.created_at, str):
            self.created_at = datetime.fromisoformat(self.created_at)


@dataclass
class Weather:
    temperature_f: float
    was_precipitating: bool
    was_cloudy: bool


@dataclass
class Media:
    images: list[str]
    videos: list[str]


@dataclass
class Sighting:
    bb_id: str
    user_id: str
    bird_feed: BirdFeed
    location_zip: str
    species: list[str]
    media: Media
    _id: Optional[str] = None
    weather: Optional[Weather] = None
    created_at: Optional[datetime] = None

    def __post_init__(self):
        if isinstance(self.bird_feed, dict):
            self.bird_feed = BirdFeed(**self.bird_feed)

        if isinstance(self.media, dict):
            self.media = Media(**self.media)

        if isinstance(self.weather, dict):
            self.weather = Weather(**self.weather)

        if isinstance(self.created_at, str):
            self.created_at = datetime.fromisoformat(self.created_at)

    def to_json(self) -> str:
        dictionary = asdict(self)
        dictionary["created_at"] = self.created_at.isoformat()
        return json.dumps(dictionary)
