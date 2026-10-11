# Development records

Keep source history, verification notes, and runtime logs separate:

1. Use Git history for source and design changes.
2. Record commands, observed results, failures, and limitations in release evidence. Use synthetic task data and omit personal paths, prompts, task titles, and screenshots from public records.
3. Runtime JSONL logs stay in the user's XDG state directory. They are bounded and should not contain full task records or document contents.

Tests and logs do not prove the interface works on every desktop. State the tested environment and distinguish actual runtime observations from fixture-based checks. Do not claim audio support from demo signals.
