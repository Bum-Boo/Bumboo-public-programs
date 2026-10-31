"""Bounded KDE display controls and service-owned recovery/expiry timers."""

from __future__ import annotations

import copy
import json
import math
import re
import subprocess
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

from .core import ControllerError

POWER = "org.kde.Solid.PowerManagement"
POWER_PATH = "/org/kde/Solid/PowerManagement"
BRIGHTNESS = POWER_PATH + "/Actions/BrightnessControl"
POLICY = POWER_PATH + "/PolicyAgent"
NIGHT = "/org/kde/KWin/NightLight"
NIGHT_KEYS = ("Active", "Mode", "DayTemperature", "NightTemperature")
ROTATIONS = {1: "none", 2: "left", 4: "inverted", 8: "right"}
DEFAULTS = {
    "brightness": 80,
    "night_enabled": False,
    "temperature": 4500,
    "scheduled": False,
    "start": "21:00",
    "end": "07:00",
    "auto_brightness": False,
    "ac_brightness": 80,
    "battery_brightness": 50,
}
PRESETS = {
    "work": {**DEFAULTS, "brightness": 80},
    "night": {**DEFAULTS, "brightness": 35, "night_enabled": True, "temperature": 4000},
    "presentation": {**DEFAULTS, "brightness": 100},
    "battery": {**DEFAULTS, "brightness": 50},
}


def integer(value, minimum, maximum, name):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ControllerError(f"{name} 값은 {minimum}~{maximum} 사이 정수로 입력해 주세요.")
    return value


def validate_settings(settings):
    if not isinstance(settings, dict) or set(settings) != set(DEFAULTS):
        raise ControllerError("화면 설정 항목을 확인해 주세요.")
    result = dict(settings)
    for key in ("brightness", "ac_brightness", "battery_brightness"):
        integer(result[key], 5, 100, "밝기")
    integer(result["temperature"], 2500, 6500, "색온도")
    for key in ("night_enabled", "scheduled", "auto_brightness"):
        if type(result[key]) is not bool:
            raise ControllerError("켜기·끄기 값을 확인해 주세요.")
    for key in ("start", "end"):
        if not isinstance(result[key], str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", result[key]):
            raise ControllerError("예약 시각은 21:00처럼 입력해 주세요.")
    if result["scheduled"] and result["start"] == result["end"]:
        raise ControllerError("야간 모드 시작과 종료 시각을 다르게 정해 주세요.")
    return result


def in_schedule(settings, now=None):
    now = (now or datetime.now()).strftime("%H:%M")
    start, end = settings["start"], settings["end"]
    return start <= now < end if start < end else now >= start or now < end


class KDEBackend:
    def __init__(self):
        try:
            from gi.repository import Gio, GLib
        except ImportError as exc:
            raise ControllerError("PyGObject를 불러오지 못해 데스크톱 기능을 쓸 수 없어요.") from exc

        self.Gio, self.GLib = Gio, GLib
        try:
            self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        except GLib.Error as exc:
            # Without a session bus only desktop features are unavailable; callers handle this.
            raise ControllerError("데스크톱 세션 D-Bus에 연결하지 못했어요.") from exc

    def dbus(self, service, path, interface, method, signature=None, args=()):
        try:
            result = self.bus.call_sync(
                service,
                path,
                interface,
                method,
                self.GLib.Variant(signature, args) if signature else None,
                None,
                self.Gio.DBusCallFlags.NONE,
                4000,
                None,
            )
            values = result.unpack()
            return values[0] if len(values) == 1 else values
        except self.GLib.Error as exc:
            raise ControllerError("화면 기능에 연결하지 못했어요. KDE 세션을 확인해 주세요.") from exc

    def command(self, args, timeout=8):
        try:
            result = subprocess.run(args, text=True, capture_output=True, timeout=timeout, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ControllerError("화면 명령을 실행하지 못했어요. 다시 시도해 주세요.") from exc
        if result.returncode:
            raise ControllerError("화면 설정을 적용하지 못했어요. 연결 상태를 확인해 주세요.")
        return result.stdout.strip()

    def brightness(self):
        values = [
            self.dbus(POWER, BRIGHTNESS, POWER + ".Actions.BrightnessControl", key)
            for key in ("brightness", "brightnessMax", "knownSafeBrightnessMin")
        ]
        if values[1] <= 0:
            raise ControllerError("밝기를 조절할 화면을 확인하지 못했어요.")
        return {
            "raw": values[0],
            "maximum": values[1],
            "minimum": values[2],
            "percent": round(values[0] * 100 / values[1]),
        }

    def set_brightness(self, percent=None, raw=None):
        state = self.brightness()
        value = raw if raw is not None else round(percent * state["maximum"] / 100)
        value = max(state["minimum"], min(state["maximum"], value))
        self.dbus(POWER, BRIGHTNESS, POWER + ".Actions.BrightnessControl", "setBrightness", "(i)", (value,))
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            if abs(self.brightness()["raw"] - value) <= 1:
                return
            time.sleep(0.08)
        raise ControllerError("변경한 밝기를 확인하지 못했어요.")

    def night(self):
        return self.dbus(
            "org.kde.KWin",
            NIGHT,
            "org.freedesktop.DBus.Properties",
            "GetAll",
            "(s)",
            ("org.kde.KWin.NightLight",),
        )

    def night_config(self):
        result = {}
        for key in NIGHT_KEYS:
            value = self.command(
                [
                    "/usr/bin/kreadconfig6",
                    "--file",
                    "kwinrc",
                    "--group",
                    "NightColor",
                    "--key",
                    key,
                    "--default",
                    "__frieren_absent__",
                ]
            )
            result[key] = None if value == "__frieren_absent__" else value
        return result

    def write_night(self, values):
        for key, value in values.items():
            if key not in NIGHT_KEYS:
                raise ControllerError("야간 설정 항목을 확인해 주세요.")
            args = ["/usr/bin/kwriteconfig6", "--file", "kwinrc", "--group", "NightColor", "--key", key]
            self.command(args + (["--delete"] if value is None else [str(value)]))
        # Send one notification after all keys, even if the last key's value was unchanged.
        # KWin 6.7 NightLight watches this signal rather than Workspace reloads.
        self.bus.emit_signal(
            None,
            "/kwinrc",
            "org.kde.kconfig.notify",
            "ConfigChanged",
            self.GLib.Variant("(a{saay})", ({"NightColor": [list(key.encode()) for key in values]},)),
        )
        self.bus.flush_sync(None)
        expected_enabled = values.get("Active") == "true"
        expected_mode = int(values.get("Mode") or 1)
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            actual = self.night()
            if actual["enabled"] == expected_enabled and actual["mode"] == expected_mode:
                return
            time.sleep(0.08)
        raise ControllerError("변경한 야간 설정을 확인하지 못했어요.")

    def set_night(self, enabled, temperature):
        if not self.night().get("available"):
            raise ControllerError("현재 화면에서 야간 모드를 지원하지 않아요.")
        self.write_night({"Active": str(enabled).lower(), "Mode": "0", "NightTemperature": str(temperature)})
        if enabled:
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                if self.night()["targetTemperature"] == temperature:
                    return
                time.sleep(0.08)
            raise ControllerError("변경한 색온도를 확인하지 못했어요.")

    def inhibit_color(self):
        return self.dbus("org.kde.KWin", NIGHT, "org.kde.KWin.NightLight", "inhibit")

    def release_color(self, cookie):
        self.dbus("org.kde.KWin", NIGHT, "org.kde.KWin.NightLight", "uninhibit", "(u)", (cookie,))

    def inhibit_screen(self):
        # ChangeScreenSettings only. Never add InterruptSession or ScreenSaver inhibition.
        return self.dbus(
            POWER,
            POLICY,
            POWER + ".PolicyAgent",
            "AddInhibition",
            "(uss)",
            (4, "Frieren OS Controller", "화면 켜두기"),
        )

    def release_screen(self, cookie):
        self.dbus(POWER, POLICY, POWER + ".PolicyAgent", "ReleaseInhibition", "(u)", (cookie,))

    def owner(self, service):
        return self.dbus(
            "org.freedesktop.DBus",
            "/org/freedesktop/DBus",
            "org.freedesktop.DBus",
            "GetNameOwner",
            "(s)",
            (service,),
        )

    def profile(self):
        profile = self.dbus(POWER, POWER_PATH, POWER, "currentProfile")
        return "ac" if profile == "AC" else "battery"

    def outputs(self):
        try:
            return json.loads(self.command(["/usr/bin/kscreen-doctor", "-j"]))["outputs"]
        except (ValueError, KeyError) as exc:
            raise ControllerError("화면 구성을 읽지 못했어요.") from exc

    def set_layout(self, layout, outputs):
        detected = {row["name"]: row for row in outputs if row["connected"]}
        args = ["/usr/bin/kscreen-doctor"]
        for row in layout:
            output = detected[row["name"]]
            prefix = f"output.{output['id']}."
            args.append(prefix + ("enable" if row["enabled"] else "disable"))
            if row["enabled"]:
                args.extend(
                    [
                        prefix + "mode." + row["mode"],
                        prefix + "rotation." + row["rotation"],
                        prefix + f"position.{row['x']},{row['y']}",
                        prefix + ("primary" if row["primary"] else "priority.2"),
                    ]
                )
        self.command(args)


def capture_layout(outputs):
    return [
        {
            "name": row["name"],
            "enabled": bool(row["enabled"]),
            "mode": row["currentModeId"],
            "rotation": ROTATIONS.get(row["rotation"], "none"),
            "x": row["pos"]["x"],
            "y": row["pos"]["y"],
            "primary": row.get("priority", 0) == 1,
            "mode_info": next((mode for mode in row["modes"] if mode["id"] == row["currentModeId"]), None),
        }
        for row in outputs
        if row["connected"]
    ]


def validate_layout(layout, outputs):
    detected = {row["name"]: row for row in outputs if row["connected"]}
    if not isinstance(layout, list) or not 1 <= len(layout) <= 8 or len(layout) != len(detected):
        raise ControllerError("연결된 화면의 설정을 모두 입력해 주세요.")
    seen, enabled, primary = set(), 0, 0
    required = {"name", "enabled", "mode", "rotation", "x", "y", "primary"}
    for row in layout:
        if not isinstance(row, dict) or set(row) != required or not isinstance(row["name"], str):
            raise ControllerError("화면 설정 항목을 확인해 주세요.")
        name = row["name"]
        if name not in detected or name in seen:
            raise ControllerError("화면 연결이 바뀌었어요. 새로고침해 주세요.")
        seen.add(name)
        if type(row["enabled"]) is not bool or type(row["primary"]) is not bool:
            raise ControllerError("화면 켜기·끄기 값을 확인해 주세요.")
        if not isinstance(row["mode"], str) or (
            row["enabled"] and row["mode"] not in {mode["id"] for mode in detected[name]["modes"]}
        ):
            raise ControllerError("이 화면에서 지원하는 해상도와 주사율을 골라 주세요.")
        if row["rotation"] not in ROTATIONS.values():
            raise ControllerError("지원하는 화면 방향을 골라 주세요.")
        integer(row["x"], 0, 16000, "가로 위치")
        integer(row["y"], 0, 16000, "세로 위치")
        if row["primary"] and not row["enabled"]:
            raise ControllerError("주 화면은 켜져 있어야 해요.")
        enabled += row["enabled"]
        primary += row["primary"]
    if not enabled or primary != 1:
        raise ControllerError("화면을 하나 이상 켜고 주 화면을 하나 골라 주세요.")
    return copy.deepcopy(layout)


def layout_matches(layout, outputs):
    applied = {row["name"]: row for row in capture_layout(outputs)}
    return all(
        all(
            applied.get(row["name"], {}).get(key) == row[key]
            for key in ("enabled", "mode", "rotation", "x", "y", "primary")
            if row["enabled"] or key == "enabled"
        )
        for row in layout
    )


class Monitor:
    def __init__(self, state_dir: Path, backend=None, clock=None):
        self.path = state_dir / "monitor.json"
        self.backend = backend or KDEBackend()
        self.clock = clock or time.time
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.thread = None
        self.error = ""
        self.screen_cookie = self.color_cookie = None
        self.screen_owner = self.color_owner = None
        self.color_until = 0
        self.last_profile = self.last_night = None
        self.last_automation = 0
        self.state = self._read()

    def _read(self):
        if not self.path.exists():
            return {
                "settings": dict(DEFAULTS),
                "preset": "original",
                "custom": None,
                "baseline": None,
                "pending": None,
                "hold_until": 0,
                "managed": False,
            }
        try:
            state = json.loads(self.path.read_text())
            validate_settings(state["settings"])
            return state
        except (ValueError, KeyError, TypeError) as exc:
            # Never silently discard the sole recovery snapshot.
            raise ControllerError("저장된 화면 설정을 읽지 못했어요. 복원 파일을 확인해 주세요.") from exc

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.state, ensure_ascii=False) + "\n")
        temporary.chmod(0o600)
        temporary.replace(self.path)

    def _snapshot(self):
        return {
            "brightness": self.backend.brightness(),
            "night": self.backend.night_config(),
            "layout": capture_layout(self.backend.outputs()),
        }

    def _baseline(self):
        if self.state["baseline"] is None:
            self.state["baseline"] = self._snapshot()
            self._save()

    def start(self):
        with self.lock:
            if self.thread:
                return
            # A daemon restart cancels unconfirmed layout changes immediately.
            if self.state["pending"]:
                try:
                    self._rollback()
                except ControllerError as exc:
                    self.error = str(exc)  # Retry from the worker when the display/session returns.
            self.thread = threading.Thread(target=self._loop, daemon=True, name="monitor-recovery")
            self.thread.start()

    def _loop(self):
        while not self.stop_event.wait(1):
            try:
                self.maintenance()
            except Exception as exc:
                self.error = str(exc)

    def close(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=10)
        with self.lock:
            if self.state["pending"]:
                self._rollback()
            self._release_hold()
            self._release_color()

    def maintenance(self):
        with self.lock:
            now = self.clock()
            if self.state["pending"] and now >= self.state["pending"]["deadline"]:
                self._rollback()
            if self.color_cookie is not None and now >= self.color_until:
                self._release_color()
            if self.state["hold_until"]:
                if now >= self.state["hold_until"]:
                    self._release_hold()
                    self.state["hold_until"] = 0
                    self._save()
                else:
                    owner = self.backend.owner(POWER)
                    if self.screen_cookie is None or owner != self.screen_owner:
                        self.screen_cookie = self.backend.inhibit_screen()
                        self.screen_owner = owner
            if now - self.last_automation >= 5 and self.state["managed"]:
                self._automate()
                self.last_automation = now

    def _automate(self, force=False):
        settings = self.state["settings"]
        if settings["auto_brightness"]:
            profile = self.backend.profile()
            if force or profile != self.last_profile:
                self.backend.set_brightness(percent=settings[profile + "_brightness"])
                self.last_profile = profile
        enabled = settings["night_enabled"] and (not settings["scheduled"] or in_schedule(settings))
        if force or (settings["scheduled"] and enabled != self.last_night):
            self.backend.set_night(enabled, settings["temperature"])
            self.last_night = enabled

    def status(self):
        with self.lock:
            errors = []
            brightness = night = None
            outputs = []
            for key, read in (
                ("brightness", self.backend.brightness),
                ("night", self.backend.night),
                ("outputs", self.backend.outputs),
            ):
                try:
                    value = read()
                    if key == "brightness":
                        brightness = value
                    elif key == "night":
                        night = value
                    else:
                        outputs = [row for row in value if row["connected"]]
                except ControllerError as exc:
                    errors.append(str(exc))
            pending = copy.deepcopy(self.state["pending"])
            if pending:
                pending = {
                    "token": pending["token"],
                    "remaining": max(0, math.ceil(pending["deadline"] - self.clock())),
                }
            return {
                "brightness": brightness,
                "night": night,
                "outputs": outputs,
                "settings": copy.deepcopy(self.state["settings"]),
                "preset": self.state["preset"],
                "custom": copy.deepcopy(self.state["custom"]),
                "has_baseline": bool(self.state["baseline"]),
                "pending": pending,
                "hold_remaining": max(0, math.ceil(self.state["hold_until"] - self.clock())),
                "color_remaining": max(0, math.ceil(self.color_until - self.clock())),
                "error": self.error or " · ".join(errors),
            }

    def configure(self, settings, preset="custom"):
        settings = validate_settings(settings)
        if preset not in (*PRESETS, "custom"):
            raise ControllerError("화면 프리셋을 확인해 주세요.")
        with self.lock:
            if self.state["pending"]:
                raise ControllerError("화면 구성을 유지하거나 되돌린 뒤 적용해 주세요.")
            before = self._snapshot()
            self._baseline()
            previous = copy.deepcopy(self.state)
            try:
                self._release_color()
                self.state.update(settings=settings, preset=preset, managed=True)
                if preset == "custom":
                    self.state["custom"] = dict(settings)
                self.backend.set_brightness(percent=settings["brightness"])
                self._automate(force=True)
                if preset == "presentation":
                    self._hold(60)
                self._save()
                self.error = ""
            except Exception:
                if preset == "presentation":
                    self._release_hold()
                self.state = previous
                self.backend.set_brightness(raw=before["brightness"]["raw"])
                self.backend.write_night(before["night"])
                self.last_profile = self.last_night = None
                self._save()
                raise
            return self.status()

    def preset(self, name):
        if not isinstance(name, str) or name not in (*PRESETS, "custom"):
            raise ControllerError("화면 프리셋을 확인해 주세요.")
        settings = self.state["custom"] if name == "custom" else PRESETS[name]
        if settings is None:
            raise ControllerError("사용자 지정 설정을 먼저 저장해 주세요.")
        return self.configure(dict(settings), name)

    def _same_owner(self, service, owner):
        try:
            return self.backend.owner(service) == owner
        except ControllerError:
            return False  # The vanished service has already dropped our inhibition.

    def _release_color(self):
        if self.color_cookie is not None:
            if self._same_owner("org.kde.KWin", self.color_owner):
                self.backend.release_color(self.color_cookie)
            self.color_cookie = None
        self.color_until = 0

    def original_color(self, minutes):
        integer(minutes, 0, 120, "원래 색 보기 시간")
        with self.lock:
            self._release_color()
            if minutes:
                self.color_owner = self.backend.owner("org.kde.KWin")
                self.color_cookie = self.backend.inhibit_color()
                self.color_until = self.clock() + minutes * 60
            return self.status()

    def _release_hold(self):
        if self.screen_cookie is not None:
            if self._same_owner(POWER, self.screen_owner):
                self.backend.release_screen(self.screen_cookie)
            self.screen_cookie = None

    def _hold(self, minutes):
        self._release_hold()
        if minutes:
            self.screen_owner = self.backend.owner(POWER)
            self.screen_cookie = self.backend.inhibit_screen()
        self.state["hold_until"] = self.clock() + minutes * 60 if minutes else 0

    def keep_awake(self, minutes):
        integer(minutes, 0, 240, "화면 켜두기 시간")
        with self.lock:
            self._hold(minutes)
            self._save()
            return self.status()

    def _restore_layout(self, saved):
        outputs = self.backend.outputs()
        detected = {row["name"]: row for row in outputs if row["connected"]}
        layout = []
        for row in saved:
            if row["name"] not in detected:
                continue
            row = dict(row)
            modes = detected[row["name"]]["modes"]
            info = row.pop("mode_info", None)
            current_info = next((m for m in modes if m["id"] == row["mode"]), None)
            if current_info is None or (
                info
                and (
                    current_info["size"] != info["size"]
                    or abs(current_info["refreshRate"] - info["refreshRate"]) > 0.2
                )
            ):
                match = next(
                    (
                        m
                        for m in modes
                        if info
                        and m["size"] == info["size"]
                        and abs(m["refreshRate"] - info["refreshRate"]) < 0.2
                    ),
                    None,
                )
                row["mode"] = (
                    match["id"] if match else (detected[row["name"]]["preferredModes"] or [modes[0]["id"]])[0]
                )
            layout.append(row)
        names = {row["name"] for row in layout}
        layout.extend(
            {k: v for k, v in row.items() if k != "mode_info"}
            for row in capture_layout(outputs)
            if row["name"] not in names
        )
        if not layout:
            raise ControllerError("복원할 화면을 연결해 주세요.")
        if not any(row["enabled"] for row in layout):
            first = layout[0]
            first.update(
                enabled=True,
                mode=(
                    detected[first["name"]]["preferredModes"] or [detected[first["name"]]["modes"][0]["id"]]
                )[0],
                x=0,
                y=0,
            )
        primary = next(
            (row for row in layout if row["enabled"] and row["primary"]),
            next(row for row in layout if row["enabled"]),
        )
        for row in layout:
            row["primary"] = row is primary
        self.backend.set_layout(validate_layout(layout, outputs), outputs)
        if not layout_matches(layout, self.backend.outputs()):
            raise ControllerError("이전 화면 구성을 복원하지 못했어요. 화면을 연결하고 다시 확인해 주세요.")

    def _rollback(self):
        pending = self.state["pending"]
        if pending:
            self._restore_layout(pending["before"])
            self.state["pending"] = None
            self._save()
            self.error = ""

    def preview_layout(self, layout):
        with self.lock:
            if self.state["pending"]:
                raise ControllerError("이전 변경을 유지하거나 되돌린 뒤 변경해 주세요.")
            outputs = self.backend.outputs()
            layout = validate_layout(layout, outputs)
            self._baseline()
            token = uuid.uuid4().hex
            self.state["pending"] = {
                "before": capture_layout(outputs),
                "token": token,
                "deadline": self.clock() + 15,
            }
            self._save()
            try:
                self.backend.set_layout(layout, outputs)
                # kscreen-doctor can return success without applying all requested settings.
                if not layout_matches(layout, self.backend.outputs()):
                    raise ControllerError("화면 구성이 일치하지 않아 이전 설정으로 되돌렸어요.")
            except Exception:
                self._rollback()
                raise
            return self.status()

    def confirm_layout(self, token, keep):
        if not isinstance(token, str) or type(keep) is not bool:
            raise ControllerError("화면 확인 요청을 확인해 주세요.")
        with self.lock:
            pending = self.state["pending"]
            if not pending or token != pending["token"]:
                raise ControllerError("화면 확인 시간이 끝났어요. 현재 화면을 확인해 주세요.")
            if self.clock() >= pending["deadline"] or not keep:
                self._rollback()
            else:
                self.state["pending"] = None
                self._save()
            return self.status()

    def reset(self):
        with self.lock:
            if self.state["pending"]:
                self._rollback()
            baseline = self.state["baseline"]
            if baseline is None:
                raise ControllerError("아직 저장한 원래 화면 설정이 없어요.")
            self._release_color()
            self._hold(0)
            self.backend.set_brightness(raw=baseline["brightness"]["raw"])
            self.backend.write_night(baseline["night"])
            self.state.update(settings=dict(DEFAULTS), preset="original", managed=False, custom=None)
            self.last_profile = self.last_night = None
            self._save()
            # Resolution restoration itself is a timed preview, with the same recovery guarantees.
            before = capture_layout(self.backend.outputs())
            self.state["pending"] = {
                "before": before,
                "token": uuid.uuid4().hex,
                "deadline": self.clock() + 15,
            }
            self._save()
            try:
                self._restore_layout(baseline["layout"])
            except Exception:
                self._rollback()
                raise
            return self.status()
