from __future__ import annotations

from contextlib import contextmanager
import tempfile
from typing import Iterator

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


def build_driver(headless: bool = True, disable_images: bool = True, timeout: int = 30) -> webdriver.Chrome:
    """Build a Chrome WebDriver configured for Naver Cafe crawling.

    Selenium 4.6+ Selenium Manager resolves the ChromeDriver binary automatically.
    For login-required cafes, use ``headless=False`` and complete login manually.
    """
    opts = Options()
    if headless:
        opts.add_argument("--headless=new")
        opts.add_argument("--window-size=1920,1080")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("--disable-extensions")
    opts.add_argument("--disable-notifications")
    opts.add_argument("--no-first-run")
    opts.add_argument("--lang=ko-KR")
    opts.add_argument(f"--user-data-dir={tempfile.mkdtemp(prefix='navercafe_chrome_')}")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    if disable_images:
        opts.add_experimental_option("prefs", {"profile.managed_default_content_settings.images": 2})
    opts.page_load_strategy = "eager"

    driver = webdriver.Chrome(options=opts)
    driver.set_page_load_timeout(timeout)
    driver.set_script_timeout(max(10, timeout - 10))
    return driver


@contextmanager
def cafe_main_frame(driver: webdriver.Chrome, timeout: int = 10) -> Iterator[None]:
    """Switch into Naver Cafe's ``#cafe_main`` iframe and always switch back."""
    WebDriverWait(driver, timeout).until(
        EC.frame_to_be_available_and_switch_to_it((By.ID, "cafe_main"))
    )
    try:
        yield
    finally:
        driver.switch_to.default_content()
