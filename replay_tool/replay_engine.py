"""
Replay Engine — fetches and orders events for a given transaction_id.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

import psycopg2
from dotenv import load_dotenv

from replay_tool.models import Event, EventType

load_dotenv()

SELECT_SQL = """
SELECT
    event_id,
    transaction_id,
    event_type,
    timestamp,
    pipeline_version,
    model_version,
    payload
FROM events
WHERE transaction_id = %s
ORDER BY timestamp ASC, event_id ASC
"""


def get_events(transaction_id: str) -> list[Event]:
    """Return all events for a transaction ordered by timestamp."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError(
            "DATABASE_URL is not set. Copy .env.example to .env and configure it."
        )

    conn = psycopg2.connect(database_url)
    try:
        with conn.cursor() as cur:
            cur.execute(SELECT_SQL, (transaction_id,))
            rows = cur.fetchall()
    finally:
        conn.close()

    events: list[Event] = []
    for row in rows:
        event_id, txn_id, event_type, timestamp, pipeline_version, model_version, payload = row
        # psycopg2 returns JSONB as a dict already; guard against string form
        if isinstance(payload, str):
            payload = json.loads(payload)
        # Ensure timestamp is timezone-aware
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        events.append(
            Event(
                event_id=event_id,
                transaction_id=txn_id,
                event_type=EventType(event_type),
                timestamp=timestamp,
                pipeline_version=pipeline_version,
                model_version=model_version,
                payload=payload,
            )
        )
    return events


def build_timeline(events: list[Event]) -> list[Event]:
    """Return events sorted by timestamp (already ordered, kept for clarity)."""
    return sorted(events, key=lambda e: (e.timestamp, str(e.event_id)))
