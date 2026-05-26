"""
User agent rotation manager.

Provides random user agent selection with:
- Default user agents (6 real Chrome/Firefox/Safari strings)
- External loading from file or any data source
- Usage tracking per user agent (count + last used timestamp)
- Fallback to defaults if external source fails
- Hot-reload capability without restart

In production, user agents are stored in a database with is_active flags.
This standalone version loads from a JSON file or uses built-in defaults.
"""
import json
import logging
import random
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
]


@dataclass
class UserAgentStats:
    """Tracks usage of a single user agent string."""
    user_agent: str
    usage_count: int = 0
    last_used_at: Optional[datetime] = None
    is_active: bool = True


class UserAgentManager:
    """
    Manages user agent rotation with usage tracking.

    Loads user agents from a JSON file or uses built-in defaults.
    Tracks how many times each UA has been selected and when.
    """

    def __init__(self, source_path: str | Path | None = None):
        self._stats: dict[str, UserAgentStats] = {}
        self._agents: list[str] = []
        self._source_path = Path(source_path) if source_path else None
        self._load(self._source_path)

    def _load(self, path: Optional[Path] = None):
        """Load user agents from file or use defaults."""
        agents: list[str] = []

        if path and path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    agents = [str(ua) for ua in data if ua]
                elif isinstance(data, dict) and "user_agents" in data:
                    agents = [str(ua) for ua in data["user_agents"] if ua]
                logger.info("Loaded %d user agents from %s", len(agents), path)
            except Exception as e:
                logger.error("Failed to load user agents from %s: %s", path, e)

        if not agents:
            agents = DEFAULT_USER_AGENTS.copy()
            logger.info("Using %d default user agents", len(agents))

        self._agents = agents
        for ua in agents:
            if ua not in self._stats:
                self._stats[ua] = UserAgentStats(user_agent=ua)

    def get_random(self, track_usage: bool = True) -> str:
        """
        Return a random user agent string.

        Args:
            track_usage: If True, increment usage counter and update timestamp.
        """
        if not self._agents:
            return DEFAULT_USER_AGENTS[0]

        selected = random.choice(self._agents)

        if track_usage:
            stats = self._stats.get(selected)
            if stats:
                stats.usage_count += 1
                stats.last_used_at = datetime.now()

        return selected

    def get_all(self) -> list[str]:
        """Return a copy of all active user agent strings."""
        return self._agents.copy()

    def get_stats(self) -> list[UserAgentStats]:
        """Return usage stats for all user agents."""
        return list(self._stats.values())

    def reload(self):
        """
        Reload user agents from the original source.

        Preserves existing usage stats for agents that remain after reload.
        """
        logger.info("Reloading user agents...")
        self._load(self._source_path)

    @property
    def count(self) -> int:
        return len(self._agents)
