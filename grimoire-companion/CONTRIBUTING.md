# Contributing

Start with [docs/START_HERE.md](docs/START_HERE.md). Keep colors in theme.py and
source adapters independent of UI and character assets. Use synthetic tasks for
examples and screenshots. Explain observable behavior, the reason for the change,
and the focused verification performed.

Run `pytest -q`, `ruff check src tests tools`, and an offscreen demo render.
Native integration changes also need the relevant part of `tools/smoke_native.py`
on an actual desktop. Do not repeatedly run the full suite for documentation changes.

Bug reports should identify OS/session, app/CAVA versions, exact steps, expected
and observed results. Review screenshots and logs before sharing; runtime data
can be personal. Never submit a knowledge vault, transcript or character pack
without the right to distribute it.

Do not mark an adapter as supporting an agent merely because it can detect a
process name. Use explicit state, timestamp, source, expiry and artifact contracts.
