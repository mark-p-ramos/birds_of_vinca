from typing import Optional, Protocol

from bov_data.data import BirdBuddy, Sighting, User


class DB(Protocol):
    def fetch_users(self) -> list[User]: ...

    def update_user(
        self, id: str, bird_buddy: Optional[BirdBuddy] = None
    ) -> None: ...

    def create_sighting(self) -> str: ...

    def fetch_sightings(self, page: int = 0, per_page: int = 20) -> list[Sighting]: ...
