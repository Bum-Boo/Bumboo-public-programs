"""Recover only desktop connection variables when systemd starts before KDE imports them."""

from __future__ import annotations

import os

import psutil

KEYS = ("DISPLAY", "XAUTHORITY", "WAYLAND_DISPLAY", "XDG_SESSION_TYPE", "XDG_CURRENT_DESKTOP")


def load_desktop_environment():
    if os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
        return
    for process in psutil.process_iter(("name", "uids")):
        try:
            if process.info["name"] not in ("plasmashell", "kwin_x11", "kwin_wayland"):
                continue
            if process.info["uids"].real != os.getuid():
                continue
            environment = process.environ()
            selected = {key: environment[key] for key in KEYS if environment.get(key)}
            if "DISPLAY" in selected or "WAYLAND_DISPLAY" in selected:
                os.environ.update(selected)
                return
        except (psutil.Error, OSError):
            continue
