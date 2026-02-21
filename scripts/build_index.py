#!/usr/bin/env python3
"""Build a dataset index from run manifests."""

import argparse
import sys

from apps.packaging.build_index import build_and_write_index


def main() -> int:
    parser = argparse.ArgumentParser(description="Build dataset index from manifests")
    parser.add_argument(
        "--dataset",
        required=True,
        choices=["pretrain", "parallel", "instructions"],
        help="Dataset type to build index for",
    )
    parser.add_argument("--bucket", required=True, help="S3 bucket name")
    parser.add_argument("--version", default="v1", help="Dataset version (default: v1)")
    parser.add_argument(
        "--manifest-dir", default="manifests/shards", help="Local manifest directory"
    )
    parser.add_argument("--output-dir", default="outputs/datasets", help="Output base directory")
    args = parser.parse_args()

    path = build_and_write_index(
        dataset=args.dataset,
        s3_bucket=args.bucket,
        version=args.version,
        manifest_dir=args.manifest_dir,
        output_dir=args.output_dir,
    )
    print(f"Index written to: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
