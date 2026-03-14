"""Tests for download_binaries.py — build-time binary download logic."""

import os
from unittest.mock import patch

from download_binaries import download_cli_binary, download_file


class TestDownloadFile:
    """Test the download_file helper."""

    def test_downloads_to_destination(self, tmp_path):
        dest = str(tmp_path / "binary")
        with patch("urllib.request.urlretrieve") as mock:
            download_file("https://example.com/file", dest)

        mock.assert_called_once_with("https://example.com/file", dest)

    def test_raises_on_http_error(self, tmp_path):
        import urllib.error

        dest = str(tmp_path / "binary")
        with patch(
            "urllib.request.urlretrieve",
            side_effect=urllib.error.HTTPError(
                "https://example.com/file", 404, "Not Found", {}, None
            ),
        ):
            try:
                download_file("https://example.com/file", dest)
                assert False, "Should have raised"
            except RuntimeError as e:
                assert "404" in str(e)


class TestDownloadCliBinary:
    """Test CLI binary download for various platforms."""

    @staticmethod
    def _fake_download(url, dest):
        """Mock download that creates the file."""
        with open(dest, "w") as f:
            f.write("fake")

    def test_downloads_darwin_arm64(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

        with patch("download_binaries.download_file", side_effect=self._fake_download) as mock_dl:
            download_cli_binary("0.20.0", "darwin", "arm64")

        url = mock_dl.call_args[0][0]
        dest = mock_dl.call_args[0][1]
        assert "agent-browser-darwin-arm64" in url
        assert "v0.20.0" in url
        assert dest.endswith("agent-browser-darwin-arm64")

    def test_downloads_linux_x86_64(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

        with patch("download_binaries.download_file", side_effect=self._fake_download) as mock_dl:
            download_cli_binary("0.20.0", "linux", "x86_64")

        url = mock_dl.call_args[0][0]
        assert "agent-browser-linux-x64" in url

    def test_downloads_windows_x86_64(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

        with patch("download_binaries.download_file", side_effect=self._fake_download) as mock_dl:
            download_cli_binary("0.20.0", "windows", "x86_64")

        url = mock_dl.call_args[0][0]
        dest = mock_dl.call_args[0][1]
        assert "agent-browser-win32-x64.exe" in url
        assert dest.endswith(".exe")

    def test_creates_bin_directory(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

        with patch("download_binaries.download_file", side_effect=self._fake_download):
            download_cli_binary("0.20.0", "darwin", "arm64")

        assert os.path.isdir("agent_browser/bin")

    def test_sets_executable_permission_on_unix(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        os.makedirs("agent_browser/bin", exist_ok=True)

        # Create the file so chmod works
        binary_path = os.path.join("agent_browser", "bin", "agent-browser-darwin-arm64")

        def fake_download(url, dest):
            with open(dest, "w") as f:
                f.write("fake")

        with patch("download_binaries.download_file", side_effect=fake_download):
            download_cli_binary("0.20.0", "darwin", "arm64")

        assert os.access(binary_path, os.X_OK)
