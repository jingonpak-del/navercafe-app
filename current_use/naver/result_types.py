# -*- coding: utf-8 -*-
"""
[모듈 07] 네이버 검색결과 노출구좌 카운트 (F열)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
역할:
    키워드로 네이버를 검색했을 때 검색결과에 등장하는
    콘텐츠 유형별 개수를 카운트합니다.
    → F열에 "카2블5지1기3" 형태로 기록됩니다.

분류 기준:
    카 (카페)   : cafe.naver.com/카페명/게시글번호 형태의 링크
    블 (블로그)  : blog.naver.com/아이디/게시글번호
                  또는 post.naver.com/아이디/게시글번호
    지 (지식iN)  : kin.naver.com/qna/detail 또는 /knowledge 경로
    기 (기타)   : naver.com 도메인이 아닌 외부 웹사이트

결과 형식:
    "카2블5지1기3"  → 카페 2개, 블로그 5개, 지식iN 1개, 외부사이트 3개
    "카0"           → 아무것도 없을 때의 기본값
    숫자가 0인 항목은 결과에서 생략됩니다.
    예) 카페와 블로그만 있으면: "카3블7"

중복 제거 방식:
    동일한 게시글이 여러 링크(추천, 광고 등)로 반복될 수 있어
    URL의 scheme + domain + path 기준으로 중복을 제거합니다.
    (쿼리스트링, 해시 제외)

제외 URL (집계에서 제외하는 네이버 내부 링크):
    검색 자체 URL, 광고관리, 쇼핑, 뉴스, 지도, 로그인, 가입,
    정책 페이지, 사전, TV 등 콘텐츠가 아닌 네이버 내부 링크

사전 준비:
    pip install selenium webdriver-manager
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import re
import time
from urllib.parse import quote, urlparse

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait


# ── 집계에서 제외할 네이버 내부 URL 패턴 ────────────────────
# 검색 인프라, 광고, 사전, 뉴스 등 콘텐츠가 아닌 링크를 제외합니다.
EXCLUDE_PATTERN = re.compile(
    r"naver\.com/(search|ad|adcr|adsManager|npost|login|join|help|policy|"
    r"notice|trend|datalab|shopping/gate|main|index|mail|band|news/read|"
    r"series|map|view/v)|accounts\.naver|nid\.naver|static\.naver|"
    r"shopping\.naver|tv\.naver|dict\.naver|jdict\.naver|terms\.naver|"
    r"developers\.naver|mybox\.naver|pay\.naver",
    re.IGNORECASE
)


def _classify(url: str):
    """
    URL을 콘텐츠 유형으로 분류합니다.

    Args:
        url: 분류할 URL 문자열

    Returns:
        "cafe"  : 네이버 카페 게시글
        "blog"  : 네이버 블로그 또는 포스트 게시글
        "kin"   : 네이버 지식iN 답변
        "other" : 외부 웹사이트 (네이버 도메인 아님)
        None    : 집계에서 제외되어야 하는 URL
    """
    u = url.lower()

    # 제외 대상: javascript 링크, # 앵커, 내부 인프라 URL
    if EXCLUDE_PATTERN.search(u) or "javascript:" in u or u.startswith("#"):
        return None

    # 카페: cafe.naver.com/카페명/게시글번호
    if "cafe.naver.com" in u:
        return "cafe" if re.search(r"cafe\.naver\.com/[^/]+/\d+", u) else None

    # 블로그: blog.naver.com/아이디/게시글번호
    if "blog.naver.com" in u:
        return "blog" if re.search(r"blog\.naver\.com/[^/?#]+/\d+", u) else None

    # 포스트: post.naver.com (블로그와 동일 카테고리)
    if "post.naver.com" in u:
        return "blog" if re.search(r"post\.naver\.com/[^/?#]+/\d+", u) else None

    # 지식iN: kin.naver.com/qna/detail 또는 /knowledge
    if "kin.naver.com" in u:
        return "kin" if re.search(r"kin\.naver\.com/(qna/detail|knowledge)", u) else None

    # 기타: naver.com이 아닌 외부 사이트
    if "naver.com" not in u and u.startswith("http"):
        return "other"

    return None  # 기타 네이버 내부 링크 (집계 제외)


def count_result_types(driver: webdriver.Chrome, keyword: str) -> str:
    """
    키워드 검색결과의 콘텐츠 유형별 개수를 카운트하여 문자열로 반환합니다.

    Args:
        driver  : 초기화된 Selenium Chrome 드라이버
        keyword : 검색할 키워드 (예: "강남 맛집")

    Returns:
        str: "카X블X지X기X" 형식의 카운트 문자열
             (개수가 0인 유형은 생략, 모두 0이면 "기0" 반환)

    예시:
        "카2블5지1기3"  → 카페 2, 블로그 5, 지식iN 1, 외부 3
        "블10기2"       → 블로그 10, 외부 2 (카페/지식iN은 0이어서 생략)
    """
    driver.get(f"https://search.naver.com/search.naver?query={quote(keyword)}")

    # 검색 결과 로딩 대기
    try:
        WebDriverWait(driver, 8).until(
            lambda d: len(d.find_elements(By.TAG_NAME, "a")) > 10)
        time.sleep(0.8)
    except Exception:
        time.sleep(2)

    # JavaScript로 페이지 내 모든 http 링크 수집
    hrefs = driver.execute_script("""
        var h = [];
        document.querySelectorAll('a[href]').forEach(function(a) {
            var u = a.href || '';
            if (u.startsWith('http')) h.push(u);
        });
        return h;
    """) or []

    counts = {"cafe": 0, "blog": 0, "kin": 0, "other": 0}
    seen   = set()

    for href in hrefs:
        # 쿼리스트링·해시를 제외한 기본 URL로 중복 확인
        try:
            p    = urlparse(href)
            base = f"{p.scheme}://{p.netloc}{p.path}".rstrip("/")
        except Exception:
            base = href

        if base in seen:
            continue  # 이미 집계한 URL 건너뜀

        cat = _classify(href)
        if cat:
            seen.add(base)
            counts[cat] += 1

    # 결과 문자열 조합
    parts = []
    if counts["cafe"]:  parts.append(f"카{counts['cafe']}")
    if counts["blog"]:  parts.append(f"블{counts['blog']}")
    if counts["kin"]:   parts.append(f"지{counts['kin']}")
    if counts["other"]: parts.append(f"기{counts['other']}")

    return "".join(parts) or "기0"


# ──────────────────────────────────────────────
# 단독 실행 테스트
# ──────────────────────────────────────────────
if __name__ == "__main__":
    from naver_cafe_strategy.browser.webdriver import build_driver

    test_keywords = [
        "강남 맛집",
        "카페 인테리어",
        "파이썬 독학",
    ]

    print("네이버 검색결과 노출구좌 카운트 테스트")
    print("=" * 40)

    driver = build_driver(headless=True)
    try:
        for kw in test_keywords:
            result = count_result_types(driver, kw)
            print(f"  [{kw}] → {result}")
    finally:
        driver.quit()
        print("드라이버 종료")
