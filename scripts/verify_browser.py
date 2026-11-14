"""Exercise an installed wheel against a local page, without a public website."""

import subprocess
import tempfile
import threading
import uuid
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

session = "wheel-check-" + uuid.uuid4().hex


def run(*args):
    return subprocess.check_output(
        ["agent-browser", "--session", session, *args], encoding="utf-8", timeout=60
    )


with tempfile.TemporaryDirectory() as temporary:
    Path(temporary, "index.html").write_text(
        '<title>Wheel verification</title><label>Name<input id="name"></label><button>Save</button>'
    )
    handler = partial(SimpleHTTPRequestHandler, directory=temporary)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        run("open", f"http://127.0.0.1:{server.server_port}")
        assert "Wheel verification" in run("get", "title")
        assert "Save" in run("snapshot", "-i")
        run("fill", "#name", "Wheel works")
        assert "Wheel works" in run("get", "value", "#name")
        run("screenshot", str(Path(temporary, "page.png")))
        assert Path(temporary, "page.png").stat().st_size > 0
        print(
            "Installed wheel: navigation, snapshot, fill, readback, screenshot verified"
        )
    finally:
        try:
            try:
                run("close")
            except (subprocess.SubprocessError, OSError):
                # Preserve the original browser/assertion failure during cleanup.
                pass
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
