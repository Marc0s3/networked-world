#!/usr/bin/env python3
"""Offline smoke test for the local server and static application."""
from __future__ import annotations

import json
import threading
import urllib.request
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import server  # noqa: E402


def main() -> None:
    handler = partial(server.Handler, directory=str(ROOT))
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        with urllib.request.urlopen(base + "/api/health", timeout=5) as response:
            payload = json.load(response)
        assert payload == {"ok": True, "version": "1.0.1"}, payload

        with urllib.request.urlopen(base + "/", timeout=5) as response:
            html = response.read().decode("utf-8")
        assert "Networked World v1.0" in html
        assert "Professional Atlas" in html
        assert '<script src="config.js"></script>' in html
        print("Offline smoke test passed.")
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


if __name__ == "__main__":
    main()
