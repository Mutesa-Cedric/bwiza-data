"""Robots.txt compliance checker.

Uses ``requests`` to fetch robots.txt (with the crawler's own User-Agent)
instead of ``urllib.robotparser.RobotFileParser.read()`` which uses Python's
default User-Agent.  Many sites return HTTP 403 to the default UA (Cloudflare,
bot-protection), and ``RobotFileParser.read()`` silently sets
``disallow_all = True`` for 401/403 — blocking every URL on that domain.

By fetching with ``requests`` and calling ``parser.parse()`` we:
* Use the same User-Agent as the actual crawler, so the response matches
  what the crawler would see.
* Treat fetch failures (timeout, connection error, 4xx/5xx) as "allow all",
  which is standard practice (RFC 9309 §2.4: unreachable robots.txt → allow).
"""

import threading
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import requests

from apps.common.logging import get_logger

log = get_logger(__name__)

_ROBOTS_FETCH_TIMEOUT_S = 10


class RobotsChecker:
    """Per-domain robots.txt cache and URL checker.

    Thread-safe: parser cache is protected by a lock.
    """

    def __init__(self, user_agent: str, enabled: bool = True):
        self._user_agent = user_agent
        self._enabled = enabled
        self._parsers: dict[str, RobotFileParser | None] = {}
        self._lock = threading.Lock()

    def _fetch_and_parse(self, origin: str) -> RobotFileParser | None:
        """Fetch robots.txt via requests and return a parsed RobotFileParser.

        Returns None on any failure (network, HTTP error, decode), which the
        caller treats as "allow all".
        """
        robots_url = f"{origin}/robots.txt"
        try:
            resp = requests.get(
                robots_url,
                timeout=_ROBOTS_FETCH_TIMEOUT_S,
                headers={"User-Agent": self._user_agent},
                allow_redirects=True,
            )
        except requests.RequestException:
            log.debug("Failed to fetch robots.txt for %s, allowing all", origin)
            return None

        if resp.status_code in (401, 403):
            # Server blocks our actual user-agent — respect that.
            parser = RobotFileParser()
            parser.disallow_all = True  # type: ignore[attr-defined]
            return parser

        if resp.status_code >= 400:
            # 404 or other client/server errors → allow all (RFC 9309 §2.4).
            log.debug("robots.txt %s returned %d, allowing all", origin, resp.status_code)
            return None

        # Parse the response body.
        try:
            lines = resp.text.splitlines()
        except Exception:
            log.debug("Failed to decode robots.txt for %s, allowing all", origin)
            return None

        parser = RobotFileParser()
        parser.parse(lines)
        return parser

    def _get_parser(self, url: str) -> RobotFileParser | None:
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"

        with self._lock:
            if origin in self._parsers:
                return self._parsers[origin]

        # Fetch outside the lock (I/O-bound)
        parser = self._fetch_and_parse(origin)

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
