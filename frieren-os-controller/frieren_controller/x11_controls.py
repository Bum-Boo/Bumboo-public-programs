"""Bounded EWMH window layouts and supported XInput2 pointer settings."""

from __future__ import annotations

import hashlib
import os
import struct
from contextlib import contextmanager

from .core import ControllerError
from .desktop_common import SessionBus, boolean, choice, fields, integer, wait_for


@contextmanager
def connection():
    if os.environ.get("XDG_SESSION_TYPE", "x11") != "x11":
        raise ControllerError("이 창 배치와 입력 제어는 현재 X11 세션에서 사용할 수 있어요.")
    from Xlib import display, error

    try:
        bus = display.Display()
        try:
            yield bus
        finally:
            bus.close()
    except (error.XError, error.DisplayConnectionError, OSError) as exc:
        raise ControllerError("화면이나 입력 장치 연결이 바뀌었어요. 다시 확인해 주세요.") from exc


def prop(bus, window, key):
    from Xlib import X

    atom = bus.intern_atom(key, only_if_exists=True)
    value = window.get_full_property(atom, X.AnyPropertyType) if atom else None
    return value.value if value is not None else None


def text_property(bus, window, key):
    value = prop(bus, window, key)
    return bytes(value).decode("utf-8", errors="replace").rstrip("\x00") if value is not None else ""


def send(bus, window, key, values):
    from Xlib import X, protocol

    event = protocol.event.ClientMessage(
        window=window, client_type=bus.intern_atom(key), data=(32, values + [0] * (5 - len(values)))
    )
    bus.screen().root.send_event(event, event_mask=X.SubstructureRedirectMask | X.SubstructureNotifyMask)
    bus.sync()


class WindowControls:
    def status(self):
        from Xlib import error

        with connection() as bus:
            root = bus.screen().root
            desktop = int((prop(bus, root, "_NET_CURRENT_DESKTOP") or [0])[0])
            names = text_property(bus, root, "_NET_DESKTOP_NAMES").split("\x00")
            count = int((prop(bus, root, "_NET_NUMBER_OF_DESKTOPS") or [1])[0])
            areas = list(
                prop(bus, root, "_NET_WORKAREA")
                or [0, 0, bus.screen().width_in_pixels, bus.screen().height_in_pixels]
            )
            area = areas[desktop * 4 : desktop * 4 + 4] or areas[:4]
            windows = []
            for xid in prop(bus, root, "_NET_CLIENT_LIST") or []:
                window = bus.create_resource_object("window", int(xid))
                try:
                    classes = window.get_wm_class() or ("", "")
                    kinds = prop(bus, window, "_NET_WM_WINDOW_TYPE") or []
                    if kinds and bus.intern_atom("_NET_WM_WINDOW_TYPE_NORMAL") not in kinds:
                        continue
                    geometry = window.get_geometry()
                    xy = root.translate_coords(window, 0, 0)
                    extents = list(prop(bus, window, "_NET_FRAME_EXTENTS") or [0, 0, 0, 0])
                    pid = int((prop(bus, window, "_NET_WM_PID") or [0])[0])
                    uid = text_property(bus, window, "_KDE_NET_WM_UUID")
                    fingerprint = hashlib.sha256(f"{xid}:{pid}:{uid}:{classes}".encode()).hexdigest()
                    states = list(prop(bus, window, "_NET_WM_STATE") or [])
                    windows.append(
                        {
                            "id": int(xid),
                            "fingerprint": fingerprint,
                            "name": text_property(bus, window, "_NET_WM_NAME")
                            or window.get_wm_name()
                            or classes[-1],
                            "app": classes[-1],
                            "instance": classes[0],
                            "desktop": int((prop(bus, window, "_NET_WM_DESKTOP") or [desktop])[0]),
                            "rect": {
                                "x": xy.x - extents[0],
                                "y": xy.y - extents[2],
                                "width": geometry.width + extents[0] + extents[1],
                                "height": geometry.height + extents[2] + extents[3],
                            },
                            "maximized": [
                                bus.get_atom_name(s)
                                for s in states
                                if bus.get_atom_name(s).startswith("_NET_WM_STATE_MAXIMIZED_")
                            ],
                        }
                    )
                except error.XError:
                    continue
            return {
                "windows": windows,
                "desktops": [
                    {"id": i, "name": names[i] if i < len(names) else str(i + 1)} for i in range(count)
                ],
                "current_desktop": desktop,
                "workarea": dict(zip(("x", "y", "width", "height"), area, strict=True)),
            }

    def validate(self, settings):
        values = fields(settings, {"windows", "rules", "current_desktop", "desktop_names"})
        state = self.status()
        count = len(state["desktops"])
        if "current_desktop" in values:
            integer(values["current_desktop"], 0, count - 1, "작업 공간")
        if "desktop_names" in values:
            names = values["desktop_names"]
            if (
                not isinstance(names, list)
                or len(names) != count
                or any(
                    not isinstance(n, str) or not 1 <= len(n) <= 60 or any(c in n for c in "\x00\n\r")
                    for n in names
                )
            ):
                raise ControllerError("작업 공간 이름을 확인해 주세요.")
        for key in ("windows", "rules"):
            if key not in values:
                continue
            rows = values[key]
            if not isinstance(rows, list) or not 1 <= len(rows) <= 40:
                raise ControllerError("배치할 창을 선택해 주세요.")
            for row in rows:
                allowed = (
                    {"id", "fingerprint", "desktop", "placement", "rect"}
                    if key == "windows"
                    else {"app", "instance", "ordinal", "desktop", "placement", "rect"}
                )
                required = ("id", "fingerprint") if key == "windows" else ("app",)
                fields(row, allowed, required)
                if key == "windows":
                    if not any(
                        w["id"] == row["id"] and w["fingerprint"] == row["fingerprint"]
                        for w in state["windows"]
                    ):
                        raise ControllerError("선택한 창이 바뀌었어요. 다시 선택해 주세요.")
                elif any(
                    not isinstance(row[k], str) or not 1 <= len(row[k]) <= 150 or "\x00" in row[k]
                    for k in ("app", "instance")
                    if k in row
                ):
                    raise ControllerError("앱 이름을 확인해 주세요.")
                if "ordinal" in row:
                    integer(row["ordinal"], 0, 39, "같은 앱의 창 순서")
                if not {"desktop", "placement", "rect"} & set(row):
                    raise ControllerError("창 위치나 작업 공간을 선택해 주세요.")
                if "desktop" in row:
                    if row["desktop"] != 2**32 - 1:
                        integer(row["desktop"], 0, count - 1, "창의 작업 공간")
                if "placement" in row and "rect" in row:
                    raise ControllerError("배치 방식과 직접 위치는 하나만 선택해 주세요.")
                if "placement" in row:
                    choice(row["placement"], ("left", "right", "top", "bottom", "maximize"))
                if "rect" in row:
                    rect = fields(row["rect"], {"x", "y", "width", "height"}, ("x", "y", "width", "height"))
                    integer(rect["width"], 200, 16000, "창 너비")
                    integer(rect["height"], 150, 16000, "창 높이")
                    integer(rect["x"], -16000, 16000, "창 가로 위치")
                    integer(rect["y"], -16000, 16000, "창 세로 위치")
                    area = state["workarea"]
                    if (
                        rect["x"] + rect["width"] <= area["x"] + 40
                        or rect["y"] + rect["height"] <= area["y"] + 40
                        or rect["x"] >= area["x"] + area["width"] - 40
                        or rect["y"] >= area["y"] + area["height"] - 40
                    ):
                        raise ControllerError("창이 화면 안에 보이도록 위치를 선택해 주세요.")
        if "windows" in values and "rules" in values:
            raise ControllerError("현재 창과 앱 배치 규칙은 하나씩 적용해 주세요.")
        return values

    def _resolve(self, settings, state):
        if "windows" in settings:
            return settings["windows"]
        rows = []
        for rule in settings.get("rules", []):
            matches = [
                w
                for w in state["windows"]
                if w["app"] == rule["app"] and ("instance" not in rule or w["instance"] == rule["instance"])
            ]
            if not matches:
                raise ControllerError(f"{rule['app']} 창을 먼저 열어 주세요.")
            if "ordinal" in rule:
                if rule["ordinal"] >= len(matches):
                    raise ControllerError(f"{rule['app']}의 저장한 창을 먼저 열어 주세요.")
                matches = [matches[rule["ordinal"]]]
            for window in matches:
                rows.append(
                    {
                        "id": window["id"],
                        "fingerprint": window["fingerprint"],
                        **{k: v for k, v in rule.items() if k not in ("app", "instance", "ordinal")},
                    }
                )
        return rows

    def capture(self, settings):
        state = self.status()
        result = {"windows": []}
        for row in self._resolve(settings, state):
            window = next(
                w for w in state["windows"] if w["id"] == row["id"] and w["fingerprint"] == row["fingerprint"]
            )
            result["windows"].append(
                {k: window[k] for k in ("id", "fingerprint", "rect", "desktop", "maximized")}
            )
        if "current_desktop" in settings:
            result["current_desktop"] = state["current_desktop"]
        if "desktop_names" in settings:
            result["desktop_names"] = [d["name"] for d in state["desktops"]]
        return result

    def comparable(self, snapshot):
        live = {(w["id"], w["fingerprint"]) for w in self.status()["windows"]}
        return {
            **snapshot,
            "windows": [w for w in snapshot["windows"] if (w["id"], w["fingerprint"]) in live],
        }

    def read_snapshot(self, snapshot):
        state = self.status()
        live = {(w["id"], w["fingerprint"]): w for w in state["windows"]}
        result = {"windows": []}
        for saved in snapshot["windows"]:
            row = live.get((saved["id"], saved["fingerprint"]))
            if row:
                result["windows"].append({k: row[k] for k in saved})
        if "current_desktop" in snapshot:
            result["current_desktop"] = state["current_desktop"]
        if "desktop_names" in snapshot:
            result["desktop_names"] = [d["name"] for d in state["desktops"]]
        return result

    @staticmethod
    def _rect(row, area):
        rect = dict(row.get("rect") or area)
        placement = row.get("placement")
        if placement in ("left", "right"):
            rect["width"] //= 2
            if placement == "right":
                rect["x"] += rect["width"]
        if placement in ("top", "bottom"):
            rect["height"] //= 2
            if placement == "bottom":
                rect["y"] += rect["height"]
        return rect

    def apply(self, settings):
        from Xlib import X

        values = self.validate(settings)
        state = self.status()
        rows = self._resolve(values, state)
        with connection() as bus:
            for row in rows:
                window = bus.create_resource_object("window", row["id"])
                if "desktop" in row:
                    send(bus, window, "_NET_WM_DESKTOP", [row["desktop"], 2])
                if "placement" in row or "rect" in row:
                    maximize = row.get("placement") == "maximize"
                    send(
                        bus,
                        window,
                        "_NET_WM_STATE",
                        [
                            1 if maximize else 0,
                            bus.intern_atom("_NET_WM_STATE_MAXIMIZED_HORZ"),
                            bus.intern_atom("_NET_WM_STATE_MAXIMIZED_VERT"),
                            2,
                        ],
                    )
                    if not maximize:
                        wait_for(
                            lambda row=row: next(
                                (
                                    w["maximized"]
                                    for w in self.status()["windows"]
                                    if w["id"] == row["id"] and w["fingerprint"] == row["fingerprint"]
                                ),
                                None,
                            ),
                            [],
                        )
                        rect = self._rect(row, state["workarea"])
                        extents = list(prop(bus, window, "_NET_FRAME_EXTENTS") or [0, 0, 0, 0])
                        send(
                            bus,
                            window,
                            "_NET_MOVERESIZE_WINDOW",
                            [
                                X.NorthWestGravity | (15 << 8) | (2 << 12),
                                rect["x"],
                                rect["y"],
                                rect["width"] - extents[0] - extents[1],
                                rect["height"] - extents[2] - extents[3],
                            ],
                        )
            root = bus.screen().root
            if "current_desktop" in values:
                send(bus, root, "_NET_CURRENT_DESKTOP", [values["current_desktop"], X.CurrentTime])
            if "desktop_names" in values:
                root.change_property(
                    bus.intern_atom("_NET_DESKTOP_NAMES"),
                    bus.intern_atom("UTF8_STRING"),
                    8,
                    "\x00".join(values["desktop_names"]).encode() + b"\x00",
                )
                bus.sync()
        # KWin applies EWMH asynchronously; verify identities and destinations before returning.
        if "current_desktop" in values:
            wait_for(lambda: self.status()["current_desktop"], values["current_desktop"])
        if "desktop_names" in values:
            wait_for(lambda: [d["name"] for d in self.status()["desktops"]], values["desktop_names"])
        for row in rows:
            if "placement" in row or "rect" in row:

                def geometry_ok(row=row):
                    window = next(
                        (
                            w
                            for w in self.status()["windows"]
                            if w["id"] == row["id"] and w["fingerprint"] == row["fingerprint"]
                        ),
                        None,
                    )
                    if not window:
                        return False
                    if row.get("placement") == "maximize":
                        return len(window["maximized"]) == 2
                    rect = self._rect(row, state["workarea"])
                    return not window["maximized"] and all(
                        abs(window["rect"][k] - v) <= 2 for k, v in rect.items()
                    )

                wait_for(geometry_ok, True)
            if "desktop" in row:
                wait_for(
                    lambda row=row: next(
                        (
                            w["desktop"]
                            for w in self.status()["windows"]
                            if w["id"] == row["id"] and w["fingerprint"] == row["fingerprint"]
                        ),
                        None,
                    ),
                    row["desktop"],
                )

    def restore(self, snapshot):
        snapshot = self.comparable(snapshot)
        settings = {k: snapshot[k] for k in ("current_desktop", "desktop_names") if k in snapshot}
        rows = []
        for row in snapshot["windows"]:
            item = {k: row[k] for k in ("id", "fingerprint", "rect")}
            if row["desktop"] != 2**32 - 1:
                item["desktop"] = row["desktop"]
            rows.append(item)
        if rows:
            settings["windows"] = rows
        if settings:
            self.apply(settings)
        with connection() as bus:
            for row in snapshot["windows"]:
                window = bus.create_resource_object("window", row["id"])
                if row["desktop"] == 2**32 - 1:
                    send(bus, window, "_NET_WM_DESKTOP", [row["desktop"], 2])
                for name in row["maximized"]:
                    send(bus, window, "_NET_WM_STATE", [1, bus.intern_atom(name), 0, 2])


POINTER_PROPERTIES = {
    "speed": "libinput Accel Speed",
    "acceleration": "libinput Accel Profile Enabled",
    "natural_scroll": "libinput Natural Scrolling Enabled",
    "tap": "libinput Tapping Enabled",
    "disable_while_typing": "libinput Disable While Typing Enabled",
}


def device_property(bus, identifier, key):
    from Xlib import X

    atom = bus.intern_atom(key, only_if_exists=True)
    if not atom:
        return None
    value = bus.xinput_get_device_property(identifier, atom, X.AnyPropertyType, 0, 64)
    if not value.type or value.value is None:
        return None
    form, contents = value.value
    return {"type": bus.get_atom_name(value.type), "format": form, "values": list(contents)}


class InputControls:
    def __init__(self, bus=None):
        self.bus = bus or SessionBus()

    def _pointers(self):
        from Xlib.ext import xinput

        rows = []
        with connection() as bus:
            for device in bus.xinput_query_device(xinput.AllDevices).devices:
                if device.use != xinput.SlavePointer:
                    continue
                properties = {
                    key: device_property(bus, device.deviceid, name)
                    for key, name in POINTER_PROPERTIES.items()
                }
                properties = {k: v for k, v in properties.items() if v is not None}
                if not properties:
                    continue
                product = device_property(bus, device.deviceid, "Device Product ID")
                fingerprint = hashlib.sha256(f"{device.name}:{product}".encode()).hexdigest()
                values = {}
                for key, row in properties.items():
                    if key == "speed":
                        speed = struct.unpack("=f", struct.pack("=I", row["values"][0]))[0]
                        values[key] = round(speed * 100)
                    elif key == "acceleration":
                        values[key] = "adaptive" if row["values"][0] else "flat"
                    else:
                        values[key] = bool(row["values"][0])
                available = device_property(bus, device.deviceid, "libinput Accel Profiles Available")
                rows.append(
                    {
                        "id": device.deviceid,
                        "name": device.name,
                        "fingerprint": fingerprint,
                        "values": values,
                        "raw": properties,
                        "acceleration_choices": [
                            name
                            for i, name in enumerate(("adaptive", "flat"))
                            if available and i < len(available["values"]) and available["values"][i]
                        ],
                    }
                )
        return rows

    def _actions(self):
        actions = []
        for component in (
            "kwin",
            "plasmashell",
            "org.kde.krunner.desktop",
            "org.kde.konsole.desktop",
            "kmix",
        ):
            rows = self.bus.call(
                "org.kde.kglobalaccel",
                "/kglobalaccel",
                "org.kde.KGlobalAccel",
                "allActionsForComponent",
                "(as)",
                ([component, "", "", ""],),
            )
            for row in rows:
                if len(row) != 4:
                    continue
                keys = self.bus.call(
                    "org.kde.kglobalaccel",
                    "/kglobalaccel",
                    "org.kde.KGlobalAccel",
                    "shortcut",
                    "(as)",
                    (row,),
                )
                actions.append(
                    {
                        "component": row[0],
                        "action": row[1],
                        "name": row[3] or row[1],
                        "action_id": row,
                        "keys": keys,
                        "sequence": sequence_text(keys),
                    }
                )
        return actions

    def status(self):
        return {"pointers": self._pointers(), "shortcuts": self._actions()}

    def validate(self, settings):
        values = fields(settings, {"pointer", "shortcut"})
        if len(values) != 1:
            raise ControllerError("입력 장치와 단축키는 하나씩 적용해 주세요.")
        if "pointer" in values:
            row = fields(values["pointer"], {"id", "fingerprint", *POINTER_PROPERTIES}, ("id", "fingerprint"))
            device = next(
                (
                    p
                    for p in self._pointers()
                    if p["id"] == row["id"] and p["fingerprint"] == row["fingerprint"]
                ),
                None,
            )
            if not device or len(row) < 3:
                raise ControllerError("입력 장치가 바뀌었어요. 다시 선택해 주세요.")
            for key in set(row) - {"id", "fingerprint"}:
                if key not in device["values"]:
                    raise ControllerError("이 장치가 지원하지 않는 설정이에요.")
                if key == "speed":
                    integer(row[key], -100, 100, "포인터 속도")
                elif key == "acceleration":
                    choice(row[key], device["acceleration_choices"], "가속 방식")
                else:
                    boolean(row[key])
        else:
            row = fields(
                values["shortcut"], {"component", "action", "sequence"}, ("component", "action", "sequence")
            )
            if not any(
                a["component"] == row["component"] and a["action"] == row["action"] for a in self._actions()
            ):
                raise ControllerError("기존 단축키 동작을 다시 선택해 주세요.")
            keys = sequence_keys(row["sequence"])
            self._check_keys(row["component"], row["action"], keys)
        return values

    def _check_keys(self, component, action, keys):
        for key in keys:
            rows = self.bus.call(
                "org.kde.kglobalaccel",
                "/kglobalaccel",
                "org.kde.KGlobalAccel",
                "getGlobalShortcutsByKey",
                "(i)",
                (key,),
            )
            if any(row[0] != component or row[4] != action for row in rows):
                raise ControllerError("다른 동작이 쓰는 단축키예요. 다른 키를 선택해 주세요.")

    def capture(self, settings):
        if "pointer" in settings:
            wanted = settings["pointer"]
            device = next(
                (
                    p
                    for p in self._pointers()
                    if p["id"] == wanted["id"] and p["fingerprint"] == wanted["fingerprint"]
                ),
                None,
            )
            if not device:
                raise ControllerError("입력 장치 연결이 바뀌었어요.")
            return {
                "pointer": {
                    "id": wanted["id"],
                    "fingerprint": wanted["fingerprint"],
                    "properties": {k: device["raw"][k] for k in wanted if k in POINTER_PROPERTIES},
                }
            }
        wanted = settings["shortcut"]
        action = next(
            a
            for a in self._actions()
            if a["component"] == wanted["component"] and a["action"] == wanted["action"]
        )
        return {"shortcut": {"action_id": action["action_id"], "keys": action["keys"]}}

    def _write_pointer(self, row):
        from Xlib import X

        live = next(
            (p for p in self._pointers() if p["id"] == row["id"] and p["fingerprint"] == row["fingerprint"]),
            None,
        )
        if not live:
            raise ControllerError("입력 장치 연결이 바뀌었어요.")
        with connection() as bus:
            for key, value in row["properties"].items():
                bus.xinput_change_device_property(
                    row["id"],
                    bus.intern_atom(POINTER_PROPERTIES[key]),
                    bus.intern_atom(value["type"]),
                    X.PropModeReplace,
                    (value["format"], value["values"]),
                )
            bus.sync()
        current = self.capture(
            {
                "pointer": {
                    "id": row["id"],
                    "fingerprint": row["fingerprint"],
                    **{k: 0 for k in row["properties"]},
                }
            }
        )
        if current["pointer"] != row:
            raise ControllerError("변경한 입력 설정을 확인하지 못했어요.")

    def apply(self, settings):
        values = self.validate(settings)
        if "pointer" in values:
            snapshot = self.capture(values)["pointer"]
            for key, value in values["pointer"].items():
                if key not in POINTER_PROPERTIES:
                    continue
                if key == "speed":
                    snapshot["properties"][key]["values"] = [
                        struct.unpack("=I", struct.pack("=f", value / 100))[0]
                    ]
                elif key == "acceleration":
                    count = len(snapshot["properties"][key]["values"])
                    snapshot["properties"][key]["values"] = [
                        int(value == "adaptive"),
                        int(value == "flat"),
                    ] + [0] * (count - 2)
                else:
                    snapshot["properties"][key]["values"] = [int(value)]
            self._write_pointer(snapshot)
        else:
            snapshot = self.capture(values)["shortcut"]
            keys = sequence_keys(values["shortcut"]["sequence"])
            actual = self.bus.call(
                "org.kde.kglobalaccel",
                "/kglobalaccel",
                "org.kde.KGlobalAccel",
                "setShortcut",
                "(asaiu)",
                (snapshot["action_id"], keys, 4),
            )
            if actual != keys:
                raise ControllerError("선택한 단축키를 적용하지 못했어요.")

    def restore(self, snapshot):
        if "pointer" in snapshot:
            self._write_pointer(snapshot["pointer"])
        else:
            row = snapshot["shortcut"]
            self._check_keys(row["action_id"][0], row["action_id"][1], row["keys"])
            actual = self.bus.call(
                "org.kde.kglobalaccel",
                "/kglobalaccel",
                "org.kde.KGlobalAccel",
                "setShortcut",
                "(asaiu)",
                (row["action_id"], row["keys"], 4),
            )
            if actual != row["keys"]:
                raise ControllerError("원래 단축키를 복원하지 못했어요.")


MODIFIERS = {"Shift": 0x02000000, "Ctrl": 0x04000000, "Alt": 0x08000000, "Meta": 0x10000000}
SPECIAL_KEYS = {
    "Escape": 0x01000000,
    "Tab": 0x01000001,
    "Backspace": 0x01000003,
    "Return": 0x01000004,
    "Enter": 0x01000005,
    "Delete": 0x01000007,
    "Home": 0x01000010,
    "End": 0x01000011,
    "Left": 0x01000012,
    "Up": 0x01000013,
    "Right": 0x01000014,
    "Down": 0x01000015,
    "PageUp": 0x01000016,
    "PageDown": 0x01000017,
    "Space": 0x20,
    "Plus": 0x2B,
    **{f"F{i}": 0x01000030 + i - 1 for i in range(1, 36)},
}


def sequence_keys(sequence):
    if not isinstance(sequence, str) or len(sequence) > 80:
        raise ControllerError("단축키는 Meta+Shift+R처럼 입력해 주세요.")
    if not sequence.strip():
        return []
    parts = sequence.strip().split("+")
    key = parts[-1]
    if key in SPECIAL_KEYS:
        number = SPECIAL_KEYS[key]
    elif len(key) == 1 and key.isascii() and key.isalnum():
        number = ord(key.upper())
    else:
        raise ControllerError("단축키는 Meta+Shift+R처럼 입력해 주세요.")
    if len(set(parts[:-1])) != len(parts[:-1]) or any(p not in MODIFIERS for p in parts[:-1]):
        raise ControllerError("단축키 조합을 확인해 주세요.")
    for modifier in parts[:-1]:
        number |= MODIFIERS[modifier]
    if not parts[:-1] and key not in SPECIAL_KEYS:
        raise ControllerError("글자 단축키에는 Ctrl, Alt 또는 Meta를 함께 사용해 주세요.")
    return [number]


def sequence_text(keys):
    labels = []
    for value in keys:
        if not value:
            continue
        key = value & 0x01FFFFFF
        title = next(
            (name for name, code in SPECIAL_KEYS.items() if code == key),
            chr(key) if 32 <= key < 127 else f"키 {key}",
        )
        labels.append("+".join([name for name, mask in MODIFIERS.items() if value & mask] + [title]))
    return ", ".join(labels)
