"""Desktop transactions must recover partial writes and preserve later user changes."""

import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from frieren_controller.audio_controls import AudioControls
from frieren_controller.core import Controller, ControllerError
from frieren_controller.desktop_extensions import DesktopExtensions
from frieren_controller.network_controls import NetworkControls, nm_fields
from frieren_controller.server import dispatch
from frieren_controller.session_controls import SessionControls
from frieren_controller.x11_controls import WindowControls, sequence_keys, sequence_text


class Backend:
    def __init__(self, fail=False):
        self.value = {"value": 0}
        self.fail = fail
        self.restore_count = 0

    def validate(self, settings):
        if not isinstance(settings, dict) or set(settings) != {"value"}:
            raise ControllerError("invalid")
        return dict(settings)

    def capture(self, _settings):
        return copy.deepcopy(self.value)

    def apply(self, settings):
        self.value = dict(settings)
        if self.fail:
            raise ControllerError("partial write")

    def restore(self, snapshot):
        self.value = dict(snapshot)
        self.restore_count += 1


class Transactions(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.controller = SimpleNamespace(state_dir=Path(self.temp.name))
        self.audio, self.style = Backend(), Backend()
        self.manager = DesktopExtensions(self.controller, {"audio": self.audio, "style": self.style})

    def test_partial_write_rolls_back_every_started_component(self):
        self.style.fail = True
        with self.assertRaises(ControllerError):
            self.manager._transaction({"audio": {"value": 1}, "style": {"value": 2}}, "gui", "test")
        self.assertEqual(self.audio.value, {"value": 0})
        self.assertEqual(self.style.value, {"value": 0})
        self.assertIsNone(self.manager.state["pending"])
        self.assertEqual(self.manager.history()[0]["status"], "failed")

    def test_conflict_does_not_overwrite_external_change(self):
        result = self.manager.configure("audio", {"value": 1}, "cli")
        self.audio.value = {"value": 3}
        with self.assertRaises(ControllerError):
            self.manager.revert(result["change"])
        self.assertEqual(self.audio.value, {"value": 3})
        self.assertEqual(self.audio.restore_count, 0)

    def test_revert_and_actor_are_persisted(self):
        result = self.manager.configure("audio", {"value": 1}, "mcp")
        self.manager.revert(result["change"], "gui")
        self.assertEqual(self.audio.value, {"value": 0})
        self.assertEqual(self.manager.history()[1]["actor"], "mcp")
        reloaded = DesktopExtensions(self.controller, {"audio": self.audio})
        self.assertEqual(reloaded.history()[1]["status"], "reverted")
        self.assertFalse(reloaded.history()[0]["reversible"])
        with self.assertRaises(ControllerError):
            reloaded.revert(reloaded.history()[0]["id"])
        self.assertEqual(self.manager.path.stat().st_mode & 0o777, 0o600)

    def test_restart_recovers_durable_pending_write(self):
        result = self.manager.configure("audio", {"value": 1})
        entry = copy.deepcopy(self.manager.state["history"][0])
        self.assertEqual(entry["id"], result["change"])
        self.manager.state["history"] = []
        self.manager.state["pending"] = entry
        self.manager._save()
        resumed = DesktopExtensions(self.controller, {"audio": self.audio})
        self.assertEqual(resumed.recover(), {"recovered": True})
        self.assertEqual(self.audio.value, {"value": 0})
        self.assertEqual(resumed.history()[0]["status"], "recovered")

    def test_commit_failure_restores_bookkeeping_and_os(self):
        real_save = self.manager._save

        def save():
            if self.manager.state["active_mode"] and self.manager.state["pending"] is None:
                raise OSError("disk full")
            real_save()

        with patch.object(self.manager, "_save", side_effect=save), self.assertRaises(ControllerError):
            self.manager._transaction({"audio": {"value": 2}}, "gui", "test", active="test")
        self.assertEqual(self.audio.value, {"value": 0})
        self.assertIsNone(self.manager.state["active_mode"])
        self.assertEqual(len(self.manager.history()), 1)

    def test_restore_failure_stays_pending_for_retry(self):
        self.style.fail = True
        with patch.object(self.style, "restore", side_effect=ControllerError("offline")):
            with self.assertRaises(ControllerError):
                self.manager._transaction({"style": {"value": 1}}, "gui", "test")
        self.assertIsNotNone(self.manager.state["pending"])
        self.assertEqual(self.manager.recover(), {"recovered": True})
        self.assertEqual(self.style.value, {"value": 0})

    def test_unrelated_preferences_survive_revert(self):
        entry = {"preferences_before": {}, "components": [{"area": "audio", "settings": {"value": 1}}]}
        self.manager.state["preferences"] = {"session": {"notifications_muted": True}}
        self.manager._restore_preferences(entry)
        self.assertTrue(self.manager.state["preferences"]["session"]["notifications_muted"])

    def test_active_mode_survives_history_trimming(self):
        self.manager._transaction({"audio": {"value": 1}}, "gui", "test", active="test")
        identifier = self.manager.state["active_mode"]["entry"]["id"]
        for i in range(301):
            self.manager._record({"id": str(i)})
        self.assertTrue(any(row["id"] == identifier for row in self.manager.state["history"]))

    def test_malformed_state_is_not_silently_replaced(self):
        self.manager.path.write_text(json.dumps({"schema": 2}))
        with self.assertRaises(ControllerError):
            DesktopExtensions(self.controller)

    def test_failed_mode_switch_reactivates_previous_mode(self):
        self.manager.save_mode("old", {"audio": {"value": 1}})
        self.manager.save_mode("new", {"style": {"value": 2}})
        self.manager.apply_mode("old")
        self.style.fail = True
        with self.assertRaises(ControllerError):
            self.manager.apply_mode("new")
        self.assertEqual(self.manager.modes()["active"], "old")
        self.assertEqual(self.audio.value, {"value": 1})
        self.manager.end_mode()
        self.assertEqual(self.audio.value, {"value": 0})


class SessionRestore(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.bus = Mock()
        self.bus.call.side_effect = AssertionError("Session restore must not require notification ownership")
        self.controls = SessionControls(SimpleNamespace(), self.bus)
        self.mode = None
        self.controls.config.read = Mock(side_effect=lambda *_: self.mode)
        self.controls.config.write = Mock(side_effect=self.write_mode)
        self.manager = DesktopExtensions(
            SimpleNamespace(state_dir=Path(self.temp.name)), {"session": self.controls}
        )

    def write_mode(self, _file, _group, _key, value):
        self.mode = value

    def test_toggle_preserves_unset_and_manual_modes_on_revert(self):
        for initial in (None, "restoreSavedSession", "emptySession"):
            for enabled in (False, True):
                with self.subTest(initial=initial, enabled=enabled):
                    self.mode = initial
                    result = self.manager.configure("session", {"session_restore": enabled}, "gui")
                    self.assertEqual(self.mode, "restorePreviousLogout" if enabled else "emptySession")
                    self.manager.revert(result["change"])
                    self.assertEqual(self.mode, initial)

    def test_external_mode_change_is_not_overwritten_by_revert(self):
        result = self.manager.configure("session", {"session_restore": False})
        self.mode = "restoreSavedSession"
        with self.assertRaises(ControllerError):
            self.manager.revert(result["change"])
        self.assertEqual(self.mode, "restoreSavedSession")

    def test_bad_boolean_or_unknown_field_does_not_write(self):
        for settings in (
            {"session_restore": "false"},
            {"session_restore": 0},
            {"session_restore": None},
            {"session_restore": False, "file": "/tmp/other"},
        ):
            with self.subTest(settings=settings), self.assertRaises(ControllerError):
                self.manager.configure("session", settings)
        self.controls.config.write.assert_not_called()

    def test_readback_failure_restores_original_mode(self):
        self.mode = "restoreSavedSession"
        captures = iter([{"mode": self.mode}, {"mode": "restorePreviousLogout"}, {"mode": self.mode}])
        with patch.object(self.controls.config, "capture", side_effect=lambda *_: next(captures)):
            with self.assertRaises(ControllerError):
                self.manager.configure("session", {"session_restore": False})
        self.assertEqual(self.mode, "restoreSavedSession")
        self.assertIsNone(self.manager.state["pending"])
        self.assertEqual(self.manager.history()[0]["status"], "failed")

    def test_live_status_distinguishes_saved_mode_and_external_updates(self):
        self.bus.call.side_effect = None
        self.bus.call.return_value = "notifications-owner"
        self.bus.properties.return_value = {"Inhibited": False}
        self.controls.controller._monitor = lambda: SimpleNamespace(state={"hold_until": 0})
        for raw, expected in ((None, True), ("restoreSavedSession", True), ("emptySession", False)):
            self.mode = raw
            state = self.controls.status()
            self.assertEqual(state["session_restore"], expected)
            self.assertEqual(state["session_restore_mode"], raw or "restorePreviousLogout")


class InterfaceValidation(unittest.TestCase):
    def test_remote_launcher_uses_only_the_existing_shortcut(self):
        with tempfile.TemporaryDirectory() as directory:
            shortcut = Path(directory) / "himmel-desktop.desktop"
            shortcut.write_text("[Desktop Entry]\nType=Application\nExec=true\n")
            controls = NetworkControls()
            with (
                patch.object(controls, "_shortcut", return_value=shortcut),
                patch("frieren_controller.network_controls.subprocess.Popen") as launch,
            ):
                self.assertEqual(controls.open_himmel(), {"opened": True})
                self.assertEqual(launch.call_args.args[0], ["/usr/bin/gio", "launch", str(shortcut)])

    def test_network_command_text_is_rejected_before_lookup(self):
        controls = NetworkControls()
        with patch.object(controls, "status") as lookup, self.assertRaises(ControllerError):
            controls.validate({"connection": "$(id)"})
        lookup.assert_not_called()

    def test_output_can_change_without_a_microphone(self):
        controls = AudioControls()
        state = {"output": "speaker", "input": "missing", "outputs": [{"id": "speaker"}], "inputs": []}
        with patch.object(controls, "status", return_value=state):
            self.assertEqual(controls.validate({"output_volume": 20}), {"output_volume": 20})

    def test_reused_audio_stream_id_is_not_restored(self):
        controls = AudioControls()
        snapshot = {"devices": [], "defaults": {}, "streams": [{"id": 1, "serial": "old"}]}
        state = {"outputs": [], "streams": [{"index": 1, "serial": "new"}]}
        with (
            patch.object(controls, "status", return_value=state),
            patch("frieren_controller.audio_controls.run") as command,
        ):
            controls.restore(snapshot)
            command.assert_not_called()

    def test_notification_inhibitor_is_reacquired_when_owner_changes(self):
        class Bus:
            owner = "first"
            inhibits = 0
            cookie = None

            def call(self, _service, _path, _interface, method, _signature=None, args=()):
                if method == "GetNameOwner":
                    return self.owner
                if method == "Inhibit":
                    self.inhibits += 1
                    self.cookie = self.inhibits
                    return self.cookie
                if method == "UnInhibit":
                    self.cookie = None

            def properties(self, *_args):
                return {"Inhibited": self.cookie is not None}

        bus = Bus()
        controls = SessionControls(SimpleNamespace(), bus)
        controls._mute(True)
        bus.owner = "second"
        bus.cookie = None
        self.assertTrue(controls.capture({"notifications_muted": True})["notifications_muted"])
        self.assertEqual(bus.inhibits, 2)
        controls._mute(False)
        self.assertIsNone(bus.cookie)

    def test_source_validation_and_context_reset(self):
        with tempfile.TemporaryDirectory() as directory:
            controller = Controller(Path(directory))
            result = dispatch(controller, {"op": "work_mode_status", "args": {}, "source": "gui"})
            self.assertTrue(result["ok"])
            self.assertEqual(controller.request_context.source, "local")
            self.assertFalse(
                dispatch(controller, {"op": "work_mode_status", "args": {}, "source": "evil"})["ok"]
            )

    def test_arbitrary_command_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            controller = Controller(Path(directory))
            self.assertFalse(dispatch(controller, {"op": "execute", "args": {"command": "id"}})["ok"])

    def test_nm_escaped_names(self):
        self.assertEqual(
            nm_fields(r"uuid:Lab\:WiFi:802-11-wireless:wlp2s0"),
            ["uuid", "Lab:WiFi", "802-11-wireless", "wlp2s0"],
        )

    def test_shortcuts_roundtrip_and_reject_shell_text(self):
        for sequence in ("Ctrl+Alt+F11", "Meta+K", "Shift+Return"):
            self.assertEqual(sequence_text(sequence_keys(sequence)), sequence)
        with self.assertRaises(ControllerError):
            sequence_keys("$(id)")

    def test_closed_window_does_not_match_reused_id(self):
        controls = WindowControls()
        snapshot = {"windows": [{"id": 1, "fingerprint": "old", "rect": {}}]}
        with patch.object(controls, "status", return_value={"windows": [{"id": 1, "fingerprint": "new"}]}):
            self.assertEqual(controls.comparable(snapshot), {"windows": []})
            self.assertEqual(controls.read_snapshot(snapshot), {"windows": []})


if __name__ == "__main__":
    unittest.main()
