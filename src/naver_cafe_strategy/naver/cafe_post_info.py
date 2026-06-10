# -*- coding: utf-8 -*-
"""
[모듈 05] 네이버 카페 게시글 정보 수집 (D열, K열)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
역할:
    네이버 카페 게시글 URL에서 게시글 제목과 조회수를 추출합니다.
    → 제목은 D열, 조회수는 K열에 기록됩니다.

네이버 카페 구조의 특수성:
    네이버 카페 게시글은 일반 웹페이지가 아닌 iframe 구조를 사용합니다.
    메인 페이지 안에 <iframe id="cafe_main">이 있고,
    그 안에 실제 게시글 내용(제목, 본문, 조회수)이 담겨 있습니다.

    일반 driver.page_source로는 iframe 내부 내용을 볼 수 없으므로,
    반드시 iframe으로 포커스를 전환(switch_to.frame)해야 합니다.

작동 방식:
    1. driver.get(url)으로 카페 게시글 페이지 로드
    2. #cafe_main iframe이 나타날 때까지 대기 후 iframe으로 전환
    3. 제목: 여러 CSS 선택자를 순서대로 시도하여 제목 텍스트 추출
    4. 조회수: 페이지 소스에서 정규식으로 숫자 추출
    5. iframe에서 나와 메인 페이지로 복귀

제목 추출 선택자 우선순위:
    ".ArticleTitle .title_text" → "h3.title" → ".title_subject"
    → "[class*='tit_h3']" → "[class*='article'] h3" → "h3"

조회수 추출 정규식 (순서대로 시도):
    r"조회\s+([0-9,]+)"    : "조회 1,234" 형태
    r"읽음\s+([0-9,]+)"    : "읽음 1,234" 형태 (일부 카페)
    r'"readCount"\s*:\s*(\d+)': JSON 데이터 내 readCount 필드

제목 추출 폴백(Fallback):
    iframe 내에서 제목을 못 찾은 경우,
    브라우저 탭 제목(driver.title)에서 " : 네이버 카페" 부분을 제거하여 사용

사전 준비:
    pip install selenium webdriver-manager
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import re
import time

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


def get_cafe_post_info(driver: webdriver.Chrome, url: str) -> dict:
    """
    네이버 카페 게시글의 제목과 조회수를 추출합니다.

    Args:
        driver : 초기화된 Selenium Chrome 드라이버
        url    : 카페 게시글 URL
                 (예: "https://cafe.naver.com/mycafe/12345678")

    Returns:
        dict: {
            "title": str,  # 게시글 제목 (추출 실패 시 "(제목 미확인)")
            "views": int,  # 조회수 (추출 실패 시 0)
        }

    주의:
        카페 운영자 설정에 따라 비회원에게 게시글이 공개되지 않으면
        제목/조회수 추출이 실패할 수 있습니다.
    """
    driver.get(url)

    # 페이지 초기 로딩 대기
    try:
        WebDriverWait(driver, 8).until(
            EC.presence_of_element_located((By.TAG_NAME, "body")))
        time.sleep(1.5)  # 동적 콘텐츠(iframe 포함) 로딩 대기
    except Exception:
        time.sleep(2)

    title, views = "", 0

    try:
        # ── STEP 1: #cafe_main iframe으로 전환 ──────────────
        WebDriverWait(driver, 8).until(
            EC.frame_to_be_available_and_switch_to_it((By.ID, "cafe_main")))

        # iframe 내부 콘텐츠 로딩 대기
        WebDriverWait(driver, 6).until(
            lambda d: d.find_elements(By.CSS_SELECTOR,
                "h3, .ArticleTitle, .title_subject, [class*='title']"))
        time.sleep(0.3)

        # ── STEP 2: 페이지 소스 취득 (조회수 추출용) ─────────
        src = driver.page_source

        # ── STEP 3: 제목 추출 (선택자 우선순위 순으로 시도) ──
        title_selectors = [
            ".ArticleTitle .title_text",   # 최신 카페 UI
            "h3.title",                    # 일반 형태
            ".title_subject",              # 구형 카페 UI
            "[class*='tit_h3']",           # 일부 카페 변형
            "[class*='article'] h3",       # article 내 h3
            "h3",                          # 모든 h3 폴백
        ]
        for sel in title_selectors:
            for el in driver.find_elements(By.CSS_SELECTOR, sel):
                t = el.text.strip()
                if t and len(t) > 2:      # 의미있는 텍스트만 (2자 초과)
                    title = t
                    break
            if title:
                break

        # ── STEP 4: 조회수 추출 (정규식 순서대로 시도) ────────
        view_patterns = [
            r"조회\s+([0-9,]+)",           # "조회 1,234"
            r"읽음\s+([0-9,]+)",           # "읽음 1,234" (일부 카페)
            r'"readCount"\s*:\s*(\d+)',    # JSON 내 readCount 필드
        ]
        for pat in view_patterns:
            m = re.search(pat, src)
            if m:
                ns = m.group(1).replace(",", "")  # 쉼표 제거
                if ns.isdigit():
                    views = int(ns)
                    break

        # ── STEP 5: iframe에서 메인 페이지로 복귀 ────────────
        driver.switch_to.default_content()

    except Exception:
        # 오류 발생 시 반드시 iframe에서 복귀
        try:
            driver.switch_to.default_content()
        except Exception:
            pass

    # ── 제목 폴백: 브라우저 탭 제목에서 추출 ─────────────────
    if not title:
        raw = driver.title or ""
        if " : 네이버 카페" in raw:
            title = raw.replace(" : 네이버 카페", "").strip()

    return {
        "title": title or "(제목 미확인)",
        "views": views,
    }


# ──────────────────────────────────────────────
# 단독 실행 테스트
# ──────────────────────────────────────────────
if __name__ == "__main__":
    from naver_cafe_strategy.browser.webdriver import build_driver

    # 테스트할 카페 게시글 URL (실제 URL로 교체)
    TEST_URL = "https://cafe.naver.com/테스트카페/12345678"

    print("카페 게시글 정보 수집 테스트")
    print("=" * 40)
    print(f"URL: {TEST_URL}")
    print()

    driver = build_driver(headless=True)
    try:
        info = get_cafe_post_info(driver, TEST_URL)
        print(f"제목  : {info['title']}")
        print(f"조회수: {info['views']:,}회")
    finally:
        driver.quit()
        print("드라이버 종료")
