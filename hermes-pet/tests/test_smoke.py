"""End-to-end smoke tests: CLI --once, the --serve HTTP server and regressions.

Everything uses synthetic temporary SQLite databases and a loopback server on
an ephemeral port. No network access beyond 127.0.0.1, no model calls.
"""

import contextlib
import hashlib
import io
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

from tools.hermes_pet import pet
from tools.hermes_pet.state_source import HermesStateSource

PROJECT_ROOT = Path(__file__).resolve().parents[1]

XSS_TEXT = "완료: <script>alert(1)</script> & <img src=x>"


def make_db(path: Path, rows) -> Path:
    """Create a synthetic Hermes state.db with the schema the pet reads."""
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.execute("create table sessions (id text primary key, source text not null, title text, started_at real not null)")
        conn.execute(
            "create table messages (id integer primary key autoincrement, session_id text not null, "
            "role text not null, content text, timestamp real not null, active integer default 1)"
        )
        conn.execute("insert into sessions values ('tg', 'telegram', 'Chat', 1.0)")
        conn.execute("insert into sessions values ('cl', 'cli', 'CLI', 2.0)")
        for session_id, role, content, active in rows:
            conn.execute(
                "insert into messages (session_id, role, content, timestamp, active) values (?, ?, ?, 10.0, ?)",
                (session_id, role, content, active),
            )
        conn.commit()
    finally:
        conn.close()
    return path


def run_main(argv) -> str:
    out = io.StringIO()
    with mock.patch.object(sys, "argv", ["pet"] + list(argv)), contextlib.redirect_stdout(out):
        rc = pet.main()
    assert rc == 0
    return out.getvalue().strip()


class CliOnceSmokeTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.tmp = Path(self._td.name)
        self.db = make_db(
            self.tmp / "state.db",
            [
                ("tg", "user", "요청", 1),
                ("tg", "assistant", "완료: 텔레그램 결과", 1),
                ("tg", "assistant", "비활성 답변", 0),
                ("cl", "assistant", "CLI 오류 답변", 1),
            ],
        )

    def tearDown(self):
        self._td.cleanup()

    def test_module_cli_once_prints_latest_telegram_result(self):
        proc = subprocess.run(
            [sys.executable, "-m", "tools.hermes_pet.pet", "--db", str(self.db), "--once"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
            env={**os.environ, "HOME": str(self.tmp), "HERMES_HOME": str(self.tmp / "hermes")},
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.strip(), "✅ 끝났어 — 완료: 텔레그램 결과")

    def test_once_with_missing_db_shows_idle_and_creates_nothing(self):
        missing = self.tmp / "nope" / "state.db"
        self.assertEqual(run_main(["--db", str(missing), "--once"]), "🌸 기다리는 중 — 아직 새 결과가 없습니다.")
        self.assertFalse(missing.exists())
        self.assertFalse(missing.parent.exists())

    def test_once_does_not_modify_database(self):
        before = hashlib.sha256(self.db.read_bytes()).hexdigest()
        run_main(["--db", str(self.db), "--once"])
        self.assertEqual(hashlib.sha256(self.db.read_bytes()).hexdigest(), before)
        self.assertFalse(Path(str(self.db) + "-journal").exists())
        self.assertFalse(Path(str(self.db) + "-wal").exists())

    def test_source_flag_replaces_default_telegram(self):
        # Regression: action="append" with default=["telegram"] appended to the
        # default, so "--source cli" still included telegram sessions.
        db = make_db(
            self.tmp / "order.db",
            [("cl", "assistant", "CLI 답변", 1), ("tg", "assistant", "텔레그램 최신", 1)],
        )
        self.assertEqual(run_main(["--db", str(db), "--once", "--source", "cli"]), "✨ 보고 있어 — CLI 답변")
        self.assertEqual(run_main(["--db", str(db), "--once"]), "✨ 보고 있어 — 텔레그램 최신")

    def test_db_path_with_uri_special_characters(self):
        # Regression: the path was put into a file: URI unescaped, so '#', '?'
        # or '%' in a directory name silently showed the idle state.
        for dirname in ("a#b", "q?x", "p%20q"):
            with self.subTest(dirname=dirname):
                db = make_db(self.tmp / dirname / "state.db", [("tg", "assistant", "완료: 특수 경로", 1)])
                self.assertEqual(run_main(["--db", str(db), "--once"]), "✅ 끝났어 — 완료: 특수 경로")

    def test_state_source_closes_connection(self):
        # Regression: "with sqlite3.connect(...)" only commits; it never closed
        # the connection (ResourceWarning: unclosed database on Python 3.13).
        opened = []
        real_connect = sqlite3.connect

        def tracking_connect(*args, **kwargs):
            conn = real_connect(*args, **kwargs)
            opened.append(conn)
            return conn

        with mock.patch("tools.hermes_pet.state_source.sqlite3.connect", side_effect=tracking_connect):
            msg = HermesStateSource(self.db).latest_assistant_message()
        self.assertIsNotNone(msg)
        self.assertEqual(len(opened), 1)
        with self.assertRaises(sqlite3.ProgrammingError):
            opened[0].execute("select 1")


class _CapturingServer(pet.ThreadingHTTPServer):
    instances = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _CapturingServer.instances.append(self)


class ServeSmokeTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.tmp = Path(self._td.name)

    def tearDown(self):
        self._td.cleanup()

    @contextlib.contextmanager
    def running(self, db: Path, asset: pet.PetAsset = pet.PetAsset()):
        _CapturingServer.instances.clear()
        source = HermesStateSource(db, allowed_sources={"telegram"})
        with mock.patch.object(pet, "ThreadingHTTPServer", _CapturingServer), contextlib.redirect_stdout(io.StringIO()):
            thread = threading.Thread(target=pet.serve, args=(source, "127.0.0.1", 0, 120, False, asset), daemon=True)
            thread.start()
            for _ in range(200):
                if _CapturingServer.instances:
                    break
                threading.Event().wait(0.01)
            server = _CapturingServer.instances[0]
            try:
                yield f"http://127.0.0.1:{server.server_address[1]}"
            finally:
                server.shutdown()
                thread.join(5)

    def get(self, url):
        try:
            with urllib.request.urlopen(url, timeout=5) as res:
                return res.status, res.headers.get("Content-Type"), res.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.headers.get("Content-Type"), exc.read()

    def test_serve_index_and_state_endpoints(self):
        db = make_db(self.tmp / "state.db", [("tg", "assistant", XSS_TEXT, 1)])
        with self.running(db) as base:
            status, ctype, body = self.get(base + "/")
            self.assertEqual(status, 200)
            self.assertTrue(ctype.startswith("text/html"))
            html = body.decode("utf-8")
            # DB text is never rendered server-side; the page inserts it via textContent.
            self.assertNotIn("alert(1)", html)
            self.assertIn("getElementById('bubble').textContent", html)
            self.assertNotIn("innerHTML", html)

            status, ctype, body = self.get(base + "/api/state")
            self.assertEqual(status, 200)
            self.assertTrue(ctype.startswith("application/json"))
            data = json.loads(body)
            self.assertEqual(data["snippet"], XSS_TEXT)
            self.assertEqual(data["source"], "telegram")

            self.assertEqual(self.get(base + "/assets/spritesheet.webp")[0], 404)
            self.assertEqual(self.get(base + "/assets/../state.db")[0], 404)
            self.assertEqual(self.get(base + "/nope")[0], 404)

    def test_serve_missing_db_reports_idle(self):
        missing = self.tmp / "missing.db"
        with self.running(missing) as base:
            data = json.loads(self.get(base + "/api/state")[2])
        self.assertEqual(data["status"], "idle")
        self.assertIsNone(data["message_id"])
        self.assertFalse(missing.exists())

    def test_serve_spritesheet_from_asset_dir(self):
        asset_dir = self.tmp / "asset"
        asset_dir.mkdir()
        (asset_dir / "pet.json").write_text('{"displayName": "Synthetic"}', encoding="utf-8")
        (asset_dir / "spritesheet.webp").write_bytes(b"RIFFsynthetic")
        asset = pet.load_pet_asset(asset_dir)
        with self.running(self.tmp / "missing.db", asset) as base:
            status, ctype, body = self.get(base + "/assets/spritesheet.webp")
        self.assertEqual((status, ctype, body), (200, "image/webp", b"RIFFsynthetic"))

    def test_asset_spritesheet_path_cannot_escape_asset_dir(self):
        # Regression: spritesheetPath from pet.json was joined unchecked, so an
        # absolute path or "../" made the server publish any readable file.
        secret = self.tmp / "secret.txt"
        secret.write_text("synthetic secret", encoding="utf-8")
        asset_dir = self.tmp / "asset"
        asset_dir.mkdir()
        for sheet in (str(secret), "../secret.txt"):
            with self.subTest(sheet=sheet):
                (asset_dir / "pet.json").write_text(json.dumps({"spritesheetPath": sheet}), encoding="utf-8")
                self.assertIsNone(pet.load_pet_asset(asset_dir).spritesheet)


if __name__ == "__main__":
    unittest.main()
