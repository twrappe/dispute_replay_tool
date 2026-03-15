#!/usr/bin/env python
"""
CLI entry point for the Dispute Replay Tool.

Usage:
    python replay.py --transaction-id TXN-9821
    python replay.py --transaction-id TXN-9821 --verbose
    python replay.py --transaction-id TXN-9821 --format json > replay.json
"""

import sys

import click

from replay_tool.replay_engine import build_timeline, get_events
from replay_tool.renderers import render_json, render_text


@click.command()
@click.option(
    "--transaction-id",
    required=True,
    help="The transaction ID to replay (e.g. TXN-9821).",
)
@click.option(
    "--verbose",
    is_flag=True,
    default=False,
    help="Include raw LLM prompt and response in extraction events.",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"], case_sensitive=False),
    default="text",
    show_default=True,
    help="Output format.",
)
def main(transaction_id: str, verbose: bool, output_format: str) -> None:
    try:
        events = get_events(transaction_id)
    except RuntimeError as exc:
        click.echo(f"Configuration error: {exc}", err=True)
        sys.exit(1)
    except Exception as exc:  # noqa: BLE001
        click.echo(f"Database error: {exc}", err=True)
        sys.exit(1)

    if not events:
        click.echo(f"No events found for transaction '{transaction_id}'.", err=True)
        sys.exit(1)

    timeline = build_timeline(events)

    if output_format == "json":
        click.echo(render_json(timeline))
    else:
        click.echo(render_text(timeline, verbose=verbose))


if __name__ == "__main__":
    main()
