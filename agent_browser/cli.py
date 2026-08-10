"""
CLI entry point for agent-browser Python wrapper.

Proxies all commands to the bundled Rust CLI binary.
"""

import subprocess
import sys

from . import get_cli_binary_path, is_cli_installed


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

    try:
        # A proxy passes the child's exit code through, so a non-zero status is
        # a result to forward rather than an error to raise on.
        result = subprocess.run(
            [cli_path] + sys.argv[1:],
            stderr=subprocess.PIPE,
            check=False,
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
            elif "Executable doesn't exist" in stderr or "Chrome not found" in stderr:
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
