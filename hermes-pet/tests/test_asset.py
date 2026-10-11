import tempfile
import unittest
from pathlib import Path

from tools.hermes_pet.pet import PetAsset, load_pet_asset, _html


class AssetTests(unittest.TestCase):
    def test_loads_pet_asset_metadata(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "pet.json").write_text(
                '{"displayName":"Frieren","spritesheetPath":"spritesheet.webp"}',
                encoding="utf-8",
            )
            (root / "spritesheet.webp").write_bytes(b"webp")
            asset = load_pet_asset(root)
            self.assertEqual(asset.display_name, "Frieren")
            self.assertEqual(asset.spritesheet.name, "spritesheet.webp")

    def test_missing_asset_falls_back_to_emoji(self):
        asset = load_pet_asset(Path("/tmp/no-such-hermes-pet-asset"))
        self.assertIsInstance(asset, PetAsset)
        self.assertIsNone(asset.spritesheet)

    def test_html_contains_sprite_layer(self):
        html = _html().decode("utf-8")
        self.assertIn('id="sprite"', html)
        self.assertIn('/assets/spritesheet.webp', html)


if __name__ == "__main__":
    unittest.main()
