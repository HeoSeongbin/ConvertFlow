import io
from collections.abc import Callable
from pathlib import Path
from typing import Protocol
from PIL import Image, ImageOps
from pypdf import PdfReader, PdfWriter, Transformation
from pypdf.generic import RectangleObject
from app.schemas.options import ConversionOptions
from app.services.validation import InvalidInput

ProgressCallback = Callable[[int, int, int], None]


class FileConverter(Protocol):
    def convert(
        self,
        sources: list[Path],
        destination: Path,
        options: ConversionOptions,
        on_page: ProgressCallback | None = None,
    ) -> int: ...


def page_geometry(width: float, height: float, options: ConversionOptions):
    pw, ph = {
        "original": (width, height),
        "A4": (210 * 72 / 25.4, 297 * 72 / 25.4),
        "Letter": (612, 792),
    }[options.page_size]
    if (
        options.orientation == "portrait"
        and pw > ph
        or options.orientation == "landscape"
        and pw < ph
    ):
        pw, ph = ph, pw
    margin = options.margin_mm * 72 / 25.4
    available_w, available_h = pw - margin * 2, ph - margin * 2
    if min(available_w, available_h) <= 0:
        raise InvalidInput("INVALID_OPTIONS", "여백이 페이지 크기보다 큽니다.")
    scale = (min if options.fit == "contain" else max)(
        available_w / width, available_h / height
    )
    return (
        pw,
        ph,
        scale,
        (pw - width * scale) / 2,
        (ph - height * scale) / 2,
        available_w,
        available_h,
    )


class ImagePDFConverter:
    def convert(
        self,
        sources: list[Path] | Path,
        destination: Path,
        options: ConversionOptions | None = None,
        on_page: ProgressCallback | None = None,
    ) -> int:
        options = options or ConversionOptions()
        sources = [sources] if isinstance(sources, Path) else sources
        writer = PdfWriter()
        count = 0
        try:
            for file_index, source in enumerate(sources):
                with Image.open(source) as original:
                    frames = getattr(original, "n_frames", 1)
                    for frame_index in range(frames):
                        original.seek(frame_index)
                        original.load()
                        stream = io.BytesIO()
                        with ImageOps.exif_transpose(original) as oriented:
                            if oriented.mode == "RGB":
                                # Opaque RGB needs neither an RGBA copy nor a white canvas.
                                oriented.save(
                                    stream,
                                    "PDF",
                                    resolution=96.0,
                                    quality=options.quality,
                                )
                            else:
                                with oriented.convert("RGBA") as image:
                                    with Image.new(
                                        "RGB", image.size, "white"
                                    ) as background:
                                        background.paste(
                                            image, mask=image.getchannel("A")
                                        )
                                        background.save(
                                            stream,
                                            "PDF",
                                            resolution=96.0,
                                            quality=options.quality,
                                        )
                        source_page = PdfReader(stream).pages[0]
                        width, height = (
                            float(source_page.mediabox.width),
                            float(source_page.mediabox.height),
                        )
                        pw, ph, scale, x, y, aw, ah = page_geometry(
                            width, height, options
                        )
                        if options.fit == "cover":
                            cx, cy = (width - aw / scale) / 2, (height - ah / scale) / 2
                            source_page.cropbox = RectangleObject(
                                (cx, cy, width - cx, height - cy)
                            )
                        page = writer.add_blank_page(pw, ph)
                        page.merge_transformed_page(
                            source_page, Transformation().scale(scale).translate(x, y)
                        )
                        count += 1
                        if on_page:
                            on_page(file_index, frame_index + 1, count)
            writer.write(destination)
            validate_pdf(destination, count)
            return count
        finally:
            writer.close()


def validate_pdf(path: Path, expected_pages: int = 1):
    if (
        path.stat().st_size == 0
        or len(PdfReader(path, strict=True).pages) != expected_pages
    ):
        raise ValueError("Invalid PDF output")
