"""Tests for file checksum."""

from apps.common.checksum import sha256_file


def test_checksum_known_content(tmp_path):
    f = tmp_path / "test.bin"
    f.write_bytes(b"hello world")
    h = sha256_file(str(f))
    assert len(h) == 64
    # Known SHA256 of "hello world"
    assert h == "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"


def test_checksum_deterministic(tmp_path):
    f = tmp_path / "test.bin"
    f.write_bytes(b"some content")
    assert sha256_file(str(f)) == sha256_file(str(f))
