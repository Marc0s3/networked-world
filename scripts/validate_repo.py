#!/usr/bin/env python3
"""Validate repository structure and syntax without third-party dependencies."""
from __future__ import annotations

import py_compile
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = (
    "index.html",
    "config.js",
    "server.py",
    "serve_networked_world.bat",
    "serve_networked_world.sh",
    "worker/worker.js",
    "worker/wrangler.jsonc",
    "scripts/build_pages.py",
    "scripts/smoke_test.py",
    ".github/workflows/pages.yml",
    ".github/workflows/validate.yml",
    "README.md",
    "LICENSE",
)


def fail(message: str) -> None:
    raise SystemExit(f"VALIDATION FAILED: {message}")


def main() -> None:
    for name in REQUIRED:
        if not (ROOT / name).is_file():
            fail(f"missing {name}")

    server_text = (ROOT / "server.py").read_text(encoding="utf-8")
    if not server_text.startswith("#!/usr/bin/env python3"):
        fail("server.py does not start as a Python program")
    for forbidden in ("**Profile Atlas**", "```", "# Networked World v1.0 —"):
        if forbidden in server_text:
            fail(f"server.py contains documentation text: {forbidden}")
    if "class Handler(SimpleHTTPRequestHandler)" not in server_text:
        fail("server.py is missing the HTTP handler")

    for relative in ("server.py", "scripts/build_pages.py", "scripts/smoke_test.py", "scripts/validate_repo.py"):
        py_compile.compile(str(ROOT / relative), doraise=True)

    html = (ROOT / "index.html").read_text(encoding="utf-8")
    if "Professional Atlas" not in html or '<script src="config.js"></script>' not in html:
        fail("index.html is not the expected Professional Atlas application")

    worker_text = (ROOT / "worker/worker.js").read_text(encoding="utf-8")
    worker_config = json.loads((ROOT / "worker/wrangler.jsonc").read_text(encoding="utf-8"))
    if worker_config.get("ratelimits"):
        fail("the public worker must not require paid Cloudflare rate-limit bindings")
    for required in ("LOCAL_RATE_LIMITS", "localRateBuckets", "trimLocalRateBuckets"):
        if required not in worker_text:
            fail(f"missing zero-cost local rate-limit guard: {required}")
    if "Retry-After" not in worker_text or "cached = await cache.match(key)" not in worker_text:
        fail("worker rate limiting must return retry guidance and preserve cache-first behavior")

    node = shutil.which("node")
    if node:
        scripts = re.findall(r"<script(?:\s[^>]*)?>(.*?)</script>", html, flags=re.DOTALL | re.IGNORECASE)
        inline = "\n".join(part for part in scripts if part.strip())
        with tempfile.TemporaryDirectory() as tmp:
            app_js = Path(tmp) / "app.js"
            worker_js = Path(tmp) / "worker.mjs"
            app_js.write_text(inline, encoding="utf-8")
            worker_js.write_text(worker_text, encoding="utf-8")
            subprocess.run([node, "--check", str(app_js)], check=True)
            subprocess.run([node, "--check", str(worker_js)], check=True)

    subprocess.run([sys.executable, str(ROOT / "scripts/smoke_test.py")], check=True)
    print("Repository validation passed.")


if __name__ == "__main__":
    main()
