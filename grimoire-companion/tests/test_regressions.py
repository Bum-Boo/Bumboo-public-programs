"""Regression tests for reproduced defects in the read-only source adapters."""

import os
import subprocess
import sys
import textwrap
import time

import pytest

from grimoire.sources import collect, from_event, write_event


def good_event(tmp_path):
    events = tmp_path / "events"
    write_event(events, event_id="good", state="done", title="Still visible")
    return events


def test_deeply_nested_record_is_isolated_not_raised(tmp_path):
    events = good_event(tmp_path)
    (events / "deep.json").write_text("[" * 200_000)  # below the 256KiB limit
    tasks, errors = collect("", events)
    assert [t.id for t in tasks] == ["event:good"]
    assert errors == ["unreadable_record"]


def test_dangling_symlink_does_not_hide_other_records(tmp_path):
    events = good_event(tmp_path)
    (events / "dangling.json").symlink_to(tmp_path / "missing.json")
    tasks, errors = collect("", events)
    assert [t.id for t in tasks] == ["event:good"]
    assert errors == ["unreadable_record"]


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="FIFOs need POSIX")
def test_fifo_named_like_a_record_does_not_block_collection(tmp_path):
    events = good_event(tmp_path)
    os.mkfifo(events / "pipe.json")
    script = textwrap.dedent(
        f"""
        from pathlib import Path
        from grimoire.sources import collect
        tasks, errors = collect("", Path({str(events)!r}))
        print([t.id for t in tasks], errors)
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, timeout=20
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "['event:good'] ['unreadable_record']"


def test_event_handoff_path_is_kept_verbatim(tmp_path):
    handoff = tmp_path / "two  spaces" / "notes.md"
    handoff.parent.mkdir()
    handoff.write_text("synthetic")
    path = write_event(
        tmp_path / "events", event_id="h", state="done", title="t", handoff=str(handoff)
    )
    assert from_event(path, time.time()).handoff == str(handoff)
