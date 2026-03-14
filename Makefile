.EXPORT_ALL_VARIABLES:

SHELL = /bin/bash

# Upstream agent-browser version (for downloading binaries).
# Override with env var: AGENT_BROWSER_VERSION=0.20.0 make wheels
AGENT_BROWSER_VERSION ?= $(shell grep '^__agent_browser_version__' agent_browser/version.py | cut -d'"' -f2)

# PyPI package version (may include .postN suffix).
# Override with env var: PACKAGE_VERSION=0.20.0 make wheels
PACKAGE_VERSION ?= $(shell grep '^__version__' agent_browser/version.py | cut -d'"' -f2)

# All supported platforms (system-machine)
PLATFORMS = darwin-arm64 darwin-x86_64 linux-x86_64 linux-arm64 windows-x86_64

version:
	@echo "Package version:        $(PACKAGE_VERSION)"
	@echo "Agent-browser version:  $(AGENT_BROWSER_VERSION)"

# Check if a newer agent-browser version exists on npm
check-upstream:
	@python3 -c "\
	import urllib.request, json, sys; \
	latest = json.loads(urllib.request.urlopen('https://registry.npmjs.org/agent-browser/latest').read())['version']; \
	current = '$(AGENT_BROWSER_VERSION)'; \
	print(f'Current: {current}'); \
	print(f'Latest:  {latest}'); \
	same = latest == current; \
	print('Up to date.' if same else f'New version available: {latest}'); \
	" 2>&1; \
	latest=$$(python3 -c "import urllib.request, json; print(json.loads(urllib.request.urlopen('https://registry.npmjs.org/agent-browser/latest').read())['version'])"); \
	if [ "$$latest" != "$(AGENT_BROWSER_VERSION)" ] && [ -n "$${GITHUB_OUTPUT:-}" ]; then \
		echo "new_version=$$latest" >> $$GITHUB_OUTPUT; \
	fi

# Generate version.py from PACKAGE_VERSION
update-version:
	@python3 update_version.py $(PACKAGE_VERSION)

clean:
	rm -rf dist build agent_browser.egg-info
	rm -rf agent_browser/bin

# Download CLI binary for a specific platform
# Usage: make download-binary TARGET_SYSTEM=darwin TARGET_MACHINE=arm64
download-binary:
	rm -rf agent_browser/bin
	AGENT_BROWSER_VERSION=$(AGENT_BROWSER_VERSION) \
		python3 download_binaries.py

# Build a wheel for a specific platform
# Usage: make wheel TARGET_SYSTEM=darwin TARGET_MACHINE=arm64
wheel: download-binary
	rm -rf build agent_browser.egg-info
	TARGET_SYSTEM=$(TARGET_SYSTEM) TARGET_MACHINE=$(TARGET_MACHINE) \
		uv build --wheel
	rm -rf agent_browser/bin
	@ls -lh dist/*.whl | tail -1

# Build wheels for all platforms
wheels: clean update-version
	@for platform in $(PLATFORMS); do \
		system=$${platform%%-*}; \
		machine=$${platform#*-}; \
		echo ""; \
		echo "=== Building wheel for $$system-$$machine ==="; \
		TARGET_SYSTEM=$$system TARGET_MACHINE=$$machine $(MAKE) download-binary wheel || exit 1; \
	done
	@echo ""
	@echo "=== All wheels ==="
	@ls -lh dist/*.whl

# Build sdist
sdist:
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
	@uv pip install --python /tmp/ab-verify/bin/python --find-links dist "agent-browser-cli==$(PACKAGE_VERSION)"
	@/tmp/ab-verify/bin/agent-browser --version
	@rm -rf /tmp/ab-verify

# End-to-end verification (used in CI, requires linux x86_64 wheel)
verify-e2e:
	pip install dist/agent_browser_cli-*-manylinux_2_17_x86_64*.whl
	agent-browser --version
	agent-browser install --with-deps

.PHONY: version check-upstream update-version clean download-binary wheel wheels sdist fmt lint test publish-test publish-prod verify verify-e2e
