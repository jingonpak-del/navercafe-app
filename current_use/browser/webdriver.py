# -*- coding: utf-8 -*-
"""
[모듈 01] Chrome WebDriver 설정
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
역할:
    Selenium으로 네이버 페이지를 자동 조작하기 위한
    Chrome 브라우저 드라이버를 초기화하고 반환합니다.

작동 방식:
    1. Selenium 4.6+ 내장 Selenium Manager가 Chrome 버전에 맞는
       ChromeDriver를 자동으로 다운로드합니다. (Chrome 업데이트와 무관)
    2. 다양한 옵션을 적용해 봇 탐지를 최소화하고 속도를 높입니다.
    3. 페이지 로드 타임아웃(30초)과 JS 실행 타임아웃(20초)을 설정해
       네트워크 오류 시 무한 대기를 방지합니다.

주요 옵션 설명:
    --headless=new              : 브라우저 창을 띄우지 않고 백그라운드 실행
    --window-size=1920,1080     : 가상 화면 크기 (headless 모드에 필요)
    --disable-blink-features=AutomationControlled : 자동화 탐지 우회
    page_load_strategy = "eager": DOM 로드 완료 시점에 제어 반환 (전체 로드 대기 X)
    images 비활성화              : 이미지 다운로드를 막아 속도 향상

사전 준비:
    pip install selenium
    구글 크롬(Chrome) 브라우저가 PC에 설치되어 있어야 합니다.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import os
import tempfile

from selenium import webdriver
from selenium.webdriver.chrome.options import Options


def build_driver(headless: bool = True) -> webdriver.Chrome:
    """
    Chrome WebDriver를 생성하여 반환합니다.

    Args:
        headless (bool): True이면 창 없이 실행 (기본값). False이면 브라우저 창 표시.

    Returns:
        webdriver.Chrome: 초기화된 Chrome 드라이버 인스턴스

    Example:
        driver = build_driver(headless=True)   # 백그라운드 실행
        driver = build_driver(headless=False)  # 브라우저 창 띄워서 실행 (디버깅용)
        driver.get("https://www.naver.com")
        driver.quit()  # 반드시 종료 호출
    """
    opts = Options()

    if headless:
        opts.add_argument("--headless=new")          # 새 헤드리스 모드 (Chrome 112+)
        opts.add_argument("--window-size=1920,1080") # 헤드리스 시 가상 해상도

    opts.add_argument("--no-sandbox")                # 샌드박스 비활성화 (Linux 환경)
    opts.add_argument("--disable-dev-shm-usage")     # 공유 메모리 오류 방지
    opts.add_argument("--disable-gpu")               # GPU 렌더링 비활성화
    opts.add_argument("--disable-blink-features=AutomationControlled")  # 봇 탐지 우회
    opts.add_argument("--disable-extensions")        # 확장 프로그램 비활성화
    opts.add_argument("--disable-notifications")     # 알림 팝업 차단
    opts.add_argument("--no-first-run")              # 첫 실행 설정 화면 스킵
    opts.add_argument("--lang=ko-KR")               # 한국어 설정
    opts.add_argument("--disable-crash-reporter")    # 크래시 리포터 비활성화
    # 매 실행마다 고유한 임시 프로필 디렉토리 → 좀비 프로세스 프로필 충돌 방지
    _tmp_profile = tempfile.mkdtemp(prefix="cafe_chrome_")
    opts.add_argument(f"--user-data-dir={_tmp_profile}")

    # 자동화 관련 정보 숨기기
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])

    # 이미지 로드 비활성화 (속도 향상)
    opts.add_experimental_option("prefs",
        {"profile.managed_default_content_settings.images": 2})

    # DOM 준비 완료 시점에 driver.get() 반환 (전체 리소스 로드 대기 없음)
    opts.page_load_strategy = "eager"

    # Selenium Manager가 Chrome 버전에 맞는 ChromeDriver 자동 매칭
    driver = webdriver.Chrome(options=opts)

    # 타임아웃 설정 (네트워크 오류 시 무한 대기 방지)
    driver.set_page_load_timeout(30)  # 페이지 로드 최대 30초
    driver.set_script_timeout(20)     # JavaScript 실행 최대 20초

    return driver


# ──────────────────────────────────────────────
# 단독 실행 테스트
# ──────────────────────────────────────────────
if __name__ == "__main__":
    print("Chrome WebDriver 초기화 테스트")
    print("=" * 40)

    # 헤드리스 모드로 드라이버 생성
    driver = build_driver(headless=True)
    print("드라이버 생성 성공!")

    # 테스트: 네이버 접속
    driver.get("https://www.naver.com")
    print(f"페이지 제목: {driver.title}")
    print(f"현재 URL: {driver.current_url}")

    # 드라이버 종료 (반드시 호출)
    driver.quit()
    print("드라이버 종료 완료")
