import base64
import hashlib
import json
from uuid import UUID

from fastapi import HTTPException


def encode_cursor(owner: str, backend: str, key: dict) -> str:
    payload = {
        "v": 1,
        "owner": hashlib.sha256(owner.encode()).hexdigest(),
        "backend": backend,
        "key": key,
    }
    return (
        base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode())
        .decode()
        .rstrip("=")
    )


def decode_cursor(value: str | None, owner: str, backend: str) -> dict | None:
    if not value:
        return None
    try:
        if len(value) > 2048:
            raise ValueError
        data = json.loads(
            base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
        )
        if (
            data["v"] != 1
            or data["owner"] != hashlib.sha256(owner.encode()).hexdigest()
            or data["backend"] != backend
        ):
            raise ValueError
        key = data["key"]
        if set(key) != {"createdAt", "complaintId", "citizenId"} or key["citizenId"] != owner:
            raise ValueError
        UUID(key["complaintId"])
        from datetime import datetime

        timestamp = datetime.fromisoformat(key["createdAt"])
        if timestamp.tzinfo is None:
            raise ValueError
        return key
    except (ValueError, TypeError, KeyError, AttributeError, UnicodeError) as error:
        raise HTTPException(400, "Invalid pagination cursor.") from error
