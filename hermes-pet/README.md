# Hermes Pet — browser and terminal core

A read-only local status companion for Hermes message databases. Python 3.10+ standard library only; it makes no model calls. This public core uses an emoji fallback; borrowed character sprites, native desktop managers, live databases and personal registries are excluded.

```sh
python3 -m unittest discover -s tests -v
python3 -m tools.hermes_pet.pet --db /absolute/path/to/state.db --once
python3 -m tools.hermes_pet.pet --db /absolute/path/to/state.db --serve
```

The browser server defaults to loopback `127.0.0.1:8765`; it displays snippets from the selected local database. Use only your own database and keep the server local. `--asset-dir` accepts your own redistributable spritesheet and pet.json metadata; no third-party character asset is bundled. Tests create synthetic temporary SQLite databases. Missing databases show idle state. MIT covers this code.
