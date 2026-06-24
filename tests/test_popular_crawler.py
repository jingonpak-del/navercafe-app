from __future__ import annotations

import json

from navercafe_app.crawlers.popular import (
    PopularArticleRow,
    extract_cafe_id_from_popular_url,
    normalize_popular_url,
    to_article_list_items,
    write_popular_rows,
)


def test_extract_cafe_id_from_popular_url() -> None:
    assert extract_cafe_id_from_popular_url("https://cafe.naver.com/f-e/cafes/14793916/popular") == "14793916"
    assert extract_cafe_id_from_popular_url("https://cafe.naver.com/ca-fe/cafes/10912875/popular?p=2") == "10912875"


def test_normalize_popular_url() -> None:
    assert normalize_popular_url("14793916") == "https://cafe.naver.com/ca-fe/cafes/14793916/popular"
    assert (
        normalize_popular_url("https://cafe.naver.com/f-e/cafes/14793916/popular")
        == "https://cafe.naver.com/ca-fe/cafes/14793916/popular"
    )


def test_write_popular_rows(tmp_path) -> None:
    rows = [
        PopularArticleRow(
            cafe_id="14793916",
            page=1,
            rank_on_page=1,
            global_rank=1,
            article_id="123",
            title="테스트 제목",
            url="https://cafe.naver.com/ca-fe/cafes/14793916/articles/123?fromPopular=true",
            author="작성자",
            written_at="2026.06.24.",
            view_count=10,
            comment_count=2,
        )
    ]
    csv_path, json_path = write_popular_rows(rows, tmp_path)
    assert csv_path.exists()
    assert "테스트 제목" in csv_path.read_text(encoding="utf-8-sig")
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data[0]["article_id"] == "123"


def test_to_article_list_items() -> None:
    rows = [
        PopularArticleRow(
            cafe_id="14793916",
            page=1,
            rank_on_page=1,
            global_rank=1,
            article_id="123",
            title="테스트 제목",
            url="https://cafe.naver.com/ca-fe/cafes/14793916/articles/123?fromPopular=true",
            view_count=10,
            comment_count=2,
        )
    ]
    [item] = to_article_list_items(rows)
    assert item.article_id == "123"
    assert item.title == "테스트 제목"
    assert item.view_count == 10
