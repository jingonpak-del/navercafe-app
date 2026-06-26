# -*- coding: utf-8 -*-
"""네이버 검색 의도/형태소 분석 기반 카페 원고 생성 MVP.

사용 예:
    uv run python scripts/naver_search_intent_cafe_manuscript.py "소음순수술" \
      --input-json output/seo_analysis/2026-06-26/소음순수술_crawled_contents.json

    uv run python scripts/naver_search_intent_cafe_manuscript.py "부산 흥신소" --max-items 5 --generate
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path

from naver_cafe_strategy.browser.webdriver import build_driver
from naver_cafe_strategy.naver.cafe_manuscript_generator import (
    generate_cafe_manuscript,
    manuscript_to_json_dict,
    manuscript_with_metadata_to_dict,
)
from naver_cafe_strategy.naver.llm_cafe_manuscript_generator import (
    LLMGenerationConfig,
    build_llm_prompt_bundle,
    build_prompt_markdown,
    generate_cafe_manuscript_with_llm,
    prompt_bundle_to_dict,
)
from naver_cafe_strategy.naver.manuscript_brief_builder import (
    brief_to_dict,
    build_brief_markdown,
    build_manuscript_brief,
)
from naver_cafe_strategy.naver.morphological_analyzer import analyze_crawled_morphology, morph_analysis_to_dict
from naver_cafe_strategy.naver.search_content_crawler import save_crawled_contents
from naver_cafe_strategy.naver.search_intent_analyzer import infer_search_intent, intent_profile_to_dict
from naver_cafe_strategy.naver.seo_content_analyzer import (
    analyze_crawled_contents,
    crawl_and_analyze_search_seo,
    load_crawled_contents_json,
)


def _safe_prefix(keyword: str) -> str:
    import re

    return re.sub(r"[^가-힣A-Za-z0-9]+", "_", keyword).strip("_") or "keyword"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="네이버 검색 결과의 형태소/검색의도를 분석해 카페 원고 브리프와 MVP 원고를 생성합니다.")
    parser.add_argument("keyword", help="분석할 네이버 검색 키워드")
    parser.add_argument("--input-json", type=Path, default=None, help="이미 저장된 *_crawled_contents.json 경로")
    parser.add_argument("--output-dir", type=Path, default=Path("output/search_intent_manuscript"), help="결과 저장 폴더")
    parser.add_argument("--output-prefix", default=None, help="결과 파일 prefix. 미지정 시 키워드 기반 자동 생성")
    parser.add_argument("--max-items", type=int, default=None, help="검색에서 최대 수집할 대표글 수")
    parser.add_argument("--delay-seconds", type=float, default=1.0, help="상세 페이지 크롤링 간 대기 초")
    parser.add_argument("--show-browser", action="store_true", help="검색/크롤링 시 브라우저 표시")
    parser.add_argument("--generate", action="store_true", help="input-json 없이 네이버 검색/크롤링부터 수행")
    parser.add_argument(
        "--generation-mode",
        choices=["rule", "prompt", "llm"],
        default="rule",
        help="원고 생성 방식: rule=기존 규칙 기반, prompt=LLM 프롬프트만 저장, llm=OpenAI 호환 API 호출",
    )
    parser.add_argument("--llm-model", default=None, help="LLM API 모델명. 기본값은 OPENAI_MODEL 또는 gpt-4o-mini")
    parser.add_argument("--llm-base-url", default=None, help="OpenAI 호환 base URL. 기본값은 OPENAI_BASE_URL 또는 OpenAI")
    parser.add_argument("--llm-api-key", default=None, help="LLM API 키. 미지정 시 OPENAI_API_KEY 사용")
    parser.add_argument("--llm-temperature", type=float, default=0.7, help="LLM temperature")
    parser.add_argument("--llm-max-tokens", type=int, default=1600, help="LLM max_tokens")
    return parser


def _write_json(path: Path, data: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def run_pipeline(args: argparse.Namespace) -> dict[str, Path]:
    prefix = args.output_prefix or _safe_prefix(args.keyword)
    out_dir = args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.input_json:
        rows = load_crawled_contents_json(args.input_json)
        crawled_path = args.input_json
        seo = analyze_crawled_contents(rows, keyword=args.keyword)
    else:
        if not args.generate:
            raise SystemExit("--input-json 없이 실행하려면 --generate를 지정해 네이버 검색/크롤링을 허용해야 합니다.")
        driver = build_driver(headless=not args.show_browser)
        try:
            rows, seo, paths = crawl_and_analyze_search_seo(
                driver,
                args.keyword,
                max_items=args.max_items,
                delay_seconds=args.delay_seconds,
                output_dir=out_dir,
                output_prefix=prefix,
            )
            crawled_path = paths["crawled_json"]
        finally:
            driver.quit()

    if args.input_json:
        crawled_copy = out_dir / f"{prefix}_crawled_contents.json"
        if crawled_copy.resolve() != Path(args.input_json).resolve():
            save_crawled_contents(rows, crawled_copy)
            crawled_path = crawled_copy

    morph = analyze_crawled_morphology(rows, keyword=args.keyword)
    intent = infer_search_intent(rows, morph)
    brief = build_manuscript_brief(keyword=args.keyword, morph=morph, intent=intent, seo=seo)
    prompt_bundle = build_llm_prompt_bundle(brief)
    if args.generation_mode == "llm":
        llm_config = LLMGenerationConfig.from_env(
            model=args.llm_model,
            base_url=args.llm_base_url,
            api_key=args.llm_api_key,
            temperature=args.llm_temperature,
            max_tokens=args.llm_max_tokens,
        )
        manuscript = generate_cafe_manuscript_with_llm(brief, config=llm_config)
        generator_mode = "llm"
    else:
        manuscript = generate_cafe_manuscript(brief)
        generator_mode = "prompt_with_rule_preview" if args.generation_mode == "prompt" else "rule"

    paths = {
        "crawled_json": Path(crawled_path),
        "morph_analysis_json": _write_json(out_dir / f"{prefix}_morph_analysis.json", morph_analysis_to_dict(morph)),
        "intent_profile_json": _write_json(out_dir / f"{prefix}_intent_profile.json", intent_profile_to_dict(intent)),
        "manuscript_brief_json": _write_json(out_dir / f"{prefix}_manuscript_brief.json", brief_to_dict(brief)),
        "manuscript_brief_md": out_dir / f"{prefix}_manuscript_brief.md",
        "llm_prompt_json": _write_json(out_dir / f"{prefix}_llm_prompt.json", prompt_bundle_to_dict(prompt_bundle)),
        "llm_prompt_md": out_dir / f"{prefix}_llm_prompt.md",
        "generated_manuscript_json": _write_json(out_dir / f"{prefix}_generated_cafe_manuscript.json", manuscript_to_json_dict(manuscript)),
        "generated_manuscript_with_meta_json": _write_json(
            out_dir / f"{prefix}_generated_cafe_manuscript_with_meta.json",
            {
                **manuscript_with_metadata_to_dict(manuscript),
                "generator_mode": generator_mode,
                "prompt_artifacts": {
                    "json": str(out_dir / f"{prefix}_llm_prompt.json"),
                    "markdown": str(out_dir / f"{prefix}_llm_prompt.md"),
                },
            },
        ),
        "seo_analysis_json": _write_json(out_dir / f"{prefix}_seo_analysis_snapshot.json", asdict(seo)),
    }
    paths["manuscript_brief_md"].write_text(build_brief_markdown(brief), encoding="utf-8")
    paths["llm_prompt_md"].write_text(build_prompt_markdown(prompt_bundle), encoding="utf-8")
    return paths


def main() -> None:
    args = build_parser().parse_args()
    paths = run_pipeline(args)
    print("\n[검색 의도 기반 카페 원고 MVP 완료]")
    for name, path in paths.items():
        print(f"- {name}: {path}")


if __name__ == "__main__":
    main()
