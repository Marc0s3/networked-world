# Cloudflare Worker

This read-only Worker proxies the public Networked.art API for the static GitHub Pages application.
It exposes only the routes used by Networked World and adds browser CORS headers.

## Deploy

From this directory:

```bash
npx wrangler login
npx wrangler deploy
```

After deployment, copy the resulting URL and append `/api`, for example:

```text
https://networked-world-api.example.workers.dev/api
```

Use that complete value as the GitHub Actions variable `NETWORKED_WORLD_API_BASE`.

## Test

```text
https://YOUR-WORKER.workers.dev/api/health
```

Expected response:

```json
{"ok":true,"version":"1.0.1"}
```
