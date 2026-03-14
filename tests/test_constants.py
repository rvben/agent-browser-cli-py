"""Tests for agent_browser.constants — platform detection, URL generation, naming."""

import pytest
from unittest.mock import patch


class TestPlatformNormalization:
    """Test that platform.system() and platform.machine() values are normalized correctly."""

    @pytest.mark.parametrize(
        "system_val, expected",
        [
            ("Darwin", "darwin"),
            ("darwin", "darwin"),
            ("Linux", "linux"),
            ("linux", "linux"),
            ("Windows", "windows"),
            ("windows", "windows"),
        ],
    )
    def test_system_normalization(self, system_val, expected):
        with (
            patch("platform.system", return_value=system_val),
            patch("platform.machine", return_value="x86_64"),
        ):
            # Re-import to trigger module-level normalization
            import importlib
            import agent_browser.constants as mod

            importlib.reload(mod)
            assert mod.SYSTEM == expected

    @pytest.mark.parametrize(
        "machine_val, expected",
        [
            ("x86_64", "x86_64"),
            ("amd64", "x86_64"),
            ("x64", "x86_64"),
            ("arm64", "arm64"),
            ("aarch64", "arm64"),
            ("armv8", "arm64"),
        ],
    )
    def test_machine_normalization(self, machine_val, expected):
        with (
            patch("platform.system", return_value="Linux"),
            patch("platform.machine", return_value=machine_val),
        ):
            import importlib
            import agent_browser.constants as mod

            importlib.reload(mod)
            assert mod.MACHINE == expected

    def test_unknown_machine_passes_through(self):
        with (
            patch("platform.system", return_value="Linux"),
            patch("platform.machine", return_value="riscv64"),
        ):
            import importlib
            import agent_browser.constants as mod

            importlib.reload(mod)
            assert mod.MACHINE == "riscv64"


class TestBinaryName:
    """Test get_binary_name() for all platforms."""

    def test_darwin_arm64(self):
        from agent_browser.constants import get_binary_name

        assert get_binary_name("darwin", "arm64") == "agent-browser-darwin-arm64"

    def test_darwin_x86_64(self):
        from agent_browser.constants import get_binary_name

        assert get_binary_name("darwin", "x86_64") == "agent-browser-darwin-x64"

    def test_linux_x86_64(self):
        from agent_browser.constants import get_binary_name

        assert get_binary_name("linux", "x86_64") == "agent-browser-linux-x64"

    def test_linux_arm64(self):
        from agent_browser.constants import get_binary_name

        assert get_binary_name("linux", "arm64") == "agent-browser-linux-arm64"

    def test_windows_x86_64(self):
        from agent_browser.constants import get_binary_name

        assert get_binary_name("windows", "x86_64") == "agent-browser-win32-x64.exe"

    def test_windows_has_exe_extension(self):
        from agent_browser.constants import get_binary_name

        name = get_binary_name("windows", "x86_64")
        assert name.endswith(".exe")

    def test_non_windows_no_exe_extension(self):
        from agent_browser.constants import get_binary_name

        for system in ("darwin", "linux"):
            name = get_binary_name(system, "arm64")
            assert not name.endswith(".exe")


class TestBinaryDownloadUrl:
    """Test get_binary_download_url() generates correct GitHub release URLs."""

    def test_url_contains_version(self):
        from agent_browser.constants import get_binary_download_url

        url = get_binary_download_url("1.2.3", "linux", "x86_64")
        assert "/v1.2.3/" in url

    def test_url_contains_repo(self):
        from agent_browser.constants import get_binary_download_url

        url = get_binary_download_url("1.0.0", "darwin", "arm64")
        assert "vercel-labs/agent-browser" in url

    def test_url_matches_binary_name(self):
        from agent_browser.constants import get_binary_download_url, get_binary_name

        for system, machine in [
            ("darwin", "arm64"),
            ("darwin", "x86_64"),
            ("linux", "x86_64"),
            ("linux", "arm64"),
            ("windows", "x86_64"),
        ]:
            url = get_binary_download_url("0.17.1", system, machine)
            name = get_binary_name(system, machine)
            assert url.endswith(f"/{name}")


class TestWheelPlatformTags:
    """Test that all 5 supported platforms have wheel tags."""

    def test_all_platforms_have_tags(self):
        from agent_browser.constants import WHEEL_PLATFORM_TAGS

        expected_platforms = [
            ("darwin", "arm64"),
            ("darwin", "x86_64"),
            ("linux", "x86_64"),
            ("linux", "arm64"),
            ("windows", "x86_64"),
        ]
        for platform in expected_platforms:
            assert platform in WHEEL_PLATFORM_TAGS, f"Missing tag for {platform}"

    def test_tag_format_darwin(self):
        from agent_browser.constants import WHEEL_PLATFORM_TAGS

        assert WHEEL_PLATFORM_TAGS[("darwin", "arm64")].startswith("macosx_")
        assert WHEEL_PLATFORM_TAGS[("darwin", "x86_64")].startswith("macosx_")

    def test_tag_format_linux(self):
        from agent_browser.constants import WHEEL_PLATFORM_TAGS

        assert "manylinux" in WHEEL_PLATFORM_TAGS[("linux", "x86_64")]
        assert "manylinux" in WHEEL_PLATFORM_TAGS[("linux", "arm64")]

    def test_tag_format_windows(self):
        from agent_browser.constants import WHEEL_PLATFORM_TAGS

        assert WHEEL_PLATFORM_TAGS[("windows", "x86_64")] == "win_amd64"

    def test_build_targets_matches_tags(self):
        from agent_browser.constants import BUILD_TARGETS, WHEEL_PLATFORM_TAGS

        assert set(BUILD_TARGETS) == set(WHEEL_PLATFORM_TAGS.keys())


