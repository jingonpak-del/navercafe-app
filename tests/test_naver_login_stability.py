from __future__ import annotations

import requests

from navercafe_app.auth.naver_login import LoginStateDetector
from navercafe_app.auth.naver_session import validate_naver_mail_session


class FakeElement:
    def __init__(self, text: str = ""):
        self.text = text


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
