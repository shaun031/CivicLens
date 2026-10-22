import re
from typing import Protocol


class StorageUnavailable(Exception):
    pass


class StorageCollision(StorageUnavailable):
    """A generated key already exists; the caller must not delete that object."""


def validate_key(key: str) -> None:
    uuid = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
    if not re.fullmatch(rf"complaints/{uuid}/{uuid}\.jpg", key):
        raise StorageUnavailable("Invalid evidence key")


class EvidenceStorage(Protocol):
    def put(self, key: str, data: bytes) -> None: ...
    def get(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...
