"""Fetch version-matched native binaries and runtime data at build time."""

import base64
import hashlib
import io
import json
import os
import re
import shutil
import tarfile
import tempfile
import urllib.error
import urllib.request
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse

USER_AGENT = "agent-browser-cli-builder"


class PrivateRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Never forward a GitHub credential to a redirected download host."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if (
            redirected is not None
            and urlparse(newurl).netloc != urlparse(req.full_url).netloc
        ):
            redirected.remove_header("Authorization")
        return redirected


def read_url(url: str) -> bytes:
    headers = {"User-Agent": USER_AGENT}
    # Authenticate metadata only; release binaries redirect to a different host.
    if urlparse(url).netloc == "api.github.com" and os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = "Bearer " + os.environ["GITHUB_TOKEN"]
    request = urllib.request.Request(url, headers=headers)
    try:
        opener = urllib.request.build_opener(PrivateRedirectHandler())
        with opener.open(request, timeout=120) as response:
            return response.read()
    except (urllib.error.URLError, TimeoutError) as e:
        raise RuntimeError(f"Failed to download {url}: {e}") from e


def download_file(url: str, dest: str) -> None:
    """Download to a temporary path; callers verify before installing it."""
    print(f"  Downloading: {url}")
    Path(dest).write_bytes(read_url(url))


def validate_version(version: str) -> None:
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError(f"Expected an upstream X.Y.Z version, got {version!r}")


def get_release_digests(version: str) -> dict:
    from agent_browser.constants import GITHUB_REPO

    release = json.loads(
        read_url(f"https://api.github.com/repos/{GITHUB_REPO}/releases/tags/v{version}")
    )
    return {
        asset["name"]: asset["digest"]
        for asset in release["assets"]
        if re.fullmatch(r"sha256:[a-f0-9]{64}", asset.get("digest") or "")
    }


def cached_assets_match(package: Path, version: str) -> bool:
    try:
        manifest = json.loads((package / "upstream.json").read_text())
        return (
            manifest["version"] == version
            and bool(manifest["files"])
            and bool(manifest["binaries"])
            and all(
                hashlib.sha256((package / name).read_bytes()).hexdigest() == digest
                for name, digest in manifest["files"].items()
            )
        )
    except (OSError, ValueError, KeyError):
        return False


def download_cli_binary(version: str, system: str, machine: str) -> None:
    """Verify the release asset digest before placing the executable in the wheel."""
    from agent_browser.constants import (
        get_binary_download_url,
        get_binary_name,
    )

    validate_version(version)
    name = get_binary_name(system, machine)
    provenance = Path("agent_browser/upstream.json")
    recorded = json.loads(provenance.read_text()) if provenance.is_file() else {}
    digests = recorded.get("binaries", {}) if recorded.get("version") == version else {}
    expected = digests.get(name) or get_release_digests(version).get(name)
    if not expected:
        raise RuntimeError(f"No SHA-256 release digest for {name} at v{version}")
    bin_dir = Path("agent_browser/bin")
    bin_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=bin_dir) as temporary:
        downloaded = Path(temporary) / name
        download_file(
            get_binary_download_url(version, system, machine), str(downloaded)
        )
        digest = hashlib.sha256(downloaded.read_bytes()).hexdigest()
        if "sha256:" + digest != expected:
            raise RuntimeError(f"SHA-256 mismatch for {name}")
        if system != "windows":
            downloaded.chmod(0o755)
        os.replace(downloaded, bin_dir / name)
    print(f"  Verified and saved {bin_dir / name}")


_LICENSE_FILES = {
    "LICENSE": "agent-browser-LICENSE",
    "cli/src/native/a11y/LICENSE-axe-core.txt": "LICENSE-axe-core.txt",
    "cli/src/native/a11y/LICENSE-axe-core-THIRD-PARTY.txt": "LICENSE-axe-core-THIRD-PARTY.txt",
}


def unpack_runtime_assets(archive: bytes, destination: Path, version: str) -> None:
    """Copy only regular runtime files, never executing or extracting npm scripts."""
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as bundle:
        if not bundle.getmember("package/package.json").isfile():
            raise RuntimeError("Upstream package manifest must be a regular file")
        manifest = bundle.extractfile("package/package.json")
        if manifest is None or json.load(manifest).get("version") != version:
            raise RuntimeError(
                "Upstream runtime data version does not match the binary"
            )
        for member in bundle:
            path = PurePosixPath(member.name)
            if (
                path.parts[:1] != ("package",)
                or ".." in path.parts
                or "\\" in member.name
                or ":" in member.name
            ):
                raise RuntimeError(f"Unsafe path in upstream archive: {member.name}")
            relative = path.relative_to("package")
            if str(relative) in _LICENSE_FILES:
                target = Path("licenses") / _LICENSE_FILES[str(relative)]
            elif relative.parts[:1] in (("skills",), ("skill-data",)):
                target = Path(*relative.parts)
            else:
                continue
            if member.isdir():
                continue
            if not member.isfile():
                raise RuntimeError(f"Expected a regular upstream file: {member.name}")
            source = bundle.extractfile(member)
            if source is None:
                raise RuntimeError(f"Cannot read upstream file: {member.name}")
            output = destination / target
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(source.read())
            output.chmod(0o755 if member.mode & 0o111 else 0o644)
    required = [
        "skill-data/core/SKILL.md",
        *(f"licenses/{n}" for n in _LICENSE_FILES.values()),
    ]
    for resource in required:
        if not (destination / resource).is_file():
            raise RuntimeError(f"Upstream archive is missing {resource}")


def download_runtime_assets(version: str) -> None:
    """Fetch npm's exact version and check its published SHA-512 integrity."""
    validate_version(version)
    if cached_assets_match(Path("agent_browser"), version):
        print(f"Runtime assets for {version} already verified")
        return
    metadata = json.loads(
        read_url(f"https://registry.npmjs.org/agent-browser/{version}")
    )
    integrity = metadata["dist"].get("integrity", "")
    if not integrity.startswith("sha512-"):
        raise RuntimeError("Upstream runtime archive has no SHA-512 integrity")
    archive = read_url(metadata["dist"]["tarball"])
    actual = base64.b64encode(hashlib.sha512(archive).digest()).decode("ascii")
    if integrity != "sha512-" + actual:
        raise RuntimeError("SHA-512 mismatch for upstream runtime archive")
    # Validate all data in isolation so a failed download leaves existing data intact.
    with tempfile.TemporaryDirectory() as temporary:
        staged = Path(temporary)
        unpack_runtime_assets(archive, staged, version)
        binaries = get_release_digests(version)
        from agent_browser.constants import BUILD_TARGETS, get_binary_name

        for system, machine in BUILD_TARGETS:
            name = get_binary_name(system, machine)
            if name not in binaries:
                raise RuntimeError(
                    f"No SHA-256 release digest for {name} at v{version}"
                )
        (staged / "upstream.json").write_text(
            json.dumps(
                {
                    "version": version,
                    "binaries": binaries,
                    "files": {
                        file.relative_to(staged).as_posix(): hashlib.sha256(
                            file.read_bytes()
                        ).hexdigest()
                        for file in sorted(staged.rglob("*"))
                        if file.is_file()
                    },
                    "runtime_archive": metadata["dist"]["tarball"],
                    "integrity": integrity,
                    "source": f"https://github.com/vercel-labs/agent-browser/tree/v{version}",
                },
                indent=2,
            )
            + "\n"
        )
        package = Path("agent_browser")
        for name in ("skills", "skill-data", "licenses"):
            target = package / name
            if target.exists():
                shutil.rmtree(target)
            if (staged / name).exists():
                shutil.copytree(staged / name, target)
        # Write provenance last. An interrupted copy cannot pass build validation.
        temporary_manifest = package / "upstream.json.tmp"
        shutil.copy2(staged / "upstream.json", temporary_manifest)
        os.replace(temporary_manifest, package / "upstream.json")
    print(f"Verified runtime skills and licenses for agent-browser {version}")


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Download verified agent-browser assets"
    )
    parser.add_argument(
        "--assets", action="store_true", help="Download runtime skills and licenses"
    )
    args = parser.parse_args()
    version = os.environ.get("AGENT_BROWSER_VERSION")
    if not version:
        parser.error("AGENT_BROWSER_VERSION environment variable not set")
    if args.assets:
        download_runtime_assets(version)
        return
    from agent_browser.constants import MACHINE, SYSTEM

    download_cli_binary(
        version,
        os.environ.get("TARGET_SYSTEM") or SYSTEM,
        os.environ.get("TARGET_MACHINE") or MACHINE,
    )


if __name__ == "__main__":
    main()
