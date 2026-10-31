"""End-to-end smoke tests on a fake sysfs tree and a fake power-profiles-daemon.

Nothing here touches the real /sys, /etc, /var, /run, systemd or D-Bus.
"""

import contextlib
import io
import json
import os
import shutil
import socket
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from freiren_quiet import cli, client, service
from freiren_quiet.hardware import Hardware
from freiren_quiet.policy import ThermalPolicy
from freiren_quiet.profiles import PRESETS, validate_custom

PSTATE = "devices/system/cpu/intel_pstate"
CPUFREQ = "devices/system/cpu/cpufreq"
RAPL = "class/powercap/intel-rapl:0"
CORETEMP = "class/hwmon/hwmon3"


def build_sysfs(root, model="GL62 6QE"):
    """Create a minimal fake sysfs of the supported laptop under ``root``."""

    def put(name, value):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{value}\n")

    put("devices/virtual/dmi/id/sys_vendor", "Micro-Star International Co., Ltd.")
    put("devices/virtual/dmi/id/product_name", model)
    for index in range(4):
        put(f"{CPUFREQ}/policy{index}/scaling_driver", "intel_pstate")
        put(f"{CPUFREQ}/policy{index}/energy_performance_preference", "balance_performance")
    for name, value in (("no_turbo", 0), ("min_perf_pct", 22), ("max_perf_pct", 100)):
        put(f"{PSTATE}/{name}", value)
    for name, value in (
        ("name", "package-0"),
        ("constraint_0_name", "long_term"),
        ("constraint_1_name", "short_term"),
        ("constraint_0_power_limit_uw", 45_000_000),
        ("constraint_1_power_limit_uw", 56_250_000),
    ):
        put(f"{RAPL}/{name}", value)
    put(f"{CORETEMP}/name", "coretemp")
    put(f"{CORETEMP}/temp1_label", "Package id 0")
    put(f"{CORETEMP}/temp1_input", 55000)
    return put


class FakePowerProfiles:
    def __init__(self, profile="balanced"):
        self.profile = profile

    def current(self):
        return self.profile

    def set(self, profile):
        self.profile = profile
        return profile


class SysfsCase(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        base = Path(directory.name)
        self.sys_root = base / "sys"
        self.state = base / "state"
        self.state.mkdir()
        self.put = build_sysfs(self.sys_root)
        self.hardware = Hardware(self.sys_root)
        self.power = FakePowerProfiles()
        baseline = self.hardware.snapshot()
        baseline["power_profile"] = None
        (self.state / "baseline.json").write_text(json.dumps(baseline))
        self.original = self.hardware.snapshot()

    def read(self, name):
        return (self.sys_root / name).read_text().strip()

    def temperature(self, celsius):
        self.put(f"{CORETEMP}/temp1_input", int(celsius * 1000))

    def controller(self):
        return service.Controller(self.hardware, self.power, self.state)


class CliParsingSmokeTests(unittest.TestCase):
    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = cli.main(list(argv))
            except SystemExit as exit_:
                code = exit_.code
        return code, out.getvalue(), err.getvalue()

    def test_version_and_help(self):
        self.assertEqual(self.run_cli("--version")[:2], (0, "0.3.0\n"))
        code, out, _ = self.run_cli("--help")
        self.assertEqual(code, 0)
        for command in ("status", "mode", "target", "custom", "reset", "effects", "run"):
            self.assertIn(command, out)

    def test_invalid_arguments_are_rejected_before_any_request(self):
        with patch.object(client, "request", side_effect=AssertionError("no request")):
            for argv in (
                ("mode", "turbo"),
                ("target", "64.5"),
                ("custom",),
                ("custom", "--cap", "70", "--preference", "max"),
                ("custom", "--cap", "70", "--power", "x"),
                ("run", "--cpu", "0", "--", "true"),
                ("run", "--cpu", "401", "--", "true"),
                ("run", "--cpu", "100"),
                ("monitor", "--seconds", "4"),
                ("effects", "delete"),
            ):
                with self.subTest(argv=argv):
                    self.assertEqual(self.run_cli(*argv)[0], 2)

    def test_run_wraps_program_in_a_user_scope_with_cpu_quota(self):
        with patch.object(cli.subprocess, "run") as run:
            run.return_value.returncode = 7
            self.assertEqual(self.run_cli("run", "--cpu", "100", "--", "make", "-j2")[0], 7)
        self.assertEqual(
            run.call_args.args[0],
            [
                "systemd-run",
                "--user",
                "--scope",
                "--quiet",
                "--collect",
                "--property=CPUQuota=100%",
                "--",
                "make",
                "-j2",
            ],
        )

    def test_commands_map_to_the_documented_socket_requests(self):
        status = {
            "mode_label": "균형",
            "cpu_c": 61.0,
            "limits": {"max_perf_pct": 75},
            "reason": "균형",
            "error": None,
        }
        cases = (
            (("status",), ("status",), {}),
            (("mode", "balanced"), ("mode",), {"mode": "balanced"}),
            (("restore",), ("mode",), {"mode": "restore"}),
            (("target", "64"), ("target",), {"target": 64}),
            (("reset",), ("reset",), {}),
            (
                ("custom", "--cap", "70", "--preference", "balance_power", "--power", "24")
                + ("--boost", "32"),
                ("configure",),
                {
                    "settings": {
                        "cap": 70,
                        "turbo": False,
                        "preference": "balance_power",
                        "power_w": 24.0,
                        "boost_w": 32.0,
                    }
                },
            ),
        )
        for argv, args, kwargs in cases:
            with self.subTest(argv=argv), patch.object(client, "request") as request:
                request.return_value = status
                code, out, _ = self.run_cli(*argv)
                self.assertEqual(code, 0)
                self.assertIn("CPU 61°C · 상한 75%", out)
                if args == ("status",):
                    request.assert_called_once_with()
                else:
                    request.assert_called_once_with(*args, **kwargs)

    def test_missing_service_is_a_clean_error(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(client, "SOCKET", str(Path(directory) / "missing.sock")):
                code, out, err = self.run_cli("status", "--json")
        self.assertEqual((code, out), (1, ""))
        self.assertIn("서비스가 실행되지 않았습니다", err)


class PolicySequenceSmokeTests(unittest.TestCase):
    def test_target_range_is_58_to_75(self):
        for target in (58, 64, 75):
            self.assertEqual(ThermalPolicy(target=target).target, target)
        for target in (57, 76):
            with self.assertRaises(ValueError):
                ThermalPolicy(target=target)

    def test_85c_protection_on_a_heat_up_cool_down_sequence(self):
        for mode in ("auto", "quiet", "balanced", "performance", "custom"):
            with self.subTest(mode=mode):
                policy = ThermalPolicy(mode, custom=PRESETS["performance"])
                caps = [policy.decide(t).cap for t in (60, 70, 80, 84.9)]
                self.assertNotIn(25, caps)
                hot = policy.decide(85)
                self.assertEqual((hot.cap, hot.no_turbo), (25, 1))
                # 76 °C resets the cool-down count; six samples at <= 75 °C release it.
                for temperature in (80, 76, 75, 70, 70, 70, 70):
                    self.assertEqual(policy.decide(temperature).cap, 25)
                self.assertGreater(policy.decide(70).cap, 25)

    def test_custom_power_limit_grid(self):
        def settings(power, boost):
            return {**PRESETS["balanced"], "power_w": power, "boost_w": boost}

        for power, boost in ((10, 10), (10.25, 56.25), (45, 45), (23.75, 32.5), (None, None)):
            with self.subTest(power=power, boost=boost):
                self.assertEqual(validate_custom(settings(power, boost))["boost_w"], boost)
        for power, boost in (
            (9.75, 20),
            (45.25, 50),
            (20, 56.5),
            (10.1, 20),
            (20, 20.3),
            (30, 29.75),
            (20, None),
            (None, 20),
        ):
            with self.subTest(power=power, boost=boost), self.assertRaises(ValueError):
                validate_custom(settings(power, boost))


class ControllerSysfsSmokeTests(SysfsCase):
    def test_performance_mode_hits_85c_guard_on_real_sysfs_writes(self):
        controller = self.controller()
        controller.request({"op": "mode", "mode": "performance"})
        self.assertEqual(
            (self.read(f"{PSTATE}/max_perf_pct"), self.read(f"{PSTATE}/no_turbo")), ("100", "0")
        )
        self.assertEqual(
            self.read(f"{CPUFREQ}/policy2/energy_performance_preference"), "performance"
        )
        self.temperature(86)
        controller.tick()
        self.assertEqual(
            (self.read(f"{PSTATE}/max_perf_pct"), self.read(f"{PSTATE}/no_turbo")), ("25", "1")
        )
        self.temperature(72)
        for _ in range(5):
            controller.tick()
            self.assertEqual(self.read(f"{PSTATE}/max_perf_pct"), "25")
        controller.tick()
        self.assertEqual(self.read(f"{PSTATE}/max_perf_pct"), "100")
        self.assertIsNone(controller.error)

    def test_missing_sensor_limits_cpu(self):
        controller = self.controller()
        controller.request({"op": "mode", "mode": "performance"})
        (self.sys_root / CORETEMP / "temp1_input").unlink()
        controller.tick()
        self.assertEqual(controller.status()["cpu_c"], None)
        self.assertEqual(
            (self.read(f"{PSTATE}/max_perf_pct"), self.read(f"{PSTATE}/no_turbo")), ("40", "1")
        )

    def test_custom_power_limits_are_written_and_reset_restores(self):
        controller = self.controller()
        settings = {
            "cap": 70,
            "turbo": False,
            "preference": "balance_power",
            "power_w": 24,
            "boost_w": 32.25,
        }
        controller.request({"op": "configure", "settings": settings})
        self.assertEqual(self.read(f"{RAPL}/constraint_0_power_limit_uw"), "24000000")
        self.assertEqual(self.read(f"{RAPL}/constraint_1_power_limit_uw"), "32250000")
        self.assertEqual(self.read(f"{PSTATE}/max_perf_pct"), "70")
        controller.request({"op": "reset"})
        self.assertEqual(self.hardware.snapshot(), self.original)

    def test_service_refuses_unsupported_hardware(self):
        self.put("devices/virtual/dmi/id/product_name", "GL63 8RC")
        with self.assertRaisesRegex(RuntimeError, "GL62 6QE"):
            self.controller()


class UnsupportedHardwareTests(unittest.TestCase):
    def test_missing_dmi_or_cpufreq_is_a_clear_refusal(self):
        # Regression: an empty /sys (VMs, containers, non-Intel) used to raise a bare
        # FileNotFoundError instead of the documented refusal.
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError, "GL62 6QE / intel_pstate"):
                Hardware(Path(directory)).validate()

    def test_other_model_and_other_driver_are_refused(self):
        for change in (
            ("devices/virtual/dmi/id/product_name", "GE62 6QF"),
            ("devices/virtual/dmi/id/sys_vendor", "Other Vendor"),
            (f"{CPUFREQ}/policy0/scaling_driver", "acpi-cpufreq"),
        ):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                build_sysfs(root)(*change)
                with self.assertRaises(RuntimeError):
                    Hardware(root).validate()

    def test_installer_refuses_before_touching_the_system(self):
        from scripts import install

        user = SimpleNamespace(pw_uid=1000, pw_gid=1000, pw_name="tester")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            build_sysfs(root, model="Other laptop")
            with (
                patch.object(sys, "argv", ["install.py", "--user", "tester"]),
                patch.object(install.os, "geteuid", return_value=0),
                patch.object(install.pwd, "getpwnam", return_value=user),
                patch.object(install.grp, "getgrgid"),
                patch.object(install, "Hardware", lambda: Hardware(root)),
                patch.object(install.subprocess, "run") as run,
                patch.object(install, "atomic_json") as write,
                patch.object(Path, "mkdir") as mkdir,
            ):
                with self.assertRaisesRegex(RuntimeError, "GL62 6QE"):
                    install.main()
        run.assert_not_called()
        write.assert_not_called()
        mkdir.assert_not_called()

    def test_installer_and_uninstaller_require_root(self):
        from scripts import install, uninstall

        stderr = io.StringIO()
        with (
            patch.object(sys, "argv", ["install.py", "--user", "tester"]),
            patch.object(os, "geteuid", return_value=1000),
            patch("subprocess.run") as run,
            contextlib.redirect_stderr(stderr),
        ):
            with self.assertRaises(SystemExit) as installer:
                install.main()
            with self.assertRaises(SystemExit) as uninstaller:
                uninstall.main()
        self.assertEqual(installer.exception.code, 2)
        self.assertIn("sudo", str(uninstaller.exception.code))
        run.assert_not_called()

    def test_live_verifier_requires_explicit_confirmation(self):
        from scripts import verify_live

        with (
            patch.object(sys, "argv", ["verify_live.py"]),
            patch.object(verify_live.client, "request") as request,
            contextlib.redirect_stderr(io.StringIO()),
            self.assertRaises(SystemExit),
        ):
            verify_live.main()
        request.assert_not_called()


class SocketServiceSmokeTests(SysfsCase):
    """Run the real serve() loop on a temporary socket, driven through the real CLI."""

    def setUp(self):
        super().setUp()
        runtime = tempfile.mkdtemp(prefix="fq-")
        self.addCleanup(shutil.rmtree, runtime, ignore_errors=True)
        self.socket_path = str(Path(runtime) / "control.sock")
        config = self.state / "config.json"
        self.allowed_uid = 4242
        config.write_text(json.dumps({"allowed_uid": self.allowed_uid, "allowed_gid": 4242}))
        self.peer_uid = self.allowed_uid
        handlers = {}
        state = self.state
        real_controller = service.Controller
        real_peer_allowed = service.peer_allowed

        def peer_allowed(connection, allowed_uid):
            # Exercise the real SO_PEERCRED read, then substitute a fake peer UID.
            real_peer_allowed(connection, os.getuid())
            return self.peer_uid in (0, allowed_uid)

        patches = (
            patch.object(service, "SOCKET", self.socket_path),
            patch.object(client, "SOCKET", self.socket_path),
            patch.object(service.os, "geteuid", return_value=0),
            patch.object(service.os, "chown"),
            patch.object(service.logging, "basicConfig"),
            patch.object(service.signal, "signal", lambda sig, fn: handlers.setdefault(sig, fn)),
            patch.object(service, "Hardware", lambda: self.hardware),
            patch.object(service, "PowerProfiles", lambda: self.power),
            patch.object(service, "Controller", lambda h, p: real_controller(h, p, state)),
            patch.object(service, "peer_allowed", peer_allowed),
        )
        for item in patches:
            item.start()
            self.addCleanup(item.stop)
        errors = []

        def run():
            try:
                service.serve(config)
            except BaseException as error:  # pragma: no cover - surfaced below
                errors.append(error)

        self.thread = threading.Thread(target=run, daemon=True)
        self.handlers = handlers
        self.errors = errors
        self.thread.start()
        self.addCleanup(self.shutdown)
        deadline = time.monotonic() + 10
        while not os.path.exists(self.socket_path):
            self.assertFalse(errors, errors)
            self.assertLess(time.monotonic(), deadline, "service did not start")
            time.sleep(0.02)

    def shutdown(self):
        # Also runs as a cleanup, so a failed assertion never leaves the loop running.
        if self.thread.is_alive() and self.handlers:
            signum = next(iter(self.handlers))
            self.handlers[signum](signum, None)
        self.thread.join(10)

    def stop(self):
        self.shutdown()
        self.assertFalse(self.thread.is_alive())
        self.assertFalse(self.errors, self.errors)
        self.assertFalse(os.path.exists(self.socket_path))

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def raw(self, payload):
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(5)
            connection.connect(self.socket_path)
            connection.sendall(payload)
            return json.loads(connection.makefile("rb").readline())

    def test_cli_round_trip_and_request_validation(self):
        code, out, _ = self.run_cli("status", "--json")
        self.assertEqual(code, 0)
        status = json.loads(out)
        self.assertEqual(
            (status["mode"], status["cpu_c"], status["fan_control"]), ("auto", 55.0, False)
        )

        self.assertEqual(self.run_cli("mode", "quiet")[0], 0)
        self.assertEqual(self.read(f"{PSTATE}/max_perf_pct"), "60")
        self.assertEqual(self.read(f"{RAPL}/constraint_0_power_limit_uw"), "18000000")
        self.assertEqual(self.run_cli("target", "70")[0], 0)

        before = self.hardware.snapshot()
        for argv in (
            ("target", "80"),
            ("custom", "--cap", "70", "--power", "30", "--boost", "28"),
            ("custom", "--cap", "70", "--power", "24.1", "--boost", "32"),
            ("custom", "--cap", "70", "--power", "50", "--boost", "56"),
            ("custom", "--cap", "20"),
        ):
            with self.subTest(argv=argv):
                code, _, err = self.run_cli(*argv)
                self.assertEqual(code, 1)
                self.assertTrue(err.startswith("Freiren Quiet: "), err)
                self.assertEqual(self.hardware.snapshot(), before)

        for payload in (
            b'{"op": "run", "command": "id"}\n',
            b'{"op": "status", "path": "/etc/shadow"}\n',
            b'{"op": "mode", "mode": "../../etc"}\n',
            b"not json\n",
            b'{"op": "status"}',  # no newline terminator
            b"{" + b" " * 5000 + b"}\n",
        ):
            with self.subTest(payload=payload[:40]):
                response = self.raw(payload)
                self.assertFalse(response["ok"])
                self.assertTrue(response["error"])
        self.assertEqual(self.hardware.snapshot(), before)

        code = self.run_cli(
            "custom",
            "--cap",
            "70",
            "--preference",
            "balance_power",
            "--power",
            "24",
            "--boost",
            "32",
        )[0]
        self.assertEqual(code, 0)
        self.assertEqual(self.read(f"{PSTATE}/max_perf_pct"), "70")
        self.assertEqual(self.read(f"{RAPL}/constraint_1_power_limit_uw"), "32000000")

        code, out, _ = self.run_cli("reset")
        self.assertEqual(code, 0)
        self.assertIn("관리 해제", out)
        self.assertEqual(self.hardware.snapshot(), self.original)
        self.stop()

    def test_other_uid_is_rejected_and_stop_restores_cpu(self):
        started = self.hardware.snapshot()
        self.peer_uid = 5555
        code, _, err = self.run_cli("mode", "performance")
        self.assertEqual(code, 1)
        self.assertIn("권한", err)
        self.assertEqual(self.hardware.snapshot(), started)

        self.peer_uid = 0  # root is always allowed
        self.assertEqual(self.run_cli("mode", "performance")[0], 0)
        self.assertEqual(self.read(f"{PSTATE}/no_turbo"), "0")
        self.assertEqual(
            self.read(f"{CPUFREQ}/policy0/energy_performance_preference"), "performance"
        )
        self.stop()
        self.assertEqual(self.hardware.snapshot(), self.original)


class ClientRejectedPeerTests(unittest.TestCase):
    def test_rejection_reply_is_read_even_if_service_closed_first(self):
        # Regression: serve() answers a rejected UID before reading the request and closes.
        # If that happened before the client's sendall, the CLI showed "Broken pipe"
        # instead of the permission error.
        runtime = tempfile.mkdtemp(prefix="fq-")
        self.addCleanup(shutil.rmtree, runtime, ignore_errors=True)
        path = str(Path(runtime) / "control.sock")
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.addCleanup(server.close)
        server.bind(path)
        server.listen(1)
        closed = threading.Event()

        def reject():
            connection, _ = server.accept()
            with connection:
                reply = {"ok": False, "error": "이 사용자는 장치 제어 권한이 없습니다."}
                connection.sendall((json.dumps(reply, ensure_ascii=False) + "\n").encode())
            closed.set()

        class LateSocket(socket.socket):
            def sendall(self, data, *args):
                if threading.current_thread() is threading.main_thread():
                    closed.wait(5)  # the client sends only after the service closed
                return super().sendall(data, *args)

        thread = threading.Thread(target=reject, daemon=True)
        thread.start()
        with (
            patch.object(client, "SOCKET", path),
            patch.object(client.socket, "socket", LateSocket),
            self.assertRaisesRegex(RuntimeError, "권한"),
        ):
            client.request("mode", mode="performance")
        thread.join(5)

    def test_closed_connection_without_reply_is_a_clean_error(self):
        runtime = tempfile.mkdtemp(prefix="fq-")
        self.addCleanup(shutil.rmtree, runtime, ignore_errors=True)
        path = str(Path(runtime) / "control.sock")
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.addCleanup(server.close)
        server.bind(path)
        server.listen(1)

        def crash():
            connection, _ = server.accept()
            with connection:
                connection.recv(4096)

        thread = threading.Thread(target=crash, daemon=True)
        thread.start()
        with (
            patch.object(client, "SOCKET", path),
            self.assertRaisesRegex(RuntimeError, "응답하지 않았습니다"),
        ):
            client.request()
        thread.join(5)


class PeerCredentialTests(unittest.TestCase):
    def test_peer_allowed_reads_so_peercred(self):
        left, right = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
        with left, right:
            self.assertTrue(service.peer_allowed(left, os.getuid()))
            if os.getuid() != 0:
                self.assertFalse(service.peer_allowed(left, os.getuid() + 1))


if __name__ == "__main__":
    unittest.main()
