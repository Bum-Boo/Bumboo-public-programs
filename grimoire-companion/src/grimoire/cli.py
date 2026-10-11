"""Public commands; event producers do not require a running GUI."""

import argparse
import importlib.metadata
import json
import os
import shutil
import signal
import sys
import tempfile
from pathlib import Path

from . import __version__
from .config import Settings, location
from .sources import write_event


def main(argv=None):
    parser = argparse.ArgumentParser(description="Grimoire · a quiet desktop companion")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--background", action="store_true", help="Start companion and tray only")
    parser.add_argument(
        "--demo", action="store_true", help="Isolated, explicitly labeled design preview"
    )
    parser.add_argument(
        "--capture", type=Path, help="Save demo window to PNG and exit (requires --demo)"
    )
    parser.add_argument("--theme", choices=["night", "dawn"], help="Preview palette, with --demo")
    sub = parser.add_subparsers(dest="command")
    event = sub.add_parser("event", help="Publish an explicit local agent state")
    event.add_argument("--id", required=True)
    event.add_argument(
        "--state", required=True, choices=["idle", "working", "done", "attention", "error"]
    )
    event.add_argument("--title", required=True)
    event.add_argument("--agent", default="agent")
    event.add_argument("--detail", default="")
    event.add_argument("--artifact", default="")
    event.add_argument("--handoff", default="")
    event.add_argument("--ttl", type=int, default=300)
    sub.add_parser("doctor", help="Report local prerequisites without modifying them")
    sub.add_parser("quit", help="Gracefully stop the running application")
    args = parser.parse_args(argv)
    if args.command == "quit":
        from PySide6.QtCore import QCoreApplication, QLockFile
        from PySide6.QtNetwork import QLocalServer, QLocalSocket

        core = QCoreApplication.instance() or QCoreApplication([])
        client = QLocalSocket()
        client.connectToServer(str(location("state") / "control.sock"))
        if not client.waitForConnected(1000):
            guard = QLockFile(str(location("state") / "instance.lock"))
            guard.setStaleLockTime(0)
            if guard.tryLock(0):
                QLocalServer.removeServer(str(location("state") / "control.sock"))
                guard.unlock()
                return 0
            print("The application is running but not responding yet.", file=sys.stderr)
            return 1
        client.write(b"quit")
        client.waitForBytesWritten(1000)
        client.disconnectFromServer()
        core.processEvents()
        return 0
    if args.command == "event":
        try:
            path = write_event(
                location("state") / "events",
                event_id=args.id,
                state=args.state,
                title=args.title,
                agent=args.agent,
                detail=args.detail,
                artifact=args.artifact,
                handoff=args.handoff,
                ttl=args.ttl,
            )
        except (OSError, ValueError) as exc:
            parser.error(str(exc))
        print(json.dumps({"ok": True, "event": str(path)}, ensure_ascii=False))
        return 0
    if args.command == "doctor":
        s = Settings()
        cava = s["cava_path"] or shutil.which("cava")
        local = Path.home() / ".local/bin/cava"
        cava = cava or (str(local) if local.is_file() else None)
        report = {
            "version": __version__,
            "python": sys.version.split()[0],
            "pyside": importlib.metadata.version("PySide6-Essentials"),
            "session": os.environ.get("XDG_SESSION_TYPE", "unknown"),
            "cava": bool(cava),
            "task_source_configured": bool(s["task_root"]),
            "task_source_exists": bool(s["task_root"] and Path(s["task_root"]).is_dir()),
            "personal_skin_configured": bool(s["skin"]),
            "settings_error": s.error,
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    if (args.capture or args.theme) and not args.demo:
        parser.error("--capture and --theme require --demo")
    return run_gui(args)


def run_gui(args):
    from PySide6.QtCore import QLockFile, QTimer
    from PySide6.QtNetwork import QLocalServer, QLocalSocket
    from PySide6.QtWidgets import QApplication

    from .app import Controller
    from .logging_utils import setup_logging

    app = QApplication([sys.argv[0]])
    app.setApplicationName("Grimoire")
    app.setApplicationVersion(__version__)
    app.setOrganizationName("Grimoire")
    app.setDesktopFileName("grimoire")
    app.setQuitOnLastWindowClosed(False)
    setup_logging()
    server = None
    lock = None
    demo_directory = None
    if args.demo:
        demo_directory = tempfile.TemporaryDirectory(prefix="grimoire-preview-")
        settings = Settings(Path(demo_directory.name) / "settings.json")
        settings.update(
            theme=args.theme or "night",
            audio_enabled=False,
            companion_visible=False,
            reduced_motion=True,
        )
    else:
        state = location("state")
        state.mkdir(parents=True, exist_ok=True, mode=0o700)
        lock = QLockFile(str(state / "instance.lock"))
        lock.setStaleLockTime(0)
        socket_name = str(state / "control.sock")
        if not lock.tryLock(0):
            client = QLocalSocket()
            client.connectToServer(socket_name)
            if client.waitForConnected(1000):
                client.write(b"show")
                client.waitForBytesWritten(1000)
                client.disconnectFromServer()
                return 0
            print(
                "Grimoire is already starting or running; try opening it again shortly.",
                file=sys.stderr,
            )
            return 1
        QLocalServer.removeServer(socket_name)
        server = QLocalServer()
        server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        if not server.listen(socket_name):
            print("Could not open local application socket.", file=sys.stderr)
            lock.unlock()
            return 1
        settings = Settings()
    controller = Controller(app, settings, demo=args.demo)
    signal.signal(signal.SIGTERM, lambda *_: controller.quit())
    signal.signal(signal.SIGINT, lambda *_: controller.quit())
    signal_tick = QTimer(app)
    signal_tick.timeout.connect(lambda: None)
    signal_tick.start(500)
    if server:

        def activate():
            connection = server.nextPendingConnection()

            def dispatch():
                command = bytes(connection.readAll())[:16]
                connection.disconnectFromServer()
                connection.deleteLater()
                if command == b"quit":
                    controller.quit()
                else:
                    controller.show_window()

            connection.readyRead.connect(dispatch)
            if connection.bytesAvailable():
                dispatch()

        server.newConnection.connect(activate)
    if not args.background or controller.tray is None:
        controller.show_window()
    capture_ok = [True]
    if args.capture:

        def capture():
            args.capture.parent.mkdir(parents=True, exist_ok=True)
            capture_ok[0] = controller.window.grab().save(str(args.capture))
            controller.quit()

        QTimer.singleShot(600, capture)
    try:
        result = app.exec()
    finally:
        controller.shutdown()
        if server:
            server.close()
        if lock:
            lock.unlock()
        if demo_directory:
            demo_directory.cleanup()
    return result if capture_ok[0] else 1
