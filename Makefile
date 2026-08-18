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
	@ls -lht dist/*.whl | head -1

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

# A wheel built at an unintended version would publish under a name nobody
# asked for, so the filenames are checked against the version being built
# before anything leaves the machine. The expected count comes from PLATFORMS
# rather than a literal, so a platform that silently drops out of the build is
# caught by the same check that a version mismatch is.
check-wheels:
	@ls -lh dist/
	@matching=$$(find dist -name "agent_browser_cli-$(PACKAGE_VERSION)-*.whl" | wc -l | tr -d ' '); \
	total=$$(find dist -name '*.whl' | wc -l | tr -d ' '); \
	if [ "$$matching" -ne $(words $(PLATFORMS)) ] || [ "$$matching" -ne "$$total" ]; then \
		echo "Error: expected $(words $(PLATFORMS)) wheels at version $(PACKAGE_VERSION), found $$matching of $$total" >&2; \
		exit 1; \
	fi; \
	echo "All $$total wheels are at $(PACKAGE_VERSION)"

# Builds the release that would ship today, so the download and packaging steps
# are exercised by an ordinary push instead of first running when a version is
# already due. The version deliberately comes from npm rather than version.py:
# version.py trails upstream between releases, so building it would rehearse
# against a binary set no release will ship and miss a change in the current
# one. `latest` is the same dist-tag check-version.yml releases from.
#
# The accepted cost is that this target is not deterministic. An upstream
# release, or an asset that lags the version that announces it, turns a run red
# for a reason that has nothing to do with the commit under test. That is
# preferred to a rehearsal that passes forever against an asset layout no
# release uses. A red run here that a rerun does not clear is upstream, not the
# commit.
# version.py is saved and restored because `wheels` regenerates it: without
# that, rehearsing on a development machine silently rewrites a tracked file to
# whatever npm currently publishes. The copy is restored rather than checked
# out, so uncommitted edits to version.py survive a rehearsal too. The two
# sub-makes are separate invocations so that the check cannot start before the
# build it checks, which `make wheels check-wheels` would allow under -j.
rehearse-release:
	@latest=$$(python3 -c "import json, urllib.request; print(json.loads(urllib.request.urlopen('https://registry.npmjs.org/agent-browser/latest').read())['version'])"); \
	if [ -z "$$latest" ]; then \
		echo "Error: could not read the current agent-browser version from npm" >&2; \
		exit 1; \
	fi; \
	echo "=== Rehearsing the release of $$latest ==="; \
	saved=$$(mktemp); \
	cp agent_browser/version.py "$$saved"; \
	trap 'cp "$$saved" agent_browser/version.py; rm -f "$$saved"' EXIT; \
	$(MAKE) wheels AGENT_BROWSER_VERSION=$$latest PACKAGE_VERSION=$$latest && \
	$(MAKE) check-wheels PACKAGE_VERSION=$$latest

# Build sdist
sdist:
	uv build --sdist

fmt:
	uv run ruff format .
	uv run ruff check --fix .

# uv rewrites uv.lock whenever pyproject.toml asks for something the lock does
# not already satisfy, so a dependency edit committed without its regenerated
# lock silently upgrades every dev tool on the next run. That is the shape of
# the failure the lock was committed to prevent: an unpinned ruff resolved to a
# newer rule set and failed a release. Checking the lock before it is used
# reports that as a stale lockfile instead of as a linter that changed its mind.
# Kept out of lint's prerequisites so that editing a dependency locally does not
# block `make lint` before `uv lock` has been run.
lock-check:
	uv lock --check

lint:
	uv run ruff check .

test:
	uv run pytest .

# --skip-existing is what makes a retried release converge. A failed release is
# retried on the next scheduled run, which rebuilds the wheels; compiled builds
# are not reproducible, so the new bytes collide with whatever the first attempt
# already uploaded and PyPI hard-fails the filename, aborting the rest.
publish-test:
	uv run --with twine --no-project -- twine upload --skip-existing --repository testpypi dist/*

publish-prod:
	uv run --with twine --no-project -- twine upload --skip-existing --repository pypi dist/*

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

.PHONY: version check-upstream update-version clean download-binary wheel wheels check-wheels rehearse-release sdist fmt lock-check lint test publish-test publish-prod verify verify-e2e
