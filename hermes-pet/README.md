# Hermes Pet — browser and terminal core

A read-only local status companion for Hermes message databases. Python 3.10+ standard library only (no install step, no third-party packages); it makes no model calls. This public core uses an emoji fallback; borrowed character sprites, native desktop managers, live databases and personal registries are excluded.

Run every command from this `hermes-pet/` folder (`python3 -m tools.hermes_pet.pet` needs it as the working directory):

```sh
cd hermes-pet
python3 -m unittest discover -s tests -v
python3 -m tools.hermes_pet.pet --db /absolute/path/to/state.db --once
python3 -m tools.hermes_pet.pet --db /absolute/path/to/state.db --serve
```

Without `--db`, the pet reads `$HERMES_HOME/profiles/<--profile>/state.db` (else `$HERMES_HOME/state.db`; `HERMES_HOME` defaults to `~/.hermes`). Only assistant messages from `telegram` sessions are shown by default; `--source NAME` (repeatable) replaces that list. `--watch` prints new results in the terminal; `python3 -m tools.hermes_pet.pet --help` lists all options.

The browser server defaults to loopback `127.0.0.1:8765` (`--host`/`--port` change it); it displays snippets from the selected local database. Use only your own database and keep the server local. `--asset-dir` accepts your own redistributable spritesheet and pet.json metadata (`spritesheetPath` must stay inside that folder); no third-party character asset is bundled. Tests create synthetic temporary SQLite databases. Missing databases show idle state. MIT covers this code.
