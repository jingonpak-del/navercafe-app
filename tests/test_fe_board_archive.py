from __future__ import annotations

from navercafe_app.crawlers.fe_board_archive import (
    BoardTarget,
    FeBoardListClient,
    extract_body_html,
    extract_detail_result,
    extract_image_urls,
    html_to_text,
    normalize_list_item,
    parse_board_url,
    sanitize_filename,
)


def test_parse_board_url() -> None:
    target = parse_board_url("https://cafe.naver.com/f-e/cafes/14793916/menus/1556?viewType=L")
    assert target.cafe_id == "14793916"
    assert target.menu_id == "1556"
    assert target.view_type == "L"


def test_sanitize_filename() -> None:
    assert sanitize_filename('a/b:c*?"<>| 제목') == "a_b_c_제목"
    assert sanitize_filename("   ") == "untitled"


def test_normalize_list_item() -> None:
    target = BoardTarget("14793916", "1556")
    item = normalize_list_item(
        target,
        {
            "articleId": 7385791,
            "subject": "이 집 사장님 미슐랭 별 숨겨놓은 거 아님?(26.03.18)",
            "writerInfo": {"nickName": "줌마렐라", "memberKey": "abc"},
            "writeDateTimestamp": 1768454117863,
            "readCount": 4274,
            "commentCount": 17,
            "representImage": "https://example.com/a.jpg",
            "hasImage": True,
            "readLevel": 110,
        },
    )
    assert item.article_id == "7385791"
    assert item.writer_nickname == "줌마렐라"
    assert item.has_image is True
    assert item.article_url.endswith("/articles/7385791?menuid=1556")


class FakeResponse:
    def __init__(self, payload: dict):
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self.payload


class FakeSession:
    def __init__(self, pages: dict[int, dict]):
        self.pages = pages
        self.calls: list[int] = []

    def get(self, url, params=None, headers=None, timeout=None):
        page = int(params["page"])
        self.calls.append(page)
        return FakeResponse(self.pages[page])


def test_iter_articles_uses_page_info_and_limit() -> None:
    pages = {
        1: {
            "result": {
                "articleList": [{"item": {"articleId": 1, "subject": "첫글"}}],
                "pageInfo": {"lastNavigationPageNumber": 2, "visibleNextButton": False},
            }
        },
        2: {
            "result": {
                "articleList": [{"item": {"articleId": 2, "subject": "둘째글"}}],
                "pageInfo": {"lastNavigationPageNumber": 2, "visibleNextButton": False},
            }
        },
    }
    client = FeBoardListClient(session=FakeSession(pages))
    rows = list(client.iter_articles(BoardTarget("14793916", "1556")))
    assert [row.article_id for row in rows] == ["1", "2"]


def test_detail_html_text_and_images() -> None:
    detail = extract_detail_result(
        {
            "result": {
                "article": {
                    "subject": "상세글",
                    "contentHtml": '<p>본문<br><img src="https://postfiles.pstatic.net/a.jpg?type=w966"></p>',
                    "contentElements": [{"url": "https://postfiles.pstatic.net/b.png"}],
                    "representImageUrl": "https://postfiles.pstatic.net/a.jpg?type=w966",
                },
                "attaches": [{"url": "https://cafefiles.pstatic.net/c.jpg"}],
            }
        }
    )
    assert extract_body_html(detail).startswith("<p>")
    assert "본문" in html_to_text(extract_body_html(detail))
    urls = extract_image_urls(detail)
    assert urls == [
        "https://postfiles.pstatic.net/a.jpg?type=w966",
        "https://postfiles.pstatic.net/b.png",
        "https://cafefiles.pstatic.net/c.jpg",
    ]
