from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class EventType(str, Enum):
    """
    Enumeration of all pipeline event types that can be stored in the event log.

    Each value corresponds to a meaningful action in the billing pipeline.
    Add new values here when instrumenting additional pipeline stages.
    """

    DOCUMENT_RECEIVED = "document.received"
    EXTRACTION_COMPLETED = "extraction.completed"
    CONTRACT_RETRIEVED = "contract.retrieved"
    RULE_FIRED = "rule.fired"
    WORKFLOW_STATE_CHANGED = "workflow.state_changed"
    INVOICE_GENERATED = "invoice.generated"


class Event(BaseModel):
    """
    Immutable envelope for a single pipeline event.

    Every event written to the event store shares this structure. The `payload`
    field holds event-type-specific data (e.g. extracted fields, rule inputs,
    invoice line items) and is stored as JSONB in Postgres.

    Fields:
        event_id:         Unique identifier for this event (UUID v4).
        transaction_id:   The billing transaction this event belongs to.
        event_type:       The pipeline stage that produced this event.
        timestamp:        UTC time the event was emitted.
        pipeline_version: Version of the billing pipeline at emit time.
        model_version:    LLM model identifier, if applicable (e.g. extraction events).
        payload:          Event-type-specific data dictionary.
    """

    event_id: UUID
    transaction_id: str
    event_type: EventType
    timestamp: datetime
    pipeline_version: str
    model_version: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)