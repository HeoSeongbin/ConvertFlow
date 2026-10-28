from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from app.core.config import settings


class Base(DeclarativeBase):
    pass


engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    connect_args={
        "connect_timeout": 3,
        "options": "-c statement_timeout=5000 -c lock_timeout=3000",
    }
    if settings.database_url.startswith("postgresql")
    else {},
)
Session = sessionmaker(engine, expire_on_commit=False)
