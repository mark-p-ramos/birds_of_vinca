from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class User:
    email: str
    bird_buddy_user: Optional[str] = None
    bird_buddy_password: Optional[str] = None
    _id: Optional[str] = None
    feed_type: Optional[str] = None
    last_polled_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


@dataclass
class Weather:
    temperature: float
    is_precipitating: bool
    sky_description: str


@dataclass
class Media:
    images: list[str]
    videos: list[str]


@dataclass
class Sighting:
    bb_id: str
    user_id: str
    feed_type: str
    species: list[str]
    media: Media
    weather: Optional[Weather] = None
    created_at: Optional[datetime] = None
