from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Literal

from selenium.common.exceptions import StaleElementReferenceException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

NAVER_LOGIN_URL = "https://nid.naver.com/nidlogin.login"
NAVER_HOME_URL = "https://www.naver.com/"

LoginStateKind = Literal[
    "logged_in",
    "bad_credentials",
    "captcha",
    "security_challenge",
    "dormant",
    "still_on_login",
    "unknown",
]


@dataclass(slots=True)
class LoginState:
    kind: LoginStateKind
    message: str = ""

    @property
    def needs_manual_action(self) -> bool:
        return self.kind in {"captcha", "security_challenge", "dormant"}


class LoginStateDetector:
    """Detect Naver login outcomes without attempting to bypass challenges.

    The selector set is based on previously decompiled programs, but challenge states are
    deliberately surfaced as manual-intervention states instead of being automated.
    """

    def detect(self, driver) -> LoginState:
        if _has_any(driver, By.ID, "captchaimg"):
            return LoginState("captcha", "CAPTCHA가 표시되어 수동 처리가 필요합니다.")

        bad_credential_elements = driver.find_elements(By.ID, "err_common")
        if bad_credential_elements:
            messages: list[str] = []
            for element in bad_credential_elements:
                try:
                    if not element.is_displayed():
                        continue
                    text = element.text.strip()
                except StaleElementReferenceException:
                    continue
                if text:
                    messages.append(text)
            if messages:
                message = " ".join(messages)
                return LoginState("bad_credentials", message)

        security_selectors = [
            (By.CSS_SELECTOR, "div.protection_content"),
            (By.CSS_SELECTOR, "ul.protection_list"),
            (By.XPATH, "//ul[@class='action_list']/li[2]/span[@class='data']"),
            (By.XPATH, "//div[contains(@class, 'warning_title')]/h2"),
        ]
        for by, selector in security_selectors:
            if _has_any(driver, by, selector):
                return LoginState("security_challenge", "보호조치/본인확인 화면이 표시되어 수동 처리가 필요합니다.")

        dormant_selectors = [
            (By.CSS_SELECTOR, "div.warning.warning_v2 div.title p"),
            (By.XPATH, "//div[contains(@class, 'warning') and contains(@class, 'warning_v2')]//p"),
        ]
        for by, selector in dormant_selectors:
            if _has_any(driver, by, selector):
                return LoginState("dormant", "휴면/추가 확인 화면이 표시되어 수동 처리가 필요합니다.")

        current_url = (driver.current_url or "").lower()
        cookie_names = {cookie.get("name") for cookie in driver.get_cookies()}
        page_head = (driver.page_source or "")[:8000]
        if {"NID_AUT", "NID_SES"} & cookie_names and "nidlogin" not in current_url:
            return LoginState("logged_in", "Naver 인증 쿠키가 확인되었습니다.")
        if "로그아웃" in page_head or "내정보" in page_head:
            return LoginState("logged_in", "로그인된 네이버 화면을 확인했습니다.")
        if "nidlogin" in current_url:
            return LoginState("still_on_login", "로그인 페이지에 머물러 있습니다.")
        return LoginState("unknown", "로그인 상태를 판별하지 못했습니다.")


def safe_naver_login(
    driver,
    username: str,
    password: str,
    *,
    timeout: int = 20,
    manual_wait_seconds: int = 120,
    keep_login: bool = False,
    input_method: Literal["auto", "clipboard", "send_keys", "js"] = "auto",
) -> bool:
    """Perform a conservative, user-visible Naver login flow.

    This routine focuses on stability: explicit waits, clear state detection, optional manual
    challenge handling, and cookie-based success verification. It does not implement CAPTCHA
    solving, security-confirmation bypass, IP rotation, or bot-evasion mouse wandering.

    ``input_method='clipboard'`` mirrors the older hotdeal crawler's login-stability pattern:
    paste credentials into the official Naver login form instead of synthesizing each character.
    If pyperclip is unavailable and ``input_method='auto'``, the function falls back to Selenium
    ``send_keys`` and finally to a DOM input-event fallback only when the field value is still empty.
    """

    wait = WebDriverWait(driver, timeout)
    driver.get(NAVER_HOME_URL)
    driver.get(NAVER_LOGIN_URL)

    try:
        id_input = wait.until(EC.element_to_be_clickable((By.ID, "id")))
        pw_input = wait.until(EC.element_to_be_clickable((By.ID, "pw")))
    except TimeoutException:
        return False

    _replace_text(driver, id_input, username, input_method=input_method)
    _replace_text(driver, pw_input, password, input_method=input_method)

    if keep_login:
        _click_if_present(driver, By.ID, "keep") or _click_if_present(driver, By.CSS_SELECTOR, "label[for='keep']")

    try:
        wait.until(EC.element_to_be_clickable((By.ID, "log.login"))).click()
    except TimeoutException:
        return False

    detector = LoginStateDetector()
    state = _wait_for_terminal_state(driver, detector, timeout=timeout)
    if state.kind == "logged_in":
        return True

    if state.needs_manual_action and manual_wait_seconds > 0:
        deadline = time.monotonic() + manual_wait_seconds
        while time.monotonic() < deadline:
            state = detector.detect(driver)
            if state.kind == "logged_in":
                return True
            if state.kind == "bad_credentials":
                return False
            time.sleep(2)

    return detector.detect(driver).kind == "logged_in"


def _wait_for_terminal_state(driver, detector: LoginStateDetector, *, timeout: int) -> LoginState:
    deadline = time.monotonic() + timeout
    last_state = LoginState("unknown")
    while time.monotonic() < deadline:
        last_state = detector.detect(driver)
        if last_state.kind in {"logged_in", "bad_credentials", "captcha", "security_challenge", "dormant"}:
            return last_state
        time.sleep(0.5)
    return last_state


def _replace_text(
    driver,
    element,
    text: str,
    *,
    input_method: Literal["auto", "clipboard", "send_keys", "js"] = "auto",
) -> None:
    element.click()
    element.send_keys(Keys.CONTROL + "a")

    if input_method == "js":
        _set_value_with_events(driver, element, text)
        return

    if input_method in {"auto", "clipboard"}:
        try:
            import pyperclip

            pyperclip.copy(text)
            element.send_keys(Keys.CONTROL + "v")
            time.sleep(0.4)
            if _element_value(element):
                return
        except Exception:
            if input_method == "clipboard":
                raise

    element.clear()
    element.send_keys(text)
    time.sleep(0.2)
    if input_method == "auto" and not _element_value(element):
        _set_value_with_events(driver, element, text)


def _element_value(element) -> str:
    try:
        return str(element.get_attribute("value") or "")
    except Exception:
        return ""


def _set_value_with_events(driver, element, text: str) -> None:
    driver.execute_script(
        """
        const el = arguments[0];
        const value = arguments[1];
        el.focus();
        el.value = '';
        el.dispatchEvent(new Event('input', { bubbles: true }));
        el.value = value;
        el.dispatchEvent(new Event('input', { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
        """,
        element,
        text,
    )
    time.sleep(0.2)
def _click_if_present(driver, by: str, selector: str) -> bool:
    elements = driver.find_elements(by, selector)
    if not elements:
        return False
    try:
        elements[0].click()
        return True
    except Exception:
        return False


def _has_any(driver, by: str, selector: str) -> bool:
    try:
        return bool(driver.find_elements(by, selector))
    except Exception:
        return False
