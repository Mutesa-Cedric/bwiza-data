"""Schema for instruction-tuning examples (Kinyarwanda)."""

from dataclasses import dataclass, field

# Stable reject reason codes for instruction examples
INSTRUCTION_REJECT_REASONS = {
    "reject.too_short",
    "reject.too_long",
    "reject.not_rw",
    "reject.low_quality",
    "reject.duplicate",
    "reject.empty_prompt",
    "reject.empty_response",
}

# Known task types for balanced dataset construction
TASK_TYPES = {
    "summarize",
    "rewrite",
    "qa",
    "translate",
    "explain",
    "safety",
    "classify",
    "generate",
    "conversation",
}


@dataclass
class InstructionExample:
    """A single instruction-tuning example."""

    id: str
    source: str  # "gold" | "synthetic" | "translated"
    task_type: str  # one of TASK_TYPES
    prompt: str
    response: str
    lang: str = "rw"
    created_at: str = ""
    meta: dict = field(default_factory=dict)

    def to_json(self) -> dict:
        return {
            "id": self.id,
            "source": self.source,
            "task_type": self.task_type,
            "prompt": self.prompt,
            "response": self.response,
            "lang": self.lang,
            "created_at": self.created_at,
            "meta": self.meta,
        }

    @classmethod
    def from_json(cls, data: dict) -> "InstructionExample":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
