"""End-to-end smoke tests for the documented entry points, using synthetic data only.

Every subprocess runs with temporary HOME and XDG directories, so nothing touches the
real user profile. The GUI checks use Qt's offscreen platform and skip cleanly when the
Qt GUI libraries cannot be loaded (for example, libEGL is missing on a bare server).

Not covered here (needs a real desktop session): tray icon, desktop companion window
placement/drag, CAVA audio capture and PipeWire monitors. Use `tools/smoke_native.py`.
"""

import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest

from grimoire.sources import collect

TIMEOUT = 60


@pytest.fixture
def env(tmp_path):
    values = dict(os.environ)
    for name, sub in [
        ("HOME", "home"),
        ("XDG_CONFIG_HOME", "config"),
        ("XDG_DATA_HOME", "data"),
        ("XDG_STATE_HOME", "state"),
        ("XDG_RUNTIME_DIR", "runtime"),
    ]:
        path = tmp_path / sub
        path.mkdir(mode=0o700)
        values[name] = str(path)
    values["QT_QPA_PLATFORM"] = "offscreen"
    values.pop("XDG_SESSION_TYPE", None)
    return values


def grimoire(env, *args, cwd=None, timeout=TIMEOUT):
    return subprocess.run(
        [sys.executable, "-m", "grimoire", *args],
        env=env,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def qt_gui_available(env):
    probe = subprocess.run(
        [sys.executable, "-c", "from PySide6.QtWidgets import QApplication; QApplication([])"],
        env=env,
        capture_output=True,
        text=True,
        timeout=TIMEOUT,
    )
    return probe.returncode == 0, (probe.stderr.strip().splitlines() or ["unknown error"])[-1]


def require_qt(env):
    ok, reason = qt_gui_available(env)
    if not ok:
        pytest.skip(f"Qt offscreen platform unavailable: {reason}")


def png_size(path: Path):
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "capture is not a PNG file"
    assert data[12:16] == b"IHDR"
    return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")


def test_event_cli_round_trips_through_source_adapter(env, tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    (work / "map.png").write_bytes(b"synthetic")
    (work / "notes.md").write_text("synthetic handoff\n")

    first = grimoire(
        env, "event", "--id", "map", "--agent", "example", "--state", "working",
        "--title", "Drawing a map", cwd=work,
    )
    assert first.returncode == 0, first.stderr
    path = Path(json.loads(first.stdout)["event"])
    events = Path(env["XDG_STATE_HOME"]) / "grimoire/events"
    assert path == events / "map.json"

    tasks, errors = collect("", events)
    assert errors == []
    assert [(t.id, t.state, t.agent, t.title) for t in tasks] == [
        ("event:map", "working", "example", "Drawing a map")
    ]

    done = grimoire(
        env, "event", "--id", "map", "--agent", "example", "--state", "done",
        "--title", "Map ready", "--artifact", "./map.png", "--handoff", "./notes.md",
        cwd=work,
    )
    assert done.returncode == 0, done.stderr
    tasks, errors = collect("", events)
    assert errors == [] and len(tasks) == 1
    task = tasks[0]
    assert (task.state, task.title) == ("done", "Map ready")
    assert task.artifacts == (str(work / "map.png"),)
    assert task.handoff == str(work / "notes.md")
    assert sorted(p.name for p in events.iterdir()) == ["map.json"]  # no temp files left


def test_event_cli_rejects_bad_input_without_writing(env):
    bad_id = grimoire(env, "event", "--id", "../escape", "--state", "done", "--title", "x")
    assert bad_id.returncode == 2 and "id must contain" in bad_id.stderr
    bad_ttl = grimoire(env, "event", "--id", "ok", "--state", "working", "--title", "x",
                       "--ttl", "5")
    assert bad_ttl.returncode == 2 and "ttl must be" in bad_ttl.stderr
    bad_state = grimoire(env, "event", "--id", "ok", "--state", "running", "--title", "x")
    assert bad_state.returncode == 2
    assert not (Path(env["XDG_STATE_HOME"]) / "grimoire/events").exists()


def test_agent_task_directory_is_read_without_modification(tmp_path):
    root = tmp_path / "tasks"
    now = time.time()
    records = {
        "alpha/one": {"status": "active", "expires": now + 600},
        "alpha/two": {"status": "completed", "expires": None},
        "beta/three": {"status": "active", "expires": now - 600},
    }
    originals = {}
    for name, spec in records.items():
        path = root / name / "state.json"
        path.parent.mkdir(parents=True)
        owner = None
        if spec["expires"] is not None:
            expires = datetime.fromtimestamp(spec["expires"], UTC).isoformat()
            owner = {"agent": "synthetic", "expires_at": expires}
        path.write_text(json.dumps({
            "schema": 1,
            "status": spec["status"],
            "project": name.split("/")[0],
            "task": name.split("/")[1],
            "title": f"Synthetic {name}",
            "updated_at": datetime.fromtimestamp(now - 60, UTC).isoformat(),
            "owner": owner,
            "checkpoint": {"summary": "synthetic", "outputs": []},
        }))
        originals[path] = path.read_bytes()

    tasks, errors = collect(str(root), tmp_path / "no-events", now)
    assert errors == []
    states = {t.id: t.state for t in tasks}
    assert states == {
        "task:alpha/one": "working",
        "task:alpha/two": "done",
        "task:beta/three": "attention",
    }
    assert all(path.read_bytes() == data for path, data in originals.items())


def test_doctor_reports_prerequisites_as_json(env):
    result = grimoire(env, "doctor")
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["version"] and report["pyside"]
    assert report["session"] == "unknown"
    assert report["task_source_configured"] is False
    assert report["settings_error"] == ""
    assert not (Path(env["XDG_CONFIG_HOME"]) / "grimoire/settings.json").exists()


def test_doctor_reports_damaged_settings_without_overwriting(env):
    settings = Path(env["XDG_CONFIG_HOME"]) / "grimoire/settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text("{not json")
    result = grimoire(env, "doctor")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["settings_error"]
    assert settings.read_text() == "{not json"


def test_capture_requires_demo(env, tmp_path):
    result = grimoire(env, "--capture", str(tmp_path / "x.png"))
    assert result.returncode == 2 and "require --demo" in result.stderr
    assert not (tmp_path / "x.png").exists()


@pytest.mark.parametrize("theme", ["night", "dawn"])
def test_offscreen_demo_capture_writes_png(env, tmp_path, theme):
    require_qt(env)
    target = tmp_path / "out" / f"{theme}.png"
    result = grimoire(env, "--demo", "--theme", theme, "--capture", str(target))
    assert result.returncode == 0, result.stderr
    width, height = png_size(target)
    assert width >= 400 and height >= 300
    assert target.stat().st_size > 10_000  # a blank window compresses far smaller
    # The demo uses its own temporary settings and never writes user configuration.
    assert not (Path(env["XDG_CONFIG_HOME"]) / "grimoire").exists()


def test_offscreen_app_lifecycle_single_instance_and_quit(env):
    require_qt(env)
    state = Path(env["XDG_STATE_HOME"]) / "grimoire"
    socket = state / "control.sock"
    if len(str(socket).encode()) > 100:
        pytest.skip("temporary path too long for a Unix domain socket")
    assert grimoire(env, "event", "--id", "smoke", "--state", "working",
                    "--title", "Synthetic").returncode == 0
    app = subprocess.Popen(
        [sys.executable, "-m", "grimoire"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.monotonic() + 20
        while not socket.exists() and app.poll() is None and time.monotonic() < deadline:
            time.sleep(0.1)
        assert app.poll() is None, app.communicate()[1]
        assert socket.exists(), "application socket did not appear"
        second = grimoire(env)  # A second launch hands off to the running instance.
        assert second.returncode == 0, second.stderr
        assert grimoire(env, "quit").returncode == 0
        assert app.wait(timeout=20) == 0
    finally:
        if app.poll() is None:
            app.kill()
            app.wait()
    log = [json.loads(line) for line in (state / "events.jsonl").read_text().splitlines()]
    names = [entry["event"] for entry in log]
    assert names[0] == "startup" and names[-1] == "shutdown"
    assert all("Synthetic" not in json.dumps(entry) for entry in log)  # titles stay out of logs


@pytest.mark.skip(
    reason="Needs a real desktop session (tray, companion placement, CAVA/PipeWire audio); "
    "run tools/smoke_native.py on a desktop instead"
)
def test_native_desktop_tray_and_cava():
    pass
