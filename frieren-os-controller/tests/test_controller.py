"""Behavioral tests for validation, persistence and reversible unit operations."""

from __future__ import annotations

import json
import socket
import subprocess
import tempfile
import threading
import unittest
from collections import namedtuple
from pathlib import Path
from unittest.mock import patch

from frieren_controller.client import call
from frieren_controller.core import Controller, ControllerError
from frieren_controller.quiet import QuietMonitor, QuietPlugin
from frieren_controller.server import Handler, ThreadedServer


class FakeSystemctl:
    def __init__(self):
        self.enabled = False
        self.active = False
        self.fail_start = False
        self.calls: list[list[str]] = []

    def __call__(self, args, **_kwargs):
        self.calls.append(args)
        if args[0] != "/usr/bin/systemctl":
            raise AssertionError(args)
        action = next(
            (
                word
                for word in args
                if word in ("list-unit-files", "list-units", "show", "enable", "disable", "start")
            ),
            None,
        )
        state = "enabled" if self.enabled else "disabled"
        activity = "active" if self.active else "inactive"
        if action == "list-unit-files":
            result = json.dumps([{"unit_file": "demo.timer", "state": state}])
        elif action == "list-units":
            result = json.dumps(
                [{"unit": "demo.timer", "active": activity, "sub": "waiting", "description": "Demo"}]
            )
        elif action == "show":
            result = "\n".join(
                (
                    "Id=demo.timer",
                    "Description=Demo",
                    "LoadState=loaded",
                    f"ActiveState={activity}",
                    "SubState=waiting",
                    f"UnitFileState={state}",
                    "FragmentPath=/tmp/demo.timer",
                )
            )
        elif action == "enable":
            self.enabled = True
            if self.fail_start:
                return subprocess.CompletedProcess(args, 1, "", "start failed")
            self.active = True
            result = ""
        elif action == "disable":
            self.enabled = False
            self.active = False
            result = ""
        elif action == "start":
            self.active = True
            result = ""
        else:
            raise AssertionError(args)
        return subprocess.CompletedProcess(args, 0, result, "")


class FakeQuiet:
    def __init__(self):
        self.mode = "balanced"
        self.target = 64
        self.effects = False

    def status(self):
        return {
            "mode": self.mode,
            "mode_label": "균형",
            "target_c": self.target,
            "cpu_c": 55.0,
            "limits": {"max_perf_pct": 75},
        }

    def set_mode(self, mode):
        self.mode = mode
        return self.status()

    def set_target(self, temperature):
        self.target = temperature
        return self.status()

    def configure(self, settings):
        self.custom = settings
        self.mode = "custom"
        return self.status()

    def reset(self):
        self.mode = "restore"
        self.target = 64
        return self.status()

    def effects_enabled(self):
        return self.effects

    def set_effects(self, enabled):
        self.effects = enabled
        return enabled


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.TemporaryDirectory()
        self.addCleanup(self.root.cleanup)
        self.runner = FakeSystemctl()
        self.quiet = FakeQuiet()
        self.controller = Controller(Path(self.root.name) / "state", runner=self.runner, quiet=self.quiet)

    def test_lists_disabled_timer_and_changes_it(self):
        rows = self.controller.list_units(scope="user", kind="timer")
        self.assertEqual(rows[0]["unit"], "demo.timer")
        self.assertFalse(rows[0]["enabled"])
        preview = self.controller.preview_toggle("user", "demo.timer", True)
        self.assertEqual(preview["action"], "enable --now")
        result = self.controller.toggle_unit("user", "demo.timer", True)
        self.assertEqual(result["after"]["active"], "active")
        self.assertTrue(self.runner.enabled)
        self.assertIn("--", next(x for x in self.runner.calls if "enable" in x))
        self.controller.toggle_unit("user", "demo.timer", False)
        self.assertFalse(self.runner.enabled)
        self.assertEqual(len(self.controller.audit_log()), 2)

    def test_rolls_back_when_enable_partly_fails(self):
        self.runner.fail_start = True
        with self.assertRaisesRegex(ControllerError, "start failed"):
            self.controller.toggle_unit("user", "demo.timer", True)
        self.assertFalse(self.runner.enabled)
        self.assertFalse(self.runner.active)
        self.assertEqual(self.controller.audit_log(), [])

    def test_rejects_protected_and_untrusted_unit_names(self):
        with self.assertRaises(ControllerError):
            self.controller.preview_toggle("system", "sshd.service", False)
        with self.assertRaises(ControllerError):
            self.controller.preview_toggle("system", "freiren-quiet.service", False)
        with self.assertRaises(ControllerError):
            self.controller.toggle_unit("user", "demo.timer; touch /tmp/unsafe", True)
        self.assertFalse(any("enable" in args for args in self.runner.calls))

    def test_notes_are_private_and_survive_restart(self):
        self.controller.set_note("user", "demo.timer", "매일 실행\n개인 메모")
        reloaded = Controller(Path(self.root.name) / "state", runner=self.runner)
        self.assertEqual(reloaded.get_note("user", "demo.timer"), "매일 실행\n개인 메모")
        self.assertEqual((reloaded.state_dir / "notes.json").stat().st_mode & 0o777, 0o600)
        self.assertNotIn("개인 메모", (reloaded.state_dir / "audit.jsonl").read_text())

    def test_custom_card_is_declarative(self):
        card = self.controller.write_module(
            "backup-timer", {"label": "백업", "kind": "unit", "scope": "user", "unit": "demo.timer"}
        )
        self.assertFalse(card["builtin"])
        self.assertEqual(self.controller.run_check("backup-timer")["value"], "중지 · 시작 꺼짐")
        with self.assertRaises(ControllerError):
            self.controller.write_module("evil", {"label": "악성", "kind": "command", "command": "whoami"})
        self.assertFalse((self.controller.modules_dir / "evil.json").exists())

    def test_socket_uses_the_same_backend(self):
        path = Path(self.root.name) / "api.sock"
        server = ThreadedServer(str(path), Handler)
        server.controller = self.controller
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.assertEqual(call("get_note", path=path, scope="user", unit="demo.timer"), "")
        call("set_note", path=path, scope="user", unit="demo.timer", note="소켓 메모")
        self.assertEqual(self.controller.get_note("user", "demo.timer"), "소켓 메모")
        self.assertEqual(call("quiet_status", path=path)["mode"], "balanced")
        self.assertEqual(call("quiet_set_mode", path=path, mode="quiet")["mode"], "quiet")
        custom = {"cap": 65, "turbo": False, "preference": "balance_power", "power_w": 22, "boost_w": 30}
        self.assertEqual(call("quiet_configure", path=path, settings=custom)["mode"], "custom")
        self.assertEqual(self.quiet.custom, custom)
        self.assertEqual(call("quiet_reset", path=path)["mode"], "restore")
        self.assertEqual(
            [item["action"] for item in self.controller.audit_log()][-2:], ["quiet_configure", "quiet_reset"]
        )
        with socket.socket(socket.AF_UNIX) as client:
            client.connect(str(path))
            client.sendall(b'{"op":"__dict__","args":{}}\n')
            self.assertFalse(json.loads(client.recv(1024))["ok"])

    def test_quiet_uses_controller_api_and_audit(self):
        self.assertEqual(self.controller.run_check("freiren-quiet")["value"], "균형 · CPU 55°C · 상한 75%")
        self.assertEqual(self.controller.quiet_set_mode("performance")["mode"], "performance")
        self.assertEqual(self.controller.quiet_set_target(68)["target_c"], 68)
        self.assertTrue(self.controller.quiet_set_effects(True)["effects_saving"])
        self.assertEqual(
            [row["action"] for row in self.controller.audit_log()],
            ["quiet_set_mode", "quiet_set_target", "quiet_set_effects"],
        )

    def test_quiet_adapter_rejects_invalid_values_before_socket(self):
        plugin = QuietPlugin(Path(self.root.name) / "missing.sock")
        for value in ("fast", "balanced; true", ""):
            with self.assertRaisesRegex(ControllerError, "전원 모드"):
                plugin.set_mode(value)
        for value in (57, 76, True, "64"):
            with self.assertRaisesRegex(ControllerError, "목표 온도"):
                plugin.set_target(value)
        with self.assertRaisesRegex(ControllerError, "연결하지 못했어요"):
            plugin.status()
        with self.assertRaisesRegex(ControllerError, "화면 효과"):
            plugin.set_effects("yes")

    def test_effects_adapter_uses_only_fixed_commands_and_verifies_result(self):
        path = Path(self.root.name) / "effects.json"
        commands = []

        def runner(args, **_kwargs):
            commands.append(args)
            if args[-1] == "save":
                path.write_text("{}")
            else:
                path.unlink()
            return subprocess.CompletedProcess(args, 0, "", "")

        plugin = QuietPlugin(runner=runner, effects_path=path)
        self.assertTrue(plugin.set_effects(True))
        self.assertFalse(plugin.set_effects(False))
        self.assertEqual(
            commands,
            [
                ["/usr/bin/freiren-quiet", "effects", "save"],
                ["/usr/bin/freiren-quiet", "effects", "restore"],
            ],
        )

    def test_custom_adapter_validates_before_sending_and_reset_supports_old_plugin(self):
        plugin = QuietPlugin()
        custom = {"cap": 65, "turbo": False, "preference": "balance_power", "power_w": 22, "boost_w": 30}
        with patch.object(plugin, "_request", return_value={"mode": "custom"}) as request:
            for change in (
                {"cap": True},
                {"turbo": 1},
                {"power_w": float("nan")},
                {"boost_w": None},
                {"boost_w": 10},
                {"power_w": 22.1},
                {"path": "/etc"},
            ):
                with self.subTest(change=change), self.assertRaises(ControllerError):
                    plugin.configure({**custom, **change})
            request.assert_not_called()
            plugin.configure(custom)
            request.assert_called_once_with({"op": "configure", "settings": custom})
        for protocol, expected in ((1, {"op": "mode", "mode": "restore"}), (2, {"op": "reset"})):
            with patch.object(plugin, "status", return_value={"protocol_version": protocol}):
                with patch.object(plugin, "_request") as request:
                    plugin.reset()
                    request.assert_called_once_with(expected)

    def test_cpu_sample_excludes_guest_and_iowait_and_reuses_short_intervals(self):
        Times = namedtuple("Times", "user system idle iowait guest guest_nice")
        with (
            patch(
                "frieren_controller.quiet.psutil.cpu_times",
                side_effect=[Times(10, 5, 30, 2, 1, 0), Times(14, 7, 32, 4, 3, 0)],
            ) as cpu_times,
            patch("frieren_controller.quiet.psutil.process_iter", return_value=[]),
            patch("frieren_controller.quiet.time.monotonic", side_effect=[0, 0.2, 5, 5.1]),
        ):
            monitor = QuietMonitor()
            self.assertIsNone(monitor.sample()["cpu_percent"])
            measured = monitor.sample()
            self.assertEqual(measured["cpu_percent"], 60)
            self.assertEqual(monitor.sample(), measured)
            self.assertEqual(cpu_times.call_count, 2)


if __name__ == "__main__":
    unittest.main()
