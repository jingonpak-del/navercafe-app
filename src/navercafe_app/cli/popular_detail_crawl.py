from __future__ import annotations

import argparse
import csv
from dataclasses import asdict, dataclass
import json
from pathlib import Path

import requests

from navercafe_app.auth.naver_session import NaverSessionManager
from navercafe_app.browser import build_driver
from navercafe_app.crawlers.article import ArticleCrawler
from navercafe_app.crawlers.comment_api import CommentApiClient
from navercafe_app.crawlers.comments import CommentCrawler
from navercafe_app.models import Comment


@dataclass(slots=True)
class PopularArticleDetailRow:
    cafe_id: str
    page: str
    global_rank: str
    article_id: str
    list_title: str
    url: str
    status: str
    detail_title: str = ""
    body_text: str = ""
    body_length: int = 0
    view_count: int = 0
    comment_count: int = 0
    comments_crawled: int = 0
    comment_authors: str = ""
    comment_texts: str = ""
    comments_json: str = ""
    comment_fetch_source: str = ""
    comment_fetch_error: str = ""
    image_count: int = 0
    error: str = ""


@dataclass(slots=True)
class PopularArticleCommentRow:
    cafe_id: str
    article_id: str
    article_url: str
    list_title: str
    comment_index: int
    author: str = ""
    text: str = ""
    written_at: str = ""
    is_reply: bool = False


def _read_source_rows(path: str | Path) -> list[dict[str, str]]:
    source = Path(path)
    if source.suffix.lower() == ".json":
        data = json.loads(source.read_text(encoding="utf-8"))
        return [{str(k): "" if v is None else str(v) for k, v in row.items()} for row in data]
    for encoding in ("utf-8-sig", "utf-8", "cp949"):
        try:
            with source.open(encoding=encoding, newline="") as f:
                return list(csv.DictReader(f))
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError("unknown", b"", 0, 1, f"지원 인코딩으로 읽을 수 없습니다: {source}")


def _status_from_body(title: str, body_text: str) -> str:
    compact = body_text.strip()
    if len(compact) >= 20:
        return "public_detail_ok"
    if "멤버" in compact or "가입" in compact or "권한" in compact:
        return "login_or_member_required"
    if not compact or title == "네이버 카페":
        return "detail_unavailable"
    return "detail_partial"


def crawl_popular_details(
    source_path: str | Path,
    output_dir: str | Path = "output/popular_details",
    headless: bool = True,
    encoding: str = "utf-8-sig",
    limit: int | None = None,
    api_comments: bool = True,
    env_path: str | Path = ".env",
    force_login: bool = False,
) -> list[PopularArticleDetailRow]:
    source_rows = _read_source_rows(source_path)
    if limit is not None:
        source_rows = source_rows[:limit]
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    driver = build_driver(headless=headless, disable_images=True, timeout=40)
    details: list[PopularArticleDetailRow] = []
    comment_rows: list[PopularArticleCommentRow] = []
    try:
        crawler = ArticleCrawler(driver, timeout=20)
        selenium_comment_crawler = CommentCrawler(driver, timeout=15)
        comment_api = _build_comment_api_client(env_path=env_path, headless=headless, force_login=force_login) if api_comments else None
        for index, row in enumerate(source_rows, start=1):
            base = {
                "cafe_id": row.get("cafe_id", ""),
                "page": row.get("page", ""),
                "global_rank": row.get("global_rank", ""),
                "article_id": row.get("article_id", ""),
                "list_title": row.get("title", ""),
                "url": row.get("url", ""),
            }
            try:
                article = crawler.crawl(base["url"])
                status = _status_from_body(article.title, article.body_text)
                comments, comment_source, comment_error = _crawl_comments(
                    article_url=base["url"],
                    cafe_id=base["cafe_id"],
                    article_id=base["article_id"],
                    article_comment_count=article.comment_count,
                    api_client=comment_api,
                    selenium_crawler=selenium_comment_crawler,
                )
                comment_rows.extend(_to_comment_rows(base, comments))
                detail = PopularArticleDetailRow(
                    **base,
                    status=status,
                    detail_title=article.title,
                    body_text=article.body_text,
                    body_length=len(article.body_text.strip()),
                    view_count=article.view_count,
                    comment_count=article.comment_count,
                    comments_crawled=len(comments),
                    comment_authors=" | ".join(comment.author for comment in comments if comment.author),
                    comment_texts="\n---\n".join(comment.text for comment in comments if comment.text),
                    comments_json=json.dumps([asdict(comment) for comment in comments], ensure_ascii=False),
                    comment_fetch_source=comment_source,
                    comment_fetch_error=comment_error,
                    image_count=len(article.images),
                )
            except Exception as exc:
                detail = PopularArticleDetailRow(**base, status="crawl_error", error=f"{type(exc).__name__}: {exc}")
            details.append(detail)
            print(
                f"[{index}/{len(source_rows)}] {base['cafe_id']} {base['article_id']} "
                f"-> {detail.status}, comments={detail.comments_crawled}, comment_source={detail.comment_fetch_source}"
            )
    finally:
        driver.quit()

    csv_path = output_path / "naver_cafe_popular_article_details.csv"
    json_path = output_path / "naver_cafe_popular_article_details.json"
    comments_csv_path = output_path / "naver_cafe_popular_article_comments.csv"
    comments_json_path = output_path / "naver_cafe_popular_article_comments.json"

    fieldnames = list(PopularArticleDetailRow.__dataclass_fields__.keys())
    with csv_path.open("w", encoding=encoding, newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for detail in details:
            writer.writerow(asdict(detail))
    json_path.write_text(json.dumps([asdict(row) for row in details], ensure_ascii=False, indent=2), encoding="utf-8")

    comment_fieldnames = list(PopularArticleCommentRow.__dataclass_fields__.keys())
    with comments_csv_path.open("w", encoding=encoding, newline="") as f:
        writer = csv.DictWriter(f, fieldnames=comment_fieldnames)
        writer.writeheader()
        for comment_row in comment_rows:
            writer.writerow(asdict(comment_row))
    comments_json_path.write_text(
        json.dumps([asdict(row) for row in comment_rows], ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"Saved detail CSV: {csv_path}")
    print(f"Saved detail JSON: {json_path}")
    print(f"Saved comments CSV: {comments_csv_path}")
    print(f"Saved comments JSON: {comments_json_path}")
    return details


def _build_comment_api_client(env_path: str | Path, headless: bool, force_login: bool) -> CommentApiClient:
    try:
        session = NaverSessionManager(env_path=env_path).get_requests_session(force_login=force_login, headless=headless)
    except Exception as exc:
        print(f"Comment API will run without login cookies: {type(exc).__name__}: {exc}")
        session = requests.Session()
    return CommentApiClient(session=session)


def _crawl_comments(
    article_url: str,
    cafe_id: str,
    article_id: str,
    article_comment_count: int,
    api_client: CommentApiClient | None,
    selenium_crawler: CommentCrawler,
) -> tuple[list[Comment], str, str]:
    if api_client is not None:
        result = api_client.fetch(article_url, cafe_id=cafe_id, article_id=article_id)
        if result.ok:
            return result.comments, "api", ""
        if article_comment_count <= 0:
            return [], "api", result.error

    try:
        comments = selenium_crawler.crawl(article_url)
        return comments, "selenium_fallback", ""
    except Exception as exc:
        return [], "selenium_fallback", f"{type(exc).__name__}: {exc}"


def _to_comment_rows(base: dict[str, str], comments: list[Comment]) -> list[PopularArticleCommentRow]:
    return [
        PopularArticleCommentRow(
            cafe_id=base["cafe_id"],
            article_id=base["article_id"],
            article_url=base["url"],
            list_title=base["list_title"],
            comment_index=index,
            author=comment.author,
            text=comment.text,
            written_at=comment.written_at,
            is_reply=comment.is_reply,
        )
        for index, comment in enumerate(comments, start=1)
    ]


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Crawl article details from a Naver Cafe popular-list CSV/JSON.")
    parser.add_argument("--source", required=True, help="Popular list CSV/JSON from popular_crawl")
    parser.add_argument("--output", default="output/popular_details", help="Output directory")
    parser.add_argument(
        "--encoding",
        default="utf-8-sig",
        choices=["utf-8", "utf-8-sig", "cp949"],
        help="CSV encoding. Default utf-8-sig opens cleanly in Excel; use utf-8 for Google Sheets.",
    )
    parser.add_argument("--limit", type=int, help="Optional max rows for a smoke test")
    parser.add_argument("--headed", action="store_true", help="Run Chrome visibly for debugging")
    parser.add_argument("--env", default=".env", help="Path to .env containing NAVER_ID/NAVER_PW/NAVER_SESSION_KEY")
    parser.add_argument("--force-login", action="store_true", help="Refresh Naver cookies before API calls")
    parser.add_argument("--no-api-comments", action="store_true", help="Disable comment API and use Selenium only")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    rows = crawl_popular_details(
        source_path=args.source,
        output_dir=args.output,
        headless=not args.headed,
        encoding=args.encoding,
        limit=args.limit,
        api_comments=not args.no_api_comments,
        env_path=args.env,
        force_login=args.force_login,
    )
    ok = sum(1 for row in rows if row.status == "public_detail_ok")
    comments = sum(row.comments_crawled for row in rows)
    print(f"Popular detail crawl finished: rows={len(rows)}, public_detail_ok={ok}, comments={comments}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
