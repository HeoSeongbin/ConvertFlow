# ruff: noqa: E402
import os
import tempfile
from pathlib import Path

TEST_ROOT = Path(tempfile.mkdtemp(prefix="convertflow-tests-"))
os.environ["DATABASE_URL"] = "sqlite:///" + str(TEST_ROOT / "test.db")
os.environ["STORAGE_ROOT"] = str(TEST_ROOT / "storage")
os.environ["REDIS_URL"] = "redis://localhost:6379/15"

import pytest
from app.core.db import Base, engine
from app.models import job  # noqa: F401


@pytest.fixture(autouse=True)
def database():
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)
