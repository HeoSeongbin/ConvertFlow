"""Local Compose load/monitoring checks; restores one Worker and Observer.

Run from repository root: python scripts/benchmark_phase5.py --output report.json
Requires an idle development stack. Keeps generated jobs as real audit history.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
import io
import json
import math
from pathlib import Path
import statistics
import subprocess
import time
from datetime import datetime, timezone
import httpx
from PIL import Image
from pypdf import PdfReader


def docker(*args):
    return subprocess.run(
        ["docker", "compose", *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def wait(check, timeout=120):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        value = check()
        if value:
            return value
        time.sleep(0.5)
    raise AssertionError("monitoring/load check timed out")


def tiff(pages, edge):
    stream = io.BytesIO()
    frames = [
        Image.new("RGB", (edge, edge), (index * 23 % 255, 80, 160))
        for index in range(pages)
    ]
    frames[0].save(
        stream,
        "TIFF",
        save_all=True,
        append_images=frames[1:],
        compression="tiff_deflate",
    )
    for frame in frames:
        frame.close()
    return stream.getvalue()


def main(output):
    report = {
        "measuredAt": datetime.now(timezone.utc).isoformat(),
        "environment": "local Docker Desktop, each worker concurrency=1, cpus=1, mem_limit=768m",
        "batches": [],
    }
    client = httpx.Client(
        base_url="http://127.0.0.1:8000",
        timeout=120,
        limits=httpx.Limits(max_keepalive_connections=0),
    )

    def get(path):
        response = client.get(path)
        response.raise_for_status()
        return response.json()

    def upload(payload, copies=1):
        response = client.post(
            "/api/v1/jobs",
            files=[
                ("file", (f"load-{index}.tiff", payload, "image/tiff"))
                for index in range(copies)
            ],
        )
        assert response.status_code == 202, response.text
        return response.json()["jobId"]

    def finished(identifier):
        data = get(f"/api/v1/jobs/{identifier}")
        assert data["status"] not in {"FAILED", "CANCELLED"}, data
        return data if data["status"] == "SUCCESS" else None

    def pdf(identifier, pages):
        response = client.get(f"/api/v1/jobs/{identifier}/download")
        assert response.status_code == 200
        assert len(PdfReader(io.BytesIO(response.content), strict=True).pages) == pages

    try:
        count = docker(
            "exec",
            "-T",
            "api",
            "python",
            "-c",
            "from app.core.db import Session; from app.models.job import Job; from sqlalchemy import select,func; db=Session(); print(db.scalar(select(func.count()).select_from(Job).where(Job.status.in_(['QUEUED','PROCESSING','RETRY_WAIT','CANCEL_REQUESTED']))))",
        )
        assert count == "0", "finish active jobs before changing Worker scale"
        docker("stop", "worker")
        identifier = upload(tiff(5, 960), copies=20)
        observed = wait(
            lambda: (
                value
                if (value := get("/api/v1/monitoring/workers"))["queue"][
                    "readyMessages"
                ]
                not in (None, 0)
                else None
            )
        )
        assert get("/api/v1/monitoring/dashboard")["counts"]["QUEUED"] == 1
        assert any(item["status"] == "UNKNOWN" for item in observed["items"])
        report["heldQueue"] = observed["queue"]
        docker("start", "worker")
        data = wait(lambda: finished(identifier))
        assert (
            data["totalFiles"] == 20
            and data["totalPages"] == 100
            and data["attemptCount"] == 1
        )
        pdf(identifier, 100)
        report["boundary"] = {
            "jobId": identifier,
            "files": 20,
            "pages": 100,
            "pixels": 92160000,
            "durationSeconds": data["durationSeconds"],
        }
        print("PASS real queue count and 20-file/100-page conversion", flush=True)
        payload = tiff(8, 1024)
        for workers in [1, 2]:
            docker("up", "-d", "--scale", f"worker={workers}", "worker")

            def observed_scale():
                value = get("/api/v1/monitoring/workers")
                online = sum(item["status"] == "ONLINE" for item in value["items"])
                return value if online == workers else None

            observed = wait(observed_scale)
            started = time.perf_counter()
            with ThreadPoolExecutor(max_workers=3) as requests:
                identifiers = list(requests.map(lambda _: upload(payload), range(6)))
            details = [
                wait(lambda identifier=identifier: finished(identifier))
                for identifier in identifiers
            ]
            wall = time.perf_counter() - started
            durations = sorted(data["durationSeconds"] for data in details)
            worker_names = {}
            for identifier in identifiers:
                pdf(identifier, 8)
                attempts = get(f"/api/v1/jobs/{identifier}/attempts")["items"]
                assert len(attempts) == 1 and attempts[0]["status"] == "SUCCESS"
                worker_names[attempts[0]["workerName"]] = (
                    worker_names.get(attempts[0]["workerName"], 0) + 1
                )
            report["batches"].append(
                {
                    "workers": workers,
                    "jobs": 6,
                    "pagesPerJob": 8,
                    "edgePixels": 1024,
                    "inputBytesPerJob": len(payload),
                    "batchWallSecondsIncludingUpload": wall,
                    "jobsPerMinute": 6 / wall * 60,
                    "medianProcessingSeconds": statistics.median(durations),
                    "p95ProcessingSecondsNearestRank": durations[
                        math.ceil(len(durations) * 0.95) - 1
                    ],
                    "workerDistribution": worker_names,
                    "jobIds": identifiers,
                }
            )
            print(
                f"PASS {workers} Worker batch: {wall:.3f}s, distribution {worker_names}",
                flush=True,
            )
        # The UI/API must stop presenting cached queue/worker values as current.
        docker("stop", "observer")
        stale = wait(
            lambda: (
                value
                if (value := get("/api/v1/monitoring/workers"))["queue"]["status"]
                == "UNKNOWN"
                and all(item["status"] == "UNKNOWN" for item in value["items"])
                else None
            ),
            60,
        )
        assert stale["queue"]["readyMessages"] is None
        report["staleObserverUnknown"] = True
        docker("start", "observer")
        wait(lambda: get("/api/v1/monitoring/workers")["queue"]["status"] == "KNOWN")
        report["dashboard"] = get("/api/v1/monitoring/dashboard")
        assert (
            report["dashboard"]["total"] == 13
            and report["dashboard"]["counts"]["SUCCESS"] == 13
        )
        # Another cookie cannot read the measured workspace's statistics.
        foreign = httpx.get("http://127.0.0.1:8000/api/v1/monitoring/dashboard").json()
        assert foreign["total"] == 0
        report["workspaceIsolation"] = True
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"PASS monitoring/load report: {output}", flush=True)
    finally:
        docker("start", "observer")
        docker("up", "-d", "--scale", "worker=1", "worker")
        client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output", type=Path, default=Path(".storage/phase5-load.json")
    )
    main(parser.parse_args().output)
