#!/usr/bin/env python3
"""One bounded native smoke pass using synthetic tasks and an inaudible test sink."""

import argparse
import json
import math
import os
import struct
import subprocess
import tempfile
import time
import uuid
import wave
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--skin", default="")
    parser.add_argument("--audio", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    temporary = tempfile.TemporaryDirectory(prefix="grimoire-native-")
    root = Path(temporary.name)
    os.environ["XDG_STATE_HOME"] = str(root / "state")
    from PySide6.QtCore import QPoint, QProcess, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QHBoxLayout, QPlainTextEdit, QPushButton, QWidget

    from grimoire.app import Controller
    from grimoire.config import Settings, location
    from grimoire.logging_utils import setup_logging
    from grimoire.sources import write_event
    from grimoire.widgets import CharacterStage

    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    app.setDesktopFileName("grimoire")
    setup_logging()
    settings = Settings(root / "settings.json")
    settings.update(audio_enabled=False, skin=args.skin, quiet=True)
    event_root = location("state") / "events"
    write_event(
        event_root,
        event_id="map",
        state="working",
        title="도서관 지도를 그리고 있어요",
        agent="test",
    )
    c = Controller(app, settings)
    checks = []
    errors = []
    module = None
    player = None

    def pump(predicate, timeout=4):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            app.processEvents()
            if predicate():
                return
            QTest.qWait(20)
        raise AssertionError("Timed out waiting for observed state")

    def check(name, condition):
        if not condition:
            raise AssertionError(name)
        checks.append(name)

    try:
        check("native_x11", app.platformName() == "xcb")
        c.show_window()
        pump(lambda: len(c.tasks) == 1)
        check("working_record_reaches_character", c.companion.state == "working")
        check("no_startup_completion", not c.celebration.isActive())
        check("disabled_audio_label", "쉬고" in c.window.audio_label.text())
        c.window.grab().save(str(args.output / "native-night.png"))
        for index, theme in enumerate(("dawn", "night")):
            c.window.tabs.setCurrentIndex(2)
            c.window.theme.setCurrentIndex(index if theme == "night" else 1)
            if settings["theme"] != theme:
                c.window.theme.setCurrentIndex(0 if theme == "night" else 1)
            check(f"theme_{theme}", settings["theme"] == theme)
            c.window.grab().save(str(args.output / f"settings-{theme}.png"))
        reduced = c.window.checks["reduced_motion"]
        c.window.settings_page.ensureWidgetVisible(reduced)
        QTest.mouseClick(reduced, Qt.MouseButton.LeftButton, pos=QPoint(10, reduced.height() // 2))
        check(
            "reduced_motion_stops_timer",
            settings["reduced_motion"] and not c.companion.clock.isActive(),
        )
        c.window.size_slider.setFocus()
        QTest.keyClick(c.window.size_slider, Qt.Key.Key_Right)
        pump(lambda: settings["scale"] == 1.01)
        check("keyboard_size_persists", Settings(settings.path)["scale"] == 1.01)
        c.change(scale=1.0)
        old_pos = c.companion.pos()
        QTest.mousePress(c.companion, Qt.MouseButton.LeftButton, pos=QPoint(120, 150))
        QTest.mouseMove(c.companion, QPoint(65, 115), delay=30)
        QTest.mouseRelease(c.companion, Qt.MouseButton.LeftButton, pos=QPoint(65, 115))
        check(
            "drag_moves_and_persists",
            c.companion.pos() != old_pos and settings["position"] is not None,
        )
        c.change(position=[100000, 100000])
        c.companion.place(settings["position"])
        check(
            "offscreen_position_clamped",
            app.primaryScreen().availableGeometry().contains(c.companion.frameGeometry()),
        )
        c.window.hide()
        QTest.mouseClick(c.companion, Qt.MouseButton.LeftButton, pos=QPoint(100, 150))
        check("character_opens_window", c.window.isVisible())
        c.change(companion_visible=False)
        check("hide", not c.companion.isVisible())
        c.toggle_companion()
        check("restore", c.companion.isVisible())
        c.change(resting=True)
        check("rest_pose", c.companion.state == "sleep")
        c.change(resting=False)
        artifact = root / "result.md"
        artifact.write_text("# A little result\n\nverification-artifact\n")
        handoff = root / "handoff.md"
        handoff.write_text("# Next step\n\nverification-handoff\n")
        write_event(
            event_root,
            event_id="map",
            state="done",
            title="새 지도가 도착했어요",
            artifact=str(artifact),
            handoff=str(handoff),
        )
        c.refresh()
        pump(lambda: c.companion.state == "done")
        check("completion_pose", c.celebration.isActive())
        c.window.tabs.setCurrentIndex(0)
        app.processEvents()
        result_button = next(
            b for b in c.window.home.findChildren(QPushButton) if b.text() == "결과 열기"
        )
        QTest.mouseClick(result_button, Qt.MouseButton.LeftButton)
        pump(lambda: bool(c.document_windows))
        reader = c.document_windows[-1]
        check(
            "result_button_reads_artifact",
            "verification-artifact" in reader.findChild(QPlainTextEdit).toPlainText(),
        )
        reader.grab().save(str(args.output / "artifact-reader.png"))
        reader.close()
        app.processEvents()
        handoff_button = next(
            b for b in c.window.home.findChildren(QPushButton) if b.text() == "이어가기"
        )
        QTest.mouseClick(handoff_button, Qt.MouseButton.LeftButton)
        pump(lambda: bool(c.document_windows))
        check(
            "handoff_button_reads_note",
            "verification-handoff"
            in c.document_windows[-1].findChild(QPlainTextEdit).toPlainText(),
        )
        c.document_windows[-1].close()
        app.processEvents()
        c.celebration.stop()
        c.refresh_state()
        write_event(event_root, event_id="map", state="done", title="Only metadata changed")
        c.refresh()
        QTest.qWait(200)
        check("completed_metadata_does_not_renotify", not c.celebration.isActive())
        if c.tray:
            c.window.close()
            check("window_closes_to_tray", not c.window.isVisible() and c.tray.isVisible())
            c.tray_menu.actions()[0].trigger()
            check("tray_restores_window", c.window.isVisible())
        # Render a real widget for every state; keep personal-skin captures outside Git.
        preview = QWidget()
        row = QHBoxLayout(preview)
        for state in ("idle", "working", "done", "sleep", "attention", "error"):
            stage = CharacterStage(compact=True)
            stage.configure(settings, c.skin)
            stage.set_state(state)
            stage.setFixedSize(250, 315)
            row.addWidget(stage)
        preview.show()
        app.processEvents()
        preview.grab().save(str(args.output / "character-states.png"))
        preview.close()
        if args.audio:
            sink = "grimoire_test_" + uuid.uuid4().hex[:8]
            module = subprocess.check_output(
                ["pactl", "load-module", "module-null-sink", f"sink_name={sink}"], text=True
            ).strip()
            c.audio.start(source=sink + ".monitor")
            pump(lambda: c.audio.frames >= 5, timeout=10)
            check("cava_real_frames", c.audio.state == "listening")
            audio_pid = c.audio.process.processId()
            wav = root / "tone.wav"
            with wave.open(str(wav), "wb") as output:
                output.setnchannels(2)
                output.setsampwidth(2)
                output.setframerate(48000)
                pcm = b"".join(
                    struct.pack("<hh", v, v)
                    for v in (
                        int(5000 * math.sin(2 * math.pi * 440 * i / 48000)) for i in range(72000)
                    )
                )
                output.writeframes(pcm)
            player = subprocess.Popen(["paplay", f"--device={sink}", str(wav)])
            pump(lambda: c.audio.last_energy > 0.05)
            check("real_pcm_changes_spectrum", max(c.window.spectrum.values) > 0.05)
            peak = c.audio.last_energy
            c.window.grab().save(str(args.output / "real-cava-signal.png"))
            pump(lambda: player.poll() is not None)
            pump(lambda: c.audio.last_energy < 0.02, timeout=5)
            check("silence_returns_to_baseline", c.audio.last_energy < 0.02)
            c.audio.stop()
            check("audio_child_cleanup", not Path(f"/proc/{audio_pid}").exists())
            c.audio.start(executable="/no/such/cava")
            pump(lambda: c.audio.state == "error")
            check(
                "missing_binary_visible_error",
                c.audio.process.state() == QProcess.ProcessState.NotRunning,
            )
            c.audio.stop()
            checks.append(f"observed_peak_{peak:.3f}")
    except Exception as exc:
        errors.append(f"{type(exc).__name__}: {exc}")
    finally:
        if player and player.poll() is None:
            player.terminate()
            player.wait(timeout=3)
        c.shutdown()
        if module:
            subprocess.run(["pactl", "unload-module", module], check=True)
        report = {
            "platform": app.platformName(),
            "custom_skin": bool(args.skin),
            "checks": checks,
            "errors": errors,
        }
        (args.output / "native-smoke.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        temporary.cleanup()
    return bool(errors)


if __name__ == "__main__":
    raise SystemExit(main())
