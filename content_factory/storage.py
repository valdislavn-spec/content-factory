"""Хранилище состояния на SQLite (без внешних зависимостей).

Хранит статьи, посты, публикации, метрики и запуски. SQLite выбран потому,
что он бесплатен, работает на любом ноутбуке/сервере и не требует СУБД.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from .models import (
    Article,
    GeneratedPost,
    MetricSnapshot,
    PublishResult,
    RunResult,
    utcnow,
)
from .utils import ensure_dir, format_iso, parse_datetime

SCHEMA = """
CREATE TABLE IF NOT EXISTS articles (
    channel_id   TEXT NOT NULL,
    article_id   TEXT NOT NULL,
    url_hash     TEXT NOT NULL,
    title        TEXT NOT NULL,
    url          TEXT NOT NULL,
    source_id    TEXT NOT NULL,
    source_name  TEXT NOT NULL,
    published_at TEXT,
    fetched_at   TEXT NOT NULL,
    text         TEXT DEFAULT '',
    summary      TEXT DEFAULT '',
    language     TEXT DEFAULT 'ru',
    meta         TEXT DEFAULT '{}',
    PRIMARY KEY (channel_id, article_id)
);
CREATE INDEX IF NOT EXISTS idx_articles_channel_time
    ON articles (channel_id, published_at);

CREATE TABLE IF NOT EXISTS posts (
    post_id      TEXT PRIMARY KEY,
    channel_id   TEXT NOT NULL,
    cluster_id   TEXT NOT NULL,
    format       TEXT NOT NULL,
    text         TEXT NOT NULL,
    hashtags     TEXT DEFAULT '[]',
    sources      TEXT DEFAULT '[]',
    created_at   TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'generated',
    score        REAL DEFAULT 0,
    external_url TEXT DEFAULT '',
    meta         TEXT DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_posts_channel_time ON posts (channel_id, created_at);

CREATE TABLE IF NOT EXISTS publishes (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id   TEXT NOT NULL,
    post_id      TEXT NOT NULL,
    publisher    TEXT NOT NULL,
    ok           INTEGER NOT NULL DEFAULT 0,
    external_id  TEXT DEFAULT '',
    url          TEXT DEFAULT '',
    error        TEXT DEFAULT '',
    dry_run      INTEGER NOT NULL DEFAULT 0,
    published_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_publishes_channel_time ON publishes (channel_id, published_at);

CREATE TABLE IF NOT EXISTS metrics (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id   TEXT NOT NULL,
    collected_at TEXT NOT NULL,
    subscribers  INTEGER,
    payload      TEXT DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_metrics_channel_time ON metrics (channel_id, collected_at);

CREATE TABLE IF NOT EXISTS runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id      TEXT NOT NULL,
    started_at      TEXT NOT NULL,
    finished_at     TEXT,
    duration_sec    REAL DEFAULT 0,
    articles_fetched INTEGER DEFAULT 0,
    articles_new    INTEGER DEFAULT 0,
    clusters        INTEGER DEFAULT 0,
    posts_generated INTEGER DEFAULT 0,
    posts_published INTEGER DEFAULT 0,
    errors          TEXT DEFAULT '[]',
    dry_run         INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_runs_channel_time ON runs (channel_id, started_at);
"""


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _loads(value: Optional[str], default: Any = None) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def _cutoff(days: float) -> str:
    return format_iso(utcnow() - timedelta(days=days))


class Storage:
    """Тонкая обёртка над SQLite с методами предметной области."""

    def __init__(self, db_path: Any) -> None:
        self.path = Path(db_path)
        ensure_dir(self.path.parent)
        self.conn = sqlite3.connect(str(self.path), timeout=30)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    # ------------------------------------------------------------------
    # Сервисное
    # ------------------------------------------------------------------
    def close(self) -> None:
        try:
            self.conn.close()
        finally:
            pass

    def __enter__(self) -> "Storage":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Статьи
    # ------------------------------------------------------------------
    def save_articles(self, channel_id: str, articles: Sequence[Article]) -> int:
        """Сохраняет статьи, возвращает число реально новых."""
        inserted = 0
        for article in articles:
            cursor = self.conn.execute(
                """INSERT OR IGNORE INTO articles
                (channel_id, article_id, url_hash, title, url, source_id, source_name,
                 published_at, fetched_at, text, summary, language, meta)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    channel_id,
                    article.id,
                    article.meta.get("url_hash") or article.id,
                    article.title,
                    article.url,
                    article.source_id,
                    article.source_name,
                    format_iso(article.published_at) or None,
                    format_iso(article.fetched_at or utcnow()),
                    article.text,
                    article.summary,
                    article.language,
                    _dumps(article.meta),
                ),
            )
            inserted += cursor.rowcount
        self.conn.commit()
        return inserted

    def filter_new_articles(
        self,
        channel_id: str,
        articles: Sequence[Article],
        window_hours: float = 24 * 30,
    ) -> List[Article]:
        """Убирает статьи, которые уже видели для этого канала."""
        if not articles:
            return []
        article_ids = [a.id for a in articles]
        placeholders = ",".join("?" for _ in article_ids)
        rows = self.conn.execute(
            f"""SELECT article_id FROM articles
                WHERE channel_id = ? AND article_id IN ({placeholders})
                AND fetched_at >= ?""",
            (channel_id, *article_ids, format_iso(utcnow() - timedelta(hours=window_hours))),
        ).fetchall()
        known = {row["article_id"] for row in rows}
        return [a for a in articles if a.id not in known]

    def recent_articles(
        self, channel_id: str, hours: float = 48.0, limit: int = 120
    ) -> List[Article]:
        """Свежие статьи канала из истории (для рекапа, когда новых нет)."""
        cutoff = format_iso(utcnow() - timedelta(hours=hours))
        rows = self.conn.execute(
            """SELECT * FROM articles
               WHERE channel_id = ?
                 AND (CASE WHEN published_at IS NULL OR published_at = ''
                           THEN fetched_at ELSE published_at END) >= ?
               ORDER BY (CASE WHEN published_at IS NULL OR published_at = ''
                              THEN fetched_at ELSE published_at END) DESC
               LIMIT ?""",
            (channel_id, cutoff, int(limit)),
        ).fetchall()
        articles: List[Article] = []
        for row in rows:
            articles.append(
                Article(
                    id=row["article_id"],
                    title=row["title"],
                    url=row["url"],
                    source_id=row["source_id"],
                    source_name=row["source_name"],
                    published_at=parse_datetime(row["published_at"]),
                    text=row["text"] or "",
                    summary=row["summary"] or "",
                    language=row["language"] or "ru",
                    meta=_loads(row["meta"], {}) or {},
                )
            )
        return articles

    def count_articles(self, channel_id: Optional[str] = None, days: float = 7) -> int:
        query = "SELECT COUNT(*) AS c FROM articles WHERE fetched_at >= ?"
        params: List[Any] = [_cutoff(days)]
        if channel_id:
            query += " AND channel_id = ?"
            params.append(channel_id)
        return int(self.conn.execute(query, params).fetchone()["c"])

    def article_sources(self, days: float = 7, limit: int = 20) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            """SELECT source_name, COUNT(*) AS count
               FROM articles WHERE fetched_at >= ?
               GROUP BY source_name ORDER BY count DESC LIMIT ?""",
            (_cutoff(days), limit),
        ).fetchall()
        return [{"source_name": row["source_name"], "count": row["count"]} for row in rows]

    # ------------------------------------------------------------------
    # Посты
    # ------------------------------------------------------------------
    def save_post(self, post: GeneratedPost, status: str = "generated") -> bool:
        cursor = self.conn.execute(
            """INSERT OR IGNORE INTO posts
            (post_id, channel_id, cluster_id, format, text, hashtags, sources,
             created_at, status, score, meta)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                post.id,
                post.channel_id,
                post.cluster_id,
                post.format,
                post.text,
                _dumps(post.hashtags),
                _dumps(post.sources),
                format_iso(post.created_at),
                status,
                float(post.score),
                _dumps(post.meta),
            ),
        )
        self.conn.commit()
        return cursor.rowcount > 0

    def mark_post_status(self, post_id: str, status: str, external_url: str = "") -> None:
        self.conn.execute(
            "UPDATE posts SET status = ?, external_url = ? WHERE post_id = ?",
            (status, external_url, post_id),
        )
        self.conn.commit()

    def recent_post_titles(self, channel_id: str, hours: float = 72) -> List[str]:
        rows = self.conn.execute(
            """SELECT text FROM posts
               WHERE channel_id = ? AND created_at >= ?
               ORDER BY created_at DESC LIMIT 100""",
            (channel_id, format_iso(utcnow() - timedelta(hours=hours))),
        ).fetchall()
        return [row["text"] for row in rows]

    def post_exists(self, post_id: str) -> bool:
        row = self.conn.execute("SELECT 1 FROM posts WHERE post_id = ?", (post_id,)).fetchone()
        return row is not None

    def get_posts(
        self, channel_id: Optional[str] = None, days: float = 7, limit: int = 500
    ) -> List[Dict[str, Any]]:
        query = "SELECT * FROM posts WHERE created_at >= ?"
        params: List[Any] = [_cutoff(days)]
        if channel_id:
            query += " AND channel_id = ?"
            params.append(channel_id)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        return [self._post_row(row) for row in self.conn.execute(query, params).fetchall()]

    @staticmethod
    def _post_row(row: sqlite3.Row) -> Dict[str, Any]:
        data = dict(row)
        data["hashtags"] = _loads(data.get("hashtags"), [])
        data["sources"] = _loads(data.get("sources"), [])
        data["meta"] = _loads(data.get("meta"), {})
        return data

    # ------------------------------------------------------------------
    # Публикации
    # ------------------------------------------------------------------
    def save_publish(self, result: PublishResult) -> None:
        self.conn.execute(
            """INSERT INTO publishes
            (channel_id, post_id, publisher, ok, external_id, url, error, dry_run, published_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                result.channel_id,
                result.post_id,
                result.publisher,
                1 if result.ok else 0,
                result.external_id,
                result.url,
                result.error,
                1 if result.dry_run else 0,
                format_iso(result.published_at),
            ),
        )
        self.conn.commit()

    def count_publishes(self, channel_id: Optional[str] = None, days: float = 7) -> Dict[str, int]:
        query = """SELECT COUNT(*) AS total,
                          SUM(CASE WHEN ok = 1 THEN 1 ELSE 0 END) AS ok,
                          SUM(CASE WHEN ok = 0 THEN 1 ELSE 0 END) AS failed,
                          SUM(CASE WHEN dry_run = 1 THEN 1 ELSE 0 END) AS dry_run
                   FROM publishes WHERE published_at >= ?"""
        params: List[Any] = [_cutoff(days)]
        if channel_id:
            query += " AND channel_id = ?"
            params.append(channel_id)
        row = self.conn.execute(query, params).fetchone()
        return {
            "total": int(row["total"] or 0),
            "ok": int(row["ok"] or 0),
            "failed": int(row["failed"] or 0),
            "dry_run": int(row["dry_run"] or 0),
        }

    def recent_publishes(self, days: float = 7, limit: int = 50) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM publishes WHERE published_at >= ? ORDER BY published_at DESC LIMIT ?",
            (_cutoff(days), limit),
        ).fetchall()
        return [dict(row) for row in rows]

    # ------------------------------------------------------------------
    # Метрики
    # ------------------------------------------------------------------
    def save_metrics(self, snapshot: MetricSnapshot) -> None:
        self.conn.execute(
            "INSERT INTO metrics (channel_id, collected_at, subscribers, payload) VALUES (?, ?, ?, ?)",
            (
                snapshot.channel_id,
                format_iso(snapshot.collected_at),
                snapshot.subscribers,
                _dumps(
                    {
                        "posts_total": snapshot.posts_total,
                        "posts_published": snapshot.posts_published,
                        "articles_total": snapshot.articles_total,
                        "avg_post_chars": snapshot.avg_post_chars,
                        "top_sources": snapshot.top_sources,
                        "top_terms": snapshot.top_terms,
                        "formats": snapshot.formats,
                        **snapshot.payload,
                    }
                ),
            ),
        )
        self.conn.commit()

    def latest_metrics(self, channel_id: str) -> Optional[Dict[str, Any]]:
        row = self.conn.execute(
            "SELECT * FROM metrics WHERE channel_id = ? ORDER BY collected_at DESC LIMIT 1",
            (channel_id,),
        ).fetchone()
        if not row:
            return None
        data = dict(row)
        data["payload"] = _loads(data.get("payload"), {})
        return data

    # ------------------------------------------------------------------
    # Запуски
    # ------------------------------------------------------------------
    def save_run(self, result: RunResult) -> None:
        self.conn.execute(
            """INSERT INTO runs
            (channel_id, started_at, finished_at, duration_sec, articles_fetched,
             articles_new, clusters, posts_generated, posts_published, errors, dry_run)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                result.channel_id,
                format_iso(result.started_at),
                format_iso(result.finished_at),
                result.duration_sec,
                result.articles_fetched,
                result.articles_new,
                result.clusters,
                result.posts_generated,
                result.posts_published,
                _dumps(result.errors),
                1 if result.dry_run else 0,
            ),
        )
        self.conn.commit()

    def recent_runs(self, days: float = 7, limit: int = 50) -> List[Dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT * FROM runs WHERE started_at >= ? ORDER BY started_at DESC LIMIT ?",
            (_cutoff(days), limit),
        ).fetchall()
        result = []
        for row in rows:
            data = dict(row)
            data["errors"] = _loads(data.get("errors"), [])
            result.append(data)
        return result

    # ------------------------------------------------------------------
    # Сводная статистика (для отчётов)
    # ------------------------------------------------------------------
    def channel_stats(self, channel_id: str, days: float = 7) -> Dict[str, Any]:
        posts = self.get_posts(channel_id, days=days)
        publishes = self.count_publishes(channel_id, days=days)
        last_run = self.conn.execute(
            "SELECT * FROM runs WHERE channel_id = ? ORDER BY started_at DESC LIMIT 1",
            (channel_id,),
        ).fetchone()
        formats: Dict[str, int] = {}
        total_chars = 0
        for post in posts:
            formats[post["format"]] = formats.get(post["format"], 0) + 1
            total_chars += len(post["text"])
        return {
            "channel_id": channel_id,
            "articles": self.count_articles(channel_id, days=days),
            "posts": len(posts),
            "formats": formats,
            "avg_post_chars": round(total_chars / len(posts), 1) if posts else 0.0,
            "publishes": publishes,
            "last_run": dict(last_run) if last_run else None,
            "latest_metrics": self.latest_metrics(channel_id),
        }

    def global_stats(self, days: float = 7) -> Dict[str, Any]:
        return {
            "days": days,
            "articles": self.count_articles(days=days),
            "posts": len(self.get_posts(days=days, limit=5000)),
            "publishes": self.count_publishes(days=days),
            "sources": self.article_sources(days=days),
            "runs": self.recent_runs(days=days),
        }
