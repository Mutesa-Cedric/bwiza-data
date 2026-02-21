"""S3 client factory with config-driven options."""

import boto3

from apps.common.config_types import S3Config
from apps.common.logging import get_logger

log = get_logger(__name__)


def get_s3_client(cfg: S3Config):
    """Build a boto3 S3 client from config. Reuse per run, not per upload."""
    kwargs = {}

    if cfg.region:
        kwargs["region_name"] = cfg.region

    if cfg.endpoint_url:
        kwargs["endpoint_url"] = cfg.endpoint_url

    session_kwargs = {}
    if cfg.profile:
        session_kwargs["profile_name"] = cfg.profile

    session = boto3.Session(**session_kwargs)
    client = session.client("s3", **kwargs)

    log.info(
        "S3 client created (bucket=%s, prefix=%s, endpoint=%s)",
        cfg.bucket,
        cfg.prefix,
        cfg.endpoint_url or "default",
    )
    return client
