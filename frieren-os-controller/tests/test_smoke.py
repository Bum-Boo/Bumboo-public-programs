"""End-to-end smoke tests through the real CLI, socket API, MCP stdio server and installer.

Everything runs against temporary XDG/HOME directories with systemctl, systemd-analyze
and the Quiet service replaced by fakes. No live systemd manager, KDE session or GTK
display is used.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import stat
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from frieren_controller import cli
from frieren_controller.core import Controller, ControllerError
from frieren_controller.server import Handler, ThreadedServer, serve, socket_path

PROJECT = Path(__file__).resolve().parents[1]
SERVICE = "[Unit]\nDescription=Smoke\n[Service]\nExecStart=/usr/bin/true\n"


class FakeSystem:
    """Stands in for systemctl/systemd-analyze, backed by a synthetic user unit directory."""

    def __init__(self, unit_dir: Path):
        self.unit_dir = unit_dir
        self.timer_enabled = False
        self.calls: list[list[str]] = []

    def __call__(self, argv, **_kwargs):
        self.calls.append(list(argv))
        out, code, err = "", 0, ""
        if argv[0] == "/usr/bin/systemd-analyze":
            if "Bogus=" in Path(argv[-1]).read_text():
                code, err = 1, "Unknown key name 'Bogus'"
        elif argv[0] != "/usr/bin/systemctl":
            raise AssertionError(f"unexpected command {argv}")
        elif "list-unit-files" in argv:
            state = "enabled" if self.timer_enabled else "disabled"
            out = json.dumps([{"unit_file": "smoke.timer", "state": state}])
        elif "list-units" in argv:
            active = "active" if self.timer_enabled else "inactive"
            out = json.dumps(
                [{"unit": "smoke.timer", "active": active, "sub": "waiting", "description": "S"}]
            )
        elif "show" in argv and argv[-1] == "smoke.timer":
            active = "active" if self.timer_enabled else "inactive"
            state = "enabled" if self.timer_enabled else "disabled"
            out = (
                "Id=smoke.timer\nDescription=S\nLoadState=loaded\n"
                f"ActiveState={active}\nSubState=waiting\nUnitFileState={state}\n"
            )
        elif "show" in argv:
            path = self.unit_dir / argv[-1]
            loaded = path.is_file()
            out = (
                f"LoadState={'loaded' if loaded else 'not-found'}\n"
                f"FragmentPath={path if loaded else ''}\nDropInPaths=\nActiveState=inactive\n"
            )
        elif "enable" in argv:
            self.timer_enabled = True
        elif "disable" in argv:
            self.timer_enabled = False
        elif "daemon-reload" in argv:
            pass
        else:
            raise AssertionError(f"unexpected systemctl call {argv}")
        return subprocess.CompletedProcess(argv, code, out, err)


class FakeQuiet:
    def status(self):
        return {"mode": "balanced", "mode_label": "균형", "target_c": 64, "cpu_c": 50.0, "limits": {}}

    def effects_enabled(self):
        return False


def run_cli(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = cli.main(list(argv))
        except SystemExit as exc:
            code = exc.code
    return code, out.getvalue(), err.getvalue()


class SmokeBase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.runtime = self.root / "runtime"
        self.runtime.mkdir(mode=0o700)
        env = {
            "HOME": str(self.root / "home"),
            "XDG_RUNTIME_DIR": str(self.runtime),
            "XDG_CONFIG_HOME": str(self.root / "config"),
            "XDG_STATE_HOME": str(self.root / "state-home"),
        }
        patcher = patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.env = {**os.environ}
        self.unit_dir = self.root / "config/systemd/user"

    def start_api(self):
        self.system = FakeSystem(self.unit_dir)
        self.controller = Controller(self.root / "state", runner=self.system, quiet=FakeQuiet())
        server = ThreadedServer(str(socket_path()), Handler)
        server.controller = self.controller
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)


class CliSmokeTests(SmokeBase):
    def test_help_lists_documented_commands(self):
        code, out, _ = run_cli("--help")
        self.assertEqual(code, 0)
        for command in ("daemon", "gui", "mcp", "dashboard", "jobs", "quiet", "list", "toggle", "note"):
            self.assertIn(command, out)
        result = subprocess.run(
            [sys.executable, "-m", "frieren_controller", "list", "--help"],
            capture_output=True,
            text=True,
            timeout=30,
            env=self.env,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--scope", result.stdout)

    def test_invalid_arguments_are_rejected_by_parser(self):
        code, _, err = run_cli("list", "--scope", "everything")
        self.assertEqual(code, 2)
        self.assertIn("invalid choice", err)

    def test_documented_commands_without_daemon_fail_without_traceback(self):
        for argv in (["dashboard"], ["list", "--scope", "user", "--kind", "timer"], ["quiet", "status"]):
            result = subprocess.run(
                [sys.executable, "-m", "frieren_controller", *argv],
                capture_output=True,
                text=True,
                timeout=30,
                env=self.env,
            )
            self.assertEqual(result.returncode, 1, argv)
            self.assertNotIn("Traceback", result.stderr)
            self.assertIn("컨트롤러 서비스에 연결하지 못했어요", result.stderr)

    def test_daemon_with_missing_runtime_directory_reports_error(self):
        # Regression: serve() used to raise a raw FileNotFoundError traceback.
        missing = self.root / "no-runtime"
        with patch.dict(os.environ, {"XDG_RUNTIME_DIR": str(missing)}):
            with patch("frieren_controller.session_environment.load_desktop_environment"):
                with self.assertRaisesRegex(ControllerError, "소켓을 만들지 못했어요"):
                    serve(controller=object())
            with patch("frieren_controller.session_environment.load_desktop_environment"):
                code, _, err = run_cli("daemon")
        self.assertEqual(code, 1)
        self.assertIn(str(missing), err)

    def test_desktop_bus_failures_become_controller_errors(self):
        # Regression: a missing session bus raised GLib.Error past serve()'s ControllerError guard.
        from frieren_controller.desktop_common import SessionBus
        from frieren_controller.monitor import KDEBackend

        with patch.dict(sys.modules, {"gi.repository": None}):
            for backend in (KDEBackend, SessionBus):
                with self.assertRaises(ControllerError):
                    backend()
        if gtk3_available():
            from gi.repository import Gio, GLib

            failure = GLib.Error("synthetic: no session bus")
            with patch.object(Gio, "bus_get_sync", side_effect=failure):
                for backend in (KDEBackend, SessionBus):
                    with self.assertRaisesRegex(ControllerError, "D-Bus"):
                        backend()

    def test_real_daemon_serves_cli_without_desktop_session(self):
        # Regression: the daemon exited with a traceback when no D-Bus session bus was reachable.
        env = {**self.env, "DBUS_SESSION_BUS_ADDRESS": f"unix:path={self.root / 'no-bus'}"}
        for name in ("DISPLAY", "WAYLAND_DISPLAY"):
            env.pop(name, None)
        daemon = subprocess.Popen(
            [sys.executable, "-m", "frieren_controller", "daemon"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )
        self.addCleanup(daemon.stderr.close)
        self.addCleanup(daemon.wait, 10)
        self.addCleanup(daemon.terminate)
        sock = self.runtime / "frieren-os-controller.sock"
        for _ in range(150):
            if sock.is_socket() or daemon.poll() is not None:
                break
            threading.Event().wait(0.1)
        self.assertIsNone(daemon.poll(), daemon.stderr.read() if daemon.poll() is not None else "")
        self.assertEqual(stat.S_IMODE(sock.stat().st_mode), 0o600)
        for argv, expected in (
            (["note", "user", "demo.timer", "데몬 메모"], 0),
            (["note", "user", "demo.timer"], 0),
        ):
            result = subprocess.run(
                [sys.executable, "-m", "frieren_controller", *argv],
                capture_output=True,
                text=True,
                timeout=30,
                env=env,
            )
            self.assertEqual(result.returncode, expected, result.stderr)
        self.assertEqual(json.loads(result.stdout), "데몬 메모")
        state = Path(env["HOME"]) / ".local/state/frieren-os-controller/notes.json"
        self.assertTrue(state.is_file())

    def test_gui_without_gtk_bindings_reports_error(self):
        # Regression: a missing PyGObject/GTK 3 typelib used to end in a traceback.
        with patch.dict(sys.modules, {"gi": None}):
            sys.modules.pop("frieren_controller.gui", None)  # force a fresh import that needs gi
            code, _, err = run_cli("gui")
        self.assertEqual(code, 1)
        self.assertIn("GTK 3", err)


class ApiSmokeTests(SmokeBase):
    def test_cli_list_toggle_note_and_quiet_through_socket(self):
        self.start_api()
        self.assertEqual(socket_path().parent, self.runtime)
        code, out, err = run_cli("list", "--scope", "user", "--kind", "timer")
        self.assertEqual(code, 0, err)
        rows = json.loads(out)
        self.assertEqual([row["unit"] for row in rows], ["smoke.timer"])
        self.assertFalse(rows[0]["enabled"])

        code, out, err = run_cli("toggle", "user", "smoke.timer", "on", "--preview")
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["action"], "enable --now")
        self.assertFalse(self.system.timer_enabled)

        code, out, err = run_cli("toggle", "user", "smoke.timer", "on")
        self.assertEqual(code, 0, err)
        self.assertTrue(self.system.timer_enabled)

        self.assertEqual(run_cli("note", "user", "smoke.timer", "합성 메모")[0], 0)
        code, out, _ = run_cli("note", "user", "smoke.timer")
        self.assertEqual(json.loads(out), "합성 메모")

        code, out, err = run_cli("quiet", "status")
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["mode"], "balanced")

        code, _, err = run_cli("toggle", "user", "bad;name.timer", "on")
        self.assertEqual(code, 1)
        self.assertIn("이름이 올바르지 않아요", err)
        self.assertEqual(
            [entry["action"] for entry in self.controller.audit_log()], ["toggle_unit", "set_note"]
        )

    def test_job_file_round_trip_into_xdg_config(self):
        self.start_api()
        code, out, err = run_cli("jobs", "read", "smoke.service")
        self.assertEqual(code, 0, err)
        before = json.loads(out)
        self.assertFalse(before["exists"])

        draft = self.root / "draft.service"
        draft.write_text(SERVICE)
        code, out, err = run_cli(
            "jobs", "save", "smoke.service", "--file", str(draft), "--revision", before["revision"]
        )
        self.assertEqual(code, 0, err)
        saved = json.loads(out)
        self.assertTrue(saved["saved"])
        target = self.unit_dir / "smoke.service"
        self.assertEqual(target.read_text(), SERVICE)
        self.assertTrue(any("daemon-reload" in call for call in self.system.calls))
        self.assertFalse(any("start" in call or "enable" in call for call in self.system.calls))

        # Invalid content and stale revisions leave the saved file untouched.
        draft.write_text(SERVICE + "Bogus=1\n")
        code, _, err = run_cli(
            "jobs", "save", "smoke.service", "--file", str(draft), "--revision", saved["revision"]
        )
        self.assertEqual(code, 1)
        self.assertIn("Bogus", err)
        code, _, err = run_cli(
            "jobs", "save", "smoke.service", "--file", str(draft), "--revision", before["revision"]
        )
        self.assertEqual(code, 1)
        self.assertIn("다른 곳에서", err)
        self.assertEqual(target.read_text(), SERVICE)
        self.assertNotIn("ExecStart", (self.controller.state_dir / "audit.jsonl").read_text())


class McpSmokeTests(SmokeBase):
    def mcp_session(self):
        process = subprocess.Popen(
            [sys.executable, "-m", "frieren_controller", "mcp"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=self.env,
        )

        def finish():
            if process.poll() is None:
                process.stdin.close()
                try:
                    process.wait(10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            process.stdout.close()
            process.stderr.close()

        self.addCleanup(finish)
        timer = threading.Timer(30, process.kill)
        timer.start()
        self.addCleanup(timer.cancel)
        counter = iter(range(1, 1000))

        def request(method, params=None):
            number = next(counter)
            message = {"jsonrpc": "2.0", "id": number, "method": method, "params": params or {}}
            process.stdin.write(json.dumps(message) + "\n")
            process.stdin.flush()
            while True:
                line = process.stdout.readline()
                if not line:
                    self.fail("MCP server closed stdout: " + process.stderr.read()[-2000:])
                reply = json.loads(line)
                if reply.get("id") == number:
                    return reply

        init = request(
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "smoke", "version": "0"},
            },
        )
        self.assertEqual(init["result"]["serverInfo"]["name"], "Frieren OS Controller")
        process.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
        process.stdin.flush()
        return process, request

    def test_initialize_list_tools_and_call_through_socket(self):
        self.start_api()
        _, request = self.mcp_session()
        tools = {tool["name"] for tool in request("tools/list")["result"]["tools"]}
        self.assertTrue({"list_units", "toggle_unit", "job_unit_save", "quiet_status"} <= tools)
        reply = request("tools/call", {"name": "list_units", "arguments": {"scope": "user", "kind": "timer"}})
        self.assertFalse(reply["result"].get("isError"), reply)
        self.assertIn("smoke.timer", json.dumps(reply["result"], ensure_ascii=False))

    def test_tool_errors_carry_controller_message(self):
        # Regression: ControllerError reached MCP clients only as "Error executing tool <name>".
        self.start_api()
        process, request = self.mcp_session()
        reply = request(
            "tools/call",
            {"name": "toggle_unit", "arguments": {"scope": "user", "unit": "x;y", "enabled": True}},
        )
        self.assertTrue(reply["result"]["isError"])
        self.assertIn("이름이 올바르지 않아요", reply["result"]["content"][0]["text"])
        self.assertFalse(any("enable" in call for call in self.system.calls))

    def test_tool_call_without_daemon_reports_connection_error(self):
        process, request = self.mcp_session()
        reply = request("tools/call", {"name": "dashboard", "arguments": {}})
        self.assertTrue(reply["result"]["isError"])
        self.assertIn("컨트롤러 서비스에 연결하지 못했어요", reply["result"]["content"][0]["text"])
        process.stdin.close()
        process.wait(10)
        self.assertNotIn("Traceback", process.stderr.read())


class InstallerSmokeTests(SmokeBase):
    def test_user_installer_writes_files_into_temporary_home(self):
        spec = importlib.util.spec_from_file_location("install_user", PROJECT / "packaging/install-user.py")
        installer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(installer)
        home = Path(os.environ["HOME"])
        executable = self.root / "bin/frieren-controller"
        executable.parent.mkdir()
        executable.write_text("#!/bin/sh\n")
        commands = []
        with (
            patch.object(installer, "EXEC", executable),
            patch.object(
                installer, "subprocess", SimpleNamespace(run=lambda args, **_: commands.append(args))
            ),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            installer.install()
        unit = (home / ".config/systemd/user/frieren-os-controller.service").read_text()
        self.assertIn(f"ExecStart={executable} daemon", unit)
        self.assertNotIn("@EXEC@", unit)
        self.assertNotIn("@PROJECT@", unit)
        desktop = (
            home / ".local/share/applications/io.github.BumBoo.FrierenOSController.desktop"
        ).read_text()
        self.assertIn(f"Exec={executable} gui", desktop)
        self.assertTrue((home / ".local/share/icons/hicolor/scalable/apps").is_dir())
        self.assertTrue(
            (
                home / ".local/share/plasma/plasmoids/io.github.BumBoo.FrierenController/metadata.json"
            ).is_file()
        )
        self.assertEqual(
            commands,
            [
                ["/usr/bin/systemctl", "--user", "daemon-reload"],
                ["/usr/bin/systemctl", "--user", "enable", "--now", "frieren-os-controller.service"],
            ],
        )


def gtk3_available() -> bool:
    try:
        import gi

        gi.require_version("Gtk", "3.0")
    except (ImportError, ValueError):
        return False
    return True


GUI_PROBE = """
from gi.repository import Gio, GLib
from frieren_controller import gui

app = gui.ControllerApp()
app.set_flags(Gio.ApplicationFlags.NON_UNIQUE)
seen = {}

def check():
    window = app.get_active_window()
    seen["title"] = window.get_title() if window else None
    app.quit()
    return False

GLib.timeout_add(2000, check)
app.run(None)
print("TITLE=" + str(seen.get("title")))
"""


class GuiSmokeTests(SmokeBase):
    @unittest.skipUnless(gtk3_available(), "PyGObject with GTK 3 typelib is not importable")
    @unittest.skipUnless(os.environ.get("DISPLAY"), "no X display; run the suite under xvfb-run -a")
    def test_main_window_opens_without_daemon(self):
        result = subprocess.run(
            [sys.executable, "-c", GUI_PROBE],
            capture_output=True,
            text=True,
            timeout=60,
            env=self.env,
            cwd=PROJECT,
        )
        self.assertEqual(result.returncode, 0, result.stderr[-2000:])
        self.assertIn("TITLE=프리렌 OS 컨트롤러", result.stdout)
        self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
