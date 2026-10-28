import hashlib
from pathlib import Path


def checksum(path: Path) -> str:
    """Bounded-buffer hashing for inputs and PDFs, independent of file size."""
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()
