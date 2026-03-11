"""Tests for agent_browser/__init__.py — package structure and path helpers."""

import os

from unittest.mock import patch


class TestPackageImport:
    """Test that the package imports cleanly and exposes expected attributes."""

    def test_version_is_string(self):
        from agent_browser import __version__

        assert isinstance(__version__, str)

    def test_version_is_semver(self):
        from agent_browser import __version__

        parts = __version__.split(".")
        assert len(parts) == 3
        for part in parts:
            assert part.isdigit()

    def test_system_is_normalized(self):
        from agent_browser import SYSTEM

        assert SYSTEM in ("darwin", "linux", "windows") or isinstance(SYSTEM, str)

    def test_machine_is_normalized(self):
        from agent_browser import MACHINE

        assert MACHINE in ("x86_64", "arm64") or isinstance(MACHINE, str)


class TestDirectoryPaths:
    """Test that directory path constants are correct."""

    def test_package_dir_exists(self):
        from agent_browser import PACKAGE_DIR

        assert os.path.isdir(PACKAGE_DIR)

    def test_package_dir_contains_init(self):
        from agent_browser import PACKAGE_DIR

        assert os.path.isfile(os.path.join(PACKAGE_DIR, "__init__.py"))

    def test_node_modules_dir_is_under_package(self):
        from agent_browser import PACKAGE_DIR, NODE_MODULES_DIR

        assert NODE_MODULES_DIR.startswith(PACKAGE_DIR)
        assert NODE_MODULES_DIR.endswith("node_modules")

    def test_bin_dir_is_under_package(self):
        from agent_browser import PACKAGE_DIR, BIN_DIR

        assert BIN_DIR.startswith(PACKAGE_DIR)
        assert BIN_DIR.endswith("bin")


class TestGetCliBinaryPath:
    """Test get_cli_binary_path() returns platform-correct paths."""

    def test_returns_string(self):
        from agent_browser import get_cli_binary_path

        path = get_cli_binary_path()
        assert isinstance(path, str)

    def test_path_is_under_bin_dir(self):
        from agent_browser import get_cli_binary_path, BIN_DIR

        path = get_cli_binary_path()
        assert path.startswith(BIN_DIR)

    def test_path_contains_agent_browser(self):
        from agent_browser import get_cli_binary_path

        path = get_cli_binary_path()
        assert "agent-browser" in os.path.basename(path)


class TestIsCliInstalled:
    """Test is_cli_installed() with different filesystem states."""

    def test_returns_false_when_no_binary(self, tmp_path):
        from agent_browser import is_cli_installed

        with patch(
            "agent_browser.get_cli_binary_path",
            return_value=str(tmp_path / "nonexistent"),
        ):
            assert is_cli_installed() is False

    def test_returns_true_when_binary_exists_executable(self, tmp_path):
        from agent_browser import is_cli_installed

        binary = tmp_path / "agent-browser-test"
        binary.write_text("#!/bin/sh\n")
        binary.chmod(0o755)
        with (
            patch("agent_browser.get_cli_binary_path", return_value=str(binary)),
            patch("agent_browser.SYSTEM", "linux"),
        ):
            assert is_cli_installed() is True

    def test_returns_false_when_binary_not_executable(self, tmp_path):
        from agent_browser import is_cli_installed

        binary = tmp_path / "agent-browser-test"
        binary.write_text("#!/bin/sh\n")
        binary.chmod(0o644)
        with (
            patch("agent_browser.get_cli_binary_path", return_value=str(binary)),
            patch("agent_browser.SYSTEM", "linux"),
        ):
            assert is_cli_installed() is False

    def test_windows_ignores_executable_bit(self, tmp_path):
        from agent_browser import is_cli_installed

        binary = tmp_path / "agent-browser-test.exe"
        binary.write_text("fake")
        binary.chmod(0o644)
        with (
            patch("agent_browser.get_cli_binary_path", return_value=str(binary)),
            patch("agent_browser.SYSTEM", "windows"),
        ):
            assert is_cli_installed() is True
