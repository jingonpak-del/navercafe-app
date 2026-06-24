from navercafe_app.models import ArticleListItem, Comment
from navercafe_app.storage.sqlite_store import SQLiteStore


def test_sqlite_store_upserts_article_and_comment(tmp_path):
    store = SQLiteStore(tmp_path / "daily.sqlite")
    store.upsert_cafe("123", "sample", "https://cafe.naver.com/sample", "샘플")
    store.upsert_board("123", "7", "자유", "")
    item = ArticleListItem(
        title="첫 글",
        url="https://cafe.naver.com/sample/100",
        article_id="100",
        author="작성자",
        written_at="2026.06.24",
        view_count=10,
        comment_count=2,
    )
    assert store.upsert_article_list_item("123", "7", item)
    assert "100" in store.get_last_seen_article_ids("123", "7")
    store.upsert_comment("123", "100", Comment(author="댓글러", text="댓글", written_at="2026.06.24"))
    assert store.count("cafes") == 1
    assert store.count("boards") == 1
    assert store.count("articles") == 1
    assert store.count("comments") == 1
    store.close()
