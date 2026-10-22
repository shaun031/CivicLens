from datetime import timedelta

from test_complaints import complaint_app as complaint_app
from test_complaints import complaint_client as complaint_client
from test_complaints import submit
from test_discovery import login_staff
from test_events import drain
from test_work_allocation import common

from app.events.schema import utcnow


def test_persisted_unsupported_outbox_version_is_dead_lettered(complaint_client, complaint_app):
    submit(complaint_client)
    repo = complaint_app.state.workflow_service.repository
    with repo.store.connection() as db:
        db.execute("UPDATE event_outbox SET event_version=2")
    assert repo.dispatch_one()
    dead = repo.listing("dead")["items"][0]
    assert dead["error_category"] == "INVALID_EVENT"
    login_staff(complaint_app, complaint_client)
    response = complaint_client.post(
        f"/api/admin/workflows/dead-letters/{dead['message_id']}/redrive", json=common()
    )
    assert response.status_code == 409


def test_exhausted_valid_transport_can_be_redriven_after_repair(complaint_client, complaint_app):
    submit(complaint_client)
    repo = complaint_app.state.workflow_service.repository
    clock = utcnow()
    repo.clock = lambda: clock

    def failed(event):
        raise OSError("Injected transport failure")

    for _ in range(5):
        assert repo.dispatch_one(failed)
        clock += timedelta(minutes=10)
    dead = repo.listing("dead")["items"][0]
    assert dead["error_category"] == "DISPATCH_FAILED"
    login_staff(complaint_app, complaint_client)
    response = complaint_client.post(
        f"/api/admin/workflows/dead-letters/{dead['message_id']}/redrive", json=common()
    )
    assert response.status_code == 200
    drain(complaint_app)
    assert repo.listing("dead")["items"] == []
    assert repo.listing("workflow")["items"][0]["status"] == "COMPLETED_WITH_REVIEW_REQUIRED"
