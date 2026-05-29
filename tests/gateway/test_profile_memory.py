"""Tests for profile-scoped memory directories."""

import pytest
from pathlib import Path


class TestProfileScopedMemory:
    def test_default_memory_dir(self):
        from tools.memory_tool import get_memory_dir
        d = get_memory_dir()
        assert d.parts[-1] == "memories"
        assert "profiles" not in d.parts

    def test_named_profile_memory_dir(self):
        from tools.memory_tool import get_memory_dir
        d = get_memory_dir("trader")
        assert d.parts[-1] == "memories"
        assert "profiles" in d.parts
        assert "trader" in d.parts

    def test_different_profiles_isolated(self):
        from tools.memory_tool import get_memory_dir
        d1 = get_memory_dir("bot-a")
        d2 = get_memory_dir("bot-b")
        assert d1 != d2
        assert "bot-a" in d1.parts
        assert "bot-b" in d2.parts

    def test_main_profile_same_as_no_arg(self):
        from tools.memory_tool import get_memory_dir
        assert get_memory_dir() == get_memory_dir("main")

    def test_soul_path_default(self):
        from tools.memory_tool import get_soul_path
        p = get_soul_path()
        assert p.name == "SOUL.md"
        assert "profiles" not in p.parts

    def test_soul_path_profile(self):
        from tools.memory_tool import get_soul_path
        p = get_soul_path("trader")
        assert p.name == "SOUL.md"
        assert "profiles" in p.parts
        assert "trader" in p.parts

    def test_soul_main_same_as_no_arg(self):
        from tools.memory_tool import get_soul_path
        assert get_soul_path() == get_soul_path("main")


class TestProfileScopedSoul:
    def test_load_soul_default_param(self):
        from agent.prompt_builder import load_soul_md
        # Should accept no args (backward compat)
        result = load_soul_md()
        # May return None or content depending on env
        assert result is None or isinstance(result, str)

    def test_load_soul_profile_param(self):
        from agent.prompt_builder import load_soul_md
        # Should accept profile_name param; falls back to global SOUL.md
        result = load_soul_md("nonexistent-profile")
        # Global SOUL.md exists, so it falls back to that
        assert result is None or isinstance(result, str)
