import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from freiren_quiet.hardware import Hardware


class HardwareTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.hardware = Hardware(self.root)
        self.put("devices/virtual/dmi/id/sys_vendor", "Micro-Star International Co., Ltd.")
        self.put("devices/virtual/dmi/id/product_name", "GL62 6QE")
        self.put("devices/system/cpu/cpufreq/policy0/scaling_driver", "intel_pstate")
        self.put(
            "devices/system/cpu/cpufreq/policy0/energy_performance_preference",
            "balance_performance",
        )
        for key, value in (("no_turbo", 1), ("min_perf_pct", 25), ("max_perf_pct", 100)):
            self.put(f"devices/system/cpu/intel_pstate/{key}", str(value))

    def put(self, filename, value):
        path = self.root / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value)

    def test_different_machine_is_rejected(self):
        self.put("devices/virtual/dmi/id/product_name", "Other laptop")
        with self.assertRaises(RuntimeError):
            self.hardware.validate()

    def test_apply_restore_round_trip_including_original_turbo_off(self):
        before = self.hardware.snapshot()
        self.hardware.apply(60, 1)
        self.assertEqual(self.hardware.snapshot()["limits"]["max_perf_pct"], 60)
        self.hardware.apply(100, 0)
        self.hardware.restore(before)
        self.assertEqual(self.hardware.snapshot(), before)

    def test_partial_write_failure_rolls_back(self):
        before = self.hardware.snapshot()
        write = self.hardware._write

        def failing_write(name, value):
            if name == "max_perf_pct" and value == 60:
                raise OSError("injected write failure")
            write(name, value)

        with patch.object(self.hardware, "_write", side_effect=failing_write):
            with self.assertRaises(OSError):
                self.hardware.apply(60, 0)
        self.assertEqual(self.hardware.snapshot(), before)

    def test_sensor_absence_is_not_zero_degrees(self):
        self.assertIsNone(self.hardware.temperatures()["cpu_c"])

    def test_uses_hottest_core_and_does_not_confuse_acpi(self):
        self.put("class/hwmon/hwmon8/name", "coretemp")
        self.put("class/hwmon/hwmon8/temp1_input", "67000")
        self.put("class/hwmon/hwmon8/temp1_label", "Package id 0")
        self.put("class/hwmon/hwmon8/temp2_input", "69000")
        self.put("class/hwmon/hwmon4/name", "acpitz")
        self.put("class/hwmon/hwmon4/temp1_input", "85000")
        self.assertEqual(self.hardware.temperatures()["cpu_c"], 69)

    def test_write_limits_are_bounded(self):
        for cap, turbo in ((24, 1), (101, 0), (True, 1), (60, 2)):
            with self.assertRaises(ValueError):
                self.hardware.apply(cap, turbo)


if __name__ == "__main__":
    unittest.main()
