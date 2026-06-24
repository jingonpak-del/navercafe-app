from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import requests

from navercafe_app.browser import build_driver

from .session_store import SessionStore

NAVER_HOME_URL = "https://www.naver.com/"
NAVER_MAIL_URL = "https://mail.naver.com/"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36"
)


@dataclass(slots=True)
class AuthState:
    logged_in: bool
    source: str
    message: str = ""


def load_env_file(path: str | os.PathLike[str] | None) -> dict[str, str]:
    """Load a simple dotenv file without adding a runtime dependency."""
    if not path:
        return {}
    env_path = Path(path)
    if not env_path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


def cookies_to_session(cookies: list[dict], user_agent: str = DEFAULT_USER_AGENT) -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        }
    )
    for cookie in cookies:
        session.cookies.set(
            cookie.get("name"),
            cookie.get("value", ""),
            domain=cookie.get("domain") or None,
            path=cookie.get("path") or "/",
        )
    return session


def apply_cookies_to_driver(driver, cookies: list[dict], domain_url: str = NAVER_HOME_URL) -> None:
    driver.get(domain_url)
    for cookie in cookies:
        selenium_cookie = {
            "name": cookie.get("name"),
            "value": cookie.get("value", ""),
            "path": cookie.get("path", "/"),
        }
        if cookie.get("domain"):
            selenium_cookie["domain"] = cookie["domain"]
        if cookie.get("expiry"):
            selenium_cookie["expiry"] = int(cookie["expiry"])
        try:
            driver.add_cookie(selenium_cookie)
        except Exception:
            # Some cookies are host-only or carry unsupported attributes. Ignore and keep loading the rest.
            continue


class NaverSessionManager:
    """Manage Naver login, persisted cookies, and requests/Selenium session reuse."""

    def __init__(
        self,
        env_path: str | os.PathLike[str] | None = ".env",
        session_store: SessionStore | None = None,
        driver_factory: Callable[..., object] = build_driver,
        login_func: Callable[[object, str, str], bool] | None = None,
        user_agent: str = DEFAULT_USER_AGENT,
    ):
        self.env_path = Path(env_path) if env_path else None
        self.env = {**load_env_file(self.env_path), **os.environ}
        self.username = self.env.get("NAVER_ID", "")
        self.password = self.env.get("NAVER_PW", "")
        session_key = self.env.get("NAVER_SESSION_KEY", "")
        self.session_store = session_store or SessionStore("data/session/naver_cookies.json", session_key)
        self.driver_factory = driver_factory
        self.login_func = login_func or self._default_login_func
        self.user_agent = user_agent

    def get_requests_session(self, force_login: bool = False, headless: bool = True) -> requests.Session:
        state = self.ensure_login(force_login=force_login, headless=headless)
        if not state.logged_in:
            raise RuntimeError(state.message or "Naver login failed")
        return cookies_to_session(self.session_store.load_cookies(), self.user_agent)

    def get_driver(self, headless: bool = True, with_login: bool = True):
        driver = self.driver_factory(headless=headless)
        if with_login:
            cookies = self.session_store.load_cookies()
            if cookies:
                apply_cookies_to_driver(driver, cookies)
                driver.get(NAVER_HOME_URL)
                time.sleep(1)
            if not cookies or not self.validate_driver_login(driver):
                state = self.ensure_login(force_login=True, headless=headless, existing_driver=driver)
                if not state.logged_in:
                    raise RuntimeError(state.message or "Naver driver login failed")
        return driver

    def ensure_login(self, force_login: bool = False, headless: bool = True, existing_driver=None) -> AuthState:
        if not force_login and self.session_store.is_available():
            cookies = self.session_store.load_cookies()
            if cookies:
                session = cookies_to_session(cookies, self.user_agent)
                if self.validate_session(session):
                    return AuthState(True, "cookie", "저장된 쿠키로 로그인 상태를 확인했습니다.")

        if not self.username or not self.password:
            return AuthState(False, "missing_credentials", "NAVER_ID/NAVER_PW가 .env 또는 환경변수에 없습니다.")

        driver = existing_driver or self.driver_factory(headless=headless)
        should_quit = existing_driver is None
        try:
            ok = self.login_func(driver, self.username, self.password)
            if not ok:
                return AuthState(False, "selenium", "Selenium 네이버 로그인에 실패했습니다. CAPTCHA/2FA/비밀번호를 확인하세요.")
            cookies = driver.get_cookies()
            self.session_store.save_cookies(cookies, username_hint=self.username)
            return AuthState(True, "selenium", "Selenium 로그인 후 쿠키를 저장했습니다.")
        finally:
            if should_quit:
                try:
                    driver.quit()
                except Exception:
                    pass

    def validate_session(self, session: requests.Session) -> bool:
        try:
            resp = session.get(NAVER_MAIL_URL, timeout=10, allow_redirects=True)
        except requests.RequestException:
            return False
        text = resp.text[:4000]
        current_url = resp.url.lower()
        if "nidlogin" in current_url or "로그인" in text and "id=" in text:
            return False
        if any(cookie.name in {"NID_AUT", "NID_SES"} for cookie in session.cookies):
            return resp.status_code < 500
        return False

    def validate_driver_login(self, driver) -> bool:
        try:
            driver.get(NAVER_HOME_URL)
            time.sleep(1)
            cookies = {cookie.get("name") for cookie in driver.get_cookies()}
            if {"NID_AUT", "NID_SES"} & cookies:
                return True
            page = driver.page_source[:5000]
            return "로그아웃" in page or "내정보" in page
        except Exception:
            return False

    @staticmethod
    def _default_login_func(driver, username: str, password: str) -> bool:
        from naver_cafe_strategy.auth.naver_login import naver_login

        return naver_login(driver, username, password)
