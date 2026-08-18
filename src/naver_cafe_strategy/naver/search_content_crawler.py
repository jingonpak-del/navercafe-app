# -*- coding: utf-8 -*-
"""
네이버 통합검색 1페이지에서 블로그/카페 결과만 수집하고 본문을 크롤링하는 재사용 모듈.

주요 기능:
    1. naver.com 검색창에 키워드를 입력해 검색 실행
    2. 첫 페이지 검색 결과에서 광고/플레이스/웹사이트를 제외
    3. 블로그(blog.naver.com)와 카페(cafe.naver.com) 게시글 링크만 추출
    4. 각 게시글의 링크, 제목, 본문을 Selenium으로 크롤링

주의:
    - 네이버 검색 DOM은 자주 바뀌므로 URL 패턴 + 섹션 텍스트 기반으로 최대한 보수적으로 필터링합니다.
    - 비공개/멤버공개 카페 글은 로그인 세션이 있는 driver에서만 본문 수집이 가능합니다.
    - 과도한 요청은 서비스 정책 위반이 될 수 있으니 delay_seconds를 두고 소량 수집에 사용하세요.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
import csv
import json
import re
import time
from pathlib import Path
from typing import Iterable, Literal
from urllib.parse import parse_qs, quote_plus, urlparse

from bs4 import BeautifulSoup
from selenium.common.exceptions import NoSuchElementException, TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

ContentType = Literal["blog", "cafe"]

_SEARCH_URL = "https://search.naver.com/search.naver?where=nexearch&query={query}"
_BLOCKED_SECTION_KEYWORDS = (
    "관련 광고",
    "파워링크",
    "비즈사이트",
    "플레이스",
    "웹사이트",
    "사이트",
    "지식iN",
)
_NAVER_UTILITY_PATHS = (
    "/MyBlog.naver",
    "/",
)


@dataclass(slots=True)
class SearchContentItem:
    """검색 결과에서 발견한 블로그/카페 게시글 후보."""

    content_type: ContentType
    url: str
    title: str
    snippet: str = ""
    source: str = "naver_search"
    rank: int = 0


@dataclass(slots=True)
class CrawledContent:
    """게시글 상세 페이지 크롤링 결과."""

    content_type: ContentType
    url: str
    title: str
    body: str
    search_title: str = ""
    search_snippet: str = ""
    rank: int = 0
    ok: bool = True
    error: str = ""
    meta: dict[str, str | int] = field(default_factory=dict)


def build_search_url(keyword: str, *, where: str = "nexearch", start: int = 1) -> str:
    """네이버 검색 URL을 생성합니다.

    ``where=nexearch`` 는 통합검색, ``where=article`` 은 카페 탭을 뜻합니다.
    ``start`` 는 네이버가 사용하는 1-based 결과 offset입니다.
    """

    query = quote_plus(keyword)
    return f"https://search.naver.com/search.naver?where={where}&query={query}&start={max(1, start)}"


def search_from_naver_home(driver, keyword: str, timeout: int = 10) -> None:
    """naver.com에 접속한 뒤 검색창에 키워드를 입력해 검색합니다.

    검색창 DOM이 변경되거나 자동화 환경에서 홈 검색이 실패할 경우 직접 검색 URL로 폴백합니다.
    """

    driver.get("https://www.naver.com")
    try:
        search_box = WebDriverWait(driver, timeout).until(
            lambda d: d.find_element(By.CSS_SELECTOR, "input[name='query'], #query")
        )
        search_box.clear()
        search_box.send_keys(keyword)
        search_box.send_keys(Keys.ENTER)
        WebDriverWait(driver, timeout).until(lambda d: "search.naver.com/search.naver" in d.current_url)
    except Exception:
        driver.get(build_search_url(keyword))

    WebDriverWait(driver, timeout).until(lambda d: d.find_elements(By.CSS_SELECTOR, "body a[href]"))
    time.sleep(0.8)


def normalize_naver_url(url: str) -> str:
    """비교/중복 제거용으로 URL의 fragment와 일부 추적성 query를 정리합니다."""

    parsed = urlparse(url)
    if parsed.netloc.endswith("blog.naver.com"):
        post = parse_blog_identity(url)
        if post:
            blog_id, log_no = post
            return f"https://blog.naver.com/{blog_id}/{log_no}"
    if parsed.netloc.endswith("cafe.naver.com"):
        cafe = parse_cafe_identity(url)
        if cafe:
            cafe_name, article_id = cafe
            return f"https://cafe.naver.com/{cafe_name}/{article_id}"
    return parsed._replace(fragment="").geturl().rstrip("/")


def parse_blog_identity(url: str) -> tuple[str, str] | None:
    """네이버 블로그 URL에서 (blog_id, log_no)를 추출합니다."""

    parsed = urlparse(url)
    if not parsed.netloc.endswith("blog.naver.com"):
        return None

    query = parse_qs(parsed.query)
    if "blogId" in query and "logNo" in query:
        return query["blogId"][0], query["logNo"][0]

    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) >= 2 and parts[1].isdigit():
        return parts[0], parts[1]
    return None


def parse_cafe_identity(url: str) -> tuple[str, str] | None:
    """네이버 카페 URL에서 (cafe_name, article_id)를 추출합니다."""

    parsed = urlparse(url)
    if not parsed.netloc.endswith("cafe.naver.com"):
        return None
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) >= 2 and parts[1].isdigit():
        return parts[0], parts[1]
    return None


def content_type_from_url(url: str) -> ContentType | None:
    """URL이 수집 대상 블로그/카페 게시글인지 판별합니다."""

    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if host.endswith("blog.naver.com") and parse_blog_identity(url):
        return "blog"
    if host.endswith("cafe.naver.com") and parse_cafe_identity(url):
        return "cafe"
    return None


def is_excluded_section_text(text: str) -> bool:
    """광고/플레이스/웹사이트 등 제외해야 하는 검색 섹션인지 판별합니다."""

    compact = re.sub(r"\s+", "", text or "")
    return any(keyword.replace(" ", "") in compact for keyword in _BLOCKED_SECTION_KEYWORDS)


def _nearest_search_block(anchor) -> BeautifulSoup:
    """검색 결과 한 건에 가까운 부모 블록을 찾습니다."""

    selectors = ["li", "div", "section"]
    node = anchor
    for _ in range(8):
        node = node.parent
        if node is None:
            break
        name = getattr(node, "name", "")
        if name in selectors:
            text = node.get_text(" ", strip=True)
            if len(text) >= len(anchor.get_text(" ", strip=True)):
                return node
    return anchor.parent or anchor


def _section_text(anchor) -> str:
    """광고/플레이스/웹사이트 제외 판정을 위한 상위 섹션 텍스트를 반환합니다."""

    node = anchor
    for _ in range(10):
        node = node.parent
        if node is None:
            break
        classes = " ".join(node.get("class", []))
        if node.name == "section" or "api_subject_bx" in classes or "sc_new" in classes:
            return node.get_text(" ", strip=True)
    return ""


def _build_search_content_item(anchor, *, rank: int) -> SearchContentItem | None:
    """링크 1개를 검색 결과 아이템으로 변환합니다."""

    href = anchor.get("href", "").strip()
    ctype = content_type_from_url(href)
    if not ctype:
        return None

    parsed = urlparse(href)
    if parsed.path in _NAVER_UTILITY_PATHS:
        return None

    section = _section_text(anchor)
    if is_excluded_section_text(section):
        return None

    normalized_url = normalize_naver_url(href)
    block = _nearest_search_block(anchor)
    title = anchor.get_text(" ", strip=True)
    if not title or len(title) < 2:
        # 같은 블록 안에서 가장 제목처럼 보이는 링크 텍스트를 보조로 사용
        for candidate in block.select("a[href]"):
            candidate_text = candidate.get_text(" ", strip=True)
            if candidate_text and len(candidate_text) > len(title):
                title = candidate_text
    if not title or title in {"내 블로그", "가입한 카페", "블로그", "카페"}:
        return None
    if title.isdigit() or title.startswith("RE"):
        return None

    snippet = block.get_text(" ", strip=True)
    if snippet.startswith(title):
        snippet = snippet[len(title):].strip()
    return SearchContentItem(
        content_type=ctype,
        url=normalized_url,
        title=title,
        snippet=snippet,
        rank=rank,
    )


def _extract_first_item_from_result_card(card, *, rank: int) -> SearchContentItem | None:
    """검색 결과 카드 하나에서 가장 위의 대표 게시글 1건만 추출합니다.

    네이버 VIEW/인기글 결과는 하나의 노출 카드 안에 대표글, 본문 미리보기 링크,
    댓글 링크, 관련/추가글 링크가 함께 들어올 수 있습니다. SEO 분석 기준의 1페이지
    노출 원고는 카드 최상단 대표글이므로 카드 내부에서는 첫 번째 유효 게시글만 반환합니다.
    """

    for anchor in card.select("a[href]"):
        item = _build_search_content_item(anchor, rank=rank)
        if item is not None:
            return item
    return None


def _result_cards(soup: BeautifulSoup) -> list:
    """네이버 검색 결과에서 개별 노출 카드 후보를 반환합니다."""

    cards = soup.select("._fe_view_power_content, ._fe_view_po")

    unique_cards = []
    seen_ids: set[int] = set()
    for card in cards:
        obj_id = id(card)
        if obj_id not in seen_ids:
            unique_cards.append(card)
            seen_ids.add(obj_id)
    return unique_cards


def extract_blog_cafe_results_from_html(html: str, *, max_items: int | None = None) -> list[SearchContentItem]:
    """네이버 검색 결과 HTML에서 블로그/카페 대표 게시글 링크만 추출합니다.

    광고/플레이스/웹사이트 섹션에 포함된 링크와 네이버 상단 유틸리티 링크는 제외합니다.
    하나의 검색 결과 카드 안에 여러 게시글 링크가 묶여 있으면 가장 위의 대표글 1건만 수집합니다.
    """

    soup = BeautifulSoup(html, "html.parser")
    results: list[SearchContentItem] = []
    seen: set[str] = set()

    cards = _result_cards(soup)
    card_ids = {id(card) for card in cards}
    if cards:
        for card in cards:
            item = _extract_first_item_from_result_card(card, rank=len(results) + 1)
            if item is None or item.url in seen:
                continue
            results.append(item)
            seen.add(item.url)
            if max_items is not None and len(results) >= max_items:
                break

    # 카드 식별자가 없는 일반 VIEW/블로그/카페 섹션 폴백: 링크 단위 추출.
    # 단, 이미 카드 단위로 처리한 영역 내부 링크는 추가글 과수집을 막기 위해 건너뜁니다.
    for anchor in soup.select("a[href]"):
        if any(id(parent) in card_ids for parent in anchor.parents):
            continue
        item = _build_search_content_item(anchor, rank=len(results) + 1)
        if item is None or item.url in seen:
            continue
        results.append(item)
        seen.add(item.url)
        if max_items is not None and len(results) >= max_items:
            break

    return results


def collect_blog_cafe_search_results(driver, keyword: str, *, timeout: int = 10, max_items: int | None = None) -> list[SearchContentItem]:
    """naver.com 검색을 실행하고 첫 페이지의 블로그/카페 게시글 결과를 반환합니다."""

    search_from_naver_home(driver, keyword, timeout=timeout)
    return extract_blog_cafe_results_from_html(driver.page_source, max_items=max_items)


def collect_cafe_results_across_search_surfaces(
    driver,
    keyword: str,
    *,
    pages: int = 10,
    timeout: int = 10,
    delay_seconds: float = 0.4,
    max_items: int | None = None,
) -> list[SearchContentItem]:
    """통합검색과 카페 탭의 지정 페이지에서 공개 카페 결과 후보를 수집합니다.

    검색 DOM/페이지네이션은 자주 바뀌므로 이 함수는 결과 URL의 출처와 페이지를
    ``source`` 에 기록하고, 상세 접근 실패 여부는 이후 ``crawl_detail`` 에 맡깁니다.
    반환값은 검색에 실제 노출된 후보이지 카페 전체 게시물의 완전한 목록이 아닙니다.
    """

    if pages < 1:
        raise ValueError("pages는 1 이상이어야 합니다.")

    results: list[SearchContentItem] = []
    seen: set[str] = set()
    for where, surface in (("nexearch", "integrated"), ("article", "cafe_tab")):
        for page in range(1, pages + 1):
            start = (page - 1) * 10 + 1
            driver.get(build_search_url(keyword, where=where, start=start))
            WebDriverWait(driver, timeout).until(lambda d: d.find_elements(By.CSS_SELECTOR, "body a[href]"))
            time.sleep(delay_seconds)
            for item in extract_blog_cafe_results_from_html(driver.page_source):
                if item.content_type != "cafe" or item.url in seen:
                    continue
                results.append(replace(item, source=f"{surface}:page={page}", rank=len(results) + 1))
                seen.add(item.url)
                if max_items is not None and len(results) >= max_items:
                    return results
    return results


def _switch_to_first_content_frame(driver, timeout: int = 8) -> bool:
    """블로그/카페 본문 iframe(mainFrame/cafe_main)이 있으면 진입합니다."""

    driver.switch_to.default_content()
    frame_selectors = ("iframe#mainFrame", "iframe[name='mainFrame']", "iframe#cafe_main", "iframe[name='cafe_main']")
    for selector in frame_selectors:
        try:
            frame = WebDriverWait(driver, timeout).until(lambda d: d.find_element(By.CSS_SELECTOR, selector))
            driver.switch_to.frame(frame)
            return True
        except (NoSuchElementException, TimeoutException):
            continue
    return False


def _clean_text(text: str) -> str:
    lines = [re.sub(r"\s+", " ", line).strip() for line in (text or "").splitlines()]
    return "\n".join(line for line in lines if line)


def _first_text(soup: BeautifulSoup, selectors: Iterable[str]) -> str:
    for selector in selectors:
        node = soup.select_one(selector)
        if node:
            text = _clean_text(node.get_text("\n", strip=True))
            if text:
                return text
    return ""


def parse_detail_html(html: str, content_type: ContentType, *, fallback_title: str = "") -> tuple[str, str]:
    """블로그/카페 상세 HTML에서 제목과 본문을 추출합니다."""

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.select("script, style, noscript, iframe"):
        tag.decompose()

    if content_type == "blog":
        title = _first_text(
            soup,
            (
                ".se-title-text",
                ".se-title-text span",
                ".pcol1.itemSubjectBoldfont",
                ".htitle .pcol1",
                "h3.se_textarea",
                "title",
            ),
        )
        body = _first_text(
            soup,
            (
                ".se-main-container",
                "#postViewArea",
                ".post_ct",
                ".post-view",
                ".view",
                "article",
                "body",
            ),
        )
    else:
        title = _first_text(
            soup,
            (
                ".title_text",
                ".ArticleTitle .title_text",
                ".tit-box .title",
                "h3.title_text",
                "h1",
                "title",
            ),
        )
        body = _first_text(
            soup,
            (
                ".se-main-container",
                ".article_viewer",
                "#app .article_viewer",
                "#postViewArea",
                ".tbody",
                "article",
                "body",
            ),
        )

    # meta[property='og:title']는 get_text가 비어 있으므로 별도 처리
    if not title:
        og = soup.select_one("meta[property='og:title'], meta[name='title']")
        title = (og.get("content", "") if og else "").strip()

    return title or fallback_title or "(제목 미확인)", body


def crawl_detail(driver, item: SearchContentItem, *, timeout: int = 12) -> CrawledContent:
    """검색 결과 1건의 상세 페이지에 접속해 제목/본문을 수집합니다."""

    try:
        driver.get(item.url)
        WebDriverWait(driver, timeout).until(lambda d: d.find_elements(By.TAG_NAME, "body"))
        time.sleep(0.7)
        _switch_to_first_content_frame(driver, timeout=3)
        html = driver.page_source
        title, body = parse_detail_html(html, item.content_type, fallback_title=item.title)
        driver.switch_to.default_content()
        return CrawledContent(
            content_type=item.content_type,
            url=item.url,
            title=title,
            body=body,
            search_title=item.title,
            search_snippet=item.snippet,
            rank=item.rank,
            ok=bool(body),
            error="" if body else "본문을 찾지 못했습니다. 로그인/권한 또는 DOM 변경 가능성이 있습니다.",
            meta={"body_length": len(body)},
        )
    except WebDriverException as exc:
        try:
            driver.switch_to.default_content()
        except Exception:
            pass
        return CrawledContent(
            content_type=item.content_type,
            url=item.url,
            title=item.title,
            body="",
            search_title=item.title,
            search_snippet=item.snippet,
            rank=item.rank,
            ok=False,
            error=str(exc),
        )


def crawl_naver_search_blog_cafe(
    driver,
    keyword: str,
    *,
    timeout: int = 10,
    max_items: int | None = None,
    delay_seconds: float = 1.0,
) -> list[CrawledContent]:
    """검색부터 상세 본문 수집까지 한 번에 실행하는 고수준 함수."""

    items = collect_blog_cafe_search_results(driver, keyword, timeout=timeout, max_items=max_items)
    crawled: list[CrawledContent] = []
    for item in items:
        crawled.append(crawl_detail(driver, item, timeout=timeout + 2))
        if delay_seconds > 0:
            time.sleep(delay_seconds)
    return crawled


def save_crawled_contents(rows: Iterable[CrawledContent], output_path: str | Path) -> Path:
    """크롤링 결과를 CSV 또는 JSON으로 저장합니다."""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = [asdict(row) for row in rows]
    if path.suffix.lower() == ".json":
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    elif path.suffix.lower() == ".csv":
        fieldnames = list(CrawledContent.__dataclass_fields__.keys())
        with path.open("w", newline="", encoding="utf-8-sig") as fp:
            writer = csv.DictWriter(fp, fieldnames=fieldnames)
            writer.writeheader()
            for row in data:
                row = {**row, "meta": json.dumps(row.get("meta", {}), ensure_ascii=False)}
                writer.writerow(row)
    else:
        raise ValueError("output_path 확장자는 .csv 또는 .json 이어야 합니다.")
    return path


if __name__ == "__main__":
    from naver_cafe_strategy.browser.webdriver import build_driver

    driver = build_driver(headless=True)
    try:
        rows = crawl_naver_search_blog_cafe(driver, "창원 흥신소", max_items=10)
        output = save_crawled_contents(rows, "output/naver_search_blog_cafe_changwon_detective.csv")
        print(f"저장 완료: {output} ({len(rows)}건)")
    finally:
        driver.quit()
