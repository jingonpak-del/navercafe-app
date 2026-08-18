# -*- coding: utf-8 -*-
"""Create an evidence-led Cafe insight bundle and disclosed product reply preview.

Examples:
  uv run python scripts/naver_evidence_led_manuscript.py "무선청소기" \
    --input-json output/sample_crawled.json --product-name "제품명" \
    --feature "HEPA 필터" --evidence "공식 제품 사양서" \
    --disclosure "[브랜드 담당자 안내]"
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path

from naver_cafe_strategy.naver.evidence_led_manuscript import (
    ProductFacts,
    build_consumer_insight_brief,
    generate_disclosed_reply_draft,
)
from naver_cafe_strategy.naver.search_content_crawler import CrawledContent


def _load_rows(path: Path) -> list[CrawledContent]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [CrawledContent(**item) for item in data]


def _write_json(path: Path, value: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="카페 증거 코퍼스에서 소비자 이슈를 분석하고 공개형 제품 답변 초안을 만듭니다.")
    parser.add_argument("keyword")
    parser.add_argument("--input-json", type=Path, required=True, help="CrawledContent JSON 배열")
    parser.add_argument("--output-dir", type=Path, default=Path("output/evidence_led_manuscript"))
    parser.add_argument("--product-name", required=True)
    parser.add_argument("--feature", action="append", required=True, help="검증된 제품 특징 (반복 지정 가능)")
    parser.add_argument("--evidence", action="append", required=True, help="특징의 확인 근거 (반복 지정 가능)")
    parser.add_argument("--disclosure", required=True, help="브랜드/협찬/관계 표기 문구")
    parser.add_argument("--restricted-claim", action="append", default=[])
    return parser


def main() -> None:
    args = build_parser().parse_args()
    rows = _load_rows(args.input_json)
    posts, brief = build_consumer_insight_brief(args.keyword, rows)
    if not brief.issue_clusters:
        raise SystemExit("분석 가능한 이슈 클러스터가 없습니다. 더 많은 공개 카페 글 또는 다른 키워드가 필요합니다.")
    product = ProductFacts(
        name=args.product_name,
        features=args.feature,
        evidence=args.evidence,
        disclosure=args.disclosure,
        restricted_claims=args.restricted_claim,
    )
    draft = generate_disclosed_reply_draft(args.keyword, brief.issue_clusters[0], product)
    prefix = args.keyword.replace(" ", "_")
    paths = {
        "evidence_posts": _write_json(args.output_dir / f"{prefix}_evidence_posts.json", [asdict(post) for post in posts]),
        "consumer_insight_brief": _write_json(args.output_dir / f"{prefix}_consumer_insight_brief.json", asdict(brief)),
        "disclosed_reply_draft": _write_json(args.output_dir / f"{prefix}_disclosed_reply_draft.json", asdict(draft)),
    }
    print("[Evidence-led Cafe manuscript bundle]")
    for name, path in paths.items():
        print(f"- {name}: {path}")


if __name__ == "__main__":
    main()
