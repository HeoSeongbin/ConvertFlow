"""Real Phase 2 API -> PostgreSQL -> Redis -> Celery -> ordered multipage PDF."""

import io
import json
import time
import httpx
from PIL import Image
from pypdf import PdfReader


def image_bytes(color, format="PNG", frames=None):
    stream = io.BytesIO()
    kwargs = (
        {
            "save_all": True,
            "append_images": [Image.new("RGB", (120, 60), c) for c in frames],
        }
        if frames
        else {}
    )
    Image.new("RGB", (120, 60), color).save(stream, format, **kwargs)
    return stream.getvalue()


def wait_job(client, job_id):
    for _ in range(90):
        response = client.get(f"/api/v1/jobs/{job_id}")
        response.raise_for_status()
        job = response.json()
        if job["status"] in {"SUCCESS", "FAILED"}:
            return job
        time.sleep(1)
    raise AssertionError("Worker did not finish within 90 seconds")


with httpx.Client(base_url="http://localhost:8080", timeout=120) as client:
    client.get("/health/ready").raise_for_status()
    options = {
        "pageSize": "Letter",
        "orientation": "landscape",
        "marginMm": 10,
        "fit": "cover",
        "quality": 75,
    }
    response = client.post(
        "/api/v1/jobs",
        files=[
            ("file", ("first.png", image_bytes("red"), "image/png")),
            (
                "file",
                ("two.tiff", image_bytes("green", "TIFF", ["blue"]), "image/tiff"),
            ),
        ],
        data={"options": json.dumps(options)},
    )
    response.raise_for_status()
    assert response.status_code == 202
    job_id = response.json()["jobId"]
    job = wait_job(client, job_id)
    assert job["status"] == "SUCCESS", job
    assert job["processedPages"] == 3 and job["processedFiles"] == 2
    assert [f["filename"] for f in job["files"]] == ["first.png", "two.tiff"]
    assert job["options"] == options
    result = client.get(f"/api/v1/jobs/{job_id}/download")
    result.raise_for_status()
    reader = PdfReader(io.BytesIO(result.content))
    assert len(reader.pages) == 3
    for page, channel in zip(reader.pages, [0, 1, 2]):
        assert (float(page.mediabox.width), float(page.mediabox.height)) == (792, 612)
        pixel = page.images[0].image.convert("RGB").getpixel((20, 20))
        assert pixel[channel] > max(pixel[i] for i in range(3) if i != channel) + 80
    listing = client.get(
        "/api/v1/jobs", params={"status": "SUCCESS", "search": job_id, "pageSize": 1}
    ).json()
    assert listing["total"] == 1 and listing["items"][0]["jobId"] == job_id
    events = client.get(f"/api/v1/jobs/{job_id}/events").json()["items"]
    assert [
        e["details"]["processedPages"] for e in events if e["type"] == "PAGE_PROCESSED"
    ] == [1, 2, 3]
    assert events[-1]["type"] == "SUCCESS"
    with httpx.Client(base_url="http://localhost:8080") as outsider:
        assert outsider.get("/api/v1/jobs").json()["total"] == 0
        assert outsider.get(f"/api/v1/jobs/{job_id}").status_code == 404
    # A valid upload whose original page is too small for the requested margins.
    response = client.post(
        "/api/v1/jobs",
        files={"file": ("small.png", image_bytes("red"), "image/png")},
        data={"options": json.dumps({"marginMm": 50})},
    )
    response.raise_for_status()
    failed_id = response.json()["jobId"]
    failed = wait_job(client, failed_id)
    assert failed["status"] == "FAILED" and failed["errorCode"] == "INVALID_OPTIONS"
    assert not failed["downloadAvailable"] and failed["result"] is None
    assert client.get(f"/api/v1/jobs/{failed_id}/download").status_code == 409
    errors = client.get(f"/api/v1/jobs/{failed_id}/events").json()["items"]
    assert errors[-1]["type"] == "FAILED"
    print(
        "PASS Phase 2:",
        json.dumps(
            {
                "successJob": job_id,
                "failedJob": failed_id,
                "pages": 3,
                "orderedColors": ["red", "green", "blue"],
                "options": options,
                "events": len(events),
                "workspaceIsolation": True,
            }
        ),
    )
