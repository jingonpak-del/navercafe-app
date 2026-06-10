from __future__ import annotations

import re
from urllib.parse import unquote, urlparse

from bs4 import BeautifulSoup

from .models import ArticleListItem, Comment, ImageAsset


def parse_int(text: str | None) -> int:
    if not text:
        return 0
    match = re.search(r"[0-9][0-9,]*", text)
    return int(match.group(0).replace(",", "")) if match else 0


def extract_title(soup: BeautifulSoup, fallback: str = "") -> str:
    selectors = [
        ".ArticleTitle .title_text",
        "h3.title",
        ".title_subject",
        "[class*='tit_h3']",
        "[class*='article'] h3",
        "h3",
    ]
    for selector in selectors:
        node = soup.select_one(selector)
        if node:
            text = node.get_text(" ", strip=True)
            if len(text) > 1:
                return text
    return fallback.replace(" : 네이버 카페", "").strip()


def extract_view_count(html: str) -> int:
    patterns = [
        r"조회\s*([0-9,]+)",
        r"읽음\s*([0-9,]+)",
        r"viewCount\D{0,20}([0-9,]+)",
        r'"readCount"\s*:\s*(\d+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, html, re.I)
        if match:
            return parse_int(match.group(1))
    return 0


def extract_comment_count(html: str) -> int:
    patterns = [r"댓글\s*([0-9,]+)", r"commentCount\D{0,20}([0-9,]+)"]
    for pattern in patterns:
        match = re.search(pattern, html, re.I)
        if match:
            return parse_int(match.group(1))
    return 0


def extract_body_text(soup: BeautifulSoup) -> str:
    selectors = [".se-main-container", ".ContentRenderer", "#tbody", ".article_viewer", "body"]
    for selector in selectors:
        node = soup.select_one(selector)
        if node:
            return node.get_text("\n", strip=True)
    return ""


def extract_image_assets(html: str) -> list[ImageAsset]:
    soup = BeautifulSoup(html, "html.parser")
    assets: list[ImageAsset] = []
    seen: set[str] = set()
    for img in soup.select("img"):
        url = img.get("data-src") or img.get("data-lazy-src") or img.get("src") or ""
        if not url or url.startswith("data:") or url in seen:
            continue
        seen.add(url)
        path = unquote(urlparse(url).path.rsplit("/", 1)[-1])
        assets.append(ImageAsset(url=url, filename=path))
    return assets


def parse_comments(html: str) -> list[Comment]:
    soup = BeautifulSoup(html, "html.parser")
    comments: list[Comment] = []
    for node in soup.select(".CommentItem, .comment_item, li[class*='Comment']"):
        text_node = node.select_one(".text_comment, .comment_text_box, [class*='comment_text']")
        if not text_node:
            continue
        author_node = node.select_one(".comment_nick_box, .nickname, [class*='nick']")
        date_node = node.select_one(".comment_info_date, .date, [class*='date']")
        classes = node.get("class") or []
        comments.append(
            Comment(
                author=author_node.get_text(" ", strip=True) if author_node else "",
                text=text_node.get_text(" ", strip=True),
                written_at=date_node.get_text(" ", strip=True) if date_node else "",
                is_reply="reply" in " ".join(classes).lower(),
            )
        )
    return comments


def parse_board_items(html: str, base_url: str = "https://cafe.naver.com") -> list[ArticleListItem]:
    soup = BeautifulSoup(html, "html.parser")
    items: list[ArticleListItem] = []
    for row in soup.select("tr, .article-board li, li[class*='article']"):
        link = row.select_one(
            "a.article, a[href*='/ArticleRead'], a[href*='articleid'], a[href*='cafe.naver.com']"
        )
        if not link:
            continue
        href = link.get("href", "")
        if href.startswith("/"):
            href = base_url + href
        title = link.get_text(" ", strip=True)
        if not title:
            continue
        row_text = row.get_text(" ", strip=True)
        items.append(
            ArticleListItem(
                title=title,
                url=href,
                view_count=extract_view_count(row_text),
                comment_count=extract_comment_count(row_text),
                is_notice="공지" in row_text[:20],
            )
        )
    return items
