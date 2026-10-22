from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)

from app.core.security import validate_password


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)


class ProfileUpdate(StrictInput):
    display_name: str = Field(min_length=1, max_length=100)

    @field_validator("display_name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = value.strip()
        if not value or any(ord(char) < 32 for char in value):
            raise ValueError("Enter a valid display name")
        return value


class LoginInput(StrictInput):
    email: EmailStr
    password: SecretStr = Field(min_length=1, max_length=128)


class RegisterInput(ProfileUpdate):
    email: EmailStr
    password: SecretStr = Field(min_length=12, max_length=128)
    confirm_password: SecretStr

    @model_validator(mode="after")
    def check_passwords(self) -> "RegisterInput":
        validate_password(self.password.get_secret_value())
        if self.password != self.confirm_password:
            raise ValueError("Passwords must match")
        return self


class ForgotPasswordInput(StrictInput):
    email: EmailStr


class ResetPasswordInput(StrictInput):
    token: SecretStr = Field(min_length=32, max_length=128)
    password: SecretStr = Field(min_length=12, max_length=128)
    confirm_password: SecretStr

    @model_validator(mode="after")
    def check_passwords(self) -> "ResetPasswordInput":
        validate_password(self.password.get_secret_value())
        if self.password != self.confirm_password:
            raise ValueError("Passwords must match")
        return self
