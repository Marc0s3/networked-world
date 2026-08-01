# Data provenance

Networked World uses public Networked.art API routes discovered from the production artist profile flow.

The admission sequence is:

```text
artist profile
  -> artist collections returned by Networked.art
  -> exclude external inventory and patron-edition collections
  -> verified works for the artist and collection
  -> work detail
  -> auction winner and patrons
```

The application deliberately does **not** start from every token owned by a wallet. That distinction prevents unrelated NFTs from entering the atlas merely because the artist or collector owns them.

Each work is identified by contract address and token ID. Relationships are attached only after the work has entered through the artist-profile source.
