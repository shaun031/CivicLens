import base64
import hashlib
import json
import math

from fastapi import HTTPException


def context_hash(context: dict) -> str:
    return hashlib.sha256(
        json.dumps(context, sort_keys=True, default=str, separators=(",", ":")).encode()
    ).hexdigest()


def pack_cursor(context: dict, key: list) -> str:
    return (
        base64.urlsafe_b64encode(
            json.dumps(
                {"v": 5, "context": context_hash(context), "key": key}, separators=(",", ":")
            ).encode()
        )
        .decode()
        .rstrip("=")
    )


def unpack_cursor(value: str | None, context: dict, lengths: tuple[int, ...]) -> list | None:
    if not value:
        return None
    try:
        if len(value) > 2048:
            raise ValueError
        data = json.loads(
            base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
        )
        key = data["key"]
        if isinstance(key, list) and any(
            (isinstance(item, float) and not math.isfinite(item))
            or (isinstance(item, str) and (len(item) > 512 or any(ord(char) < 32 for char in item)))
            for item in key
        ):
            raise ValueError
        if (
            data["v"] != 5
            or data["context"] != context_hash(context)
            or not isinstance(key, list)
            or len(key) not in lengths
            or any(
                not isinstance(item, (str, int, float)) or isinstance(item, bool) for item in key
            )
        ):
            raise ValueError
        return key
    except (ValueError, TypeError, KeyError, UnicodeError) as error:
        raise HTTPException(400, "Invalid cursor or changed query context.") from error
