from __future__ import annotations

FRAME_WIDTH = 192
FRAME_HEIGHT = 208
SPRITE_COLUMNS = 8
SPRITE_ROWS = 9
SPRITESHEET_WIDTH = FRAME_WIDTH * SPRITE_COLUMNS
SPRITESHEET_HEIGHT = FRAME_HEIGHT * SPRITE_ROWS

# Codex pet row contract:
# 0 idle, 1 running-right, 2 running-left, 3 waving, 4 jumping,
# 5 failed, 6 waiting, 7 running/working, 8 review/completed.
_STATUS_ROWS = {
    "idle": 0,
    "working": 7,
    "completed": 8,
    "needs_approval": 6,
    "error": 5,
}


def sprite_row_for_status(status: str) -> int:
    return _STATUS_ROWS.get(status, 0)
