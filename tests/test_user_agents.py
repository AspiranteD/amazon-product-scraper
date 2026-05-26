"""Tests for the user-agent rotator."""
import json
import tempfile

from src.scraper.user_agents import UserAgentRotator, DEFAULT_USER_AGENTS


class TestUserAgentRotator:

    def test_default_agents_loaded(self):
        rotator = UserAgentRotator()
        assert len(rotator) == len(DEFAULT_USER_AGENTS)

    def test_get_random_returns_string(self):
        rotator = UserAgentRotator()
        ua = rotator.get_random()
        assert isinstance(ua, str)
        assert "Mozilla" in ua

    def test_usage_tracking(self):
        rotator = UserAgentRotator()
        for _ in range(10):
            rotator.get_random()
        stats = rotator.get_usage_stats()
        assert sum(stats.values()) == 10

    def test_load_from_json_file(self):
        agents = ["CustomAgent/1.0", "CustomAgent/2.0"]
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        json.dump(agents, tmp)
        tmp.close()

        rotator = UserAgentRotator(source=tmp.name)
        assert len(rotator) == 2
        assert rotator.get_random() in agents

    def test_fallback_on_invalid_file(self):
        rotator = UserAgentRotator(source="/nonexistent/path.json")
        assert len(rotator) == len(DEFAULT_USER_AGENTS)

    def test_get_all_returns_copy(self):
        rotator = UserAgentRotator()
        agents = rotator.get_all()
        agents.clear()
        assert len(rotator) > 0
