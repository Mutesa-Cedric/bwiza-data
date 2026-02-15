"""Tests for WET record parser."""

from apps.cc_miner.wet_parser import WetRecord, parse_wet


_SAMPLE_WET = """WARC/1.0
WARC-Type: conversion
WARC-Target-URI: https://example.rw/page1
Content-Type: text/plain
Content-Length: 26

Muraho neza. Amakuru?
Ni meza.
WARC/1.0
WARC-Type: conversion
WARC-Target-URI: https://example.rw/page2
Content-Type: text/plain
Content-Length: 10

Umugore w'igihugu.
"""


def test_parses_two_records():
    lines = _SAMPLE_WET.strip().split("\n")
    records = list(parse_wet(iter(lines)))
    assert len(records) == 2
    assert records[0].url == "https://example.rw/page1"
    assert "Muraho" in records[0].text
    assert records[1].url == "https://example.rw/page2"


def test_skips_record_without_url():
    wet = """WARC/1.0
WARC-Type: warcinfo
Content-Type: text/plain

some warcinfo text
WARC/1.0
WARC-Type: conversion
WARC-Target-URI: https://example.rw/real
Content-Type: text/plain

Real content here.
"""
    records = list(parse_wet(iter(wet.strip().split("\n"))))
    assert len(records) == 1
    assert records[0].url == "https://example.rw/real"


def test_empty_input():
    records = list(parse_wet(iter([])))
    assert records == []


def test_handles_empty_payload():
    wet = """WARC/1.0
WARC-Type: conversion
WARC-Target-URI: https://example.rw/empty
Content-Type: text/plain

"""
    records = list(parse_wet(iter(wet.strip().split("\n"))))
    assert records == []
