"""Tests for setup.py — platform tag generation and build validation.

setup.py imports setuptools which is a build dependency, not a runtime dep.
We test the pure logic by reimplementing the detection inline (same as setup.py does)
and verify consistency with constants.py.
"""

import os
import platform

import pytest
from unittest.mock import patch


# Replicate the pure functions from setup.py (they're intentionally inlined there
# to avoid importing agent_browser at build time)
_WHEEL_PLATFORM_TAGS = {
    ("darwin", "arm64"): "macosx_11_0_arm64",
    ("darwin", "x86_64"): "macosx_10_9_x86_64",
    ("linux", "x86_64"): "manylinux_2_17_x86_64.manylinux2014_x86_64",
    ("linux", "arm64"): "manylinux_2_17_aarch64.manylinux2014_aarch64",
    ("windows", "x86_64"): "win_amd64",
}


def _detect_platform():
    system = platform.system().lower()
    machine = platform.machine().lower()
    if system.startswith("darwin"):
        system = "darwin"
    elif system.startswith("linux"):
        system = "linux"
    elif system.startswith("win"):
        system = "windows"
    if machine in ("amd64", "x86_64", "x64"):
        machine = "x86_64"
    elif machine in ("arm64", "aarch64", "armv8"):
        machine = "arm64"
    return system, machine


def get_platform_tag():
    default_system, default_machine = _detect_platform()
    system = os.environ.get("TARGET_SYSTEM", default_system)
    machine = os.environ.get("TARGET_MACHINE", default_machine)
    tag = _WHEEL_PLATFORM_TAGS.get((system, machine))
    if not tag:
        raise RuntimeError(
            f"No wheel platform tag for {system}-{machine}. "
            f"Supported: {list(_WHEEL_PLATFORM_TAGS.keys())}"
        )
    return tag


class TestDetectPlatform:
    """Test _detect_platform() normalization logic (inlined in setup.py)."""

    @pytest.mark.parametrize(
        "system_val, machine_val, expected",
        [
            ("Darwin", "arm64", ("darwin", "arm64")),
            ("Darwin", "x86_64", ("darwin", "x86_64")),
            ("Linux", "x86_64", ("linux", "x86_64")),
            ("Linux", "aarch64", ("linux", "arm64")),
            ("Windows", "AMD64", ("windows", "x86_64")),
            ("Linux", "armv8", ("linux", "arm64")),
            ("Linux", "x64", ("linux", "x86_64")),
        ],
    )
    def test_normalizes_correctly(self, system_val, machine_val, expected):
        with (
            patch("platform.system", return_value=system_val),
            patch("platform.machine", return_value=machine_val),
        ):
            assert _detect_platform() == expected


class TestGetPlatformTag:
    """Test get_platform_tag() uses env vars and falls back to detection."""

    def test_uses_target_env_vars(self):
        with patch.dict(
            os.environ, {"TARGET_SYSTEM": "linux", "TARGET_MACHINE": "arm64"}
        ):
            tag = get_platform_tag()
        assert "aarch64" in tag or "arm64" in tag

    def test_all_supported_platforms_have_tags(self):
        for (system, machine), expected_tag in _WHEEL_PLATFORM_TAGS.items():
            with patch.dict(
                os.environ, {"TARGET_SYSTEM": system, "TARGET_MACHINE": machine}
            ):
                tag = get_platform_tag()
            assert tag == expected_tag

    def test_unsupported_platform_raises(self):
        with patch.dict(
            os.environ, {"TARGET_SYSTEM": "freebsd", "TARGET_MACHINE": "x86_64"}
        ):
            with pytest.raises(RuntimeError, match="No wheel platform tag"):
                get_platform_tag()

    def test_falls_back_to_current_platform(self):
        env = os.environ.copy()
        env.pop("TARGET_SYSTEM", None)
        env.pop("TARGET_MACHINE", None)
        with patch.dict(os.environ, env, clear=True):
            tag = get_platform_tag()
            assert isinstance(tag, str)
            assert len(tag) > 0


class TestWheelPlatformTagsConsistency:
    """Verify setup.py tags match constants.py tags."""

    def test_setup_tags_match_constants(self):
        from agent_browser.constants import WHEEL_PLATFORM_TAGS

        assert _WHEEL_PLATFORM_TAGS == WHEEL_PLATFORM_TAGS

    def test_all_five_platforms_present(self):
        assert len(_WHEEL_PLATFORM_TAGS) == 5

    def test_darwin_tags_have_macosx_prefix(self):
        for (system, _), tag in _WHEEL_PLATFORM_TAGS.items():
            if system == "darwin":
                assert tag.startswith("macosx_")

    def test_linux_tags_have_manylinux(self):
        for (system, _), tag in _WHEEL_PLATFORM_TAGS.items():
            if system == "linux":
                assert "manylinux" in tag

    def test_windows_tag(self):
        assert _WHEEL_PLATFORM_TAGS[("windows", "x86_64")] == "win_amd64"
