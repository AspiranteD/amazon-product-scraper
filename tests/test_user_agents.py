"""Tests for UserAgentManager."""
import json
import pytest
from pathlib import Path
from src.scraper.user_agents import UserAgentManager, DEFAULT_USER_AGENTS


class TestDefaults:
    def test_uses_defaults_when_no_file(self):
        manager = UserAgentManager()
        assert manager.count == len(DEFAULT_USER_AGENTS)
        assert set(manager.get_all()) == set(DEFAULT_USER_AGENTS)

    def test_uses_defaults_when_file_missing(self, tmp_path):
        manager = UserAgentManager(source_path=tmp_path / "nonexistent.json")
        assert manager.count == len(DEFAULT_USER_AGENTS)


class TestFileLoading:
    def test_loads_from_list_format(self, tmp_path):
        agents = ["Agent/1.0", "Agent/2.0", "Agent/3.0"]
        path = tmp_path / "agents.json"
        path.write_text(json.dumps(agents))

        manager = UserAgentManager(source_path=path)
        assert manager.count == 3
        assert manager.get_all() == agents

    def test_loads_from_dict_format(self, tmp_path):
        data = {"user_agents": ["DictAgent/1.0", "DictAgent/2.0"]}
        path = tmp_path / "agents.json"
        path.write_text(json.dumps(data))

        manager = UserAgentManager(source_path=path)
        assert manager.count == 2

    def test_invalid_json_falls_back_to_defaults(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text("not json {{{")

        manager = UserAgentManager(source_path=path)
        assert manager.count == len(DEFAULT_USER_AGENTS)

    def test_empty_list_falls_back_to_defaults(self, tmp_path):
        path = tmp_path / "empty.json"
        path.write_text("[]")

        manager = UserAgentManager(source_path=path)
        assert manager.count == len(DEFAULT_USER_AGENTS)

    def test_filters_empty_strings(self, tmp_path):
        agents = ["Agent/1.0", "", None, "Agent/2.0"]
        path = tmp_path / "agents.json"
        path.write_text(json.dumps(agents))

        manager = UserAgentManager(source_path=path)
        assert manager.count == 2


class TestRandomSelection:
    def test_returns_string(self):
        manager = UserAgentManager()
        ua = manager.get_random()
        assert isinstance(ua, str)
        assert len(ua) > 0

    def test_tracks_usage(self):
        manager = UserAgentManager()
        ua = manager.get_random(track_usage=True)
        stats = {s.user_agent: s for s in manager.get_stats()}
        assert stats[ua].usage_count >= 1
        assert stats[ua].last_used_at is not None

    def test_no_tracking_when_disabled(self):
        manager = UserAgentManager()
        manager.get_random(track_usage=False)
        total_usage = sum(s.usage_count for s in manager.get_stats())
        assert total_usage == 0

    def test_multiple_calls_distribute(self):
        manager = UserAgentManager()
        for _ in range(100):
            manager.get_random()
        used = [s for s in manager.get_stats() if s.usage_count > 0]
        assert len(used) >= 2


class TestReload:
    def test_reload_preserves_stats(self, tmp_path):
        agents = ["Agent/1.0", "Agent/2.0"]
        path = tmp_path / "agents.json"
        path.write_text(json.dumps(agents))

        manager = UserAgentManager(source_path=path)

        for _ in range(5):
            manager.get_random()
        stats_before = {s.user_agent: s.usage_count for s in manager.get_stats()}

        manager.reload()
        stats_after = {s.user_agent: s.usage_count for s in manager.get_stats()}

        for ua in agents:
            assert stats_after[ua] == stats_before[ua]

    def test_reload_picks_up_new_agents(self, tmp_path):
        path = tmp_path / "agents.json"
        path.write_text(json.dumps(["Agent/1.0"]))

        manager = UserAgentManager(source_path=path)
        assert manager.count == 1

        path.write_text(json.dumps(["Agent/1.0", "Agent/2.0", "Agent/3.0"]))
        manager.reload()
        assert manager.count == 3
