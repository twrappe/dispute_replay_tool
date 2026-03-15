"""
EventEmitter — inserts immutable events into the Postgres event store.

Usage:
    emitter = EventEmitter(transaction_id="TXN-9821")
    emitter.emit("extraction.completed", payload={...})
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any

import psycopg2
from dotenv import load_dotenv

from replay_tool.models import EventType

load_dotenv()

INSERT_SQL = """
INSERT INTO events
    (event_id, transaction_id, event_type, timestamp,
     pipeline_version, model_version, payload)
VALUES
    (%s, %s, %s, %s, %s, %s, %s)
"""


class EventEmitter:
    def __init__(self, transaction_id: str) -> None:
        self.transaction_id = transaction_id
        self.pipeline_version = os.getenv("PIPELINE_VERSION", "unknown")
        self._database_url = os.getenv("DATABASE_URL")
        if not self._database_url:
            raise RuntimeError(
                "DATABASE_URL is not set. Copy .env.example to .env and configure it."
            )

    def emit(
        self,
        event_type: str | EventType,
        payload: dict[str, Any],
        model_version: str | None = None,
    ) -> str:
        """Insert one event and return its event_id."""
        event_id = str(uuid.uuid4())
        timestamp = datetime.now(tz=timezone.utc)

        conn = psycopg2.connect(self._database_url)
        try:
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute(
                    INSERT_SQL,
                    (
                        event_id,
                        self.transaction_id,
                        str(event_type),
                        timestamp,
                        self.pipeline_version,
                        model_version,
                        json.dumps(payload),
                    ),
                )
        finally:
            conn.close()

        return event_id
