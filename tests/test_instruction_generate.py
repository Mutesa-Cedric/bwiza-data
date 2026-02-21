"""Tests for instruction generation pipeline."""

import json
import tempfile
from pathlib import Path

from apps.instructions.generate import (
    DEFAULT_TOPICS,
    TEMPLATES,
    _make_id,
    generate_synthetic,
    load_gold_seeds,
)


def test_make_id_deterministic():
    id1 = _make_id("gold", "prompt", "response")
    id2 = _make_id("gold", "prompt", "response")
    assert id1 == id2
    assert len(id1) == 16


def test_make_id_different_inputs():
    id1 = _make_id("gold", "a", "b")
    id2 = _make_id("gold", "c", "d")
    assert id1 != id2


def test_load_gold_seeds():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "seeds.jsonl"
        seeds = [
            {"prompt": "Kigali ni iki?", "response": "Umurwa mukuru."},
            {"prompt": "Rwanda iri he?", "response": "Mu burasirazuba bw'Afurika."},
        ]
        p.write_text("\n".join(json.dumps(s) for s in seeds))

        examples = load_gold_seeds(str(p))
        assert len(examples) == 2
        assert examples[0].source == "gold"
        assert examples[0].task_type == "qa"
        assert examples[0].prompt == "Kigali ni iki?"
        assert examples[0].response == "Umurwa mukuru."
        assert examples[0].lang == "rw"


def test_load_gold_seeds_with_task_type():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "seeds.jsonl"
        seed = {
            "prompt": "Sobanura u Rwanda",
            "response": "Igihugu cyo mu burasirazuba bw'Afurika.",
            "task_type": "explain",
        }
        p.write_text(json.dumps(seed))

        examples = load_gold_seeds(str(p))
        assert len(examples) == 1
        assert examples[0].task_type == "explain"


def test_load_gold_seeds_skips_empty():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "seeds.jsonl"
        seeds = [
            {"prompt": "", "response": "something"},
            {"prompt": "valid", "response": ""},
            {"prompt": "ok", "response": "ok"},
        ]
        p.write_text("\n".join(json.dumps(s) for s in seeds))

        examples = load_gold_seeds(str(p))
        assert len(examples) == 1
        assert examples[0].prompt == "ok"


def test_load_gold_seeds_skips_comments():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "seeds.jsonl"
        lines = [
            "# This is a comment",
            json.dumps({"prompt": "hi", "response": "hello"}),
            "",
            json.dumps({"prompt": "bye", "response": "goodbye"}),
        ]
        p.write_text("\n".join(lines))

        examples = load_gold_seeds(str(p))
        assert len(examples) == 2


def test_load_gold_seeds_missing_file():
    examples = load_gold_seeds("/nonexistent/path/seeds.jsonl")
    assert examples == []


def test_generate_synthetic_default():
    examples = generate_synthetic()
    expected = len(TEMPLATES) * len(DEFAULT_TOPICS)
    assert len(examples) == expected
    assert all(e.source == "synthetic" for e in examples)
    assert all(e.lang == "rw" for e in examples)


def test_generate_synthetic_custom():
    topics = ["igihugu", "abantu"]
    templates = [("qa", "{topic} ni iki?", "")]
    examples = generate_synthetic(topics=topics, templates=templates)
    assert len(examples) == 2
    assert examples[0].prompt == "igihugu ni iki?"
    assert examples[1].prompt == "abantu ni iki?"
    assert examples[0].task_type == "qa"


def test_generate_synthetic_ids_unique():
    examples = generate_synthetic()
    ids = [e.id for e in examples]
    assert len(ids) == len(set(ids))


def test_generate_synthetic_task_types():
    examples = generate_synthetic()
    task_types = {e.task_type for e in examples}
    assert "summarize" in task_types
    assert "explain" in task_types
    assert "qa" in task_types
