import io
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from pypdf import PdfReader
from sqlalchemy import select
from app.main import app
from app.core.db import Session
from app.models.job import Job, Outbox
from app.tasks.convert import convert_job
from app.services.dispatcher import dispatch_once
from app.storage.local import storage

client = TestClient(app)


def image_bytes(format="PNG", **kwargs):
    output = io.BytesIO()
    Image.new("RGB", (60, 40), "red").save(output, format, **kwargs)
    return output.getvalue()


def upload():
    response = client.post(
        "/api/v1/jobs", files={"file": ("sample.png", image_bytes(), "image/png")}
    )
    assert response.status_code == 202
    return response.json()


def test_upload_worker_status_download():
    job = upload()
    headers = {"X-Job-Token": job["accessToken"]}
    url = f"/api/v1/jobs/{job['jobId']}"
    assert client.get(url, headers=headers).json()["status"] == "QUEUED"
    assert client.get(url + "/download", headers=headers).status_code == 409
    convert_job.run(job["jobId"])
    completed = client.get(url, headers=headers).json()
    assert completed["status"] == "SUCCESS"
    assert completed["progress"] == 100
    response = client.get(url + "/download", headers=headers)
    assert response.headers["content-type"] == "application/pdf"
    assert len(PdfReader(io.BytesIO(response.content)).pages) == 1
    convert_job.run(job["jobId"])
    assert client.get(url + "/download", headers=headers).content == response.content


def test_access_control():
    job = upload()
    outsider = TestClient(app)
    for suffix in ("", "/download"):
        assert outsider.get(f"/api/v1/jobs/{job['jobId']}" + suffix).status_code == 404
        assert (
            outsider.get(
                f"/api/v1/jobs/{job['jobId']}" + suffix,
                headers={"X-Job-Token": "wrong"},
            ).status_code
            == 404
        )


@pytest.mark.parametrize(
    "name,content,mime",
    [
        ("fake.png", b"malformed", "image/png"),
        ("fake.jpg", image_bytes(), "image/jpeg"),
        ("sample.png", image_bytes(), "application/octet-stream"),
    ],
)
def test_invalid_uploads(name, content, mime):
    response = client.post("/api/v1/jobs", files={"file": (name, content, mime)})
    assert response.status_code == 422
    with Session() as db:
        assert db.scalar(select(Job)) is None


def test_dispatch_retries_without_losing_job():
    upload()
    with patch(
        "app.services.dispatcher.celery_app.send_task", side_effect=ConnectionError
    ):
        dispatch_once()
    with Session() as db:
        event = db.scalar(select(Outbox))
        assert event.published_at is None
        assert event.retry_count == 1
    with patch("app.services.dispatcher.celery_app.send_task") as send:
        dispatch_once()
        dispatch_once()
        assert send.call_count == 1
    with Session() as db:
        assert db.scalar(select(Outbox)).published_at is not None


def test_conversion_failure_not_downloadable():
    job = upload()
    with patch(
        "app.tasks.convert.ImagePDFConverter.convert", side_effect=OSError("disk full")
    ):
        convert_job.run(job["jobId"])
    headers = {"X-Job-Token": job["accessToken"]}
    assert (
        client.get(f"/api/v1/jobs/{job['jobId']}", headers=headers).json()["status"]
        == "FAILED"
    )
    assert (
        client.get(f"/api/v1/jobs/{job['jobId']}/download", headers=headers).status_code
        == 409
    )


def test_storage_traversal():
    with pytest.raises(ValueError):
        storage.path("../escape")


def test_tampered_result_rejected():
    job = upload()
    convert_job.run(job["jobId"])
    with Session() as db:
        record = db.get(Job, job["jobId"])
        storage.path(record.output_path).write_bytes(b"corrupt")
    assert (
        client.get(
            f"/api/v1/jobs/{job['jobId']}/download",
            headers={"X-Job-Token": job["accessToken"]},
        ).status_code
        == 410
    )


def test_oversize_and_multipage_supported():
    with patch("app.api.routes.settings.max_upload_bytes", 10):
        assert (
            client.post(
                "/api/v1/jobs", files={"file": ("big.png", image_bytes(), "image/png")}
            ).json()["detail"]["code"]
            == "FILE_TOO_LARGE"
        )
    data = image_bytes("TIFF", save_all=True, append_images=[Image.new("RGB", (5, 5))])
    response = client.post(
        "/api/v1/jobs", files={"file": ("multi.tiff", data, "image/tiff")}
    )
    assert response.status_code == 202
    job = response.json()
    assert job["totalPages"] == 2
    convert_job.run(job["jobId"])
    pdf = client.get(
        f"/api/v1/jobs/{job['jobId']}/download",
        headers={"X-Job-Token": job["accessToken"]},
    )
    assert len(PdfReader(io.BytesIO(pdf.content)).pages) == 2


@pytest.mark.parametrize(
    "format,filename,mime",
    [
        ("JPEG", "test.jpg", "image/jpeg"),
        ("BMP", "test.bmp", "image/bmp"),
        ("WEBP", "test.webp", "image/webp"),
        ("TIFF", "test.tiff", "image/tiff"),
    ],
)
def test_supported_formats(format, filename, mime):
    response = client.post(
        "/api/v1/jobs", files={"file": (filename, image_bytes(format), mime)}
    )
    assert response.status_code == 202
    job = response.json()
    convert_job.run(job["jobId"])
    result = client.get(
        f"/api/v1/jobs/{job['jobId']}/download",
        headers={"X-Job-Token": job["accessToken"]},
    )
    assert result.status_code == 200
    page = PdfReader(io.BytesIO(result.content)).pages[0]
    assert float(page.mediabox.width) / float(page.mediabox.height) == pytest.approx(
        1.5
    )


def test_pixel_limit():
    with patch("app.services.validation.settings.max_pixels", 100):
        response = client.post(
            "/api/v1/jobs", files={"file": ("image.png", image_bytes(), "image/png")}
        )
    assert response.status_code == 422


def test_multiple_uploads_supported():
    response = client.post(
        "/api/v1/jobs",
        files=[
            ("file", ("a.png", image_bytes(), "image/png")),
            ("file", ("b.png", image_bytes(), "image/png")),
        ],
    )
    assert response.status_code == 202
    assert response.json()["totalFiles"] == 2
