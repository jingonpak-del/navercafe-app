from __future__ import annotations

from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from ..browser import cafe_main_frame
from ..models import Article
from ..parsers import (
    extract_body_text,
    extract_comment_count,
    extract_image_assets,
    extract_title,
    extract_view_count,
)


class ArticleCrawler:
    """Crawl a single Naver Cafe article page."""

    def __init__(self, driver, timeout: int = 10):
        self.driver = driver
        self.timeout = timeout

    def crawl(self, url: str) -> Article:
        self.driver.get(url)
        WebDriverWait(self.driver, self.timeout).until(lambda d: d.find_elements(By.TAG_NAME, "body"))
        html = ""
        title_fallback = self.driver.title or ""
        try:
            with cafe_main_frame(self.driver, self.timeout):
                WebDriverWait(self.driver, self.timeout).until(
                    lambda d: d.find_elements(By.CSS_SELECTOR, "body")
                )
                html = self.driver.page_source
        except Exception:
            html = self.driver.page_source

        soup = BeautifulSoup(html, "html.parser")
        images = [asset.url for asset in extract_image_assets(html)]
        return Article(
            url=url,
            title=extract_title(soup, fallback=title_fallback) or "(제목 미확인)",
            body_text=extract_body_text(soup),
            view_count=extract_view_count(html),
            comment_count=extract_comment_count(html),
            images=images,
            raw={"html_length": len(html)},
        )
