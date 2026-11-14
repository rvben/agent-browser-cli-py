"""Setup script with custom build steps for agent-browser wrapper."""

import hashlib
import json
import os
import re
import runpy
import shutil

from setuptools import find_packages, setup

# bdist_wheel is built into setuptools >= 70.1
from setuptools.command.bdist_wheel import bdist_wheel
from setuptools.command.build_py import build_py
from setuptools.command.sdist import sdist

# Execute the dependency-free constants file without importing the package.
# Build isolation must not import agent_browser or depend on its installed version.
_CONSTANTS = runpy.run_path(
    os.path.join(os.path.dirname(__file__), "agent_browser", "constants.py")
)
_WHEEL_PLATFORM_TAGS = _CONSTANTS["WHEEL_PLATFORM_TAGS"]


def _detect_platform():
    return _CONSTANTS["SYSTEM"], _CONSTANTS["MACHINE"]


def _target_platform():
    default_system, default_machine = _detect_platform()
    return (
        os.environ.get("TARGET_SYSTEM") or default_system,
        os.environ.get("TARGET_MACHINE") or default_machine,
    )


def get_platform_tag():
    """Get the wheel platform tag from TARGET_SYSTEM/TARGET_MACHINE env vars."""
    system, machine = _target_platform()
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
            if not os.path.isfile(
                os.path.join(
                    bin_dir, _CONSTANTS["get_binary_name"](*_target_platform())
                )
            ):
                raise RuntimeError(
                    f"CLI binary not found in {bin_dir}. "
                    "Run 'make download-binary' first."
                )

            required = [
                "upstream.json",
                "skill-data/core/SKILL.md",
                "licenses/agent-browser-LICENSE",
                "licenses/LICENSE-axe-core.txt",
                "licenses/LICENSE-axe-core-THIRD-PARTY.txt",
            ]
            for resource in required:
                if not os.path.isfile(os.path.join("agent_browser", resource)):
                    raise RuntimeError(
                        f"Missing upstream resource {resource}. Run 'make download-assets' first."
                    )

            with open("agent_browser/upstream.json") as f:
                upstream = json.load(f)
            if upstream["version"] != re.sub(r"\.post\d+$", "", version):
                raise RuntimeError("Runtime assets do not match the package version")
            if not upstream.get("files") or not upstream.get("binaries"):
                raise RuntimeError(
                    "Runtime provenance is missing checksums. Run 'make download-assets' first."
                )
            for name, digest in upstream["files"].items():
                with open(os.path.join("agent_browser", name), "rb") as f:
                    if hashlib.sha256(f.read()).hexdigest() != digest:
                        raise RuntimeError(
                            f"Runtime resource checksum mismatch: {name}"
                        )
            binary_name = _CONSTANTS["get_binary_name"](*_target_platform())
            with open(os.path.join(bin_dir, binary_name), "rb") as f:
                if (
                    "sha256:" + hashlib.sha256(f.read()).hexdigest()
                    != upstream["binaries"][binary_name]
                ):
                    raise RuntimeError(f"Binary checksum mismatch: {binary_name}")

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
                "skill-data/**/*",
                "skills/**/*",
                "licenses/*",
                "upstream.json",
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
