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

# Path to bundled playwright-core CLI (relative to node_modules)
_PLAYWRIGHT_CLI = os.path.join(NODE_MODULES_DIR, "playwright-core", "cli.js")


def _is_install_command() -> bool:
    """Check if the user is running 'agent-browser install [--with-deps]'."""
    args = sys.argv[1:]
    return len(args) >= 1 and args[0] == "install"


def _run_install(node_path: str) -> int:
    """Install Chromium via bundled playwright-core, bypassing npx/npm."""
    args = sys.argv[2:]  # everything after 'install'

    cmd = [node_path, _PLAYWRIGHT_CLI, "install", "chromium"] + args
    try:
        return subprocess.call(cmd)
    except FileNotFoundError:
        print(f"Error: Could not execute {cmd[0]}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


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

    # Handle 'install' directly via bundled playwright-core to avoid npm
    if _is_install_command():
        return _run_install(node_path)

    env = os.environ.copy()

    # Point the Rust CLI to the cached Node.js so it can start the daemon
    node_dir = os.path.dirname(node_path)
    env["PATH"] = node_dir + os.pathsep + env.get("PATH", "")

    # Tell the daemon where to find its node_modules
    env["NODE_PATH"] = NODE_MODULES_DIR

    # Point the Rust CLI to the bundled daemon code
    env["AGENT_BROWSER_HOME"] = os.path.join(NODE_MODULES_DIR, "agent-browser")

    # Prevent npx from hitting the npm registry — all deps are bundled
    env["NPM_CONFIG_OFFLINE"] = "true"

    try:
        result = subprocess.run(
            [cli_path] + sys.argv[1:],
            env=env,
            stderr=subprocess.PIPE,
        )
        stderr = result.stderr.decode("utf-8", errors="replace")
        if stderr:
            print(stderr, end="", file=sys.stderr)
        if result.returncode != 0:
            if "error while loading shared libraries" in stderr:
                print(
                    "\nHint: Chromium is missing system dependencies. Run:\n"
                    "  agent-browser install --with-deps",
                    file=sys.stderr,
                )
            elif "Executable doesn't exist" in stderr:
                print(
                    "\nHint: Chromium is not installed. Run:\n"
                    "  agent-browser install",
                    file=sys.stderr,
                )
        return result.returncode
    except FileNotFoundError:
        print(f"Error: Could not execute {cli_path}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


def entry_point():
    sys.exit(main())


if __name__ == "__main__":
    sys.exit(main())
