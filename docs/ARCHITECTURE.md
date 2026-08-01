# Architecture

## Local

```text
Browser
  -> Python server (`server.py`)
       -> static files
       -> read-only proxy routes
            -> api.networked.art
```

## Public

```text
Browser
  -> GitHub Pages
       -> Cloudflare Worker
            -> api.networked.art
```

## Application layers

- `index.html`: interface, canvas map, layout, interaction, and inspector.
- `config.js`: API base for the current environment.
- `server.py`: zero-dependency local static server and proxy.
- `worker/worker.js`: public read-only API proxy with caching and CORS.
- `scripts/build_pages.py`: builds the static Pages artifact.
- `scripts/validate_repo.py`: guards against malformed or misplaced files.
