from typing import Optional, Protocol

from bov_data.data import Sighting, User


class DB(Protocol):
    def fetch_users(self) -> list[User]: ...

    def update_user(
        self, id: str, feed_type: Optional[str] = None, last_polled_at: Optional[str] = None
    ) -> None: ...

    def create_sighting(self) -> str: ...

    def fetch_sightings(self, page: int = 0, per_page: int = 20) -> list[Sighting]: ...
