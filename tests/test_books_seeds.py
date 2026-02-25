"""Tests for books corpus seed loader."""

from apps.books_corpus.seeds import domain_for_seed, load_book_seeds


def test_load_book_seeds_url_only(tmp_path):
    p = tmp_path / "books.txt"
    p.write_text("https://example.org/book.pdf\n", encoding="utf-8")

    seeds = load_book_seeds(p)
    assert len(seeds) == 1
    assert seeds[0].url == "https://example.org/book.pdf"
    assert seeds[0].license_status == "unknown"


def test_load_book_seeds_tsv_fields(tmp_path):
    p = tmp_path / "books.txt"
    p.write_text(
        "https://reb.rw/file.pdf\tREB S4\treb.rw\tunknown\tunknown\tverify\n",
        encoding="utf-8",
    )

    seeds = load_book_seeds(p)
    assert len(seeds) == 1
    seed = seeds[0]
    assert seed.title == "REB S4"
    assert seed.source_name == "reb.rw"
    assert seed.license_notes == "verify"
    assert domain_for_seed(seed) == "reb.rw"


def test_load_book_seeds_deduplicates_urls(tmp_path):
    p = tmp_path / "books.txt"
    p.write_text(
        "\n".join(
            [
                "https://example.org/a.pdf",
                "https://example.org/a.pdf",
                "# comment",
                "",
            ]
        ),
        encoding="utf-8",
    )

    seeds = load_book_seeds(p)
    assert len(seeds) == 1
