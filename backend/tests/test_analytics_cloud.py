import copy
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from botocore.exceptions import ClientError

from app.core.config import Settings
from app.events.schema import new_event
from app.integrations.database.dynamodb_analytics import LIMITS, DynamoAnalytics
from app.models.incident import IncidentError


class OfflineClient:
    """No network-capable SDK object is created by these adapter fixtures."""

    def __init__(self):
        self.items = {}
        self.calls = []
        self.repository = None

    def decoded(self, item):
        return {k: self.repository.deserializer.deserialize(v) for k, v in item.items()}

    def get_item(self, **kwargs):
        self.calls.append(("get", kwargs))
        key = self.decoded(kwargs["Key"])
        value = self.items.get((key["pk"], key["sk"]))
        return {"Item": self.repository.encode(value)} if value else {}

    def put_item(self, **kwargs):
        self.calls.append(("put", kwargs))
        value = self.decoded(kwargs["Item"])
        if value["sk"] == "manifest":
            current = self.items.get((value["pk"], value["sk"]), {})
            if current.get("revision", 0) != value["revision"]:
                raise ClientError({"Error": {"Code": "ConditionalCheckFailedException"}}, "PutItem")
        self.items[(value["pk"], value["sk"])] = value

    def query(self, **kwargs):
        self.calls.append(("query", kwargs))
        pk = self.decoded(kwargs["ExpressionAttributeValues"])[":pk"]
        return {
            "Items": [
                self.repository.encode(v) for (p, _), v in sorted(self.items.items()) if p == pk
            ]
        }

    def transact_write_items(self, **kwargs):
        self.calls.append(("transact", kwargs))
        event = self.decoded(kwargs["TransactItems"][0]["Put"]["Item"])
        key = (event["pk"], event["sk"])
        if key in self.items:
            raise ClientError(
                {
                    "Error": {"Code": "TransactionCanceledException"},
                    "CancellationReasons": [{"Code": "ConditionalCheckFailed"}, {"Code": "None"}],
                },
                "TransactWriteItems",
            )
        self.items[key] = event
        manifest = self.items.setdefault((event["pk"], "manifest"), {"revision": 0})
        manifest.update(revision=manifest["revision"] + 1, dirty=True)


def repository():
    client = OfflineClient()
    settings = Settings(_env_file=None, app_env="test", workflow_table_name="offline-operations")
    value = DynamoAnalytics(settings, client)
    client.repository = value
    return value, client


def test_projection_staging_retries_invalidation_and_revision_fenced_publish():
    repo, client = repository()
    source = {key: [] for key in LIMITS}
    now = datetime.now(UTC).isoformat()
    staged = repo.stage_source(source, "test_generation", 0, now)
    assert staged["chunks"] == len(LIMITS)
    assert repo.snapshot()["incidents"] == []
    assert all(kwargs.get("ConsistentRead", True) for _, kwargs in client.calls)
    event = new_event("IncidentMembershipChanged", str(uuid4()))
    assert repo.observe(event) and not repo.observe(event)
    with pytest.raises(IncidentError) as error:
        repo.snapshot()
    assert error.value.status == 503
    with pytest.raises(ClientError):
        repo.stage_source(source, "stale_generation", 0, now)
    repo.stage_source(source, "reconciled_generation", 1, now)
    assert repo.snapshot()["meta"]["revision"] == 1
    # Older out-of-order events only invalidate; they cannot roll data backwards.
    old = new_event(
        "IncidentStatusChanged", str(uuid4()), now=datetime.now(UTC) - timedelta(days=10)
    )
    assert repo.observe(old)
    assert client.items[(repo.pk, "manifest")]["dirty"]
    assert not any(call == "scan" for call, _ in client.calls)


def test_cloud_absent_expired_incomplete_or_tampered_projection_never_fakes_zero():
    repo, client = repository()
    with pytest.raises(IncidentError):
        repo.snapshot()
    now = datetime.now(UTC).isoformat()
    repo.stage_source({key: [] for key in LIMITS}, "one", 0, now)
    first = next(v for (pk, _), v in client.items.items() if pk == repo.pk + "#one")
    saved = copy.deepcopy(first)
    first["body"] = json.dumps({"collection": "complaints", "rows": [{"password": "private"}]})
    with pytest.raises(IncidentError):
        repo.snapshot()
    first.update(saved)
    manifest = client.items[(repo.pk, "manifest")]
    manifest["calculatedAt"] = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
    with pytest.raises(IncidentError):
        repo.snapshot()
    manifest["calculatedAt"] = now
    manifest["chunks"] += 1
    with pytest.raises(IncidentError):
        repo.snapshot()


def test_cloud_projection_privacy_size_and_generation_validation_before_writes():
    repo, client = repository()
    now = datetime.now(UTC).isoformat()
    with pytest.raises(IncidentError):
        repo.stage_source({"complaints": [{"email": "secret@example.com"}]}, "one", 0, now)
    with pytest.raises(IncidentError):
        repo.stage_source({}, "bad/generation", 0, now)
    assert not client.calls
