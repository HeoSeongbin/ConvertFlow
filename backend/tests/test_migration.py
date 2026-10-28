import os
import subprocess
import sys
from pathlib import Path
from sqlalchemy import create_engine, text


def test_phase1_database_upgrade_preserves_existing_jobs(tmp_path):
    backend = Path(__file__).resolve().parents[1]
    url = "sqlite:///" + str(tmp_path / "migration.db")
    env = {**os.environ, "DATABASE_URL": url}

    def migrate(revision):
        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", revision],
            cwd=backend,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )

    migrate("0001")
    engine = create_engine(url)
    with engine.begin() as db:
        for identifier, status in [
            ("old-success", "SUCCESS"),
            ("old-failure", "FAILED"),
            ("old-queued", "QUEUED"),
        ]:
            db.execute(
                text(
                    "INSERT INTO conversion_job (job_id,access_hash,status,progress,original_filename,input_path,file_size,mime_type,checksum,created_at,completed_at,error_code,error_message,output_path,output_size,output_checksum) VALUES (:id,'hash',:status,:progress,'legacy.png','uploads/legacy',42,'image/png','checksum','2026-10-25 10:00:00',:completed,:code,:message,:output,:size,:checksum)"
                ),
                dict(
                    id=identifier,
                    status=status,
                    progress=100 if status == "SUCCESS" else 0,
                    completed="2026-10-25 10:00:01" if status != "QUEUED" else None,
                    code="DECODE_FAILED" if status == "FAILED" else None,
                    message="original failure detail" if status == "FAILED" else None,
                    output="results/legacy.pdf" if status == "SUCCESS" else None,
                    size=123 if status == "SUCCESS" else None,
                    checksum="outputhash" if status == "SUCCESS" else None,
                ),
            )
    migrate("head")
    with engine.connect() as db:
        assert (
            db.scalar(
                text(
                    "SELECT COUNT(*) FROM conversion_job WHERE lease_expires_at IS NOT NULL OR heartbeat_at IS NOT NULL"
                )
            )
            == 0
        )
    with engine.connect() as db:
        assert db.scalar(text("SELECT COUNT(*) FROM conversion_job")) == 3
        assert db.scalar(text("SELECT COUNT(*) FROM conversion_job_file")) == 3
        assert db.scalar(text("SELECT COUNT(*) FROM conversion_result")) == 1
        assert db.scalar(text("SELECT COUNT(*) FROM conversion_event")) == 3
        assert (
            db.scalar(
                text(
                    "SELECT error_message FROM conversion_job WHERE job_id='old-failure'"
                )
            )
            == "original failure detail"
        )
        assert (
            db.scalar(
                text(
                    "SELECT output_checksum FROM conversion_job WHERE job_id='old-success'"
                )
            )
            == "outputhash"
        )
        assert db.scalar(text("SELECT checksum FROM conversion_result")) == "outputhash"
        assert (
            db.scalar(
                text(
                    "SELECT processed_pages FROM conversion_job WHERE job_id='old-success'"
                )
            )
            == 1
        )
        assert (
            db.scalar(
                text("SELECT stage FROM conversion_job WHERE job_id='old-queued'")
            )
            == "QUEUED"
        )
        assert (
            db.scalar(
                text(
                    "SELECT COUNT(*) FROM conversion_job WHERE workspace_hash IS NOT NULL"
                )
            )
            == 0
        )
        assert db.scalar(text("SELECT COUNT(*) FROM conversion_attempt")) == 2
        assert (
            db.scalar(
                text("SELECT origin FROM conversion_attempt WHERE job_id='old-failure'")
            )
            == "LEGACY"
        )
        assert (
            db.scalar(
                text(
                    "SELECT error_message FROM conversion_attempt WHERE job_id='old-failure'"
                )
            )
            == "original failure detail"
        )
        assert (
            db.scalar(
                text(
                    "SELECT attempt_count FROM conversion_job WHERE job_id='old-queued'"
                )
            )
            == 0
        )
        assert (
            db.scalar(
                text(
                    "SELECT COUNT(*) FROM conversion_result WHERE attempt_id IS NOT NULL"
                )
            )
            == 1
        )
    engine.dispose()
