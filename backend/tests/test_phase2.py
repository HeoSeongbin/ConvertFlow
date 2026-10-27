import io
import json
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from pypdf import PdfReader
from sqlalchemy import select, func
from app.main import app
from app.core.db import Session
from app.core.config import settings
from app.models.job import Job, JobFile, Result, Event, Outbox
from app.schemas.options import ConversionOptions
from app.converters.image_pdf import page_geometry
from app.tasks.convert import convert_job
from app.storage.local import storage


def raster(color="red", format="PNG", frames=None):
    stream = io.BytesIO()
    image = Image.new("RGB", (80, 40), color)
    image.save(
        stream,
        format,
        save_all=bool(frames),
        append_images=[Image.new("RGB", (80, 40), c) for c in frames or []]
        if format == "TIFF"
        else [],
    )
    return stream.getvalue()


def submit(client, options=None, files=None):
    response = client.post(
        "/api/v1/jobs",
        files=files
        or [
            ("file", ("first.tiff", raster("green", "TIFF", ["blue"]), "image/tiff")),
            ("file", ("last.png", raster("red"), "image/png")),
        ],
        data={"options": json.dumps(options or {})},
    )
    assert response.status_code == 202, response.text
    return response.json()


def test_file_frame_order_and_options():
    client = TestClient(app)
    job = submit(
        client,
        {
            "pageSize": "A4",
            "orientation": "landscape",
            "marginMm": 12,
            "fit": "contain",
            "quality": 85,
        },
    )
    assert job["totalFiles"] == 2 and job["totalPages"] == 3
    convert_job.run(job["jobId"])
    detail = client.get(f"/api/v1/jobs/{job['jobId']}").json()
    assert detail["processedFiles"] == 2 and detail["processedPages"] == 3
    assert [f["filename"] for f in detail["files"]] == ["first.tiff", "last.png"]
    assert [f["pageCount"] for f in detail["files"]] == [2, 1]
    assert detail["options"]["marginMm"] == 12
    result = client.get(f"/api/v1/jobs/{job['jobId']}/download")
    reader = PdfReader(io.BytesIO(result.content))
    assert len(reader.pages) == 3
    for page, expected_channel in zip(reader.pages, [1, 2, 0]):
        assert float(page.mediabox.width) == pytest.approx(297 * 72 / 25.4)
        assert float(page.mediabox.height) == pytest.approx(210 * 72 / 25.4)
        rgb = page.images[0].image.convert("RGB").getpixel((10, 10))
        assert (
            rgb[expected_channel]
            > max(rgb[i] for i in range(3) if i != expected_channel) + 80
        )
    events = client.get(f"/api/v1/jobs/{job['jobId']}/events").json()["items"]
    assert [
        e["details"]["processedPages"] for e in events if e["type"] == "PAGE_PROCESSED"
    ] == [1, 2, 3]
    assert events[-1]["type"] == "SUCCESS"
    assert [e["sequence"] for e in events] == list(range(1, len(events) + 1))
    with Session() as db:
        assert db.scalar(select(func.count()).select_from(Result)) == 1


@pytest.mark.parametrize(
    "options",
    [
        {"quality": 0},
        {"quality": 101},
        {"quality": 2.5},
        {"pageSize": "A3"},
        {"marginMm": -1},
        {"marginMm": 51},
        {"orientation": "diagonal"},
        {"fit": "stretch"},
        {"unknown": True},
        {"marginMm": float("nan")},
    ],
)
def test_invalid_options_do_not_create_jobs(options):
    client = TestClient(app)
    response = client.post(
        "/api/v1/jobs",
        files={"file": ("x.png", raster(), "image/png")},
        data={"options": json.dumps(options)},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "INVALID_OPTIONS"
    with Session() as db:
        assert db.scalar(select(Job)) is None
        assert db.scalar(select(Outbox)) is None


def test_atomic_upload_cleanup_on_later_invalid_file():
    client = TestClient(app)
    before = {
        path for path in settings.storage_root.glob("uploads/*/*") if path.is_file()
    }
    response = client.post(
        "/api/v1/jobs",
        files=[
            ("file", ("valid.png", raster(), "image/png")),
            ("file", ("broken.png", b"broken", "image/png")),
        ],
    )
    assert response.status_code == 422
    assert "broken.png" in response.json()["detail"]["message"]
    with Session() as db:
        assert db.scalar(select(Job)) is None
        assert db.scalar(select(JobFile)) is None
    after = {
        path for path in settings.storage_root.glob("uploads/*/*") if path.is_file()
    }
    assert after == before


@pytest.mark.parametrize(
    "setting,value,code",
    [
        ("max_files", 1, "FILE_LIMIT_EXCEEDED"),
        ("max_pages", 2, "PAGE_LIMIT_EXCEEDED"),
        ("max_total_upload_bytes", 10, "FILE_TOO_LARGE"),
        ("max_total_pixels", 8000, "PIXEL_LIMIT_EXCEEDED"),
    ],
)
def test_aggregate_limits(setting, value, code):
    client = TestClient(app)
    with patch.object(settings, setting, value):
        response = client.post(
            "/api/v1/jobs",
            files=[
                ("file", ("x.tiff", raster("red", "TIFF", ["blue"]), "image/tiff")),
                ("file", ("y.png", raster(), "image/png")),
            ],
        )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == code


def test_workspace_history_filters_pagination_and_isolation():
    owner, outsider = TestClient(app), TestClient(app)
    job = submit(owner)
    second = submit(owner, files=[("file", ("unique.png", raster(), "image/png"))])
    convert_job.run(job["jobId"])
    page = owner.get("/api/v1/jobs?pageSize=1&page=1").json()
    assert page["total"] == 2 and len(page["items"]) == 1
    assert (
        owner.get("/api/v1/jobs?pageSize=1&page=2").json()["items"][0]["jobId"]
        != page["items"][0]["jobId"]
    )
    assert owner.get("/api/v1/jobs?status=SUCCESS").json()["total"] == 1
    assert owner.get("/api/v1/jobs?search=last.png").json()["total"] == 1
    assert owner.get("/api/v1/jobs?search=%25").json()["total"] == 0
    assert outsider.get("/api/v1/jobs").json()["total"] == 0
    submit(outsider)
    assert outsider.get("/api/v1/jobs").json()["total"] == 1
    for suffix in ("", "/events", "/download"):
        assert outsider.get(f"/api/v1/jobs/{job['jobId']}" + suffix).status_code == 404
    # Phase 1 token clients remain supported without the workspace cookie.
    outsider.cookies.clear()
    assert (
        outsider.get(
            f"/api/v1/jobs/{second['jobId']}",
            headers={"X-Job-Token": second["accessToken"]},
        ).status_code
        == 200
    )
    assert owner.get("/api/v1/jobs?page=0").status_code == 422
    assert owner.get("/api/v1/jobs?pageSize=51").status_code == 422
    assert owner.get("/api/v1/jobs?status=UNKNOWN").status_code == 422


def test_failed_partial_conversion_preserves_events_and_hides_result():
    client = TestClient(app)
    job = submit(client)

    def fail(sources, destination, options, on_page):
        destination.write_bytes(b"partial")
        on_page(0, 1, 1)
        raise OSError("disk full")

    with (
        patch("app.tasks.convert.ImagePDFConverter.convert", side_effect=fail),
        patch.object(settings, "max_auto_retries", 0),
    ):
        convert_job.run(job["jobId"])
    detail = client.get(f"/api/v1/jobs/{job['jobId']}").json()
    assert detail["status"] == "FAILED" and detail["processedPages"] == 1
    assert detail["errorCode"] == "STORAGE_ERROR"
    assert detail["result"] is None
    assert client.get(f"/api/v1/jobs/{job['jobId']}/download").status_code == 409
    before = client.get(f"/api/v1/jobs/{job['jobId']}/events").json()
    assert before["items"][-1]["details"]["exceptionType"] == "OSError"
    convert_job.run(job["jobId"])
    assert client.get(f"/api/v1/jobs/{job['jobId']}/events").json() == before
    assert not list(storage.path(f"processing/{job['jobId']}").glob("*/output.pdf"))


def test_duplicate_concurrent_delivery_publishes_one_result():
    client = TestClient(app)
    job = submit(client)
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(convert_job.run, job["jobId"]) for _ in range(2)]
        for future in futures:
            future.result(timeout=15)
    with Session() as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(Result)
                .where(Result.job_id == job["jobId"])
            )
            == 1
        )
        assert (
            db.scalar(
                select(func.count())
                .select_from(Event)
                .where(Event.job_id == job["jobId"], Event.event_type == "SUCCESS")
            )
            == 1
        )
    events = client.get(f"/api/v1/jobs/{job['jobId']}/events?limit=2").json()
    assert events["hasMore"] and events["nextAfter"] == 2
    next_page = client.get(
        f"/api/v1/jobs/{job['jobId']}/events?after=2&limit=100"
    ).json()
    assert next_page["items"][0]["sequence"] == 3


def test_margin_and_fit_geometry():
    contain = page_geometry(200, 100, ConversionOptions(pageSize="Letter", marginMm=10))
    cover = page_geometry(
        200, 100, ConversionOptions(pageSize="Letter", marginMm=10, fit="cover")
    )
    margin = 10 * 72 / 25.4
    assert contain[0:2] == (612, 792)
    assert contain[3] == pytest.approx(margin)
    assert contain[2] < cover[2]
    with pytest.raises(ValueError):
        page_geometry(10, 10, ConversionOptions(marginMm=10))


def test_quality_changes_actual_embedded_image_size():
    client = TestClient(app)
    image = Image.effect_noise((300, 200), 100).convert("RGB")
    buf = io.BytesIO()
    image.save(buf, "PNG")
    sizes = []
    for quality in (10, 95):
        job = submit(
            client,
            {"quality": quality},
            [("file", ("noise.png", buf.getvalue(), "image/png"))],
        )
        convert_job.run(job["jobId"])
        response = client.get(f"/api/v1/jobs/{job['jobId']}/download")
        sizes.append(
            len(PdfReader(io.BytesIO(response.content)).pages[0].images[0].data)
        )
    assert sizes[1] > sizes[0] * 2


@pytest.mark.parametrize("fit", ["contain", "cover"])
def test_actual_pdf_margin_fit_and_orientation(fit):
    client = TestClient(app)
    options = {
        "pageSize": "Letter",
        "orientation": "portrait",
        "marginMm": 10,
        "fit": fit,
    }
    job = submit(client, options, [("file", ("image.png", raster(), "image/png"))])
    convert_job.run(job["jobId"])
    response = client.get(f"/api/v1/jobs/{job['jobId']}/download")
    page = PdfReader(io.BytesIO(response.content)).pages[0]
    assert (float(page.mediabox.width), float(page.mediabox.height)) == (612, 792)
    _, _, scale, x, y, aw, ah = page_geometry(60, 30, ConversionOptions(**options))
    operations = page.get_contents().operations
    matrix = next(operands for operands, operation in operations if operation == b"cm")
    assert [float(value) for value in matrix] == pytest.approx(
        [scale, 0, 0, scale, x, y]
    )
    if fit == "cover":
        clip = next(
            operands for operands, operation in operations if operation == b"re"
        )
        assert [float(value) for value in clip] == pytest.approx(
            [(60 - aw / scale) / 2, (30 - ah / scale) / 2, aw / scale, ah / scale]
        )


def test_invalid_margin_for_original_page_preserves_failure():
    client = TestClient(app)
    job = submit(
        client, {"marginMm": 50}, [("file", ("small.png", raster(), "image/png"))]
    )
    convert_job.run(job["jobId"])
    detail = client.get(f"/api/v1/jobs/{job['jobId']}").json()
    assert detail["status"] == "FAILED" and detail["errorCode"] == "INVALID_OPTIONS"
    assert not detail["downloadAvailable"]


def test_exif_orientation_and_transparency_regression():
    client = TestClient(app)
    original = Image.new("RGB", (80, 40), "red")
    exif = original.getexif()
    exif[274] = 6
    stream = io.BytesIO()
    original.save(stream, "JPEG", exif=exif)
    alpha = Image.new("RGBA", (80, 40), (0, 0, 0, 0))
    transparent = io.BytesIO()
    alpha.save(transparent, "PNG")
    job = submit(
        client,
        files=[
            ("file", ("rotate.jpg", stream.getvalue(), "image/jpeg")),
            ("file", ("alpha.png", transparent.getvalue(), "image/png")),
        ],
    )
    convert_job.run(job["jobId"])
    result = client.get(f"/api/v1/jobs/{job['jobId']}/download")
    pages = PdfReader(io.BytesIO(result.content)).pages
    assert float(pages[0].mediabox.width) / float(
        pages[0].mediabox.height
    ) == pytest.approx(0.5)
    rgb = pages[1].images[0].image.convert("RGB").getpixel((0, 0))
    assert min(rgb) > 245
