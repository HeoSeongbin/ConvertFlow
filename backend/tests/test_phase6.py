from fastapi.testclient import TestClient
from sqlalchemy import select
from app.main import app
from app.core.db import Session
from app.models.job import Job, Event
from app.services.events import record_event
from app.services.lifecycle import lock_job
from test_phase3 import upload


def test_latest_events_cursor_preserves_existing_ascending_contract_and_ownership():
    client = TestClient(app)
    identifier = upload(client)
    with Session.begin() as db:
        lock_job(db, identifier)
        for _ in range(65):
            record_event(db, identifier, "TEST", "pagination fixture")
    default = client.get(
        f"/api/v1/jobs/{identifier}/events", params={"limit": 3}
    ).json()
    assert [e["sequence"] for e in default["items"]] == [1, 2, 3]
    assert default["nextAfter"] == 3
    before = None
    sequence = []
    while True:
        params = {"order": "desc", "limit": 30}
        if before is not None:
            params["before"] = before
        response = client.get(f"/api/v1/jobs/{identifier}/events", params=params)
        assert response.status_code == 200
        data = response.json()
        sequence.extend(e["sequence"] for e in data["items"])
        if not data["hasMore"]:
            break
        before = data["nextBefore"]
    assert sequence == list(range(66, 0, -1))
    assert (
        TestClient(app).get(f"/api/v1/jobs/{identifier}/events?order=desc").status_code
        == 404
    )
    with Session() as db:
        assert db.get(Job, identifier).status == "QUEUED"
        assert (
            len(db.scalars(select(Event).where(Event.job_id == identifier)).all()) == 66
        )


def test_event_cursor_validation():
    client = TestClient(app)
    identifier = upload(client)
    for query in ["order=bad", "order=desc&before=0", "limit=101"]:
        assert (
            client.get(f"/api/v1/jobs/{identifier}/events?{query}").status_code == 422
        )
