"""Optional per-session KWin effect savings, with an exact list for restoration."""

import json
import os
import subprocess
from pathlib import Path

from .hardware import atomic_json

EFFECTS = ("blur", "contrast", "translucency")


def state_path():
    base = Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state")))
    return base / "freiren-quiet/effects.json"


def call(method, *args):
    result = subprocess.run(
        ["qdbus6", "org.kde.KWin", "/Effects", f"org.kde.kwin.Effects.{method}", *args],
        capture_output=True,
        text=True,
        timeout=3,
        check=True,
    )
    return result.stdout.strip()


def set_savings(enabled):
    path = state_path()
    if enabled:
        if path.exists():
            return
        loaded = [effect for effect in EFFECTS if call("isEffectLoaded", effect) == "true"]
        atomic_json(path, {"restore": loaded})
        try:
            for effect in loaded:
                call("unloadEffect", effect)
                if call("isEffectLoaded", effect) != "false":
                    raise RuntimeError(f"효과 비활성화 실패: {effect}")
        except Exception:
            set_savings(False)
            raise
    elif path.exists():
        data = json.loads(path.read_text())
        for effect in data["restore"]:
            if effect not in EFFECTS:
                raise ValueError("복원할 효과 목록이 올바르지 않습니다.")
            if call("isEffectLoaded", effect) != "true" and call("loadEffect", effect) != "true":
                raise RuntimeError(f"효과 복원 실패: {effect}")
        path.unlink()
