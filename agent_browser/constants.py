"""
Shared constants for agent-browser Python wrapper.
"""

import platform

# Platform detection
SYSTEM = platform.system().lower()
MACHINE = platform.machine().lower()

# Normalize machine architecture
if MACHINE in ("amd64", "x86_64", "x64"):
    MACHINE = "x86_64"
elif MACHINE in ("arm64", "aarch64", "armv8"):
    MACHINE = "arm64"

# Normalize system names
if SYSTEM.startswith("darwin"):
    SYSTEM = "darwin"
elif SYSTEM.startswith("linux"):
    SYSTEM = "linux"
elif SYSTEM.startswith("win"):
    SYSTEM = "windows"

# GitHub release binary naming convention
GITHUB_REPO = "vercel-labs/agent-browser"


def get_binary_name(system: str = SYSTEM, machine: str = MACHINE) -> str:
    """Get the platform-specific binary name as used in GitHub releases."""
    arch_map = {"x86_64": "x64", "arm64": "arm64"}
    arch_key = arch_map.get(machine, machine)

    if system == "windows":
        return f"agent-browser-win32-{arch_key}.exe"
    return f"agent-browser-{system}-{arch_key}"


def get_binary_download_url(
    version: str,
    system: str = SYSTEM,
    machine: str = MACHINE,
) -> str:
    """Get the GitHub release download URL for the Rust binary."""
    name = get_binary_name(system, machine)
    return f"https://github.com/{GITHUB_REPO}/releases/download/v{version}/{name}"


# Wheel platform tags for each target
WHEEL_PLATFORM_TAGS = {
    ("darwin", "arm64"): "macosx_11_0_arm64",
    ("darwin", "x86_64"): "macosx_10_9_x86_64",
    ("linux", "x86_64"): "manylinux_2_17_x86_64.manylinux2014_x86_64",
    ("linux", "arm64"): "manylinux_2_17_aarch64.manylinux2014_aarch64",
    ("windows", "x86_64"): "win_amd64",
}

# All supported build targets
BUILD_TARGETS = list(WHEEL_PLATFORM_TAGS.keys())
