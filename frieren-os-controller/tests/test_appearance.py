"""Restore, partial-failure, stale-device and profile-preservation behavior."""

from __future__ import annotations

import copy
import json
import struct
import tempfile
import unittest
import zlib
from pathlib import Path
from unittest.mock import patch

from frieren_controller.appearance import DEFAULT_TERMINAL, Appearance, dump_ini, ini, put
from frieren_controller.core import Controller, ControllerError
from frieren_controller.server import dispatch


def tiny_png():
    def chunk(kind, data):
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(b"\x00\x60\x40\x80"))
        + chunk(b"IEND", b"")
    )


class FakeBackend:
    def __init__(self, home):
        self.home = home
        self.current = {
            "activity": "a",
            "desktops": [
                {"id": 1, "screen": 0, "plugin": "org.kde.image", "image": {"Image": "file:///old.png"}},
                {
                    "id": 2,
                    "screen": 1,
                    "plugin": "org.kde.slideshow",
                    "image": {"Image": "file:///other.png", "FillMode": 6},
                },
            ],
        }
        self.tabs = [
            {
                "service": "org.kde.konsole-10",
                "path": "/Sessions/1",
                "identity": "aaa",
                "profile": "Original",
            },
            {"service": "org.kde.konsole-10", "path": "/Sessions/2", "identity": "bbb", "profile": "Other"},
        ]
        self.writes = []
        self.ignore_once = False
        self.fail_default = False
        self.default_writes = 0

    def command(self, args):
        path = self.home / ".config/konsolerc"
        parser = ini(path.read_text())
        if args[-1] == "--delete":
            parser.remove_option("Desktop Entry", "DefaultProfile")
        else:
            put(parser, "Desktop Entry", "DefaultProfile", args[-1])
        path.write_text(dump_ini(parser))
        self.default_writes += 1
        if self.fail_default:
            self.fail_default = False
            raise ControllerError("partial config write")
        return ""

    def desktops(self):
        return copy.deepcopy(self.current)

    def write(self, activity, rows):
        if activity != self.current["activity"]:
            raise ControllerError("wrong activity")
        self.writes.append(copy.deepcopy(rows))
        if self.ignore_once:
            self.ignore_once = False
            return
        for row in rows:
            target = next((r for r in self.current["desktops"] if r["id"] == row["id"]), None)
            if target is None or target["screen"] != row["screen"]:
                raise ControllerError("detached screen")
            target.update(copy.deepcopy(row))

    def sessions(self):
        return copy.deepcopy(self.tabs)


class AppearanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        (self.home / ".config").mkdir()
        (self.home / ".config/konsolerc").write_text(
            "[Desktop Entry]\nDefaultProfile=Original.profile\n[General]\nKeep=42\n"
        )
        directory = self.home / ".local/share/konsole"
        directory.mkdir(parents=True)
        self.profile = directory / "Original.profile"
        self.profile.write_text(
            "[General]\nName=Original\nParent=FALLBACK/\n"
            "[Appearance]\nColorScheme=Original\nFont=keep this font\n"
        )
        self.scheme = directory / "Original.colorscheme"
        self.scheme.write_text(
            "[General]\nOpacity=0.9\n[Color1]\nColor=12,34,56\n[Background]\nColor=30,30,46\n[Foreground]\nColor=205,214,244\n"
        )
        self.original_bytes = (self.profile.read_bytes(), self.scheme.read_bytes())
        self.backend = FakeBackend(self.home)
        self.state_dir = self.home / "state"
        self.controller = Appearance(self.state_dir, self.backend, self.home)
        self.image = self.home / 'photo "quoted" 한글.png'
        self.image.write_bytes(tiny_png())

    def test_first_original_survives_repeated_apply_restart_and_reset(self):
        before = self.backend.desktops()
        self.controller.wallpaper_set(str(self.image), 1, "fit")
        first = self.controller.path.read_bytes()
        self.controller.wallpaper_set(str(self.image), 1, "center")
        restart = Appearance(self.state_dir, self.backend, self.home)
        restart.wallpaper_reset(1)
        self.assertEqual(before, self.backend.desktops())
        self.assertEqual(json.loads(first)["wallpapers"], restart.state["wallpapers"])
        self.assertNotIn("FillMode", self.backend.current["desktops"][0]["image"])

    def test_all_screens_preserve_plugins_and_individual_placement(self):
        before = self.backend.desktops()
        self.controller.wallpaper_set(str(self.image))
        self.assertTrue(all(r["plugin"] == "org.kde.image" for r in self.backend.current["desktops"]))
        self.controller.wallpaper_reset()
        self.assertEqual(before, self.backend.desktops())

    def test_failed_readback_restores_immediately_previous_wallpaper(self):
        self.controller.wallpaper_set(str(self.image), 1, "fit")
        before = self.backend.desktops()
        self.backend.ignore_once = True
        with self.assertRaises(ControllerError):
            self.controller.wallpaper_set(str(self.image), 1, "tile")
        self.assertEqual(before, self.backend.desktops())
        self.controller.wallpaper_reset(1)
        self.assertEqual(self.backend.current["desktops"][0]["image"], {"Image": "file:///old.png"})

    def test_unknown_or_detached_screen_does_not_change_other_screens(self):
        with self.assertRaises(ControllerError):
            self.controller.wallpaper_set(str(self.image), 999)
        self.assertFalse(self.backend.writes)
        self.controller.wallpaper_set(str(self.image), 1)
        self.backend.current["desktops"].pop(0)
        with self.assertRaises(ControllerError):
            self.controller.wallpaper_reset(1)
        self.assertEqual(self.backend.current["desktops"][0]["plugin"], "org.kde.slideshow")

    def test_rejects_non_image_files_and_invalid_settings_before_system_write(self):
        fake = self.home / "fake.png"
        fake.write_text("not an image")
        for path in (str(fake), "/etc/passwd", "https://example.test/a.png", str(self.image) + "\n"):
            with self.assertRaises(ControllerError):
                self.controller.wallpaper_set(path)
        for fields in (
            {"opacity": 101},
            {"opacity": True},
            {"foreground": "#fff;bad"},
            {"apply_running": "true"},
            {"command": "bad"},
        ):
            with self.assertRaises(ControllerError):
                self.controller.terminal_configure(DEFAULT_TERMINAL | fields)
        self.assertFalse(self.backend.writes)
        self.assertEqual(self.backend.default_writes, 0)
        self.assertIsNone(self.controller.state["terminal"])

    def test_terminal_clones_preserves_ansi_font_original_and_unrelated_tabs(self):
        result = self.controller.terminal_configure(DEFAULT_TERMINAL | {"image": str(self.image)})
        self.assertEqual(self.backend.tabs[0]["profile"], "Original")
        self.assertEqual(self.backend.tabs[1]["profile"], "Other")
        profile = ini(self.controller.resource(self.controller.read_default(), ".profile").read_text())
        scheme = ini(
            self.controller.resource(profile["Appearance"]["ColorScheme"], ".colorscheme").read_text()
        )
        self.assertEqual(profile["Appearance"]["Font"], "keep this font")
        self.assertEqual(scheme["Color1"]["Color"], "12,34,56")
        self.image.unlink()
        self.assertTrue(Path(result["terminal"]["settings"]["image"]).is_file())
        Appearance(self.state_dir, self.backend, self.home).terminal_reset()
        self.assertEqual(self.controller.read_default(), "Original.profile")
        self.assertEqual(self.backend.tabs[0]["profile"], "Original")
        self.assertEqual(self.original_bytes, (self.profile.read_bytes(), self.scheme.read_bytes()))
        self.assertEqual(ini(self.controller.konsolerc.read_text())["General"]["Keep"], "42")

    def test_partial_terminal_write_rolls_back_default_and_generated_files(self):
        self.backend.fail_default = True
        with self.assertRaises(ControllerError):
            self.controller.terminal_configure(DEFAULT_TERMINAL)
        self.assertEqual(self.controller.read_default(), "Original.profile")
        self.assertEqual(self.backend.tabs[0]["profile"], "Original")
        self.assertIsNone(self.controller.state["settings"])
        self.assertTrue(self.controller.status()["terminal"]["has_baseline"])

    def test_failed_second_terminal_apply_restores_previous_custom_files(self):
        self.controller.terminal_configure(DEFAULT_TERMINAL)
        paths = list(self.controller.konsole_dir.glob("FrierenController.*"))
        before = {path: path.read_bytes() for path in paths}
        self.backend.fail_default = True
        with self.assertRaises(ControllerError):
            self.controller.terminal_configure(DEFAULT_TERMINAL | {"opacity": 70})
        self.assertEqual(before, {path: path.read_bytes() for path in paths})
        self.assertEqual(self.controller.state["settings"]["opacity"], 90)

    def test_new_window_uses_fixed_executable_and_selected_profile(self):
        self.controller.terminal_configure(DEFAULT_TERMINAL)
        with patch("frieren_controller.appearance.subprocess.Popen") as launch:
            self.controller.terminal_open()
        args = launch.call_args.args[0]
        self.assertEqual(args[:3], ["/usr/bin/konsole", "--separate", "--profile"])
        self.assertEqual(Path(args[3]), self.controller.resource(self.controller.read_default(), ".profile"))
        self.controller.terminal_reset()
        self.assertEqual(self.backend.tabs[0]["profile"], "Original")

    def test_missing_default_key_is_removed_on_reset(self):
        self.controller.konsolerc.write_text("[General]\nKeep=42\n")
        self.controller.terminal_configure(DEFAULT_TERMINAL)
        self.controller.terminal_reset()
        self.assertIsNone(self.controller.read_default())
        self.assertEqual(ini(self.controller.konsolerc.read_text())["General"]["Keep"], "42")

    def test_api_is_shared_and_does_not_accept_commands(self):
        facade = Controller(self.state_dir)
        facade.appearance = self.controller
        result = dispatch(
            facade, {"op": "wallpaper_set", "args": {"image": str(self.image), "desktop_id": 1}}
        )
        self.assertTrue(result["ok"])
        self.assertFalse(dispatch(facade, {"op": "wallpaper_set", "args": {"command": "bad"}})["ok"])
        self.assertTrue(dispatch(facade, {"op": "wallpaper_reset", "args": {"desktop_id": 1}})["ok"])
        self.assertEqual(facade.audit_log()[-1]["action"], "wallpaper_reset")
