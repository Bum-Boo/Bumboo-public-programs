# Development guide

## Architecture

Python 3.11+ and PySide6 Essentials for a native QWidget application. Use QPainter
for the limited animated canvas, standard accessible Qt controls for interactions,
QProcess for CAVA, and a background worker for filesystem collectors. No browser,
AI model or network service is needed at runtime. GUI work stays on the Qt thread.
The controller is a QObject; collector results enter its decorated Slot through
Qt's queued connection. Discard results whose configured source has since changed.
Cache scaled sprites. Idle updates are approximately 6fps, working/celebration
12fps, and live audio at most 24fps; hidden stages skip repaint requests.

- `models.py`: normalized task and event contracts, truthful state mapping.
- `sources.py`: bounded read-only agent-task and generic event adapters.
- `audio.py`: CAVA child process, framing, startup/error/restart/stop lifecycle.
- `config.py`: validated user settings and atomic persistence.
- `theme.py`: color tokens and Qt styling.
- `widgets.py`: character stage, spectrum and draggable companion.
- `app.py`: control window, settings, tray and application lifecycle.
- `cli.py`: launch, doctor and structured event entry point.

User files use XDG config/data/state locations. Public defaults contain no personal
paths. The local setup can point to an `agent-task` records directory; it never
needs arbitrary vault access. Do not rewrite existing task records or agent hooks.

## Source semantics

An active task with a valid lease is **recorded as active**, not independently
proven to have a live process. Expired lease -> stale / 확인 필요. Explicit finish
-> recorded complete. First-run old completions do not cause notification storms.
The agent-task writer uses `completed`; the adapter also accepts `complete`.
Owners may be null on finished records. Bounded reads isolate malformed inputs:
256KiB per record and at most 512 records per source; show the most recent 14 days
plus valid active leases. The window renders at most 100 history rows.
New completion -> short visible cue, optional tray notice, result/handoff actions.
Malformed files produce bounded diagnostics and do not erase otherwise valid tasks.
No arbitrary shell commands or network URLs from event files are executed.

A generic `grimoire event` adapter supports working/done/attention/error/idle and
a local artifact/handoff path. Producers should refresh running events. Future
remote adapters must use explicit bounded status APIs; no recurrent SSH scans.

## Audio

Use [CAVA](https://github.com/karlstav/cava)'s documented raw 8-bit binary output.
Keep partial frames across reads, limit buffering, and handle process exit.
Target system playback monitor through PipeWire's PulseAudio compatibility layer,
never the default microphone. Silence has a static baseline. Missing CAVA is an
honest unavailable state; demo signals are explicitly labeled and isolated.
Only one app instance / CAVA child; close and disable terminate the child.

## Verification budget

Focused unit tests: stale/completion precedence, damaged input, stream framing,
configuration bounds, event writing. One native smoke suite: pages/settings,
drag/persistence, tray recovery, source event -> character -> artifact flow,
real CAVA signal and child cleanup. Small CPU/RSS sample. Re-run only affected
checks after fixes. Keep exact command, exit status and limitations in evidence.

## Extensibility

Adapters return normalized tasks. Themes use token dictionaries. Skin packs use
an image and JSON grid metadata, never executable code. Validate image dimensions
before decoding (4096px per side, 8MP total, 24MB file); require an idle fallback.
Text artifacts use the native read-only viewer with a 2MB cap. Other permitted
documents use desktop associations. Never execute commands embedded in records.
Settings version must allow adding fields without discarding unknown future fields.
Package editable install and wheel; CI uses synthetic data and offscreen Qt.

## Dependencies and license

Project code/original artwork: MIT. PySide6/Qt: upstream LGPL/GPL/commercial
terms (installed separately, unmodified, dynamically loaded). CAVA: MIT, separate
executable. Consult `THIRD_PARTY.md`; preserve third-party notices when bundling.
