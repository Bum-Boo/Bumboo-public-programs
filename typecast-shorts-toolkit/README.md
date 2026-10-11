# Typecast Shorts Toolkit

Experimental caption timing parsers and Adobe panels for locally supplied Typecast-style audio/caption folders. This fresh public edition contains synthetic examples, no voice recordings, customer projects or screenshots. It is not affiliated with Typecast or Adobe.

## Core

Node.js 22+ and npm:

```sh
npm ci
npm test
npm run build
```

The shared core parses SRT, VTT and supported timestamp JSON, validates folders and exports SRT. Tests verify this core; they do not execute Adobe APIs. `samples/synthetic` contains fabricated captions and an original generated sine tone.

## After Effects ScriptUI

Close unrelated work. In an empty test project, run `apps/after-effects-typecast-sync/src/TypecastShortsSync.jsx` using File → Scripts → Run Script File. Keep the three included JSX helper files beside it. To dock the panel, copy that complete source folder into the application ScriptUI Panels directory and restart After Effects. Select a test composition and the synthetic folder before generating caption layers. No manifest is needed for a ScriptUI panel. It modifies the selected composition and may adjust its duration.

## Premiere UXP

Install Adobe UXP Developer Tool separately and load `apps/premiere-typecast-sync/src/manifest.json` as a development plugin. The manifest targets Premiere Pro 25.6+, requires local filesystem access and points to the colocated index.html. This is development installation, not a signed marketplace package. Use the synthetic folder in a blank test project. Caption generation uses SRT fallback where native public DOM support is unavailable. Adobe runtime behavior has not been verified by this public packaging pass.

See [limitations](docs/limitations.md), [workflow](docs/mvp-workflow.md), and [file formats](docs/typecast-file-format.md). MIT covers user-authored code and synthetic sample; external host software and user-supplied media retain separate terms.
