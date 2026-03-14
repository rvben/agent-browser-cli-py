# agent-browser-cli

Install [agent-browser](https://agent-browser.dev/) via pip/uv — no npm required.

## Installation

```bash
pip install agent-browser-cli
# or
uvx agent-browser-cli --version
```

## Setup

Install the browser (Chromium):

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
agent-browser close
```

All commands are proxied directly to the bundled Rust CLI binary.

## How it works

The wheel bundles the **platform-specific Rust CLI binary** (~6MB) from [GitHub releases](https://github.com/vercel-labs/agent-browser/releases). That's it — agent-browser 0.20.0+ is fully native Rust with zero npm dependencies.

On first use, run `agent-browser install` to download Chromium.

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
