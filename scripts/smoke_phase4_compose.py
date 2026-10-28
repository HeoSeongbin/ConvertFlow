"""Host-only destructive fault checks on LOCAL Compose; requires no active jobs.

Uses only newly uploaded fixtures. Stops/restarts services and always restores
them. Never removes volumes. Run after smoke_phase4.py, with standard services up.
"""

import io
import json
import subprocess
import time
import httpx
from PIL import Image


def docker(*args):
    return subprocess.run(
        ["docker", "compose", *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def inside(code):
    return docker("exec", "-T", "api", "python", "-c", code)


def wait(check, timeout=100):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        try:
            if result := check():
                return result
        except (httpx.HTTPError, subprocess.CalledProcessError):
            pass
        time.sleep(0.5)
    raise AssertionError("Compose recovery timed out")


def main():
    client = httpx.Client(
        base_url="http://127.0.0.1:8000",
        timeout=8,
        limits=httpx.Limits(max_keepalive_connections=0),
    )
    fixture = io.BytesIO()
    Image.new("RGB", (100, 60), "blue").save(fixture, "PNG")
    report = {}
    restore = None

    def upload():
        response = client.post(
            "/api/v1/jobs",
            files={"file": ("compose-fault.png", fixture.getvalue(), "image/png")},
        )
        assert response.status_code == 202, response.text
        return response.json()["jobId"]

    def detail(identifier):
        response = client.get(f"/api/v1/jobs/{identifier}")
        response.raise_for_status()
        return response.json()

    def successful(identifier, count):
        wait(lambda: detail(identifier)["status"] == "SUCCESS")
        assert detail(identifier)["attemptCount"] == count
        attempts = client.get(f"/api/v1/jobs/{identifier}/attempts").json()["items"]
        if count == 2:
            assert attempts[1]["errorCode"] == "WORKER_LEASE_EXPIRED", attempts
        response = client.get(f"/api/v1/jobs/{identifier}/download")
        assert response.status_code == 200 and response.content.startswith(b"%PDF")

    def blocked():
        nonlocal restore
        docker("stop", "worker")
        identifier = upload()
        lookup = (
            "from app.core.db import Session; from app.models.job import JobFile; "
            "from app.storage.local import storage; from sqlalchemy import select; import os; "
            f"db=Session(); f=db.scalar(select(JobFile).where(JobFile.job_id=='{identifier}')); "
            "print(storage.path(f.storage_path))"
        )
        path = inside(lookup)
        prefix = f"from pathlib import Path; import os; p=Path({path!r}); b=p.with_suffix('.phase4-backup'); "
        inside(prefix + "os.replace(p,b); os.mkfifo(p)")
        restore = prefix + "os.replace(b,p) if b.exists() else None"
        docker("start", "worker")
        wait(lambda: detail(identifier)["status"] == "PROCESSING")
        # FIFO blocks native source read; no special production fault flags.
        time.sleep(1)
        return identifier, prefix

    try:
        assert (
            inside(
                "from app.core.db import Session; from app.models.job import Job; from sqlalchemy import select,func; db=Session(); print(db.scalar(select(func.count()).select_from(Job).where(Job.status.in_(['QUEUED','PROCESSING','RETRY_WAIT','CANCEL_REQUESTED']))))"
            )
            == "0"
        ), "finish active jobs first"
        identifier, _ = blocked()
        docker("kill", "-s", "SIGKILL", "worker")
        inside(restore)
        restore = None
        docker("start", "worker")
        successful(identifier, 2)
        report["composePreforkSIGKILL"] = identifier
        print(json.dumps(report), flush=True)
        # Outbox survives unavailable Redis without losing upload registration.
        docker("stop", "redis")
        identifier = upload()
        time.sleep(5)
        assert detail(identifier)["status"] == "QUEUED"
        docker("start", "redis")
        successful(identifier, 1)
        report["redisOutboxRecovery"] = identifier
        print(json.dumps(report), flush=True)
        identifier, prefix = blocked()
        docker("stop", "postgres")
        # Exceed the product's 30s Lease while heartbeats cannot reach the DB.
        time.sleep(35)
        inside(prefix + "p.write_bytes(b.read_bytes()); os.replace(b,p)")
        restore = None
        time.sleep(5)
        docker("start", "postgres")
        successful(identifier, 2)
        report["postgresLeaseRecovery"] = identifier
        docker("restart", "api", "dispatcher")
        wait(lambda: client.get("/health/ready").status_code == 200)
        assert detail(identifier)["status"] == "SUCCESS"
        report["apiDispatcherRestartPreserved"] = True
        print(json.dumps(report, indent=2), flush=True)
    finally:
        try:
            if restore:
                inside(restore)
        finally:
            docker("start", "postgres", "redis", "worker", "dispatcher", "api")
            client.close()


if __name__ == "__main__":
    main()
