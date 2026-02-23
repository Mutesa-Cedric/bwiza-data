"""Robots.txt compliance checker."""

import threading
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

from apps.common.logging import get_logger

log = get_logger(__name__)


class RobotsChecker:
    """Per-domain robots.txt cache and URL checker.

    Thread-safe: parser cache is protected by a lock.
    """

    def __init__(self, user_agent: str, enabled: bool = True):
        self._user_agent = user_agent
        self._enabled = enabled
        self._parsers: dict[str, RobotFileParser | None] = {}
        self._lock = threading.Lock()

    def _get_parser(self, url: str) -> RobotFileParser | None:
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"

        with self._lock:
            if origin in self._parsers:
                return self._parsers[origin]

        # Fetch outside the lock (I/O-bound)
        robots_url = f"{origin}/robots.txt"
        parser = RobotFileParser()
        parser.set_url(robots_url)
        try:
            parser.read()
        except Exception:
            log.debug("Failed to fetch robots.txt for %s, allowing all", origin)
            parser = None  # type: ignore[assignment]

        with self._lock:
            # Another thread may have cached it while we fetched
            if origin not in self._parsers:
                self._parsers[origin] = parser
            return self._parsers[origin]

    def is_allowed(self, url: str) -> bool:
        """Check if the URL is allowed by robots.txt."""
        if not self._enabled:
            return True

        parser = self._get_parser(url)
        if parser is None:
            return True

        return parser.can_fetch(self._user_agent, url)
