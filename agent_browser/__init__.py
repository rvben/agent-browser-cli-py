"""
agent-browser - Python wrapper for the agent-browser CLI.

Bundles the Rust CLI binary and Node.js daemon code. Node.js runtime
is downloaded on first use to ~/.cache/agent-browser-py/.
"""

import os
import logging

from .version import __version__ as __version__
from .constants import SYSTEM as SYSTEM, MACHINE as MACHINE

logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
NODE_MODULES_DIR = os.path.join(PACKAGE_DIR, "node_modules")
BIN_DIR = os.path.join(PACKAGE_DIR, "bin")


def get_cli_binary_path() -> str:
    """Get the path to the bundled Rust CLI binary."""
    from .constants import get_binary_name

    return os.path.join(BIN_DIR, get_binary_name())


def is_cli_installed() -> bool:
    """Check if the bundled Rust CLI binary exists."""
    path = get_cli_binary_path()
    return os.path.exists(path) and (SYSTEM == "windows" or os.access(path, os.X_OK))
