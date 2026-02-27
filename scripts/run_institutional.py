"""Run institutional wave 2 pipeline for one or all source domains."""

import argparse
import sys

from apps.common.config import load_config
from apps.common.logging import get_logger
from apps.institutional.run import run_institutional
from apps.institutional.source_profile import get_profile, load_profiles

log = get_logger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Institutional wave 2 pipeline")
    parser.add_argument(
        "--source",
        default="",
        help="Run single source by domain (e.g. minubumwe.gov.rw)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Discovery only")
    parser.add_argument("--resume", default="", help="Resume a previous run")
    parser.add_argument("--max-pages", type=int, default=0, help="Override max_listing_pages")
    parser.add_argument("--max-items", type=int, default=0, help="Override max_items")
    parser.add_argument(
        "--profiles",
        default="configs/institutional_sources.yaml",
        help="Path to source profiles YAML",
    )
    args = parser.parse_args()

    cfg = load_config()

    if args.source:
        profile = get_profile(args.source, args.profiles)
        if profile is None:
            print(f"Source not found: {args.source}", file=sys.stderr)
            sys.exit(1)
        profiles = [profile]
    else:
        profiles = load_profiles(args.profiles)

    if not profiles:
        print("No source profiles found.", file=sys.stderr)
        sys.exit(1)

    for profile in profiles:
        log.info("Starting institutional pipeline for %s", profile.domain)
        try:
            stats = run_institutional(
                cfg,
                profile,
                resume_run_id=args.resume,
                dry_run=args.dry_run,
                max_pages_override=args.max_pages,
                max_items_override=args.max_items,
            )
            log.info(
                "Done [%s]: kept=%d seen=%d chars=%d",
                profile.domain,
                stats.docs_kept,
                stats.docs_seen,
                stats.total_kept_chars,
            )
        except Exception:
            log.exception("FAILED [%s] — continuing to next source", profile.domain)
            continue


if __name__ == "__main__":
    main()
