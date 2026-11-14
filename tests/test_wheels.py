"""A mislabeled or incomplete wheel must fail the publication gate."""

import hashlib
import json
import runpy
import struct
import zipfile
from pathlib import Path

import pytest

CHECK = runpy.run_path(
    str(Path(__file__).resolve().parent.parent / "scripts/check_wheels.py")
)["check_wheel"]


@pytest.mark.parametrize(
    "fault",
    [
        None,
        "missing-reference",
        "wrong-binary",
        "stale-skills",
        "stale-version",
        "wrong-metadata",
    ],
)
def test_wheel_content_gate(tmp_path, fault):
    binary = bytearray(128)
    binary[:6] = b"\x7fELF\x02\x01"
    struct.pack_into("<H", binary, 18, 62)
    struct.pack_into("<Q", binary, 40, 64)
    struct.pack_into("<HH", binary, 58, 64, 1)
    prefix = "agent_browser_cli-0.43.0.data/purelib/agent_browser/"
    payload = {
        "__init__.py": b"",
        "bin/agent-browser-linux-musl-x64": bytes(binary),
        "version.py": b'__version__ = "0.43.0"\n__agent_browser_version__ = "0.43.0"\n',
        "upstream.json": json.dumps({"version": "0.43.0"}).encode(),
        "skill-data/core/SKILL.md": b"core",
        "skill-data/core/references/commands.md": b"reference",
        "skills/agent-browser/SKILL.md": b"discovery",
        "licenses/agent-browser-LICENSE": b"Apache-2.0",
        "licenses/LICENSE-axe-core.txt": b"MPL-2.0",
        "licenses/LICENSE-axe-core-THIRD-PARTY.txt": b"MIT AND ISC",
    }
    provenance = {
        "version": "0.43.0",
        "binaries": {
            "agent-browser-linux-musl-x64": "sha256:"
            + hashlib.sha256(binary).hexdigest()
        },
        "files": {},
    }
    payload["upstream.json"] = json.dumps(provenance).encode()
    metadata = b"Version: 0.43.0\nLicense-Expression: MIT AND Apache-2.0\n"
    if fault == "missing-reference":
        del payload["skill-data/core/references/commands.md"]
    elif fault == "wrong-binary":
        payload["bin/agent-browser-linux-x64"] = payload.pop(
            "bin/agent-browser-linux-musl-x64"
        )
    elif fault == "stale-skills":
        payload["upstream.json"] = b'{"version":"0.42.0"}'
    elif fault == "stale-version":
        payload["version.py"] = (
            b'__version__ = "0.42.0"\n__agent_browser_version__ = "0.42.0"'
        )
    elif fault == "wrong-metadata":
        metadata = b"Version: 0.42.0\nLicense-Expression: MIT\n"
    wheel = tmp_path / "test.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        for path, content in payload.items():
            archive.writestr(prefix + path, content)
        archive.writestr("agent_browser_cli-0.43.0.dist-info/METADATA", metadata)
        for license_name in (
            "LICENSE",
            "agent_browser/licenses/agent-browser-LICENSE",
            "agent_browser/licenses/LICENSE-axe-core.txt",
            "agent_browser/licenses/LICENSE-axe-core-THIRD-PARTY.txt",
        ):
            archive.writestr(
                "agent_browser_cli-0.43.0.dist-info/licenses/" + license_name, "license"
            )
    if fault is None:
        CHECK(wheel, "0.43.0", "linux-musl", "x86_64")
    else:
        with pytest.raises((KeyError, RuntimeError)):
            CHECK(wheel, "0.43.0", "linux-musl", "x86_64")
