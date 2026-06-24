from __future__ import annotations

import argparse
import csv
from dataclasses import asdict, dataclass
import json
from pathlib import Path

from navercafe_app.browser import build_driver
from navercafe_app.crawlers.article import ArticleCrawler


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
    image_count: int = 0
    error: str = ""


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
    encoding: str = "utf-8",
    limit: int | None = None,
) -> list[PopularArticleDetailRow]:
    source_rows = _read_source_rows(source_path)
    if limit is not None:
        source_rows = source_rows[:limit]
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    driver = build_driver(headless=headless, disable_images=True, timeout=40)
    details: list[PopularArticleDetailRow] = []
    try:
        crawler = ArticleCrawler(driver, timeout=20)
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
                detail = PopularArticleDetailRow(
                    **base,
                    status=status,
                    detail_title=article.title,
                    body_text=article.body_text,
                    body_length=len(article.body_text.strip()),
                    view_count=article.view_count,
                    comment_count=article.comment_count,
                    image_count=len(article.images),
                )
            except Exception as exc:
                detail = PopularArticleDetailRow(**base, status="crawl_error", error=f"{type(exc).__name__}: {exc}")
            details.append(detail)
            print(f"[{index}/{len(source_rows)}] {base['cafe_id']} {base['article_id']} -> {detail.status}")
    finally:
        driver.quit()

    csv_path = output_path / "naver_cafe_popular_article_details.csv"
    json_path = output_path / "naver_cafe_popular_article_details.json"
    fieldnames = list(PopularArticleDetailRow.__dataclass_fields__.keys())
    with csv_path.open("w", encoding=encoding, newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for detail in details:
            writer.writerow(asdict(detail))
    json_path.write_text(json.dumps([asdict(row) for row in details], ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved detail CSV: {csv_path}")
    print(f"Saved detail JSON: {json_path}")
    return details


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Crawl article details from a Naver Cafe popular-list CSV/JSON.")
    parser.add_argument("--source", required=True, help="Popular list CSV/JSON from popular_crawl")
    parser.add_argument("--output", default="output/popular_details", help="Output directory")
    parser.add_argument(
        "--encoding",
        default="utf-8",
        choices=["utf-8", "utf-8-sig", "cp949"],
        help="CSV encoding. Use utf-8 for Google Sheets.",
    )
    parser.add_argument("--limit", type=int, help="Optional max rows for a smoke test")
    parser.add_argument("--headed", action="store_true", help="Run Chrome visibly for debugging")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    rows = crawl_popular_details(
        source_path=args.source,
        output_dir=args.output,
        headless=not args.headed,
        encoding=args.encoding,
        limit=args.limit,
    )
    ok = sum(1 for row in rows if row.status == "public_detail_ok")
    print(f"Popular detail crawl finished: rows={len(rows)}, public_detail_ok={ok}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
