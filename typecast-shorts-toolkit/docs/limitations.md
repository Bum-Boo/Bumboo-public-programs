# Known Limitations

## Premiere Pro UXP Caption Creation

Adobe's public Premiere Pro UXP documentation currently exposes project import APIs and sequence caption track inspection APIs, including `Project.importFiles`, `Sequence.getCaptionTrack`, and `Sequence.getCaptionTrackCount`. The documented `CaptionTrack` API exposes track metadata and track item reads, but not a stable public cue creation method.

Because of that, the Premiere MVP uses the closest reliable workflow:

1. Parse and normalize cues.
2. Generate `typecast_sync_fallback.srt`.
3. Try to import audio and SRT into the project.
4. Show the manual step to place audio at `00:00` and use/import the SRT as captions if direct placement is unavailable.

References:

- Adobe Premiere Pro UXP API overview: https://developer.adobe.com/premiere-pro/uxp/resources/fundamentals/apis/
- Adobe Premiere Pro UXP `Project.importFiles`: https://developer.adobe.com/premiere-pro/uxp/ppro-reference/classes/project
- Adobe Premiere Pro UXP `Sequence` caption track methods: https://developer.adobe.com/premiere-pro/uxp/ppro-reference/classes/sequence
- Adobe Premiere Pro UXP `CaptionTrack`: https://developer.adobe.com/premiere-pro/uxp/ppro-reference/classes/captiontrack

## After Effects Runtime Parser

After Effects ScriptUI runs ExtendScript/JSX rather than modern TypeScript modules. The AE panel includes an ExtendScript-compatible parser implementation aligned with the shared TypeScript core. The shared core remains the tested source of parser behavior; a later build step can generate the JSX include automatically from the core package.

## Styling

The MVP does not implement caption style presets, word-by-word highlighting, animation, B-roll selection, rendering, exporting, or uploading.
