from pathlib import Path
from pydantic_settings import BaseSettings


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
    cors_origin: str = "http://localhost:8080"


settings = Settings()
