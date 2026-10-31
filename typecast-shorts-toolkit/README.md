# Typecast Shorts Toolkit

Experimental caption timing parsers and Adobe panels for locally supplied Typecast-style audio/caption folders. This fresh public edition contains synthetic examples, no voice recordings, customer projects or screenshots. It is not affiliated with Typecast or Adobe.

## Core

Node.js 22+ and npm:

```sh
npm ci
npm test
npm run build
```

`npm ci` installs the workspace dev tools (TypeScript, Node types). `npm test` compiles `packages/typecast-sync-core` to `dist/` and runs every `packages/typecast-sync-core/tests/*.test.mjs` file with the built-in `node --test` runner; `npm run build` only compiles. Verified on Linux with Node 22.

The shared core parses SRT, VTT and supported timestamp JSON, validates folders and exports SRT. `samples/synthetic` contains fabricated captions and an original generated sine tone.

What the tests cover:

- `parsers.test.mjs`, `smoke.test.mjs`: core parsers and the end-to-end path on synthetic folders (discover job folder, parse, normalize, validate, export SRT, reparse), including `samples/synthetic`, CRLF/BOM input, `,`/`.` millisecond separators, VTT headers/NOTE/STYLE/cue settings and overlap warnings.
- `panels.smoke.test.mjs`: the parser and job-discovery JavaScript embedded in the After Effects JSX and in the Premiere `main.js`, loaded under Node with small fake host objects (ExtendScript `File`/`Folder`, UXP storage, Premiere project, DOM), plus a check that `manifest.json` is valid and references existing files.
- `regressions.test.mjs`: fixed defects.

Not covered: anything that needs the Adobe hosts (footage import, layer creation, Premiere caption tracks, UXP permissions). The tests never execute Adobe APIs. The Premiere `src/*.ts` helpers are not part of `npm run build` and are not loaded by the panel (`index.html` loads the standalone `main.js`).

## After Effects ScriptUI

Close unrelated work. In an empty test project, run `apps/after-effects-typecast-sync/src/TypecastShortsSync.jsx` using File → Scripts → Run Script File. Keep the three included JSX helper files beside it. To dock the panel, copy that complete source folder into the application ScriptUI Panels directory and restart After Effects. Select a test composition and the synthetic folder before generating caption layers. No manifest is needed for a ScriptUI panel. It modifies the selected composition and may adjust its duration.

## Premiere UXP

Install Adobe UXP Developer Tool separately and load `apps/premiere-typecast-sync/src/manifest.json` as a development plugin. The manifest targets Premiere Pro 25.6+, requires local filesystem access and points to the colocated index.html. This is development installation, not a signed marketplace package. Use the synthetic folder in a blank test project. Caption generation uses SRT fallback where native public DOM support is unavailable. Adobe runtime behavior has not been verified by this public packaging pass.

See [limitations](docs/limitations.md), [workflow](docs/mvp-workflow.md), and [file formats](docs/typecast-file-format.md). MIT covers user-authored code and synthetic sample; external host software and user-supplied media retain separate terms.
