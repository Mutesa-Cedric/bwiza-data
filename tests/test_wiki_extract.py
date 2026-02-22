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
    assert "</ref>" not in result
    assert "Source here" not in result
    assert "Fact." in result
    assert "More text." in result


def test_clean_wikitext_strips_ref_with_url():
    result = clean_wikitext("Fact.<ref>https://example.com/page</ref> More.")
    assert "</ref>" not in result
    assert "https://" not in result
    assert "Fact." in result
    assert "More." in result


def test_clean_wikitext_strips_self_closing_ref():
    result = clean_wikitext('Fact.<ref name="abc" /> More.')
    assert "<ref" not in result
    assert "Fact." in result


def test_clean_wikitext_strips_multiple_refs():
    raw = "A.<ref>src1</ref> B.<ref>src2</ref> C."
    result = clean_wikitext(raw)
    assert "</ref>" not in result
    assert "A." in result
    assert "B." in result
    assert "C." in result


def test_clean_wikitext_strips_references_tag():
    result = clean_wikitext("Text.\n<references />\nMore.")
    assert "<references" not in result


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


def test_clean_wikitext_strips_file_links():
    raw = "Text before.\n[[File:Rwanda_map.png|thumb|320x320px|Map of Rwanda]]\nText after."
    result = clean_wikitext(raw)
    assert "File:" not in result
    assert "thumb" not in result
    assert "320x320px" not in result
    assert "Text before." in result
    assert "Text after." in result


def test_clean_wikitext_strips_image_links():
    raw = "Intro.\n[[Image:Flag.svg|right|200px|Flag]]\nMore."
    result = clean_wikitext(raw)
    assert "Image:" not in result
    assert "right" not in result.lower().split("intro")[0]
    assert "200px" not in result
    assert "Intro." in result


def test_clean_wikitext_strips_dosiye_links():
    raw = "Intro.\n[[Dosiye:Photo.jpg|thumb|Caption]]\nMore."
    result = clean_wikitext(raw)
    assert "Dosiye:" not in result
    assert "thumb" not in result


def test_clean_wikitext_strips_tables():
    raw = 'Before.\n{| class="wikitable"\n|-\n! Header\n|-\n| Cell\n|}\nAfter.'
    result = clean_wikitext(raw)
    assert "wikitable" not in result
    assert "Before." in result
    assert "After." in result


def test_clean_wikitext_strips_thumb_residuals():
    result = clean_wikitext("thumb|Some caption text")
    assert "thumb|" not in result


def test_clean_wikitext_strips_px_sizes():
    result = clean_wikitext("320x320px|Flag of Germany")
    assert "320x320px" not in result


def test_clean_wikitext_strips_bare_urls():
    result = clean_wikitext("Text before. https://example.com/page Text after.")
    assert "https://" not in result
    assert "Text before." in result
    assert "Text after." in result


def test_clean_wikitext_strips_html_tags():
    result = clean_wikitext("Before.<div>content</div>After.")
    assert "<div>" not in result
    assert "</div>" not in result


def test_clean_wikitext_strips_br_tags():
    result = clean_wikitext("Line one.<br>Line two.<br/>More.")
    assert "<br" not in result


def test_clean_wikitext_decodes_html_entities():
    result = clean_wikitext("Babcock &amp; Wilcox")
    assert "&amp;" not in result
    assert "Babcock & Wilcox" in result


def test_clean_wikitext_strips_table_row_remnants():
    result = clean_wikitext("Before.\n|-\n| cell content\n|}\nAfter.")
    assert "|-" not in result
    assert "|}" not in result


def test_clean_wikitext_strips_unquoted_html_attrs():
    result = clean_wikitext("align=center colspan=2 text")
    assert "align=center" not in result
    assert "colspan=2" not in result


def test_clean_wikitext_strips_kinyarwanda_categories():
    result = clean_wikitext("Some text.\nIkiciro:Ibihugu by'Afurika\nIkiciro:Rwanda")
    assert "Ikiciro:" not in result
    assert "Some text." in result


def test_clean_wikitext_strips_french_categories():
    result = clean_wikitext("Du texte.\nCatégorie:Pays d'Afrique")
    assert "Catégorie:" not in result


def test_clean_wikitext_strips_magic_words():
    result = clean_wikitext("Content.\n__FORCETOC__\n__NOEDITSECTION__\nMore.")
    assert "__FORCETOC__" not in result
    assert "__NOEDITSECTION__" not in result
    assert "Content." in result


def test_clean_wikitext_strips_empty_parens():
    result = clean_wikitext("Joseph Habineza () was a politician.")
    assert "( )" not in result
    assert "()" not in result
    assert "Joseph Habineza" in result


def test_clean_wikitext_strips_soft_hyphens():
    result = clean_wikitext("bu\u00addahitisha amazi")
    assert "\u00ad" not in result
    assert "budahitisha" in result


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

[[File:Rwanda_map.png|thumb|320x320px|Ikarita y'u Rwanda]]
[[Image:Flag_of_Rwanda.svg|right|200px]]

{{Infobox country
| name = Rwanda
| capital = [[Kigali]]
}}

== Amateka ==
U Rwanda rwagize abami benshi.<ref>Igitabo cy'amateka</ref>

{| class="wikitable"
|-
! Umwaka !! Icyabaye
|-
| 1962 || Ubwigenge
|}

Nyuma y'ubwigenge, u Rwanda rwateye imbere mu by'ubukungu.{{citation needed}}

[[Category:Ibihugu by'Afurika]]
[[Ikiciro:Ibihugu]]
[[en:Rwanda]]
[[fr:Rwanda]]
__FORCETOC__"""

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
    assert "</ref>" not in result
    assert "Category:" not in result
    assert "Infobox" not in result
    assert "thumb" not in result
    assert "320x320px" not in result
    assert "File:" not in result
    assert "Image:" not in result
    assert "wikitable" not in result
    assert "|-" not in result
    assert "|}" not in result
    assert "Ikiciro:" not in result
    assert "__FORCETOC__" not in result
