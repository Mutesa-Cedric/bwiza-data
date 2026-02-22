"""Parse Wikipedia XML dump and extract clean article text."""

from __future__ import annotations

import bz2
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import mwparserfromhell

from apps.common.logging import get_logger

log = get_logger(__name__)

# MediaWiki XML namespace
MW_NS = "http://www.mediawiki.org/xml/export-0.10/"

# Tags to remove (non-content); keep formatting tags like b, i, small, sup, sub
_REMOVE_TAGS = frozenset(
    {
        "ref",
        "references",
        "gallery",
        "nowiki",
        "source",
        "syntaxhighlight",
        "code",
        "pre",
        "math",
        "score",
        "timeline",
        "imagemap",
        "includeonly",
        "noinclude",
        "onlyinclude",
        "categorytree",
    }
)

# Patterns to strip from extracted text (post-strip_code)
_CATEGORY_RE = re.compile(r"^Category:.*$", re.MULTILINE | re.IGNORECASE)
_INTERWIKI_RE = re.compile(r"^[a-z]{2,3}:.*$", re.MULTILINE)
_REF_TAG_RE = re.compile(r"<ref[^>]*/?>.*?(?:</ref>)?", re.DOTALL)
_CURLY_RE = re.compile(r"\{\{[^}]*\}\}")
_MULTI_NEWLINE_RE = re.compile(r"\n{3,}")
_HEADING_RE = re.compile(r"^=+\s*(.*?)\s*=+$", re.MULTILINE)


@dataclass
class WikiArticle:
    """A single extracted Wikipedia article."""

    title: str
    text: str
    page_id: int


def clean_wikitext(raw: str) -> str:
    """Remove wikitext markup and return plain text."""
    # Pre-strip ref tags (mwparserfromhell struggles with nested refs)
    text = _REF_TAG_RE.sub("", raw)

    # Parse with mwparserfromhell
    wikicode = mwparserfromhell.parse(text)

    # Remove templates (infoboxes, navboxes, etc.)
    for template in wikicode.filter_templates():
        try:
            wikicode.remove(template)
        except ValueError:
            pass

    # Remove non-content HTML tags (keep bold, italic, etc.)
    for tag in wikicode.filter_tags():
        if str(tag.tag).lower() in _REMOVE_TAGS:
            try:
                wikicode.remove(tag)
            except ValueError:
                pass

    # Get plain text (strips [[link|text]] -> text, etc.)
    text = wikicode.strip_code()

    # Post-processing: remove remaining markup artifacts
    text = _CATEGORY_RE.sub("", text)
    text = _INTERWIKI_RE.sub("", text)
    text = _CURLY_RE.sub("", text)

    # Convert headings to plain text
    text = _HEADING_RE.sub(r"\1", text)

    # Collapse whitespace
    text = _MULTI_NEWLINE_RE.sub("\n\n", text)
    return text.strip()


def _tag(local: str) -> str:
    """Return namespaced tag for MediaWiki XML."""
    return f"{{{MW_NS}}}{local}"


def parse_dump(dump_path: Path) -> Iterator[WikiArticle]:
    """Stream-parse a Wikipedia XML dump and yield articles.

    Handles both .xml.bz2 (compressed) and .xml (uncompressed) files.
    Skips redirects and non-article namespaces (ns != 0).
    """
    if dump_path.suffix == ".bz2" or dump_path.name.endswith(".xml.bz2"):
        opener = bz2.open(dump_path, "rb")
    else:
        opener = open(dump_path, "rb")

    count = 0
    skipped_redirect = 0
    skipped_ns = 0

    with opener as f:
        for event, elem in ET.iterparse(f, events=("end",)):
            if elem.tag != _tag("page"):
                continue

            # Check namespace — only ns=0 (articles)
            ns_elem = elem.find(_tag("ns"))
            if ns_elem is not None and ns_elem.text != "0":
                skipped_ns += 1
                elem.clear()
                continue

            # Skip redirects
            if elem.find(_tag("redirect")) is not None:
                skipped_redirect += 1
                elem.clear()
                continue

            title_elem = elem.find(_tag("title"))
            id_elem = elem.find(_tag("id"))
            revision = elem.find(_tag("revision"))
            text_elem = revision.find(_tag("text")) if revision is not None else None

            if title_elem is None or text_elem is None or text_elem.text is None:
                elem.clear()
                continue

            title = title_elem.text or ""
            page_id = int(id_elem.text) if id_elem is not None and id_elem.text else 0
            raw_text = text_elem.text

            cleaned = clean_wikitext(raw_text)
            if cleaned:
                count += 1
                yield WikiArticle(title=title, text=cleaned, page_id=page_id)

            # Free memory — critical for streaming large dumps
            elem.clear()

    log.info(
        "Parsed dump: %d articles extracted, %d redirects skipped, %d non-articles skipped",
        count,
        skipped_redirect,
        skipped_ns,
    )
