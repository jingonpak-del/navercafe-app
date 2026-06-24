"""Reusable helpers extracted from the 2026 Naver Cafe comment-master analysis.

The module intentionally contains read-only / preparation utilities only: target parsing,
work DB duplicate guards, comment-bank selection, board API URL builders, and new-post
baselines. Mutating operations such as posting comments, likes, view events, IP rotation,
or challenge bypass are not included.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable
from urllib.parse import urlencode

from navercafe_app.models import ArticleListItem

CAFE_GATE_INFO_URL = "https://apis.naver.com/cafe-web/cafe2/CafeGateInfo.json"
ARTICLE_LIST_V3_URL = "https://apis.naver.com/cafe-web/cafe2/ArticleListV3.json"


@dataclass(slots=True)
class CafeBoardTarget:
    cafe_slug: str
    menu_id: str
    extraction_limit: int | None = None
    raw: str = ""


@dataclass(slots=True)
class ArticleFilter:
    title_include: list[str] = field(default_factory=list)
    title_exclude: list[str] = field(default_factory=list)
    author_include: list[str] = field(default_factory=list)
    author_exclude: list[str] = field(default_factory=list)
    min_comment_count: int | None = None
    max_comment_count: int | None = None


@dataclass(slots=True)
class NewPost:
    target_key: str
    article: ArticleListItem
    baseline: int
    timestamp: int


def parse_cafe_board_targets(lines: Iterable[str]) -> list[CafeBoardTarget]:
    """Parse legacy `2. 작업 카페.txt` style lines.

    Supported columns are tab/comma/pipe separated. The first two fields are cafe slug/url
    and menu id; the optional third field is a per-board extraction limit.
    """
    targets: list[CafeBoardTarget] = []
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = _split_legacy_line(line)
        if len(parts) < 2:
            continue
        slug = normalize_cafe_slug(parts[0])
        limit = _parse_int(parts[2]) if len(parts) >= 3 else None
        targets.append(CafeBoardTarget(cafe_slug=slug, menu_id=parts[1].strip(), extraction_limit=limit, raw=raw_line.rstrip("\n")))
    return targets


def normalize_cafe_slug(value: str) -> str:
    value = value.strip().rstrip("/")
    if "cafe.naver.com/" in value:
        value = value.split("cafe.naver.com/", 1)[1]
    return value.split("/", 1)[0].split("?", 1)[0]


def cafe_gate_info_url(cafe_slug: str) -> str:
    return f"{CAFE_GATE_INFO_URL}?{urlencode({'cluburl': cafe_slug})}"


def article_list_v3_url(cafe_id: str, menu_id: str, *, page: int = 1, per_page: int = 15) -> str:
    params = {
        "search.clubid": cafe_id,
        "search.queryType": "lastArticle",
        "search.menuid": menu_id,
        "search.page": page,
        "search.perPage": per_page,
    }
    return f"{ARTICLE_LIST_V3_URL}?{urlencode(params)}"


def load_comment_bank(path: str | Path) -> list[str]:
    """Load a comment-bank file, converting legacy `$` markers into line breaks."""
    bank_path = Path(path)
    if not bank_path.exists():
        return []
    comments: list[str] = []
    for raw_line in bank_path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if line:
            comments.append(line.replace("$", "\n"))
    return comments


def select_comment_for_article(
    *,
    cafe_slug: str,
    article_id: str,
    article_comment_dir: str | Path,
    global_comments: list[str],
    randomize: bool = True,
) -> str | None:
    """Select article-specific comment text before falling back to the global bank."""
    specific_path = Path(article_comment_dir) / f"{cafe_slug}_{article_id}.txt"
    candidates = load_comment_bank(specific_path) or list(global_comments)
    if not candidates:
        return None
    return random.choice(candidates) if randomize else candidates[0]


class WorkDatabase:
    """Append-only duplicate guard compatible with legacy `작업DB.txt` files."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._items: set[str] | None = None

    def load(self) -> set[str]:
        if self._items is None:
            if not self.path.exists():
                self._items = set()
            else:
                self._items = {line.strip() for line in self.path.read_text(encoding="utf-8-sig").splitlines() if line.strip()}
        return self._items

    def contains(self, key: str) -> bool:
        return key in self.load()

    def mark(self, key: str) -> bool:
        """Append `key` if it is new. Returns True when a new key was written."""
        items = self.load()
        if key in items:
            return False
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fp:
            fp.write(f"{key}\n")
        items.add(key)
        return True


def filter_articles(items: Iterable[ArticleListItem], criteria: ArticleFilter, worked: WorkDatabase | None = None) -> list[ArticleListItem]:
    result: list[ArticleListItem] = []
    for item in items:
        if worked and worked.contains(item.url or item.article_id):
            continue
        if criteria.title_include and not any(token in item.title for token in criteria.title_include):
            continue
        if criteria.title_exclude and any(token in item.title for token in criteria.title_exclude):
            continue
        if criteria.author_include and not any(token in item.author for token in criteria.author_include):
            continue
        if criteria.author_exclude and any(token in item.author for token in criteria.author_exclude):
            continue
        if criteria.min_comment_count is not None and item.comment_count < criteria.min_comment_count:
            continue
        if criteria.max_comment_count is not None and item.comment_count > criteria.max_comment_count:
            continue
        result.append(item)
    return result


class NewPostTracker:
    """Per-board timestamp baseline tracker for new-post detection."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._state: dict[str, int] | None = None

    def load(self) -> dict[str, int]:
        if self._state is None:
            if not self.path.exists():
                self._state = {}
            else:
                raw = json.loads(self.path.read_text(encoding="utf-8") or "{}")
                self._state = {str(key): int(value) for key, value in raw.items() if _parse_int(value) is not None}
        return self._state

    def detect(self, target_key: str, items: Iterable[ArticleListItem]) -> list[NewPost]:
        baseline = self.load().get(target_key, 0)
        posts: list[NewPost] = []
        newest = baseline
        for item in items:
            timestamp = article_timestamp(item)
            if timestamp > newest:
                newest = timestamp
            if timestamp > baseline:
                posts.append(NewPost(target_key=target_key, article=item, baseline=baseline, timestamp=timestamp))
        if newest > baseline:
            self.load()[target_key] = newest
        return posts

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.load(), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def article_timestamp(item: ArticleListItem) -> int:
    value = item.written_at.strip()
    direct = _parse_int(value)
    if direct is not None:
        return direct
    for fmt in ("%Y.%m.%d. %H:%M", "%Y.%m.%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return int(datetime.strptime(value, fmt).timestamp() * 1000)
        except ValueError:
            continue
    return 0


def _split_legacy_line(line: str) -> list[str]:
    for delimiter in ("\t", "|", ","):
        if delimiter in line:
            return [part.strip() for part in line.split(delimiter)]
    return line.split()


def _parse_int(value: object) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None
