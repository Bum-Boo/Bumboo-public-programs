"""DDC support uses detected identity, fixed registers and verified readback."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from frieren_controller.core import ControllerError
from frieren_controller.external_monitor import ExternalControls, parse_detect, parse_vcp

DETECT = """Display 1
   I2C bus: /dev/i2c-7
   DRM connector: card1-HDMI-A-1
   Monitor: DEL:Test Panel:123
Invalid display
   I2C bus: /dev/i2c-15
   DRM connector: card2-eDP-1
   Monitor: LGD::
"""


class ExternalTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.calls = []
        self.values = {"10": 80, "12": 50, "60": 17}
        self.detect = DETECT
        self.ignore_write = False
        self.external = ExternalControls(Path(self.directory.name), self.run_command)
        self.identifier = parse_detect(DETECT)[0]["id"]
        patcher = patch("frieren_controller.external_monitor.shutil.which", return_value="/usr/bin/ddcutil")
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_command(self, args, **kwargs):
        self.calls.append(args)
        if "detect" in args:
            return self.detect
        if "capabilities" in args:
            return "(prot(monitor)vcp(10 12 60(0f 11 12)))"
        if "getvcp" in args:
            code = args[args.index("getvcp") + 1]
            if code == "60":
                return f"VCP 60 SNC x{self.values[code]:02x}"
            return f"VCP {code} C {self.values[code]} 100"
        if "setvcp" in args:
            index = args.index("setvcp")
            if self.ignore_write:
                self.ignore_write = False
            else:
                self.values[args[index + 1]] = int(args[index + 2])
            return ""
        raise AssertionError(args)

    def test_detect_skips_invalid_internal_and_parses_fixed_values(self):
        self.assertEqual(len(parse_detect(DETECT)), 1)
        self.assertEqual(parse_vcp("VCP 10 C 90 120", "10")["value"], 75)
        self.assertEqual(parse_vcp("VCP 60 SNC x11", "60")["value"], 17)
        with self.assertRaises(ControllerError):
            parse_vcp("VCP 10 ERR", "10")

    def test_supported_fields_set_verify_and_original_restore(self):
        self.assertEqual(len(self.external.status()["displays"]), 1)
        self.external.set(self.identifier, "brightness", 60)
        self.external.set(self.identifier, "brightness", 40)
        self.external.set(self.identifier, "contrast", 70)
        self.external.set(self.identifier, "input", 15)
        self.external.reset(self.identifier)
        self.assertEqual(self.values, {"10": 80, "12": 50, "60": 17})
        writes = [call for call in self.calls if "setvcp" in call]
        self.assertTrue(all(call[0] == "/usr/bin/ddcutil" and "--verify" in call for call in writes))

    def test_hotplug_cannot_write_to_replacement_on_same_bus(self):
        self.detect = DETECT.replace("Test Panel:123", "Other:999")
        with self.assertRaises(ControllerError):
            self.external.set(self.identifier, "brightness", 70)
        self.assertFalse(any("setvcp" in call for call in self.calls))

    def test_fixed_features_and_supported_input_only(self):
        for feature, value in (("ff", 30), ("brightness", 0), ("input", 99), ("contrast", True)):
            with self.subTest(feature=feature), self.assertRaises(ControllerError):
                self.external.set(self.identifier, feature, value)
        with self.assertRaises(ControllerError):
            self.external.set("/dev/i2c-7", "brightness", 50)
        self.assertFalse(any("setvcp" in call for call in self.calls))

    def test_mismatched_readback_restores_previous_value(self):
        self.ignore_write = True
        with self.assertRaises(ControllerError):
            self.external.set(self.identifier, "brightness", 70)
        self.assertEqual(self.values["10"], 80)
