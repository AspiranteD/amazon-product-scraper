"""
User-agent rotation manager.

Loads user agents from a JSON file or uses built-in defaults.
Tracks usage statistics for analysis.
"""
import json
import logging
import random
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
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0",
]


class UserAgentRotator:
    """
    Manages a pool of user-agent strings with random rotation.

    Can load from a JSON file (list of strings) or use built-in defaults.
    Tracks how many times each user-agent has been selected.
    """

    def __init__(self, source: Optional[str | Path] = None):
        """
        Args:
            source: Path to a JSON file containing a list of user-agent strings.
                    If None, uses built-in defaults.
        """
        self._agents: list[str] = []
        self._usage: dict[str, int] = {}

        if source:
            self._load_from_file(Path(source))
        else:
            self._agents = list(DEFAULT_USER_AGENTS)

        self._usage = {ua: 0 for ua in self._agents}
        logger.info("Loaded %d user agents", len(self._agents))

    def _load_from_file(self, path: Path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                self._agents = [str(ua) for ua in data if ua]
            else:
                logger.warning("Expected JSON list, got %s. Using defaults.", type(data).__name__)
                self._agents = list(DEFAULT_USER_AGENTS)
        except Exception as e:
            logger.warning("Failed to load user agents from %s: %s. Using defaults.", path, e)
            self._agents = list(DEFAULT_USER_AGENTS)

    def get_random(self) -> str:
        """Return a random user-agent string and track usage."""
        ua = random.choice(self._agents)
        self._usage[ua] = self._usage.get(ua, 0) + 1
        return ua

    def get_all(self) -> list[str]:
        """Return all available user-agent strings."""
        return self._agents.copy()

    def get_usage_stats(self) -> dict[str, int]:
        """Return usage count per user-agent."""
        return self._usage.copy()

    def __len__(self) -> int:
        return len(self._agents)
