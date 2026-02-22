"""Download Kinyarwanda Wikipedia dump from Wikimedia."""

from __future__ import annotations

from pathlib import Path

import requests

from apps.common.logging import get_logger

log = get_logger(__name__)

RW_DUMP_URL = "https://dumps.wikimedia.org/rwwiki/latest/rwwiki-latest-pages-articles.xml.bz2"

# rw Wikipedia is small — dump should be under 100MB
MAX_EXPECTED_BYTES = 100 * 1024 * 1024


def download_rw_dump(output_dir: str, url: str = RW_DUMP_URL) -> Path:
    """Download the Kinyarwanda Wikipedia dump.

    Skips download if file already exists with matching Content-Length.
    Returns path to the downloaded .xml.bz2 file.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    dest = out / "rwwiki-latest-pages-articles.xml.bz2"

    # Check remote size via HEAD
    head = requests.head(url, timeout=30, allow_redirects=True)
    head.raise_for_status()
    remote_size = int(head.headers.get("Content-Length", 0))

    if remote_size > MAX_EXPECTED_BYTES:
        raise ValueError(
            f"Dump size {remote_size} exceeds {MAX_EXPECTED_BYTES} — "
            "check URL is for rw (Kinyarwanda), not rw+others"
        )

    # Skip if already downloaded and size matches
    if dest.exists() and remote_size > 0 and dest.stat().st_size == remote_size:
        log.info("Dump already downloaded: %s (%d bytes)", dest, remote_size)
        return dest

    log.info("Downloading %s (%d bytes) -> %s", url, remote_size, dest)
    resp = requests.get(url, stream=True, timeout=300)
    resp.raise_for_status()

    downloaded = 0
    with open(dest, "wb") as f:
        for chunk in resp.iter_content(chunk_size=1024 * 1024):
            f.write(chunk)
            downloaded += len(chunk)
            if downloaded % (10 * 1024 * 1024) < len(chunk):
                log.info("  downloaded %d MB...", downloaded // (1024 * 1024))

    log.info("Download complete: %s (%d bytes)", dest, downloaded)
    return dest
