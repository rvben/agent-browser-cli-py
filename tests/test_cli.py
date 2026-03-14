"""Tests for agent_browser.cli — CLI entry point."""

import sys
import subprocess

import pytest
from unittest.mock import patch, MagicMock


def _mock_run(returncode=0, stderr=b""):
    """Create a mock subprocess.run result."""
    result = MagicMock(spec=subprocess.CompletedProcess)
    result.returncode = returncode
    result.stderr = stderr
    return result


class TestMain:
    """Test the main() function that proxies to the Rust CLI."""

    def test_returns_1_when_binary_missing(self, capsys):
        from agent_browser.cli import main

        with patch("agent_browser.cli.is_cli_installed", return_value=False):
            result = main()

        assert result == 1
        captured = capsys.readouterr()
        assert "not found" in captured.err

    def test_proxies_to_cli_binary(self):
        from agent_browser.cli import main

        with (
            patch("agent_browser.cli.is_cli_installed", return_value=True),
            patch(
                "agent_browser.cli.get_cli_binary_path",
                return_value="/fake/agent-browser",
            ),
            patch("subprocess.run", return_value=_mock_run()) as mock_run,
            patch.object(sys, "argv", ["agent-browser", "--version"]),
        ):
            result = main()

        assert result == 0
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args[0] == "/fake/agent-browser"
        assert args[1] == "--version"

    def test_passes_all_args_to_subprocess(self):
        from agent_browser.cli import main

        with (
            patch("agent_browser.cli.is_cli_installed", return_value=True),
            patch("agent_browser.cli.get_cli_binary_path", return_value="/fake/binary"),
            patch("subprocess.run", return_value=_mock_run()) as mock_run,
            patch.object(
                sys, "argv", ["agent-browser", "open", "example.com", "--headless"]
            ),
        ):
            main()

        args = mock_run.call_args[0][0]
        assert args == ["/fake/binary", "open", "example.com", "--headless"]

    def test_propagates_cli_exit_code(self):
        from agent_browser.cli import main

        with (
            patch("agent_browser.cli.is_cli_installed", return_value=True),
            patch("agent_browser.cli.get_cli_binary_path", return_value="/fake/binary"),
            patch("subprocess.run", return_value=_mock_run(returncode=42)),
            patch.object(sys, "argv", ["agent-browser"]),
        ):
            result = main()

        assert result == 42

    def test_install_command_proxied_to_rust_binary(self):
        """Install is now handled by the Rust binary, not intercepted."""
        from agent_browser.cli import main

        with (
            patch("agent_browser.cli.is_cli_installed", return_value=True),
            patch(
                "agent_browser.cli.get_cli_binary_path",
                return_value="/fake/agent-browser",
            ),
            patch("subprocess.run", return_value=_mock_run()) as mock_run,
            patch.object(sys, "argv", ["agent-browser", "install", "--with-deps"]),
        ):
            result = main()

        assert result == 0
        args = mock_run.call_args[0][0]
        assert args == ["/fake/agent-browser", "install", "--with-deps"]

    def test_keyboard_interrupt_returns_130(self):
        from agent_browser.cli import main

        with (
            patch("agent_browser.cli.is_cli_installed", return_value=True),
            patch("agent_browser.cli.get_cli_binary_path", return_value="/fake/binary"),
            patch("subprocess.run", side_effect=KeyboardInterrupt),
            patch.object(sys, "argv", ["agent-browser"]),
        ):
            result = main()

        assert result == 130

    def test_file_not_found_returns_1(self, capsys):
        from agent_browser.cli import main

        with (
            patch("agent_browser.cli.is_cli_installed", return_value=True),
            patch("agent_browser.cli.get_cli_binary_path", return_value="/fake/binary"),
            patch("subprocess.run", side_effect=FileNotFoundError),
            patch.object(sys, "argv", ["agent-browser"]),
        ):
            result = main()

        assert result == 1


class TestErrorHints:
    """Test that helpful hints are shown for common errors."""

    def test_hints_install_with_deps_on_missing_shared_libs(self, capsys):
        from agent_browser.cli import main

        stderr = b"error while loading shared libraries: libnspr4.so: cannot open"
        with (
            patch("agent_browser.cli.is_cli_installed", return_value=True),
            patch("agent_browser.cli.get_cli_binary_path", return_value="/fake/binary"),
            patch("subprocess.run", return_value=_mock_run(returncode=1, stderr=stderr)),
            patch.object(sys, "argv", ["agent-browser", "open", "example.com"]),
        ):
            result = main()

        assert result == 1
        captured = capsys.readouterr()
        assert "agent-browser install --with-deps" in captured.err

    def test_hints_install_on_missing_chromium(self, capsys):
        from agent_browser.cli import main

        stderr = b"Executable doesn't exist at /root/.cache/ms-playwright/chromium"
        with (
            patch("agent_browser.cli.is_cli_installed", return_value=True),
            patch("agent_browser.cli.get_cli_binary_path", return_value="/fake/binary"),
            patch("subprocess.run", return_value=_mock_run(returncode=1, stderr=stderr)),
            patch.object(sys, "argv", ["agent-browser", "open", "example.com"]),
        ):
            result = main()

        assert result == 1
        captured = capsys.readouterr()
        assert "agent-browser install" in captured.err

    def test_hints_install_on_chrome_not_found(self, capsys):
        from agent_browser.cli import main

        stderr = b"Chrome not found. Run `agent-browser install` to download Chrome"
        with (
            patch("agent_browser.cli.is_cli_installed", return_value=True),
            patch("agent_browser.cli.get_cli_binary_path", return_value="/fake/binary"),
            patch("subprocess.run", return_value=_mock_run(returncode=1, stderr=stderr)),
            patch.object(sys, "argv", ["agent-browser", "open", "example.com"]),
        ):
            result = main()

        assert result == 1
        captured = capsys.readouterr()
        assert "agent-browser install" in captured.err

    def test_no_hint_on_success(self, capsys):
        from agent_browser.cli import main

        with (
            patch("agent_browser.cli.is_cli_installed", return_value=True),
            patch("agent_browser.cli.get_cli_binary_path", return_value="/fake/binary"),
            patch("subprocess.run", return_value=_mock_run()),
            patch.object(sys, "argv", ["agent-browser", "open", "example.com"]),
        ):
            result = main()

        assert result == 0
        captured = capsys.readouterr()
        assert "Hint" not in captured.err

    def test_no_hint_on_unrelated_error(self, capsys):
        from agent_browser.cli import main

        stderr = b"some other error"
        with (
            patch("agent_browser.cli.is_cli_installed", return_value=True),
            patch("agent_browser.cli.get_cli_binary_path", return_value="/fake/binary"),
            patch("subprocess.run", return_value=_mock_run(returncode=1, stderr=stderr)),
            patch.object(sys, "argv", ["agent-browser", "open", "example.com"]),
        ):
            result = main()

        assert result == 1
        captured = capsys.readouterr()
        assert "Hint" not in captured.err


class TestEntryPoint:
    """Test the entry_point() wrapper."""

    def test_calls_sys_exit_with_main_result(self):
        from agent_browser.cli import entry_point

        with (
            patch("agent_browser.cli.main", return_value=0),
            pytest.raises(SystemExit) as exc_info,
        ):
            entry_point()

        assert exc_info.value.code == 0

    def test_exits_with_error_code(self):
        from agent_browser.cli import entry_point

        with (
            patch("agent_browser.cli.main", return_value=1),
            pytest.raises(SystemExit) as exc_info,
        ):
            entry_point()

        assert exc_info.value.code == 1
