"""Real HTTP -> PostgreSQL -> Redis -> Linux Celery -> PDF smoke test.
Run after docker compose up: python scripts/smoke.py
"""

import io
import time
import httpx
from PIL import Image
from pypdf import PdfReader

image = io.BytesIO()
Image.new("RGB", (320, 240), "#278b73").save(image, "PNG")
with httpx.Client(base_url="http://localhost:8080", timeout=30) as client:
    client.get("/health/ready").raise_for_status()
    response = client.post(
        "/api/v1/jobs", files={"file": ("smoke.png", image.getvalue(), "image/png")}
    )
    response.raise_for_status()
    assert response.status_code == 202
    job = response.json()
    headers = {"X-Job-Token": job["accessToken"]}
    for _ in range(60):
        response = client.get(f"/api/v1/jobs/{job['jobId']}", headers=headers)
        response.raise_for_status()
        status = response.json()
        if status["status"] in {"SUCCESS", "FAILED"}:
            break
        time.sleep(1)
    assert status["status"] == "SUCCESS", status
    result = client.get(f"/api/v1/jobs/{job['jobId']}/download", headers=headers)
    result.raise_for_status()
    assert len(PdfReader(io.BytesIO(result.content)).pages) == 1
    assert status["progress"] == 100
    print("PASS: real API -> DB -> Redis -> Worker -> valid one-page PDF", job["jobId"])
