import os
import stat
from contextlib import suppress
from pathlib import Path

from app.integrations.storage.base import StorageCollision, StorageUnavailable, validate_key


class LocalEvidence:
    def __init__(self, root: Path, max_bytes: int):
        self.root = Path(os.path.abspath(root))
        self.max_bytes = max_bytes

    def path(self, key: str, create: bool = False) -> Path:
        validate_key(key)
        result = self.root.joinpath(*key.split("/"))
        # Reject symlinks and Windows directory junctions, including configured ancestors.
        for component in [*reversed(result.parents), result]:
            if component.is_symlink() or component.is_junction():
                raise StorageUnavailable("Unsafe evidence path")
        if create:
            self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
            (self.root / "complaints").mkdir(exist_ok=True, mode=0o700)
            result.parent.mkdir(exist_ok=True, mode=0o700)
        return result

    def put(self, key: str, data: bytes) -> None:
        if not data or len(data) > self.max_bytes:
            raise StorageUnavailable("Invalid evidence size")
        path = None
        owned = False
        try:
            path = self.path(key, create=True)
            descriptor = os.open(
                path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600
            )
            owned = True
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
        except FileExistsError as error:
            raise StorageCollision("Evidence key already exists") from error
        except (OSError, StorageUnavailable) as error:
            if owned and path is not None:
                with suppress(OSError):
                    path.unlink(missing_ok=True)
            raise StorageUnavailable("Evidence could not be saved") from error

    def get(self, key: str) -> bytes:
        try:
            path = self.path(key)
            descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            with os.fdopen(descriptor, "rb") as stream:
                if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                    raise StorageUnavailable("Invalid evidence object")
                data = stream.read(self.max_bytes + 1)
            if len(data) > self.max_bytes:
                raise StorageUnavailable("Invalid evidence size")
            return data
        except (OSError, StorageUnavailable) as error:
            raise StorageUnavailable("Evidence is unavailable") from error

    def delete(self, key: str) -> None:
        try:
            self.path(key).unlink(missing_ok=True)
        except (OSError, StorageUnavailable) as error:
            raise StorageUnavailable("Evidence cleanup failed") from error
