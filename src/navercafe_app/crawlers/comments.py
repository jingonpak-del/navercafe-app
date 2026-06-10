from __future__ import annotations

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from ..browser import cafe_main_frame
from ..models import Comment
from ..parsers import parse_comments


class CommentCrawler:
    """Collect visible comments from a Naver Cafe article."""

    def __init__(self, driver, timeout: int = 10):
        self.driver = driver
        self.timeout = timeout

    def crawl(self, article_url: str) -> list[Comment]:
        self.driver.get(article_url)
        WebDriverWait(self.driver, self.timeout).until(lambda d: d.find_elements(By.TAG_NAME, "body"))
        try:
            with cafe_main_frame(self.driver, self.timeout):
                html = self.driver.page_source
        except Exception:
            html = self.driver.page_source
        return parse_comments(html)
