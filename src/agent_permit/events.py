from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from agent_permit.analytics import AnalyticsEvent, append_analytics_event
from agent_permit.db import PostgresStore, RunEventRecord


class EventSink(Protocol):
    def publish(self, event: AnalyticsEvent) -> None:
        pass


@dataclass(frozen=True)
class JsonlEventSink:
    path: Path

    def publish(self, event: AnalyticsEvent) -> None:
        append_analytics_event(self.path, event)


@dataclass
class DatabaseEventSink:
    store: PostgresStore
    scan_run_id: str
    job_id: str | None = None
    sequence: int = 0

    def publish(self, event: AnalyticsEvent) -> None:
        self.sequence += 1
        self.store.append_run_event(
            RunEventRecord(
                job_id=self.job_id,
                scan_run_id=self.scan_run_id,
                event_name=event.event_name,
                sequence=self.sequence,
                occurred_at=event.occurred_at,
                payload_json=event.payload,
            )
        )


@dataclass
class EventPublisher:
    sinks: list[EventSink] = field(default_factory=list)

    def publish(self, event: AnalyticsEvent) -> None:
        for sink in self.sinks:
            sink.publish(event)
