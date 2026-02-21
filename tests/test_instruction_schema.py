"""Tests for InstructionExample schema."""

import json

from apps.common.instruction_schema import (
    INSTRUCTION_REJECT_REASONS,
    TASK_TYPES,
    InstructionExample,
)


def _sample_example():
    return InstructionExample(
        id="instr_001",
        source="gold",
        task_type="qa",
        prompt="Kigali ni iki?",
        response="Kigali ni umurwa mukuru w'u Rwanda.",
        lang="rw",
        created_at="2026-02-21T12:00:00Z",
        meta={"origin": "manual"},
    )


def test_to_json():
    ex = _sample_example()
    d = ex.to_json()
    assert d["id"] == "instr_001"
    assert d["source"] == "gold"
    assert d["task_type"] == "qa"
    assert d["prompt"] == "Kigali ni iki?"
    assert d["response"] == "Kigali ni umurwa mukuru w'u Rwanda."
    assert d["lang"] == "rw"
    assert d["meta"]["origin"] == "manual"


def test_from_json():
    ex = _sample_example()
    d = ex.to_json()
    restored = InstructionExample.from_json(d)
    assert restored.id == ex.id
    assert restored.prompt == ex.prompt
    assert restored.response == ex.response
    assert restored.task_type == ex.task_type


def test_json_serializable():
    ex = _sample_example()
    serialized = json.dumps(ex.to_json())
    assert isinstance(serialized, str)
    loaded = json.loads(serialized)
    assert loaded["id"] == "instr_001"


def test_from_json_ignores_extra_fields():
    d = _sample_example().to_json()
    d["extra_field"] = "should_be_ignored"
    restored = InstructionExample.from_json(d)
    assert restored.id == "instr_001"


def test_reject_reasons_are_stable():
    assert "reject.too_short" in INSTRUCTION_REJECT_REASONS
    assert "reject.too_long" in INSTRUCTION_REJECT_REASONS
    assert "reject.not_rw" in INSTRUCTION_REJECT_REASONS
    assert "reject.duplicate" in INSTRUCTION_REJECT_REASONS
    assert "reject.low_quality" in INSTRUCTION_REJECT_REASONS


def test_task_types_are_stable():
    assert "qa" in TASK_TYPES
    assert "summarize" in TASK_TYPES
    assert "translate" in TASK_TYPES
    assert "safety" in TASK_TYPES


def test_default_values():
    ex = InstructionExample(
        id="x",
        source="gold",
        task_type="qa",
        prompt="a",
        response="b",
    )
    assert ex.lang == "rw"
    assert ex.created_at == ""
    assert ex.meta == {}
