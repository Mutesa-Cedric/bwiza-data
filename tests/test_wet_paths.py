"""Tests for WET URL list loader."""

from apps.cc_miner.wet_paths import get_wet_urls
from apps.common.config_types import AppConfig


def _cfg_with_file(path: str, max_wet: int = 0) -> AppConfig:
    cfg = AppConfig()
    cfg.cc.wet_paths_file = path
    cfg.cc.max_wet_files = max_wet
    return cfg


def test_loads_urls(tmp_path):
    f = tmp_path / "urls.txt"
    f.write_text("https://a.com/wet1.gz\nhttps://b.com/wet2.gz\n")
    urls = get_wet_urls(_cfg_with_file(str(f)))
    assert urls == ["https://a.com/wet1.gz", "https://b.com/wet2.gz"]


def test_skips_comments_and_blanks(tmp_path):
    f = tmp_path / "urls.txt"
    f.write_text("# comment\n\nhttps://a.com/wet.gz\n\n# another\n")
    urls = get_wet_urls(_cfg_with_file(str(f)))
    assert urls == ["https://a.com/wet.gz"]


def test_respects_max_wet_files(tmp_path):
    f = tmp_path / "urls.txt"
    f.write_text("\n".join(f"https://a.com/{i}.gz" for i in range(20)))
    urls = get_wet_urls(_cfg_with_file(str(f), max_wet=5))
    assert len(urls) == 5


def test_empty_file(tmp_path):
    f = tmp_path / "urls.txt"
    f.write_text("")
    urls = get_wet_urls(_cfg_with_file(str(f)))
    assert urls == []


def test_missing_file_raises():
    import pytest

    with pytest.raises(FileNotFoundError):
        get_wet_urls(_cfg_with_file("/nonexistent/file.txt"))
