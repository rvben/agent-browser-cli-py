"""
Node.js runtime management — downloads on first use to ~/.cache/agent-browser-py/.

The Node.js binary is not bundled in the wheel to keep package size under
PyPI limits. Instead, it's downloaded once on first invocation.
"""

import os
import sys
import shutil
import tarfile
import zipfile
import tempfile
import urllib.request
import urllib.error

from .constants import (
    CACHE_DIR,
    NODE_VERSION,
    SYSTEM,
    get_node_download_url,
)


def get_node_dir() -> str:
    """Get the directory where Node.js is cached."""
    return os.path.join(CACHE_DIR, f"node-v{NODE_VERSION}")


def get_node_bin_path() -> str:
    """Get the expected path to the cached node binary."""
    node_dir = get_node_dir()
    if SYSTEM == "windows":
        return os.path.join(node_dir, "node.exe")
    return os.path.join(node_dir, "bin", "node")


def is_node_installed() -> bool:
    """Check if Node.js is downloaded and ready."""
    path = get_node_bin_path()
    return os.path.exists(path) and (SYSTEM == "windows" or os.access(path, os.X_OK))


def ensure_node() -> str:
    """Ensure Node.js is available, downloading if needed. Returns path to node binary."""
    if is_node_installed():
        return get_node_bin_path()

    print(f"Downloading Node.js v{NODE_VERSION} (one-time setup)...")
    download_node()
    print("Done.")

    path = get_node_bin_path()
    if not os.path.exists(path):
        raise RuntimeError(f"Node.js download completed but binary not found at {path}")
    return path


def download_node() -> None:
    """Download and extract Node.js to the cache directory.

    Keeps bin/ (node, npm, npx) and lib/node_modules/npm/ (npm runtime).
    Strips include/, share/, docs, and other unnecessary files.
    """
    node_dir = get_node_dir()

    if os.path.exists(node_dir):
        shutil.rmtree(node_dir)
    os.makedirs(node_dir, exist_ok=True)

    url = get_node_download_url()

    with tempfile.NamedTemporaryFile(
        suffix=".zip" if url.endswith(".zip") else ".tar.gz",
        delete=False,
    ) as tmp:
        tmp_path = tmp.name

    try:
        urllib.request.urlretrieve(url, tmp_path)

        with tempfile.TemporaryDirectory() as extract_dir:
            if url.endswith(".zip"):
                with zipfile.ZipFile(tmp_path, "r") as zf:
                    zf.extractall(extract_dir)
            else:
                with tarfile.open(tmp_path, "r:gz") as tar:
                    if sys.version_info >= (3, 12):
                        tar.extractall(extract_dir, filter="data")
                    else:
                        tar.extractall(extract_dir)

            # Find the extracted node-v* directory
            extracted = None
            for item in os.listdir(extract_dir):
                if item.startswith("node-v"):
                    extracted = os.path.join(extract_dir, item)
                    break

            if not extracted:
                raise RuntimeError("Could not find node directory in archive")

            # Move the full distribution, then strip what we don't need
            for item in os.listdir(extracted):
                src = os.path.join(extracted, item)
                dst = os.path.join(node_dir, item)
                if os.path.isdir(src):
                    shutil.copytree(src, dst, symlinks=True)
                else:
                    shutil.copy2(src, dst)

            # Strip unnecessary directories
            for strip_dir in ("include", "share"):
                path = os.path.join(node_dir, strip_dir)
                if os.path.exists(path):
                    shutil.rmtree(path)

            # Strip unnecessary files from root
            for strip_file in ("CHANGELOG.md", "README.md"):
                path = os.path.join(node_dir, strip_file)
                if os.path.exists(path):
                    os.unlink(path)

            # Ensure binaries are executable
            bin_dir = os.path.join(node_dir, "bin")
            if os.path.exists(bin_dir):
                for item in os.listdir(bin_dir):
                    item_path = os.path.join(bin_dir, item)
                    if os.path.isfile(item_path) or os.path.islink(item_path):
                        try:
                            os.chmod(item_path, 0o755)
                        except OSError:
                            pass

    except urllib.error.HTTPError as e:
        raise RuntimeError(
            f"Failed to download Node.js from {url}: HTTP {e.code}"
        ) from e
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
