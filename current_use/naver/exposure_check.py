# -*- coding: utf-8 -*-
"""
[모듈 04] 네이버 검색 노출 여부 확인 (J열)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
역할:
    특정 키워드로 네이버를 검색했을 때,
    지정한 카페 게시글이 검색 결과에 노출되는지 확인합니다.
    → "1"(노출됨) 또는 "0"(노출 안됨)를 반환하여 J열에 기록합니다.

작동 방식:
    1. Selenium으로 네이버 검색 결과 페이지를 엽니다.
    2. 페이지 내 모든 <a href="..."> 링크를 수집합니다.
    3. 수집된 링크 중에 목표 카페 게시글 URL이 포함되는지 확인합니다.

링크 매칭 방식 (두 가지 중 하나라도 매칭 시 "O"):
    방법 1: 카페 게시글 ID로 매칭
        카페 URL "cafe.naver.com/카페명/게시글번호" 형태에서
        "카페명/게시글번호" 부분을 추출하여 링크에 포함되는지 확인
        예) "mycafe/12345678" 이 링크 어딘가에 포함되면 노출로 판정

    방법 2: URL 직접 포함 확인
        목표 URL 전체가 수집된 링크에 포함되는지 확인

왜 두 가지를 쓰나요?:
    네이버 검색 결과에서 카페 게시글 링크는 리다이렉트(추적 URL)를 거칠 수 있어
    원본 URL과 완전히 일치하지 않을 수 있습니다.
    카페명/게시글번호를 핵심 식별자로 사용하면 리다이렉트 여부와 무관하게 판정 가능합니다.

사전 준비:
    pip install selenium webdriver-manager
    Google Chrome 브라우저 설치 필요
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import re
import time
from urllib.parse import quote

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait


def _cafe_id(url: str):
    """
    네이버 카페 게시글 URL에서 '카페명/게시글번호'를 추출합니다.

    Args:
        url: 카페 게시글 URL (예: "https://cafe.naver.com/mycafe/12345678")

    Returns:
        str | None: "mycafe/12345678" 형태의 문자열, 카페 URL이 아닌 경우 None
    """
    m = re.search(r"cafe\.naver\.com/([^/?#]+)/(\d+)", url)
    return f"{m.group(1)}/{m.group(2)}" if m else None


def check_exposure(driver: webdriver.Chrome, keyword: str, target_url: str) -> str:
    """
    키워드 네이버 검색 결과에 target_url이 노출되는지 확인합니다.

    Args:
        driver     : 초기화된 Selenium Chrome 드라이버
        keyword    : 검색할 키워드 (예: "강남 카페 추천")
        target_url : 노출 여부를 확인할 카페 게시글 URL

    Returns:
        "1" : 검색 결과에 해당 게시글이 노출됨
        "0" : 검색 결과에 해당 게시글이 없음

    주의:
        네이버 검색은 로그인 여부, 개인화, 지역 등에 따라 결과가 달라질 수 있습니다.
        이 함수는 비로그인 상태의 일반 검색 결과를 기준으로 확인합니다.
    """
    # 네이버 검색 실행
    search_url = f"https://search.naver.com/search.naver?query={quote(keyword)}"
    driver.get(search_url)

    # 검색 결과 로딩 대기 (링크 10개 이상 나타날 때까지)
    try:
        WebDriverWait(driver, 8).until(
            lambda d: len(d.find_elements(By.TAG_NAME, "a")) > 10)
        time.sleep(0.5)  # 동적 콘텐츠 추가 로딩 대기
    except Exception:
        time.sleep(2)   # 타임아웃 시 추가 대기

    # 목표 카페 ID 추출 (카페명/게시글번호)
    tid = _cafe_id(target_url)

    # JavaScript로 페이지 내 모든 http 링크 수집
    hrefs = driver.execute_script("""
        var h = [];
        document.querySelectorAll('a[href]').forEach(function(a) {
            var u = a.href || '';
            if (u.startsWith('http')) h.push(u);
        });
        return h;
    """) or []

    # 링크 매칭 확인
    for link in hrefs:
        # 방법 1: 카페 ID(카페명/게시글번호) 포함 여부
        if tid and tid in link:
            return "1"
        # 방법 2: 원본 URL 포함 여부
        if target_url.rstrip("/") in link:
            return "1"

    return "0"


# ──────────────────────────────────────────────
# 단독 실행 테스트
# ──────────────────────────────────────────────
if __name__ == "__main__":
    from naver_cafe_strategy.browser.webdriver import build_driver

    # 테스트용 데이터 (실제 데이터로 교체)
    test_cases = [
        {
            "keyword":    "강남 카페 추천",
            "target_url": "https://cafe.naver.com/테스트카페/12345678",
        },
    ]

    print("네이버 검색 노출 확인 테스트")
    print("=" * 40)

    driver = build_driver(headless=True)
    try:
        for tc in test_cases:
            result = check_exposure(driver, tc["keyword"], tc["target_url"])
            status = "✔ 노출됨" if result == "1" else "✘ 미노출"
            print(f"  키워드: {tc['keyword']}")
            print(f"  결과: {status} ({result})")
    finally:
        driver.quit()
        print("드라이버 종료")
