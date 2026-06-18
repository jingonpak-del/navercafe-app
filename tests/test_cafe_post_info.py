from naver_cafe_strategy.naver.cafe_post_info import (
    extract_counts_from_html,
    parse_cafe_article_url,
    save_metrics_csv,
)


def test_parse_cafe_article_url_path_style():
    cafe_slug, article_id = parse_cafe_article_url("https://cafe.naver.com/feko/10791546")

    assert cafe_slug == "feko"
    assert article_id == "10791546"


def test_parse_cafe_article_url_query_style():
    cafe_slug, article_id = parse_cafe_article_url(
        "https://cafe.naver.com/ArticleRead.nhn?clubid=123&articleid=987654"
    )

    assert cafe_slug == "ArticleRead.nhn"
    assert article_id == "987654"


def test_extract_counts_from_visible_text():
    text = """
    제목 샘플 게시글
    조회 1,234
    댓글 56
    좋아요 7
    """

    assert extract_counts_from_html("", text) == {"views": 1234, "comments": 56, "likes": 7}


def test_extract_counts_from_json_like_html():
    html = '''
    <script>
    window.__ARTICLE__ = {
      "readCount": 4321,
      "commentCount": 18,
      "sympathyCount": 9
    };
    </script>
    '''

    assert extract_counts_from_html(html) == {"views": 4321, "comments": 18, "likes": 9}


def test_save_metrics_csv(tmp_path):
    output = tmp_path / "metrics.csv"
    rows = [
        {
            "url": "https://cafe.naver.com/feko/10791546",
            "cafe_slug": "feko",
            "article_id": "10791546",
            "title": "테스트",
            "views": 1,
            "comments": 2,
            "likes": 3,
            "error": "",
        }
    ]

    saved = save_metrics_csv(rows, output)

    assert saved == output
    content = output.read_text(encoding="utf-8-sig")
    assert "views,comments,likes" in content
    assert "10791546" in content
