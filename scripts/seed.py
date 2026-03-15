"""
Inserts the TXN-9821 sample transaction so the quickstart works immediately.

Run after migrate.py:
    python scripts/seed.py
"""

from replay_tool.emitter import EventEmitter


def seed() -> None:
    txn_id = "TXN-9821"
    emitter = EventEmitter(transaction_id=txn_id)

    # 1. Document received
    emitter.emit(
        "document.received",
        payload={
            "source": "email attachment (carrier@freightco.com)",
            "file_name": "BOL_9821.pdf",
            "document_id": "doc_abc123",
        },
    )
    print(f"[{txn_id}] Emitted: document.received")

    # 2. Extraction completed (delivery_time is low confidence)
    emitter.emit(
        "extraction.completed",
        model_version="gpt-4o-2024-08-06",
        payload={
            "input_document_id": "doc_abc123",
            "extracted_fields": {
                "pickup_time": {"value": "2024-11-14T14:00:00Z", "confidence": 0.91},
                "delivery_time": {"value": "2024-11-14T18:47:00Z", "confidence": 0.74},
                "weight_lbs": {"value": 4200, "confidence": 0.98},
            },
            "low_confidence_fields": ["delivery_time"],
            "raw_llm_prompt": "Extract pickup_time, delivery_time, weight_lbs from the attached BOL.",
            "raw_llm_response": '{"pickup_time": "2024-11-14T14:00:00Z", "delivery_time": "2024-11-14T18:47:00Z", "weight_lbs": 4200}',
        },
    )
    print(f"[{txn_id}] Emitted: extraction.completed")

    # 3. Contract retrieved
    emitter.emit(
        "contract.retrieved",
        payload={
            "contract_id": "CTR-441",
            "contract_name": "FreightCo Master Agreement, effective 2024-01-01",
            "chunk_id": "c_8812",
            "score": 0.87,
            "relevant_clause": "Detention charges apply after 2hr free time at delivery",
        },
    )
    print(f"[{txn_id}] Emitted: contract.retrieved")

    # 4. Rule fired
    emitter.emit(
        "rule.fired",
        payload={
            "rule_name": "detention_charge_calculator",
            "inputs": {
                "scheduled_delivery": {
                    "value": "2024-11-14 16:00",
                    "source": "from contract",
                },
                "actual_delivery": {
                    "value": "2024-11-14 18:47",
                    "source": "from extraction",
                },
                "free_time_hours": {
                    "value": 2,
                    "source": "from contract clause",
                },
            },
            "calculation": "(18:47 - 16:00) - 2hr free time = 0hr 47min",
            "output": "No detention charge (under free time threshold)",
        },
    )
    print(f"[{txn_id}] Emitted: rule.fired")

    # 5. Invoice generated
    emitter.emit(
        "invoice.generated",
        payload={
            "total": "$3,840.00",
            "line_items": {
                "base_rate": "$3,840",
                "detention": "$0",
                "fuel_surcharge": "$0",
            },
        },
    )
    print(f"[{txn_id}] Emitted: invoice.generated")

    print("\nSeed complete. Run: python replay.py --transaction-id TXN-9821")


if __name__ == "__main__":
    seed()
