from app.models.user import Principal
from app.services.auth_service import AuthService


class LocalIdentityProvider:
    def __init__(self, service: AuthService) -> None:
        self.service = service

    def authenticate(self, credential: str | None) -> Principal:
        return self.service.authenticate(credential)

    def update_profile(self, user: Principal, name: str, credential: str | None) -> Principal:
        return self.service.update_profile(user, name)
