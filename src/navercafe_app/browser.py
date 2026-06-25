from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import tempfile
from typing import Iterator

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


def build_driver(
    headless: bool = True,
    disable_images: bool = True,
    timeout: int = 30,
    user_data_dir: str | None = None,
) -> webdriver.Chrome:
    """Build a Chrome WebDriver configured for Naver Cafe crawling.

    Selenium 4.6+ Selenium Manager resolves the ChromeDriver binary automatically.
    For login-required cafes, use ``headless=False`` and complete login manually.
    Pass ``user_data_dir`` for a persistent manual-login profile; otherwise a temporary profile
    is used to avoid profile lock conflicts.
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
    profile_dir = user_data_dir or tempfile.mkdtemp(prefix="navercafe_chrome_")
    Path(profile_dir).mkdir(parents=True, exist_ok=True)
    opts.add_argument(f"--user-data-dir={profile_dir}")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    if disable_images:
        opts.add_experimental_option("prefs", {"profile.managed_default_content_settings.images": 2})
    opts.page_load_strategy = "eager"

    driver = webdriver.Chrome(options=opts)
    _apply_driver_timeouts(driver, timeout)
    try:
        driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"},
        )
    except Exception:
        pass
    return driver


def build_undetected_driver(
    headless: bool = False,
    disable_images: bool = False,
    timeout: int = 30,
    user_data_dir: str | None = None,
) -> webdriver.Chrome:
    """Build an optional undetected-chromedriver instance for manual Naver login renewal.

    This mirrors the user's older hotdeal crawler pattern but remains a normal user-visible
    login flow: CAPTCHA/2FA/security challenges are still handled manually by the account owner.
    """
    try:
        import undetected_chromedriver as uc
    except ImportError as exc:
        raise RuntimeError(
            "NAVER_LOGIN_DRIVER=undetected requires optional dependency 'undetected-chromedriver'. "
            "Install with: uv pip install undetected-chromedriver pyperclip curl-cffi"
        ) from exc

    opts = uc.ChromeOptions()
    if headless:
        opts.add_argument("--headless=new")
        opts.add_argument("--window-size=1920,1080")
    opts.add_argument("--lang=ko-KR")
    opts.add_argument("--disable-notifications")
    if user_data_dir:
        Path(user_data_dir).mkdir(parents=True, exist_ok=True)
        opts.add_argument(f"--user-data-dir={user_data_dir}")
    if disable_images:
        opts.add_experimental_option("prefs", {"profile.managed_default_content_settings.images": 2})

    kwargs = {"options": opts}
    chrome_major = _get_chrome_major_version()
    if chrome_major:
        kwargs["version_main"] = chrome_major
    driver = uc.Chrome(**kwargs)
    _apply_driver_timeouts(driver, timeout)
    return driver


def build_login_driver(
    *,
    mode: str = "selenium",
    headless: bool = False,
    disable_images: bool = False,
    timeout: int = 30,
    user_data_dir: str | None = None,
):
    mode = (mode or "selenium").lower()
    if mode in {"undetected", "uc", "undetected_chromedriver"}:
        return build_undetected_driver(
            headless=headless,
            disable_images=disable_images,
            timeout=timeout,
            user_data_dir=user_data_dir,
        )
    if mode != "selenium":
        raise ValueError(f"Unsupported login driver mode: {mode}")
    return build_driver(
        headless=headless,
        disable_images=disable_images,
        timeout=timeout,
        user_data_dir=user_data_dir,
    )


def _apply_driver_timeouts(driver, timeout: int) -> None:
    driver.set_page_load_timeout(timeout)
    driver.set_script_timeout(max(10, timeout - 10))


def _get_chrome_major_version() -> int | None:
    try:
        import re
        import subprocess

        keys = [
            r"HKEY_CURRENT_USER\Software\Google\Chrome\BLBeacon",
            r"HKEY_LOCAL_MACHINE\SOFTWARE\Google\Chrome\BLBeacon",
            r"HKEY_LOCAL_MACHINE\SOFTWARE\WOW6432Node\Google\Chrome\BLBeacon",
        ]
        for key in keys:
            result = subprocess.run(
                ["reg", "query", key, "/v", "version"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            match = re.search(r"(\d+)\.\d+\.\d+\.\d+", result.stdout)
            if match:
                return int(match.group(1))
    except Exception:
        return None
    return None


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
