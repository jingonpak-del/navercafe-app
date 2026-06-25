from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any
from urllib.parse import parse_qs, urlparse

import requests

from navercafe_app.auth.naver_session import DEFAULT_USER_AGENT
from navercafe_app.models import Comment
from navercafe_app.parsers import parse_int


@dataclass(frozen=True, slots=True)
class CommentApiResult:
    comments: list[Comment]
    source: str = ""
    ok: bool = False
    error: str = ""


def extract_cafe_and_article_ids(url: str, cafe_id_hint: str = "", article_id_hint: str = "") -> tuple[str, str]:
    """Extract Naver Cafe numeric cafe/article IDs from common desktop and /f-e URLs."""
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    path = parsed.path

    cafe_id = cafe_id_hint or (query.get("clubid") or query.get("clubId") or [""])[0]
    article_id = article_id_hint or (query.get("articleid") or query.get("articleId") or [""])[0]

    if not cafe_id:
        match = re.search(r"/cafes/(\d+)(?:/|$)", path, re.I)
        if match:
            cafe_id = match.group(1)
    if not article_id:
        match = re.search(r"/articles/(\d+)(?:[/?#]|$)", path, re.I)
        if match:
            article_id = match.group(1)
    if not article_id:
        match = re.search(r"/(\d+)(?:[/?#]|$)", path)
        if match:
            article_id = match.group(1)

    return cafe_id, article_id


class CommentApiClient:
    """Fetch Naver Cafe comments through web API endpoints before falling back to Selenium.

    Naver changes endpoint versions occasionally. The client tries known cafe-web comment API
    shapes and parses several JSON layouts so the rest of the crawler can prefer HTTP calls.
    """

    def __init__(self, session: requests.Session | None = None, timeout: int = 15):
        self.session = session or requests.Session()
        self.timeout = timeout
        self.session.headers.update(
            {
                "User-Agent": DEFAULT_USER_AGENT,
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
                "Referer": "https://cafe.naver.com/",
                "X-Requested-With": "XMLHttpRequest",
            }
        )

    def fetch(
        self,
        article_url: str,
        cafe_id: str = "",
        article_id: str = "",
        max_pages: int = 20,
    ) -> CommentApiResult:
        cafe_id, article_id = extract_cafe_and_article_ids(article_url, cafe_id, article_id)
        if not cafe_id or not article_id:
            return CommentApiResult([], ok=False, error="missing_cafe_or_article_id")

        comments: list[Comment] = []
        last_error = ""
        source = ""
        for endpoint in self._endpoint_candidates(cafe_id, article_id):
            endpoint_comments: list[Comment] = []
            for page in range(1, max_pages + 1):
                try:
                    resp = self.session.get(
                        endpoint.format(page=page),
                        params={"requestFrom": "A"},
                        timeout=self.timeout,
                    )
                    if resp.status_code in {401, 403, 404}:
                        last_error = f"http_{resp.status_code}"
                        break
                    resp.raise_for_status()
                    data = resp.json()
                except Exception as exc:
                    last_error = f"{type(exc).__name__}: {exc}"
                    break

                page_comments = comments_from_api_payload(data)
                if not page_comments:
                    if page == 1:
                        last_error = "empty_comments"
                    break
                endpoint_comments.extend(page_comments)
                if not _has_next_page(data, page):
                    break

            if endpoint_comments:
                comments = endpoint_comments
                source = endpoint
                break

        return CommentApiResult(comments, source=source, ok=bool(comments), error="" if comments else last_error)

    @staticmethod
    def _endpoint_candidates(cafe_id: str, article_id: str) -> list[str]:
        return [
            f"https://apis.naver.com/cafe-web/cafe-articleapi/v3/cafes/{cafe_id}/articles/{article_id}/comments/pages/{{page}}",
            f"https://apis.naver.com/cafe-web/cafe-articleapi/v2/cafes/{cafe_id}/articles/{article_id}/comments/pages/{{page}}",
            f"https://apis.naver.com/cafe-web/cafe-articleapi/cafes/{cafe_id}/articles/{article_id}/comments/pages/{{page}}",
        ]


def comments_from_api_payload(payload: Any) -> list[Comment]:
    """Parse comments from known and nested Naver Cafe API JSON payloads."""
    candidates: list[dict[str, Any]] = []
    _collect_comment_dicts(payload, candidates)

    comments: list[Comment] = []
    seen: set[tuple[str, str, str]] = set()
    for item in candidates:
        text = _first_text(item, "content", "text", "comment", "commentText", "body")
        if not text:
            continue
        author = _author_from_item(item)
        written_at = _first_text(item, "createdAt", "createDate", "regDate", "writtenAt", "date", "updateDate")
        is_reply = bool(
            item.get("parentCommentId")
            or item.get("refCommentId")
            or item.get("reply")
            or item.get("isReply")
            or item.get("isRef")
            or (item.get("refId") and item.get("id") and item.get("refId") != item.get("id"))
        )
        key = (author, text, written_at)
        if key in seen:
            continue
        seen.add(key)
        comments.append(Comment(author=author, text=text, written_at=written_at, is_reply=is_reply))
    return comments


def _collect_comment_dicts(value: Any, out: list[dict[str, Any]]) -> None:
    if isinstance(value, dict):
        keys = {str(k) for k in value}
        if {"content", "text", "comment", "commentText"} & keys and (
            {"writer", "author", "user", "member", "nickName", "nickname"} & keys
        ):
            out.append(value)
        for child in value.values():
            _collect_comment_dicts(child, out)
    elif isinstance(value, list):
        for child in value:
            _collect_comment_dicts(child, out)


def _first_text(item: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = item.get(key)
        if value is None:
            continue
        if isinstance(value, str):
            return _clean_text(value)
        if isinstance(value, (int, float)):
            return str(value)
    return ""


def _author_from_item(item: dict[str, Any]) -> str:
    for key in ("writer", "author", "user", "member"):
        value = item.get(key)
        if isinstance(value, dict):
            found = _first_text(value, "nick", "nickName", "nickname", "name", "id", "memberId")
            if found:
                return found
        elif isinstance(value, str) and value.strip():
            return _clean_text(value)
    return _first_text(item, "nick", "nickName", "nickname", "writerNick", "userName", "memberId")


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _has_next_page(payload: Any, current_page: int) -> bool:
    if not isinstance(payload, dict):
        return False
    if "hasNext" in payload:
        return bool(payload.get("hasNext"))
    for key in ("totalPages", "lastPage", "pageCount"):
        if key in payload:
            return current_page < parse_int(str(payload.get(key)))
    # Nested page metadata is common; inspect one level recursively.
    for value in payload.values():
        if isinstance(value, dict) and _has_next_page(value, current_page):
            return True
    # When page metadata is missing, stop after the first non-empty page to avoid needless calls.
    return False
