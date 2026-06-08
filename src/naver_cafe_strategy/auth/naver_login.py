# -*- coding: utf-8 -*-
"""
[모듈 01] 네이버 로그인
=============================
Selenium WebDriver를 이용한 네이버 자동 로그인 모듈.
봇 탐지 우회 설정 및 로그인 성공/실패/캡챠 감지 처리 포함.

필요 패키지:
    pip install selenium
"""

import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

NAVER_LOGIN_URL = "https://nid.naver.com/nidlogin.login"
NAVER_MAIN_URL  = "https://www.naver.com/"


# ─────────────────────────────────────────────
# 드라이버 생성
# ─────────────────────────────────────────────

def create_driver(chromedriver_path: str = None) -> webdriver.Chrome:
    """
    봇 탐지 우회 옵션이 적용된 Chrome WebDriver 생성.

    Args:
        chromedriver_path: chromedriver.exe 경로 (None이면 PATH에서 자동 탐색)

    Returns:
        webdriver.Chrome 인스턴스
    """
    options = Options()

    # ── 봇 탐지 우회 ──────────────────────────────
    options.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/116.0.0.0 Safari/537.36"
    )
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-infobars")
    options.add_argument("--lang=ko-KR")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    if chromedriver_path:
        driver = webdriver.Chrome(service=Service(chromedriver_path), options=options)
    else:
        driver = webdriver.Chrome(options=options)

    # navigator.webdriver 속성 제거 (추가 우회)
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    })

    return driver


# ─────────────────────────────────────────────
# 로그인
# ─────────────────────────────────────────────

def naver_login(driver: webdriver.Chrome, naver_id: str, naver_pw: str) -> bool:
    """
    네이버 로그인 수행.

    Args:
        driver   : create_driver()로 생성한 WebDriver
        naver_id : 네이버 아이디
        naver_pw : 네이버 비밀번호

    Returns:
        bool: 로그인 성공 여부
    """
    try:
        driver.get(NAVER_LOGIN_URL)
        wait = WebDriverWait(driver, 10)

        # ID 입력
        id_input = wait.until(EC.presence_of_element_located((By.ID, "id")))
        id_input.clear()
        id_input.send_keys(naver_id)
        time.sleep(0.3)

        # PW 입력
        pw_input = driver.find_element(By.ID, "pw")
        pw_input.clear()
        pw_input.send_keys(naver_pw)
        time.sleep(0.3)

        # 로그인 버튼 클릭
        driver.find_element(By.ID, "log.login").click()
        time.sleep(2)

        # 캡챠 감지 → 수동 처리 대기
        if _check_captcha(driver):
            print(f"[{naver_id}] 캡챠 감지 — 수동으로 처리 후 Enter를 누르세요.")
            input()

        # 로그인 오류 감지
        if _check_login_error(driver):
            print(f"[{naver_id}] 로그인 실패 — ID/PW를 확인하세요.")
            return False

        # 로그인 성공 확인 (URL 변경 여부)
        time.sleep(1)
        if "nidlogin" not in driver.current_url:
            print(f"[{naver_id}] 로그인 성공")
            return True

        return False

    except Exception as e:
        print(f"[{naver_id}] 로그인 중 예외 발생: {e}")
        return False


# ─────────────────────────────────────────────
# 로그인 상태 확인
# ─────────────────────────────────────────────

def get_logged_in_user(driver: webdriver.Chrome) -> str | None:
    """
    현재 로그인된 사용자 정보 반환.

    Returns:
        사용자 표시 이름 또는 None
    """
    try:
        driver.get(NAVER_MAIN_URL)
        time.sleep(1)
        elements = driver.find_elements(By.CLASS_NAME, "MyView-module__my_info___GNmHz")
        if elements:
            return elements[0].text
        return None
    except Exception:
        return None


# ─────────────────────────────────────────────
# 내부 헬퍼
# ─────────────────────────────────────────────

def _check_captcha(driver: webdriver.Chrome) -> bool:
    """캡챠 이미지 존재 여부 확인."""
    return len(driver.find_elements(By.ID, "captchaimg")) > 0


def _check_login_error(driver: webdriver.Chrome) -> bool:
    """로그인 오류 메시지 존재 여부 확인."""
    return len(driver.find_elements(By.XPATH, '//div[@id="err_common"]')) > 0


# ─────────────────────────────────────────────
# 사용 예시
# ─────────────────────────────────────────────

if __name__ == "__main__":
    NAVER_ID = "your_id"
    NAVER_PW = "your_pw"

    driver = create_driver()
    try:
        success = naver_login(driver, NAVER_ID, NAVER_PW)
        if success:
            user = get_logged_in_user(driver)
            print(f"로그인된 사용자: {user}")
    finally:
        input("종료하려면 Enter를 누르세요...")
        driver.quit()
