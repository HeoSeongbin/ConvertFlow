"""Reproducible LOCAL Compose/E2E validation. Preserves volumes and restores services.

Run on an idle stack. --faults temporarily interrupts Worker/DB/Redis and executes
the existing real process-kill/fencing suites; no product fault-injection flags.
COMPOSE_PROJECT_NAME is inherited by every child command for isolated runs.
"""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--faults", action="store_true")
    args = parser.parse_args()
    output = ROOT / "artifacts" / "phase7"
    output.mkdir(parents=True, exist_ok=True)
    report = {
        "project": os.environ.get("COMPOSE_PROJECT_NAME", "convertflow"),
        "steps": [],
    }

    def run(name, command, cwd=ROOT):
        start = time.monotonic()
        with (output / f"{name}.log").open("w", encoding="utf-8") as log:
            completed = subprocess.run(
                command, cwd=cwd, stdout=log, stderr=subprocess.STDOUT, timeout=900
            )
        report["steps"].append(
            {
                "name": name,
                "exitCode": completed.returncode,
                "seconds": round(time.monotonic() - start, 2),
            }
        )
        (output / "summary.json").write_text(
            json.dumps(report, indent=2), encoding="utf-8"
        )
        print(f"{name}: exit {completed.returncode}", flush=True)
        completed.check_returncode()

    def compose(*args):
        subprocess.run(["docker", "compose", *args], cwd=ROOT, check=True)

    try:
        run(
            "ready",
            ["docker", "compose", "up", "-d", "--wait", "--wait-timeout", "180"],
        )
        run(
            "idle",
            [
                "docker",
                "compose",
                "exec",
                "-T",
                "api",
                "python",
                "-c",
                "from app.core.db import Session; from app.models.job import Job; "
                "from sqlalchemy import select,func; "
                "db=Session(); n=db.scalar(select(func.count()).select_from(Job).where("
                "Job.status.in_(['QUEUED','PROCESSING','RETRY_WAIT','CANCEL_REQUESTED']))); "
                "assert n == 0, 'Finish active jobs before validation'",
            ],
        )
        for script in ["smoke", "smoke_phase2", "smoke_phase6"]:
            run(script, [sys.executable, f"scripts/{script}.py"])
        run("schema", ["docker", "compose", "exec", "-T", "api", "alembic", "check"])
        run("e2e", ["docker", "compose", "run", "--rm", "--build", "e2e"])
        compose("stop", "worker")
        try:
            run(
                "e2e-queued",
                [
                    "docker",
                    "compose",
                    "run",
                    "--rm",
                    "--no-deps",
                    "e2e",
                    "npm",
                    "run",
                    "test:e2e:queued",
                ],
            )
        finally:
            compose("start", "worker")
        if args.faults:
            compose("stop", "dispatcher")
            try:
                for phase in [3, 4]:
                    filename = f"smoke_phase{phase}.py"
                    compose("cp", f"scripts/{filename}", f"api:/tmp/{filename}")
                    run(
                        f"phase{phase}-isolated",
                        [
                            "docker",
                            "compose",
                            "exec",
                            "-T",
                            "-e",
                            "PYTHONPATH=/app",
                            "api",
                            "python",
                            f"/tmp/{filename}",
                        ],
                    )
            finally:
                compose("start", "dispatcher")
            run("compose-faults", [sys.executable, "scripts/smoke_phase4_compose.py"])
    finally:
        # Attempt restoration even after assertions/nonzero exits; never delete volumes.
        try:
            run(
                "restore",
                ["docker", "compose", "up", "-d", "--wait", "--wait-timeout", "180"],
            )
        finally:
            run("services", ["docker", "compose", "ps", "--all"])


if __name__ == "__main__":
    main()
