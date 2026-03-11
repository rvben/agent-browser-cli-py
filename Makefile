.EXPORT_ALL_VARIABLES:

SHELL = /bin/bash

AGENT_BROWSER_VERSION ?= 0.17.1

# All supported platforms (system-machine)
PLATFORMS = darwin-arm64 darwin-x86_64 linux-x86_64 linux-arm64 windows-x86_64

version:
	@echo "agent-browser version: $(AGENT_BROWSER_VERSION)"

clean:
	rm -rf dist build agent_browser.egg-info
	rm -rf agent_browser/bin
	rm -rf agent_browser/node_modules

# Download npm package (shared across all platforms, only done once)
download-npm:
	@if [ ! -d agent_browser/node_modules/agent-browser ]; then \
		echo "Downloading npm package..."; \
		AGENT_BROWSER_VERSION=$(AGENT_BROWSER_VERSION) uv run python download_binaries.py --npm-only; \
	else \
		echo "npm package already downloaded, skipping."; \
	fi

# Download CLI binary for a specific platform
# Usage: make download-binary TARGET_SYSTEM=darwin TARGET_MACHINE=arm64
download-binary:
	rm -rf agent_browser/bin
	AGENT_BROWSER_VERSION=$(AGENT_BROWSER_VERSION) \
		uv run python download_binaries.py --binary-only

# Build a wheel for a specific platform
# Usage: make wheel TARGET_SYSTEM=darwin TARGET_MACHINE=arm64
wheel: download-npm download-binary
	rm -rf build agent_browser.egg-info
	TARGET_SYSTEM=$(TARGET_SYSTEM) TARGET_MACHINE=$(TARGET_MACHINE) \
		uv build --wheel
	rm -rf agent_browser/bin
	@ls -lh dist/*.whl | tail -1

# Build wheels for all platforms
wheels: clean download-npm
	@for platform in $(PLATFORMS); do \
		system=$${platform%%-*}; \
		machine=$${platform#*-}; \
		echo ""; \
		echo "=== Building wheel for $$system-$$machine ==="; \
		TARGET_SYSTEM=$$system TARGET_MACHINE=$$machine $(MAKE) download-binary wheel; \
	done
	@echo ""
	@echo "=== All wheels ==="
	@ls -lh dist/*.whl

# Build sdist (no platform-specific binaries)
sdist: download-npm
	uv build --sdist

fmt:
	uv run ruff format .
	uv run ruff check --fix .

lint:
	uv run ruff check .

test:
	uv run pytest .

publish-test:
	uv run --with twine --no-project -- twine upload --repository testpypi dist/*

publish-prod:
	uv run --with twine --no-project -- twine upload --repository pypi dist/*

verify:
	@uv venv -q /tmp/ab-verify
	@uv pip install --python /tmp/ab-verify/bin/python --find-links dist agent-browser-cli==$(AGENT_BROWSER_VERSION)
	@/tmp/ab-verify/bin/agent-browser --version
	@rm -rf /tmp/ab-verify

.PHONY: version clean download-npm download-binary wheel wheels sdist fmt lint test publish-test publish-prod verify
