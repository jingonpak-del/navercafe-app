from navercafe_app.auth.naver_session import NaverSessionManager, cookies_to_session
from navercafe_app.auth.session_store import SessionStore


class FakeDriver:
    def __init__(self):
        self.quit_called = False

    def get_cookies(self):
        return [
            {"name": "NID_AUT", "value": "aut", "domain": ".naver.com", "path": "/"},
            {"name": "NID_SES", "value": "ses", "domain": ".naver.com", "path": "/"},
        ]

    def quit(self):
        self.quit_called = True


def test_session_store_roundtrip_plain(tmp_path):
    store = SessionStore(tmp_path / "cookies.json")
    cookies = [{"name": "NID_SES", "value": "abc", "domain": ".naver.com", "path": "/"}]
    store.save_cookies(cookies, username_hint="user")
    assert store.is_available()
    assert store.load_cookies()[0]["name"] == "NID_SES"


def test_session_store_roundtrip_encoded(tmp_path):
    store = SessionStore(tmp_path / "cookies.enc.json", encryption_key="secret")
    cookies = [{"name": "NID_AUT", "value": "abc", "domain": ".naver.com", "path": "/"}]
    store.save_cookies(cookies)
    assert "NID_AUT" not in (tmp_path / "cookies.enc.json").read_text(encoding="utf-8")
    assert store.load_cookies()[0]["value"] == "abc"


def test_cookies_to_session_sets_naver_cookies():
    session = cookies_to_session([{"name": "NID_AUT", "value": "v", "domain": ".naver.com", "path": "/"}])
    assert session.cookies.get("NID_AUT") == "v"


def test_naver_session_manager_logs_in_and_saves_cookies(tmp_path):
    env = tmp_path / ".env"
    env.write_text("NAVER_ID=tester\nNAVER_PW=pass\nNAVER_SESSION_KEY=k\n", encoding="utf-8")
    store = SessionStore(tmp_path / "cookies.json", encryption_key="k")

    manager = NaverSessionManager(
        env_path=env,
        session_store=store,
        driver_factory=lambda **kwargs: FakeDriver(),
        login_func=lambda driver, username, password: username == "tester" and password == "pass",
    )
    state = manager.ensure_login(force_login=True)
    assert state.logged_in
    assert state.source == "selenium"
    assert store.load_cookies()[0]["name"] == "NID_AUT"


def test_naver_session_manager_accepts_gui_credential_overrides(tmp_path):
    env = tmp_path / ".env"
    env.write_text("NAVER_ID=\nNAVER_PW=\nNAVER_SESSION_KEY=k\n", encoding="utf-8")
    store = SessionStore(tmp_path / "cookies.json", encryption_key="k")

    manager = NaverSessionManager(
        env_path=env,
        session_store=store,
        driver_factory=lambda **kwargs: FakeDriver(),
        login_func=lambda driver, username, password: username == "screen-user" and password == "screen-pass",
        username="screen-user",
        password="screen-pass",
    )

    state = manager.ensure_login(force_login=True)

    assert state.logged_in
    assert store.load_cookies()[0]["name"] == "NID_AUT"
