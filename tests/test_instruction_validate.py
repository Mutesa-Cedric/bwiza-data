"""Tests for instruction validation."""

from unittest.mock import patch

from apps.common.config_types import InstructionsConfig
from apps.common.instruction_schema import InstructionExample
from apps.instructions.validate import (
    _has_excessive_repeats,
    validate_instruction,
    validate_instruction_with_lid,
)


def _cfg(**overrides):
    return InstructionsConfig(**overrides)


def _ex(**overrides: object) -> InstructionExample:
    ex = InstructionExample(
        id="test_001",
        source="gold",
        task_type="qa",
        prompt="Kigali ni iki?",
        response="Kigali ni umurwa mukuru w'u Rwanda.",
    )
    for k, v in overrides.items():
        setattr(ex, k, v)
    return ex


def test_valid_example():
    ok, reason = validate_instruction(_ex(), _cfg())
    assert ok is True
    assert reason == ""


def test_empty_prompt():
    ok, reason = validate_instruction(_ex(prompt=""), _cfg())
    assert ok is False
    assert reason == "reject.empty_prompt"


def test_whitespace_prompt():
    ok, reason = validate_instruction(_ex(prompt="   "), _cfg())
    assert ok is False
    assert reason == "reject.empty_prompt"


def test_empty_response():
    ok, reason = validate_instruction(_ex(response=""), _cfg())
    assert ok is False
    assert reason == "reject.empty_response"


def test_prompt_too_short():
    ok, reason = validate_instruction(
        _ex(prompt="ab"),
        _cfg(min_chars_prompt=5),
    )
    assert ok is False
    assert reason == "reject.too_short"


def test_response_too_short():
    ok, reason = validate_instruction(
        _ex(response="short"),
        _cfg(min_chars_response=10),
    )
    assert ok is False
    assert reason == "reject.too_short"


def test_prompt_too_long():
    ok, reason = validate_instruction(
        _ex(prompt="x" * 5000),
        _cfg(max_chars_prompt=100),
    )
    assert ok is False
    assert reason == "reject.too_long"


def test_response_too_long():
    ok, reason = validate_instruction(
        _ex(response="x" * 10000),
        _cfg(max_chars_response=100),
    )
    assert ok is False
    assert reason == "reject.too_long"


def test_repeated_lines_rejected():
    junk = "\n".join(["This is repeated junk text."] * 20)
    ok, reason = validate_instruction(_ex(response=junk), _cfg())
    assert ok is False
    assert reason == "reject.low_quality"


def test_has_excessive_repeats_few_lines():
    assert _has_excessive_repeats("short\ntext") is False


def test_has_excessive_repeats_unique_lines():
    text = "\n".join([f"Unique line number {i}" for i in range(10)])
    assert _has_excessive_repeats(text) is False


def test_has_excessive_repeats_spam():
    text = "\n".join(["Spam line repeated"] * 10)
    assert _has_excessive_repeats(text) is True


def test_lid_accepts_rw():
    with patch(
        "apps.common.lid.predict_lang",
        return_value=("kin_Latn", 0.92, "glotlid"),
    ):
        ok, reason = validate_instruction_with_lid(_ex(), _cfg())
        assert ok is True
        assert reason == ""


def test_lid_rejects_english():
    with patch(
        "apps.common.lid.predict_lang",
        return_value=("eng_Latn", 0.95, "glotlid"),
    ):
        ok, reason = validate_instruction_with_lid(_ex(), _cfg())
        assert ok is False
        assert reason == "reject.not_rw"


def test_lid_rejects_other_lang():
    with patch(
        "apps.common.lid.predict_lang",
        return_value=("fra_Latn", 0.90, "glotlid"),
    ):
        ok, reason = validate_instruction_with_lid(_ex(), _cfg())
        assert ok is False
        assert reason == "reject.not_rw"


def test_lid_skips_when_basic_fails():
    """LID check should not run if basic validation fails."""
    with patch("apps.common.lid.predict_lang") as mock_lid:
        ok, reason = validate_instruction_with_lid(_ex(prompt=""), _cfg())
        assert ok is False
        assert reason == "reject.empty_prompt"
        mock_lid.assert_not_called()
