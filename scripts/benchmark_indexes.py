"""PostgreSQL TEMP fixture only; never inserts synthetic jobs into product tables."""

import json
from sqlalchemy import text
from app.core.db import engine


def main():
    report = {
        "fixtureRows": 100000,
        "scope": "isolated PostgreSQL TEMP table, synthetic distribution",
        "queries": {},
    }
    with engine.connect() as db:
        transaction = db.begin()
        try:
            db.execute(
                text(
                    "CREATE TEMP TABLE phase5_index_fixture (job_id text, status text, lease_expires_at timestamptz, workspace_hash text, completed_at timestamptz) ON COMMIT DROP"
                )
            )
            db.execute(
                text(
                    "INSERT INTO phase5_index_fixture SELECT n::text, CASE WHEN n%10=0 THEN 'PROCESSING' ELSE 'SUCCESS' END, now() + ((n/10)%10000-5)*interval '1 second', (n%10)::text, now() - ((n/10)%10000)*interval '1 minute' FROM generate_series(1,100000) n"
                )
            )
            for column in ["status", "lease_expires_at", "workspace_hash"]:
                db.execute(
                    text(
                        f"CREATE INDEX old_{column} ON phase5_index_fixture ({column})"
                    )
                )
            db.execute(text("ANALYZE phase5_index_fixture"))
            db.execute(
                text(
                    "CREATE TEMP TABLE phase5_attempt_fixture (job_id text, finished_at timestamptz) ON COMMIT DROP"
                )
            )
            db.execute(
                text(
                    "INSERT INTO phase5_attempt_fixture SELECT (n%100)::text, now()-(n%10000)*interval '1 minute' FROM generate_series(1,100000) n"
                )
            )
            db.execute(
                text("CREATE INDEX old_attempt_job ON phase5_attempt_fixture(job_id)")
            )
            db.execute(text("ANALYZE phase5_attempt_fixture"))
            queries = {
                "expiredLease": "SELECT job_id FROM phase5_index_fixture WHERE status IN ('PROCESSING','CANCEL_REQUESTED') AND (lease_expires_at<=now() OR lease_expires_at IS NULL) ORDER BY job_id LIMIT 20",
                "workspaceRecent": "SELECT count(*) FROM phase5_index_fixture WHERE workspace_hash='2' AND completed_at>=now()-interval '1 hour' AND completed_at<=now()",
                "attemptRecent": "SELECT count(*) FROM phase5_attempt_fixture WHERE job_id='42' AND finished_at>=now()-interval '1 hour' AND finished_at<=now()",
            }
            for stage in ["before", "after"]:
                if stage == "after":
                    db.execute(
                        text(
                            "CREATE INDEX new_attempt_job_finished ON phase5_attempt_fixture(job_id,finished_at)"
                        )
                    )
                    db.execute(
                        text(
                            "CREATE INDEX new_status_lease ON phase5_index_fixture (status,lease_expires_at)"
                        )
                    )
                    db.execute(
                        text(
                            "CREATE INDEX new_workspace_completed ON phase5_index_fixture (workspace_hash,completed_at)"
                        )
                    )
                for name, query in queries.items():
                    # Warm cache once, then retain actual plans and timings.
                    db.execute(text(query)).all()
                    plans = [
                        db.execute(
                            text("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + query)
                        ).scalar()[0]
                        for _ in range(3)
                    ]
                    report["queries"].setdefault(name, {})[stage] = plans
        finally:
            transaction.rollback()
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
