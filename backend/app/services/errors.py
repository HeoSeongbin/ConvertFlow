import errno
import random
from dataclasses import dataclass
from billiard.exceptions import SoftTimeLimitExceeded
from PIL import UnidentifiedImageError
from pydantic import ValidationError
from app.core.config import settings
from app.services.validation import InvalidInput

MANUAL_RETRY_CODES = {
    "WORKER_LEASE_EXPIRED",
    "STORAGE_ERROR",
    "TIME_LIMIT_EXCEEDED",
    "RESOURCE_EXHAUSTED",
    "CONVERSION_FAILED",
}


@dataclass(frozen=True)
class Failure:
    code: str
    message: str
    retryable: bool


def classify_error(exc: Exception) -> Failure:
    if isinstance(exc, InvalidInput):
        return Failure(exc.code, str(exc), False)
    if isinstance(exc, ValidationError):
        return Failure("INVALID_OPTIONS", "출력 옵션을 확인하세요.", False)
    if isinstance(exc, FileNotFoundError):
        return Failure("SOURCE_MISSING", "입력 파일 또는 저장 경로가 없습니다.", False)
    if isinstance(exc, UnidentifiedImageError):
        return Failure("DECODE_FAILED", "이미지를 읽을 수 없습니다.", False)
    if isinstance(exc, SoftTimeLimitExceeded):
        return Failure(
            "TIME_LIMIT_EXCEEDED", "작업 처리 시간 제한을 초과했습니다.", True
        )
    if isinstance(exc, MemoryError):
        return Failure("RESOURCE_EXHAUSTED", "Worker 메모리가 부족합니다.", True)
    if isinstance(exc, PermissionError):
        return Failure("STORAGE_ERROR", "파일 저장소 접근 권한을 확인하세요.", False)
    if isinstance(exc, OSError):
        transient = exc.errno not in {
            errno.EACCES,
            errno.EPERM,
            errno.EINVAL,
            errno.ENOENT,
        }
        return Failure("STORAGE_ERROR", "파일 저장소 오류가 발생했습니다.", transient)
    return Failure("CONVERSION_FAILED", "PDF 변환에 실패했습니다.", False)


def retry_delay(retry_number: int) -> float:
    ceiling = min(
        settings.retry_max_seconds,
        settings.retry_base_seconds * 2 ** max(0, retry_number - 1),
    )
    return random.uniform(ceiling / 2, ceiling)
