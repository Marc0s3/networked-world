# Networked World

**An interactive atlas of the Networked.art ecosystem.**

Networked World turns verified artist works, settled-auction winners, patrons, and shared relationships into a clean multi-scale map.

The interface has three visual levels:

1. **Profile Atlas** — artist origin and clean collection cards.
2. **Collection View** — every verified work in a readable local field.
3. **Artwork Relationship View** — winner and patrons unfold around the selected artwork.

## Local use

### Windows

1. Download and extract the repository ZIP.
2. Double-click `serve_networked_world.bat`.
3. The application opens on a free local port.

### macOS / Linux

```bash
chmod +x serve_networked_world.sh
./serve_networked_world.sh
```

Python 3 is required. No Python packages need to be installed.

> Do not open `index.html` directly. The local Python server also provides the read-only API proxy required by the browser.

## Publish on GitHub Pages

The public deployment uses:

```text
GitHub Pages -> Cloudflare Worker -> public Networked.art API
```

Follow [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

## Validate the repository

```bash
python scripts/validate_repo.py
```

The validator checks the repository structure, Python syntax, browser JavaScript, Worker JavaScript, and an offline local-server smoke test.

## Data boundary

The explorer starts from the artist profile data returned by Networked.art and excludes collections classified as external inventory or patron editions. It does not begin by scanning every NFT held by a wallet.

See [docs/DATA_PROVENANCE.md](docs/DATA_PROVENANCE.md).

## License

MIT. See [LICENSE](LICENSE).

## Status

Independent open-source project. Not affiliated with or endorsed by Networked.art.
