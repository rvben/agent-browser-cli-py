"""Behaviour of the shell steps that decide what gets released.

These steps run only when a release is under way, so nothing else exercises
them and a defect in one surfaces as a broken publish rather than as a red
commit. Each test pulls the step's script verbatim out of the workflow YAML
and runs it, so what is asserted here is the code that will run in CI. The
only substitution is the endpoint URL, which lets a case choose the HTTP
response a registry gives back.
"""

import http.server
import json
import os
import subprocess
import tempfile
import threading
from pathlib import Path

import pytest
import yaml

WORKFLOWS = Path(__file__).resolve().parent.parent / ".github" / "workflows"

PYPI_URL = "https://pypi.org/pypi/agent-browser-cli/json"
NPM_URL = "https://registry.npmjs.org/agent-browser/latest"

# A port nothing listens on, to stand in for a registry that cannot be reached.
UNREACHABLE = "http://127.0.0.1:1/unreachable"

ROUTES = {
    "/pypi": (200, "application/json", {"info": {"version": "1.2.3.post4"}}),
    "/npm": (200, "application/json", {"version": "1.2.3"}),
    "/unusable": (200, "application/json", {"info": {"version": "not-a-version"}}),
    "/notfound": (404, "application/json", {"message": "Not Found"}),
}


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/html":
            status, ctype, body = 200, "text/html", b"<html>proxy error</html>"
        elif self.path == "/unavailable":
            status, ctype, body = 503, "text/plain", b"unavailable"
        else:
            status, ctype, payload = ROUTES.get(
                self.path, (404, "text/plain", {"message": "no route"})
            )
            body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        """Keep the test output free of one access line per request."""


@pytest.fixture(scope="session")
def registry():
    """A stand-in registry, so no test result depends on the network."""
    server = http.server.HTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def step_script(workflow, job, step_id):
    document = yaml.safe_load((WORKFLOWS / workflow).read_text())
    for step in document["jobs"][job]["steps"]:
        if step.get("id") == step_id:
            return step["run"]
    raise AssertionError(f"{workflow} has no step with id {step_id!r}")


def run_step(script, env=None, replace=None):
    """Run a step's script and return its exit code and the outputs it set."""
    if replace is not None:
        original, substitute = replace
        assert original in script, f"{original} is no longer in this step"
        script = script.replace(original, substitute)
    with tempfile.TemporaryDirectory() as workspace:
        output = Path(workspace) / "github_output"
        output.touch()
        completed = subprocess.run(
            ["bash", "-c", script],
            capture_output=True,
            text=True,
            check=False,
            env={**os.environ, **(env or {}), "GITHUB_OUTPUT": str(output)},
        )
        written = dict(
            line.strip().split("=", 1)
            for line in output.read_text().splitlines()
            if "=" in line
        )
    return completed.returncode, written


# A registry that answers 404 is the one case that means "this project has no
# releases". Every other unhappy answer means the question went unanswered, and
# reporting a version for it would let an unreachable index read as an empty
# one, which makes every upstream version look unreleased.
@pytest.mark.parametrize(
    ("route", "exit_code", "version"),
    [
        ("/pypi", 0, "1.2.3"),
        ("/notfound", 0, "0.0.0"),
        ("/unavailable", 1, None),
        ("/html", 1, None),
        ("/unusable", 1, None),
        (None, 1, None),
    ],
    ids=[
        "a published version has its post suffix dropped",
        "404 is the only answer meaning nothing is published",
        "a 503 is not a version",
        "a body that is not JSON is not a version",
        "a version that is not X.Y.Z is refused",
        "an unreachable index is not a version",
    ],
)
def test_pypi_read(registry, route, exit_code, version):
    script = step_script("check-version.yml", "check", "current")
    target = UNREACHABLE if route is None else registry + route
    code, outputs = run_step(script, replace=(PYPI_URL, target))
    assert code == exit_code
    assert outputs.get("version") == version


# The npm read has no equivalent of the 404 case: an upstream package that has
# gone missing is an error, never a version to release against.
@pytest.mark.parametrize(
    ("route", "exit_code", "version"),
    [
        ("/npm", 0, "1.2.3"),
        ("/notfound", 1, None),
        ("/unavailable", 1, None),
        ("/html", 1, None),
        (None, 1, None),
    ],
    ids=[
        "the dist-tag version is read",
        "a missing upstream package is an error",
        "a 503 is not a version",
        "a body that is not JSON is not a version",
        "an unreachable registry is not a version",
    ],
)
def test_npm_read(registry, route, exit_code, version):
    script = step_script("check-version.yml", "check", "latest")
    target = UNREACHABLE if route is None else registry + route
    code, outputs = run_step(script, replace=(NPM_URL, target))
    assert code == exit_code
    assert outputs.get("version") == version


# The version a release builds comes from an input when the release workflow is
# called, and from the tag when one is pushed. Both paths feed the wheel
# filenames, so a version that parses wrong publishes under a name nobody asked
# for. INPUT_VERSION is always set by the step's env block, to the empty string
# when there is no input.
@pytest.mark.parametrize(
    ("input_version", "ref", "exit_code", "package", "upstream"),
    [
        ("0.34.0", "", 0, "0.34.0", "0.34.0"),
        ("0.20.0.post1", "", 0, "0.20.0.post1", "0.20.0"),
        ("", "refs/tags/v0.34.0", 0, "0.34.0", "0.34.0"),
        ("", "refs/tags/v0.20.0.post1", 0, "0.20.0.post1", "0.20.0"),
        ("1.2", "", 1, None, None),
        ("v1.2.3", "", 1, None, None),
        ("1.2.3rc1", "", 1, None, None),
        ("", "refs/heads/main", 1, None, None),
    ],
    ids=[
        "an input version is used as given",
        "a post release keeps its suffix but builds the plain upstream",
        "a tag supplies the version when there is no input",
        "a post release tag is split the same way",
        "an incomplete version is refused",
        "a version still carrying its tag prefix is refused",
        "a prerelease is refused",
        "a ref that is not a version tag is refused",
    ],
)
def test_parse_version(input_version, ref, exit_code, package, upstream):
    script = step_script("build-and-publish.yml", "build", "version")
    code, outputs = run_step(
        script, env={"INPUT_VERSION": input_version, "GITHUB_REF": ref}
    )
    assert code == exit_code
    assert outputs.get("package_version") == package
    assert outputs.get("upstream_version") == upstream
