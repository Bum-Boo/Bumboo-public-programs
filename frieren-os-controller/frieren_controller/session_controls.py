"""Service-owned notification inhibition and power/display composition."""

from __future__ import annotations

import copy
import time

from .core import ControllerError
from .desktop_common import Config, SessionBus, boolean, choice, fields, integer
from .monitor import POWER, POWER_PATH, validate_settings

NOTIFY_SERVICE = "org.freedesktop.Notifications"
NOTIFY_PATH = "/org/freedesktop/Notifications"
TIMEOUT_KEYS = {
    f"{profile}_{key}": ("powerdevilrc", (profile, "Display"), entry)
    for profile in ("AC", "Battery", "LowBattery")
    for key, entry in (("enabled", "TurnOffDisplayWhenIdle"), ("seconds", "TurnOffDisplayIdleTimeoutSec"))
}
SESSION_RESTORE_KEYS = {"mode": ("ksmserverrc", ("General",), "loginMode")}


class SessionControls:
    def __init__(self, controller, bus=None):
        self.controller = controller
        self.bus = bus or SessionBus()
        self.config = Config(self.bus)
        self.cookie = None
        self.owner = None
        self.muted_requested = False

    def _check_owner(self):
        owner = self.bus.call(
            "org.freedesktop.DBus",
            "/org/freedesktop/DBus",
            "org.freedesktop.DBus",
            "GetNameOwner",
            "(s)",
            (NOTIFY_SERVICE,),
        )
        if self.owner != owner:
            self.cookie = None
            self.owner = owner
            if self.muted_requested:
                self._mute(True)

    def status(self):
        self._check_owner()
        props = self.bus.properties(NOTIFY_SERVICE, NOTIFY_PATH, NOTIFY_SERVICE)
        restore_mode = self.config.read(*SESSION_RESTORE_KEYS["mode"]) or "restorePreviousLogout"
        return {
            "session_restore": restore_mode != "emptySession",
            "session_restore_mode": restore_mode,
            "notifications_muted": self.cookie is not None,
            "notifications_inhibited": bool(props.get("Inhibited")),
            "screen_until": self.controller._monitor().state["hold_until"],
            "timeouts": self.config.capture(TIMEOUT_KEYS, TIMEOUT_KEYS),
        }

    def validate(self, settings):
        values = fields(settings, {"notifications_muted", "keep_awake", "screen_timeout", "session_restore"})
        if "session_restore" in values:
            boolean(values["session_restore"])
        if "notifications_muted" in values:
            boolean(values["notifications_muted"])
        if "keep_awake" in values:
            integer(values["keep_awake"], 0, 240, "화면 유지 시간")
        if "screen_timeout" in values:
            integer(values["screen_timeout"], 60, 3600, "화면 꺼짐 시간")
        return values

    def capture(self, settings):
        result = {}
        if "notifications_muted" in settings:
            self._check_owner()
            result["notifications_muted"] = self.cookie is not None
        if "session_restore" in settings:
            result["session_restore"] = self.config.capture(SESSION_RESTORE_KEYS, SESSION_RESTORE_KEYS)
        if "keep_awake" in settings:
            result["screen_until"] = self.controller._monitor().state["hold_until"]
        if "screen_timeout" in settings:
            result["timeouts"] = self.config.capture(TIMEOUT_KEYS, TIMEOUT_KEYS)
        return result

    def _mute(self, enabled):
        self._check_owner()
        self.muted_requested = enabled
        if enabled and self.cookie is None:
            self.cookie = self.bus.call(
                NOTIFY_SERVICE,
                NOTIFY_PATH,
                NOTIFY_SERVICE,
                "Inhibit",
                "(ssa{sv})",
                ("io.github.BumBoo.FrierenOSController", "프리렌 작업 모드", {}),
            )
        elif not enabled and self.cookie is not None:
            self.bus.call(NOTIFY_SERVICE, NOTIFY_PATH, NOTIFY_SERVICE, "UnInhibit", "(u)", (self.cookie,))
            self.cookie = None
        if enabled and not self.bus.properties(NOTIFY_SERVICE, NOTIFY_PATH, NOTIFY_SERVICE).get("Inhibited"):
            raise ControllerError("알림 숨김을 확인하지 못했어요.")

    def _reload_power(self):
        self.bus.call(POWER, POWER_PATH, POWER, "reparseConfiguration")
        self.bus.call(POWER, POWER_PATH, POWER, "loadProfile", "(b)", (True,))

    def apply(self, settings):
        values = self.validate(settings)
        if "session_restore" in values:
            writes = {"mode": "restorePreviousLogout" if values["session_restore"] else "emptySession"}
            self.config.restore(SESSION_RESTORE_KEYS, writes)
            if self.config.capture(SESSION_RESTORE_KEYS, SESSION_RESTORE_KEYS) != writes:
                raise ControllerError("세션 복원 설정을 확인하지 못했어요. 다시 시도해 주세요.")
        if "notifications_muted" in values:
            self._mute(values["notifications_muted"])
        if "keep_awake" in values:
            self.controller._monitor().keep_awake(values["keep_awake"])
        if "screen_timeout" in values:
            writes = {
                key: ("true" if key.endswith("_enabled") else str(values["screen_timeout"]))
                for key in TIMEOUT_KEYS
            }
            self.config.restore(TIMEOUT_KEYS, writes)
            self._reload_power()
            if self.config.capture(TIMEOUT_KEYS, TIMEOUT_KEYS) != writes:
                raise ControllerError("자동 화면 꺼짐 설정을 확인하지 못했어요.")

    def restore(self, snapshot):
        if "session_restore" in snapshot:
            self.config.restore(SESSION_RESTORE_KEYS, snapshot["session_restore"])
        if "notifications_muted" in snapshot:
            self._mute(snapshot["notifications_muted"])
        if "screen_until" in snapshot:
            monitor = self.controller._monitor()
            with monitor.lock:
                monitor._release_hold()
                monitor.state["hold_until"] = (
                    snapshot["screen_until"] if snapshot["screen_until"] > time.time() else 0
                )
                monitor._save()
                monitor.maintenance()
        if "timeouts" in snapshot:
            self.config.restore(TIMEOUT_KEYS, snapshot["timeouts"])
            self._reload_power()

    @staticmethod
    def comparable(snapshot):
        result = copy.deepcopy(snapshot)
        if result.get("screen_until", 0) < time.time() and "screen_until" in result:
            result["screen_until"] = 0
        return result

    def close(self):
        if self.cookie is not None:
            try:
                self._mute(False)
            except ControllerError:
                pass


class PowerControls:
    def __init__(self, controller):
        self.controller = controller

    def status(self):
        value = self.controller.quiet.status()
        return {key: value[key] for key in ("mode", "target_c", "custom")}

    def validate(self, settings):
        values = fields(settings, {"mode", "target_c"})
        if "mode" in values:
            choice(
                values["mode"], ("auto", "quiet", "balanced", "performance", "custom", "restore"), "전원 모드"
            )
        if "target_c" in values:
            integer(values["target_c"], 58, 75, "목표 온도")
        return values

    def capture(self, settings):
        state = self.status()
        result = {key: state[key] for key in settings}
        if "mode" in settings:
            result["custom"] = state["custom"]
        return result

    def apply(self, settings):
        values = self.validate(settings)
        if "target_c" in values:
            self.controller.quiet.set_target(values["target_c"])
        if "mode" in values:
            self.controller.quiet.set_mode(values["mode"])
        if any(self.status()[key] != value for key, value in values.items()):
            raise ControllerError("변경한 전원 모드를 확인하지 못했어요.")

    def restore(self, snapshot):
        values = dict(snapshot)
        custom = values.pop("custom", None)
        if custom is not None and self.status()["custom"] != custom:
            self.controller.quiet.configure(custom)
        self.apply(values)


class DisplayControls:
    def __init__(self, controller):
        self.controller = controller

    def status(self):
        return self.controller._monitor().status()

    def validate(self, settings):
        monitor = self.controller._monitor()
        values = fields(settings, monitor.state["settings"])
        validate_settings({**monitor.state["settings"], **values})
        return values

    def capture(self, settings):
        monitor = self.controller._monitor()
        with monitor.lock:
            return {
                "state": {
                    key: copy.deepcopy(monitor.state[key])
                    for key in ("settings", "managed", "preset", "custom")
                },
                "brightness": monitor.backend.brightness()["raw"],
                "maximum": monitor.backend.brightness()["maximum"],
                "night": monitor.backend.night_config(),
            }

    def apply(self, settings):
        values = self.validate(settings)
        monitor = self.controller._monitor()
        monitor.configure({**monitor.state["settings"], **values})

    def restore(self, snapshot):
        monitor = self.controller._monitor()
        with monitor.lock:
            monitor.state.update(copy.deepcopy(snapshot["state"]))
            monitor._save()
            monitor.backend.set_brightness(raw=snapshot["brightness"])
            monitor.backend.write_night(snapshot["night"])
            monitor.last_profile = monitor.last_night = None
