# Local development

## Start

```bash
python server.py --port 0
```

`--port 0` asks the operating system for a free port, so the application does not collide with other local tools or LLM servers.

## Do not use `file://`

Opening `index.html` directly bypasses the Python proxy and causes browser fetch errors. Always use the launcher or `server.py`.

## Validate

```bash
python scripts/validate_repo.py
```

## Static Pages build test

```bash
NETWORKED_WORLD_API_BASE="https://example.workers.dev/api" python scripts/build_pages.py
```

On Windows Command Prompt:

```bat
set NETWORKED_WORLD_API_BASE=https://example.workers.dev/api
python scriptsuild_pages.py
```
