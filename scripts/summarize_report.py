#!/usr/bin/env python3
"""Pretty-print key metrics from a RunReport JSON file."""

import json
import sys
from pathlib import Path


def summarize(data: dict) -> None:
    run_id = data.get("run_id", "unknown")
    source = data.get("source", "unknown")

    docs_seen = data.get("docs_seen", 0)
    docs_kept = data.get("docs_kept", 0)
    keep_rate = docs_kept / docs_seen if docs_seen else 0.0

    print(f"Run: {run_id} ({source})")
    print(f"  Crawl: {data.get('crawl_id', 'n/a')}")
    print(f"  Started: {data.get('started_at', 'n/a')}")
    print(f"  Ended: {data.get('ended_at', 'n/a')}")
    print()
    print(
        f"  WET files: {data.get('wet_files_succeeded', 0)}/{data.get('wet_files_attempted', 0)}"
    )
    print(f"  Docs seen: {docs_seen:,}")
    print(f"  Docs kept: {docs_kept:,} ({keep_rate:.1%})")
    print(f"  Docs deduped: {data.get('docs_deduped', 0):,}")
    print(f"  Avg doc chars: {data.get('avg_doc_chars_kept', 0):.0f}")
    print()
    print(f"  Shards: {data.get('shards_written', 0)}")
    print(f"  Bytes: {data.get('bytes_written', 0):,}")
    print(f"  Tokens (est): {data.get('token_estimate_total', 0):,}")
    print()

    reasons = data.get("reject_reasons", {})
    if reasons:
        print("  Top reject reasons:")
        for reason, count in sorted(reasons.items(), key=lambda x: -x[1])[:10]:
            print(f"    {reason}: {count:,}")
    else:
        print("  No rejections recorded.")

    print()
    domains = data.get("top_domains_kept", [])
    if domains:
        print("  Top kept domains:")
        for entry in domains[:10]:
            print(f"    {entry['domain']}: {entry['docs']:,}")

    lid_hist = data.get("lid_score_histogram", {})
    if lid_hist:
        print()
        print("  LID score distribution:")
        for bucket, count in sorted(lid_hist.items()):
            print(f"    {bucket}: {count:,}")

    print()
    fp = data.get("config_fingerprint", "")
    if fp:
        print(f"  Config fingerprint: {fp[:16]}...")
    git = data.get("git_commit", "")
    if git:
        print(f"  Git commit: {git}")


def main() -> int:
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <report.json>", file=sys.stderr)
        return 1

    path = Path(sys.argv[1])
    if not path.exists():
        print(f"File not found: {path}", file=sys.stderr)
        return 1

    data = json.loads(path.read_text())
    summarize(data)
    return 0


if __name__ == "__main__":
    sys.exit(main())
