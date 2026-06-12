# -*- coding: utf-8 -*-
"""네이버 키워드 검색 결과 및 원고 SEO 분석 실행 스크립트.

사용 예:
    # 네이버에서 키워드 검색 → 블로그/카페 대표글 크롤링 → SEO 분석 파일 저장
    uv run python scripts/naver_keyword_search_manuscript_analysis.py "부산 흥신소"

    # 최대 수집 수와 출력 prefix 지정
    uv run python scripts/naver_keyword_search_manuscript_analysis.py "창원 흥신소" --max-items 5 --output-prefix changwon_detective

    # 이미 저장된 크롤링 JSON만 다시 분석
    uv run python scripts/naver_keyword_search_manuscript_analysis.py "부산 흥신소" \
      --input-json output/seo_analysis/부산_흥신소_crawled_contents.json
"""

from __future__ import annotations

import argparse
from pathlib import Path

from naver_cafe_strategy.browser.webdriver import build_driver
from naver_cafe_strategy.naver.seo_content_analyzer import (
    SearchSEOAnalysis,
    analyze_crawled_file,
    crawl_and_analyze_search_seo,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="네이버 키워드 검색 1페이지의 블로그/카페 대표글을 크롤링하고 원고 SEO 지표를 분석합니다.",
    )
    parser.add_argument("keyword", help="분석할 네이버 검색 키워드. 예: '부산 흥신소'")
    parser.add_argument(
        "--input-json",
        type=Path,
        default=None,
        help="이미 저장된 *_crawled_contents.json 경로. 지정하면 네이버 재검색 없이 분석만 수행합니다.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output/seo_analysis"),
        help="결과 파일 저장 폴더. 기본값: output/seo_analysis",
    )
    parser.add_argument("--output-prefix", default=None, help="결과 파일명 prefix. 미지정 시 키워드 기반 자동 생성")
    parser.add_argument("--max-items", type=int, default=None, help="최대 수집 대표글 수. 기본값: 제한 없음")
    parser.add_argument("--delay-seconds", type=float, default=1.0, help="상세 페이지 크롤링 간 대기 초. 기본값: 1.0")
    parser.add_argument("--show-browser", action="store_true", help="디버깅용으로 Chrome 창을 표시합니다")
    return parser


def print_analysis_summary(analysis: SearchSEOAnalysis, paths: dict[str, Path] | None = None) -> None:
    """터미널에서 확인하기 쉬운 최소 요약을 출력합니다."""

    print(f"\n[분석 완료] 키워드: {analysis.keyword}")
    print(f"수집/분석 대표글 수: {analysis.document_count}")
    print("\n[원고별 핵심 지표]")
    for body in analysis.body_analyses:
        print(
            f"- {body.rank}. {body.content_type} | {body.title} | "
            f"본문 {body.char_count:,}자 | 키워드 {body.keyword_count}회 | {body.url}"
        )

    rec = analysis.recommendation
    print("\n[SEO 작성 권장 범위]")
    print(f"- 제목 글자수: {rec.title_char_count_range[0]}~{rec.title_char_count_range[1]}자")
    print(f"- 본문 글자수: {rec.body_char_count_range[0]:,}~{rec.body_char_count_range[1]:,}자")
    print(f"- 본문 키워드 반복: {rec.keyword_count_range[0]}~{rec.keyword_count_range[1]}회")
    print(f"- 1000자당 키워드 밀도 중앙값: {rec.keyword_density_per_1000_chars_median}")
    print(f"- 공통 반복 단어 상위: {dict(list(analysis.common_words.items())[:10])}")

    if paths:
        print("\n[저장 파일]")
        for name, path in paths.items():
            print(f"- {name}: {path}")


def run_from_args(args: argparse.Namespace) -> SearchSEOAnalysis:
    if args.input_json:
        analysis = analyze_crawled_file(
            args.input_json,
            keyword=args.keyword,
            output_dir=args.output_dir,
            output_prefix=args.output_prefix,
        )
        prefix = args.output_prefix or args.keyword.replace(" ", "_")
        paths = {
            "analysis_json": args.output_dir / f"{prefix}_seo_analysis.json",
            "summary_csv": args.output_dir / f"{prefix}_seo_summary.csv",
            "compact_context_json": args.output_dir / f"{prefix}_llm_compact_context.json",
        }
        print_analysis_summary(analysis, paths)
        return analysis

    driver = build_driver(headless=not args.show_browser)
    try:
        _rows, analysis, paths = crawl_and_analyze_search_seo(
            driver,
            args.keyword,
            max_items=args.max_items,
            delay_seconds=args.delay_seconds,
            output_dir=args.output_dir,
            output_prefix=args.output_prefix,
        )
        print_analysis_summary(analysis, paths)
        return analysis
    finally:
        driver.quit()


def main() -> None:
    args = build_parser().parse_args()
    run_from_args(args)


if __name__ == "__main__":
    main()
