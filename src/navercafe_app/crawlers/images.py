from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

import requests
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from ..browser import cafe_main_frame
from ..models import ImageAsset
from ..parsers import extract_image_assets


class ImageCrawler:
    """Extract and optionally download image URLs from a Naver Cafe article."""

    def __init__(self, driver, timeout: int = 10):
        self.driver = driver
        self.timeout = timeout

    def collect(self, article_url: str) -> list[ImageAsset]:
        self.driver.get(article_url)
        WebDriverWait(self.driver, self.timeout).until(lambda d: d.find_elements(By.TAG_NAME, "body"))
        try:
            with cafe_main_frame(self.driver, self.timeout):
                html = self.driver.page_source
        except Exception:
            html = self.driver.page_source
        return extract_image_assets(html)


def download_image(url: str, output_dir: str | Path, filename: str | None = None, timeout: int = 20) -> Path:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    if not filename:
        filename = Path(urlparse(url).path).name or "image.bin"
    target = output / filename
    response = requests.get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
    response.raise_for_status()
    target.write_bytes(response.content)
    return target
