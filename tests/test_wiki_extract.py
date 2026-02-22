"""Tests for Wikipedia article extraction."""

from pathlib import Path

from apps.wiki_miner.extract import WikiArticle, clean_wikitext, parse_dump

# Small XML fixture mimicking MediaWiki dump format
FIXTURE_XML = """\
<mediawiki xmlns="http://www.mediawiki.org/xml/export-0.10/">
  <page>
    <title>U Rwanda</title>
    <ns>0</ns>
    <id>1</id>
    <revision>
      <id>100</id>
      <text xml:space="preserve">'''U Rwanda''' ni igihugu kiri mu [[Afurika y'Iburasirazuba]].

== Amateka ==
U Rwanda rwagize abami benshi.

== Ubukungu ==
Ubukungu bw'u Rwanda burimo gukura.

[[Category:Ibihugu by'Afurika]]
[[en:Rwanda]]</text>
    </revision>
  </page>
  <page>
    <title>Redirect Page</title>
    <ns>0</ns>
    <id>2</id>
    <redirect title="U Rwanda" />
    <revision>
      <id>101</id>
      <text xml:space="preserve">#REDIRECT [[U Rwanda]]</text>
    </revision>
  </page>
  <page>
    <title>Talk:U Rwanda</title>
    <ns>1</ns>
    <id>3</id>
    <revision>
      <id>102</id>
      <text xml:space="preserve">This is a talk page discussion.</text>
    </revision>
  </page>
  <page>
    <title>Kigali</title>
    <ns>0</ns>
    <id>4</id>
    <revision>
      <id>103</id>
      <text xml:space="preserve">'''Kigali''' ni umurwa mukuru w'u {{Country|Rwanda}}.

Kigali ifite abaturage miliyoni {{formatnum:1200000}}.

== Isura ==
Kigali iherereye ku misozi.&lt;ref&gt;Source here&lt;/ref&gt;

{{Infobox city
| name = Kigali
| population = 1200000
}}</text>
    </revision>
  </page>
  <page>
    <title>Empty Article</title>
    <ns>0</ns>
    <id>5</id>
    <revision>
      <id>104</id>
      <text xml:space="preserve"></text>
    </revision>
  </page>
</mediawiki>
"""


def _write_fixture(tmp_path: Path) -> Path:
    path = tmp_path / "dump.xml"
    path.write_text(FIXTURE_XML, encoding="utf-8")
    return path


def test_parse_dump_extracts_articles(tmp_path):
    dump = _write_fixture(tmp_path)
    articles = list(parse_dump(dump))

    # Should get 2 articles: "U Rwanda" and "Kigali"
    # Skipped: redirect (id=2), talk page (ns=1), empty (id=5)
    assert len(articles) == 2
    titles = {a.title for a in articles}
    assert titles == {"U Rwanda", "Kigali"}


def test_parse_dump_skips_redirects(tmp_path):
    dump = _write_fixture(tmp_path)
    articles = list(parse_dump(dump))
    assert all(a.title != "Redirect Page" for a in articles)


def test_parse_dump_skips_non_articles(tmp_path):
    dump = _write_fixture(tmp_path)
    articles = list(parse_dump(dump))
    assert all(a.title != "Talk:U Rwanda" for a in articles)


def test_parse_dump_page_ids(tmp_path):
    dump = _write_fixture(tmp_path)
    articles = list(parse_dump(dump))
    ids = {a.page_id for a in articles}
    assert ids == {1, 4}


def test_parse_dump_article_is_dataclass(tmp_path):
    dump = _write_fixture(tmp_path)
    article = list(parse_dump(dump))[0]
    assert isinstance(article, WikiArticle)
    assert isinstance(article.text, str)
    assert isinstance(article.page_id, int)


def test_clean_wikitext_strips_bold():
    assert "Rwanda" in clean_wikitext("'''Rwanda'''")
    assert "'''" not in clean_wikitext("'''Rwanda'''")


def test_clean_wikitext_strips_links():
    result = clean_wikitext("[[Afurika y'Iburasirazuba]]")
    assert "[[" not in result
    assert "Afurika" in result


def test_clean_wikitext_strips_templates():
    result = clean_wikitext("Population: {{formatnum:1200000}}")
    assert "{{" not in result
    assert "}}" not in result


def test_clean_wikitext_strips_categories():
    result = clean_wikitext("Some text.\n[[Category:Ibihugu by'Afurika]]")
    assert "Category:" not in result
    assert "Some text." in result


def test_clean_wikitext_strips_interwiki():
    result = clean_wikitext("Some text.\n[[en:Rwanda]]")
    assert "[[en:" not in result
    assert "Some text." in result


def test_clean_wikitext_strips_ref_tags():
    result = clean_wikitext("Fact.<ref>Source here</ref> More text.")
    assert "<ref>" not in result
    assert "Fact." in result
    assert "More text." in result


def test_clean_wikitext_strips_infobox():
    raw = "Intro.\n{{Infobox city\n| name = Kigali\n| population = 1200000\n}}\nMore."
    result = clean_wikitext(raw)
    assert "Infobox" not in result
    assert "Intro." in result


def test_clean_wikitext_converts_headings():
    result = clean_wikitext("== Amateka ==\nContent here.")
    assert "==" not in result
    assert "Amateka" in result
    assert "Content here." in result


def test_clean_wikitext_empty_input():
    assert clean_wikitext("") == ""


def test_parse_dump_bz2(tmp_path):
    """Test that bz2-compressed dumps are handled."""
    import bz2

    compressed = bz2.compress(FIXTURE_XML.encode("utf-8"))
    dump = tmp_path / "dump.xml.bz2"
    dump.write_bytes(compressed)

    articles = list(parse_dump(dump))
    assert len(articles) == 2


def test_clean_wikitext_integration():
    """Integration test: full article cleanup."""
    raw = """\
'''U Rwanda''' ni igihugu kiri mu [[Afurika y'Iburasirazuba]].

{{Infobox country
| name = Rwanda
| capital = [[Kigali]]
}}

== Amateka ==
U Rwanda rwagize abami benshi.<ref>Igitabo cy'amateka</ref>

Nyuma y'ubwigenge, u Rwanda rwateye imbere mu by'ubukungu.{{citation needed}}

[[Category:Ibihugu by'Afurika]]
[[en:Rwanda]]
[[fr:Rwanda]]"""

    result = clean_wikitext(raw)

    # Should have clean content
    assert "U Rwanda" in result
    assert "igihugu" in result
    assert "Amateka" in result
    assert "ubwigenge" in result

    # Should not have markup
    assert "[[" not in result
    assert "]]" not in result
    assert "{{" not in result
    assert "}}" not in result
    assert "<ref>" not in result
    assert "Category:" not in result
    assert "Infobox" not in result
