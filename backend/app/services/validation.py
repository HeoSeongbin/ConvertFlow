import warnings
from dataclasses import dataclass
from pathlib import Path
from PIL import Image, UnidentifiedImageError
from app.core.config import settings

FORMATS = {
    "PNG": ({".png"}, "image/png"),
    "JPEG": ({".jpg", ".jpeg"}, "image/jpeg"),
    "BMP": ({".bmp"}, "image/bmp"),
    "WEBP": ({".webp"}, "image/webp"),
    "TIFF": ({".tif", ".tiff"}, "image/tiff"),
}


class InvalidInput(ValueError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class ImageInfo:
    mime_type: str
    page_count: int
    pixels: int


def validate_image(path: Path, filename: str, mime: str | None) -> ImageInfo:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path) as image:
                if image.format not in FORMATS:
                    raise InvalidInput(
                        "UNSUPPORTED_FORMAT", "지원하지 않는 이미지 형식입니다."
                    )
                extensions, actual_mime = FORMATS[image.format]
                if (
                    Path(filename).suffix.lower() not in extensions
                    or mime != actual_mime
                ):
                    raise InvalidInput(
                        "INVALID_FILE", "확장자, MIME, 실제 형식이 일치하지 않습니다."
                    )
                pages = getattr(image, "n_frames", 1)
                if pages > settings.max_pages:
                    raise InvalidInput(
                        "PAGE_LIMIT_EXCEEDED", "이미지 페이지 제한을 초과했습니다."
                    )
                if pages > 1 and image.format != "TIFF":
                    raise InvalidInput(
                        "UNSUPPORTED_FORMAT", "다중 프레임은 TIFF만 지원합니다."
                    )
                image.verify()
            pixels = 0
            with Image.open(path) as image:
                for index in range(pages):
                    image.seek(index)
                    count = image.width * image.height
                    if count > settings.max_pixels:
                        raise InvalidInput(
                            "PIXEL_LIMIT_EXCEEDED", "페이지 픽셀 제한을 초과했습니다."
                        )
                    pixels += count
                    if pixels > settings.max_total_pixels:
                        raise InvalidInput(
                            "PIXEL_LIMIT_EXCEEDED", "전체 픽셀 제한을 초과했습니다."
                        )
                    image.load()
            return ImageInfo(actual_mime, pages, pixels)
    except InvalidInput:
        raise
    except (
        UnidentifiedImageError,
        OSError,
        EOFError,
        ValueError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as exc:
        raise InvalidInput(
            "DECODE_FAILED", "이미지의 모든 페이지를 안전하게 읽을 수 없습니다."
        ) from exc
