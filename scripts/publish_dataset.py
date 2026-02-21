#!/usr/bin/env python3
"""Publish packaged dataset artifacts to S3."""

import argparse
import sys

from apps.common.config import load_config
from apps.common.s3_client import get_s3_client
from apps.packaging.publish import publish_dataset


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish dataset to S3")
    parser.add_argument(
        "--dataset",
        required=True,
        choices=["pretrain", "parallel", "instructions"],
        help="Dataset type",
    )
    parser.add_argument("--version", default="v1", help="Dataset version")
    parser.add_argument("--base-dir", required=True, help="Local directory with dataset artifacts")
    parser.add_argument("--bucket", required=True, help="S3 bucket name")
    parser.add_argument("--no-verify", action="store_true", help="Skip post-upload verification")
    args = parser.parse_args()

    cfg = load_config()
    client = get_s3_client(cfg.s3)

    result = publish_dataset(
        dataset=args.dataset,
        version=args.version,
        base_dir=args.base_dir,
        s3_client=client,
        bucket=args.bucket,
        s3_cfg=cfg.s3,
        verify=not args.no_verify,
    )

    print(f"Uploaded: {result.uploaded}")
    print(f"Skipped: {result.skipped}")
    print(f"Verified: {result.verified}")
    print(f"Failed: {result.failed}")

    if result.errors:
        print("\nErrors:")
        for err in result.errors:
            print(f"  {err}")

    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
