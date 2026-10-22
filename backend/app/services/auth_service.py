import json
import os
import sqlite3
import time
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import HTTPException

from app.core.config import Settings
from app.core.security import (
    hash_password,
    password_hasher,
    random_token,
    token_hash,
    verify_password,
)
from app.models.user import Principal, Role
from app.repositories.auth_store import AuthStore
from app.schemas.auth import ProfileUpdate, RegisterInput


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def principal_from_row(row: sqlite3.Row) -> Principal:
    return Principal(
        id=row["id"],
        email=row["email"],
        display_name=row["display_name"],
        role=Role(row["role"]),
        provider="local",
        is_active=bool(row["is_active"]),
        is_verified=bool(row["is_verified"]),
    )


class AuthService:
    def __init__(self, settings: Settings) -> None:
        if settings.app_env not in ("local", "test") or settings.auth_provider != "local":
            raise ValueError("Local authentication is disabled outside local/test environments")
        self.settings = settings
        self.store = AuthStore(settings.local_db_path)
        self._dummy_hash = hash_password(random_token())

    def rate_limit(self, bucket: str, limit: int = 5, window: int = 900) -> None:
        now = int(time.time())
        with self.store.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM rate_limits WHERE expires_at <= ?", (now,))
            key = token_hash(bucket)
            record = db.execute("SELECT * FROM rate_limits WHERE bucket=?", (key,)).fetchone()
            if record and record["attempts"] >= limit:
                raise HTTPException(
                    429,
                    "Too many attempts. Try again later.",
                    headers={"Retry-After": str(record["expires_at"] - now)},
                )
            db.execute(
                "INSERT INTO rate_limits VALUES (?,1,?) "
                "ON CONFLICT(bucket) DO UPDATE SET attempts=attempts+1",
                (key, now + window),
            )

    def register(self, data: RegisterInput, role: Role = Role.CITIZEN) -> Principal:
        user_id, timestamp = str(uuid4()), now_iso()
        try:
            with self.store.connection() as db:
                db.execute(
                    "INSERT INTO users(id,email,display_name,password_hash,role,"
                    "created_at,updated_at) "
                    "VALUES (?,?,?,?,?,?,?)",
                    (
                        user_id,
                        str(data.email).casefold(),
                        data.display_name,
                        hash_password(data.password.get_secret_value()),
                        role.value,
                        timestamp,
                        timestamp,
                    ),
                )
                row = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        except sqlite3.IntegrityError as error:
            raise HTTPException(409, "An account with this email cannot be registered.") from error
        return principal_from_row(row)

    def login(
        self, email: str, password: str, ip: str, previous_token: str | None
    ) -> tuple[Principal, str]:
        email = email.casefold()
        self.rate_limit(f"login-ip:{ip}", limit=20)
        self.rate_limit(f"login:{ip}:{email}")
        with self.store.connection() as db:
            row = db.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
            valid = verify_password(row["password_hash"] if row else self._dummy_hash, password)
            if not row or not valid or not row["is_active"] or not row["is_verified"]:
                raise HTTPException(401, "Invalid email or password.")
            token = random_token()
            if previous_token:
                db.execute("DELETE FROM sessions WHERE token_hash=?", (token_hash(previous_token),))
            db.execute("DELETE FROM sessions WHERE expires_at <= ?", (int(time.time()),))
            db.execute(
                "INSERT INTO sessions VALUES (?,?,?)",
                (
                    token_hash(token),
                    row["id"],
                    int(time.time()) + self.settings.session_ttl_seconds,
                ),
            )
            db.execute("UPDATE users SET last_login_at=? WHERE id=?", (now_iso(), row["id"]))
            db.execute(
                "DELETE FROM rate_limits WHERE bucket=?", (token_hash(f"login:{ip}:{email}"),)
            )
            if password_hasher.check_needs_rehash(row["password_hash"]):
                db.execute(
                    "UPDATE users SET password_hash=? WHERE id=?",
                    (hash_password(password), row["id"]),
                )
        return principal_from_row(row), token

    def authenticate(self, token: str | None) -> Principal:
        if not token or len(token) > 128:
            raise HTTPException(401, "Authentication required.")
        with self.store.connection() as db:
            row = db.execute(
                "SELECT users.* FROM users JOIN sessions ON sessions.user_id=users.id "
                "WHERE sessions.token_hash=? AND sessions.expires_at>? "
                "AND users.is_active=1 AND users.is_verified=1",
                (token_hash(token), int(time.time())),
            ).fetchone()
        if not row:
            raise HTTPException(401, "Authentication required.")
        return principal_from_row(row)

    def logout(self, token: str | None) -> None:
        if token:
            with self.store.connection() as db:
                db.execute("DELETE FROM sessions WHERE token_hash=?", (token_hash(token),))

    def update_profile(self, user: Principal, name: str) -> Principal:
        name = ProfileUpdate(display_name=name).display_name
        with self.store.connection() as db:
            db.execute(
                "UPDATE users SET display_name=?,updated_at=? WHERE id=?",
                (name, now_iso(), user.id),
            )
            row = db.execute("SELECT * FROM users WHERE id=?", (user.id,)).fetchone()
        return principal_from_row(row)

    def request_reset(self, email: str) -> None:
        with self.store.connection() as db:
            row = db.execute(
                "SELECT id FROM users WHERE email=? AND is_active=1", (email.casefold(),)
            ).fetchone()
            if not row:
                return
            token = random_token()
            db.execute("DELETE FROM password_resets WHERE user_id=?", (row["id"],))
            db.execute(
                "INSERT INTO password_resets VALUES (?,?,?)",
                (token_hash(token), row["id"], int(time.time()) + self.settings.reset_ttl_seconds),
            )
            outbox = self.store.path.parent / "outbox"
            outbox.mkdir(parents=True, exist_ok=True)
            # Private development outbox only; never returned by an HTTP endpoint or logged.
            path = outbox / f"{uuid4()}.json"
            with os.fdopen(
                os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w", encoding="utf-8"
            ) as message:
                json.dump(
                    {
                        "email": email.casefold(),
                        "reset_url": f"http://localhost:5173/reset-password#token={token}",
                    },
                    message,
                )

    def reset_password(self, token: str, password: str) -> None:
        new_hash = hash_password(password)
        with self.store.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT user_id FROM password_resets WHERE token_hash=? AND expires_at>?",
                (token_hash(token), int(time.time())),
            ).fetchone()
            if not row:
                raise HTTPException(400, "Reset link is invalid or expired.")
            db.execute(
                "UPDATE users SET password_hash=?,updated_at=? WHERE id=?",
                (new_hash, now_iso(), row["user_id"]),
            )
            db.execute("DELETE FROM password_resets WHERE user_id=?", (row["user_id"],))
            db.execute("DELETE FROM sessions WHERE user_id=?", (row["user_id"],))
