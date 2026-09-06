from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    db_backend: Literal["sql", "mongo"] = "sql"
    database_url: str = "sqlite:///./gym_saas.db"
    mongodb_url: str = ""
    mongodb_database: str = "gym_nexus"
    jwt_secret_key: str = "change_this_to_a_real_secret"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_fallback_port: int = 2525
    smtp_timeout: int = 10
    smtp_use_ssl: bool = False
    smtp_user: str = ""
    smtp_password: str = ""
    from_email: str = ""
    brevo_api_key: str = ""
    brevo_sender_name: str = "GYM-NEXUS"
    scheduler_enabled: bool = True
    public_url: str = ""  # optional public base URL used in emails (e.g. https://app.example.com)

    @field_validator("mongodb_url")
    @classmethod
    def validate_mongodb_url(cls, value: str) -> str:
        if value and not value.startswith(("mongodb://", "mongodb+srv://")):
            raise ValueError("MONGODB_URL must start with mongodb:// or mongodb+srv://")
        return value

    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_webhook_secret: str = ""

    r2_account_id: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket_name: str = ""
    r2_endpoint_url: str = ""
    r2_public_url: str = ""

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")


settings = Settings()
