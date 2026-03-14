#!/usr/bin/env python3
"""
Generate version.py at build time from the package version.

Called by `make wheels` before building. Version comes from:
  1. CLI argument: python3 update_version.py 0.20.0
  2. Environment: PACKAGE_VERSION=0.20.0 python3 update_version.py
  3. Fallback: reads current version.py (for local dev)

For post-releases (0.20.0.post1), the upstream version is extracted
by stripping the .postN suffix.
"""

import os
import re
import sys


def extract_upstream_version(package_version: str) -> str:
    """Strip .postN suffix to get the upstream agent-browser version."""
    return re.sub(r"\.post\d+$", "", package_version)


def read_current_version() -> str:
    """Read the current version from version.py as fallback."""
    version_file = os.path.join("agent_browser", "version.py")
    with open(version_file) as f:
        match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', f.read())
        if match:
            return match.group(1)
    return "0.0.0"


def main():
    if len(sys.argv) > 1:
        package_version = sys.argv[1]
    elif "PACKAGE_VERSION" in os.environ:
        package_version = os.environ["PACKAGE_VERSION"]
    else:
        package_version = read_current_version()
        print(f"No version specified, using current: {package_version}")
        return

    package_version = package_version.lstrip("v")
    upstream_version = extract_upstream_version(package_version)

    content = f'''"""Version information for agent-browser Python wrapper."""

__version__ = "{package_version}"
__agent_browser_version__ = "{upstream_version}"
'''

    version_file = os.path.join("agent_browser", "version.py")
    with open(version_file, "w") as f:
        f.write(content)

    print(f"Updated version.py: package={package_version}, upstream={upstream_version}")


if __name__ == "__main__":
    main()
