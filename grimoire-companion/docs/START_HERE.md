# Getting started

Grimoire has four main parts:

- `src/grimoire/models.py`, `sources.py`, and `skin.py` define normalized task data, local readers, and data-only character packs.
- `audio.py` manages the optional CAVA child process.
- `widgets.py` and `app.py` implement the Qt interface.
- `config.py` and `logging_utils.py` keep user settings and bounded logs in XDG locations.

Start with the install steps in the root [README](../README.md), then read the [development guide](DEVELOPMENT.md). The [design notes](STYLE_GUIDE.md) describe the visual tokens and the [record keeping guide](RECORDING.md) explains what belongs in project evidence.

The application can run without a task source or CAVA. Missing inputs are shown as unavailable; no task or audio activity is simulated as live.
