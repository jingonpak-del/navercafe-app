from navercafe_app.cli.daily_crawl import DailyCrawler
from navercafe_app.config.targets import parse_targets
from navercafe_app.models import Article, ArticleListItem, Comment
from navercafe_app.storage.sqlite_store import SQLiteStore


class FakeBoardCrawler:
    def __init__(self, driver):
        self.driver = driver

    def crawl_page(self, club_id, menu_id, page=1, include_notices=False):
        if page > 1:
            return []
        return [
            ArticleListItem(
                title="신규 글",
                url="https://cafe.naver.com/sample/100",
                article_id="100",
                author="목록작성자",
                comment_count=1,
            )
        ]


class FakeArticleCrawler:
    def __init__(self, driver):
        self.driver = driver

    def crawl(self, url):
        return Article(url=url, title="상세 제목", body_text="본문", view_count=3, comment_count=1)


class FakeCommentCrawler:
    def __init__(self, driver):
        self.driver = driver

    def crawl(self, url):
        return [Comment(author="댓글러", text="좋아요", written_at="2026.06.24")]


def test_daily_crawler_collects_new_articles_comments_and_exports(tmp_path):
    targets = parse_targets(
        {
            "defaults": {"max_pages_per_board": 1, "include_comments": True, "delay_seconds": {"min": 0, "max": 0}},
            "targets": [
                {
                    "name": "샘플",
                    "cafe_url": "https://cafe.naver.com/sample",
                    "cafe_id": "123",
                    "boards": [{"name": "자유", "menu_id": "7"}],
                }
            ],
        }
    )
    store = SQLiteStore(tmp_path / "daily.sqlite")
    crawler = DailyCrawler(
        store,
        driver=object(),
        board_crawler_factory=FakeBoardCrawler,
        article_crawler_factory=FakeArticleCrawler,
        comment_crawler_factory=FakeCommentCrawler,
    )
    result = crawler.crawl(targets, export_dir=tmp_path / "export")
    assert result.new_articles == 1
    assert result.detail_articles == 1
    assert result.comments == 1
    assert store.count("articles") == 1
    assert store.count("comments") == 1
    assert (tmp_path / "export" / "daily_articles.csv").exists()
    store.close()
