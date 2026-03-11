"""Tests for download_binaries.py — build-time npm/binary download logic."""

import json
import shutil
import tarfile

from unittest.mock import patch, MagicMock

from download_binaries import (
    install_npm_dependency,
    install_npm_dependencies,
    parse_semver,
    resolve_version,
    strip_node_modules,
)


class TestParseSemver:
    """Test semver string parsing."""

    def test_parses_standard_version(self):
        assert parse_semver("1.2.3") == (1, 2, 3)

    def test_parses_zero_version(self):
        assert parse_semver("0.0.0") == (0, 0, 0)

    def test_parses_large_numbers(self):
        assert parse_semver("22.14.0") == (22, 14, 0)

    def test_returns_zero_for_invalid(self):
        assert parse_semver("not-a-version") == (0, 0, 0)

    def test_ignores_prerelease_suffix(self):
        assert parse_semver("1.0.0-beta.1") == (1, 0, 0)


class TestResolveVersion:
    """Test npm version spec resolution."""

    VERSIONS = [
        "1.0.0", "1.1.0", "1.2.3",
        "2.0.0", "2.0.5", "2.1.0", "2.3.7",
        "3.0.0", "3.1.0",
        "4.0.0", "4.7.0",
    ]

    def test_caret_stays_within_major(self):
        result = resolve_version("^2.0.5", self.VERSIONS)
        assert result == "2.3.7"

    def test_caret_does_not_cross_major(self):
        result = resolve_version("^2.0.0", self.VERSIONS)
        assert result == "2.3.7"
        assert not result.startswith("3")

    def test_caret_major_3(self):
        result = resolve_version("^3.0.0", self.VERSIONS)
        assert result == "3.1.0"

    def test_tilde_stays_within_minor(self):
        result = resolve_version("~2.0.0", self.VERSIONS)
        assert result == "2.0.5"

    def test_tilde_does_not_cross_minor(self):
        result = resolve_version("~2.0.0", self.VERSIONS)
        assert result != "2.1.0"

    def test_exact_version(self):
        result = resolve_version("2.0.5", self.VERSIONS)
        assert result == "2.0.5"

    def test_exact_version_missing(self):
        result = resolve_version("9.9.9", self.VERSIONS)
        assert result is None

    def test_gte_returns_highest(self):
        result = resolve_version(">=3.0.0", self.VERSIONS)
        assert result == "4.7.0"

    def test_fallback_to_latest(self):
        result = resolve_version("*", self.VERSIONS)
        assert result == "4.7.0"

    def test_empty_versions(self):
        result = resolve_version("^1.0.0", [])
        assert result is None

    def test_readable_stream_scenario(self):
        """lazystream needs ^2.0.5, should get 2.x not 4.x."""
        versions = ["2.0.0", "2.0.5", "2.3.0", "3.0.0", "3.6.0", "4.0.0", "4.7.0"]
        result = resolve_version("^2.0.5", versions)
        assert result == "2.3.0"


class TestInstallNpmDependency:
    """Test single npm dependency download and extraction."""

    def _create_fake_npm_tarball(
        self, tmp_path, name="fake-pkg", version="1.0.0", deps=None
    ):
        """Create a minimal npm tarball with package.json."""
        pkg_dir = tmp_path / "package"
        pkg_dir.mkdir(parents=True, exist_ok=True)
        pkg_json = {
            "name": name,
            "version": version,
        }
        if deps:
            pkg_json["dependencies"] = deps
        (pkg_dir / "package.json").write_text(json.dumps(pkg_json))
        (pkg_dir / "index.js").write_text(f"module.exports = '{name}';")

        # Use a safe filename (scoped packages have / in the name)
        safe_name = name.replace("/", "__").replace("@", "")
        tarball_path = tmp_path / f"{safe_name}-{version}.tgz"
        with tarfile.open(str(tarball_path), "w:gz") as tar:
            tar.add(str(pkg_dir), arcname="package")

        return str(tarball_path)

    def _mock_registry(self, name, version, tarball_url):
        """Create a mock registry response with the version as both latest and only entry."""
        data = json.dumps(
            {
                "dist-tags": {"latest": version},
                "versions": {version: {"dist": {"tarball": tarball_url}}},
            }
        ).encode()
        mock_resp = MagicMock()
        mock_resp.read.return_value = data
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        return mock_resp

    def test_skips_if_already_installed(self, tmp_path):
        node_modules = tmp_path / "node_modules"
        dest = node_modules / "existing-pkg"
        dest.mkdir(parents=True)

        with patch("urllib.request.urlopen") as mock_urlopen:
            install_npm_dependency(str(node_modules), "existing-pkg", "^1.0.0")
            mock_urlopen.assert_not_called()

    def test_installs_package(self, tmp_path):
        node_modules = tmp_path / "node_modules"
        node_modules.mkdir()
        tarball = self._create_fake_npm_tarball(tmp_path, "my-pkg", "2.0.0")
        mock_resp = self._mock_registry("my-pkg", "2.0.0", f"file://{tarball}")

        with (
            patch("urllib.request.urlopen", return_value=mock_resp),
            patch(
                "urllib.request.urlretrieve",
                side_effect=lambda url, path: shutil.copy2(tarball, path),
            ),
        ):
            install_npm_dependency(str(node_modules), "my-pkg", "^2.0.0")

        assert (node_modules / "my-pkg" / "package.json").exists()
        assert (node_modules / "my-pkg" / "index.js").exists()

    def test_installs_scoped_package(self, tmp_path):
        """Scoped packages like @scope/name need special URL encoding."""
        node_modules = tmp_path / "node_modules"
        node_modules.mkdir()
        tarball = self._create_fake_npm_tarball(tmp_path, "@scope/pkg", "1.0.0")
        mock_resp = self._mock_registry("@scope/pkg", "1.0.0", f"file://{tarball}")

        captured_urls = []

        def tracking_urlopen(url):
            captured_urls.append(url)
            return mock_resp

        with (
            patch("urllib.request.urlopen", side_effect=tracking_urlopen),
            patch(
                "urllib.request.urlretrieve",
                side_effect=lambda url, path: shutil.copy2(tarball, path),
            ),
        ):
            install_npm_dependency(str(node_modules), "@scope/pkg", "^1.0.0")

        assert (node_modules / "@scope" / "pkg" / "package.json").exists()
        assert any("%2F" in url for url in captured_urls), (
            "Scoped package URL should contain %2F encoding"
        )

    def test_installs_sub_dependencies(self, tmp_path):
        """Dependencies of dependencies should be installed recursively."""
        node_modules = tmp_path / "node_modules"
        node_modules.mkdir()

        # Parent depends on child
        parent_tarball = self._create_fake_npm_tarball(
            tmp_path / "parent", "parent-pkg", "1.0.0", deps={"child-pkg": "^1.0.0"}
        )
        child_tarball = self._create_fake_npm_tarball(
            tmp_path / "child", "child-pkg", "1.0.0"
        )

        parent_resp = self._mock_registry(
            "parent-pkg", "1.0.0", f"file://{parent_tarball}"
        )
        child_resp = self._mock_registry(
            "child-pkg", "1.0.0", f"file://{child_tarball}"
        )

        def mock_urlopen(url):
            if "child-pkg" in url:
                return child_resp
            return parent_resp

        def mock_urlretrieve(url, path):
            if "child" in url:
                shutil.copy2(child_tarball, path)
            else:
                shutil.copy2(parent_tarball, path)

        with (
            patch("urllib.request.urlopen", side_effect=mock_urlopen),
            patch("urllib.request.urlretrieve", side_effect=mock_urlretrieve),
        ):
            install_npm_dependency(str(node_modules), "parent-pkg", "^1.0.0")

        assert (node_modules / "parent-pkg" / "package.json").exists()
        assert (node_modules / "child-pkg" / "package.json").exists()

    def test_deduplication_first_version_wins(self, tmp_path):
        """If a package is already in node_modules, skip it (flat dedup)."""
        node_modules = tmp_path / "node_modules"
        node_modules.mkdir()

        # Pre-install child-pkg
        child_dir = node_modules / "child-pkg"
        child_dir.mkdir()
        (child_dir / "package.json").write_text(
            json.dumps({"name": "child-pkg", "version": "1.0.0"})
        )

        # Parent depends on child, but child is already there
        parent_tarball = self._create_fake_npm_tarball(
            tmp_path / "parent",
            "parent-pkg",
            "1.0.0",
            deps={
                "child-pkg": "^2.0.0"
            },  # Different version spec, but already installed
        )
        parent_resp = self._mock_registry(
            "parent-pkg", "1.0.0", f"file://{parent_tarball}"
        )

        with (
            patch("urllib.request.urlopen", return_value=parent_resp),
            patch(
                "urllib.request.urlretrieve",
                side_effect=lambda url, path: shutil.copy2(parent_tarball, path),
            ),
        ):
            install_npm_dependency(str(node_modules), "parent-pkg", "^1.0.0")

        # child-pkg should still have version 1.0.0 (not re-downloaded)
        with open(child_dir / "package.json") as f:
            data = json.load(f)
        assert data["version"] == "1.0.0"

    def test_handles_registry_http_error(self, tmp_path, capsys):
        """HTTP errors from the registry should be warned, not crash."""
        import urllib.error

        node_modules = tmp_path / "node_modules"
        node_modules.mkdir()

        with patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.HTTPError(
                "https://registry.npmjs.org/fake", 404, "Not Found", {}, None
            ),
        ):
            install_npm_dependency(str(node_modules), "fake-pkg", "^1.0.0")

        captured = capsys.readouterr()
        assert "Warning" in captured.out or not (node_modules / "fake-pkg").exists()


class TestStripNodeModules:
    """Test strip_node_modules() removes unnecessary files."""

    def test_strips_test_directories(self, tmp_path):
        node_modules = tmp_path / "node_modules"
        pkg = node_modules / "some-pkg"
        test_dir = pkg / "test"
        test_dir.mkdir(parents=True)
        (test_dir / "test.js").write_text("test()")
        (pkg / "index.js").write_text("module.exports = {}")

        strip_node_modules(str(node_modules))

        assert not test_dir.exists()
        assert (pkg / "index.js").exists()

    def test_strips_doc_directories(self, tmp_path):
        node_modules = tmp_path / "node_modules"
        pkg = node_modules / "some-pkg"
        for dirname in ("docs", "doc", "examples", "example"):
            d = pkg / dirname
            d.mkdir(parents=True)
            (d / "file.txt").write_text("content")
        (pkg / "index.js").write_text("module.exports = {}")

        strip_node_modules(str(node_modules))

        for dirname in ("docs", "doc", "examples", "example"):
            assert not (pkg / dirname).exists()

    def test_strips_map_files(self, tmp_path):
        node_modules = tmp_path / "node_modules"
        pkg = node_modules / "some-pkg"
        pkg.mkdir(parents=True)
        (pkg / "index.js").write_text("module.exports = {}")
        (pkg / "index.js.map").write_text("{}")
        (pkg / "style.css.map").write_text("{}")

        strip_node_modules(str(node_modules))

        assert (pkg / "index.js").exists()
        assert not (pkg / "index.js.map").exists()
        assert not (pkg / "style.css.map").exists()

    def test_strips_markdown_files(self, tmp_path):
        node_modules = tmp_path / "node_modules"
        pkg = node_modules / "some-pkg"
        pkg.mkdir(parents=True)
        (pkg / "index.js").write_text("module.exports = {}")
        (pkg / "CHANGELOG.md").write_text("# Changes")
        (pkg / "README.md").write_text("# Readme")
        (pkg / "HISTORY.md").write_text("# History")

        strip_node_modules(str(node_modules))

        assert not (pkg / "CHANGELOG.md").exists()
        assert not (pkg / "README.md").exists()
        assert not (pkg / "HISTORY.md").exists()

    def test_preserves_license_files(self, tmp_path):
        node_modules = tmp_path / "node_modules"
        pkg = node_modules / "some-pkg"
        pkg.mkdir(parents=True)
        (pkg / "index.js").write_text("module.exports = {}")
        (pkg / "LICENSE").write_text("MIT")
        (pkg / "LICENSE.md").write_text("MIT License")

        strip_node_modules(str(node_modules))

        assert (pkg / "LICENSE").exists()
        # LICENSE.md has .md extension but starts with LICENSE, so preserved
        assert (pkg / "LICENSE.md").exists()

    def test_preserves_type_definition_files(self, tmp_path):
        node_modules = tmp_path / "node_modules"
        pkg = node_modules / "some-pkg"
        pkg.mkdir(parents=True)
        (pkg / "index.js").write_text("module.exports = {}")
        (pkg / "index.d.ts").write_text("export default {}")

        strip_node_modules(str(node_modules))

        assert (pkg / "index.d.ts").exists()

    def test_strips_config_files(self, tmp_path):
        node_modules = tmp_path / "node_modules"
        pkg = node_modules / "some-pkg"
        pkg.mkdir(parents=True)
        (pkg / "index.js").write_text("module.exports = {}")
        for name in (".eslintrc.json", ".prettierrc.json", "tsconfig.json", ".npmrc"):
            (pkg / name).write_text("{}")

        strip_node_modules(str(node_modules))

        for name in (".eslintrc.json", ".prettierrc.json", "tsconfig.json", ".npmrc"):
            assert not (pkg / name).exists()

    def test_strips_github_directory(self, tmp_path):
        node_modules = tmp_path / "node_modules"
        pkg = node_modules / "some-pkg"
        gh = pkg / ".github"
        gh.mkdir(parents=True)
        (gh / "workflows.yml").write_text("ci: true")
        (pkg / "index.js").write_text("module.exports = {}")

        strip_node_modules(str(node_modules))

        assert not gh.exists()

    def test_reports_size_reduction(self, tmp_path, capsys):
        node_modules = tmp_path / "node_modules"
        pkg = node_modules / "some-pkg"
        test_dir = pkg / "test"
        test_dir.mkdir(parents=True)
        (test_dir / "big_test.js").write_text("x" * 10000)
        (pkg / "index.js").write_text("module.exports = {}")

        strip_node_modules(str(node_modules))

        captured = capsys.readouterr()
        assert "Stripped" in captured.out or "MB" in captured.out


class TestInstallNpmDependencies:
    """Test install_npm_dependencies() reads package.json and installs all deps."""

    def test_reads_dependencies_from_package_json(self, tmp_path):
        node_modules = tmp_path / "node_modules"
        ab_dir = node_modules / "agent-browser"
        ab_dir.mkdir(parents=True)
        (ab_dir / "package.json").write_text(
            json.dumps(
                {
                    "name": "agent-browser",
                    "version": "0.17.1",
                    "dependencies": {
                        "playwright-core": "^1.58.0",
                        "ws": "^8.0.0",
                    },
                }
            )
        )

        with patch("download_binaries.install_npm_dependency") as mock_install:
            install_npm_dependencies(str(node_modules))

        assert mock_install.call_count == 2
        call_args = [c[0] for c in mock_install.call_args_list]
        dep_names = [args[1] for args in call_args]
        assert "playwright-core" in dep_names
        assert "ws" in dep_names

    def test_handles_no_dependencies(self, tmp_path):
        node_modules = tmp_path / "node_modules"
        ab_dir = node_modules / "agent-browser"
        ab_dir.mkdir(parents=True)
        (ab_dir / "package.json").write_text(
            json.dumps(
                {
                    "name": "agent-browser",
                    "version": "0.17.1",
                }
            )
        )

        with patch("download_binaries.install_npm_dependency") as mock_install:
            install_npm_dependencies(str(node_modules))

        mock_install.assert_not_called()
