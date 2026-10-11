import json
from datetime import datetime, timezone

import pytest

from grimoire.audio import FrameDecoder
from grimoire.config import Settings, normalize
from grimoire.models import aggregate, openable_path
from grimoire.sources import collect, from_agent_task, from_event, write_event

NOW = 1800000000


def iso(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat()


def task_file(tmp_path, status="active", expiry=NOW + 60):
    path = tmp_path / "project/task/state.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema": 1,
                "status": status,
                "project": "project",
                "task": "task",
                "title": "A task",
                "updated_at": iso(NOW),
                "owner": {"agent": "test", "expires_at": iso(expiry)},
                "checkpoint": {"outputs": ["/tmp/result.md"]},
                "revision": 2,
            }
        )
    )
    return path


def test_active_lease_and_expiry_are_distinct(tmp_path):
    path = task_file(tmp_path)
    assert from_agent_task(path, NOW).state == "working"
    assert from_agent_task(path, NOW + 61).state == "attention"


@pytest.mark.parametrize("status", ["completed", "complete"])
def test_actual_completed_record_does_not_require_live_owner(tmp_path, status):
    path = task_file(tmp_path, status, NOW - 600)
    obj = json.loads(path.read_text())
    obj["owner"] = None
    path.write_text(json.dumps(obj))
    task = from_agent_task(path, NOW)
    assert task.state == "done" and task.artifacts == ("/tmp/result.md",)


def test_damaged_record_does_not_remove_good_records(tmp_path):
    task_file(tmp_path)
    broken = tmp_path / "broken/task/state.json"
    broken.parent.mkdir(parents=True)
    broken.write_text("{")
    tasks, errors = collect(str(tmp_path), tmp_path / "events", NOW)
    assert len(tasks) == 1 and errors == ["unreadable_record"]


def test_generic_event_expiry_and_replacement(tmp_path):
    path = write_event(tmp_path, event_id="one", state="working", title="Collecting", ttl=10)
    obj = json.loads(path.read_text())
    obj["updated_at"] = iso(NOW - 11)
    path.write_text(json.dumps(obj))
    assert from_event(path, NOW).state == "attention"
    write_event(tmp_path, event_id="one", state="done", title="Ready")
    assert len(list(tmp_path.glob("*.json"))) == 1
    assert from_event(path, NOW).state == "done"


def test_event_cannot_escape_directory(tmp_path):
    with pytest.raises(ValueError):
        write_event(tmp_path, event_id="../../escape", state="done", title="x")
    assert not list(tmp_path.iterdir())


def test_partial_binary_frames_and_backlog_use_latest_complete():
    decoder = FrameDecoder(4)
    assert decoder.feed(b"\x00\x01") is None
    assert decoder.feed(b"\x02\x03\x04") == [x / 255 for x in (0, 1, 2, 3)]
    assert decoder.feed(bytes(range(5, 14))) == [x / 255 for x in (8, 9, 10, 11)]
    assert decoder.pending == bytes([12, 13])


def test_settings_bounds_and_unknown_fields_survive(tmp_path):
    settings = Settings(tmp_path / "settings.json")
    settings.update(
        scale=100,
        gain=float("nan"),
        theme="invalid",
        future_option=42,
        audio_source="microphone",
        quiet="yes",
    )
    loaded = Settings(settings.path)
    assert loaded["scale"] == 1 and loaded["gain"] == 1
    assert loaded["theme"] == "night" and loaded["quiet"] is True
    assert loaded["audio_source"] == "auto" and loaded["future_option"] == 42
    assert normalize({"audio_source": "test.monitor"})["audio_source"] == "test.monitor"


def test_corrupt_settings_fall_back_without_overwriting(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("bad")
    assert Settings(path).error
    assert path.read_text() == "bad"


def test_open_artifact_rejects_executable_missing_and_accepts_document(tmp_path):
    good = tmp_path / "result.md"
    good.write_text("result")
    bad = tmp_path / "run.desktop"
    bad.write_text("[Desktop Entry]")
    assert openable_path(str(good)) == good
    assert openable_path(str(bad)) is None
    assert openable_path(str(tmp_path / "missing.md")) is None
    assert openable_path(str(tmp_path)) == tmp_path


def test_working_has_precedence_over_old_attention(tmp_path):
    path = task_file(tmp_path)
    working = from_agent_task(path, NOW)
    stale = from_agent_task(path, NOW + 61)
    assert aggregate([stale, working]) == "working"
    assert aggregate([stale]) == "attention"
    assert aggregate([]) == "idle"
