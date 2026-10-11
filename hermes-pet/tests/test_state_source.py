import sqlite3
import tempfile
import unittest
from pathlib import Path

from tools.hermes_pet.state_source import HermesStateSource, PetMessage


class StateSourceTests(unittest.TestCase):
    def _make_db(self) -> Path:
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        path = Path(tmp.name)
        conn = sqlite3.connect(path)
        conn.execute("create table sessions (id text primary key, source text not null, title text, started_at real not null)")
        conn.execute(
            "create table messages (id integer primary key autoincrement, session_id text not null, role text not null, content text, timestamp real not null, active integer default 1)"
        )
        conn.execute("insert into sessions (id, source, title, started_at) values ('s1', 'telegram', 'Chat', 10.0)")
        conn.execute("insert into sessions (id, source, title, started_at) values ('s2', 'cli', 'Ignore', 11.0)")
        conn.execute("insert into messages (session_id, role, content, timestamp) values ('s1', 'user', '요청', 12.0)")
        conn.execute("insert into messages (session_id, role, content, timestamp) values ('s1', 'assistant', '완료: 기존 결과만 표시한다.', 13.0)")
        conn.execute("insert into messages (session_id, role, content, timestamp) values ('s2', 'assistant', 'CLI 답변', 14.0)")
        conn.commit()
        conn.close()
        return path

    def test_reads_latest_assistant_message_from_telegram_read_only(self):
        path = self._make_db()
        try:
            source = HermesStateSource(path, allowed_sources={"telegram"})
            msg = source.latest_assistant_message()
            self.assertIsInstance(msg, PetMessage)
            self.assertEqual(msg.content, "완료: 기존 결과만 표시한다.")
            self.assertEqual(msg.source, "telegram")
        finally:
            path.unlink(missing_ok=True)

    def test_missing_database_returns_none(self):
        source = HermesStateSource(Path("/tmp/does-not-exist-hermes-pet.db"))
        self.assertIsNone(source.latest_assistant_message())


if __name__ == "__main__":
    unittest.main()
