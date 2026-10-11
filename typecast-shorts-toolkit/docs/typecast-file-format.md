# Typecast Job File Format

Each short-form job is expected to be one folder:

```text
short_001/
  voice.wav
  captions.srt
  script.txt
  typecast.json
```

## Required for Accurate Sync

- `voice.wav` or `voice.mp3`
- One timing source:
  - `typecast.json` with timestamped captions or words
  - `captions.srt`
  - `captions.vtt`

`script.txt` is useful reference text, but it cannot produce accurate sync without timing data.

## Timing Priority

1. `typecast.json`, if it contains usable timestamped cue or word data.
2. `captions.srt`.
3. `captions.vtt`.
4. `script.txt`, warning only.

## Normalized Cue Model

```json
{
  "id": 1,
  "startSeconds": 0,
  "endSeconds": 2.4,
  "text": "Caption text",
  "words": [
    {
      "text": "Caption",
      "startSeconds": 0,
      "endSeconds": 0.5
    }
  ]
}
```

## Supported Typecast JSON Shapes

The parser intentionally accepts several common timestamp shapes because Typecast exports can vary by workflow:

```json
{
  "captions": [
    { "start": 0, "end": 1.2, "text": "First caption" },
    { "startSeconds": 1.3, "endSeconds": 2.4, "caption": "Second caption" }
  ]
}
```

Word-level data is grouped into readable cue chunks:

```json
{
  "words": [
    { "word": "Hello", "start": 0, "end": 0.25 },
    { "word": "world.", "start": 0.3, "end": 0.6 }
  ]
}
```

Millisecond-like fields with `_ms` suffix or very large numeric values are normalized to seconds.
