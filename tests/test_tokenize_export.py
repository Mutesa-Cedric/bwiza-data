"""Tests for pre-tokenized packed-sequence Parquet export."""

import json

import pyarrow.parquet as pq
import zstandard as zstd

from apps.packaging.tokenize_export import _pack_sequences


class MockTokenizer:
    """Simple tokenizer that maps each character to its ordinal."""

    vocab_size = 256
    eos_token_id = 0

    def encode(self, text: str) -> list[int]:
        return [ord(c) for c in text]


EOS = MockTokenizer.eos_token_id


def _make_doc(text: str, doc_id: str = "d1") -> dict:
    return {"id": doc_id, "text": text}


def _make_shard(tmp_path, name: str, docs: list[dict]) -> None:
    """Write a zstd-compressed JSONL shard."""
    shard_path = tmp_path / name
    cctx = zstd.ZstdCompressor()
    lines = "\n".join(json.dumps(d, ensure_ascii=False) for d in docs) + "\n"
    with open(shard_path, "wb") as f:
        f.write(cctx.compress(lines.encode("utf-8")))


# --- _pack_sequences ---


def test_pack_basic():
    """Pack two short docs into one sequence."""
    docs = [_make_doc("ab"), _make_doc("cd")]
    seqs = list(_pack_sequences(docs, MockTokenizer(), EOS, max_length=20))
    assert len(seqs) == 1
    # "ab" + EOS + "cd" = [97,98,0,99,100]
    assert seqs[0] == [97, 98, EOS, 99, 100]


def test_pack_exact_max_length():
    """When buffer is exactly max_length, yield one full sequence."""
    # 5 chars => 5 tokens, max_length=5 => exactly 1 sequence
    docs = [_make_doc("abcde")]
    seqs = list(_pack_sequences(docs, MockTokenizer(), EOS, max_length=5))
    assert len(seqs) == 1
    assert len(seqs[0]) == 5


def test_pack_splits_long_doc():
    """A single long doc should be split into multiple sequences."""
    text = "a" * 10  # 10 tokens
    docs = [_make_doc(text)]
    seqs = list(_pack_sequences(docs, MockTokenizer(), EOS, max_length=4))
    # 10 tokens -> [4, 4, 2]
    assert len(seqs) == 3
    assert len(seqs[0]) == 4
    assert len(seqs[1]) == 4
    assert len(seqs[2]) == 2


def test_pack_no_padding():
    """Last sequence should not be padded."""
    docs = [_make_doc("abc")]  # 3 tokens
    seqs = list(_pack_sequences(docs, MockTokenizer(), EOS, max_length=10))
    assert len(seqs) == 1
    assert len(seqs[0]) == 3


def test_pack_eos_between_docs():
    """EOS token should separate documents."""
    docs = [_make_doc("a"), _make_doc("b"), _make_doc("c")]
    seqs = list(_pack_sequences(docs, MockTokenizer(), EOS, max_length=100))
    assert len(seqs) == 1
    # "a" + EOS + "b" + EOS + "c"
    expected = [ord("a"), EOS, ord("b"), EOS, ord("c")]
    assert seqs[0] == expected


def test_pack_empty_docs_skipped():
    """Documents with no text content should be skipped."""
    docs = [_make_doc(""), _make_doc("ab"), {"id": "x"}]
    seqs = list(_pack_sequences(docs, MockTokenizer(), EOS, max_length=100))
    assert len(seqs) == 1
    assert seqs[0] == [97, 98]


def test_pack_empty_input():
    """No docs -> no sequences."""
    seqs = list(_pack_sequences([], MockTokenizer(), EOS, max_length=10))
    assert seqs == []


def test_pack_multiple_full_sequences():
    """Multiple docs that fill multiple sequences."""
    # 3 docs of 3 chars each, with EOS between = 3 + 1 + 3 + 1 + 3 = 11 tokens
    docs = [_make_doc("abc"), _make_doc("def"), _make_doc("ghi")]
    seqs = list(_pack_sequences(docs, MockTokenizer(), EOS, max_length=5))
    # Total tokens in buffer: [97,98,99, 0, 100,101,102, 0, 103,104,105]
    # seq1: [97,98,99,0,100] (5), seq2: [101,102,0,103,104] (5), seq3: [105] (1)
    assert len(seqs) == 3
    assert len(seqs[0]) == 5
    assert len(seqs[1]) == 5
    assert len(seqs[2]) == 1


# --- export_split_to_parquet (integration with mock tokenizer) ---


def test_export_split_to_parquet(tmp_path, monkeypatch):
    """End-to-end export with mock tokenizer."""
    # Create shard
    docs = [_make_doc(f"text number {i}", doc_id=f"doc-{i}") for i in range(5)]
    _make_shard(tmp_path, "shard_001.jsonl.zst", docs)

    # Create split file referencing the shard
    split_file = tmp_path / "train.txt"
    split_file.write_text("prefix/shard_001.jsonl.zst\n")

    output_path = tmp_path / "train.parquet"

    # Mock the tokenizer loading and imports
    mock_tok = MockTokenizer()

    def mock_from_pretrained(*args, **kwargs):
        return mock_tok

    monkeypatch.setattr(
        "transformers.AutoTokenizer.from_pretrained",
        mock_from_pretrained,
        raising=False,
    )

    # We need to mock the import inside the function
    import sys
    import types

    mock_transformers = types.ModuleType("transformers")
    mock_auto_tok = type(
        "AutoTokenizer", (), {"from_pretrained": staticmethod(mock_from_pretrained)}
    )
    mock_transformers.AutoTokenizer = mock_auto_tok  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "transformers", mock_transformers)

    from apps.packaging.tokenize_export import export_split_to_parquet

    stats = export_split_to_parquet(
        split_file=str(split_file),
        shard_dir=str(tmp_path),
        output_path=str(output_path),
        tokenizer_name="mock",
        max_length=50,
    )

    assert output_path.exists()
    assert stats["sequences"] > 0
    assert stats["total_tokens"] > 0
    assert stats["shards_processed"] == 1
    assert stats["shards_skipped"] == 0

    # Read back and verify schema
    table = pq.read_table(str(output_path))
    assert "input_ids" in table.column_names
    assert "length" in table.column_names

    # Verify lengths match actual input_ids lengths
    for i in range(len(table)):
        ids = table.column("input_ids")[i].as_py()
        length = table.column("length")[i].as_py()
        assert length == len(ids)
        assert length <= 50


def test_export_split_missing_shard(tmp_path, monkeypatch):
    """Shards not found locally should be skipped."""
    split_file = tmp_path / "train.txt"
    split_file.write_text("prefix/nonexistent.jsonl.zst\n")

    output_path = tmp_path / "train.parquet"

    mock_tok = MockTokenizer()

    import sys
    import types

    mock_transformers = types.ModuleType("transformers")
    mock_auto_tok = type(
        "AutoTokenizer",
        (),
        {"from_pretrained": staticmethod(lambda *a, **k: mock_tok)},
    )
    mock_transformers.AutoTokenizer = mock_auto_tok  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "transformers", mock_transformers)

    from apps.packaging.tokenize_export import export_split_to_parquet

    stats = export_split_to_parquet(
        split_file=str(split_file),
        shard_dir=str(tmp_path),
        output_path=str(output_path),
        tokenizer_name="mock",
        max_length=50,
    )

    assert stats["shards_skipped"] == 1
    assert stats["sequences"] == 0


def test_export_all_splits(tmp_path, monkeypatch):
    """All three split files should produce parquet outputs."""
    # Create shard
    docs = [_make_doc(f"doc text {i}", doc_id=f"d-{i}") for i in range(3)]
    _make_shard(tmp_path, "shard_001.jsonl.zst", docs)

    # Create split files
    splits_dir = tmp_path / "splits"
    splits_dir.mkdir()
    for name in ("train", "val", "test"):
        (splits_dir / f"{name}.txt").write_text("prefix/shard_001.jsonl.zst\n")

    output_dir = tmp_path / "parquet"

    mock_tok = MockTokenizer()

    import sys
    import types

    mock_transformers = types.ModuleType("transformers")
    mock_auto_tok = type(
        "AutoTokenizer",
        (),
        {"from_pretrained": staticmethod(lambda *a, **k: mock_tok)},
    )
    mock_transformers.AutoTokenizer = mock_auto_tok  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "transformers", mock_transformers)

    from apps.packaging.tokenize_export import export_all_splits

    results = export_all_splits(
        splits_dir=str(splits_dir),
        shard_dir=str(tmp_path),
        output_dir=str(output_dir),
        tokenizer_name="mock",
        max_length=50,
    )

    assert "train" in results
    assert "val" in results
    assert "test" in results

    for name in ("train", "val", "test"):
        assert (output_dir / f"{name}.parquet").exists()
        assert results[name]["sequences"] > 0

    assert (output_dir / "export_summary.json").exists()
