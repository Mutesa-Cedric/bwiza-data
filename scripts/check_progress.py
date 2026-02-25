#!/usr/bin/env python3
"""Check live progress of all running/recent pipelines.

Reads RunState JSON files from manifests/state/ and prints a summary.
Safe to run while pipelines are active.

Usage:
    python scripts/check_progress.py           # all recent runs
    python scripts/check_progress.py --active   # only running/paused
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

STATE_DIR = Path("manifests/state")
SHARD_DIR = Path("outputs/shards")


def _load_states() -> list[dict]:
    if not STATE_DIR.exists():
        return []
    states = []
    for f in sorted(STATE_DIR.glob("*.json")):
        try:
            states.append(json.loads(f.read_text()))
        except (json.JSONDecodeError, OSError):
            continue
    return states


def _time_ago(iso_str: str) -> str:
    if not iso_str:
        return "—"
    try:
        dt = datetime.fromisoformat(iso_str)
        delta = datetime.now(timezone.utc) - dt
        hours = delta.total_seconds() / 3600
        if hours < 1:
            return f"{int(delta.total_seconds() / 60)}m ago"
        if hours < 24:
            return f"{hours:.1f}h ago"
        return f"{delta.days}d ago"
    except ValueError:
        return iso_str


def _format_bytes(b: int) -> str:
    if b < 1024:
        return f"{b} B"
    if b < 1024 * 1024:
        return f"{b / 1024:.1f} KB"
    return f"{b / (1024 * 1024):.1f} MB"


def main() -> int:
    parser = argparse.ArgumentParser(description="Check pipeline progress")
    parser.add_argument(
        "--active",
        action="store_true",
        help="Only show running or paused runs",
    )
    args = parser.parse_args()

    states = _load_states()
    if not states:
        print("No run states found in manifests/state/")
        return 0

    if args.active:
        states = [s for s in states if s.get("status") in ("running", "paused")]
        if not states:
            print("No active runs.")
            return 0

    # Sort: running first, then by updated_at desc
    status_order = {"running": 0, "paused": 1, "completed": 2, "failed": 3, "created": 4}
    states.sort(key=lambda s: (status_order.get(s.get("status", ""), 9), s.get("updated_at", "")))
    states.reverse()
    # But running should be first
    states.sort(key=lambda s: status_order.get(s.get("status", ""), 9))

    # Print
    header = (
        f"{'Pipeline':<20} {'Status':<10} {'Done':<12} "
        f"{'Shards':<8} {'Written':<10} {'Updated':<12} {'Run ID'}"
    )
    print(header)
    print("─" * len(header))

    for s in states:
        pipeline = s.get("pipeline", "?")
        status = s.get("status", "?")
        done = s.get("items_done", 0)
        total = s.get("items_total", 0)
        skipped = s.get("items_skipped", 0)
        shards = s.get("shards_closed", 0)
        written = s.get("bytes_written", 0)
        updated = _time_ago(s.get("updated_at", ""))
        run_id = s.get("run_id", "?")

        # Progress string
        if total > 0:
            pct = done / total * 100
            progress = f"{done}/{total} ({pct:.0f}%)"
        elif done > 0:
            progress = f"{done}"
        else:
            progress = "—"

        if skipped > 0:
            progress += f" +{skipped}skip"

        # Status indicator
        indicator = {
            "running": "▶ running",
            "paused": "⏸ paused",
            "completed": "✓ done",
            "failed": "✗ failed",
            "created": "○ created",
        }.get(status, status)

        print(
            f"{pipeline:<20} {indicator:<10} {progress:<12} {shards:<8} "
            f"{_format_bytes(written):<10} {updated:<12} {run_id}"
        )

        # Show current item for running pipelines
        current = s.get("current_item", "")
        if status == "running" and current:
            # Truncate long URLs
            if len(current) > 70:
                current = current[:67] + "..."
            print(f"  └─ {current}")

        # Show failure reason
        reason = s.get("failure_reason", "")
        if reason and status in ("failed", "paused"):
            print(f"  └─ reason: {reason}")

    # Overall corpus stats
    print()
    if SHARD_DIR.exists():
        shard_files = list(SHARD_DIR.rglob("*.jsonl.zst"))
        total_bytes = sum(f.stat().st_size for f in shard_files)
        print(f"Corpus: {len(shard_files)} shards, {_format_bytes(total_bytes)} compressed")

    return 0


if __name__ == "__main__":
    sys.exit(main())
