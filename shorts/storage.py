from __future__ import annotations

import sqlite3
from pathlib import Path

from .curator import is_duplicate
from .models import NewsItem, canonical_url


class Storage:
    def __init__(self, path: str | Path = "data/history.sqlite3") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.execute("PRAGMA journal_mode=WAL")
        self._create_tables()

    def _create_tables(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS news (
                identity TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                url TEXT NOT NULL,
                source TEXT NOT NULL,
                published_at TEXT NOT NULL,
                detected_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS publications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                slot TEXT NOT NULL,
                kind TEXT NOT NULL,
                identity TEXT NOT NULL,
                video_id TEXT,
                video_url TEXT,
                status TEXT NOT NULL,
                cost INTEGER NOT NULL DEFAULT 0,
                published_at TEXT NOT NULL
            );
            """
        )
        self.connection.commit()

    def seen_identity(self, identity: str) -> bool:
        row = self.connection.execute(
            "SELECT 1 FROM news WHERE identity = ?", (identity,)
        ).fetchone()
        return row is not None

    def seen_item(self, item: NewsItem) -> bool:
        if item.url and self.seen_identity(canonical_url(item.url)):
            return True
        rows = self.connection.execute("SELECT title, url FROM news").fetchall()
        return any(
            is_duplicate(
                item,
                NewsItem(
                    title=title,
                    url=url,
                    source="",
                    published_at=None,
                ),
            )
            for title, url in rows
        )

    def mark_seen(self, identity: str, title: str, url: str, source: str, published_at: str) -> None:
        self.connection.execute(
            """
            INSERT OR IGNORE INTO news
            (identity, title, url, source, published_at, detected_at)
            VALUES (?, ?, ?, ?, ?, datetime('now'))
            """,
            (identity, title, url, source, published_at),
        )
        self.connection.commit()

    def record_publication(
        self,
        slot: str,
        kind: str,
        identity: str,
        status: str,
        video_id: str | None = None,
        video_url: str | None = None,
        cost: int = 0,
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO publications
            (slot, kind, identity, video_id, video_url, status, cost, published_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            (slot, kind, identity, video_id, video_url, status, cost),
        )
        self.connection.commit()

    def daily_upload_count(self) -> int:
        row = self.connection.execute(
            """
            SELECT COUNT(*) FROM publications
            WHERE status = 'uploaded'
              AND published_at >= datetime('now', 'start of day')
            """
        ).fetchone()
        return int(row[0] if row else 0)

    def daily_quota_cost(self) -> int:
        row = self.connection.execute(
            """
            SELECT COALESCE(SUM(cost), 0) FROM publications
            WHERE published_at >= datetime('now', 'start of day')
            """
        ).fetchone()
        return int(row[0] if row else 0)

    def close(self) -> None:
        self.connection.close()
