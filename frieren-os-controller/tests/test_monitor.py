"""Behavioral checks for timed recovery, hotplug, input rejection and original-state preservation."""

from __future__ import annotations

import copy
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from frieren_controller.core import ControllerError
from frieren_controller.monitor import (
    DEFAULTS,
    KDEBackend,
    Monitor,
    capture_layout,
    in_schedule,
    validate_settings,
)


class FakeBackend:
    def __init__(self):
        self.percent = 100
        self.config = {"Active": None, "Mode": None, "DayTemperature": None, "NightTemperature": None}
        self.rows = [
            {
                "id": 1,
                "name": "eDP-1",
                "connected": True,
                "enabled": True,
                "currentModeId": "a",
                "modes": [
                    {"id": "a", "size": {"width": 1920, "height": 1080}, "refreshRate": 60},
                    {"id": "b", "size": {"width": 1280, "height": 720}, "refreshRate": 60},
                ],
                "preferredModes": ["a"],
                "rotation": 1,
                "pos": {"x": 0, "y": 0},
                "priority": 1,
            }
        ]
        self.calls = []
        self.power_profile = "ac"
        self.service_owner = "owner1"
        self.fail_night = False
        self.ignore_layout = False
        self.cookies = 0

    def brightness(self):
        return {"raw": self.percent, "maximum": 100, "minimum": 1, "percent": self.percent}

    def set_brightness(self, percent=None, raw=None):
        self.percent = percent if raw is None else raw
        self.calls.append(("brightness", self.percent))

    def night_config(self):
        return dict(self.config)

    def night(self):
        return {"available": True, "enabled": self.config["Active"] == "true", "currentTemperature": 6500}

    def set_night(self, enabled, temperature):
        if self.fail_night:
            raise ControllerError("night failure")
        self.config.update(Active=str(enabled).lower(), NightTemperature=str(temperature), Mode="0")
        self.calls.append(("night", enabled, temperature))

    def write_night(self, config):
        self.config = dict(config)

    def outputs(self):
        return copy.deepcopy(self.rows)

    def set_layout(self, layout, outputs):
        self.calls.append(("layout", copy.deepcopy(layout)))
        if self.ignore_layout:
            self.ignore_layout = False
            return
        for row in layout:
            state = next(r for r in self.rows if r["name"] == row["name"])
            state.update(
                enabled=row["enabled"],
                currentModeId=row["mode"],
                rotation={"none": 1, "left": 2, "inverted": 4, "right": 8}[row["rotation"]],
                pos={"x": row["x"], "y": row["y"]},
                priority=1 if row["primary"] else 2,
            )

    def profile(self):
        return self.power_profile

    def owner(self, service):
        return self.service_owner

    def inhibit_screen(self):
        self.cookies += 1
        self.calls.append(("hold", self.cookies))
        return self.cookies

    def release_screen(self, cookie):
        self.calls.append(("release_hold", cookie))

    def inhibit_color(self):
        self.cookies += 1
        return self.cookies

    def release_color(self, cookie):
        self.calls.append(("release_color", cookie))


class MonitorTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.backend = FakeBackend()
        self.now = 1000
        self.monitor = Monitor(Path(self.directory.name), self.backend, clock=lambda: self.now)

    def layout(self, mode="b"):
        layout = capture_layout(self.backend.outputs())
        for row in layout:
            row.pop("mode_info")
        layout[0]["mode"] = mode
        return layout

    def test_invalid_custom_changes_nothing(self):
        for delta in (
            {"brightness": 0},
            {"brightness": True},
            {"temperature": 9000},
            {"scheduled": True, "start": "21:00", "end": "21:00"},
            {"start": "99:00"},
            {"auto_brightness": "yes"},
            {"path": "/tmp/a"},
        ):
            with self.subTest(delta=delta), self.assertRaises(ControllerError):
                self.monitor.configure({**DEFAULTS, **delta})
        self.assertEqual(self.backend.calls, [])
        self.assertFalse(self.monitor.path.exists())

    def test_presets_custom_and_baseline_survive_restart(self):
        self.monitor.preset("night")
        baseline = copy.deepcopy(self.monitor.state["baseline"])
        self.monitor.configure({**DEFAULTS, "brightness": 63})
        self.monitor.preset("work")
        self.monitor.preset("custom")
        self.assertEqual(self.backend.percent, 63)
        reopened = Monitor(Path(self.directory.name), self.backend, clock=lambda: self.now)
        self.assertEqual(reopened.state["baseline"], baseline)
        reset = reopened.reset()
        self.assertEqual(self.backend.percent, 100)
        self.assertEqual(self.backend.config, baseline["night"])
        reopened.confirm_layout(reset["pending"]["token"], True)
        self.assertFalse(reopened.state["managed"])
        self.assertIsNone(reopened.state["custom"])

    def test_failed_configuration_restores_state_and_original_keys(self):
        self.backend.fail_night = True
        with self.assertRaises(ControllerError):
            self.monitor.preset("night")
        self.assertEqual(self.backend.percent, 100)
        self.assertTrue(all(value is None for value in self.backend.config.values()))
        self.assertFalse(self.monitor.state["managed"])

    def test_gui_disconnect_does_not_prevent_rollback(self):
        self.monitor.preview_layout(self.layout())
        self.assertEqual(self.backend.rows[0]["currentModeId"], "b")
        self.now += 16
        self.monitor.maintenance()
        self.assertEqual(self.backend.rows[0]["currentModeId"], "a")
        self.assertIsNone(self.monitor.state["pending"])

    def test_confirmation_retains_layout_and_rejects_stale_token(self):
        result = self.monitor.preview_layout(self.layout())
        token = result["pending"]["token"]
        with self.assertRaises(ControllerError):
            self.monitor.confirm_layout("wrong", True)
        self.monitor.confirm_layout(token, True)
        self.now += 20
        self.monitor.maintenance()
        self.assertEqual(self.backend.rows[0]["currentModeId"], "b")
        with self.assertRaises(ControllerError):
            self.monitor.confirm_layout(token, True)

    def test_expired_confirm_cannot_keep_layout(self):
        result = self.monitor.preview_layout(self.layout())
        self.now += 16
        self.monitor.confirm_layout(result["pending"]["token"], True)
        self.assertEqual(self.backend.rows[0]["currentModeId"], "a")

    def test_restart_recovers_pending_change_immediately(self):
        self.monitor.preview_layout(self.layout())
        reopened = Monitor(Path(self.directory.name), self.backend, clock=lambda: self.now)
        reopened.start()
        self.addCleanup(reopened.close)
        self.assertEqual(self.backend.rows[0]["currentModeId"], "a")
        self.assertIsNone(reopened.state["pending"])

    def test_success_exit_without_effect_is_rejected(self):
        self.backend.ignore_layout = True
        with self.assertRaises(ControllerError):
            self.monitor.preview_layout(self.layout())
        self.assertIsNone(self.monitor.state["pending"])
        self.assertEqual(self.backend.rows[0]["currentModeId"], "a")

    def test_no_all_off_unknown_mode_or_injected_name(self):
        for key, value in (
            ("enabled", False),
            ("mode", "999"),
            ("name", "1;touch /tmp/a"),
            ("rotation", "none;true"),
            ("x", -1),
            ("primary", False),
        ):
            layout = self.layout()
            layout[0][key] = value
            with self.subTest(key=key), self.assertRaises(ControllerError):
                self.monitor.preview_layout(layout)
        self.assertEqual(self.backend.calls, [])

    def test_hotplug_recovery_keeps_new_screen_usable(self):
        self.monitor.preview_layout(self.layout())
        new = copy.deepcopy(self.backend.rows[0])
        new.update(name="HDMI-1", id=2, enabled=False, priority=0)
        self.backend.rows = [new]
        self.now += 16
        self.monitor.maintenance()
        self.assertTrue(self.backend.rows[0]["enabled"])
        self.assertEqual(self.backend.rows[0]["priority"], 1)

    def test_hold_expiry_release_and_restart_reacquisition(self):
        self.monitor.keep_awake(1)
        self.monitor.maintenance()
        self.assertEqual(len([c for c in self.backend.calls if c[0] == "hold"]), 1)
        self.backend.service_owner = "owner2"
        self.monitor.maintenance()
        self.assertEqual(len([c for c in self.backend.calls if c[0] == "hold"]), 2)
        self.now += 61
        self.monitor.maintenance()
        self.assertIsNone(self.monitor.screen_cookie)
        self.assertEqual(self.monitor.state["hold_until"], 0)

    def test_original_color_is_temporary(self):
        self.monitor.original_color(1)
        self.now += 61
        self.monitor.maintenance()
        self.assertIsNone(self.monitor.color_cookie)
        self.assertEqual(self.backend.calls[-1][0], "release_color")

    def test_power_transition_only_applies_opted_in_brightness(self):
        self.monitor.configure(
            {**DEFAULTS, "auto_brightness": True, "ac_brightness": 90, "battery_brightness": 40}
        )
        self.assertEqual(self.backend.percent, 90)
        self.backend.power_profile = "battery"
        self.now += 6
        self.monitor.maintenance()
        self.assertEqual(self.backend.percent, 40)
        calls = len(self.backend.calls)
        self.now += 6
        self.monitor.maintenance()
        self.assertEqual(len(self.backend.calls), calls)

    def test_midnight_schedule_and_same_day_schedule(self):
        settings = {**DEFAULTS, "scheduled": True}
        for hour, expected in ((23, True), (6, True), (7, False), (20, False), (21, True)):
            self.assertEqual(in_schedule(settings, datetime(2026, 9, 30, hour)), expected)
        self.assertTrue(
            in_schedule({**settings, "start": "09:00", "end": "17:00"}, datetime(2026, 9, 30, 10))
        )

    def test_schedule_updates_enabled_state(self):
        with patch("frieren_controller.monitor.in_schedule", return_value=False):
            self.monitor.configure({**DEFAULTS, "night_enabled": True, "scheduled": True})
            self.assertEqual(self.backend.config["Active"], "false")
        with patch("frieren_controller.monitor.in_schedule", return_value=True):
            self.now += 6
            self.monitor.maintenance()
            self.assertEqual(self.backend.config["Active"], "true")

    def test_corrupt_state_preserved(self):
        self.monitor.path.write_text("{broken")
        with self.assertRaises(ControllerError):
            Monitor(Path(self.directory.name), self.backend)
        self.assertEqual(self.monitor.path.read_text(), "{broken")

    def test_settings_schema(self):
        self.assertEqual(validate_settings(DEFAULTS), DEFAULTS)
        self.monitor.preset("work")
        persisted = json.loads(self.monitor.path.read_text())
        self.assertEqual(persisted["baseline"]["brightness"]["raw"], 100)


class KDEConfigTests(unittest.TestCase):
    def test_one_notification_after_all_keys_even_when_last_key_unchanged(self):
        config = {"Active": "false", "Mode": "0", "NightTemperature": "4500"}
        actual = {"available": True, "enabled": False, "mode": 0, "targetTemperature": 6500}
        calls = []
        backend = KDEBackend.__new__(KDEBackend)

        class Bus:
            def emit_signal(self, destination, path, interface, member, body):
                calls.append((path, interface, member, body))
                actual.update(
                    enabled=config["Active"] == "true",
                    mode=int(config["Mode"]),
                    targetTemperature=int(config["NightTemperature"]),
                )

            def flush_sync(self, unused):
                pass

        class VariantFactory:
            @staticmethod
            def Variant(signature, body):
                return signature, body

        def command(args):
            config[args[args.index("--key") + 1]] = args[-1]
            return ""

        backend.bus = Bus()
        backend.GLib = VariantFactory()
        backend.command = command
        backend.night = lambda: dict(actual)
        backend.set_night(True, 4500)
        self.assertTrue(actual["enabled"])
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][:3], ("/kwinrc", "org.kde.kconfig.notify", "ConfigChanged"))
        self.assertEqual(calls[0][3][0], "(a{saay})")
