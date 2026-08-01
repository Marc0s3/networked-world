# Deployment

The browser application is static, but Networked.art does not expose the required API routes directly to arbitrary browser origins. A small read-only Cloudflare Worker is therefore used as the public proxy.

## 1. Deploy the Worker

Install Node.js, open a terminal in `worker/`, then run:

```bash
npx wrangler login
npx wrangler deploy
```

Wrangler prints a URL such as:

```text
https://networked-world-api.YOUR-SUBDOMAIN.workers.dev
```

Open this health endpoint:

```text
https://networked-world-api.YOUR-SUBDOMAIN.workers.dev/api/health
```

It should return:

```json
{"ok":true,"version":"1.0.1"}
```

## 2. Add the GitHub Actions variable

In the GitHub repository, open:

```text
Settings -> Secrets and variables -> Actions -> Variables
```

Create this repository variable:

```text
Name:  NETWORKED_WORLD_API_BASE
Value: https://networked-world-api.YOUR-SUBDOMAIN.workers.dev/api
```

The value must use HTTPS and end exactly in `/api`.

## 3. Enable GitHub Pages

Open:

```text
Settings -> Pages
```

Under **Build and deployment**, select:

```text
Source: GitHub Actions
```

## 4. Run the Pages workflow

Open **Actions -> Deploy GitHub Pages -> Run workflow**.

After deployment, the application will normally be available at:

```text
https://YOUR-GITHUB-USERNAME.github.io/networked-world/
```

## Why the workflow may initially be skipped

The Pages jobs intentionally run only after `NETWORKED_WORLD_API_BASE` exists. This prevents publishing a site that cannot reach its API proxy.
