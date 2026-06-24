from __future__ import annotations

from navercafe_app.models import ArticleListItem
from navercafe_app.reusable.comment_master import (
    ArticleFilter,
    NewPostTracker,
    WorkDatabase,
    article_list_v3_url,
    cafe_gate_info_url,
    filter_articles,
    load_comment_bank,
    normalize_cafe_slug,
    parse_cafe_board_targets,
    select_comment_for_article,
)


def test_parse_cafe_board_targets_from_legacy_lines() -> None:
    targets = parse_cafe_board_targets([
        "https://cafe.naver.com/mycafe\t12\t30",
        "othercafe|99",
        "# comment",
        "bad_line",
    ])

    assert [(target.cafe_slug, target.menu_id, target.extraction_limit) for target in targets] == [
        ("mycafe", "12", 30),
        ("othercafe", "99", None),
    ]


def test_url_builders_encode_expected_parameters() -> None:
    assert cafe_gate_info_url("abc") == "https://apis.naver.com/cafe-web/cafe2/CafeGateInfo.json?cluburl=abc"
    url = article_list_v3_url("123", "456", page=2, per_page=50)
    assert "ArticleListV3.json" in url
    assert "search.clubid=123" in url
    assert "search.menuid=456" in url
    assert "search.page=2" in url
    assert "search.perPage=50" in url


def test_comment_bank_article_specific_fallback(tmp_path) -> None:
    comment_dir = tmp_path / "댓글원고"
    comment_dir.mkdir()
    (comment_dir / "mycafe_10.txt").write_text("첫줄$둘째줄\n", encoding="utf-8")

    assert load_comment_bank(comment_dir / "mycafe_10.txt") == ["첫줄\n둘째줄"]
    assert select_comment_for_article(
        cafe_slug="mycafe",
        article_id="10",
        article_comment_dir=comment_dir,
        global_comments=["전역"],
        randomize=False,
    ) == "첫줄\n둘째줄"
    assert select_comment_for_article(
        cafe_slug="mycafe",
        article_id="11",
        article_comment_dir=comment_dir,
        global_comments=["전역"],
        randomize=False,
    ) == "전역"


def test_work_database_and_filter_articles(tmp_path) -> None:
    db = WorkDatabase(tmp_path / "작업DB.txt")
    assert db.mark("https://cafe.naver.com/a/1") is True
    assert db.mark("https://cafe.naver.com/a/1") is False

    items = [
        ArticleListItem(title="좋은 후기", url="https://cafe.naver.com/a/1", article_id="1", author="nick", comment_count=1),
        ArticleListItem(title="질문 글", url="https://cafe.naver.com/a/2", article_id="2", author="user", comment_count=3),
        ArticleListItem(title="광고 글", url="https://cafe.naver.com/a/3", article_id="3", author="seller", comment_count=0),
    ]
    filtered = filter_articles(
        items,
        ArticleFilter(title_exclude=["광고"], author_exclude=["seller"], min_comment_count=2),
        worked=db,
    )

    assert [item.article_id for item in filtered] == ["2"]


def test_new_post_tracker_detects_and_persists_baseline(tmp_path) -> None:
    tracker = NewPostTracker(tmp_path / "new_posts.json")
    items = [
        ArticleListItem(title="old", url="u1", article_id="1", written_at="1000"),
        ArticleListItem(title="new", url="u2", article_id="2", written_at="2000"),
    ]

    first = tracker.detect("mycafe_12", items)
    assert [post.article.article_id for post in first] == ["1", "2"]
    tracker.save()

    tracker2 = NewPostTracker(tmp_path / "new_posts.json")
    second = tracker2.detect("mycafe_12", items)
    assert second == []


def test_normalize_cafe_slug() -> None:
    assert normalize_cafe_slug("https://cafe.naver.com/mycafe/123?x=1") == "mycafe"
    assert normalize_cafe_slug("mycafe") == "mycafe"
