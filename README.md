# agent-browser-cli

Install [agent-browser](https://agent-browser.dev/) with pip or uv. The wheel includes the upstream native Rust CLI, its matching agent skills, and license notices. No Node.js or npm installation is required.

```bash
pip install --upgrade agent-browser-cli
# or run without a permanent install
uvx agent-browser-cli --version
```

Download Chrome for Testing once:

```bash
agent-browser install
# Linux: also install the browser's system libraries
agent-browser install --with-deps
```

## Use it

```bash
agent-browser open https://example.com
agent-browser snapshot -i
agent-browser click @e1
agent-browser close
```

All commands and flags go directly to the bundled CLI. `agent-browser-cli` is an alias for `agent-browser`. For the full command reference, run `agent-browser --help` or visit the [upstream docs](https://agent-browser.dev/).

For an AI agent, start with the instructions shipped with its installed version:

```bash
agent-browser skills get core
agent-browser skills get core --ref commands
agent-browser skills list
```

The built-in MCP server is available with `agent-browser mcp`:

```json
{
  "mcpServers": {
    "agent-browser": {
      "command": "agent-browser",
      "args": ["mcp"]
    }
  }
}
```

Use pip or uv to upgrade this distribution, so the binary and skills stay at the same version. Upstream's `upgrade` command manages upstream installation methods.

## Supported platforms

| Platform | Architecture | Minimum runtime |
| --- | --- | --- |
| macOS | ARM64 | macOS 11 |
| macOS | x86_64 | macOS 10.12 |
| Linux (glibc) | x86_64, ARM64 | glibc 2.28 |
| Linux (musl, including Alpine) | x86_64, ARM64 | musl 1.2 |
| Windows | x86_64 | Upstream Windows support |

These requirements describe the CLI binary. Python requires 3.10 or later, and Chrome may require a newer operating system. Alpine wheels supply the CLI; installing a compatible browser and its libraries is a separate step. A running browser can also be attached over CDP.

## Upstream tracking

The updater checks npm every six hours and publishes platform wheels for a newer stable upstream release. The package version follows upstream; `.postN` identifies a packaging-only correction. Upstream 0.20.0 removed the Node.js/Playwright daemon in favor of native Rust, which this package bundles directly.

At build time, binaries come from the matching GitHub release and are checked against its SHA-256 asset digests. Skills, references, templates, and license notices come from the exact npm version and are checked against its SHA-512 archive integrity. Build scripts do not execute npm scripts. Installed packages record the runtime archive version, source, archive integrity, binary digests, and runtime-file checksums in `agent_browser/upstream.json`.

## Development

```bash
uv sync --locked
make lint test
make wheel TARGET_SYSTEM=darwin TARGET_MACHINE=arm64
make wheels check-wheels                   # all seven platforms
make rehearse-release                     # build current upstream; preserve version.py
```

`make wheels` downloads all version-matched inputs. For individual builds, `make wheel` downloads the binary and runtime data for the selected target. Use `TARGET_SYSTEM=linux-musl` for Alpine. Override `PACKAGE_VERSION` and `AGENT_BROWSER_VERSION` together when building a packaging post-release.

`make verify` installs the local wheel in an isolated environment and checks version, skills, MCP, and notices. `make verify-e2e` is the Linux CI check: it also installs Chrome and exercises navigation, snapshots, input, and screenshots against a local page. CI checks wheel contents, binary architecture, and glibc/macOS requirements before publication and rehearses release builds daily.

## Licenses

The Python wrapper is [MIT licensed](LICENSE). The bundled agent-browser CLI and runtime skills are [Apache-2.0 licensed](https://github.com/vercel-labs/agent-browser/blob/main/LICENSE). Upstream also includes axe-core under MPL-2.0 and third-party MIT/ISC notices. Wheels include these upstream license texts under `agent_browser/licenses/`, with matching source information in `agent_browser/upstream.json`.
