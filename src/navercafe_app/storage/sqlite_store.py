from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from navercafe_app.models import Article, ArticleListItem, Comment


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class CrawlRunSummary:
    run_id: int
    started_at: str
    finished_at: str = ""
    status: str = "running"
    target_summary: str = ""
    error: str = ""


class SQLiteStore:
    """SQLite persistence for daily Naver Cafe article/comment snapshots."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.init_schema()

    def close(self) -> None:
        self.conn.close()

    def init_schema(self) -> None:
        self.conn.executescript(
            """
            create table if not exists cafes(
                cafe_id text primary key,
                cafe_slug text,
                cafe_url text,
                name text,
                created_at text not null
            );
            create table if not exists boards(
                id integer primary key autoincrement,
                cafe_id text not null,
                menu_id text not null,
                name text,
                board_url text,
                created_at text not null,
                unique(cafe_id, menu_id)
            );
            create table if not exists articles(
                id integer primary key autoincrement,
                cafe_id text not null,
                menu_id text not null,
                article_id text not null,
                url text,
                title text,
                author text,
                written_at text,
                body_text text,
                view_count integer default 0,
                comment_count integer default 0,
                raw_json text,
                first_seen_at text not null,
                last_seen_at text not null,
                unique(cafe_id, article_id)
            );
            create table if not exists comments(
                id integer primary key autoincrement,
                cafe_id text not null,
                article_id text not null,
                comment_id text not null,
                parent_comment_id text,
                author text,
                text text,
                written_at text,
                is_reply integer default 0,
                raw_json text,
                first_seen_at text not null,
                unique(cafe_id, article_id, comment_id)
            );
            create table if not exists crawl_runs(
                id integer primary key autoincrement,
                started_at text not null,
                finished_at text,
                status text not null,
                target_summary text,
                error text
            );
            """
        )
        self.conn.commit()

    def upsert_cafe(self, cafe_id: str, cafe_slug: str = "", cafe_url: str = "", name: str = "") -> None:
        now = utc_now()
        self.conn.execute(
            """
            insert into cafes(cafe_id, cafe_slug, cafe_url, name, created_at)
            values(?, ?, ?, ?, ?)
            on conflict(cafe_id) do update set
                cafe_slug=excluded.cafe_slug,
                cafe_url=excluded.cafe_url,
                name=excluded.name
            """,
            (cafe_id, cafe_slug, cafe_url, name, now),
        )
        self.conn.commit()

    def upsert_board(self, cafe_id: str, menu_id: str, name: str = "", board_url: str = "") -> None:
        now = utc_now()
        self.conn.execute(
            """
            insert into boards(cafe_id, menu_id, name, board_url, created_at)
            values(?, ?, ?, ?, ?)
            on conflict(cafe_id, menu_id) do update set
                name=excluded.name,
                board_url=excluded.board_url
            """,
            (cafe_id, menu_id, name, board_url, now),
        )
        self.conn.commit()

    def upsert_article_list_item(self, cafe_id: str, menu_id: str, item: ArticleListItem) -> bool:
        article_id = item.article_id or _article_id_from_url(item.url)
        return self.upsert_article(
            cafe_id=cafe_id,
            menu_id=menu_id,
            article_id=article_id,
            url=item.url,
            title=item.title,
            author=item.author,
            written_at=item.written_at,
            view_count=item.view_count,
            comment_count=item.comment_count,
            raw={"is_notice": item.is_notice},
        )

    def upsert_article(
        self,
        cafe_id: str,
        menu_id: str,
        article_id: str,
        url: str = "",
        title: str = "",
        author: str = "",
        written_at: str = "",
        body_text: str = "",
        view_count: int = 0,
        comment_count: int = 0,
        raw: dict[str, Any] | None = None,
    ) -> bool:
        if not article_id:
            raise ValueError("article_id is required")
        now = utc_now()
        before = self.conn.total_changes
        self.conn.execute(
            """
            insert into articles(
                cafe_id, menu_id, article_id, url, title, author, written_at, body_text,
                view_count, comment_count, raw_json, first_seen_at, last_seen_at
            ) values(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(cafe_id, article_id) do update set
                menu_id=excluded.menu_id,
                url=coalesce(nullif(excluded.url, ''), articles.url),
                title=coalesce(nullif(excluded.title, ''), articles.title),
                author=coalesce(nullif(excluded.author, ''), articles.author),
                written_at=coalesce(nullif(excluded.written_at, ''), articles.written_at),
                body_text=coalesce(nullif(excluded.body_text, ''), articles.body_text),
                view_count=excluded.view_count,
                comment_count=excluded.comment_count,
                raw_json=excluded.raw_json,
                last_seen_at=excluded.last_seen_at
            """,
            (
                cafe_id,
                menu_id,
                article_id,
                url,
                title,
                author,
                written_at,
                body_text,
                int(view_count or 0),
                int(comment_count or 0),
                json.dumps(raw or {}, ensure_ascii=False),
                now,
                now,
            ),
        )
        self.conn.commit()
        return self.conn.total_changes > before

    def upsert_article_detail(self, cafe_id: str, menu_id: str, article_id: str, article: Article) -> bool:
        return self.upsert_article(
            cafe_id=cafe_id,
            menu_id=menu_id,
            article_id=article_id,
            url=article.url,
            title=article.title,
            author=article.author,
            written_at=article.written_at,
            body_text=article.body_text,
            view_count=article.view_count,
            comment_count=article.comment_count,
            raw={**article.raw, "images": article.images},
        )

    def upsert_comment(self, cafe_id: str, article_id: str, comment: Comment, comment_id: str | None = None) -> bool:
        cid = comment_id or _stable_comment_id(comment)
        now = utc_now()
        before = self.conn.total_changes
        self.conn.execute(
            """
            insert into comments(
                cafe_id, article_id, comment_id, parent_comment_id, author, text, written_at,
                is_reply, raw_json, first_seen_at
            ) values(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(cafe_id, article_id, comment_id) do update set
                author=excluded.author,
                text=excluded.text,
                written_at=excluded.written_at,
                is_reply=excluded.is_reply,
                raw_json=excluded.raw_json
            """,
            (
                cafe_id,
                article_id,
                cid,
                "",
                comment.author,
                comment.text,
                comment.written_at,
                1 if comment.is_reply else 0,
                json.dumps(_to_dict(comment), ensure_ascii=False),
                now,
            ),
        )
        self.conn.commit()
        return self.conn.total_changes > before

    def get_last_seen_article_ids(self, cafe_id: str, menu_id: str, limit: int = 200) -> set[str]:
        rows = self.conn.execute(
            """
            select article_id from articles
            where cafe_id=? and menu_id=?
            order by first_seen_at desc
            limit ?
            """,
            (cafe_id, menu_id, limit),
        ).fetchall()
        return {str(row["article_id"]) for row in rows}

    def start_run(self, target_summary: str = "") -> CrawlRunSummary:
        started = utc_now()
        cur = self.conn.execute(
            "insert into crawl_runs(started_at, status, target_summary, error) values(?, ?, ?, ?)",
            (started, "running", target_summary, ""),
        )
        self.conn.commit()
        return CrawlRunSummary(run_id=int(cur.lastrowid), started_at=started, target_summary=target_summary)

    def finish_run(self, run_id: int, status: str = "success", error: str = "") -> None:
        self.conn.execute(
            "update crawl_runs set finished_at=?, status=?, error=? where id=?",
            (utc_now(), status, error, run_id),
        )
        self.conn.commit()

    def count(self, table: str) -> int:
        if table not in {"cafes", "boards", "articles", "comments", "crawl_runs"}:
            raise ValueError(f"Unsupported table: {table}")
        return int(self.conn.execute(f"select count(*) from {table}").fetchone()[0])


def _to_dict(value: Any) -> dict[str, Any]:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, dict):
        return value
    return {"value": str(value)}


def _stable_comment_id(comment: Comment) -> str:
    import hashlib

    key = "|".join([comment.author, comment.written_at, comment.text, "1" if comment.is_reply else "0"])
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:20]


def _article_id_from_url(url: str) -> str:
    from navercafe_app.cafe_urls import extract_article_id

    return extract_article_id(url)
