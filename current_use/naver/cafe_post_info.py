# -*- coding: utf-8 -*-
"""
네이버 카페 게시글 성과 지표 수집
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

역할:
    네이버 카페 게시글 URL에서 제목, 조회수, 댓글수, 좋아요수를 추출합니다.

핵심 포인트:
    - 네이버 카페 글은 보통 메인 페이지 안의 iframe(id="cafe_main")에 실제 글이 있습니다.
    - Selenium으로 페이지를 열고 iframe 내부로 전환한 뒤 DOM 텍스트/HTML을 함께 분석합니다.
    - 카페 UI가 조금씩 달라져도 동작하도록 CSS 선택자 + 정규식 fallback을 같이 사용합니다.

사전 준비:
    uv pip install selenium
    또는
    pip install selenium

사용 예:
    python -m naver_cafe_strategy.naver.cafe_post_info \
      https://cafe.naver.com/feko/10791546 \
      https://cafe.naver.com/feko/10791557 \
      https://cafe.naver.com/feko/10791575 \
      --output output/feko_post_metrics.csv

주의:
    - 비공개/멤버 전용 글이면 로그인된 브라우저 세션이 필요할 수 있습니다.
    - 조회수/댓글수/좋아요수 표기가 카페 스킨 또는 네이버 UI 변경으로 바뀌면
      COUNT_PATTERNS 또는 CSS 선택자를 보강하면 됩니다.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

from __future__ import annotations

import argparse
import csv
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse

from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


COUNT_PATTERNS: dict[str, list[re.Pattern[str]]] = {
    "views": [
        re.compile(r"조회(?:수)?\s*[:：]?\s*([0-9,]+)"),
        re.compile(r"읽음\s*[:：]?\s*([0-9,]+)"),
        re.compile(r'"(?:readCount|viewCount|readCnt|viewCnt)"\s*:\s*"?([0-9,]+)"?'),
    ],
    "comments": [
        re.compile(r"댓글\s*[:：]?\s*([0-9,]+)"),
        re.compile(r'"(?:commentCount|commentCnt|replyCount|replyCnt)"\s*:\s*"?([0-9,]+)"?'),
    ],
    "likes": [
        re.compile(r"좋아요\s*[:：]?\s*([0-9,]+)"),
        re.compile(r"공감\s*[:：]?\s*([0-9,]+)"),
        re.compile(r'"(?:likeCount|likeCnt|sympathyCount|empathyCount|upCount)"\s*:\s*"?([0-9,]+)"?'),
    ],
}

TITLE_SELECTORS = [
    ".ArticleTitle .title_text",  # 최신 카페 UI
    "h3.title_text",
    "h3.title",
    ".title_subject",  # 구형 카페 UI
    "[class*='tit_h3']",
    "[class*='article'] h3",
    "h3",
]

# 지표별로 자주 쓰이는 CSS 후보. 실패해도 전체 텍스트/HTML 정규식 fallback이 처리합니다.
COUNT_SELECTORS: dict[str, list[str]] = {
    "views": [
        ".ArticleTool .count",
        ".article_info .count",
        ".article_info [class*='count']",
        "[class*='view']",
        "[class*='read']",
    ],
    "comments": [
        ".button_comment .num",
        ".CommentBox .comment_option .num",
        ".ArticleTool .button_comment",
        "a[href*='comment']",
        "[class*='comment'] [class*='num']",
    ],
    "likes": [
        ".u_likeit_list_btn .u_likeit_list_module .u_cnt",
        ".u_likeit_text._count",
        ".u_likeit_text",
        ".like_article .u_cnt",
        "[class*='like'] [class*='cnt']",
        "[class*='like'] [class*='count']",
        "[class*='sympathy']",
    ],
}


@dataclass
class CafePostMetrics:
    url: str
    cafe_slug: str
    article_id: str
    title: str
    views: int
    comments: int
    likes: int
    error: str = ""


def _to_int(value: str | None) -> int:
    if not value:
        return 0
    digits = re.sub(r"[^0-9]", "", value)
    return int(digits) if digits else 0


def parse_cafe_article_url(url: str) -> tuple[str, str]:
    """https://cafe.naver.com/{cafe_slug}/{article_id} 형태에서 카페명/글번호를 추출합니다."""
    parsed = urlparse(url)
    parts = [part for part in parsed.path.split("/") if part]
    cafe_slug = parts[0] if parts else ""
    article_id = ""

    # 일반 형태: /feko/10791546
    if len(parts) >= 2 and parts[1].isdigit():
        article_id = parts[1]
    else:
        # 구형 URL 쿼리 형태 대응: ?articleid=123 또는 ?articleId=123
        match = re.search(r"(?:articleid|articleId|article_id)=([0-9]+)", parsed.query)
        article_id = match.group(1) if match else ""

    return cafe_slug, article_id


def extract_count_from_text(text: str, metric: str) -> int:
    """텍스트/HTML에서 조회수·댓글수·좋아요수를 정규식으로 추출합니다."""
    for pattern in COUNT_PATTERNS[metric]:
        match = pattern.search(text)
        if match:
            return _to_int(match.group(1))
    return 0


def extract_counts_from_html(html: str, visible_text: str = "") -> dict[str, int]:
    """HTML과 화면 텍스트를 합쳐 지표를 추출합니다. 테스트 가능한 순수 함수입니다."""
    source = f"{visible_text}\n{html}"
    return {
        "views": extract_count_from_text(source, "views"),
        "comments": extract_count_from_text(source, "comments"),
        "likes": extract_count_from_text(source, "likes"),
    }


def _first_text_by_selectors(driver: webdriver.Chrome, selectors: Iterable[str]) -> str:
    for selector in selectors:
        for element in driver.find_elements(By.CSS_SELECTOR, selector):
            text = (element.text or "").strip()
            if text:
                return text
    return ""


def _count_by_selectors(driver: webdriver.Chrome, metric: str) -> int:
    for selector in COUNT_SELECTORS[metric]:
        for element in driver.find_elements(By.CSS_SELECTOR, selector):
            text = (element.text or "").strip()
            value = extract_count_from_text(text, metric)
            if value:
                return value
    return 0


def get_cafe_post_info(driver: webdriver.Chrome, url: str, wait_seconds: int = 10) -> dict:
    """
    단일 네이버 카페 게시글의 제목/조회수/댓글수/좋아요수를 수집합니다.

    Args:
        driver: 초기화된 Selenium Chrome 드라이버
        url: 네이버 카페 게시글 URL
        wait_seconds: iframe/본문 로딩 대기 시간

    Returns:
        dict: {
            "url": str,
            "cafe_slug": str,
            "article_id": str,
            "title": str,
            "views": int,
            "comments": int,
            "likes": int,
            "error": str,
        }
    """
    cafe_slug, article_id = parse_cafe_article_url(url)
    result = CafePostMetrics(
        url=url,
        cafe_slug=cafe_slug,
        article_id=article_id,
        title="(제목 미확인)",
        views=0,
        comments=0,
        likes=0,
    )

    try:
        driver.get(url)
        WebDriverWait(driver, wait_seconds).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        time.sleep(1.0)

        switched_to_frame = False
        try:
            WebDriverWait(driver, wait_seconds).until(
                EC.frame_to_be_available_and_switch_to_it((By.ID, "cafe_main"))
            )
            switched_to_frame = True
        except TimeoutException:
            # 일부 모바일/SPA URL은 iframe 없이 본문이 노출될 수 있어 현재 문서에서 계속 시도합니다.
            switched_to_frame = False

        WebDriverWait(driver, max(3, wait_seconds // 2)).until(lambda d: d.find_elements(By.CSS_SELECTOR, "body"))
        time.sleep(0.5)

        title = _first_text_by_selectors(driver, TITLE_SELECTORS)
        if title:
            result.title = title

        # CSS 선택자로 먼저 시도하고, 실패한 지표는 전체 텍스트/HTML 정규식으로 보강합니다.
        result.views = _count_by_selectors(driver, "views")
        result.comments = _count_by_selectors(driver, "comments")
        result.likes = _count_by_selectors(driver, "likes")

        html = driver.page_source or ""
        visible_text = driver.execute_script("return document.body ? document.body.innerText : '';") or ""
        fallback_counts = extract_counts_from_html(html, visible_text)
        result.views = result.views or fallback_counts["views"]
        result.comments = result.comments or fallback_counts["comments"]
        result.likes = result.likes or fallback_counts["likes"]

        if switched_to_frame:
            driver.switch_to.default_content()

        if result.title == "(제목 미확인)":
            raw_title = (driver.title or "").replace(" : 네이버 카페", "").strip()
            if raw_title:
                result.title = raw_title

    except (TimeoutException, WebDriverException, Exception) as exc:  # noqa: BLE001 - CLI에서 오류 문자열을 반환하기 위함
        result.error = f"{type(exc).__name__}: {exc}"
        try:
            driver.switch_to.default_content()
        except Exception:  # noqa: BLE001
            pass

    return asdict(result)


def collect_cafe_post_metrics(driver: webdriver.Chrome, urls: Iterable[str], wait_seconds: int = 10) -> list[dict]:
    """여러 게시글 URL의 지표를 순서대로 수집합니다."""
    rows: list[dict] = []
    for url in urls:
        rows.append(get_cafe_post_info(driver, url, wait_seconds=wait_seconds))
    return rows


def save_metrics_csv(rows: list[dict], output_path: str | Path) -> Path:
    """수집 결과를 CSV로 저장합니다."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["url", "cafe_slug", "article_id", "title", "views", "comments", "likes", "error"]
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path


def _print_table(rows: list[dict]) -> None:
    print("url\tarticle_id\ttitle\tviews\tcomments\tlikes\terror")
    for row in rows:
        print(
            f"{row['url']}\t{row['article_id']}\t{row['title']}\t"
            f"{row['views']}\t{row['comments']}\t{row['likes']}\t{row['error']}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="네이버 카페 게시글 조회수/댓글수/좋아요수 수집")
    parser.add_argument("urls", nargs="+", help="수집할 네이버 카페 게시글 URL")
    parser.add_argument("--output", "-o", default="", help="CSV 저장 경로 예: output/feko_post_metrics.csv")
    parser.add_argument("--headless", action=argparse.BooleanOptionalAction, default=True, help="Chrome headless 실행 여부")
    parser.add_argument("--wait-seconds", type=int, default=10, help="게시글 로딩 대기 시간")
    args = parser.parse_args(argv)

    from naver_cafe_strategy.browser.webdriver import build_driver

    driver = build_driver(headless=args.headless)
    try:
        rows = collect_cafe_post_metrics(driver, args.urls, wait_seconds=args.wait_seconds)
    finally:
        driver.quit()

    _print_table(rows)
    if args.output:
        saved_path = save_metrics_csv(rows, args.output)
        print(f"CSV 저장 완료: {saved_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
