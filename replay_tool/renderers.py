"""
Renderers — convert a timeline of Events into human-readable text or JSON.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from replay_tool.models import Event, EventType

# Confidence threshold below which a field is flagged as low-confidence
LOW_CONFIDENCE_THRESHOLD = 0.80

_DIVIDER = "─" * 53


def _fmt_time(ts: datetime) -> str:
    return ts.strftime("%H:%M:%S")


def _has_low_confidence(payload: dict[str, Any]) -> bool:
    fields = payload.get("extracted_fields", {})
    for field_data in fields.values():
        if isinstance(field_data, dict):
            conf = field_data.get("confidence")
            if conf is not None and float(conf) < LOW_CONFIDENCE_THRESHOLD:
                return True
    return False


def _render_document_received(event: Event) -> list[str]:
    p = event.payload
    lines = [
        f"[{_fmt_time(event.timestamp)}] DOCUMENT RECEIVED",
        f"  Source:    {p.get('source', 'unknown')}",
        f"  File:      {p.get('file_name', 'unknown')}",
        f"  Doc ID:    {p.get('document_id', 'unknown')}",
    ]
    return lines


def _render_extraction_completed(event: Event, verbose: bool) -> list[str]:
    p = event.payload
    low_conf = _has_low_confidence(p)
    flag = "  \u26a0\ufe0f LOW CONFIDENCE" if low_conf else ""
    lines = [
        f"[{_fmt_time(event.timestamp)}] EXTRACTION COMPLETED{flag}",
        f"  Model:     {event.model_version or 'unknown'}",
        f"  Pipeline:  v{event.pipeline_version}",
        "  Fields:",
    ]
    for field_name, field_data in p.get("extracted_fields", {}).items():
        if isinstance(field_data, dict):
            val = field_data.get("value", "")
            conf = field_data.get("confidence", "")
            warn = " \u26a0\ufe0f" if conf != "" and float(conf) < LOW_CONFIDENCE_THRESHOLD else ""
            lines.append(f"    {field_name:<20} \u2192 {val}  (confidence: {conf}){warn}")
        else:
            lines.append(f"    {field_name:<20} \u2192 {field_data}")
    if verbose:
        if p.get("raw_llm_prompt"):
            lines += ["  Raw LLM Prompt:", f"    {p['raw_llm_prompt']}"]
        if p.get("raw_llm_response"):
            lines += ["  Raw LLM Response:", f"    {p['raw_llm_response']}"]
    return lines


def _render_contract_retrieved(event: Event) -> list[str]:
    p = event.payload
    lines = [
        f"[{_fmt_time(event.timestamp)}] CONTRACT RETRIEVED",
        f"  Contract:  {p.get('contract_id', 'unknown')} ({p.get('contract_name', '')})",
        f"  Retrieval: chunk_id={p.get('chunk_id', 'unknown')}, score={p.get('score', 'unknown')}",
        f"  Relevant clause: \"{p.get('relevant_clause', '')}\"",
    ]
    return lines


def _render_rule_fired(event: Event) -> list[str]:
    p = event.payload
    lines = [
        f"[{_fmt_time(event.timestamp)}] RULE FIRED: {p.get('rule_name', 'unknown')}",
        "  Inputs:",
    ]
    for k, v in p.get("inputs", {}).items():
        if isinstance(v, dict):
            lines.append(f"    {k:<24} \u2192 {v.get('value', '')}  ({v.get('source', '')})")
        else:
            lines.append(f"    {k:<24} \u2192 {v}")
    if p.get("calculation"):
        lines.append(f"  Calculation:  {p['calculation']}")
    if "output" in p:
        lines.append(f"  Output:       {p['output']}")
    return lines


def _render_workflow_state_changed(event: Event) -> list[str]:
    p = event.payload
    lines = [
        f"[{_fmt_time(event.timestamp)}] WORKFLOW STATE CHANGED",
        f"  From:          {p.get('from_state', 'unknown')}",
        f"  To:            {p.get('to_state', 'unknown')}",
        f"  Triggered by:  {p.get('trigger_event', 'unknown')}",
    ]
    return lines


def _render_invoice_generated(event: Event) -> list[str]:
    p = event.payload
    lines = [
        f"[{_fmt_time(event.timestamp)}] INVOICE GENERATED",
        f"  Total:     {p.get('total', 'unknown')}",
    ]
    items = p.get("line_items", {})
    if items:
        formatted = ", ".join(f"{k}={v}" for k, v in items.items())
        lines.append(f"  Line items: {formatted}")
    return lines


def render_text(timeline: list[Event], verbose: bool = False) -> str:
    if not timeline:
        return "No events found for this transaction."

    transaction_id = timeline[0].transaction_id
    generated_at = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    output: list[str] = [
        f"DISPUTE REPLAY: {transaction_id}",
        f"Generated: {generated_at}",
        _DIVIDER,
        "",
    ]

    for event in timeline:
        if event.event_type == EventType.DOCUMENT_RECEIVED:
            output.extend(_render_document_received(event))
        elif event.event_type == EventType.EXTRACTION_COMPLETED:
            output.extend(_render_extraction_completed(event, verbose))
        elif event.event_type == EventType.CONTRACT_RETRIEVED:
            output.extend(_render_contract_retrieved(event))
        elif event.event_type == EventType.RULE_FIRED:
            output.extend(_render_rule_fired(event))
        elif event.event_type == EventType.WORKFLOW_STATE_CHANGED:
            output.extend(_render_workflow_state_changed(event))
        elif event.event_type == EventType.INVOICE_GENERATED:
            output.extend(_render_invoice_generated(event))
        output.append("")

    output.append(_DIVIDER)
    return "\n".join(output)


def render_json(timeline: list[Event]) -> str:
    return json.dumps(
        [json.loads(e.model_dump_json()) for e in timeline],
        indent=2,
    )
