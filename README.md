# Dispute Replay Tool

> Reconstruct the full decision timeline of any freight billing transaction — every input received, every LLM call made, every rule fired, every state transition — as a human-readable audit log.

---

## Problem Statement

When a carrier or shipper disputes an invoice, analysts face a painful investigation: piecing together what data the system had, what the AI extracted, which contract terms were applied, and in what order decisions were made. This process is manual, slow, and error-prone — especially when disputes arrive weeks after the original transaction.

The Dispute Replay Tool solves this by making every billing decision **deterministically replayable** from a structured event log.

---

## How It Works

Every meaningful action in the billing pipeline is emitted as an immutable event:

```
document.received        → raw input captured
extraction.completed     → LLM output + confidence scores recorded
contract.retrieved       → RAG retrieval result stored (chunks + scores)
rule.fired               → which rule, which inputs, which output
workflow.state_changed   → transition recorded with triggering event
invoice.generated        → final billing output with full lineage
```

Given a `transaction_id`, the tool reconstructs the complete timeline and renders it as a structured audit log — queryable via SQL, viewable in a UI, and exportable for dispute resolution.

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                  Billing Pipeline                    │
│  (extraction → contract retrieval → rules → invoice) │
└──────────────────────┬──────────────────────────────┘
                       │ emits events
                       ▼
┌─────────────────────────────────────────────────────┐
│                   Event Store                        │
│     (Postgres / append-only, immutable log)          │
└──────────────────────┬──────────────────────────────┘
                       │ queried by
                       ▼
┌─────────────────────────────────────────────────────┐
│              Replay Engine                           │
│   reconstructs timeline for a given transaction_id  │
└──────────────────────┬──────────────────────────────┘
                       │ renders to
                ┌──────┴──────┐
                ▼             ▼
           CLI output      REST API
           (JSON/text)    (for UI or export)
```

---

## Event Schema

Each event is stored with a consistent envelope:

```json
{
  "event_id": "uuid",
  "transaction_id": "TXN-9821",
  "event_type": "extraction.completed",
  "timestamp": "2024-11-14T14:32:07Z",
  "pipeline_version": "1.4.2",
  "model_version": "gpt-4o-2024-08-06",
  "payload": {
    "input_document_id": "doc_abc123",
    "extracted_fields": {
      "pickup_time": { "value": "2024-11-14T14:00:00Z", "confidence": 0.91 },
      "delivery_time": { "value": "2024-11-14T18:47:00Z", "confidence": 0.74 },
      "weight_lbs": { "value": 4200, "confidence": 0.98 }
    },
    "low_confidence_fields": ["delivery_time"],
    "raw_llm_prompt": "...",
    "raw_llm_response": "..."
  }
}
```

Key design decisions:
- **Immutable** — events are never updated, only appended
- **Self-contained** — each event stores the full LLM input/output, not just a reference
- **Versioned** — model and pipeline versions are captured on every event

---

## Replay Output Example

```
DISPUTE REPLAY: TXN-9821
Generated: 2024-12-01T09:15:00Z
─────────────────────────────────────────────────────

[14:31:02] DOCUMENT RECEIVED
  Source:    email attachment (carrier@freightco.com)
  File:      BOL_9821.pdf
  Doc ID:    doc_abc123

[14:32:07] EXTRACTION COMPLETED  ⚠️ LOW CONFIDENCE
  Model:     gpt-4o-2024-08-06
  Pipeline:  v1.4.2
  Fields:
    pickup_time    → 2024-11-14 14:00  (confidence: 0.91)
    delivery_time  → 2024-11-14 18:47  (confidence: 0.74) ⚠️
    weight_lbs     → 4,200 lbs         (confidence: 0.98)

[14:32:09] CONTRACT RETRIEVED
  Contract:  CTR-441 (FreightCo Master Agreement, effective 2024-01-01)
  Retrieval: chunk_id=c_8812, score=0.87
  Relevant clause: "Detention charges apply after 2hr free time at delivery"

[14:32:09] RULE FIRED: detention_charge_calculator
  Inputs:
    scheduled_delivery  → 2024-11-14 16:00 (from contract)
    actual_delivery     → 2024-11-14 18:47 (from extraction)
    free_time_hours     → 2 (from contract clause)
  Calculation:  (18:47 - 16:00) - 2hr free time = 0hr 47min
  Output:       No detention charge (under free time threshold)

[14:32:10] INVOICE GENERATED
  Total:     $3,840.00
  Line items: base_rate=$3,840, detention=$0, fuel_surcharge=$0

─────────────────────────────────────────────────────
DISPUTE NOTES:
  Carrier claims delivery at 15:45, not 18:47.
  → Extraction confidence for delivery_time was LOW (0.74)
  → Recommend: pull telematics data for TXN-9821 to arbitrate
```

---

## Quickstart

### Prerequisites

- Python 3.11+
- PostgreSQL 15+
- Access to the billing pipeline's event stream (Kafka / SQS / direct DB)

### Installation

```bash
git clone https://github.com/your-org/dispute-replay-tool
cd dispute-replay-tool
pip install -r requirements.txt
cp .env.example .env  # configure DB and event store connection
python scripts/migrate.py
```

### Replay a Transaction

```bash
# CLI
python replay.py --transaction-id TXN-9821

# With full LLM prompt/response output
python replay.py --transaction-id TXN-9821 --verbose

# Export as JSON
python replay.py --transaction-id TXN-9821 --format json > replay.json
```

### REST API

```bash
uvicorn app:app --reload

GET /replay/{transaction_id}
GET /replay/{transaction_id}?format=json
GET /replay/{transaction_id}/events          # raw event log
GET /replay/{transaction_id}/diff?compare=v2 # compare two pipeline runs
```

---

## Instrumentation Guide

To make a pipeline stage replayable, emit an event after each meaningful action:

```python
from replay_tool.emitter import EventEmitter

emitter = EventEmitter(transaction_id=txn_id)

# After LLM extraction
emitter.emit("extraction.completed", payload={
    "input_document_id": doc_id,
    "extracted_fields": fields_with_confidence,
    "raw_llm_prompt": prompt,
    "raw_llm_response": response,
    "model_version": model_version,
    "pipeline_version": PIPELINE_VERSION,
})
```

---

## SQL Analysis

The event store is designed to be queried directly for investigation:

```sql
-- Find all transactions where delivery_time confidence was below 0.8
SELECT
    transaction_id,
    payload->'extracted_fields'->'delivery_time'->>'confidence' AS confidence,
    timestamp
FROM events
WHERE event_type = 'extraction.completed'
  AND (payload->'extracted_fields'->'delivery_time'->>'confidence')::float < 0.8
ORDER BY timestamp DESC;

-- Find transactions that skipped detention calculation
SELECT e1.transaction_id
FROM events e1
WHERE e1.event_type = 'invoice.generated'
  AND NOT EXISTS (
    SELECT 1 FROM events e2
    WHERE e2.transaction_id = e1.transaction_id
      AND e2.event_type = 'rule.fired'
      AND e2.payload->>'rule_name' = 'detention_charge_calculator'
  );
```

---

## Key Design Decisions

**Why append-only events instead of snapshotting state?**
Snapshots tell you *what* the final state was. Events tell you *how* you got there. Disputes require the latter.

**Why store raw LLM prompts and responses?**
Model behavior changes across versions. Storing the full prompt/response means you can reproduce the exact conditions that led to a disputed output, even after the model is updated.

**Why capture confidence scores as first-class fields?**
Low-confidence extractions are the most common root cause of disputes. Making confidence queryable lets you proactively identify at-risk invoices before disputes are raised.

---

## Roadmap

- [ ] Side-by-side diff between two pipeline versions for the same transaction
- [ ] Automated dispute risk scoring at invoice generation time
- [ ] Webhook integration to auto-generate replay reports when disputes are opened
- [ ] Integration with Datadog/Honeycomb for trace correlation

---

## License

MIT
#   d i s p u t e _ r e p l a y _ t o o l  
 