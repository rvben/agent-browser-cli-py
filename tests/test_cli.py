"""Tests for agent_browser.cli — CLI entry point and environment setup."""

import os
import sys

import pytest
from unittest.mock import patch


class TestMain:
    """Test the main() function that proxies to the Rust CLI."""

    def test_returns_1_when_binary_missing(self, capsys):
        from agent_browser.cli import main

        with patch("agent_browser.cli.is_cli_installed", return_value=False):
            result = main()

        assert result == 1
        captured = capsys.readouterr()
        assert "not found" in captured.err

    def test_returns_1_when_node_download_fails(self, capsys):
        from agent_browser.cli import main

        with (
            patch("agent_browser.cli.is_cli_installed", return_value=True),
            patch("agent_browser.cli.get_cli_binary_path", return_value="/fake/binary"),
            patch(
                "agent_browser.cli.ensure_node",
                side_effect=RuntimeError("Network error"),
            ),
        ):
            result = main()

        assert result == 1
        captured = capsys.readouterr()
        assert "Network error" in captured.err

    def test_proxies_to_cli_binary(self):
        from agent_browser.cli import main

        with (
            patch("agent_browser.cli.is_cli_installed", return_value=True),
            patch(
                "agent_browser.cli.get_cli_binary_path",
                return_value="/fake/agent-browser",
            ),
            patch("agent_browser.cli.ensure_node", return_value="/fake/node/bin/node"),
            patch("agent_browser.cli.NODE_MODULES_DIR", "/fake/node_modules"),
            patch("subprocess.call", return_value=0) as mock_call,
            patch.object(sys, "argv", ["agent-browser", "--version"]),
        ):
            result = main()

        assert result == 0
        mock_call.assert_called_once()
        args, kwargs = mock_call.call_args
        assert args[0][0] == "/fake/agent-browser"
        assert args[0][1] == "--version"

    def test_passes_all_args_to_subprocess(self):
        from agent_browser.cli import main

        with (
            patch("agent_browser.cli.is_cli_installed", return_value=True),
            patch("agent_browser.cli.get_cli_binary_path", return_value="/fake/binary"),
            patch("agent_browser.cli.ensure_node", return_value="/fake/node/bin/node"),
            patch("agent_browser.cli.NODE_MODULES_DIR", "/fake/node_modules"),
            patch("subprocess.call", return_value=0) as mock_call,
            patch.object(
                sys, "argv", ["agent-browser", "open", "example.com", "--headless"]
            ),
        ):
            main()

        args = mock_call.call_args[0][0]
        assert args == ["/fake/binary", "open", "example.com", "--headless"]

    def test_propagates_cli_exit_code(self):
        from agent_browser.cli import main

        with (
            patch("agent_browser.cli.is_cli_installed", return_value=True),
            patch("agent_browser.cli.get_cli_binary_path", return_value="/fake/binary"),
            patch("agent_browser.cli.ensure_node", return_value="/fake/node/bin/node"),
            patch("agent_browser.cli.NODE_MODULES_DIR", "/fake/node_modules"),
            patch("subprocess.call", return_value=42),
            patch.object(sys, "argv", ["agent-browser"]),
        ):
            result = main()

        assert result == 42

    def test_keyboard_interrupt_returns_130(self):
        from agent_browser.cli import main

        with (
            patch("agent_browser.cli.is_cli_installed", return_value=True),
            patch("agent_browser.cli.get_cli_binary_path", return_value="/fake/binary"),
            patch("agent_browser.cli.ensure_node", return_value="/fake/node/bin/node"),
            patch("agent_browser.cli.NODE_MODULES_DIR", "/fake/node_modules"),
            patch("subprocess.call", side_effect=KeyboardInterrupt),
            patch.object(sys, "argv", ["agent-browser"]),
        ):
            result = main()

        assert result == 130

    def test_file_not_found_returns_1(self, capsys):
        from agent_browser.cli import main

        with (
            patch("agent_browser.cli.is_cli_installed", return_value=True),
            patch("agent_browser.cli.get_cli_binary_path", return_value="/fake/binary"),
            patch("agent_browser.cli.ensure_node", return_value="/fake/node/bin/node"),
            patch("agent_browser.cli.NODE_MODULES_DIR", "/fake/node_modules"),
            patch("subprocess.call", side_effect=FileNotFoundError),
            patch.object(sys, "argv", ["agent-browser"]),
        ):
            result = main()

        assert result == 1


class TestEnvironmentSetup:
    """Test that main() sets up the environment correctly for the Rust CLI."""

    def test_node_dir_prepended_to_path(self):
        from agent_browser.cli import main

        captured_env = {}

        def capture_env(cmd, env=None):
            captured_env.update(env or {})
            return 0

        with (
            patch("agent_browser.cli.is_cli_installed", return_value=True),
            patch("agent_browser.cli.get_cli_binary_path", return_value="/fake/binary"),
            patch("agent_browser.cli.ensure_node", return_value="/cache/node/bin/node"),
            patch("agent_browser.cli.NODE_MODULES_DIR", "/fake/node_modules"),
            patch("subprocess.call", side_effect=capture_env),
            patch.object(sys, "argv", ["agent-browser"]),
        ):
            main()

        assert captured_env["PATH"].startswith("/cache/node/bin" + os.pathsep)

    def test_node_path_set_to_node_modules(self):
        from agent_browser.cli import main

        captured_env = {}

        def capture_env(cmd, env=None):
            captured_env.update(env or {})
            return 0

        with (
            patch("agent_browser.cli.is_cli_installed", return_value=True),
            patch("agent_browser.cli.get_cli_binary_path", return_value="/fake/binary"),
            patch("agent_browser.cli.ensure_node", return_value="/cache/node/bin/node"),
            patch("agent_browser.cli.NODE_MODULES_DIR", "/pkg/node_modules"),
            patch("subprocess.call", side_effect=capture_env),
            patch.object(sys, "argv", ["agent-browser"]),
        ):
            main()

        assert captured_env["NODE_PATH"] == "/pkg/node_modules"

    def test_agent_browser_home_set(self):
        from agent_browser.cli import main

        captured_env = {}

        def capture_env(cmd, env=None):
            captured_env.update(env or {})
            return 0

        with (
            patch("agent_browser.cli.is_cli_installed", return_value=True),
            patch("agent_browser.cli.get_cli_binary_path", return_value="/fake/binary"),
            patch("agent_browser.cli.ensure_node", return_value="/cache/node/bin/node"),
            patch("agent_browser.cli.NODE_MODULES_DIR", "/fake/node_modules"),
            patch("subprocess.call", side_effect=capture_env),
            patch.object(sys, "argv", ["agent-browser", "open", "example.com"]),
        ):
            main()

        assert captured_env["AGENT_BROWSER_HOME"] == os.path.join(
            "/fake/node_modules", "agent-browser"
        )

    def test_npm_config_offline_set(self):
        from agent_browser.cli import main

        captured_env = {}

        def capture_env(cmd, env=None):
            captured_env.update(env or {})
            return 0

        with (
            patch("agent_browser.cli.is_cli_installed", return_value=True),
            patch("agent_browser.cli.get_cli_binary_path", return_value="/fake/binary"),
            patch("agent_browser.cli.ensure_node", return_value="/cache/node/bin/node"),
            patch("agent_browser.cli.NODE_MODULES_DIR", "/fake/node_modules"),
            patch("subprocess.call", side_effect=capture_env),
            patch.object(sys, "argv", ["agent-browser"]),
        ):
            main()

        assert captured_env["NPM_CONFIG_OFFLINE"] == "true"

    def test_inherits_existing_env(self):
        from agent_browser.cli import main

        captured_env = {}

        def capture_env(cmd, env=None):
            captured_env.update(env or {})
            return 0

        with (
            patch("agent_browser.cli.is_cli_installed", return_value=True),
            patch("agent_browser.cli.get_cli_binary_path", return_value="/fake/binary"),
            patch("agent_browser.cli.ensure_node", return_value="/cache/node/bin/node"),
            patch("agent_browser.cli.NODE_MODULES_DIR", "/fake/node_modules"),
            patch("subprocess.call", side_effect=capture_env),
            patch.object(sys, "argv", ["agent-browser"]),
            patch.dict(os.environ, {"MY_CUSTOM_VAR": "hello"}),
        ):
            main()

        assert captured_env.get("MY_CUSTOM_VAR") == "hello"


class TestInstallIntercept:
    """Test that 'install' is intercepted and uses bundled playwright-core."""

    def test_install_calls_playwright_core_directly(self):
        from agent_browser.cli import main

        with (
            patch("agent_browser.cli.is_cli_installed", return_value=True),
            patch(
                "agent_browser.cli.get_cli_binary_path",
                return_value="/fake/agent-browser",
            ),
            patch("agent_browser.cli.ensure_node", return_value="/cache/node/bin/node"),
            patch("agent_browser.cli._PLAYWRIGHT_CLI", "/fake/node_modules/playwright-core/cli.js"),
            patch("subprocess.call", return_value=0) as mock_call,
            patch.object(sys, "argv", ["agent-browser", "install"]),
        ):
            result = main()

        assert result == 0
        mock_call.assert_called_once()
        args = mock_call.call_args[0][0]
        assert args[0] == "/cache/node/bin/node"
        assert "playwright-core/cli.js" in args[1]
        assert "install" in args
        assert "chromium" in args

    def test_install_passes_with_deps(self):
        from agent_browser.cli import main

        with (
            patch("agent_browser.cli.is_cli_installed", return_value=True),
            patch("agent_browser.cli.get_cli_binary_path", return_value="/fake/binary"),
            patch("agent_browser.cli.ensure_node", return_value="/cache/node/bin/node"),
            patch("agent_browser.cli._PLAYWRIGHT_CLI", "/fake/pw/cli.js"),
            patch("subprocess.call", return_value=0) as mock_call,
            patch.object(sys, "argv", ["agent-browser", "install", "--with-deps"]),
        ):
            main()

        args = mock_call.call_args[0][0]
        assert "--with-deps" in args

    def test_install_does_not_proxy_to_rust_cli(self):
        from agent_browser.cli import main

        with (
            patch("agent_browser.cli.is_cli_installed", return_value=True),
            patch(
                "agent_browser.cli.get_cli_binary_path",
                return_value="/fake/agent-browser",
            ),
            patch("agent_browser.cli.ensure_node", return_value="/cache/node/bin/node"),
            patch("agent_browser.cli._PLAYWRIGHT_CLI", "/fake/pw/cli.js"),
            patch("subprocess.call", return_value=0) as mock_call,
            patch.object(sys, "argv", ["agent-browser", "install"]),
        ):
            main()

        # Should NOT call the Rust binary
        args = mock_call.call_args[0][0]
        assert args[0] != "/fake/agent-browser"

    def test_non_install_still_proxies_to_rust_cli(self):
        from agent_browser.cli import main

        with (
            patch("agent_browser.cli.is_cli_installed", return_value=True),
            patch(
                "agent_browser.cli.get_cli_binary_path",
                return_value="/fake/agent-browser",
            ),
            patch("agent_browser.cli.ensure_node", return_value="/cache/node/bin/node"),
            patch("agent_browser.cli.NODE_MODULES_DIR", "/fake/node_modules"),
            patch("subprocess.call", return_value=0) as mock_call,
            patch.object(sys, "argv", ["agent-browser", "open", "example.com"]),
        ):
            main()

        args = mock_call.call_args[0][0]
        assert args[0] == "/fake/agent-browser"


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
