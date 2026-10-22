from typing import Protocol

from app.models.user import Principal


class IdentityProvider(Protocol):
    def authenticate(self, credential: str | None) -> Principal: ...
    def update_profile(self, user: Principal, name: str, credential: str | None) -> Principal: ...
