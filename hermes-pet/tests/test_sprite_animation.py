import unittest

from tools.hermes_pet.pet import _html, message_payload
from tools.hermes_pet.sprite import FRAME_HEIGHT, FRAME_WIDTH, SPRITE_COLUMNS, SPRITE_ROWS, sprite_row_for_status
from tools.hermes_pet.state_source import PetMessage


class SpriteAnimationTests(unittest.TestCase):
    def test_geometry_matches_downloaded_spritesheet(self):
        self.assertEqual(FRAME_WIDTH, 192)
        self.assertEqual(FRAME_HEIGHT, 208)
        self.assertEqual(SPRITE_COLUMNS, 8)
        self.assertEqual(SPRITE_ROWS, 9)

    def test_statuses_map_to_stable_sprite_rows(self):
        self.assertEqual(sprite_row_for_status("idle"), 0)
        self.assertEqual(sprite_row_for_status("working"), 7)
        self.assertEqual(sprite_row_for_status("completed"), 8)
        self.assertEqual(sprite_row_for_status("needs_approval"), 6)
        self.assertEqual(sprite_row_for_status("error"), 5)
        self.assertEqual(sprite_row_for_status("unknown"), 0)

    def test_payload_includes_sprite_row_without_summary_call(self):
        msg = PetMessage(1, "s", "telegram", "assistant", "완료: 끝났어", 1.0)
        payload = message_payload(msg)
        self.assertEqual(payload["status"], "completed")
        self.assertEqual(payload["sprite_row"], 8)

    def test_html_has_sprite_animation_controls(self):
        html = _html().decode("utf-8")
        self.assertIn("@keyframes sprite-step", html)
        self.assertIn("steps(8)", html)
        self.assertIn("--sprite-row", html)
        self.assertIn("data.sprite_row", html)


if __name__ == "__main__":
    unittest.main()
