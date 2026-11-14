"""Validate the contents, versions and platform coverage of release wheels."""

import ast
import hashlib
import json
import runpy
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONSTANTS = runpy.run_path(str(ROOT / "agent_browser/constants.py"))
CHECK_BINARY = runpy.run_path(str(ROOT / "scripts/binary_compatibility.py"))[
    "check_binary"
]


def check_wheel(path: Path, version: str, system: str, machine: str) -> None:
    with zipfile.ZipFile(path) as wheel:
        names = wheel.namelist()
        prefix = next(
            n.removesuffix("__init__.py")
            for n in names
            if n.endswith("agent_browser/__init__.py")
        )
        expected = CONSTANTS["get_binary_name"](system, machine)
        binaries = [n for n in names if n.startswith(prefix + "bin/")]
        if binaries != [prefix + "bin/" + expected]:
            raise RuntimeError(f"{path.name}: unexpected binaries {binaries}")
        required = [
            "upstream.json",
            "skill-data/core/SKILL.md",
            "skill-data/core/references/commands.md",
            "skills/agent-browser/SKILL.md",
            "licenses/agent-browser-LICENSE",
            "licenses/LICENSE-axe-core.txt",
            "licenses/LICENSE-axe-core-THIRD-PARTY.txt",
        ]
        for resource in required:
            if not wheel.read(prefix + resource):
                raise RuntimeError(f"{path.name}: empty resource {resource}")
        upstream = version.split(".post")[0]
        provenance = json.loads(wheel.read(prefix + "upstream.json"))
        if provenance["version"] != upstream:
            raise RuntimeError(f"{path.name}: mismatched runtime assets")
        binary = wheel.read(prefix + "bin/" + expected)
        if (
            "sha256:" + hashlib.sha256(binary).hexdigest()
            != provenance["binaries"][expected]
        ):
            raise RuntimeError(f"{path.name}: binary checksum mismatch")
        CHECK_BINARY(binary, system, machine)
        for resource, digest in provenance["files"].items():
            if hashlib.sha256(wheel.read(prefix + resource)).hexdigest() != digest:
                raise RuntimeError(
                    f"{path.name}: runtime checksum mismatch for {resource}"
                )
        for license_name in (
            "LICENSE",
            "agent_browser/licenses/agent-browser-LICENSE",
            "agent_browser/licenses/LICENSE-axe-core.txt",
            "agent_browser/licenses/LICENSE-axe-core-THIRD-PARTY.txt",
        ):
            if not any(
                n.endswith(".dist-info/licenses/" + license_name) for n in names
            ):
                raise RuntimeError(
                    f"{path.name}: missing distribution license {license_name}"
                )
        assignments = {
            node.targets[0].id: ast.literal_eval(node.value)
            for node in ast.parse(wheel.read(prefix + "version.py")).body
            if isinstance(node, ast.Assign)
        }
        if (
            assignments.get("__version__") != version
            or assignments.get("__agent_browser_version__") != upstream
        ):
            raise RuntimeError(f"{path.name}: mismatched version.py")
        metadata = wheel.read(
            next(n for n in names if n.endswith(".dist-info/METADATA"))
        ).decode()
        if f"Version: {version}\n" not in metadata or "Apache-2.0" not in metadata:
            raise RuntimeError(f"{path.name}: incorrect distribution metadata")
    print(f"Verified {path.name}: binary, skills, licenses, versions")


def main():
    version = sys.argv[1]
    expected = {
        f"agent_browser_cli-{version}-py3-none-{tag}.whl": (system, machine)
        for (system, machine), tag in CONSTANTS["WHEEL_PLATFORM_TAGS"].items()
    }
    actual = {p.name for p in Path("dist").glob("*.whl")}
    if actual != set(expected):
        raise RuntimeError(
            f"Wheel set mismatch: missing {set(expected) - actual}, extra {actual - set(expected)}"
        )
    for name, (system, machine) in expected.items():
        check_wheel(Path("dist") / name, version, system, machine)


if __name__ == "__main__":
    main()
