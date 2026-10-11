"""Versioned XDG settings. No personal paths are compiled into the application."""

import json
import os
import tempfile
from pathlib import Path


def location(kind: str) -> Path:
    default = {"config": ".config", "data": ".local/share", "state": ".local/state"}[kind]
    return Path(os.environ.get(f"XDG_{kind.upper()}_HOME", Path.home() / default)) / "grimoire"


DEFAULTS = {
    "schema": 1,
    "theme": "night",
    "audio_enabled": True,
    "companion_visible": True,
    "always_on_top": True,
    "reduced_motion": False,
    "quiet": True,
    "resting": False,
    "scale": 1.0,
    "gain": 1.0,
    "position": None,
    "task_root": "",
    "skin": "",
    "cava_path": "",
    "audio_source": "auto",
}


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(prefix=".grimoire-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def normalize(raw: dict) -> dict:
    result = {**DEFAULTS, **raw}  # Preserve unknown fields for forward-compatible edits.
    for name, default in DEFAULTS.items():
        value = result[name]
        if (
            isinstance(default, bool)
            and not isinstance(value, bool)
            or isinstance(default, str)
            and not isinstance(value, str)
        ):
            result[name] = default
    for name, low, high in [("scale", 0.65, 1.6), ("gain", 0.25, 3.0)]:
        value = result[name]
        if not isinstance(value, (float, int)) or not low <= value <= high:
            result[name] = DEFAULTS[name]
    if result["theme"] not in ("night", "dawn"):
        result["theme"] = "night"
    position = result["position"]
    if not (
        isinstance(position, list)
        and len(position) == 2
        and all(isinstance(v, int) and abs(v) <= 100000 for v in position)
    ):
        result["position"] = None
    source = result["audio_source"]
    if source != "auto" and not (
        source.endswith(".monitor") and all(c.isalnum() or c in "._-" for c in source)
    ):
        result["audio_source"] = "auto"
    return result


class Settings:
    def __init__(self, path: Path | None = None):
        self.path = path or location("config") / "settings.json"
        self.error = ""
        try:
            if self.path.stat().st_size > 65536:
                raise ValueError("Settings too large")
            raw = json.loads(self.path.read_text())
            if not isinstance(raw, dict):
                raise ValueError("Settings must be an object")
        except FileNotFoundError:
            raw = {}
        except (OSError, ValueError):
            raw = {}
            self.error = "설정 파일을 읽지 못해 기본값으로 열었어요."
        self.values = normalize(raw)

    def __getitem__(self, key):
        return self.values[key]

    def update(self, **changes):
        candidate = normalize({**self.values, **changes})
        atomic_json(self.path, candidate)
        self.values = candidate
