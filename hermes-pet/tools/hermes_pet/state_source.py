from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
import sqlite3
from typing import Iterable
from urllib.parse import quote


@dataclass(frozen=True)
class PetMessage:
    id: int
    session_id: str
    source: str
    role: str
    content: str
    timestamp: float


class HermesStateSource:
    """Read-only view over a Hermes state.db message store."""

    def __init__(self, db_path: Path | str, allowed_sources: Iterable[str] | None = None):
        self.db_path = Path(db_path).expanduser()
        self.allowed_sources = set(allowed_sources or {"telegram"})

    def latest_assistant_message(self, after_id: int | None = None) -> PetMessage | None:
        if not self.db_path.exists():
            return None

        query = """
            select m.id, m.session_id, s.source, m.role, coalesce(m.content, ''), m.timestamp
            from messages m
            join sessions s on s.id = m.session_id
            where m.role = 'assistant'
              and coalesce(m.active, 1) = 1
              and coalesce(m.content, '') != ''
        """
        params: list[object] = []

        if self.allowed_sources:
            placeholders = ",".join("?" for _ in self.allowed_sources)
            query += f" and s.source in ({placeholders})"
            params.extend(sorted(self.allowed_sources))

        if after_id is not None:
            query += " and m.id > ?"
            params.append(after_id)

        query += " order by m.id desc limit 1"

        # Percent-encode the path so '?', '#' or '%' in a directory name are not
        # parsed as URI query/fragment/escape characters by SQLite.
        uri = f"file:{quote(self.db_path.as_posix(), safe='/:')}?mode=ro"
        try:
            with closing(sqlite3.connect(uri, uri=True, timeout=1.0)) as conn:
                row = conn.execute(query, params).fetchone()
        except sqlite3.Error:
            return None

        if row is None:
            return None
        return PetMessage(
            id=int(row[0]),
            session_id=str(row[1]),
            source=str(row[2]),
            role=str(row[3]),
            content=str(row[4]),
            timestamp=float(row[5]),
        )
