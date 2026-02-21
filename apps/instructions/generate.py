"""Instruction generation pipeline (gold seeds + synthetic templates)."""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from apps.common.instruction_schema import InstructionExample
from apps.common.logging import get_logger

log = get_logger(__name__)

# Synthetic templates: (task_type, prompt_template, response_template)
# {topic} is replaced with a topic string from the topic list.
TEMPLATES = [
    (
        "summarize",
        "Sobanura mu magambo make: {topic}",
        "",
    ),
    (
        "explain",
        "Sobanura {topic} mu Kinyarwanda.",
        "",
    ),
    (
        "translate",
        "Hindura mu Kinyarwanda: {topic}",
        "",
    ),
    (
        "qa",
        "{topic} ni iki?",
        "",
    ),
    (
        "rewrite",
        "Andika {topic} mu buryo bworoshye.",
        "",
    ),
]

# Default topics for synthetic generation
DEFAULT_TOPICS = [
    "u Rwanda",
    "umurwa mukuru Kigali",
    "amateka y'u Rwanda",
    "ubuhinzi mu Rwanda",
    "ubuvuzi mu Rwanda",
    "uburezi mu Rwanda",
    "imikino y'umupira w'amaguru",
    "ikirere cy'u Rwanda",
    "inyamaswa zo mu Rwanda",
    "amategeko y'u Rwanda",
    "ubucuruzi mu Rwanda",
    "ikoranabuhanga mu Rwanda",
    "umuco nyarwanda",
    "indimi zo mu Rwanda",
    "ubumwe bw'abanyarwanda",
    "iterambere ry'u Rwanda",
    "ubukungu bw'u Rwanda",
    "ingabo z'u Rwanda",
    "urugendo mu Rwanda",
    "ibidukikije mu Rwanda",
]


def _make_id(source: str, prompt: str, response: str) -> str:
    """Create a stable ID from source + prompt + response."""
    content = f"{source}||{prompt}||{response}"
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def load_gold_seeds(seed_file: str) -> list[InstructionExample]:
    """Load gold instruction examples from a JSONL file.

    Each line should be a JSON object with at minimum:
    - prompt: str
    - response: str
    Optionally: task_type, meta
    """
    path = Path(seed_file)
    if not path.exists():
        log.warning("Seed file not found: %s", seed_file)
        return []

    examples = []
    now = datetime.now(timezone.utc).isoformat()

    for i, line in enumerate(path.read_text().splitlines()):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            log.warning("Skipping invalid JSON at line %d in %s", i + 1, seed_file)
            continue

        prompt = data.get("prompt", "").strip()
        response = data.get("response", "").strip()
        if not prompt or not response:
            continue

        task_type = data.get("task_type", "qa")
        ex = InstructionExample(
            id=_make_id("gold", prompt, response),
            source="gold",
            task_type=task_type,
            prompt=prompt,
            response=response,
            lang="rw",
            created_at=now,
            meta=data.get("meta", {}),
        )
        examples.append(ex)

    log.info("Loaded %d gold seed examples from %s", len(examples), seed_file)
    return examples


def generate_synthetic(
    topics: list[str] | None = None,
    templates: list[tuple[str, str, str]] | None = None,
) -> list[InstructionExample]:
    """Generate synthetic prompt-only examples from templates x topics.

    These are prompt skeletons; responses are empty (to be filled
    by a model or human later). They are still useful as dataset
    scaffolding for task-type balance.
    """
    topics = topics or DEFAULT_TOPICS
    templates = templates or TEMPLATES
    now = datetime.now(timezone.utc).isoformat()

    examples = []
    for task_type, prompt_tpl, response_tpl in templates:
        for topic in topics:
            prompt = prompt_tpl.format(topic=topic)
            response = response_tpl.format(topic=topic) if response_tpl else ""

            ex = InstructionExample(
                id=_make_id("synthetic", prompt, response),
                source="synthetic",
                task_type=task_type,
                prompt=prompt,
                response=response,
                lang="rw",
                created_at=now,
                meta={"template": prompt_tpl, "topic": topic},
            )
            examples.append(ex)

    log.info(
        "Generated %d synthetic examples (%d templates x %d topics)",
        len(examples),
        len(templates),
        len(topics),
    )
    return examples
