"""Smoke-test an installed wheel, including runtime files absent from bare binaries."""

import json
import subprocess
from pathlib import Path

import agent_browser


def run(*args):
    return subprocess.check_output(
        ["agent-browser", *args], encoding="utf-8", timeout=30
    )


version = agent_browser.__version__.split(".post")[0]
assert run("--version").strip() == f"agent-browser {version}"
assert run("skills", "get", "core").strip()
assert run("skills", "get", "core", "--ref", "commands").strip()
assert "core" in run("skills", "list")
result = json.loads(run("mcp", "call", "agent_browser_tools_profiles", "{}"))
assert not result.get("isError"), result
package = Path(agent_browser.__file__).parent
assert json.loads((package / "upstream.json").read_text())["version"] == version
for name in (
    "agent-browser-LICENSE",
    "LICENSE-axe-core.txt",
    "LICENSE-axe-core-THIRD-PARTY.txt",
):
    assert (package / "licenses" / name).stat().st_size > 0
print(f"Installed {version}: skills, references, MCP, and licenses verified")
