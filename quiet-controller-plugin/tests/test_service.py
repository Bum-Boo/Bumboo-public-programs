import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from freiren_quiet.service import Controller
from freiren_quiet.profiles import PRESETS


class FakeHardware:
    def __init__(self):
        self.values = {
            "identity": {"model": "GL62 6QE"},
            "limits": {"no_turbo": 1, "min_perf_pct": 25, "max_perf_pct": 100},
            "epp": {"policy0": "balance_performance"},
            "power_limits": {"power_w": 45, "boost_w": 56.25},
        }

    def validate(self):
        return self.identity()

    def identity(self):
        return self.values["identity"]

    def snapshot(self):
        return copy.deepcopy(self.values)

    def power_snapshot(self):
        return copy.deepcopy(self.values["power_limits"])

    def set_power_limits(self, limits):
        self.values["power_limits"] = {key: limits[key] for key in ("power_w", "boost_w")}

    def set_preference(self, value):
        self.values["epp"]["policy0"] = value

    def temperatures(self):
        return {"cpu_c": 66, "sensors": {}}

    def apply(self, cap, no_turbo):
        self.values["limits"].update(max_perf_pct=cap, no_turbo=no_turbo)

    def restore(self, snapshot):
        self.values = copy.deepcopy(snapshot)

    def _restore_limits(self, limits):
        self.values["limits"] = copy.deepcopy(limits)

    def gpu_state(self):
        return "suspended"


class FakePower:
    def __init__(self):
        self.profile = "balanced"
        self.failed = False

    def current(self):
        if self.failed:
            raise RuntimeError("D-Bus unavailable")
        return self.profile

    def set(self, profile):
        if self.failed:
            raise RuntimeError("D-Bus unavailable")
        self.profile = profile
        return profile


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.state = Path(self.directory.name)
        self.hardware = FakeHardware()
        self.power = FakePower()
        self.baseline = self.hardware.snapshot()
        (self.state / "baseline.json").write_text(json.dumps(self.baseline))
        self.controller = Controller(self.hardware, self.power, self.state)

    def test_custom_persists_across_restart_and_reset_restores_original(self):
        original_file = (self.state / "baseline.json").read_bytes()
        settings = {**PRESETS["balanced"], "cap": 68, "power_w": 23.5, "boost_w": 32}
        status = self.controller.request({"op": "configure", "settings": settings})
        self.assertEqual(status["limits"]["max_perf_pct"], 68)
        self.assertEqual(status["power_limits"], {"power_w": 23.5, "boost_w": 32})
        second = Controller(self.hardware, self.power, self.state)
        self.assertEqual(second.status()["custom"], settings)
        second.request({"op": "target", "target": 70})
        status = second.request({"op": "reset"})
        self.assertEqual(self.hardware.snapshot(), self.baseline)
        self.assertEqual(
            (status["mode"], status["target_c"], status["advanced"]), ("restore", 64, False)
        )
        self.assertEqual(status["custom"], PRESETS["balanced"])
        self.assertEqual((self.state / "baseline.json").read_bytes(), original_file)
        third = Controller(self.hardware, self.power, self.state)
        self.assertEqual(third.status()["mode"], "restore")
        self.assertEqual(self.hardware.snapshot(), self.baseline)

    def test_presets_apply_power_and_custom_can_release_only_power_limits(self):
        for mode, values in PRESETS.items():
            status = self.controller.request({"op": "mode", "mode": mode})
            self.assertEqual(status["power_limits"]["power_w"], values["power_w"])
            self.assertEqual(status["epp"]["policy0"], values["preference"])
        settings = {**PRESETS["balanced"], "cap": 60, "power_w": None, "boost_w": None}
        self.controller.request({"op": "configure", "settings": settings})
        self.assertEqual(self.hardware.power_snapshot(), self.baseline["power_limits"])
        self.assertEqual(self.hardware.values["limits"]["max_perf_pct"], 60)

    def test_failed_configuration_rolls_back_hardware_policy_and_saved_settings(self):
        self.controller.change_mode("balanced")
        before = self.hardware.snapshot()
        saved = (self.state / "settings.json").read_bytes()
        with patch.object(self.hardware, "set_power_limits", side_effect=OSError("write refused")):
            with self.assertRaises(RuntimeError):
                self.controller.request({"op": "configure", "settings": PRESETS["performance"]})
        self.assertEqual(self.hardware.snapshot(), before)
        self.assertEqual(self.controller.policy.mode, "balanced")
        self.assertEqual(self.power.profile, "balanced")
        self.assertEqual((self.state / "settings.json").read_bytes(), saved)

    def test_legacy_start_does_not_change_power_limits_or_baseline(self):
        self.assertFalse(self.controller.advanced)
        self.assertEqual(self.hardware.power_snapshot(), self.baseline["power_limits"])
        original = (self.state / "power-baseline.json").read_bytes()
        self.controller.change_mode("quiet")
        Controller(self.hardware, self.power, self.state)
        self.assertEqual((self.state / "power-baseline.json").read_bytes(), original)

    def test_invalid_custom_values_never_mutate_hardware(self):
        before = self.hardware.snapshot()
        invalid = (
            {"cap": True},
            {"cap": 101},
            {"turbo": 1},
            {"preference": "../../etc"},
            {"power_w": float("nan")},
            {"power_w": float("inf")},
            {"power_w": True},
            {"power_w": 20.1},
            {"power_w": 46},
            {"boost_w": 20},
            {"boost_w": None},
            {"path": "/sys/invalid"},
        )
        for change in invalid:
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.controller.request(
                    {"op": "configure", "settings": {**PRESETS["balanced"], **change}}
                )
            self.assertEqual(self.hardware.snapshot(), before)
        self.controller.power_baseline = {"power_w": 25, "boost_w": 30}
        with self.assertRaises(ValueError):
            self.controller.request({"op": "configure", "settings": PRESETS["performance"]})

    def test_missing_rapl_still_supports_cpu_custom_and_reset(self):
        self.hardware.values["power_limits"] = None
        (self.state / "power-baseline.json").unlink()
        controller = Controller(self.hardware, self.power, self.state)
        self.assertFalse(controller.status()["capabilities"]["power_limits"])
        with self.assertRaises(ValueError):
            controller.request({"op": "configure", "settings": PRESETS["balanced"]})
        controller.request(
            {"op": "configure", "settings": {**PRESETS["quiet"], "power_w": None, "boost_w": None}}
        )
        self.assertEqual(controller.status()["limits"]["max_perf_pct"], 60)
        controller.request({"op": "reset"})

    def test_power_failure_cannot_raise_emergency_limit(self):
        self.hardware.temperatures = lambda: {"cpu_c": 86, "sensors": {}}
        self.power.failed = True
        self.controller.tick()
        self.assertEqual(self.hardware.values["limits"]["max_perf_pct"], 25)

    def test_manual_mode_survives_service_recreation(self):
        self.controller.request({"op": "mode", "mode": "quiet"})
        second = Controller(self.hardware, self.power, self.state)
        self.assertEqual(second.policy.mode, "quiet")
        self.assertEqual(second.baseline, self.baseline)

    def test_restore_exact_original_state(self):
        self.controller.request({"op": "mode", "mode": "performance"})
        self.controller.request({"op": "mode", "mode": "restore"})
        self.assertEqual(self.hardware.snapshot(), self.baseline)
        self.assertEqual(self.power.profile, "balanced")

    def test_external_kde_selection_is_respected(self):
        self.power.profile = "performance"
        self.controller.tick()
        self.assertEqual(self.controller.policy.mode, "restore")
        self.assertEqual(self.power.profile, "performance")
        self.assertEqual(self.hardware.snapshot()["limits"], self.baseline["limits"])

    def test_invalid_requests_cannot_inject_paths_or_commands(self):
        for request in (
            [],
            {"op": "run", "command": "id"},
            {"op": "mode", "mode": "../../etc"},
            {"op": "target", "target": True},
            {"op": "status", "path": "/etc/shadow"},
            {"op": []},
        ):
            with self.subTest(request=request), self.assertRaises(ValueError):
                self.controller.request(request)

    def test_ppd_failure_applies_conservative_cpu_limit(self):
        self.power.failed = True
        self.controller.tick()
        self.assertEqual(self.hardware.values["limits"]["max_perf_pct"], 40)
        self.assertIsNotNone(self.controller.error)
        self.power.failed = False
        self.controller.tick()
        self.assertIsNone(self.controller.error)

    def test_stop_restores_cpu_even_when_ppd_fails(self):
        self.power.failed = True
        with self.assertRaises(RuntimeError):
            self.controller.restore()
        self.assertEqual(self.hardware.snapshot(), self.baseline)

    def test_restore_request_succeeds_with_warning_when_ppd_unavailable(self):
        self.power.failed = True
        status = self.controller.request({"op": "mode", "mode": "restore"})
        self.assertEqual(status["mode"], "restore")
        self.assertEqual(self.hardware.snapshot(), self.baseline)
        self.assertIsNotNone(status["error"])

    def test_temperature_status_remains_available_when_ppd_is_down(self):
        self.power.failed = True
        status = self.controller.status()
        self.assertEqual(status["cpu_c"], 66)
        self.assertIsNone(status["power_profile"])

    def test_sensor_failure_overrides_performance(self):
        self.controller.change_mode("performance")
        self.hardware.temperatures = lambda: {"cpu_c": None, "sensors": {}}
        self.controller.tick()
        self.assertEqual(self.hardware.values["limits"]["max_perf_pct"], 40)
        self.assertEqual(self.hardware.values["limits"]["no_turbo"], 1)


if __name__ == "__main__":
    unittest.main()
