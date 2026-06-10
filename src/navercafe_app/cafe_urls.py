from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse


@dataclass(frozen=True, slots=True)
class CafeUrlParts:
    cafe_slug: str = ""
    club_id: str = ""
    menu_id: str = ""
    article_id: str = ""


def parse_cafe_url(url: str) -> CafeUrlParts:
    """Parse common Naver Cafe URL shapes into cafe/article identifiers."""
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    parts = [p for p in parsed.path.split("/") if p]
    cafe_slug = parts[0] if parts else ""

    article_id = ""
    if len(parts) >= 2 and parts[1].isdigit():
        article_id = parts[1]
    if not article_id:
        for key in ("articleid", "articleId", "articleid_"):
            if query.get(key):
                article_id = query[key][0]
                break

    return CafeUrlParts(
        cafe_slug=cafe_slug,
        club_id=(query.get("clubid") or query.get("clubId") or [""])[0],
        menu_id=(query.get("menuid") or query.get("menuId") or [""])[0],
        article_id=article_id,
    )


def make_article_url(cafe_slug: str, article_id: str) -> str:
    return f"https://cafe.naver.com/{cafe_slug}/{article_id}"


def make_board_url(club_id: str, menu_id: str, page: int = 1) -> str:
    return (
        "https://cafe.naver.com/ArticleList.nhn"
        f"?search.clubid={club_id}&search.menuid={menu_id}&search.page={page}"
    )


def extract_article_id(text: str) -> str:
    match = re.search(r"/(\d+)(?:[?#]|$)", text) or re.search(r"articleid[=:/](\d+)", text, re.I)
    return match.group(1) if match else ""
