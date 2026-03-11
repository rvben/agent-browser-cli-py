# agent-browser-cli

Install [agent-browser](https://agent-browser.dev/) via pip/uv — no npm required. Node.js is managed automatically.

## Installation

```bash
pip install agent-browser-cli
# or
uv pip install agent-browser-cli
```

## First run

On first invocation, Node.js v22 is automatically downloaded to `~/.cache/agent-browser-py/` (one-time, ~30MB):

```bash
agent-browser --version
# Downloading Node.js v22.14.0 (one-time setup)...
# Done.
# 0.17.1
```

Then install the browser (Chromium via Playwright):

```bash
agent-browser install
```

On Linux you may need system dependencies:

```bash
agent-browser install --with-deps
```

## Usage

```bash
agent-browser open example.com
agent-browser snapshot
agent-browser click @e1
```

All commands are proxied directly to the bundled Rust CLI binary.

## How it works

The wheel bundles:

1. **Rust CLI binary** (~15MB) — from [GitHub releases](https://github.com/vercel-labs/agent-browser/releases)
2. **Node.js daemon code** (~18MB) — from the [npm registry](https://www.npmjs.com/package/agent-browser) with all JS dependencies

Downloaded at runtime (cached in `~/.cache/agent-browser-py/`):

3. **Node.js runtime** (~30MB) — from [nodejs.org](https://nodejs.org/), downloaded on first use
4. **Chromium** — via `agent-browser install` (Playwright CDN)

No npm installation is required on your system. Node.js is downloaded and managed automatically.

## Supported platforms

- macOS (arm64, x86_64)
- Linux (x86_64, aarch64)
- Windows (x86_64)

## Building from source

```bash
make wheel TARGET_SYSTEM=darwin TARGET_MACHINE=arm64  # Single platform
make wheels                                            # All 5 platforms
make verify                                            # Install and verify
```

## License

MIT — This wrapper packages upstream software under their respective licenses:
- agent-browser: [MIT](https://github.com/vercel-labs/agent-browser/blob/main/LICENSE)
- Node.js: [MIT](https://github.com/nodejs/node/blob/main/LICENSE)
