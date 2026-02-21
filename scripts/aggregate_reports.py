#!/usr/bin/env python3
"""Aggregate multiple RunReport files into a dataset summary."""

import json
import sys
from pathlib import Path

from apps.common.aggregate import aggregate_reports


def main() -> int:
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <reports_dir> [output_path]", file=sys.stderr)
        return 1

    reports_dir = Path(sys.argv[1])
    output_path = sys.argv[2] if len(sys.argv) > 2 else "outputs/reports/aggregate.json"

    if not reports_dir.is_dir():
        print(f"Not a directory: {reports_dir}", file=sys.stderr)
        return 1

    report_files = sorted(reports_dir.glob("*.json"))
    report_files = [f for f in report_files if f.name != "aggregate.json"]

    if not report_files:
        print(f"No report JSON files found in {reports_dir}", file=sys.stderr)
        return 1

    print(f"Aggregating {len(report_files)} reports...")
    result = aggregate_reports(report_files)

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False))

    print("\nAggregate summary:")
    print(f"  Runs: {result['runs']}")
    print(f"  Total docs seen: {result['total_docs_seen']:,}")
    print(f"  Total docs kept: {result['total_docs_kept']:,}")
    print(f"  Keep rate: {result['keep_rate']:.1%}")
    print(f"  Total tokens (est): {result['total_token_estimate']:,}")
    print(f"  Total shards: {result['total_shards']}")
    print(f"  Config consistent: {result['config_consistent']}")
    print(f"\nWritten to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
