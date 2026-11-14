"""Exercise the actual build backend instead of copying its implementation."""

import hashlib
import json
import runpy
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def backend():
    return runpy.run_path(str(ROOT / "setup.py"))


def test_build_and_runtime_use_identical_platform_tags(backend):
    from agent_browser.constants import WHEEL_PLATFORM_TAGS

    assert backend["_WHEEL_PLATFORM_TAGS"] == WHEEL_PLATFORM_TAGS
    assert len(WHEEL_PLATFORM_TAGS) == 7


@pytest.mark.parametrize(
    "system,machine,tag",
    [
        ("darwin", "arm64", "macosx_11_0_arm64"),
        ("darwin", "x86_64", "macosx_10_12_x86_64"),
        ("linux", "x86_64", "manylinux_2_28_x86_64"),
        ("linux", "arm64", "manylinux_2_28_aarch64"),
        ("linux-musl", "x86_64", "musllinux_1_2_x86_64"),
        ("linux-musl", "arm64", "musllinux_1_2_aarch64"),
        ("windows", "x86_64", "win_amd64"),
    ],
)
def test_cross_build_tags(backend, monkeypatch, system, machine, tag):
    monkeypatch.setenv("TARGET_SYSTEM", system)
    monkeypatch.setenv("TARGET_MACHINE", machine)
    assert backend["get_platform_tag"]() == tag


def test_unsupported_target_fails(backend, monkeypatch):
    monkeypatch.setenv("TARGET_SYSTEM", "freebsd")
    with pytest.raises(RuntimeError, match="No wheel platform tag"):
        backend["get_platform_tag"]()


@pytest.mark.parametrize(
    "missing",
    ["bin", "skills", "licenses", "version", "content", "binary-content", None],
)
def test_build_rejects_incomplete_or_mismatched_resources(
    backend, monkeypatch, tmp_path, missing
):
    from setuptools import Distribution

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TARGET_SYSTEM", "linux")
    monkeypatch.setenv("TARGET_MACHINE", "x86_64")
    package = tmp_path / "agent_browser"
    files = {
        "version.py": '__version__ = "0.43.0.post1"',
        "bin/agent-browser-linux-x64": "binary",
        "skill-data/core/SKILL.md": "skill",
        "licenses/agent-browser-LICENSE": "license",
        "licenses/LICENSE-axe-core.txt": "license",
        "licenses/LICENSE-axe-core-THIRD-PARTY.txt": "license",
        "upstream.json": '{"version":"0.43.0"}',
    }
    for name, content in files.items():
        p = package / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    manifest = {
        "version": "0.43.0",
        "files": {
            name: hashlib.sha256(content.encode()).hexdigest()
            for name, content in files.items()
            if name.startswith(("licenses/", "skill-data/"))
        },
        "binaries": {
            "agent-browser-linux-x64": "sha256:" + hashlib.sha256(b"binary").hexdigest()
        },
    }
    (package / "upstream.json").write_text(json.dumps(manifest))
    if missing == "content":
        (package / "skill-data/core/SKILL.md").write_text("corrupt")
    elif missing == "binary-content":
        (package / "bin/agent-browser-linux-x64").write_text("corrupt")
    elif missing == "version":
        (package / "upstream.json").write_text('{"version":"0.42.0"}')
    elif missing in ("bin", "skills", "licenses"):
        name = {
            "bin": "bin/agent-browser-linux-x64",
            "skills": "skill-data/core/SKILL.md",
            "licenses": "licenses/agent-browser-LICENSE",
        }[missing]
        (package / name).unlink()
    command = backend["CustomBuildPy"](Distribution())
    command.ensure_finalized()
    if missing is None:
        with patch("setuptools.command.build_py.build_py.run") as build:
            command.run()
            build.assert_called_once()
        return
    expected = {
        "bin": "CLI binary not found",
        "skills": "Missing upstream resource skill-data",
        "licenses": "Missing upstream resource licenses",
        "version": "Runtime assets do not match",
        "content": "Runtime resource checksum mismatch",
        "binary-content": "Binary checksum mismatch",
    }
    with pytest.raises(RuntimeError, match=expected[missing]):
        command.run()


def test_empty_target_variables_use_host_defaults(backend, monkeypatch):
    monkeypatch.setenv("TARGET_SYSTEM", "")
    monkeypatch.setenv("TARGET_MACHINE", "")
    system, machine = backend["_detect_platform"]()
    assert (
        backend["get_platform_tag"]()
        == backend["_WHEEL_PLATFORM_TAGS"][(system, machine)]
    )
