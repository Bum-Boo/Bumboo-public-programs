"""Data-only sprite packs. Cropping occurs during rendering, never executes pack code."""

import json
from pathlib import Path

from PySide6.QtCore import QRect
from PySide6.QtGui import QImageReader, QPixmap

from .models import STATES


class Skin:
    def __init__(self, path=""):
        self.name = "작은 마법서"
        self.frames = {}
        self.error = ""
        if not path:
            return
        try:
            manifest = Path(path).expanduser().resolve(strict=True)
            if manifest.stat().st_size > 16384:
                raise ValueError("Large manifest")
            data = json.loads(manifest.read_text())
            if not isinstance(data, dict):
                raise ValueError("Manifest must be an object")
            if data.get("schema") != 1:
                raise ValueError("Unsupported skin")
            image = (manifest.parent / data["image"]).resolve(strict=True)
            if not image.is_relative_to(manifest.parent) or image.stat().st_size > 24_000_000:
                raise ValueError("Image must be inside pack and below 24MB")
            columns, rows = data.get("columns", 1), data.get("rows", 1)
            if not all(isinstance(v, int) and 1 <= v <= 8 for v in (columns, rows)):
                raise ValueError("Invalid grid")
            reader = QImageReader(str(image))
            size = reader.size()
            if (
                not size.isValid()
                or size.width() > 4096
                or size.height() > 4096
                or size.width() * size.height() > 8_000_000
            ):
                raise ValueError("Image too large")
            canvas = reader.read()
            if canvas.isNull() or canvas.width() < columns or canvas.height() < rows:
                raise ValueError("Invalid image")
            w, h = canvas.width() // columns, canvas.height() // rows
            states = data.get("states", {"idle": 0})
            if not isinstance(states, dict):
                raise ValueError("States must be an object")
            for state, index in states.items():
                if (
                    state not in STATES
                    or not isinstance(index, int)
                    or not 0 <= index < rows * columns
                ):
                    raise ValueError("Invalid state")
                self.frames[state] = QPixmap.fromImage(
                    canvas.copy(QRect(index % columns * w, index // columns * h, w, h))
                )
            if "idle" not in self.frames:
                raise ValueError("Skin must have idle frame")
            self.name = str(data.get("name", "동반자"))[:60]
        except (ValueError, OSError, KeyError, TypeError):
            self.error = "캐릭터 파일을 읽지 못해 기본 마법서를 보여요."
            self.frames = {}

    def frame(self, state):
        return self.frames.get(state, self.frames.get("idle"))
