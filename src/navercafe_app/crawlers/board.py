from __future__ import annotations

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from ..browser import cafe_main_frame
from ..cafe_urls import make_board_url
from ..models import ArticleListItem
from ..parsers import parse_board_items


class BoardCrawler:
    """Crawl article list pages by club/menu/page."""

    def __init__(self, driver, timeout: int = 10):
        self.driver = driver
        self.timeout = timeout

    def crawl_page(
        self, club_id: str, menu_id: str, page: int = 1, include_notices: bool = False
    ) -> list[ArticleListItem]:
        url = make_board_url(club_id, menu_id, page)
        return self.crawl_url(url, include_notices=include_notices)

    def crawl_url(self, url: str, include_notices: bool = False) -> list[ArticleListItem]:
        """Crawl a rendered Naver Cafe list URL, including f-e special pages such as popular."""
        self.driver.get(url)
        WebDriverWait(self.driver, self.timeout).until(lambda d: d.find_elements(By.TAG_NAME, "body"))
        try:
            with cafe_main_frame(self.driver, self.timeout):
                html = self.driver.page_source
        except Exception:
            html = self.driver.page_source
        items = parse_board_items(html)
        if not include_notices:
            items = [item for item in items if not item.is_notice]
        return items

    def crawl_pages(self, club_id: str, menu_id: str, start_page: int, end_page: int) -> list[ArticleListItem]:
        result: list[ArticleListItem] = []
        for page in range(start_page, end_page + 1):
            result.extend(self.crawl_page(club_id, menu_id, page))
        return result
