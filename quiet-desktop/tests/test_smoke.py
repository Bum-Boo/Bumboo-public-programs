"""End-to-end smoke tests with a fake sysfs tree, a fake PPD and a temporary Unix socket.

Nothing here touches the real /sys, D-Bus, systemd or /run. The GTK window is only started
when GTK, psutil and a display are available (for example under xvfb-run); otherwise skipped.
"""

import contextlib
import io
import json
import os
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
import unittest
from functools import partial
from pathlib import Path
from unittest.mock import patch

from freiren_quiet import cli, client, service
from freiren_quiet.hardware import Hardware
from freiren_quiet.policy import ThermalPolicy
from freiren_quiet.service import Controller

PACKAGE_ROOT = Path(__file__).resolve().parents[1]


def short_tempdir(testcase):
    # AF_UNIX paths are limited to ~107 bytes; prefer /tmp over a long $TMPDIR.
    base = "/tmp" if os.path.isdir("/tmp") and os.access("/tmp", os.W_OK) else None
    directory = tempfile.mkdtemp(prefix="fq-", dir=base)
    testcase.addCleanup(shutil.rmtree, directory, True)
    return Path(directory)


class FakeSysfs:
    """A minimal MSI GL62 6QE sysfs tree under a temporary directory."""

    def __init__(self, root: Path, model="GL62 6QE", driver="intel_pstate"):
        self.root = root
        self.put("devices/virtual/dmi/id/sys_vendor", "Micro-Star International Co., Ltd.")
        self.put("devices/virtual/dmi/id/product_name", model)
        self.put("devices/system/cpu/cpufreq/policy0/scaling_driver", driver)
        self.put(
            "devices/system/cpu/cpufreq/policy0/energy_performance_preference",
            "balance_performance",
        )
        for key, value in (("no_turbo", 0), ("min_perf_pct", 30), ("max_perf_pct", 100)):
            self.put(f"devices/system/cpu/intel_pstate/{key}", str(value))
        self.put("class/hwmon/hwmon3/name", "coretemp")
        self.put("class/hwmon/hwmon3/temp1_label", "Package id 0")
        self.set_temperature(60)

    def put(self, name, value):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value)

    def set_temperature(self, celsius):
        sensor = self.root / "class/hwmon/hwmon3/temp1_input"
        if celsius is None:
            sensor.unlink(missing_ok=True)
        else:
            self.put("class/hwmon/hwmon3/temp1_input", str(int(celsius * 1000)))

    def limit(self, name):
        return int((self.root / "devices/system/cpu/intel_pstate" / name).read_text())


class FakePPD:
    def __init__(self, profile="balanced"):
        self.profile = profile
        self.profiles = ["power-saver", "balanced", "performance"]

    def current(self):
        return self.profile

    def supported(self):
        return list(self.profiles)

    def set(self, requested):
        effective = requested if requested in self.profiles else "balanced"
        self.profile = effective
        return effective


def make_state(directory: Path, hardware: Hardware, profile="balanced"):
    baseline = hardware.snapshot()
    baseline["power_profile"] = profile
    (directory / "baseline.json").write_text(json.dumps(baseline))
    return baseline


class AutoPolicyRuleSmokeTests(unittest.TestCase):
    """Synthetic temperature sequences for every rule listed in README '자동 조절 규칙'."""

    def run_sequence(self, policy, temperatures):
        return [policy.decide(value) for value in temperatures]

    def test_auto_starts_at_60_and_target_range_is_58_to_75(self):
        policy = ThermalPolicy()
        self.assertEqual((policy.mode, policy.target, policy.cap), ("auto", 64, 60))
        for target in (58, 75):
            ThermalPolicy(target=target)
        for target in (57, 76):
            with self.assertRaises(ValueError):
                ThermalPolicy(target=target)

    def test_two_hot_readings_lower_cap_by_5(self):
        decisions = self.run_sequence(ThermalPolicy(target=64), [67, 67])
        self.assertEqual([d.cap for d in decisions], [60, 55])
        self.assertTrue(all(d.no_turbo == 1 for d in decisions))
        # 66.9°C is below target+3 and must not count.
        decisions = self.run_sequence(ThermalPolicy(target=64), [66.9] * 4)
        self.assertEqual({d.cap for d in decisions}, {60})

    def test_six_cool_readings_raise_cap_by_5_up_to_75(self):
        decisions = self.run_sequence(ThermalPolicy(target=64), [60] * 6)
        self.assertEqual([d.cap for d in decisions], [60] * 5 + [65])
        decisions = self.run_sequence(ThermalPolicy(target=64), [60] * 200)
        self.assertEqual(decisions[-1].cap, 75)
        # 60.1°C is above target-4 and must not count.
        decisions = self.run_sequence(ThermalPolicy(target=64), [60.1] * 12)
        self.assertEqual({d.cap for d in decisions}, {60})

    def test_auto_78c_limits_immediately_to_40(self):
        decision = ThermalPolicy().decide(78)
        self.assertEqual((decision.cap, decision.no_turbo), (40, 1))
        self.assertEqual(ThermalPolicy("quiet").decide(78).cap, 60)

    def test_85c_guard_in_every_managed_mode_until_six_cool_readings(self):
        for mode in ("auto", "quiet", "balanced", "performance"):
            with self.subTest(mode=mode):
                policy = ThermalPolicy(mode)
                decisions = self.run_sequence(policy, [85, 80, 75, 75, 75, 75, 75, 75])
                self.assertEqual([d.cap for d in decisions[:7]], [25] * 7)
                self.assertTrue(all(d.no_turbo == 1 for d in decisions[:7]))
                self.assertNotEqual(decisions[7].cap, 25)

    def test_sensor_failure_limits_to_40_with_turbo_off(self):
        for mode in ("auto", "quiet", "balanced", "performance"):
            with self.subTest(mode=mode):
                decision = ThermalPolicy(mode).decide(None)
                self.assertEqual((decision.cap, decision.no_turbo), (40, 1))
                self.assertIn("센서", decision.reason)

    def test_regression_sensor_loss_during_85c_guard_keeps_25(self):
        # README: the 25% guard is only relaxed after six readings <= 75°C.
        policy = ThermalPolicy("performance")
        policy.decide(86)
        decision = policy.decide(None)
        self.assertEqual((decision.cap, decision.no_turbo), (25, 1))
        self.assertEqual(policy.decide(80).cap, 25)

    def test_regression_mode_change_does_not_clear_85c_guard(self):
        for previous, selected in (("auto", "performance"), ("performance", "performance")):
            with self.subTest(previous=previous, selected=selected):
                policy = ThermalPolicy(previous)
                policy.decide(86)
                policy.set_mode(selected)
                decision = policy.decide(80)
                self.assertEqual((decision.cap, decision.no_turbo), (25, 1))
                for _ in range(6):
                    decision = policy.decide(70)
                self.assertEqual((decision.cap, decision.no_turbo), (100, 0))


class ControllerOnFakeSysfsSmokeTests(unittest.TestCase):
    """Real Hardware class on a fake sysfs, driven through Controller.tick()."""

    def setUp(self):
        self.root = short_tempdir(self)
        self.sysfs = FakeSysfs(self.root / "sys")
        self.state = self.root / "state"
        self.state.mkdir()
        self.hardware = Hardware(self.sysfs.root)
        self.power = FakePPD()
        self.baseline = make_state(self.state, self.hardware)

    def test_auto_sequence_writes_pstate_and_restore_returns_baseline(self):
        controller = Controller(self.hardware, self.power, self.state)
        self.assertEqual(self.sysfs.limit("max_perf_pct"), 60)
        self.assertEqual(self.sysfs.limit("no_turbo"), 1)
        self.assertEqual(self.power.profile, "power-saver")
        caps = []
        for temperature in (68, 68, 68, 68, 79, 86, None, 70, 70, 70, 70, 70, 70):
            self.sysfs.set_temperature(temperature)
            controller.tick()
            caps.append(self.sysfs.limit("max_perf_pct"))
        self.assertEqual(caps, [60, 55, 55, 50, 40, 25, 25, 25, 25, 25, 25, 25, 40])
        status = controller.request({"op": "status"})
        self.assertEqual(status["limits"]["max_perf_pct"], 40)
        self.assertFalse(status["fan_control"])
        controller.request({"op": "mode", "mode": "restore"})
        self.assertEqual(
            self.hardware.snapshot(),
            {k: v for k, v in self.baseline.items() if k != "power_profile"},
        )
        self.assertEqual(self.power.profile, "balanced")

    def test_regression_mode_request_during_85c_guard_keeps_25(self):
        controller = Controller(self.hardware, self.power, self.state)
        self.sysfs.set_temperature(86)
        controller.tick()
        self.sysfs.set_temperature(80)
        controller.request({"op": "mode", "mode": "performance"})
        self.assertEqual(self.sysfs.limit("max_perf_pct"), 25)
        self.assertEqual(self.sysfs.limit("no_turbo"), 1)

    def test_other_hardware_is_refused(self):
        cases = {
            "other model": lambda s: s.put("devices/virtual/dmi/id/product_name", "GL63 8RC"),
            "other vendor": lambda s: s.put("devices/virtual/dmi/id/sys_vendor", "ACME"),
            "acpi-cpufreq": lambda s: s.put(
                "devices/system/cpu/cpufreq/policy0/scaling_driver", "acpi-cpufreq"
            ),
            "missing control": lambda s: (
                s.root / "devices/system/cpu/intel_pstate/no_turbo"
            ).unlink(),
        }
        for name, mutate in cases.items():
            with self.subTest(name):
                root = short_tempdir(self)
                sysfs = FakeSysfs(root / "sys")
                state = root / "state"
                state.mkdir()
                make_state(state, Hardware(sysfs.root))
                mutate(sysfs)
                before = sorted(p.read_text() for p in sysfs.root.rglob("*") if p.is_file())
                with self.assertRaises(RuntimeError):
                    Controller(Hardware(sysfs.root), FakePPD(), state)
                after = sorted(p.read_text() for p in sysfs.root.rglob("*") if p.is_file())
                self.assertEqual(before, after)

    def test_baseline_from_another_machine_is_refused(self):
        baseline = json.loads((self.state / "baseline.json").read_text())
        baseline["identity"]["model"] = "GL62M 7RD"
        (self.state / "baseline.json").write_text(json.dumps(baseline))
        with self.assertRaises(RuntimeError):
            Controller(self.hardware, self.power, self.state)
        self.assertEqual(self.sysfs.limit("max_perf_pct"), 100)


class FakeCredentials:
    """Stands in for a connection so SO_PEERCRED parsing can be tested with any UID."""

    def __init__(self, uid):
        self.uid = uid

    def getsockopt(self, level, option, size):
        assert (level, option, size) == (socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
        return struct.pack("3i", 4242, self.uid, 4242)


@unittest.skipUnless(hasattr(socket, "SO_PEERCRED"), "SO_PEERCRED is Linux-only")
class ServiceSocketSmokeTests(unittest.TestCase):
    """serve() on a temporary socket with fake sysfs/PPD; CLI talks to it via client.py."""

    allowed_uid = 54321

    def setUp(self):
        self.root = short_tempdir(self)
        self.sysfs = FakeSysfs(self.root / "sys")
        self.state = self.root / "state"
        self.state.mkdir()
        self.power = FakePPD()
        self.baseline = make_state(self.state, Hardware(self.sysfs.root))
        self.socket_path = str(self.root / "control.sock")
        config = self.root / "config.json"
        config.write_text(json.dumps({"allowed_uid": self.allowed_uid, "allowed_gid": 0}))
        self.peer_uid = self.allowed_uid
        real_peer_allowed = service.peer_allowed
        handlers = {}
        patches = [
            patch.object(service, "SOCKET", self.socket_path),
            patch.object(client, "SOCKET", self.socket_path),
            patch.object(service, "Hardware", lambda: Hardware(self.sysfs.root)),
            patch.object(service, "PowerProfiles", lambda: self.power),
            patch.object(service, "Controller", partial(Controller, state=self.state)),
            patch.object(service.os, "geteuid", lambda: 0),
            patch.object(service.os, "chown", lambda *args: None),
            patch.object(service.signal, "signal", lambda sig, fn: handlers.__setitem__(sig, fn)),
            patch.object(
                service,
                "peer_allowed",
                lambda connection, allowed: real_peer_allowed(
                    FakeCredentials(self.peer_uid), allowed
                ),
            ),
        ]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)
        self.failure = []

        def target():
            try:
                service.serve(config)
            except Exception as error:  # pragma: no cover - surfaced by the assertion below
                self.failure.append(error)

        self.thread = threading.Thread(target=target, daemon=True)
        self.thread.start()
        deadline = time.monotonic() + 5
        while not os.path.exists(self.socket_path) and time.monotonic() < deadline:
            if self.failure:
                raise self.failure[0]
            time.sleep(0.02)
        self.assertTrue(os.path.exists(self.socket_path), "service socket did not appear")
        self.stop = handlers[service.signal.SIGTERM]

    def shutdown(self):
        self.stop()
        self.thread.join(5)
        self.assertFalse(self.thread.is_alive())
        self.assertEqual(self.failure, [])

    def raw(self, payload: bytes):
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(5)
            connection.connect(self.socket_path)
            connection.sendall(payload)
            connection.shutdown(socket.SHUT_WR)
            return json.loads(connection.makefile("rb").readline())

    def cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_cli_round_trip_and_restore_on_stop(self):
        code, out, _ = self.cli("status", "--json")
        self.assertEqual(code, 0)
        status = json.loads(out)
        self.assertEqual((status["mode"], status["target_c"]), ("auto", 64))
        self.assertEqual(status["limits"]["max_perf_pct"], 60)
        self.assertEqual(status["cpu_c"], 60)

        code, out, _ = self.cli("mode", "quiet")
        self.assertEqual(code, 0)
        self.assertIn("조용함", out)
        self.assertEqual(self.sysfs.limit("max_perf_pct"), 60)

        code, out, _ = self.cli("mode", "performance")
        self.assertEqual((code, self.sysfs.limit("max_perf_pct")), (0, 100))
        self.assertEqual(self.sysfs.limit("no_turbo"), 0)

        code, _, err = self.cli("target", "90")
        self.assertEqual(code, 1)
        self.assertIn("58~75", err)
        self.assertEqual(self.cli("target", "70")[0], 0)
        settings = json.loads((self.state / "settings.json").read_text())
        self.assertEqual(settings, {"mode": "performance", "target": 70})

        self.shutdown()
        self.assertFalse(os.path.exists(self.socket_path))
        hardware = Hardware(self.sysfs.root)
        self.assertEqual(hardware.snapshot()["limits"], self.baseline["limits"])
        self.assertEqual(self.power.profile, "balanced")

    def test_request_validation_over_socket(self):
        bad = [
            b"[]\n",
            b'{"op": "run", "command": "id"}\n',
            b'{"op": "mode", "mode": "../../etc"}\n',
            b'{"op": "target", "target": "64"}\n',
            b'{"op": "status", "path": "/etc/shadow"}\n',
            b"not json\n",
            b'{"op": "status"}',  # no newline terminator
            b'{"op": "status", "pad": "' + b"x" * 5000 + b'"}\n',
        ]
        for payload in bad:
            with self.subTest(payload=payload[:40]):
                response = self.raw(payload)
                self.assertFalse(response["ok"])
                self.assertIsInstance(response["error"], str)
        self.assertEqual(self.sysfs.limit("max_perf_pct"), 60)
        self.assertTrue(self.raw(b'{"op": "status"}\n')["ok"])
        self.shutdown()

    def test_other_uid_is_rejected_and_root_is_allowed(self):
        self.peer_uid = self.allowed_uid + 1
        response = self.raw(b'{"op": "mode", "mode": "performance"}\n')
        self.assertEqual(response, {"ok": False, "error": "이 사용자는 장치 제어 권한이 없습니다."})
        self.assertEqual(self.sysfs.limit("max_perf_pct"), 60)
        self.peer_uid = 0
        self.assertTrue(self.raw(b'{"op": "status"}\n')["ok"])
        self.shutdown()


class PeerCredentialTests(unittest.TestCase):
    def test_peer_allowed_parses_so_peercred(self):
        self.assertTrue(service.peer_allowed(FakeCredentials(1000), 1000))
        self.assertTrue(service.peer_allowed(FakeCredentials(0), 1000))
        self.assertFalse(service.peer_allowed(FakeCredentials(1001), 1000))

    @unittest.skipUnless(hasattr(socket, "SO_PEERCRED"), "SO_PEERCRED is Linux-only")
    def test_peer_allowed_on_real_socketpair(self):
        left, right = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
        with left, right:
            self.assertTrue(service.peer_allowed(left, os.getuid()))


class CliSmokeTests(unittest.TestCase):
    def setUp(self):
        directory = short_tempdir(self)
        missing = patch.object(client, "SOCKET", str(directory / "missing.sock"))
        missing.start()
        self.addCleanup(missing.stop)

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = cli.main(list(argv))
            except SystemExit as exit_:
                code = exit_.code
        return code, out.getvalue(), err.getvalue()

    def test_version(self):
        code, out, _ = self.run_cli("--version")
        self.assertEqual((code, out.strip()), (0, "0.1.0"))

    def test_service_not_running_is_a_clean_error(self):
        for argv in (["status"], ["status", "--json"], ["mode", "auto"], ["restore"]):
            with self.subTest(argv=argv):
                code, out, err = self.run_cli(*argv)
                self.assertEqual(code, 1)
                self.assertIn("서비스가 실행되지 않았습니다", err)
                self.assertNotIn("Traceback", err)

    def test_argument_validation(self):
        for argv in (
            ["mode", "turbo"],
            ["target", "hot"],
            ["run", "--cpu", "0", "--", "true"],
            ["run", "--cpu", "401", "--", "true"],
            ["run", "--cpu", "100"],
            ["monitor", "--seconds", "4"],
            ["monitor", "--seconds", "3601"],
            ["effects", "toggle"],
        ):
            with self.subTest(argv=argv):
                self.assertEqual(self.run_cli(*argv)[0], 2)

    def test_run_builds_user_scope_command_without_shell(self):
        with patch.object(cli.subprocess, "run") as run:
            run.return_value.returncode = 7
            code, _, _ = self.run_cli("run", "--cpu", "150", "--", "make", "-j2", "a b")
        self.assertEqual(code, 7)
        command = run.call_args.args[0]
        self.assertEqual(command[:5], ["systemd-run", "--user", "--scope", "--quiet", "--collect"])
        self.assertEqual(command[5:], ["--property=CPUQuota=150%", "--", "make", "-j2", "a b"])
        self.assertNotIn("shell", run.call_args.kwargs)


def gui_available():
    try:
        import gi  # noqa: F401
        import psutil  # noqa: F401
    except ImportError:
        return False
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


@unittest.skipUnless(
    gui_available(),
    "needs python3-gi + GTK 3 + psutil and a display (run under xvfb-run); "
    "GUI interaction itself is not covered",
)
class GuiStartupSmokeTest(unittest.TestCase):
    def test_window_starts_and_reports_missing_service(self):
        directory = short_tempdir(self)
        probe = textwrap.dedent(
            """
            import json, sys
            sys.path.insert(0, sys.argv[1])
            from freiren_quiet import client
            client.SOCKET = sys.argv[2]
            from freiren_quiet.gui import Gio, GLib, QuietApp
            app = QuietApp()
            app.set_flags(Gio.ApplicationFlags.NON_UNIQUE)
            result = {}
            def check():
                window = app.window
                if window is None or window.busy:
                    return True
                result["message"] = window.message.get_text()
                result["error"] = window.message.get_style_context().has_class("error")
                window.destroy()
                app.quit()
                return False
            GLib.timeout_add(200, check)
            GLib.timeout_add_seconds(15, app.quit)
            app.run(None)
            print(json.dumps(result))
            """
        )
        environment = dict(os.environ, XDG_STATE_HOME=str(directory / "state"))
        completed = subprocess.run(
            [sys.executable, "-c", probe, str(PACKAGE_ROOT), str(directory / "none.sock")],
            capture_output=True,
            text=True,
            timeout=40,
            env=environment,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertNotIn("Traceback", completed.stderr)
        result = json.loads(completed.stdout.strip().splitlines()[-1])
        self.assertTrue(result["error"])
        self.assertIn("서비스가 실행되지 않았습니다", result["message"])


if __name__ == "__main__":
    unittest.main()
