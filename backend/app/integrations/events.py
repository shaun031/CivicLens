"""AWS transports: lazily constructed clients, bounded private envelopes, no email subscriptions."""

import json

from app.events.schema import Event


class EventBridgePublisher:
    def __init__(self, bus, client=None):
        self.bus, self._client = bus, client

    def publish(self, event: Event):
        if not self.bus:
            raise RuntimeError("EVENT_BUS_NAME is required")
        if self._client is None:
            import boto3
            from botocore.config import Config

            self._client = boto3.client(
                "events",
                config=Config(
                    connect_timeout=3,
                    read_timeout=5,
                    retries={"max_attempts": 2, "mode": "standard"},
                ),
            )
        result = self._client.put_events(
            Entries=[
                {
                    "EventBusName": self.bus,
                    "Source": event.source,
                    "DetailType": event.eventType,
                    "Detail": event.model_dump_json(),
                    "Time": event.occurredAt,
                }
            ]
        )
        if result.get("FailedEntryCount", 0) or not result.get("Entries", [{}])[0].get("EventId"):
            raise RuntimeError("EventBridge did not accept the event")
        return {"accepted": True}


class SNSPublisher:
    def __init__(self, topic, client=None, enabled=False):
        self.topic, self._client, self.enabled = topic, client, enabled

    def publish(self, event, *, eligible=False, opted_in=False):
        if not self.enabled or not eligible or not opted_in:
            return {
                "status": "SKIPPED",
                "reason": "Operational channel is not explicitly enabled and eligible",
            }
        if (
            event.eventType not in ("IncidentOverdue", "WorkflowFailed", "IncidentPriorityChanged")
            or not self.topic
        ):
            raise ValueError("Not an approved operational alert")
        if self._client is None:
            import boto3
            from botocore.config import Config

            self._client = boto3.client(
                "sns",
                config=Config(
                    connect_timeout=3,
                    read_timeout=5,
                    retries={"max_attempts": 2, "mode": "standard"},
                ),
            )
        # Never include recipient contact data, evidence, descriptions or arbitrary message text.
        message = json.dumps(
            {
                "eventId": str(event.eventId),
                "eventType": event.eventType,
                "aggregateId": str(event.aggregateId),
                "correlationId": str(event.correlationId),
            }
        )
        result = self._client.publish(
            TopicArn=self.topic, Subject="CivicLens operational review", Message=message
        )
        if not result.get("MessageId"):
            raise RuntimeError("SNS publication not confirmed")
        return {"status": "PUBLISHED", "messageId": result["MessageId"]}
