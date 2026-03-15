"""
FastAPI application for the Dispute Replay Tool.

Start:
    uvicorn app:app --reload

Endpoints:
    GET /replay/{transaction_id}               → rendered text audit log
    GET /replay/{transaction_id}?format=json   → JSON audit log
    GET /replay/{transaction_id}/events        → raw event list as JSON
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse, PlainTextResponse

from replay_tool.replay_engine import build_timeline, get_events
from replay_tool.renderers import render_json, render_text

app = FastAPI(
    title="Dispute Replay Tool",
    description="Reconstruct the full decision timeline of any freight billing transaction.",
    version="1.0.0",
)


@app.get(
    "/replay/{transaction_id}",
    summary="Render the audit log for a transaction",
    response_class=PlainTextResponse,
)
def replay(
    transaction_id: str,
    format: Annotated[Literal["text", "json"], Query(description="Output format")] = "text",
    verbose: Annotated[bool, Query(description="Include raw LLM prompts/responses")] = False,
) -> PlainTextResponse | JSONResponse:
    events = _fetch_or_404(transaction_id)
    timeline = build_timeline(events)

    if format == "json":
        import json
        return JSONResponse(content=json.loads(render_json(timeline)))

    return PlainTextResponse(content=render_text(timeline, verbose=verbose))


@app.get(
    "/replay/{transaction_id}/events",
    summary="Return the raw event list for a transaction",
)
def replay_events(transaction_id: str) -> JSONResponse:
    import json
    events = _fetch_or_404(transaction_id)
    timeline = build_timeline(events)
    return JSONResponse(content=json.loads(render_json(timeline)))


def _fetch_or_404(transaction_id: str):
    try:
        events = get_events(transaction_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Database error: {exc}") from exc

    if not events:
        raise HTTPException(
            status_code=404,
            detail=f"No events found for transaction '{transaction_id}'.",
        )
    return events
