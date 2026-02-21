"""Tests for S3 client factory."""

from unittest.mock import patch

from apps.common.config_types import S3Config
from apps.common.s3_client import get_s3_client


def test_creates_client_with_defaults():
    cfg = S3Config(enabled=True, bucket="test-bucket")
    with patch("apps.common.s3_client.boto3") as mock_boto:
        get_s3_client(cfg)
        mock_boto.Session.assert_called_once_with()
        mock_boto.Session().client.assert_called_once_with("s3")


def test_passes_region_and_endpoint():
    cfg = S3Config(
        enabled=True,
        bucket="test-bucket",
        region="us-east-1",
        endpoint_url="http://localhost:9000",
    )
    with patch("apps.common.s3_client.boto3") as mock_boto:
        get_s3_client(cfg)
        mock_boto.Session().client.assert_called_once_with(
            "s3",
            region_name="us-east-1",
            endpoint_url="http://localhost:9000",
        )


def test_passes_profile():
    cfg = S3Config(enabled=True, bucket="test-bucket", profile="my-profile")
    with patch("apps.common.s3_client.boto3") as mock_boto:
        get_s3_client(cfg)
        mock_boto.Session.assert_called_once_with(profile_name="my-profile")
