import tempfile
import unittest
from pathlib import Path

from scripts.install import Deployment


class DeploymentTests(unittest.TestCase):
    def test_rollback_restores_code_and_settings_without_replacing_baseline(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "installed"
            source.mkdir()
            (source / "service.py").write_text("previous code")
            settings = root / "settings.json"
            settings.write_text('{"mode":"balanced"}')
            new_file = root / "new-file"
            baseline = root / "baseline.json"
            baseline.write_text("original baseline")
            deployment = Deployment(root, [source, settings, new_file])
            (source / "service.py").write_text("broken upgrade")
            (source / "new.py").write_text("new module")
            settings.write_text("changed")
            new_file.write_text("new")
            deployment.restore()
            self.assertEqual((source / "service.py").read_text(), "previous code")
            self.assertFalse((source / "new.py").exists())
            self.assertFalse(new_file.exists())
            self.assertEqual(settings.read_text(), '{"mode":"balanced"}')
            self.assertEqual(baseline.read_text(), "original baseline")
            self.assertEqual(deployment.backup.stat().st_mode & 0o777, 0o700)
