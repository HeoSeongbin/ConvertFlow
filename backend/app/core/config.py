from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import Field, model_validator


class Settings(BaseSettings):
    database_url: str = (
        "postgresql+psycopg://convertflow:convertflow@postgres/convertflow"
    )
    redis_url: str = "redis://redis:6379/0"
    storage_root: Path = Path("/data")
    max_upload_bytes: int = 20 * 1024 * 1024
    max_pixels: int = 25_000_000
    max_files: int = 20
    max_pages: int = 100
    max_total_pixels: int = 100_000_000
    max_total_upload_bytes: int = 100 * 1024 * 1024
    max_auto_retries: int = 3
    retry_base_seconds: int = 5
    retry_max_seconds: int = 300
    lease_seconds: int = Field(default=30, ge=3)
    heartbeat_seconds: int = Field(default=5, ge=1)
    redispatch_seconds: int = Field(default=30, ge=3)

    @model_validator(mode="after")
    def lease_interval(self):
        if self.heartbeat_seconds * 2 >= self.lease_seconds:
            raise ValueError("heartbeat_seconds must be less than half lease_seconds")
        return self

    cors_origin: str = "http://localhost:8080"


settings = Settings()
