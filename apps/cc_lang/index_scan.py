"""Scan Common Crawl columnar index for pages in a target language.

The CC columnar index is stored as Parquet files on S3/HTTPS at:
  https://data.commoncrawl.org/cc-index/table/cc-main/warc/

Each crawl has ~300 Parquet files (~900MB each, 7.5M rows).
We use DuckDB's HTTP range-read support to query only the columns
we need without downloading full files (>99% bandwidth savings).
"""

from __future__ import annotations

import gzip
import time
from collections.abc import Iterator
from dataclasses import dataclass

import duckdb
import requests

from apps.common.logging import get_logger

log = get_logger(__name__)

CC_COLLINFO = "https://index.commoncrawl.org/collinfo.json"
CC_DATA_BASE = "https://data.commoncrawl.org"

# Columns we need from the index
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

    Downloads cc-index-table.paths.gz and filters for subset=warc.
    """
    paths_url = f"{CC_DATA_BASE}/crawl-data/{crawl_id}/cc-index-table.paths.gz"
    try:
        resp = requests.get(paths_url, timeout=60)
        resp.raise_for_status()
        all_paths = gzip.decompress(resp.content).decode().strip().split("\n")
        warc_paths = [p for p in all_paths if "subset=warc" in p and p.endswith(".parquet")]
        warc_paths.sort()
        if warc_paths:
            log.info("Found %d index files for %s", len(warc_paths), crawl_id)
            return warc_paths
    except Exception as exc:
        log.warning("Failed to list index files for %s: %s", crawl_id, exc)

    return []


def scan_index_file(
    file_key: str,
    lang_code: str = "kin",
) -> list[LangIndexRecord]:
    """Query a single Parquet index file for target language using DuckDB.

    DuckDB reads remote Parquet via HTTP range requests, fetching only
    the columns needed. For a 900MB file with 7.5M rows, this typically
    downloads <5MB to find language matches.
    """
    url = f"{CC_DATA_BASE}/{file_key}"

    try:
        con = duckdb.connect()
        con.execute("INSTALL httpfs; LOAD httpfs;")

        query = f"""
            SELECT url, content_languages, warc_filename,
                   warc_record_offset, warc_record_length
            FROM read_parquet('{url}')
            WHERE content_languages IS NOT NULL
              AND content_languages LIKE '%{lang_code}%'
        """
        rows = con.execute(query).fetchall()
        con.close()
    except Exception as exc:
        log.warning("Failed to query index file %s: %s", file_key, exc)
        return []

    records = []
    for row in rows:
        records.append(
            LangIndexRecord(
                url=row[0] or "",
                content_languages=row[1] or "",
                warc_filename=row[2] or "",
                warc_record_offset=row[3] or 0,
                warc_record_length=row[4] or 0,
            )
        )

    return records


def scan_crawl_for_language(
    crawl_id: str,
    lang_code: str = "kin",
    rate_limit_s: float = 0.5,
) -> Iterator[LangIndexRecord]:
    """Scan all index files for a crawl, yielding matching records.

    Uses DuckDB HTTP range reads — only downloads the columns needed
    (~5MB per file instead of ~900MB).
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
