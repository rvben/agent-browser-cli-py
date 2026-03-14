#!/usr/bin/env python3
"""
Build-time script to download the platform-specific Rust CLI binary
from GitHub releases. Called by the Makefile before building the wheel.
"""

import os
import sys
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

    print(f"Downloading CLI binary: {binary_name}")
    download_file(url, dest)

    if system != "windows":
        os.chmod(dest, 0o755)

    print(f"  Saved to: {dest}")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Download agent-browser binary")
    parser.parse_args()

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

    print(f"Downloading agent-browser v{version} for {system}-{machine}")
    download_cli_binary(version, system, machine)
    print("\nDone.")


if __name__ == "__main__":
    main()
