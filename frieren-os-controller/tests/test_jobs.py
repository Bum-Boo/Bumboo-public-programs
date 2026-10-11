"""Job editing must preserve content and reject conflicts before any job runs."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from frieren_controller.core import Controller, ControllerError
from frieren_controller.jobs import JobEditor
from frieren_controller.server import dispatch

SERVICE = "[Unit]\nDescription=Test\n[Service]\nExecStart=/usr/bin/true\n[Install]\nWantedBy=default.target\n"


class Runner:
    def __init__(self, unit_dir):
        self.root = unit_dir
        self.vendor = {}
        self.calls = []
        self.fail_verify = False
        self.fail_reload_once = False
        self.cron = None
        self.cron_fail_once = False
        self.cron_read_error = False
        self.real_verify = False
        self.extra_dropins = {}
        self.fail_remove_absent = False
        self.fail_reinstall = False

    def __call__(self, argv, **_):
        self.calls.append(argv)
        code, out, err = 0, "", ""
        if argv[0] == "/usr/bin/systemctl":
            if "is-active" in argv:
                code, out = 3, "inactive\n"
            elif "daemon-reload" in argv:
                if self.fail_reload_once:
                    self.fail_reload_once = False
                    code, err = 1, "reload failed"
            else:
                unit = argv[-1]
                main = self.root / unit
                exists = main.exists() or unit in self.vendor
                if "show" in argv:
                    vendor = self.root.parent / "vendor" / unit
                    if unit in self.vendor:
                        vendor.parent.mkdir(exist_ok=True)
                        vendor.write_text(self.vendor[unit])
                    dropins = list(self.extra_dropins.get(unit, []))
                    override = self.root / (unit + ".d/90-frieren-controller.conf")
                    if override.exists():
                        dropins.append(override)
                    out = (
                        "LoadState="
                        + ("loaded" if exists else "not-found")
                        + "\nFragmentPath="
                        + (str(main) if main.exists() else (str(vendor) if exists else ""))
                        + "\nDropInPaths="
                        + " ".join(map(str, dropins))
                        + "\nActiveState=inactive\n"
                    )
                elif "cat" in argv:
                    origin = main if main.exists() else Path("/usr/lib/systemd/user") / unit
                    out = (
                        "# " + str(origin) + "\n" + (main.read_text() if main.exists() else self.vendor[unit])
                    )
                    override = self.root / (unit + ".d/90-frieren-controller.conf")
                    if override.exists():
                        out += "\n# " + str(override) + "\n" + override.read_text()
                else:
                    raise AssertionError(argv)
        elif argv[0] == "/usr/bin/systemd-analyze":
            if self.real_verify:
                return subprocess.run(
                    argv,
                    text=True,
                    capture_output=True,
                    check=False,
                    env={**os.environ, "SYSTEMD_UNIT_PATH": str(self.root) + ":/usr/lib/systemd/user"},
                    timeout=15,
                )
            if self.fail_verify:
                code, err = 1, "invalid unit"
        elif argv[0].endswith("crontab"):
            action = argv[1]
            if action == "-l":
                if self.cron_read_error:
                    code, err = 1, "permission denied"
                elif self.cron is None:
                    code, err = 1, "no crontab for test"
                else:
                    out = self.cron
            elif action == "-r":
                self.cron = None
                if self.fail_remove_absent:
                    code, err = 1, "no crontab for test"
            elif action == "-T":
                if "bad schedule" in Path(argv[2]).read_text():
                    code, err = 1, "bad minute"
            else:
                if self.fail_reinstall and Path(action).read_text() == "# preserved\n":
                    return subprocess.CompletedProcess(argv, 1, "", "restore denied")
                self.cron = Path(action).read_text()
                if self.cron_fail_once:
                    self.cron_fail_once = False
                    code, err = 1, "partial write"
        else:
            raise AssertionError(argv)
        return subprocess.CompletedProcess(argv, code, out, err)


class JobTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.units = self.root / "units"
        self.units.mkdir()
        self.runner = Runner(self.units)
        self.c = Controller(self.root / "state", runner=self.runner, quiet=object())
        self.crontab = self.root / "crontab"
        self.crontab.touch()
        self.editor = JobEditor(self.c, self.units, self.crontab)

    def test_create_edit_backup_without_start_or_enable(self):
        first = self.editor.unit_read("demo.service")
        self.assertFalse(first["exists"])
        saved = self.editor.unit_save("demo.service", SERVICE, first["revision"])
        self.assertEqual(saved["content"], SERVICE)
        second = SERVICE.replace("Test", "Updated")
        self.editor.unit_save("demo.service", second, saved["revision"])
        backup = json.loads((self.c.state_dir / "job-demo.service.json").read_text())
        self.assertEqual(backup["before"], SERVICE)
        self.assertEqual((self.units / "demo.service").stat().st_mode & 0o777, 0o600)
        self.assertFalse(any("start" in a or "enable" in a or "restart" in a for a in self.runner.calls))
        self.assertNotIn("ExecStart", (self.c.state_dir / "audit.jsonl").read_text())

    def test_vendor_override_preserves_original_and_replaces_managed_part(self):
        self.runner.vendor["vendor.service"] = SERVICE
        first = self.editor.unit_read("vendor.service")
        self.assertEqual(first["mode"], "override")
        one = "[Service]\nExecStart=\nExecStart=/usr/bin/false\n"
        saved = self.editor.unit_save("vendor.service", one, first["revision"])
        self.assertNotIn(one, saved["base"])
        self.editor.unit_save("vendor.service", "[Service]\nRestart=no\n", saved["revision"])
        self.assertFalse((self.units / "vendor.service").exists())
        self.assertEqual(self.runner.vendor["vendor.service"], SERVICE)

    def test_conflict_and_invalid_content_do_not_write(self):
        first = self.editor.unit_read("demo.service")
        (self.units / "demo.service").write_text(SERVICE)
        with self.assertRaisesRegex(ControllerError, "다른 곳"):
            self.editor.unit_save("demo.service", SERVICE, first["revision"])
        first = self.editor.unit_read("demo.service")
        self.runner.fail_verify = True
        with self.assertRaises(ControllerError):
            self.editor.unit_save("demo.service", SERVICE + "bad", first["revision"])
        self.assertEqual((self.units / "demo.service").read_text(), SERVICE)
        self.assertFalse((self.c.state_dir / "job-demo.service.json").exists())

    @unittest.skipUnless(Path("/usr/bin/systemd-analyze").is_file(), "systemd verifier unavailable")
    def test_installed_override_cannot_hide_invalid_new_command_in_real_verifier(self):
        self.runner.vendor["demo.service"] = SERVICE.replace(
            "[Service]\n", "[Service]\n# /ordinary-comment.conf\n"
        )
        common = self.root / "service.d/10-test.conf"
        common.parent.mkdir()
        common.write_text("[Service]\n# /another-comment.conf\nRestart=no\n")
        self.runner.extra_dropins["demo.service"] = [common]
        self.runner.real_verify = True
        before = self.editor.unit_read("demo.service")
        valid = "[Service]\nExecStart=\nExecStart=/usr/bin/true\n"
        saved = self.editor.unit_save("demo.service", valid, before["revision"])
        with self.assertRaises(ControllerError):
            self.editor.unit_save(
                "demo.service",
                "[Service]\nExecStart=\nExecStart=/missing-frieren-test-command\n",
                saved["revision"],
            )
        self.assertEqual(self.editor.unit_read("demo.service")["content"], valid)

    def test_reload_failure_restores_existing_or_removes_new_file(self):
        for old in (None, SERVICE):
            target = self.units / "demo.service"
            if old is not None:
                target.write_text(old)
            before = self.editor.unit_read("demo.service")
            self.runner.fail_reload_once = True
            with self.assertRaisesRegex(ControllerError, "이전 파일"):
                self.editor.unit_save("demo.service", SERVICE.replace("Test", "New"), before["revision"])
            self.assertEqual(target.read_text() if target.exists() else None, old)

    def test_names_protected_units_symlinks_and_size(self):
        for unit in (
            "../escape.service",
            "-bad.service",
            "frieren-os-controller.service",
            "systemd-test.timer",
            "dbus.service",
            "pipewire-pulse.service",
            "wireplumber.service",
            "plasma-kwin_x11.service",
            "plasma-plasmashell.service",
            "xdg-desktop-portal-kde.service",
        ):
            with self.subTest(unit=unit), self.assertRaises(ControllerError):
                self.editor.unit_read(unit)
        (self.units / "alias.service").symlink_to(self.root / "target")
        with self.assertRaises(ControllerError):
            self.editor.unit_read("alias.service")
        state = self.editor.unit_read("demo.service")
        for content in ("", "\x00", "a" * 24001):
            with self.subTest(content=content[:10]), self.assertRaises(ControllerError):
                self.editor.unit_save("demo.service", content, state["revision"])

    def test_cron_preserves_comments_environment_and_conflict(self):
        original = '# comment\nMAILTO=""\n0 9 * * * /usr/bin/true\n'
        self.runner.cron = original
        before = self.editor.cron_read()
        after = self.editor.cron_save(original + "@reboot /usr/bin/true\n", before["revision"])
        self.assertIn(original, after["content"])
        with self.assertRaisesRegex(ControllerError, "다른 곳"):
            self.editor.cron_save(original, before["revision"])
        self.assertEqual(json.loads((self.c.state_dir / "job-crontab.json").read_text())["before"], original)

    def test_bad_cron_and_unreadable_cron_do_not_overwrite(self):
        self.runner.cron = "0 9 * * * /usr/bin/true\n"
        first = self.editor.cron_read()
        with self.assertRaises(ControllerError):
            self.editor.cron_save("bad schedule", first["revision"])
        self.assertEqual(self.runner.cron, first["content"])
        self.runner.cron_read_error = True
        with self.assertRaises(ControllerError):
            self.editor.cron_read()

    def test_cron_partial_install_failure_rolls_back_absence_and_content(self):
        for old in (None, "# preserved\n"):
            self.runner.cron = old
            before = self.editor.cron_read()
            self.runner.cron_fail_once = True
            with self.assertRaisesRegex(ControllerError, "이전 crontab"):
                self.editor.cron_save("0 9 * * * /usr/bin/true\n", before["revision"])
            self.assertEqual(self.runner.cron, old)

    def test_cron_rollback_reports_absence_and_failed_restore_correctly(self):
        before = self.editor.cron_read()
        self.runner.cron_fail_once = True
        self.runner.fail_remove_absent = True
        with self.assertRaisesRegex(ControllerError, "partial write"):
            self.editor.cron_save("0 9 * * * /usr/bin/true\n", before["revision"])
        self.runner.cron = "# preserved\n"
        before = self.editor.cron_read()
        self.runner.cron_fail_once = True
        self.runner.fail_reinstall = True
        with self.assertRaisesRegex(ControllerError, "복구.*job-crontab.json"):
            self.editor.cron_save("0 9 * * * /usr/bin/true\n", before["revision"])

    def test_new_timer_requires_existing_service(self):
        timer = "[Timer]\nOnCalendar=daily\nUnit=demo.service\n"
        before = self.editor.unit_read("demo.timer")
        with self.assertRaisesRegex(ControllerError, "먼저"):
            self.editor.unit_save("demo.timer", timer, before["revision"])
        self.assertFalse((self.units / "demo.timer").exists())
        (self.units / "demo.service").write_text(SERVICE)
        self.assertTrue(self.editor.unit_save("demo.timer", timer, before["revision"])["exists"])

    def test_missing_cronie_is_explicit_and_api_has_no_root_or_path_argument(self):
        self.crontab.unlink()
        self.assertFalse(self.editor.cron_read()["available"])
        with self.assertRaises(ControllerError):
            self.editor.cron_save("", "x")
        for op, args in (
            ("job_unit_read", {"unit": "demo.service", "scope": "system"}),
            ("job_unit_save", {"unit": "demo.service", "path": "/tmp/evil"}),
            ("job_cron_read", {"user": "root"}),
        ):
            self.assertFalse(dispatch(self.c, {"op": op, "args": args})["ok"])


if __name__ == "__main__":
    unittest.main()
