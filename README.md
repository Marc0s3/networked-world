# Networked World

> **An interactive visual atlas of the Networked.art ecosystem.**

Explore artists, artworks, auction winners, patrons, and shared relationships through a clean multi-scale map designed specifically for Networked.art.

---

## Overview

Networked World is an open-source explorer that transforms the Networked.art ecosystem into an interactive visual atlas.

Instead of browsing pages, lists, or wallet inventories, every artist becomes a navigable relational space where artworks, collectors and patrons reveal the social structure of an artistic community.

The goal is not simply to visualize NFTs.

The goal is to visualize **relationships**.

---

## Features

- 🎨 Artist-centric exploration
- 🖼️ Verified artwork discovery
- 🏆 Auction winner visualization
- 💚 Patron relationship mapping
- 🌐 Shared collector bridges
- 🔍 Multi-scale navigation
- ⚡ Lightweight, dependency-free frontend
- 🔓 Fully open source

---

## Navigation

Networked World is composed of three visual layers.

### Profile Atlas

A high-level overview of an artist.

- collections
- verified works
- relationship density
- shared collectors

---

### Collection View

Explore every verified artwork inside a collection through a clean spatial layout.

---

### Artwork Relationship View

Reveal the complete social graph of a single artwork.

- auction winner
- patrons
- shared relationships
- visual constellation

---

## Philosophy

Traditional NFT explorers answer questions like:

> Who owns this NFT?

Networked World instead asks:

> **How is this artwork connected to the people around it?**

The project treats artworks as social objects rather than isolated assets.

---

## Local Development

### Windows

Simply run

```bash
serve_networked_world.bat
```

---

### macOS / Linux

```bash
chmod +x serve_networked_world.sh
./serve_networked_world.sh
```

Python 3 is required.

No additional packages are necessary.

> Do **not** open `index.html` directly.
> The local server also provides the read-only API proxy required by the browser.

---


## Data

Networked World starts from the public artist profile returned by Networked.art.

It does **not** begin by scanning every NFT inside a wallet.

Only verified artist works are used to construct the relationship graph.

More details:

```
docs/DATA_PROVENANCE.md
```

---

## Project Status

Current status

**Beta**

The explorer is actively evolving and new visualization models are continuously being developed.

Upcoming work includes:

- Bloom Atlas
- Collection Morphology
- Network Navigation
- Shared Collector Analytics
- Cinematic Mode

---

## License

MIT

---

## Disclaimer

Networked World is an independent open-source project.

It is **not affiliated with, endorsed by, or officially associated with Networked.art**.

---

Made with ❤️ for the Networked.art community.
