#!/usr/bin/env python3
"""
Build-time script to download components bundled in the wheel:
  1. Rust CLI binary from GitHub releases
  2. agent-browser npm package (daemon code + JS dependencies)

Node.js is NOT bundled — it's downloaded on first run to ~/.cache/.
This script is called by the Makefile before building the wheel.
"""

import os
import re
import sys
import shutil
import tarfile
import tempfile
import json
import urllib.request
import urllib.error


def download_file(url: str, dest: str) -> None:
    """Download a file from a URL to a local path."""
    print(f"  Downloading: {url}")
    try:
        urllib.request.urlretrieve(url, dest)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Failed to download {url}: HTTP {e.code}") from e


def download_cli_binary(version: str, system: str, machine: str) -> None:
    """Download the Rust CLI binary from GitHub releases."""
    from agent_browser.constants import get_binary_name, get_binary_download_url

    bin_dir = os.path.join("agent_browser", "bin")
    os.makedirs(bin_dir, exist_ok=True)

    binary_name = get_binary_name(system, machine)
    url = get_binary_download_url(version, system, machine)
    dest = os.path.join(bin_dir, binary_name)

    print(f"\n[1/2] Downloading CLI binary: {binary_name}")
    download_file(url, dest)

    if system != "windows":
        os.chmod(dest, 0o755)

    print(f"  Saved to: {dest}")


def download_npm_package(version: str) -> None:
    """Download the agent-browser npm package and its dependencies."""
    from agent_browser.constants import get_npm_tarball_url

    node_modules_dir = os.path.join("agent_browser", "node_modules")

    if os.path.exists(node_modules_dir):
        shutil.rmtree(node_modules_dir)
    os.makedirs(node_modules_dir, exist_ok=True)

    url = get_npm_tarball_url(version)

    print(f"\n[2/2] Downloading npm package v{version}")

    with tempfile.NamedTemporaryFile(suffix=".tgz", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        download_file(url, tmp_path)

        with tempfile.TemporaryDirectory() as temp_dir:
            with tarfile.open(tmp_path, "r:gz") as tar:
                if sys.version_info >= (3, 12):
                    tar.extractall(temp_dir, filter="data")
                else:
                    tar.extractall(temp_dir)

            package_dir = os.path.join(temp_dir, "package")
            dest_dir = os.path.join(node_modules_dir, "agent-browser")
            shutil.copytree(package_dir, dest_dir)

        print(f"  Extracted to: {dest_dir}")
    finally:
        os.unlink(tmp_path)

    # Install JS dependencies
    install_npm_dependencies(node_modules_dir)

    # Strip unnecessary files
    strip_node_modules(node_modules_dir)


def strip_node_modules(node_modules_dir: str) -> None:
    """Remove unnecessary files from node_modules to reduce package size."""
    strip_extensions = {
        ".map",
        ".md",
        ".markdown",
        ".txt",
        ".yml",
        ".yaml",
        ".eslintrc",
        ".prettierrc",
        ".editorconfig",
        ".npmignore",
        ".gitignore",
        ".travis.yml",
    }
    strip_names = {
        "CHANGELOG.md",
        "CHANGES.md",
        "HISTORY.md",
        "README.md",
        "readme.md",
        "README",
        "Makefile",
        "Gruntfile.js",
        "Gulpfile.js",
        ".eslintrc.json",
        ".prettierrc.json",
        "tsconfig.json",
        "tslint.json",
        "jest.config.js",
        "karma.conf.js",
        ".npmrc",
    }
    strip_dirs = {
        "test",
        "tests",
        "__tests__",
        "docs",
        "doc",
        "example",
        "examples",
        ".github",
        "benchmark",
        "benchmarks",
        "coverage",
    }

    removed_bytes = 0
    for root, dirs, files in os.walk(node_modules_dir, topdown=True):
        for d in list(dirs):
            if d in strip_dirs:
                dir_path = os.path.join(root, d)
                size = sum(
                    os.path.getsize(os.path.join(dp, f))
                    for dp, _, fn in os.walk(dir_path)
                    for f in fn
                )
                shutil.rmtree(dir_path)
                dirs.remove(d)
                removed_bytes += size

        for f in files:
            file_path = os.path.join(root, f)
            _, ext = os.path.splitext(f)
            if ext in strip_extensions or f in strip_names:
                if f.endswith(".d.ts") or f.upper().startswith("LICENSE"):
                    continue
                removed_bytes += os.path.getsize(file_path)
                os.unlink(file_path)

    size_mb = sum(
        os.path.getsize(os.path.join(dp, f))
        for dp, _, fn in os.walk(node_modules_dir)
        for f in fn
    ) / (1024 * 1024)
    print(
        f"  Stripped node_modules to {size_mb:.1f}MB (removed {removed_bytes / (1024 * 1024):.1f}MB)"
    )


def install_npm_dependencies(node_modules_dir: str) -> None:
    """Install npm dependencies by downloading tarballs from the registry."""
    package_json_path = os.path.join(node_modules_dir, "agent-browser", "package.json")
    with open(package_json_path) as f:
        package_data = json.load(f)

    dependencies = package_data.get("dependencies", {})
    if not dependencies:
        return

    print(f"\n  Installing {len(dependencies)} npm dependencies...")

    for dep_name, dep_version_spec in dependencies.items():
        install_npm_dependency(node_modules_dir, dep_name, dep_version_spec)


def parse_semver(version: str) -> tuple[int, int, int]:
    """Parse a semver string into (major, minor, patch)."""
    match = re.match(r"(\d+)\.(\d+)\.(\d+)", version)
    if not match:
        return (0, 0, 0)
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


def is_prerelease(version: str) -> bool:
    """Check if a version string contains a prerelease tag."""
    match = re.match(r"\d+\.\d+\.\d+(.*)", version)
    if not match:
        return False
    suffix = match.group(1)
    return bool(suffix and suffix.startswith("-"))


def resolve_version(version_spec: str, available_versions: list[str]) -> str | None:
    """Resolve a npm version spec to the best matching version.

    Supports: ^x.y.z, ~x.y.z, x.y.z (exact), >=x.y.z, x (major-only).
    """
    spec = version_spec.strip()

    # Parse all valid semver versions, skipping prereleases
    candidates = []
    for v in available_versions:
        if is_prerelease(v):
            continue
        parsed = parse_semver(v)
        if parsed != (0, 0, 0) or v == "0.0.0":
            candidates.append((parsed, v))

    if not candidates:
        return None

    # Exact version
    if re.match(r"^\d+\.\d+\.\d+$", spec):
        return spec if spec in available_versions else None

    # ^x.y.z — compatible with major (>=x.y.z, <next-major)
    m = re.match(r"^\^(\d+\.\d+\.\d+)$", spec)
    if m:
        floor = parse_semver(m.group(1))
        ceiling_major = floor[0] + 1 if floor[0] > 0 else 0
        matching = [
            (p, v) for p, v in candidates
            if p >= floor and (floor[0] == 0 or p[0] < ceiling_major)
        ]
        if not matching:
            return None
        return max(matching, key=lambda x: x[0])[1]

    # ~x.y.z — compatible with minor (>=x.y.z, <x.next-minor.0)
    m = re.match(r"^~(\d+\.\d+\.\d+)$", spec)
    if m:
        floor = parse_semver(m.group(1))
        matching = [
            (p, v) for p, v in candidates
            if p >= floor and p[0] == floor[0] and p[1] == floor[1]
        ]
        if not matching:
            return None
        return max(matching, key=lambda x: x[0])[1]

    # >=x.y.z
    m = re.match(r"^>=(\d+\.\d+\.\d+)$", spec)
    if m:
        floor = parse_semver(m.group(1))
        matching = [(p, v) for p, v in candidates if p >= floor]
        if not matching:
            return None
        return max(matching, key=lambda x: x[0])[1]

    # Fallback: return the latest version
    return max(candidates, key=lambda x: x[0])[1]


def install_npm_dependency(node_modules_dir: str, name: str, version_spec: str) -> None:
    """Download and extract a single npm dependency from the registry."""
    # Skip if already installed (flat node_modules, first version wins)
    dest_dir = os.path.join(node_modules_dir, name)
    if os.path.exists(dest_dir):
        return

    # Handle scoped packages (@scope/name) in registry URL
    if name.startswith("@"):
        registry_url = f"https://registry.npmjs.org/{name.replace('/', '%2F')}"
    else:
        registry_url = f"https://registry.npmjs.org/{name}"

    try:
        with urllib.request.urlopen(registry_url) as resp:
            registry_data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        print(f"  Warning: Could not fetch registry data for {name}: HTTP {e.code}")
        return

    available_versions = list(registry_data.get("versions", {}).keys())
    version = resolve_version(version_spec, available_versions)
    if not version:
        # Fall back to latest
        version = registry_data.get("dist-tags", {}).get("latest")
    if not version:
        print(f"  Warning: No matching version found for {name}@{version_spec}")
        return

    version_data = registry_data["versions"].get(version)
    if not version_data:
        print(f"  Warning: Version {version} not found in registry for {name}")
        return

    tarball_url = version_data["dist"]["tarball"]

    print(f"  {name}@{version}")

    with tempfile.NamedTemporaryFile(suffix=".tgz", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        urllib.request.urlretrieve(tarball_url, tmp_path)

        os.makedirs(os.path.dirname(dest_dir), exist_ok=True)

        with tempfile.TemporaryDirectory() as temp_dir:
            with tarfile.open(tmp_path, "r:gz") as tar:
                if sys.version_info >= (3, 12):
                    tar.extractall(temp_dir, filter="data")
                else:
                    tar.extractall(temp_dir)

            package_dir = os.path.join(temp_dir, "package")
            if os.path.exists(package_dir):
                shutil.copytree(package_dir, dest_dir)

        # Recursively install sub-dependencies
        sub_package_json = os.path.join(dest_dir, "package.json")
        if os.path.exists(sub_package_json):
            with open(sub_package_json) as f:
                sub_data = json.load(f)
            sub_deps = sub_data.get("dependencies", {})
            for sub_name, sub_version in sub_deps.items():
                install_npm_dependency(node_modules_dir, sub_name, sub_version)

    finally:
        os.unlink(tmp_path)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Download agent-browser components")
    parser.add_argument(
        "--npm-only", action="store_true", help="Only download npm package"
    )
    parser.add_argument(
        "--binary-only", action="store_true", help="Only download CLI binary"
    )
    args = parser.parse_args()

    version = os.environ.get("AGENT_BROWSER_VERSION")
    if not version:
        print("ERROR: AGENT_BROWSER_VERSION environment variable not set")
        sys.exit(1)

    target_system = os.environ.get("TARGET_SYSTEM")
    target_machine = os.environ.get("TARGET_MACHINE")

    sys.path.insert(0, os.getcwd())
    from agent_browser.constants import SYSTEM, MACHINE

    system = target_system or SYSTEM
    machine = target_machine or MACHINE

    if args.npm_only:
        print(f"Downloading npm package for agent-browser v{version}")
        download_npm_package(version)
    elif args.binary_only:
        print(f"Downloading CLI binary for {system}-{machine}")
        download_cli_binary(version, system, machine)
    else:
        print(f"Downloading all components for agent-browser v{version}")
        print(f"Platform: {system}-{machine}")
        download_cli_binary(version, system, machine)
        download_npm_package(version)

    print("\nDone.")


if __name__ == "__main__":
    main()
