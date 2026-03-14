#!/usr/bin/env python
"""Setup script with custom build steps for agent-browser wrapper."""

import os
import platform
import re
import shutil
from setuptools import setup, find_packages
from setuptools.command.build_py import build_py
from setuptools.command.sdist import sdist

# bdist_wheel is built into setuptools >= 70.1
from setuptools.command.bdist_wheel import bdist_wheel

# Inline platform tag map — no imports from agent_browser needed
_WHEEL_PLATFORM_TAGS = {
    ("darwin", "arm64"): "macosx_11_0_arm64",
    ("darwin", "x86_64"): "macosx_10_9_x86_64",
    ("linux", "x86_64"): "manylinux_2_17_x86_64.manylinux2014_x86_64",
    ("linux", "arm64"): "manylinux_2_17_aarch64.manylinux2014_aarch64",
    ("windows", "x86_64"): "win_amd64",
}


def _detect_platform():
    """Detect normalized system/machine without importing agent_browser."""
    system = platform.system().lower()
    machine = platform.machine().lower()
    if system.startswith("darwin"):
        system = "darwin"
    elif system.startswith("linux"):
        system = "linux"
    elif system.startswith("win"):
        system = "windows"
    if machine in ("amd64", "x86_64", "x64"):
        machine = "x86_64"
    elif machine in ("arm64", "aarch64", "armv8"):
        machine = "arm64"
    return system, machine


def get_platform_tag():
    """Get the wheel platform tag from TARGET_SYSTEM/TARGET_MACHINE env vars."""
    default_system, default_machine = _detect_platform()
    system = os.environ.get("TARGET_SYSTEM", default_system)
    machine = os.environ.get("TARGET_MACHINE", default_machine)
    tag = _WHEEL_PLATFORM_TAGS.get((system, machine))
    if not tag:
        raise RuntimeError(
            f"No wheel platform tag for {system}-{machine}. "
            f"Supported: {list(_WHEEL_PLATFORM_TAGS.keys())}"
        )
    return tag


def read_long_description():
    with open("README.md", "r", encoding="utf-8") as fh:
        return fh.read()


def get_version():
    with open(os.path.join("agent_browser", "version.py"), "r") as f:
        content = f.read()
        match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', content)
        if match:
            return match.group(1)
        raise ValueError("Could not find __version__ in version.py")


class CustomBuildPy(build_py):
    """Validate that the CLI binary is downloaded before building.

    Skips validation for editable installs (development mode).
    """

    def run(self):
        version = get_version()
        print(f"Building agent-browser wrapper v{version}")

        # Skip validation for editable installs
        if not self.editable_mode:
            bin_dir = os.path.join("agent_browser", "bin")
            if not os.path.exists(bin_dir) or not os.listdir(bin_dir):
                raise RuntimeError(
                    f"CLI binary not found in {bin_dir}. "
                    "Run 'make download-binary' first."
                )

        build_py.run(self)


class CustomSdist(sdist):
    """Exclude platform-specific binaries from source distribution."""

    def make_release_tree(self, base_dir, files):
        sdist.make_release_tree(self, base_dir, files)

        bin_dir = os.path.join(base_dir, "agent_browser", "bin")
        if os.path.exists(bin_dir):
            print(f"Removing {bin_dir} from source distribution")
            shutil.rmtree(bin_dir)
            os.makedirs(bin_dir, exist_ok=True)


class PlatformBdistWheel(bdist_wheel):
    """Build a platform-specific wheel based on TARGET_SYSTEM/TARGET_MACHINE."""

    def finalize_options(self):
        bdist_wheel.finalize_options(self)
        self.root_is_pure = False

    def get_tag(self):
        return "py3", "none", get_platform_tag()


if __name__ == "__main__":
    setup(
        name="agent-browser-cli",
        version=get_version(),
        description="Python wrapper for agent-browser CLI — browser automation for AI agents, no npm required",
        long_description=read_long_description(),
        long_description_content_type="text/markdown",
        url="https://github.com/rvben/agent-browser-cli-py",
        author="Ruben J. Jongejan",
        author_email="ruben.jongejan@gmail.com",
        packages=find_packages(),
        package_data={
            "agent_browser": [
                "bin/*",
            ],
        },
        include_package_data=True,
        entry_points={
            "console_scripts": [
                "agent-browser=agent_browser.cli:entry_point",
                "agent-browser-cli=agent_browser.cli:entry_point",
            ],
        },
        python_requires=">=3.10",
        classifiers=[
            "Development Status :: 3 - Alpha",
            "Intended Audience :: Developers",
            "Programming Language :: Python :: 3",
            "Programming Language :: Python :: 3.10",
            "Programming Language :: Python :: 3.11",
            "Programming Language :: Python :: 3.12",
            "Programming Language :: Python :: 3.13",
        ],
        cmdclass={
            "build_py": CustomBuildPy,
            "sdist": CustomSdist,
            "bdist_wheel": PlatformBdistWheel,
        },
    )
