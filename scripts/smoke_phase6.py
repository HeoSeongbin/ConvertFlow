"""Actual API/Worker PDF and latest-first cursor compatibility checks."""

import io
import json
import time
import httpx
from PIL import Image
from pypdf import PdfReader


def main():
    client = httpx.Client(base_url="http://127.0.0.1:8000", timeout=30)
    frames = [
        Image.new("RGB", (48, 32), (index * 7 % 255, 90, 160)) for index in range(32)
    ]
    stream = io.BytesIO()
    frames[0].save(stream, "TIFF", save_all=True, append_images=frames[1:])
    for frame in frames:
        frame.close()
    response = client.post(
        "/api/v1/jobs",
        files={"file": ("phase6-cursor.tiff", stream.getvalue(), "image/tiff")},
    )
    assert response.status_code == 202, response.text
    identifier = response.json()["jobId"]
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        data = client.get(f"/api/v1/jobs/{identifier}").json()
        assert data["status"] != "FAILED", data
        if data["status"] == "SUCCESS":
            break
        time.sleep(0.3)
    assert data["status"] == "SUCCESS" and data["attemptCount"] == 1
    first = client.get(
        f"/api/v1/jobs/{identifier}/events", params={"order": "desc", "limit": 30}
    ).json()
    assert first["items"][0]["type"] == "SUCCESS" and first["hasMore"]
    second = client.get(
        f"/api/v1/jobs/{identifier}/events",
        params={"order": "desc", "limit": 30, "before": first["nextBefore"]},
    ).json()
    sequence = [
        event["sequence"] for page in [first, second] for event in page["items"]
    ]
    ascending = client.get(
        f"/api/v1/jobs/{identifier}/events", params={"limit": 100}
    ).json()
    assert sequence == [event["sequence"] for event in reversed(ascending["items"])]
    assert len(sequence) == len(set(sequence))
    pdf = client.get(f"/api/v1/jobs/{identifier}/download")
    assert (
        pdf.status_code == 200
        and len(PdfReader(io.BytesIO(pdf.content), strict=True).pages) == 32
    )
    assert (
        httpx.get(
            f"http://127.0.0.1:8000/api/v1/jobs/{identifier}/events?order=desc"
        ).status_code
        == 404
    )
    assert (
        httpx.get(
            f"http://127.0.0.1:8000/api/v1/jobs/{identifier}/download"
        ).status_code
        == 404
    )
    print(
        json.dumps(
            {
                "jobId": identifier,
                "pages": 32,
                "events": len(sequence),
                "latestEvent": first["items"][0]["type"],
                "cursorNoDuplicatesOrGaps": True,
                "legacyAscendingPreserved": True,
                "authorizationPreserved": True,
            },
            indent=2,
        )
    )
    client.close()


if __name__ == "__main__":
    main()
