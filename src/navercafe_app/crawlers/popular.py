from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import csv
import json
import re
import time

from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from ..cafe_urls import extract_article_id
from ..models import ArticleListItem
from ..parsers import parse_int


POPULAR_URL_RE = re.compile(r"/cafes/(?P<cafe_id>\d+)/popular")


@dataclass(slots=True)
class PopularArticleRow:
    cafe_id: str
    page: int
    rank_on_page: int
    global_rank: int
    article_id: str
    title: str
    url: str
    author: str = ""
    written_at: str = ""
    view_count: int = 0
    comment_count: int = 0


def extract_cafe_id_from_popular_url(url: str) -> str:
    match = POPULAR_URL_RE.search(url)
    if not match:
        raise ValueError(f"인기글 URL에서 cafe_id를 찾을 수 없습니다: {url}")
    return match.group("cafe_id")


def normalize_popular_url(url_or_cafe_id: str) -> str:
    """Return the Vue app URL that renders a cafe's popular list.

    The public f-e URL embeds an iframe.  The inner ca-fe URL is easier and more
    stable for Selenium because it directly exposes the table and pagination.
    """
    value = str(url_or_cafe_id).strip()
    if value.isdigit():
        cafe_id = value
    else:
        cafe_id = extract_cafe_id_from_popular_url(value)
    return f"https://cafe.naver.com/ca-fe/cafes/{cafe_id}/popular"


def _absolute_url(href: str) -> str:
    if href.startswith("http://") or href.startswith("https://"):
        return href
    if href.startswith("/"):
        return "https://cafe.naver.com" + href
    return "https://cafe.naver.com/" + href.lstrip("/")


def _same_page(a: list[PopularArticleRow], b: list[PopularArticleRow]) -> bool:
    return bool(a and b) and [row.article_id for row in a] == [row.article_id for row in b]


class PopularBoardCrawler:
    """Crawl Naver Cafe /popular pages rendered by the ca-fe Vue app."""

    def __init__(self, driver, timeout: int = 20, page_wait_seconds: float = 1.0):
        self.driver = driver
        self.timeout = timeout
        self.page_wait_seconds = page_wait_seconds

    def crawl(self, url_or_cafe_id: str, pages: int = 2) -> list[PopularArticleRow]:
        if pages < 1:
            return []
        url = normalize_popular_url(url_or_cafe_id)
        cafe_id = extract_cafe_id_from_popular_url(url)
        self.driver.get(url)
        self._wait_for_board_or_empty()

        rows: list[PopularArticleRow] = []
        seen_pages: set[tuple[str, ...]] = set()
        for page in range(1, pages + 1):
            current = self._extract_current_page(cafe_id=cafe_id, page=page)
            signature = tuple(row.article_id for row in current)
            if not current or signature in seen_pages:
                break
            seen_pages.add(signature)
            rows.extend(current)
            if page >= pages:
                break
            if not self._move_to_page(page + 1, before=current):
                break
        for index, row in enumerate(rows, start=1):
            row.global_rank = index
        return rows

    def _wait_for_board_or_empty(self) -> None:
        def loaded(driver) -> bool:
            return bool(
                driver.find_elements(By.CSS_SELECTOR, ".ArticleBoard tbody tr")
                or driver.find_elements(By.CSS_SELECTOR, ".nodata")
                or "멤버만 볼 수 있습니다" in driver.page_source
            )

        WebDriverWait(self.driver, self.timeout).until(loaded)
        time.sleep(self.page_wait_seconds)

    def _extract_current_page(self, cafe_id: str, page: int) -> list[PopularArticleRow]:
        rows: list[PopularArticleRow] = []
        table_rows = self.driver.find_elements(By.CSS_SELECTOR, ".ArticleBoard tbody tr")
        for rank_on_page, row in enumerate(table_rows, start=1):
            try:
                link = row.find_element(By.CSS_SELECTOR, "a.article, a[href*='/articles/']")
            except Exception:
                continue
            href = _absolute_url(link.get_attribute("href") or "")
            article_id = extract_article_id(href)
            title = link.text.strip()
            if not article_id or not title:
                continue
            rows.append(
                PopularArticleRow(
                    cafe_id=cafe_id,
                    page=page,
                    rank_on_page=rank_on_page,
                    global_rank=0,
                    article_id=article_id,
                    title=title,
                    url=href,
                    author=self._text_or_empty(row, ".td_name .nickname, .ArticleBoardWriterInfo .nickname"),
                    written_at=self._text_or_empty(row, ".td_date"),
                    view_count=parse_int(self._text_or_empty(row, ".td_view")),
                    comment_count=self._extract_comment_count(row),
                )
            )
        return rows

    @staticmethod
    def _text_or_empty(root, selector: str) -> str:
        try:
            return root.find_element(By.CSS_SELECTOR, selector).text.strip()
        except Exception:
            return ""

    @staticmethod
    def _extract_comment_count(root) -> int:
        selectors = [".comment", "a[href*='commentFocus']", "[class*='comment']"]
        for selector in selectors:
            try:
                text = root.find_element(By.CSS_SELECTOR, selector).text.strip()
            except Exception:
                continue
            value = parse_int(text)
            if value:
                return value
        return 0

    def _move_to_page(self, page: int, before: list[PopularArticleRow]) -> bool:
        selectors = [
            f"button[aria-label='{page}페이지']",
            f"a[aria-label='{page}페이지']",
            ".paginate_area button",
            ".paginate_area a",
        ]
        candidates = []
        for selector in selectors:
            candidates.extend(self.driver.find_elements(By.CSS_SELECTOR, selector))
        for element in candidates:
            if element.text.strip() != str(page) and element.get_attribute("aria-label") != f"{page}페이지":
                continue
            try:
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
                self.driver.execute_script("arguments[0].click();", element)
                WebDriverWait(self.driver, self.timeout).until(
                    lambda _driver: not _same_page(before, self._extract_current_page(cafe_id=before[0].cafe_id, page=page))
                )
                time.sleep(self.page_wait_seconds)
                return True
            except TimeoutException:
                return False
            except Exception:
                continue
        return False


def write_popular_rows(
    rows: list[PopularArticleRow], output_dir: str | Path, encoding: str = "utf-8"
) -> tuple[Path, Path]:
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)
    csv_path = path / "naver_cafe_popular_articles.csv"
    json_path = path / "naver_cafe_popular_articles.json"
    fieldnames = list(PopularArticleRow.__dataclass_fields__.keys())
    with csv_path.open("w", newline="", encoding=encoding) as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))
    json_path.write_text(json.dumps([asdict(row) for row in rows], ensure_ascii=False, indent=2), encoding="utf-8")
    return csv_path, json_path


def to_article_list_items(rows: list[PopularArticleRow]) -> list[ArticleListItem]:
    return [
        ArticleListItem(
            title=row.title,
            url=row.url,
            article_id=row.article_id,
            author=row.author,
            written_at=row.written_at,
            view_count=row.view_count,
            comment_count=row.comment_count,
        )
        for row in rows
    ]
