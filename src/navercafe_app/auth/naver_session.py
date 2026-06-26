from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal

import requests

from navercafe_app.browser import build_driver, build_login_driver

from .session_store import SessionStore

NAVER_HOME_URL = "https://www.naver.com/"
NAVER_MAIL_URL = "https://mail.naver.com/"
NAVER_MAIL_INIT_DATA_URL = "https://mail.naver.com/json/initData"
NAVER_CAFE_MY_LIST_URL = "https://apis.naver.com/cafe-web/cafe2/CafeMyCafeList.json"
DEFAULT_CHROME_MAJOR = 131
DEFAULT_USER_AGENT = (
    f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    f"AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{DEFAULT_CHROME_MAJOR}.0.0.0 Safari/537.36"
)


@dataclass(slots=True)
class AuthState:
    logged_in: bool
    source: str
    message: str = ""


SessionValidationStatus = Literal["valid", "expired", "challenge", "unknown"]


@dataclass(slots=True)
class SessionValidationResult:
    status: SessionValidationStatus
    message: str = ""

    @property
    def is_valid(self) -> bool:
        return self.status == "valid"


def validate_naver_mail_session(session: requests.Session, timeout: int = 10) -> SessionValidationResult:
    """Validate Naver cookies through the same mail initData family observed in legacy apps."""
    try:
        resp = session.post(NAVER_MAIL_INIT_DATA_URL, timeout=timeout, allow_redirects=True)
    except requests.RequestException as exc:
        return SessionValidationResult("unknown", f"mail initData 요청 실패: {exc}")

    text = resp.text[:4000]
    current_url = resp.url.lower()
    if "nidlogin" in current_url or "로그인" in text and "id=" in text:
        return SessionValidationResult("expired", "로그인 페이지로 리다이렉트되었습니다.")
    if any(marker in text for marker in ("captcha", "보호조치", "본인확인", "인증")):
        return SessionValidationResult("challenge", "인증/보호조치 응답이 감지되었습니다.")

    try:
        payload = resp.json()
    except ValueError:
        payload = None
    if isinstance(payload, dict):
        if payload.get("userIdNo") or payload.get("userId") or payload.get("email"):
            return SessionValidationResult("valid", "mail initData 응답에서 로그인 사용자를 확인했습니다.")
        if str(payload.get("result", "")).upper() == "FAIL" or str(payload.get("message", "")).strip():
            return SessionValidationResult("expired", str(payload.get("message") or "mail initData 실패 응답"))

    if resp.status_code < 500 and any(cookie.name in {"NID_AUT", "NID_SES"} for cookie in session.cookies):
        return SessionValidationResult("valid", "Naver 인증 쿠키와 mail 응답 상태를 확인했습니다.")
    return SessionValidationResult("unknown", f"판별 불가 응답(status={resp.status_code})")


def validate_naver_cafe_session(session: requests.Session, timeout: int = 10) -> SessionValidationResult:
    """Validate Naver Cafe cookies against the Cafe API used by older crawler code."""
    try:
        resp = session.get(NAVER_CAFE_MY_LIST_URL, timeout=timeout, allow_redirects=True)
    except requests.RequestException as exc:
        return SessionValidationResult("unknown", f"CafeMyCafeList 요청 실패: {exc}")

    current_url = resp.url.lower()
    text = resp.text[:4000]
    if "nidlogin" in current_url or "로그인" in text and "id=" in text:
        return SessionValidationResult("expired", "카페 API가 로그인 페이지로 리다이렉트되었습니다.")
    if any(marker in text for marker in ("captcha", "보호조치", "본인확인", "인증")):
        return SessionValidationResult("challenge", "카페 API 응답에서 인증/보호조치가 감지되었습니다.")

    try:
        payload = resp.json()
    except ValueError:
        payload = None
    if isinstance(payload, dict):
        status = str(payload.get("message", {}).get("status", ""))
        if status == "200":
            return SessionValidationResult("valid", "CafeMyCafeList API에서 로그인 상태를 확인했습니다.")
        if status in {"401", "403"}:
            return SessionValidationResult("expired", f"카페 API 인증 실패(status={status})")

    if resp.status_code in {401, 403}:
        return SessionValidationResult("expired", f"카페 API HTTP 인증 실패(status={resp.status_code})")
    return SessionValidationResult("unknown", f"카페 API 판별 불가 응답(status={resp.status_code})")


def build_session_headers(chrome_major: int = DEFAULT_CHROME_MAJOR) -> dict[str, str]:
    return {
        "User-Agent": (
            f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            f"AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{chrome_major}.0.0.0 Safari/537.36"
        ),
        "Sec-Ch-Ua": f'"Chromium";v="{chrome_major}", "Google Chrome";v="{chrome_major}", "Not;A=Brand";v="99"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://cafe.naver.com/",
        "Origin": "https://cafe.naver.com",
    }


def make_requests_session(user_agent: str = DEFAULT_USER_AGENT, prefer_curl_cffi: bool = False) -> requests.Session:
    if prefer_curl_cffi:
        try:
            from curl_cffi import requests as curl_requests

            session = curl_requests.Session(impersonate="chrome131")
            session.headers.update(
                {
                    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
                    "Referer": "https://cafe.naver.com/",
                    "Origin": "https://cafe.naver.com",
                }
            )
            return session
        except Exception:
            pass

    session = requests.Session()
    headers = build_session_headers(DEFAULT_CHROME_MAJOR)
    headers["User-Agent"] = user_agent
    session.headers.update(headers)
    return session


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


def _env_bool(value: str | None, *, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _split_env_list(value: str) -> list[str]:
    return [item.strip() for item in value.replace("\n", ",").split(",") if item.strip()]


def cookies_to_session(
    cookies: list[dict],
    user_agent: str = DEFAULT_USER_AGENT,
    prefer_curl_cffi: bool = False,
) -> requests.Session:
    session = make_requests_session(user_agent, prefer_curl_cffi=prefer_curl_cffi)
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
        self.login_driver_mode = self.env.get("NAVER_LOGIN_DRIVER", "selenium")
        self.login_input_method = self.env.get("NAVER_LOGIN_INPUT_METHOD", "auto")
        self.keep_login = _env_bool(self.env.get("NAVER_KEEP_LOGIN"), default=True)
        self.prefer_curl_cffi = _env_bool(self.env.get("NAVER_USE_CURL_CFFI"), default=True)
        self.login_profile_dir = self.env.get("NAVER_LOGIN_PROFILE_DIR", "data/chrome-profile/naver-login")
        self.login_warmup_urls = _split_env_list(self.env.get("NAVER_LOGIN_WARMUP_URLS", ""))
        self.chrome_binary_path = self.env.get("NAVER_CHROME_BINARY", "")
        self.chromedriver_path = self.env.get("NAVER_CHROMEDRIVER", "")
        if driver_factory is build_driver:
            self.driver_factory = self._build_configured_driver
        else:
            self.driver_factory = driver_factory
        self.login_func = login_func or self._default_login_func
        self.user_agent = user_agent

    def get_requests_session(self, force_login: bool = False, headless: bool = True) -> requests.Session:
        state = self.ensure_login(force_login=force_login, headless=headless)
        if not state.logged_in:
            raise RuntimeError(state.message or "Naver login failed")
        return cookies_to_session(
            self.session_store.load_cookies(),
            self.user_agent,
            prefer_curl_cffi=self.prefer_curl_cffi,
        )

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
                session = cookies_to_session(cookies, self.user_agent, prefer_curl_cffi=self.prefer_curl_cffi)
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
            self._warm_up_login_context(driver)
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
        cafe_result = validate_naver_cafe_session(session)
        if cafe_result.status in {"valid", "expired", "challenge"}:
            return cafe_result.is_valid

        result = validate_naver_mail_session(session)
        if result.status in {"valid", "expired", "challenge"}:
            return result.is_valid

        # Fallback for transient endpoint changes: visit the mailbox shell and detect redirects.
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

    def _build_configured_driver(self, headless: bool = True):
        return build_login_driver(
            mode=self.login_driver_mode,
            headless=headless,
            disable_images=headless,
            user_data_dir=self.login_profile_dir if not headless else None,
            chrome_binary_path=self.chrome_binary_path or None,
            chromedriver_path=self.chromedriver_path or None,
        )

    def _warm_up_login_context(self, driver) -> None:
        urls = [url for url in self.login_warmup_urls if url]
        if not urls:
            return
        for url in urls:
            try:
                driver.get(url)
                time.sleep(2)
            except Exception:
                continue

    def _default_login_func(self, driver, username: str, password: str) -> bool:
        from navercafe_app.auth.naver_login import safe_naver_login

        return safe_naver_login(
            driver,
            username,
            password,
            keep_login=self.keep_login,
            input_method=self.login_input_method,  # type: ignore[arg-type]
        )
