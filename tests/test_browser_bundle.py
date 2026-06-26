from __future__ import annotations

from navercafe_app.browser_bundle import BrowserBundlePaths, find_bundled_browser


def test_find_bundled_browser_detects_portable_layout(tmp_path, monkeypatch) -> None:
    chrome = tmp_path / "browsers" / "chrome-win64" / "chrome.exe"
    driver = tmp_path / "drivers" / "chromedriver-win64" / "chromedriver.exe"
    chrome.parent.mkdir(parents=True)
    driver.parent.mkdir(parents=True)
    chrome.write_text("chrome", encoding="utf-8")
    driver.write_text("driver", encoding="utf-8")
    monkeypatch.delenv("NAVER_CHROME_BINARY", raising=False)
    monkeypatch.delenv("NAVER_CHROMEDRIVER", raising=False)

    paths = find_bundled_browser(tmp_path)

    assert paths.is_complete
    assert paths.chrome_binary == chrome
    assert paths.chromedriver == driver


def test_find_bundled_browser_env_override(monkeypatch, tmp_path) -> None:
    chrome = tmp_path / "custom-chrome.exe"
    driver = tmp_path / "custom-driver.exe"
    monkeypatch.setenv("NAVER_CHROME_BINARY", str(chrome))
    monkeypatch.setenv("NAVER_CHROMEDRIVER", str(driver))

    paths = find_bundled_browser(tmp_path)

    assert paths == BrowserBundlePaths(chrome, driver)
