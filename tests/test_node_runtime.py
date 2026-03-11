"""Tests for agent_browser.node_runtime — Node.js download and caching."""

import os
import tarfile

import pytest
from unittest.mock import patch

from agent_browser.node_runtime import (
    get_node_dir,
    get_node_bin_path,
    is_node_installed,
    ensure_node,
    download_node,
)


class TestGetNodeDir:
    """Test get_node_dir() path construction."""

    def test_contains_node_version(self):
        from agent_browser.constants import NODE_VERSION

        node_dir = get_node_dir()
        assert f"node-v{NODE_VERSION}" in node_dir

    def test_under_cache_dir(self):
        from agent_browser.constants import CACHE_DIR

        node_dir = get_node_dir()
        assert node_dir.startswith(CACHE_DIR)


class TestGetNodeBinPath:
    """Test get_node_bin_path() for different platforms."""

    @patch("agent_browser.node_runtime.SYSTEM", "darwin")
    def test_darwin_has_bin_subdir(self):
        path = get_node_bin_path()
        assert "/bin/node" in path

    @patch("agent_browser.node_runtime.SYSTEM", "linux")
    def test_linux_has_bin_subdir(self):
        path = get_node_bin_path()
        assert "/bin/node" in path

    @patch("agent_browser.node_runtime.SYSTEM", "windows")
    def test_windows_has_exe(self):
        path = get_node_bin_path()
        assert path.endswith("node.exe")
        assert "/bin/" not in path


class TestIsNodeInstalled:
    """Test is_node_installed() with mocked filesystem."""

    def test_returns_false_when_binary_missing(self, tmp_path):
        with patch(
            "agent_browser.node_runtime.get_node_bin_path",
            return_value=str(tmp_path / "nonexistent"),
        ):
            assert is_node_installed() is False

    def test_returns_true_when_binary_exists_and_executable(self, tmp_path):
        node_bin = tmp_path / "node"
        node_bin.write_text("#!/bin/sh\n")
        node_bin.chmod(0o755)
        with (
            patch(
                "agent_browser.node_runtime.get_node_bin_path",
                return_value=str(node_bin),
            ),
            patch("agent_browser.node_runtime.SYSTEM", "linux"),
        ):
            assert is_node_installed() is True

    def test_returns_false_when_binary_not_executable(self, tmp_path):
        node_bin = tmp_path / "node"
        node_bin.write_text("#!/bin/sh\n")
        node_bin.chmod(0o644)
        with (
            patch(
                "agent_browser.node_runtime.get_node_bin_path",
                return_value=str(node_bin),
            ),
            patch("agent_browser.node_runtime.SYSTEM", "linux"),
        ):
            assert is_node_installed() is False

    def test_windows_skips_executable_check(self, tmp_path):
        node_bin = tmp_path / "node.exe"
        node_bin.write_text("fake binary")
        node_bin.chmod(0o644)  # Not executable, but Windows doesn't care
        with (
            patch(
                "agent_browser.node_runtime.get_node_bin_path",
                return_value=str(node_bin),
            ),
            patch("agent_browser.node_runtime.SYSTEM", "windows"),
        ):
            assert is_node_installed() is True


class TestEnsureNode:
    """Test ensure_node() caching and download logic."""

    def test_returns_path_when_already_installed(self, tmp_path):
        node_bin = tmp_path / "bin" / "node"
        node_bin.parent.mkdir(parents=True)
        node_bin.write_text("#!/bin/sh\n")
        node_bin.chmod(0o755)

        with (
            patch("agent_browser.node_runtime.is_node_installed", return_value=True),
            patch(
                "agent_browser.node_runtime.get_node_bin_path",
                return_value=str(node_bin),
            ),
        ):
            result = ensure_node()
            assert result == str(node_bin)

    def test_downloads_when_not_installed(self, tmp_path):
        node_bin = tmp_path / "bin" / "node"
        node_bin.parent.mkdir(parents=True)
        node_bin.write_text("#!/bin/sh\n")
        node_bin.chmod(0o755)

        with (
            patch("agent_browser.node_runtime.is_node_installed", return_value=False),
            patch("agent_browser.node_runtime.download_node") as mock_download,
            patch(
                "agent_browser.node_runtime.get_node_bin_path",
                return_value=str(node_bin),
            ),
        ):
            result = ensure_node()
            mock_download.assert_called_once()
            assert result == str(node_bin)

    def test_raises_when_download_fails(self, tmp_path):
        missing = str(tmp_path / "bin" / "node")

        with (
            patch("agent_browser.node_runtime.is_node_installed", return_value=False),
            patch("agent_browser.node_runtime.download_node"),
            patch("agent_browser.node_runtime.get_node_bin_path", return_value=missing),
        ):
            with pytest.raises(RuntimeError, match="binary not found"):
                ensure_node()


class TestDownloadNode:
    """Test download_node() extraction and directory structure."""

    def _create_fake_node_tarball(self, tmp_path, version="22.14.0"):
        """Create a minimal fake Node.js tarball with expected structure."""
        node_name = f"node-v{version}-linux-arm64"
        node_root = tmp_path / node_name
        bin_dir = node_root / "bin"
        lib_dir = node_root / "lib" / "node_modules" / "npm"
        include_dir = node_root / "include"
        share_dir = node_root / "share"

        bin_dir.mkdir(parents=True)
        lib_dir.mkdir(parents=True)
        include_dir.mkdir(parents=True)
        share_dir.mkdir(parents=True)

        # Create node binary
        (bin_dir / "node").write_text("#!/bin/sh\necho node")
        (bin_dir / "node").chmod(0o755)

        # Create npm as symlink (this is what real Node.js does)
        npm_cli = lib_dir / "bin" / "npm-cli.js"
        npm_cli.parent.mkdir(parents=True)
        npm_cli.write_text("#!/usr/bin/env node\nconsole.log('npm')")
        (bin_dir / "npm").symlink_to("../lib/node_modules/npm/bin/npm-cli.js")

        # Create npx as symlink
        npx_cli = lib_dir / "bin" / "npx-cli.js"
        npx_cli.write_text("#!/usr/bin/env node\nconsole.log('npx')")
        (bin_dir / "npx").symlink_to("../lib/node_modules/npm/bin/npx-cli.js")

        # Create files in dirs that should be stripped
        (include_dir / "node.h").write_text("// header")
        (share_dir / "doc.txt").write_text("docs")
        (node_root / "CHANGELOG.md").write_text("# Changes")
        (node_root / "README.md").write_text("# Node")
        (node_root / "LICENSE").write_text("MIT")

        # Create tarball
        tarball_path = tmp_path / "node.tar.gz"
        with tarfile.open(str(tarball_path), "w:gz") as tar:
            tar.add(str(node_root), arcname=node_name)

        return str(tarball_path)

    def test_extracts_and_strips_correctly(self, tmp_path):
        tarball = self._create_fake_node_tarball(tmp_path)
        node_dir = tmp_path / "installed"

        with (
            patch(
                "agent_browser.node_runtime.get_node_dir", return_value=str(node_dir)
            ),
            patch(
                "agent_browser.node_runtime.get_node_download_url",
                return_value=f"file://{tarball}",
            ),
            patch(
                "urllib.request.urlretrieve",
                side_effect=lambda url, path: __import__("shutil").copy2(tarball, path),
            ),
        ):
            download_node()

        # bin/ should exist with node, npm, npx
        assert (node_dir / "bin" / "node").exists()
        assert (node_dir / "bin" / "npm").exists() or (
            node_dir / "bin" / "npm"
        ).is_symlink()
        assert (node_dir / "bin" / "npx").exists() or (
            node_dir / "bin" / "npx"
        ).is_symlink()

        # lib/ should exist (npm runtime)
        assert (node_dir / "lib").exists()

        # Stripped directories should not exist
        assert not (node_dir / "include").exists()
        assert not (node_dir / "share").exists()

        # Stripped files should not exist
        assert not (node_dir / "CHANGELOG.md").exists()
        assert not (node_dir / "README.md").exists()

        # LICENSE should still exist (we don't strip it)
        assert (node_dir / "LICENSE").exists()

    def test_preserves_symlinks(self, tmp_path):
        """Verify npm/npx symlinks are preserved, not resolved to copies."""
        tarball = self._create_fake_node_tarball(tmp_path)
        node_dir = tmp_path / "installed"

        with (
            patch(
                "agent_browser.node_runtime.get_node_dir", return_value=str(node_dir)
            ),
            patch(
                "agent_browser.node_runtime.get_node_download_url",
                return_value=f"file://{tarball}",
            ),
            patch(
                "urllib.request.urlretrieve",
                side_effect=lambda url, path: __import__("shutil").copy2(tarball, path),
            ),
        ):
            download_node()

        npm_path = node_dir / "bin" / "npm"
        npx_path = node_dir / "bin" / "npx"

        assert npm_path.is_symlink(), "npm should be a symlink, not a regular file"
        assert npx_path.is_symlink(), "npx should be a symlink, not a regular file"

    def test_binaries_are_executable(self, tmp_path):
        tarball = self._create_fake_node_tarball(tmp_path)
        node_dir = tmp_path / "installed"

        with (
            patch(
                "agent_browser.node_runtime.get_node_dir", return_value=str(node_dir)
            ),
            patch(
                "agent_browser.node_runtime.get_node_download_url",
                return_value=f"file://{tarball}",
            ),
            patch(
                "urllib.request.urlretrieve",
                side_effect=lambda url, path: __import__("shutil").copy2(tarball, path),
            ),
        ):
            download_node()

        node_bin = node_dir / "bin" / "node"
        assert os.access(str(node_bin), os.X_OK), "node binary should be executable"

    def test_cleans_up_existing_dir(self, tmp_path):
        """If node_dir already exists from a previous download, it should be replaced."""
        tarball = self._create_fake_node_tarball(tmp_path)
        node_dir = tmp_path / "installed"
        node_dir.mkdir()
        (node_dir / "stale_file.txt").write_text("old stuff")

        with (
            patch(
                "agent_browser.node_runtime.get_node_dir", return_value=str(node_dir)
            ),
            patch(
                "agent_browser.node_runtime.get_node_download_url",
                return_value=f"file://{tarball}",
            ),
            patch(
                "urllib.request.urlretrieve",
                side_effect=lambda url, path: __import__("shutil").copy2(tarball, path),
            ),
        ):
            download_node()

        assert not (node_dir / "stale_file.txt").exists()
        assert (node_dir / "bin" / "node").exists()

    def test_cleans_up_temp_file_on_success(self, tmp_path):
        """The downloaded archive temp file should be cleaned up."""
        tarball = self._create_fake_node_tarball(tmp_path)
        node_dir = tmp_path / "installed"
        created_temps = []

        def tracking_urlretrieve(url, path):
            created_temps.append(path)
            __import__("shutil").copy2(tarball, path)

        with (
            patch(
                "agent_browser.node_runtime.get_node_dir", return_value=str(node_dir)
            ),
            patch(
                "agent_browser.node_runtime.get_node_download_url",
                return_value=f"file://{tarball}",
            ),
            patch("urllib.request.urlretrieve", side_effect=tracking_urlretrieve),
        ):
            download_node()

        for temp in created_temps:
            assert not os.path.exists(temp), f"Temp file {temp} was not cleaned up"

    def test_raises_on_http_error(self, tmp_path):
        import urllib.error

        node_dir = tmp_path / "installed"

        with (
            patch(
                "agent_browser.node_runtime.get_node_dir", return_value=str(node_dir)
            ),
            patch(
                "agent_browser.node_runtime.get_node_download_url",
                return_value="https://example.com/fake.tar.gz",
            ),
            patch(
                "urllib.request.urlretrieve",
                side_effect=urllib.error.HTTPError(
                    "https://example.com/fake.tar.gz", 404, "Not Found", {}, None
                ),
            ),
        ):
            with pytest.raises(RuntimeError, match="HTTP 404"):
                download_node()
