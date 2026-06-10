from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


@dataclass(slots=True)
class Article:
    url: str
    title: str = ""
    body_text: str = ""
    author: str = ""
    written_at: str = ""
    view_count: int = 0
    comment_count: int = 0
    images: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ArticleListItem:
    title: str
    url: str
    article_id: str = ""
    author: str = ""
    written_at: str = ""
    view_count: int = 0
    comment_count: int = 0
    is_notice: bool = False


@dataclass(slots=True)
class Comment:
    author: str = ""
    text: str = ""
    written_at: str = ""
    is_reply: bool = False


@dataclass(slots=True)
class ImageAsset:
    url: str
    filename: str = ""
    content_type: str = ""


@dataclass(slots=True)
class AttendanceResult:
    member_id: str
    active_dates: set[date]

    def active_count(self) -> int:
        return len(self.active_dates)

    def to_sorted_strings(self) -> list[str]:
        return [d.isoformat() for d in sorted(self.active_dates)]
