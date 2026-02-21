#!/usr/bin/env python3
"""Operational summary of recent runs from local state files.

Usage:
    python scripts/ops_summary.py
    python scripts/ops_summary.py --state-dir manifests/state
"""

import argparse
import json
import sys
from pathlib import Path

from apps.common.run_state import RunState


def load_all_states(state_dir: str) -> list[RunState]:
    """Load all RunState files from a directory."""
    d = Path(state_dir)
    if not d.exists():
        return []
    states = []
    for path in sorted(d.glob("*.json")):
        try:
            state = RunState.from_json(path.read_text())
            states.append(state)
        except (json.JSONDecodeError, KeyError):
            continue
    return states


def format_summary(states: list[RunState]) -> str:
    """Format a human-readable summary of all runs."""
    if not states:
        return "No runs found."

    lines = []
    header = (
        f"{'Run ID':<24} {'Pipeline':<20} {'Status':<12}"
        f" {'Done':>6} {'Failed':>6} {'Shards':>6} {'Updated'}"
    )
    lines.append(header)
    lines.append("-" * 110)

    for s in sorted(states, key=lambda x: x.updated_at or "", reverse=True):
        updated = s.updated_at[:19] if s.updated_at else "—"
        lines.append(
            f"{s.run_id:<24} {s.pipeline:<20} {s.status:<12} "
            f"{s.items_done:>6} {s.items_failed:>6} {s.shards_closed:>6} "
            f"{updated}"
        )

    # Summary
    by_status = {}
    for s in states:
        by_status.setdefault(s.status, []).append(s)

    lines.append("")
    lines.append("Summary:")
    for status, group in sorted(by_status.items()):
        total_done = sum(s.items_done for s in group)
        lines.append(f"  {status}: {len(group)} runs, {total_done} items done")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Ops summary of recent runs")
    parser.add_argument(
        "--state-dir",
        default="manifests/state",
        help="Directory containing state files",
    )
    args = parser.parse_args()

    states = load_all_states(args.state_dir)
    print(format_summary(states))
    return 0


if __name__ == "__main__":
    sys.exit(main())
