"""
CLI entry point for agent-browser Python wrapper.

Proxies all commands to the bundled Rust CLI binary, with the environment
configured so the Rust binary can find the cached Node.js and bundled daemon code.
"""

import os
import sys
import subprocess

from . import (
    NODE_MODULES_DIR,
    get_cli_binary_path,
    is_cli_installed,
)
from .node_runtime import ensure_node


def main() -> int:
    if not is_cli_installed():
        print(
            "Error: agent-browser binary not found. "
            "The package may not have been built correctly.",
            file=sys.stderr,
        )
        print(
            "Please reinstall: uv pip install --force-reinstall agent-browser-cli",
            file=sys.stderr,
        )
        return 1

    cli_path = get_cli_binary_path()

    # Ensure Node.js is available (downloads on first run)
    try:
        node_path = ensure_node()
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    env = os.environ.copy()

    # Point the Rust CLI to the cached Node.js so it can start the daemon
    node_dir = os.path.dirname(node_path)
    env["PATH"] = node_dir + os.pathsep + env.get("PATH", "")

    # Tell the daemon where to find its node_modules
    env["NODE_PATH"] = NODE_MODULES_DIR

    # Prevent npx from hitting the npm registry — all deps are bundled
    env["NPM_CONFIG_OFFLINE"] = "true"

    try:
        return subprocess.call([cli_path] + sys.argv[1:], env=env)
    except FileNotFoundError:
        print(f"Error: Could not execute {cli_path}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


def entry_point():
    sys.exit(main())


if __name__ == "__main__":
    sys.exit(main())
