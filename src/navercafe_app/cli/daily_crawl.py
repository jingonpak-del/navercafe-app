from __future__ import annotations

import argparse
import csv
import random
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

from navercafe_app.auth.naver_session import NaverSessionManager
from navercafe_app.cafe_urls import extract_article_id
from navercafe_app.config.targets import BoardTarget, CafeTarget, load_targets
from navercafe_app.crawlers.article import ArticleCrawler
from navercafe_app.crawlers.board import BoardCrawler
from navercafe_app.crawlers.comments import CommentCrawler
from navercafe_app.models import Article, ArticleListItem, Comment
from navercafe_app.storage.sqlite_store import SQLiteStore


@dataclass(slots=True)
class DailyCrawlResult:
    cafes: int = 0
    boards: int = 0
    listed_articles: int = 0
    new_articles: int = 0
    detail_articles: int = 0
    comments: int = 0
    errors: list[str] | None = None

    def __post_init__(self) -> None:
        if self.errors is None:
            self.errors = []


@dataclass(slots=True)
class CollectedArticleRow:
    cafe_id: str
    cafe_name: str
    menu_id: str
    board_name: str
    article_id: str
    title: str
    url: str
    author: str = ""
    written_at: str = ""
    view_count: int = 0
    comment_count: int = 0
    body_text: str = ""


class DailyCrawler:
    def __init__(
        self,
        store: SQLiteStore,
        driver,
        board_crawler_factory: Callable[[object], BoardCrawler] = BoardCrawler,
        article_crawler_factory: Callable[[object], ArticleCrawler] = ArticleCrawler,
        comment_crawler_factory: Callable[[object], CommentCrawler] = CommentCrawler,
    ):
        self.store = store
        self.driver = driver
        self.board_crawler = board_crawler_factory(driver)
        self.article_crawler = article_crawler_factory(driver)
        self.comment_crawler = comment_crawler_factory(driver)
        self.rows: list[CollectedArticleRow] = []

    def crawl(self, targets, export_dir: str | Path | None = None) -> DailyCrawlResult:
        result = DailyCrawlResult(cafes=len(targets.targets))
        for cafe in targets.targets:
            cafe_id = self._resolve_cafe_id(cafe)
            self.store.upsert_cafe(cafe_id, cafe.cafe_slug, cafe.cafe_url, cafe.name)
            for board in cafe.boards:
                result.boards += 1
                try:
                    self._crawl_board(targets.defaults, cafe, cafe_id, board, result)
                except Exception as exc:
                    result.errors.append(f"{cafe.name}/{board.name}: {exc}")
        if export_dir:
            self.export_csv(export_dir)
        return result

    def export_csv(self, export_dir: str | Path) -> Path:
        path = Path(export_dir)
        path.mkdir(parents=True, exist_ok=True)
        out = path / "daily_articles.csv"
        with out.open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "cafe_id",
                    "cafe_name",
                    "menu_id",
                    "board_name",
                    "article_id",
                    "title",
                    "url",
                    "author",
                    "written_at",
                    "view_count",
                    "comment_count",
                    "body_text",
                ],
            )
            writer.writeheader()
            for row in self.rows:
                writer.writerow(asdict(row))
        return out

    def _crawl_board(self, defaults, cafe: CafeTarget, cafe_id: str, board: BoardTarget, result: DailyCrawlResult) -> None:
        menu_id = board.storage_menu_id
        self.store.upsert_board(cafe_id, menu_id, board.name, board.board_url)
        max_pages = board.max_pages or defaults.max_pages_per_board
        include_comments = defaults.include_comments if board.include_comments is None else board.include_comments
        include_images = defaults.include_images if board.include_images is None else board.include_images
        seen_ids = self.store.get_last_seen_article_ids(cafe_id, menu_id)

        for page in range(1, max_pages + 1):
            items = self._crawl_board_items(cafe_id, menu_id, board, page)
            result.listed_articles += len(items)
            if not items:
                break
            for item in items:
                article_id = item.article_id or extract_article_id(item.url)
                if not article_id:
                    continue
                is_new = article_id not in seen_ids
                self.store.upsert_article_list_item(cafe_id, menu_id, item)
                if not is_new:
                    continue
                result.new_articles += 1
                detail = self._safe_article_detail(item, include_images=include_images)
                if detail:
                    result.detail_articles += 1
                    self.store.upsert_article_detail(cafe_id, menu_id, article_id, detail)
                    self.rows.append(
                        CollectedArticleRow(
                            cafe_id=cafe_id,
                            cafe_name=cafe.name,
                            menu_id=menu_id,
                            board_name=board.name,
                            article_id=article_id,
                            title=detail.title or item.title,
                            url=detail.url or item.url,
                            author=detail.author or item.author,
                            written_at=detail.written_at or item.written_at,
                            view_count=detail.view_count or item.view_count,
                            comment_count=detail.comment_count or item.comment_count,
                            body_text=detail.body_text,
                        )
                    )
                else:
                    self.rows.append(
                        CollectedArticleRow(
                            cafe_id=cafe_id,
                            cafe_name=cafe.name,
                            menu_id=menu_id,
                            board_name=board.name,
                            article_id=article_id,
                            title=item.title,
                            url=item.url,
                            author=item.author,
                            written_at=item.written_at,
                            view_count=item.view_count,
                            comment_count=item.comment_count,
                        )
                    )
                if include_comments:
                    comments = self._safe_comments(item.url)
                    for comment in comments:
                        self.store.upsert_comment(cafe_id, article_id, comment)
                    result.comments += len(comments)
            delay = random.uniform(defaults.delay_seconds.min, defaults.delay_seconds.max)
            time.sleep(delay)

    def _crawl_board_items(self, cafe_id: str, menu_id: str, board: BoardTarget, page: int) -> list[ArticleListItem]:
        if board.type == "popular" or (board.board_url and not board.menu_id):
            # Naver f-e popular pages are special pages, not normal menu boards.
            # They do not have search.menuid; crawl the rendered URL directly.
            if page > 1:
                return []
            return self.board_crawler.crawl_url(board.board_url)
        return self.board_crawler.crawl_page(cafe_id, menu_id, page=page)

    def _safe_article_detail(self, item: ArticleListItem, include_images: bool = False) -> Article | None:
        try:
            article = self.article_crawler.crawl(item.url)
            if not include_images:
                article.images.clear()
            return article
        except Exception:
            return None

    def _safe_comments(self, article_url: str) -> list[Comment]:
        try:
            return self.comment_crawler.crawl(article_url)
        except Exception:
            return []

    @staticmethod
    def _resolve_cafe_id(cafe: CafeTarget) -> str:
        if cafe.cafe_id:
            return cafe.cafe_id
        try:
            from naver_cafe_strategy.cafe.cafe_info import get_cafe_id

            cafe_id = get_cafe_id(cafe.cafe_url)
        except Exception:
            cafe_id = None
        if not cafe_id:
            raise ValueError(f"cafe_id를 확인할 수 없습니다: {cafe.name or cafe.cafe_url}")
        return str(cafe_id)


def run_daily_crawl(
    targets_path: str | Path,
    env_path: str | Path = ".env",
    db_path: str | Path = "data/naver_cafe_daily.sqlite",
    export_dir: str | Path | None = "output/daily",
    headless: bool = True,
    force_login: bool = False,
) -> DailyCrawlResult:
    targets = load_targets(targets_path)
    store = SQLiteStore(db_path)
    run = store.start_run(target_summary=f"{len(targets.targets)} cafes")
    manager = NaverSessionManager(env_path=env_path)
    driver = None
    try:
        manager.ensure_login(force_login=force_login, headless=headless)
        driver = manager.get_driver(headless=headless, with_login=True)
        crawler = DailyCrawler(store, driver)
        result = crawler.crawl(targets, export_dir=export_dir)
        status = "success" if not result.errors else "partial_success"
        store.finish_run(run.run_id, status=status, error="\n".join(result.errors or []))
        return result
    except Exception as exc:
        store.finish_run(run.run_id, status="failed", error=str(exc))
        raise
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass
        store.close()


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Daily crawler for login-required Naver Cafe boards.")
    parser.add_argument("--targets", default="config/cafe_targets.yaml", help="YAML/JSON target config path")
    parser.add_argument("--env", default=".env", help="dotenv file containing NAVER_ID/NAVER_PW")
    parser.add_argument("--db", default="data/naver_cafe_daily.sqlite", help="SQLite output database")
    parser.add_argument("--export", default="output/daily", help="CSV export directory; use '' to disable")
    parser.add_argument("--headed", action="store_true", help="Run Chrome with a visible window for CAPTCHA/2FA/manual checks")
    parser.add_argument("--force-login", action="store_true", help="Ignore stored cookies and perform Selenium login")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    result = run_daily_crawl(
        targets_path=args.targets,
        env_path=args.env,
        db_path=args.db,
        export_dir=args.export or None,
        headless=not args.headed,
        force_login=args.force_login,
    )
    print(
        "Daily crawl finished: "
        f"cafes={result.cafes}, boards={result.boards}, listed={result.listed_articles}, "
        f"new={result.new_articles}, details={result.detail_articles}, comments={result.comments}, "
        f"errors={len(result.errors or [])}"
    )
    for error in result.errors or []:
        print(f"ERROR: {error}")
    return 0 if not result.errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
