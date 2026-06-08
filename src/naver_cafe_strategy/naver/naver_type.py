# -*- coding: utf-8 -*-
"""
[모듈 06] 네이버 검색결과 A/B 타입 판별 (G열, H열, I열)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
역할:
    키워드로 네이버를 검색했을 때 검색결과 페이지가
    A타입(브랜드/특화 섹션 포함)인지 B타입(일반 섹션만)인지 판별합니다.
    → G열: A 또는 B
    → H열: A박스 섹션 목록 (A타입일 때)
    → I열: 일반 섹션 목록

A타입 vs B타입 정의:
    ┌─────────────────────────────────────────────┐
    │ B타입 (일반)                                  │
    │   네이버가 기본 제공하는 표준 섹션만 표시          │
    │   예: 블로그, 카페, 지식iN, 뉴스, 이미지 등       │
    │                                               │
    │ A타입 (특화/브랜드)                             │
    │   표준 섹션 외에 특별한 섹션(A박스)이 추가로 표시   │
    │   예: "맛집 BEST", "브랜드명 공식 정보" 등         │
    │   광고주가 많은 키워드나 특정 브랜드 키워드에 나타남  │
    └─────────────────────────────────────────────┘

판별 방식:
    1. 검색결과 페이지의 모든 <h2> 태그 텍스트를 수집합니다.
    2. 각 h2가 표준 섹션 목록(STANDARD_SECTIONS)에 속하는지 확인합니다.
    3. 표준 섹션이 아닌 h2가 하나라도 있으면 → A타입
    4. 모든 h2가 표준 섹션이면 → B타입

표준 섹션 목록 (STANDARD_SECTIONS):
    뉴스, 이미지, 동영상, 블로그, 카페, 지식iN, 어학사전,
    VIEW, 쇼핑, 지도, 웹사이트, 인플루언서, AI 브리핑 등
    → 이 섹션들은 네이버가 자동으로 구성하는 기본 섹션입니다.

표준 패턴으로 처리되는 경우:
    "OO관련 광고", "OO관련 브랜드 콘텐츠", "브랜드 검색",
    "플레이스", "함께 보는 숏텐츠" 등도 표준으로 취급합니다.

사전 준비:
    pip install selenium webdriver-manager
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import re
import time
from urllib.parse import quote

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait


# ── 표준 섹션 집합 ────────────────────────────────────────
# 이 목록에 포함된 h2 텍스트는 '일반 섹션'으로 분류됩니다.
STANDARD_SECTIONS = {
    "AI 브리핑", "뉴스", "이미지", "동영상", "블로그", "카페", "지식iN", "어학사전",
    "지식백과", "학술정보", "지도", "웹사이트", "스포츠", "전체", "클립", "인플루언서",
    "VIEW", "숏텐츠", "쇼핑", "연관 검색어", "네이버 가격비교", "네이버플러스 스토어",
    "네이버 클립", "플레이스", "새로 오픈했어요",
}

# ── 표준 섹션으로 취급하는 패턴 (정규식) ─────────────────
STANDARD_PATTERNS = [
    re.compile(r".+관련\s*광고"),             # "OO관련 광고"
    re.compile(r"^함께\s*보는.+숏텐츠"),       # "함께 보는 OO 숏텐츠"
    re.compile(r"^플레이스"),                  # "플레이스 OO"
    re.compile(r".+관련\s*브랜드\s*콘텐츠"),   # "OO관련 브랜드 콘텐츠"
    re.compile(r"^브랜드\s*검색$"),            # "브랜드 검색"
    re.compile(r".+FAQ$"),                    # "OO FAQ"
]


def _normalize(text: str) -> str:
    """연속 공백을 하나로 줄이고 앞뒤 공백을 제거합니다."""
    return re.sub(r"\s+", " ", text).strip()


def _is_standard(text: str) -> bool:
    """
    해당 텍스트가 표준 섹션(일반 섹션)인지 판별합니다.

    Returns:
        True  : 표준 섹션 (STANDARD_SECTIONS에 있거나 STANDARD_PATTERNS에 매칭)
        False : 비표준 섹션 → A박스로 분류
    """
    n = _normalize(text)
    return n in STANDARD_SECTIONS or any(p.search(n) for p in STANDARD_PATTERNS)


def check_naver_type(driver: webdriver.Chrome, keyword: str) -> dict:
    """
    키워드의 네이버 검색결과 타입을 판별합니다.

    Args:
        driver  : 초기화된 Selenium Chrome 드라이버
        keyword : 검색할 키워드 (예: "강남 맛집")

    Returns:
        dict: {
            "type"   : "A" 또는 "B",
            "a_boxes": list[str],  # A박스(비표준) 섹션 이름 목록
            "normals": list[str],  # 표준 섹션 이름 목록
        }

    예시 결과:
        A타입: {"type": "A", "a_boxes": ["강남 맛집 BEST"], "normals": ["블로그", "카페"]}
        B타입: {"type": "B", "a_boxes": [],                  "normals": ["블로그", "카페", "뉴스"]}
    """
    driver.get(f"https://search.naver.com/search.naver?query={quote(keyword)}")

    # h2 태그 2개 이상 나타날 때까지 대기
    try:
        WebDriverWait(driver, 6).until(
            lambda d: len(d.find_elements(By.TAG_NAME, "h2")) >= 2)
        time.sleep(0.3)
    except Exception:
        time.sleep(1.5)

    # JavaScript로 모든 h2 텍스트 수집
    try:
        all_h2 = driver.execute_script("""
            var r = [];
            document.querySelectorAll('h2').forEach(function(el) {
                var t = el.innerText.replace(/\\s+/g, ' ').trim();
                if (t) r.push(t);
            });
            return r;
        """) or []

        # 중복 제거 및 정규화
        seen, clean = set(), []
        for t in all_h2:
            t = _normalize(t)
            if t and t not in seen:
                seen.add(t)
                clean.append(t)
    except Exception:
        clean = []

    # 표준/비표준 분류
    a_boxes = [h for h in clean if _normalize(h) and not _is_standard(h)]
    normals  = [h for h in clean if _normalize(h) in STANDARD_SECTIONS]

    return {
        "type":    "A" if a_boxes else "B",
        "a_boxes": a_boxes,
        "normals": normals,
    }


# ──────────────────────────────────────────────
# 단독 실행 테스트
# ──────────────────────────────────────────────
if __name__ == "__main__":
    from naver_cafe_strategy.browser.webdriver import build_driver

    test_keywords = [
        "강남 맛집",        # A타입 가능성 높음 (경쟁 키워드)
        "날씨",             # B타입 가능성 높음 (정보성)
        "카페 인테리어",
    ]

    print("네이버 검색결과 A/B 타입 판별 테스트")
    print("=" * 40)

    driver = build_driver(headless=True)
    try:
        for kw in test_keywords:
            result = check_naver_type(driver, kw)
            print(f"\n  키워드: [{kw}]")
            print(f"  타입  : {result['type']}타입")
            if result["a_boxes"]:
                print(f"  A박스 : {' | '.join(result['a_boxes'])}")
            if result["normals"]:
                print(f"  일반  : {' | '.join(result['normals'])}")
    finally:
        driver.quit()
        print("\n드라이버 종료")
