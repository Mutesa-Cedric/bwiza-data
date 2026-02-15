"""Minimal WET record parser."""

from collections.abc import Iterator
from dataclasses import dataclass

_WARC_RECORD_START = "WARC/1.0"
_TARGET_URI_PREFIX = "WARC-Target-URI:"
_CONTENT_TYPE_LINE = "Content-Type: text/plain"


@dataclass
class WetRecord:
    """A single record extracted from a WET file."""

    url: str | None
    text: str


def parse_wet(lines_iter: Iterator[str]) -> Iterator[WetRecord]:
    """Parse WET format lines into records."""
    url = None
    payload_lines: list[str] = []
    in_payload = False
    header_done = False

    for raw_line in lines_iter:
        line = raw_line.rstrip("\n").rstrip("\r")

        if line.startswith(_WARC_RECORD_START):
            # Emit previous record if we have payload
            if payload_lines and url:
                text = "\n".join(payload_lines).strip()
                if text:
                    yield WetRecord(url=url, text=text)

            url = None
            payload_lines = []
            in_payload = False
            header_done = False
            continue

        if not header_done:
            if line.startswith(_TARGET_URI_PREFIX):
                url = line[len(_TARGET_URI_PREFIX) :].strip()
            elif line == "":
                # Empty line separates headers from payload
                header_done = True
                in_payload = True
            continue

        if in_payload:
            payload_lines.append(line)

    # Emit last record
    if payload_lines and url:
        text = "\n".join(payload_lines).strip()
        if text:
            yield WetRecord(url=url, text=text)
