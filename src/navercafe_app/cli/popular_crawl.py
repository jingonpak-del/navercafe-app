from __future__ import annotations

import argparse
from pathlib import Path

from navercafe_app.browser import build_driver
from navercafe_app.crawlers.popular import PopularArticleRow, PopularBoardCrawler, write_popular_rows

DEFAULT_POPULAR_URLS = [
    "https://cafe.naver.com/f-e/cafes/14793916/popular",
    "https://cafe.naver.com/f-e/cafes/10912875/popular",
    "https://cafe.naver.com/f-e/cafes/29434212/popular",
    "https://cafe.naver.com/f-e/cafes/10094499/popular",
    "https://cafe.naver.com/f-e/cafes/12182370/popular",
    "https://cafe.naver.com/f-e/cafes/23593632/popular",
    "https://cafe.naver.com/f-e/cafes/20655292/popular",
    "https://cafe.naver.com/f-e/cafes/10050813/popular",
    "https://cafe.naver.com/f-e/cafes/23451561/popular",
    "https://cafe.naver.com/f-e/cafes/22897837/popular",
]


def read_urls(path: str | Path | None) -> list[str]:
    if not path:
        return DEFAULT_POPULAR_URLS.copy()
    rows = Path(path).read_text(encoding="utf-8").splitlines()
    return [row.strip() for row in rows if row.strip() and not row.strip().startswith("#")]


def crawl_popular_urls(
    urls: list[str],
    pages: int = 2,
    output_dir: str | Path = "output/popular",
    headless: bool = True,
    encoding: str = "utf-8-sig",
) -> list[PopularArticleRow]:
    driver = build_driver(headless=headless, disable_images=True, timeout=40)
    rows: list[PopularArticleRow] = []
    try:
        crawler = PopularBoardCrawler(driver, timeout=25)
        for url in urls:
            cafe_rows = crawler.crawl(url, pages=pages)
            rows.extend(cafe_rows)
            print(f"{url} -> {len(cafe_rows)} rows")
    finally:
        driver.quit()
    csv_path, json_path = write_popular_rows(rows, output_dir, encoding=encoding)
    print(f"Saved CSV: {csv_path}")
    print(f"Saved JSON: {json_path}")
    return rows


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Crawl Naver Cafe popular article lists.")
    parser.add_argument("--urls", help="Text file containing one popular URL per line. Defaults to the 10 target cafes.")
    parser.add_argument("--pages", type=int, default=2, help="Number of visible popular-list pages to collect per cafe")
    parser.add_argument("--output", default="output/popular", help="Output directory for CSV/JSON files")
    parser.add_argument(
        "--encoding",
        default="utf-8-sig",
        choices=["utf-8", "utf-8-sig", "cp949"],
        help="CSV encoding. Default utf-8-sig opens cleanly in Excel; use utf-8 for Google Sheets.",
    )
    parser.add_argument("--headed", action="store_true", help="Run Chrome visibly for debugging")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    urls = read_urls(args.urls)
    rows = crawl_popular_urls(
        urls,
        pages=args.pages,
        output_dir=args.output,
        headless=not args.headed,
        encoding=args.encoding,
    )
    print(f"Popular crawl finished: cafes={len(urls)}, rows={len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
