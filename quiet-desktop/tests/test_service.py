import copy
import json
import tempfile
import unittest
from pathlib import Path

from freiren_quiet.service import Controller


class FakeHardware:
    def __init__(self):
        self.values = {
            "identity": {"model": "GL62 6QE"},
            "limits": {"no_turbo": 1, "min_perf_pct": 25, "max_perf_pct": 100},
            "epp": {"policy0": "balance_performance"},
        }

    def validate(self):
        return self.identity()

    def identity(self):
        return self.values["identity"]

    def snapshot(self):
        return copy.deepcopy(self.values)

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
