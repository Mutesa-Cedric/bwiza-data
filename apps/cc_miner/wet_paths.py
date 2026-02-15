"""WET file URL list loader."""

from pathlib import Path

from apps.common.config_types import AppConfig


def get_wet_urls(cfg: AppConfig) -> list[str]:
    """Load WET URLs from the configured paths file."""
    path = Path(cfg.cc.wet_paths_file)
    if not path.exists():
        raise FileNotFoundError(f"WET paths file not found: {path}")

    urls = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            urls.append(line)

    limit = cfg.cc.max_wet_files
    if limit > 0:
        urls = urls[:limit]

    return urls
