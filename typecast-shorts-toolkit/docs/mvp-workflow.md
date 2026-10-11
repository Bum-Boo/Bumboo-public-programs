# MVP Workflow

## Shared Core

Run parser tests:

```powershell
npm install
npm test
```

The core package exposes:

- `parseSrt(input)`
- `parseVtt(input)`
- `parseTypecastJson(input)`
- `secondsToTimecode(seconds, fps)`
- `validateJobFolder(path)`
- `discoverTypecastJob(path)`
- `normalizeWhitespace(text)`
- `splitLongCue(text, maxCharsPerLine, maxLines)`

## After Effects

1. Open an AE project with an existing shorts template composition.
2. Select or open the composition.
3. Add an optional text layer named `CAPTION_TEMPLATE`.
4. Add an optional placeholder layer named `VOICE_HERE`.
5. Open `Typecast Shorts Sync`.
6. Select the Typecast job folder.
7. Generate captions.

The panel deletes old `CAPTION_AUTO_` layers, imports voice audio, places it at time `0`, duplicates the template text layer when available, and applies cue `inPoint` and `outPoint` timing.

## Premiere Pro

1. Open a Premiere Pro project and target sequence.
2. Open the UXP panel.
3. Refresh the active sequence.
4. Select the Typecast job folder.
5. Generate captions.

The panel writes `typecast_sync_fallback.srt`, tries to import the voice audio and fallback SRT into the project, and shows the manual final step if Premiere does not create/place captions automatically.
