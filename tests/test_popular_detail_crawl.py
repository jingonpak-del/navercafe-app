from __future__ import annotations

import csv
import json

from navercafe_app.cli.popular_detail_crawl import _crawl_comments, _read_source_rows, _status_from_body, _to_comment_rows
from navercafe_app.models import Comment


def test_read_source_rows_json(tmp_path) -> None:
    path = tmp_path / "rows.json"
    path.write_text(json.dumps([{"cafe_id": 14793916, "title": "테스트"}], ensure_ascii=False), encoding="utf-8")
    rows = _read_source_rows(path)
    assert rows == [{"cafe_id": "14793916", "title": "테스트"}]


def test_read_source_rows_csv_utf8_sig(tmp_path) -> None:
    path = tmp_path / "rows.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["cafe_id", "title"])
        writer.writeheader()
        writer.writerow({"cafe_id": "14793916", "title": "한글 제목"})
    rows = _read_source_rows(path)
    assert rows[0]["title"] == "한글 제목"


def test_status_from_body() -> None:
    assert _status_from_body("제목", "본문이 충분히 길어서 공개글로 판단할 수 있습니다.") == "public_detail_ok"
    assert _status_from_body("네이버 카페", "") == "detail_unavailable"
    assert _status_from_body("제목", "멤버만 볼 수 있습니다") == "login_or_member_required"


def test_to_comment_rows() -> None:
    rows = _to_comment_rows(
        {"cafe_id": "14793916", "article_id": "123", "url": "https://example.com", "list_title": "글"},
        [Comment(author="댓글작성자", text="댓글내용", written_at="오늘", is_reply=False)],
    )

    assert rows[0].author == "댓글작성자"
    assert rows[0].text == "댓글내용"
    assert rows[0].comment_index == 1


def test_crawl_comments_prefers_api() -> None:
    class FakeApi:
        def fetch(self, article_url, cafe_id="", article_id=""):
            return type(
                "Result",
                (),
                {"ok": True, "comments": [Comment(author="API작성자", text="API댓글")], "error": ""},
            )()

    class FakeSelenium:
        def crawl(self, article_url):  # pragma: no cover - should not be used
            raise AssertionError("selenium fallback should not run")

    comments, source, error = _crawl_comments(
        "https://example.com",
        cafe_id="1",
        article_id="2",
        article_comment_count=1,
        api_client=FakeApi(),
        selenium_crawler=FakeSelenium(),
    )

    assert source == "api"
    assert error == ""
    assert comments[0].author == "API작성자"
