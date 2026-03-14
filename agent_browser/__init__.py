"""
agent-browser - Python wrapper for the agent-browser CLI.

Bundles the platform-specific Rust CLI binary for easy installation via pip/uvx.
"""

import os

from .version import __version__ as __version__
from .constants import SYSTEM as SYSTEM, MACHINE as MACHINE

PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
BIN_DIR = os.path.join(PACKAGE_DIR, "bin")


def get_cli_binary_path() -> str:
    """Get the path to the bundled Rust CLI binary."""
    from .constants import get_binary_name

    return os.path.join(BIN_DIR, get_binary_name())


def is_cli_installed() -> bool:
    """Check if the bundled Rust CLI binary exists."""
    path = get_cli_binary_path()
    return os.path.exists(path) and (SYSTEM == "windows" or os.access(path, os.X_OK))
