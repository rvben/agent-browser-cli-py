"""Verify build inputs before they become executable wheel contents."""

import base64
import hashlib
import io
import json
import tarfile
import urllib.error
from pathlib import Path
from unittest.mock import patch

import pytest

from agent_browser.constants import BUILD_TARGETS, get_binary_name
from download_binaries import (
    PrivateRedirectHandler,
    download_cli_binary,
    download_file,
    download_runtime_assets,
    read_url,
    unpack_runtime_assets,
)


def runtime_archive(version="0.43.0", extra=None, omit=None):
    files = {
        "package/package.json": json.dumps({"version": version}).encode(),
        "package/skill-data/core/SKILL.md": b"core skill",
        "package/skill-data/core/references/commands.md": b"commands",
        "package/skills/agent-browser/SKILL.md": b"discovery",
        "package/LICENSE": b"Apache-2.0",
        "package/cli/src/native/a11y/LICENSE-axe-core.txt": b"MPL-2.0",
        "package/cli/src/native/a11y/LICENSE-axe-core-THIRD-PARTY.txt": b"MIT and ISC",
        "package/scripts/postinstall.js": b"must never ship or execute",
        **(extra or {}),
    }
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz") as bundle:
        for name, data in files.items():
            if name == omit:
                continue
            member = tarfile.TarInfo(name)
            if data is None:
                member.type = tarfile.SYMTYPE
                member.linkname = "/tmp/escape"
                bundle.addfile(member)
            else:
                member.size = len(data)
                bundle.addfile(member, io.BytesIO(data))
    return output.getvalue()


@pytest.mark.parametrize(
    "system,machine,name",
    [
        ("darwin", "arm64", "agent-browser-darwin-arm64"),
        ("linux", "x86_64", "agent-browser-linux-x64"),
        ("linux-musl", "arm64", "agent-browser-linux-musl-arm64"),
        ("windows", "x86_64", "agent-browser-win32-x64.exe"),
    ],
)
def test_binary_verified_before_install(tmp_path, monkeypatch, system, machine, name):
    monkeypatch.chdir(tmp_path)
    data = b"verified executable"
    release = json.dumps(
        {
            "assets": [
                {"name": name, "digest": "sha256:" + hashlib.sha256(data).hexdigest()}
            ]
        }
    ).encode()
    with patch("download_binaries.read_url", side_effect=[release, data]):
        download_cli_binary("0.43.0", system, machine)
    binary = tmp_path / "agent_browser/bin" / name
    assert binary.read_bytes() == data
    if system != "windows":
        assert binary.stat().st_mode & 0o111


def test_corrupt_binary_preserves_previous_download(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    binary = Path("agent_browser/bin/agent-browser-darwin-arm64")
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b"old good executable")
    release = json.dumps(
        {"assets": [{"name": binary.name, "digest": "sha256:" + "0" * 64}]}
    ).encode()
    with (
        patch("download_binaries.read_url", side_effect=[release, b"corrupt"]),
        pytest.raises(RuntimeError, match="SHA-256 mismatch"),
    ):
        download_cli_binary("0.43.0", "darwin", "arm64")
    assert binary.read_bytes() == b"old good executable"


@pytest.mark.parametrize(
    "assets", [[], [{"name": "agent-browser-darwin-arm64", "digest": None}]]
)
def test_missing_release_digest_is_rejected(tmp_path, monkeypatch, assets):
    monkeypatch.chdir(tmp_path)
    with (
        patch(
            "download_binaries.read_url",
            return_value=json.dumps({"assets": assets}).encode(),
        ),
        pytest.raises(RuntimeError, match="No SHA-256"),
    ):
        download_cli_binary("0.43.0", "darwin", "arm64")
    assert not Path("agent_browser/bin").exists()


def test_failed_download_is_actionable(tmp_path):
    with (
        patch(
            "urllib.request.OpenerDirector.open",
            side_effect=urllib.error.HTTPError(
                "https://example.com", 404, "missing", {}, None
            ),
        ),
        pytest.raises(RuntimeError, match="404"),
    ):
        download_file("https://example.com", str(tmp_path / "file"))


def test_runtime_payload_contains_only_matching_skills_and_licenses(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    archive = runtime_archive()
    integrity = "sha512-" + base64.b64encode(hashlib.sha512(archive).digest()).decode()
    metadata = json.dumps(
        {
            "dist": {
                "integrity": integrity,
                "tarball": "https://registry.npmjs.org/agent-browser/-/agent-browser-0.43.0.tgz",
            }
        }
    ).encode()
    digests = {
        get_binary_name(*target): "sha256:" + "0" * 64 for target in BUILD_TARGETS
    }
    with (
        patch("download_binaries.read_url", side_effect=[metadata, archive]) as fetch,
        patch("download_binaries.get_release_digests", return_value=digests),
    ):
        download_runtime_assets("0.43.0")
        # Every later platform reuses the same verified version-matched data.
        download_runtime_assets("0.43.0")
        assert fetch.call_count == 2
    package = Path("agent_browser")
    assert (
        package / "skill-data/core/references/commands.md"
    ).read_text() == "commands"
    assert (package / "licenses/agent-browser-LICENSE").read_text() == "Apache-2.0"
    assert json.loads((package / "upstream.json").read_text())["version"] == "0.43.0"
    assert not (package / "scripts").exists()


def test_corrupt_runtime_archive_preserves_existing_skills(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    old = Path("agent_browser/skill-data/core/SKILL.md")
    old.parent.mkdir(parents=True)
    old.write_text("keep me")
    metadata = json.dumps(
        {
            "dist": {
                "integrity": "sha512-wrong",
                "tarball": "https://example.com/archive",
            }
        }
    ).encode()
    with (
        patch("download_binaries.read_url", side_effect=[metadata, runtime_archive()]),
        pytest.raises(RuntimeError, match="SHA-512 mismatch"),
    ):
        download_runtime_assets("0.43.0")
    assert old.read_text() == "keep me"


@pytest.mark.parametrize(
    "archive,error",
    [
        (runtime_archive("0.42.0"), "version does not match"),
        (runtime_archive(omit="package/LICENSE"), "missing licenses"),
        (
            runtime_archive(extra={"package/skill-data/../../escaped": b"bad"}),
            "Unsafe path",
        ),
        (
            runtime_archive(extra={"package/skill-data/link": None}),
            "regular upstream file",
        ),
    ],
)
def test_invalid_archive_rejected(tmp_path, archive, error):
    with pytest.raises(RuntimeError, match=error):
        unpack_runtime_assets(archive, tmp_path, "0.43.0")
    assert not (tmp_path.parent / "escaped").exists()


@pytest.mark.parametrize(
    "name", ["package/skills/..\\..\\escaped", "package/skills/C:escaped"]
)
def test_windows_archive_paths_are_rejected(tmp_path, name):
    with pytest.raises(RuntimeError, match="Unsafe path"):
        unpack_runtime_assets(runtime_archive(extra={name: b"bad"}), tmp_path, "0.43.0")


@pytest.mark.parametrize(
    "url,authenticated",
    [
        (
            "https://api.github.com/repos/vercel-labs/agent-browser/releases/latest",
            True,
        ),
        (
            "https://github.com/vercel-labs/agent-browser/releases/download/v0.43.0/binary",
            False,
        ),
        ("https://registry.npmjs.org/agent-browser/0.43.0", False),
    ],
)
def test_credentials_are_only_sent_to_github_api(monkeypatch, url, authenticated):
    monkeypatch.setenv("GITHUB_TOKEN", "test-only-credential")
    with patch("urllib.request.OpenerDirector.open") as opened:
        opened.return_value.__enter__.return_value.read.return_value = b"ok"
        assert read_url(url) == b"ok"
    request = opened.call_args.args[0]
    assert bool(request.get_header("Authorization")) is authenticated
    assert request.get_header("User-agent") == "agent-browser-cli-builder"


def test_redirect_drops_authentication_on_another_host():
    import urllib.request

    request = urllib.request.Request(
        "https://api.github.com/source",
        headers={"Authorization": "Bearer test-only-credential"},
    )
    redirected = PrivateRedirectHandler().redirect_request(
        request,
        None,
        302,
        "redirect",
        {},
        "https://objects.githubusercontent.com/binary",
    )
    assert redirected.get_header("Authorization") is None
