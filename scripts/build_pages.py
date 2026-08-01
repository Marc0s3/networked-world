#!/usr/bin/env python3
"""Build the static GitHub Pages artifact."""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "_site"
STATIC_FILES = ("index.html", "favicon.svg", "site.webmanifest", "robots.txt")


def validated_api_base() -> str:
    value = os.environ.get("NETWORKED_WORLD_API_BASE", "").strip().rstrip("/")
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc or not value.endswith("/api"):
        raise SystemExit(
            "NETWORKED_WORLD_API_BASE must be an HTTPS Cloudflare Worker URL ending in /api. "
            "Set it in GitHub: Settings > Secrets and variables > Actions > Variables."
        )
    return value


def main() -> None:
    api_base = validated_api_base()
    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    OUTPUT.mkdir(parents=True)

    for name in STATIC_FILES:
        source = ROOT / name
        if not source.is_file():
            raise SystemExit(f"Missing required static file: {name}")
        shutil.copy2(source, OUTPUT / name)

    (OUTPUT / "config.js").write_text(
        "window.NETWORKED_WORLD_API_BASE = " + json.dumps(api_base) + ";\n",
        encoding="utf-8",
    )
    (OUTPUT / ".nojekyll").write_text("", encoding="utf-8")
    print(f"Built {OUTPUT} with API base {api_base}")


if __name__ == "__main__":
    main()
