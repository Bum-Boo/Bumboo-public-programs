# Typecast Shorts Sync for After Effects

ScriptUI panel name: **Typecast Shorts Sync**.

## Install

1. Copy these files into the After Effects `ScriptUI Panels` folder:
   - `TypecastShortsSync.jsx`
   - `aeLayerUtils.jsx`
   - `aeImportUtils.jsx`
   - `aeCaptionGenerator.jsx`
2. Restart After Effects.
3. Open the panel from `Window > TypecastShortsSync.jsx`.

Typical Windows panel folder:

```text
C:\Program Files\Adobe\Adobe After Effects <version>\Support Files\Scripts\ScriptUI Panels
```

## Usage

1. Open your AE project.
2. Select the template composition in the Project panel or make it the active comp.
3. Optionally include a text layer named `CAPTION_TEMPLATE`.
4. Optionally include a placeholder layer named `VOICE_HERE`.
5. Click `Select Typecast Folder`.
6. Click `Generate Captions`.

The script imports `voice.wav` or `voice.mp3`, places it at time `0`, deletes existing `CAPTION_AUTO_` layers, and creates one timed text layer per cue.

## Notes

- If `CAPTION_TEMPLATE` exists, it is duplicated so its styling is preserved where After Effects exposes it through layer duplication.
- If no template exists, the script creates simple centered lower-third text layers.
- `script.txt` alone is not enough for accurate sync. Use `captions.srt`, `captions.vtt`, or timestamped `typecast.json`.
