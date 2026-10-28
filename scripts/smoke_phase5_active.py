"""Local Compose only: observe an actual blocked task, then release normally."""

import io
import json
import httpx
from PIL import Image
from benchmark_phase5 import docker, wait


def inside(code):
    return docker("exec", "-T", "api", "python", "-c", code)


def main():
    restore = None
    client = httpx.Client(
        base_url="http://127.0.0.1:8000",
        timeout=20,
        limits=httpx.Limits(max_keepalive_connections=0),
    )
    try:
        assert (
            inside(
                "from app.core.db import Session; from app.models.job import Job; from sqlalchemy import select,func; db=Session(); print(db.scalar(select(func.count()).select_from(Job).where(Job.status.in_(['QUEUED','PROCESSING','RETRY_WAIT','CANCEL_REQUESTED']))))"
            )
            == "0"
        )
        docker("stop", "worker")
        stream = io.BytesIO()
        Image.new("RGB", (120, 80), "green").save(stream, "PNG")
        response = client.post(
            "/api/v1/jobs",
            files={"file": ("active-observation.png", stream.getvalue(), "image/png")},
        )
        assert response.status_code == 202, response.text
        identifier = response.json()["jobId"]
        path = inside(
            "from app.core.db import Session; from app.models.job import JobFile; from sqlalchemy import select; from app.storage.local import storage; "
            + f"db=Session(); print(storage.path(db.scalar(select(JobFile).where(JobFile.job_id=='{identifier}')).storage_path))"
        )
        prefix = f"import os; from pathlib import Path; p=Path({path!r}); b=p.with_suffix('.phase5-backup'); "
        inside(prefix + "os.replace(p,b); os.mkfifo(p)")
        restore = prefix + "os.replace(b,p) if b.exists() else None"
        docker("start", "worker")

        def observed():
            data = client.get("/api/v1/monitoring/workers").json()
            return next(
                (
                    worker
                    for worker in data["items"]
                    if worker["status"] == "ONLINE"
                    and any(job["jobId"] == identifier for job in worker["jobs"])
                ),
                None,
            )

        worker = wait(observed)
        assert worker["activeCount"] >= 1
        job = next(job for job in worker["jobs"] if job["jobId"] == identifier)
        assert (
            job["heartbeatAt"]
            and job["leaseExpiresAt"]
            and job["status"] == "PROCESSING"
        )
        assert (
            identifier
            not in httpx.get("http://127.0.0.1:8000/api/v1/monitoring/workers").text
        )
        # Open the writer, replace the path, then write to the old FIFO inode.
        # Subsequent decoder opens see the restored regular file, not the FIFO.
        inside(
            prefix
            + "data=b.read_bytes(); fd=os.open(p,os.O_WRONLY); os.replace(b,p); os.write(fd,data); os.close(fd)"
        )
        restore = None
        result = wait(
            lambda: (
                data
                if (data := client.get(f"/api/v1/jobs/{identifier}").json())["status"]
                == "SUCCESS"
                else None
            )
        )
        assert result["attemptCount"] == 1
        print(
            json.dumps(
                {"jobId": identifier, "worker": worker, "releasedNormally": True},
                indent=2,
            )
        )
    finally:
        try:
            if restore:
                docker("kill", "-s", "SIGKILL", "worker")
                inside(restore)
        finally:
            docker("start", "worker")
            client.close()


if __name__ == "__main__":
    main()
