import stat
from pathlib import Path
from unittest.mock import patch

import pytest
from claude_agent_sdk._errors import CLINotFoundError

from server.services.claude_mcp_service import _is_cli_not_found_error
from server.utils.general import _is_executable_file, find_claude_cli_path


@pytest.fixture
def fake_home(tmp_path):
    return tmp_path / "home"


def _make_executable(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _only_under(base: Path):
    """Return a patched _is_executable_file that only accepts paths under base."""
    real_check = _is_executable_file

    def _check(p: Path) -> bool:
        try:
            p.resolve().relative_to(base.resolve())
        except ValueError:
            return False
        return real_check(p)

    return _check


class TestEnvVarOverride:
    def test_byaan_env_var_returns_path(self, fake_home, monkeypatch):
        cli = fake_home / "custom" / "claude"
        _make_executable(cli)
        monkeypatch.setenv("BYAAN_CLAUDE_CLI_PATH", str(cli))
        monkeypatch.delenv("CLAUDE_CLI_PATH", raising=False)

        result = find_claude_cli_path(search_path="/nonexistent", home_dir=fake_home)
        assert result == str(cli)

    def test_claude_cli_path_env_var_returns_path(self, fake_home, monkeypatch):
        cli = fake_home / "other" / "claude"
        _make_executable(cli)
        monkeypatch.delenv("BYAAN_CLAUDE_CLI_PATH", raising=False)
        monkeypatch.setenv("CLAUDE_CLI_PATH", str(cli))

        result = find_claude_cli_path(search_path="/nonexistent", home_dir=fake_home)
        assert result == str(cli)

    def test_env_var_ignored_when_not_executable(self, fake_home, monkeypatch):
        cli = fake_home / "bad" / "claude"
        cli.parent.mkdir(parents=True, exist_ok=True)
        cli.write_text("not executable")
        monkeypatch.setenv("BYAAN_CLAUDE_CLI_PATH", str(cli))
        monkeypatch.delenv("CLAUDE_CLI_PATH", raising=False)

        with patch("server.utils.general._is_executable_file", side_effect=_only_under(fake_home)):
            result = find_claude_cli_path(search_path="/nonexistent", home_dir=fake_home)
        assert result is None


class TestCustomHomeDir:
    def test_home_dir_local_bin(self, fake_home, monkeypatch):
        monkeypatch.delenv("BYAAN_CLAUDE_CLI_PATH", raising=False)
        monkeypatch.delenv("CLAUDE_CLI_PATH", raising=False)

        cli = fake_home / ".local" / "bin" / "claude"
        _make_executable(cli)

        with patch("server.utils.general._is_executable_file", side_effect=_only_under(fake_home)):
            result = find_claude_cli_path(search_path="/nonexistent", home_dir=fake_home)
        assert result == str(cli)

    def test_native_installer_current(self, fake_home, monkeypatch):
        monkeypatch.delenv("BYAAN_CLAUDE_CLI_PATH", raising=False)
        monkeypatch.delenv("CLAUDE_CLI_PATH", raising=False)

        cli = fake_home / ".local" / "share" / "claude" / "current" / "claude"
        _make_executable(cli)

        with patch("server.utils.general._is_executable_file", side_effect=_only_under(fake_home)):
            result = find_claude_cli_path(search_path="/nonexistent", home_dir=fake_home)
        assert result == str(cli)

    def test_native_installer_versions(self, fake_home, monkeypatch):
        monkeypatch.delenv("BYAAN_CLAUDE_CLI_PATH", raising=False)
        monkeypatch.delenv("CLAUDE_CLI_PATH", raising=False)

        cli = fake_home / ".local" / "share" / "claude" / "versions" / "1.0.0" / "claude"
        _make_executable(cli)

        with patch("server.utils.general._is_executable_file", side_effect=_only_under(fake_home)):
            result = find_claude_cli_path(search_path="/nonexistent", home_dir=fake_home)
        assert result == str(cli)


class TestIsCliNotFoundError:
    def test_true_for_cli_not_found_error(self):
        assert _is_cli_not_found_error(CLINotFoundError("not found")) is True

    def test_true_for_no_such_file_message(self):
        err = FileNotFoundError("No such file or directory: 'claude'")
        assert _is_cli_not_found_error(err) is True

    def test_false_for_generic_error(self):
        assert _is_cli_not_found_error(RuntimeError("something else")) is False

    def test_false_for_unrelated_file_not_found(self):
        err = FileNotFoundError("No such file or directory: 'python'")
        assert _is_cli_not_found_error(err) is False

    def test_false_for_claude_config_path(self):
        err = FileNotFoundError("No such file or directory: '/home/user/.claude/projects/session.json'")
        assert _is_cli_not_found_error(err) is False

    def test_true_for_full_path_to_claude_binary(self):
        err = FileNotFoundError("No such file or directory: '/usr/local/bin/claude'")
        assert _is_cli_not_found_error(err) is True
