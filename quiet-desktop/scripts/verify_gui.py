"""Opt-in GTK/live-service smoke check and capture of only this app's window."""

import argparse
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from freiren_quiet import client  # noqa: E402
from freiren_quiet.gui import Gdk, Gio, GLib, QuietApp  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm-live", action="store_true", required=True)
    parser.add_argument("--screenshot", type=Path, required=True)
    args = parser.parse_args()
    original = client.request()
    app = QuietApp()
    app.set_flags(Gio.ApplicationFlags.NON_UNIQUE)
    step = 0
    failed = []
    attempts = 0

    def advance():
        nonlocal step, attempts
        attempts += 1
        try:
            assert attempts < 60, "GUI operation timed out"
            window = app.window
            if not window or window.busy or window.last_status is None:
                return True
            if step == 0:
                window.buttons["quiet"].clicked()
            elif step == 1:
                assert window.last_status["mode"] == "quiet", window.last_status
                assert window.values["cap"].get_text() == "60%", window.last_status
                print("PASS: GTK quiet button and metric readback")
                window.buttons["auto"].clicked()
            elif step == 2:
                assert window.last_status["mode"] == "auto", window.last_status
                window.present()
            elif step == 3:
                surface = window.get_window()
                capture = Gdk.pixbuf_get_from_window(
                    surface, 0, 0, surface.get_width(), surface.get_height()
                )
                assert capture is not None, "Could not capture app window"
                args.screenshot.parent.mkdir(parents=True, exist_ok=True)
                capture.savev(str(args.screenshot), "png", [], [])
                print(f"PASS: GUI capture {args.screenshot}")
                window.destroy()
                app.quit()
                return False
            step += 1
            return True
        except Exception:
            failed.append(traceback.format_exc())
            app.quit()
            return False

    GLib.timeout_add_seconds(1, advance)
    try:
        app.run(None)
    finally:
        client.request("target", target=original["target_c"])
        client.request("mode", mode=original["mode"])
    if failed:
        raise RuntimeError(failed[0])


if __name__ == "__main__":
    main()
