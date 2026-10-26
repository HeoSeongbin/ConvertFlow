from pathlib import Path
from typing import Protocol
from app.core.config import settings


class Storage(Protocol):
    def path(self, relative: str) -> Path: ...


class LocalStorage:
    def path(self, relative: str) -> Path:
        root = settings.storage_root.resolve()
        target = (root / relative).resolve()
        if not target.is_relative_to(root):
            raise ValueError("Unsafe storage path")
        target.parent.mkdir(parents=True, exist_ok=True)
        return target


storage = LocalStorage()
