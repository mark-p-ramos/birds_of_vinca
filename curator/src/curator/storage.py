import os
import uuid
from dataclasses import dataclass

from google.cloud import storage


@dataclass(frozen=True)
class _GCS:
    client: storage.Client = storage.Client(project="birds-of-vinca")

    @property
    def bucket(self) -> storage.Bucket:
        return self.client.bucket("birds_of_vinca")


# Reused across warm invocations (important for performance)
GCS = _GCS()


def unique_blob_name(prefix: str, file_name: str) -> str:
    _, ext = os.path.splitext(file_name)
    return f"{prefix}/{uuid.uuid4()}{ext}"
