"""Installed with root ownership; -I keeps user Python paths out of the service."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from freiren_quiet.cli import main  # noqa: E402

raise SystemExit(main())
