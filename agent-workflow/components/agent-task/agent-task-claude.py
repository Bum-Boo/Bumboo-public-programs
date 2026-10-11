#!/usr/bin/env python3
"""Fail-open lifecycle bridge; no transcript access."""
try:
    from agent_task import hook_main
    hook_main()
except Exception:
    print("{}")
