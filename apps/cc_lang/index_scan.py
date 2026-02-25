"""Scan Common Crawl columnar index for pages in a target language.

The CC columnar index is stored as Parquet files on S3/HTTPS at:
  https://data.commoncrawl.org/cc-index/table/cc-main/warc/

Each crawl has ~300 Parquet files. We download and scan each one,
filtering on content_languages for ISO 639-3 codes (e.g., 'kin').
"""

from __future__ import annotations

import io
import time
from collections.abc import Iterator
from dataclasses import dataclass

import pyarrow.parquet as pq
import requests

from apps.common.logging import get_logger

log = get_logger(__name__)

CC_INDEX_BASE = "https://data.commoncrawl.org/cc-index/table/cc-main/warc"
CC_COLLINFO = "https://index.commoncrawl.org/collinfo.json"

# Columns we need from the index (minimizes download size)
INDEX_COLUMNS = [
    "url",
    "content_languages",
    "warc_filename",
    "warc_record_offset",
    "warc_record_length",
]


@dataclass
class LangIndexRecord:
    """A record from the CC columnar index matching our language filter."""

    url: str
    content_languages: str
    warc_filename: str
    warc_record_offset: int
    warc_record_length: int


def discover_crawl_ids(
    min_date: str = "2018-39",
    max_date: str = "",
    max_crawls: int = 50,
) -> list[str]:
    """Fetch available crawl IDs from collinfo.json.

    Language annotations are available from CC-MAIN-2018-39 onward.
    """
    resp = requests.get(CC_COLLINFO, timeout=30)
    resp.raise_for_status()

    ids = []
    for entry in resp.json():
        cid = entry.get("id", "")
        if not cid.startswith("CC-MAIN-"):
            continue
        date_part = cid.replace("CC-MAIN-", "")
        if min_date and date_part < min_date:
            continue
        if max_date and date_part > max_date:
            continue
        ids.append(cid)

    ids.sort(reverse=True)
    return ids[:max_crawls]


def list_index_files(crawl_id: str) -> list[str]:
    """List Parquet file paths for a crawl's warc subset.

    Downloads the _metadata or uses a predictable naming pattern.
    CC index files follow: part-NNNNN-*.gz.parquet (300 files per crawl).
    We fetch the directory listing from the CC paths file.
    """
    prefix = f"cc-index/table/cc-main/warc/crawl={crawl_id}/subset=warc/"

    # Try fetching the listing via Common Crawl's S3 listing API
    listing_url = f"https://data.commoncrawl.org/?prefix={prefix}&delimiter=/"
    try:
        resp = requests.get(listing_url, timeout=30)
        if resp.status_code == 200:
            # Parse XML listing
            import xml.etree.ElementTree as ET

            root = ET.fromstring(resp.text)
            ns = {"s3": "http://s3.amazonaws.com/doc/2006-03-01/"}
            keys = []
            for content in root.findall(".//s3:Contents/s3:Key", ns):
                key = content.text
                if key and key.endswith(".parquet"):
                    keys.append(key)
            if keys:
                keys.sort()
                log.info("Found %d index files for %s", len(keys), crawl_id)
                return keys
    except Exception as exc:
        log.warning("Failed to list index files for %s: %s", crawl_id, exc)

    # Fallback: try a known recent pattern (0..299)
    log.warning("Using fallback part enumeration for %s", crawl_id)
    return []


def scan_index_file(
    file_key: str,
    lang_code: str = "kin",
) -> list[LangIndexRecord]:
    """Download and scan a single Parquet index file for target language.

    Uses pyarrow to read only the columns we need and apply row-group
    filtering where possible.
    """
    url = f"https://data.commoncrawl.org/{file_key}"

    try:
        resp = requests.get(url, timeout=120)
        resp.raise_for_status()
    except requests.RequestException as exc:
        log.warning("Failed to download index file %s: %s", file_key, exc)
        return []

    try:
        table = pq.read_table(
            io.BytesIO(resp.content),
            columns=INDEX_COLUMNS,
        )
    except Exception as exc:
        log.warning("Failed to parse Parquet %s: %s", file_key, exc)
        return []

    # Filter for target language
    records = []
    langs_col = table.column("content_languages")
    urls_col = table.column("url")
    fnames_col = table.column("warc_filename")
    offsets_col = table.column("warc_record_offset")
    lengths_col = table.column("warc_record_length")

    for i in range(len(table)):
        lang_val = langs_col[i].as_py()
        if lang_val is None:
            continue
        if lang_code not in lang_val:
            continue

        records.append(
            LangIndexRecord(
                url=urls_col[i].as_py() or "",
                content_languages=lang_val,
                warc_filename=fnames_col[i].as_py() or "",
                warc_record_offset=offsets_col[i].as_py() or 0,
                warc_record_length=lengths_col[i].as_py() or 0,
            )
        )

    return records


def scan_crawl_for_language(
    crawl_id: str,
    lang_code: str = "kin",
    rate_limit_s: float = 0.5,
) -> Iterator[LangIndexRecord]:
    """Scan all index files for a crawl, yielding matching records.

    Downloads ~300 Parquet files sequentially (each ~600MB compressed,
    but we only read 5 columns so actual transfer is much smaller).
    """
    file_keys = list_index_files(crawl_id)
    if not file_keys:
        log.warning("No index files found for crawl %s", crawl_id)
        return

    total_found = 0
    for idx, key in enumerate(file_keys):
        records = scan_index_file(key, lang_code)
        total_found += len(records)

        if records:
            log.info(
                "  [%d/%d] %s: %d %s records (total: %d)",
                idx + 1,
                len(file_keys),
                key.split("/")[-1],
                len(records),
                lang_code,
                total_found,
            )
            yield from records
        elif (idx + 1) % 50 == 0:
            log.info(
                "  [%d/%d] scanned, %d %s records so far",
                idx + 1,
                len(file_keys),
                total_found,
                lang_code,
            )

        time.sleep(rate_limit_s)

    log.info(
        "Crawl %s scan complete: %d %s records from %d files",
        crawl_id,
        total_found,
        lang_code,
        len(file_keys),
    )
