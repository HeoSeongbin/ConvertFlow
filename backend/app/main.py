from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from redis import Redis
from sqlalchemy import text
from app.api.routes import router
from app.core.config import settings
from app.core.db import engine
from app.core.logging import configure_logging

configure_logging()
app = FastAPI(title="ConvertFlow", version="0.4.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.cors_origin],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-Job-Token"],
)
app.include_router(router)


@app.get("/health/live")
def live():
    return {"status": "alive"}


@app.get("/health/ready")
def ready():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        Redis.from_url(
            settings.redis_url, socket_connect_timeout=2, socket_timeout=2
        ).ping()
    except Exception as exc:
        raise HTTPException(503, "Dependencies unavailable") from exc
    return {"status": "ready"}
