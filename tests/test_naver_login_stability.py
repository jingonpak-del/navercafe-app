from __future__ import annotations

import requests

from navercafe_app.auth.naver_login import LoginStateDetector, _replace_text
from navercafe_app.auth.naver_session import (
    NaverSessionManager,
    cookies_to_session,
    validate_naver_cafe_session,
    validate_naver_mail_session,
)


class FakeElement:
    def __init__(self, text: str = "", displayed: bool = True):
        self.text = text
        self._displayed = displayed
        self.calls: list[str] = []

    def is_displayed(self) -> bool:
        return self._displayed

    def click(self) -> None:
        self.calls.append("click")

    def clear(self) -> None:
        self.calls.append("clear")

    def send_keys(self, value) -> None:
        self.calls.append(f"send_keys:{value}")


class FakeDriver:
    def __init__(self, *, elements=None, cookies=None, current_url="https://www.naver.com/", page_source=""):
        self.elements = elements or {}
        self._cookies = cookies or []
        self.current_url = current_url
        self.page_source = page_source

    def find_elements(self, by, selector):
        return self.elements.get((by, selector), [])

    def get_cookies(self):
        return self._cookies


class FakeResponse:
    def __init__(self, *, url="https://mail.naver.com/json/initData", text="{}", status_code=200, payload=None):
        self.url = url
        self.text = text
        self.status_code = status_code
        self._payload = payload

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


def test_login_state_detector_captcha() -> None:
    detector = LoginStateDetector()
    driver = FakeDriver(elements={("id", "captchaimg"): [FakeElement()]})

    state = detector.detect(driver)

    assert state.kind == "captcha"
    assert state.needs_manual_action is True


def test_login_state_detector_logged_in_by_cookie() -> None:
    detector = LoginStateDetector()
    driver = FakeDriver(cookies=[{"name": "NID_AUT"}])

    assert detector.detect(driver).kind == "logged_in"


def test_login_state_detector_ignores_hidden_bad_credential_element() -> None:
    detector = LoginStateDetector()
    driver = FakeDriver(
        elements={("id", "err_common"): [FakeElement("ID/PW 오류 메시지가 표시되었습니다.", displayed=False)]},
        current_url="https://nid.naver.com/nidlogin.login",
    )

    assert detector.detect(driver).kind == "still_on_login"


def test_replace_text_auto_falls_back_to_send_keys_when_clipboard_unavailable(monkeypatch) -> None:
    element = FakeElement()

    def fail_import(name, *args, **kwargs):
        if name == "pyperclip":
            raise ImportError("missing")
        return original_import(name, *args, **kwargs)

    original_import = __import__
    monkeypatch.setattr("builtins.__import__", fail_import)

    _replace_text(element, "abc", input_method="auto")

    assert "clear" in element.calls
    assert "send_keys:abc" in element.calls


def test_validate_naver_mail_session_valid(monkeypatch) -> None:
    session = requests.Session()

    def fake_post(*args, **kwargs):
        return FakeResponse(payload={"userIdNo": "123"})

    monkeypatch.setattr(session, "post", fake_post)

    result = validate_naver_mail_session(session)

    assert result.status == "valid"
    assert result.is_valid is True


def test_validate_naver_mail_session_expired_redirect(monkeypatch) -> None:
    session = requests.Session()

    def fake_post(*args, **kwargs):
        return FakeResponse(url="https://nid.naver.com/nidlogin.login", text="로그인 id=")

    monkeypatch.setattr(session, "post", fake_post)

    assert validate_naver_mail_session(session).status == "expired"


def test_validate_naver_cafe_session_valid(monkeypatch) -> None:
    session = requests.Session()

    def fake_get(*args, **kwargs):
        return FakeResponse(payload={"message": {"status": "200"}})

    monkeypatch.setattr(session, "get", fake_get)

    result = validate_naver_cafe_session(session)

    assert result.status == "valid"
    assert result.is_valid is True


def test_cookies_to_session_adds_cafe_headers() -> None:
    session = cookies_to_session([{"name": "NID_AUT", "value": "x", "domain": ".naver.com"}])

    assert session.cookies.get("NID_AUT") == "x"
    assert session.headers["Referer"] == "https://cafe.naver.com/"
    assert "Sec-Ch-Ua" in session.headers


def test_session_manager_reads_login_stability_env(tmp_path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "NAVER_ID=user",
                "NAVER_PW=pass",
                "NAVER_SESSION_KEY=key",
                "NAVER_LOGIN_DRIVER=undetected",
                "NAVER_LOGIN_INPUT_METHOD=clipboard",
                "NAVER_KEEP_LOGIN=false",
                "NAVER_USE_CURL_CFFI=false",
                "NAVER_LOGIN_PROFILE_DIR=data/custom-profile",
                "NAVER_LOGIN_WARMUP_URLS=https://cafe.naver.com/example,https://cafe.naver.com/f-e/cafes/1",
            ]
        ),
        encoding="utf-8",
    )

    manager = NaverSessionManager(env_path=env_path)

    assert manager.login_driver_mode == "undetected"
    assert manager.login_input_method == "clipboard"
    assert manager.keep_login is False
    assert manager.prefer_curl_cffi is False
    assert manager.login_profile_dir == "data/custom-profile"
    assert manager.login_warmup_urls == ["https://cafe.naver.com/example", "https://cafe.naver.com/f-e/cafes/1"]
