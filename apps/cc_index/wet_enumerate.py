"""Enumerate WET file URLs from Common Crawl's wet.paths.gz manifest."""

import gzip

import requests

from apps.common.logging import get_logger

log = get_logger(__name__)

CC_DATA_BASE = "https://data.commoncrawl.org"


def enumerate_wet_urls(
    crawl: str,
    user_agent: str = "bwiza-data/0.1",
    timeout_s: int = 60,
) -> list[str]:
    """Fetch and parse wet.paths.gz for a given crawl, returning full URLs.

    This replaces manual management of configs/wet_sample_urls.txt.
    Each crawl has ~90K WET files; use max_wet_files in CCConfig to limit.
    """
    paths_url = f"{CC_DATA_BASE}/crawl-data/{crawl}/wet.paths.gz"
    log.info("Fetching WET paths from %s", paths_url)

    resp = requests.get(
        paths_url,
        timeout=timeout_s,
        headers={"User-Agent": user_agent},
    )
    resp.raise_for_status()

    raw = gzip.decompress(resp.content)
    lines = raw.decode("utf-8", errors="replace").strip().splitlines()

    urls = [f"{CC_DATA_BASE}/{line.strip()}" for line in lines if line.strip()]
    log.info("Found %d WET file URLs for crawl %s", len(urls), crawl)
    return urls
