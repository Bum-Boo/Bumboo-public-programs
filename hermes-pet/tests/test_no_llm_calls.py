import unittest
from pathlib import Path


FORBIDDEN_STRINGS = [
    "/v1/chat/completions",
    "/v1/responses",
    "chat.completions.create",
    "responses.create",
    "openai",
    "anthropic",
    "hermes chat",
    "subprocess.run",
    "subprocess.Popen",
]


class NoLLMCallsTests(unittest.TestCase):
    def test_pet_source_contains_no_model_or_agent_invocation_paths(self):
        root = Path(__file__).resolve().parents[1] / "tools/hermes_pet"
        source_files = [p for p in root.glob("*.py") if p.name != "__init__.py"]
        self.assertTrue(source_files, "expected pet source files to exist")
        combined = "\n".join(p.read_text(encoding="utf-8") for p in source_files)
        lower = combined.lower()
        for forbidden in FORBIDDEN_STRINGS:
            self.assertNotIn(forbidden.lower(), lower)


if __name__ == "__main__":
    unittest.main()
