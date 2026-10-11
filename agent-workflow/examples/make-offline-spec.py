import json
from pathlib import Path
import sys
root = Path(__file__).resolve().parents[1]
spec = {"goal": "Verify synthetic arithmetic", "checks": [{"id": "arithmetic", "claim": "2 + 2 equals 4", "command": [sys.executable, "-c", "assert 2 + 2 == 4"], "cwd": str(root), "sources": [str(root / "README.md")], "timeout_seconds": 10}]}
print(json.dumps(spec, indent=2))
