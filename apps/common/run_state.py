"""RunState schema for durable run checkpointing and resumability."""

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

# Valid pipeline names
PIPELINES = {
    "cc_miner",
    "targeted_crawler",
    "parallel",
    "instructions",
    "cc_index",
    "wayback",
    "cc_lang",
    "books_corpus",
    "heritage",
}

# Valid run statuses
STATUSES = {"created", "running", "paused", "completed", "failed"}


@dataclass
class RunState:
    """Durable checkpoint representing run progress."""

    # Identity
    run_id: str = ""
    pipeline: str = ""  # one of PIPELINES
    source: str = ""  # "commoncrawl" | "targeted_web" | ...

    # Config
    config_fingerprint: str = ""
    git_commit: str = ""

    # Lifecycle
    status: str = "created"  # one of STATUSES
    started_at: str = ""
    updated_at: str = ""
    ended_at: str = ""
    failure_reason: str = ""

    # Progress
    items_total: int = 0
    items_done: int = 0
    items_failed: int = 0
    items_skipped: int = 0
    current_item: str = ""

    # Artifacts
    shards_closed: int = 0
    bytes_written: int = 0
    uploaded_shards: int = 0
    last_shard_name: str = ""

    # Notes
    meta: dict = field(default_factory=dict)

    def touch(self) -> None:
        """Update the updated_at timestamp."""
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def start(self) -> None:
        """Transition to running."""
        now = datetime.now(timezone.utc).isoformat()
        self.status = "running"
        self.started_at = self.started_at or now
        self.updated_at = now

    def pause(self, reason: str = "") -> None:
        """Transition to paused."""
        self.status = "paused"
        if reason:
            self.failure_reason = reason
        self.touch()

    def complete(self) -> None:
        """Transition to completed."""
        now = datetime.now(timezone.utc).isoformat()
        self.status = "completed"
        self.ended_at = now
        self.updated_at = now

    def fail(self, reason: str) -> None:
        """Transition to failed."""
        now = datetime.now(timezone.utc).isoformat()
        self.status = "failed"
        self.failure_reason = reason
        self.ended_at = now
        self.updated_at = now

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: dict) -> "RunState":
        known = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)  # type: ignore[arg-type]

    @classmethod
    def from_json(cls, text: str) -> "RunState":
        return cls.from_dict(json.loads(text))
