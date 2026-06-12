# -*- coding: utf-8 -*-
"""
네이버 검색 1페이지 블로그/카페 원고 SEO 분석 모듈.

목적:
    특정 키워드로 검색했을 때 1페이지에 노출되는 블로그/카페 원고의 제목/본문 패턴을
    코드로 요약하여, 대량 작업 시 LLM 토큰을 쓰지 않고도 반복 가능한 SEO 기준 데이터를 만듭니다.

분석 항목:
    - 제목 글자수, 제목 내 중복 단어/횟수, 제목 키워드 포함 여부/위치
    - 본문 글자수, 본문 키워드 반복수/밀도, 본문 내 반복 단어/횟수
    - 전체 원고 공통 반복 단어, 각 원고별 공통 단어 반복수
    - 상위 원고 기준 권장 제목 길이/본문 길이/키워드 반복수 범위

외부 형태소 분석기 없이 표준 라이브러리만 사용합니다.
정밀 형태소 분석은 아니지만 설치/토큰 비용 없이 대량 처리하기 쉽도록 설계했습니다.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field
import csv
import json
import math
import re
from pathlib import Path
from statistics import median
from typing import Iterable

from .search_content_crawler import CrawledContent, crawl_naver_search_blog_cafe, save_crawled_contents

# 조사/어미/일반 불용어. 프로젝트 상황에 맞춰 호출 시 extra_stopwords로 추가 가능합니다.
DEFAULT_STOPWORDS = frozenset(
    {
        "그리고",
        "그러나",
        "그래서",
        "하지만",
        "있는",
        "없는",
        "있고",
        "없고",
        "합니다",
        "했습니다",
        "됩니다",
        "됩니다",
        "대한",
        "통해",
        "위해",
        "경우",
        "때문",
        "정도",
        "관련",
        "이번",
        "저희",
        "우리",
        "제가",
        "저는",
        "오늘",
        "요즘",
        "정말",
        "많이",
        "바로",
        "이런",
        "저런",
        "그런",
        "것은",
        "것도",
        "것이",
        "것을",
        "수가",
        "수도",
        "등을",
        "등의",
        "등이",
        "에서",
        "으로",
        "에게",
        "까지",
        "부터",
        "보다",
        "처럼",
        "하고",
        "하면",
        "해서",
        "되면",
        "에는",
        "라는",
        "라고",
        "이라",
        "이라면",
        "입니다",
        "합니다",
        "있습니다",
        "했습니다",
    }
)

_TOKEN_RE = re.compile(r"[가-힣A-Za-z0-9]+")
_KOREAN_JOSA_RE = re.compile(
    r"(으로써|으로서|에게서|한테서|께서|에서|에게|한테|으로|부터|까지|보다|처럼|와|과|을|를|이|가|은|는|의|에|도|만|로|고|며|나|랑)$"
)


@dataclass(slots=True)
class TitleSEOAnalysis:
    """원고 제목 1건 분석 결과."""

    rank: int
    content_type: str
    url: str
    title: str
    char_count: int
    keyword_count: int
    keyword_in_title: bool
    keyword_position: int
    repeated_words: dict[str, int] = field(default_factory=dict)


@dataclass(slots=True)
class BodySEOAnalysis:
    """원고 본문 1건 분석 결과."""

    rank: int
    content_type: str
    url: str
    title: str
    char_count: int
    word_count: int
    keyword_count: int
    keyword_density_per_1000_chars: float
    keyword_density_percent_of_words: float
    repeated_words: dict[str, int] = field(default_factory=dict)
    common_word_counts: dict[str, int] = field(default_factory=dict)


@dataclass(slots=True)
class SEORecommendation:
    """상위 노출 원고들의 중앙값 기반 작성 참고 범위."""

    title_char_count_median: int
    title_char_count_range: tuple[int, int]
    body_char_count_median: int
    body_char_count_range: tuple[int, int]
    keyword_count_median: int
    keyword_count_range: tuple[int, int]
    keyword_density_per_1000_chars_median: float
    suggested_title_must_include_keyword: bool
    suggested_first_paragraph_include_keyword: bool
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SearchSEOAnalysis:
    """검색 키워드 기준 1페이지 원고 묶음 분석 결과."""

    keyword: str
    document_count: int
    title_analyses: list[TitleSEOAnalysis]
    body_analyses: list[BodySEOAnalysis]
    title_global_repeated_words: dict[str, int]
    body_global_repeated_words: dict[str, int]
    common_words: dict[str, int]
    recommendation: SEORecommendation


def normalize_text(text: str) -> str:
    """공백을 정리한 분석용 텍스트를 반환합니다."""

    return re.sub(r"\s+", " ", text or "").strip()


def compact_char_count(text: str) -> int:
    """SEO 원고 길이 비교용 글자수. 공백은 제외합니다."""

    return len(re.sub(r"\s+", "", text or ""))


def split_keyword_terms(keyword: str) -> set[str]:
    """키워드 구문과 구성 단어를 제외어로 사용할 수 있게 합니다."""

    terms = {normalize_token(token) for token in _TOKEN_RE.findall(keyword or "") if normalize_token(token)}
    compact_keyword = normalize_token(re.sub(r"\s+", "", keyword or ""))
    if compact_keyword:
        terms.add(compact_keyword)
    return terms


def normalize_token(token: str) -> str:
    """간단한 한국어 조사 제거 + 소문자 변환으로 단어를 정규화합니다."""

    token = (token or "").strip().lower()
    token = _KOREAN_JOSA_RE.sub("", token)
    return token


def tokenize(text: str, *, keyword: str = "", stopwords: Iterable[str] | None = None) -> list[str]:
    """분석용 토큰 목록을 생성합니다.

    - 2글자 미만 단어 제외
    - 기본 불용어 제외
    - 키워드 구성 단어 제외 가능: 공통 반복어 분석에서 키워드 자체가 과대 집계되지 않도록 함
    """

    excluded = set(DEFAULT_STOPWORDS)
    if stopwords:
        excluded.update(normalize_token(word) for word in stopwords)
    excluded.update(split_keyword_terms(keyword))

    tokens: list[str] = []
    for raw in _TOKEN_RE.findall(text or ""):
        token = normalize_token(raw)
        if len(token) < 2:
            continue
        if token in excluded:
            continue
        if token.isdigit():
            continue
        tokens.append(token)
    return tokens


def count_keyword(text: str, keyword: str) -> int:
    """본문/제목에서 키워드 구문 반복 횟수를 계산합니다.

    공백 차이를 흡수하기 위해 원문과 키워드 모두 공백 제거 후 카운트합니다.
    예: '창원 흥신소'와 '창원흥신소'를 같은 키워드로 봅니다.
    """

    normalized_text = re.sub(r"\s+", "", text or "").lower()
    normalized_keyword = re.sub(r"\s+", "", keyword or "").lower()
    if not normalized_text or not normalized_keyword:
        return 0
    return normalized_text.count(normalized_keyword)


def repeated_word_counts(
    text: str,
    *,
    keyword: str = "",
    min_count: int = 2,
    top_n: int = 30,
    stopwords: Iterable[str] | None = None,
) -> dict[str, int]:
    """텍스트 안에서 반복되는 단어와 횟수를 반환합니다."""

    counts = Counter(tokenize(text, keyword=keyword, stopwords=stopwords))
    return dict(counts.most_common(top_n if top_n > 0 else None)) if min_count <= 1 else {
        word: count for word, count in counts.most_common(top_n if top_n > 0 else None) if count >= min_count
    }


def analyze_title(title: str, *, keyword: str, rank: int, content_type: str, url: str) -> TitleSEOAnalysis:
    """제목 1건의 길이/키워드/중복 단어를 분석합니다."""

    compact_title = re.sub(r"\s+", "", title or "").lower()
    compact_keyword = re.sub(r"\s+", "", keyword or "").lower()
    position = compact_title.find(compact_keyword) if compact_keyword else -1
    return TitleSEOAnalysis(
        rank=rank,
        content_type=content_type,
        url=url,
        title=title,
        char_count=compact_char_count(title),
        keyword_count=count_keyword(title, keyword),
        keyword_in_title=position >= 0,
        keyword_position=position,
        repeated_words=repeated_word_counts(title, keyword=keyword, min_count=2, top_n=20),
    )


def analyze_body(
    body: str,
    *,
    keyword: str,
    rank: int,
    content_type: str,
    url: str,
    title: str,
    common_words: Iterable[str] = (),
) -> BodySEOAnalysis:
    """본문 1건의 글자수/키워드 반복수/반복 단어를 분석합니다."""

    char_count = compact_char_count(body)
    tokens = tokenize(body, keyword=keyword)
    word_count = len(tokens)
    keyword_count = count_keyword(body, keyword)
    repeated = repeated_word_counts(body, keyword=keyword, min_count=2, top_n=50)
    common_counts = {word: repeated.get(word, 0) for word in common_words if repeated.get(word, 0) > 0}
    return BodySEOAnalysis(
        rank=rank,
        content_type=content_type,
        url=url,
        title=title,
        char_count=char_count,
        word_count=word_count,
        keyword_count=keyword_count,
        keyword_density_per_1000_chars=round((keyword_count / char_count * 1000) if char_count else 0.0, 2),
        keyword_density_percent_of_words=round((keyword_count / word_count * 100) if word_count else 0.0, 2),
        repeated_words=repeated,
        common_word_counts=common_counts,
    )


def find_common_words(
    bodies: Iterable[str],
    *,
    keyword: str,
    min_documents: int = 2,
    top_n: int = 50,
) -> dict[str, int]:
    """여러 원고에 공통적으로 등장하는 단어와 전체 반복 수를 반환합니다.

    키워드 구성 단어는 제외합니다.
    """

    total_counts: Counter[str] = Counter()
    document_counts: Counter[str] = Counter()
    for body in bodies:
        counts = Counter(tokenize(body, keyword=keyword))
        total_counts.update(counts)
        document_counts.update(counts.keys())

    return {
        word: total_counts[word]
        for word, _ in total_counts.most_common(top_n if top_n > 0 else None)
        if document_counts[word] >= min_documents
    }


def percentile_range(values: list[int], *, lower_ratio: float = 0.25, upper_ratio: float = 0.75) -> tuple[int, int]:
    """간단한 분위 범위를 반환합니다. 값이 적을 때도 안정적으로 동작합니다."""

    if not values:
        return 0, 0
    sorted_values = sorted(values)
    lower_index = max(0, min(len(sorted_values) - 1, math.floor((len(sorted_values) - 1) * lower_ratio)))
    upper_index = max(0, min(len(sorted_values) - 1, math.ceil((len(sorted_values) - 1) * upper_ratio)))
    return sorted_values[lower_index], sorted_values[upper_index]


def build_recommendation(
    *,
    keyword: str,
    titles: list[TitleSEOAnalysis],
    bodies: list[BodySEOAnalysis],
    raw_bodies: list[str],
) -> SEORecommendation:
    """상위 원고 분석값으로 신규 원고 작성 참고 범위를 생성합니다."""

    title_counts = [row.char_count for row in titles]
    body_counts = [row.char_count for row in bodies]
    keyword_counts = [row.keyword_count for row in bodies]
    densities = [row.keyword_density_per_1000_chars for row in bodies]
    title_keyword_ratio = sum(1 for row in titles if row.keyword_in_title) / len(titles) if titles else 0.0
    first_paragraph_hits = 0
    for body in raw_bodies:
        first_250_chars = re.sub(r"\s+", "", body or "")[:250]
        if count_keyword(first_250_chars, keyword) > 0:
            first_paragraph_hits += 1
    first_ratio = first_paragraph_hits / len(raw_bodies) if raw_bodies else 0.0

    notes: list[str] = []
    if title_keyword_ratio >= 0.6:
        notes.append("상위 원고 다수가 제목에 검색 키워드를 포함합니다.")
    if first_ratio >= 0.6:
        notes.append("상위 원고 다수가 본문 초반부에 검색 키워드를 포함합니다.")
    if bodies:
        notes.append("본문 글자수와 키워드 반복수는 중앙값/분위 범위를 기준으로 과도한 반복을 피하세요.")

    return SEORecommendation(
        title_char_count_median=int(median(title_counts)) if title_counts else 0,
        title_char_count_range=percentile_range(title_counts),
        body_char_count_median=int(median(body_counts)) if body_counts else 0,
        body_char_count_range=percentile_range(body_counts),
        keyword_count_median=int(median(keyword_counts)) if keyword_counts else 0,
        keyword_count_range=percentile_range(keyword_counts),
        keyword_density_per_1000_chars_median=round(float(median(densities)), 2) if densities else 0.0,
        suggested_title_must_include_keyword=title_keyword_ratio >= 0.6,
        suggested_first_paragraph_include_keyword=first_ratio >= 0.6,
        notes=notes,
    )


def analyze_crawled_contents(
    rows: Iterable[CrawledContent],
    *,
    keyword: str,
    common_min_documents: int = 2,
    common_top_n: int = 50,
) -> SearchSEOAnalysis:
    """크롤링된 블로그/카페 원고 묶음을 제목/본문 기준으로 분석합니다."""

    docs = [row for row in rows if row.ok and row.body]
    common_words = find_common_words(
        [row.body for row in docs],
        keyword=keyword,
        min_documents=common_min_documents,
        top_n=common_top_n,
    )
    titles = [
        analyze_title(row.title, keyword=keyword, rank=row.rank, content_type=row.content_type, url=row.url)
        for row in docs
    ]
    bodies = [
        analyze_body(
            row.body,
            keyword=keyword,
            rank=row.rank,
            content_type=row.content_type,
            url=row.url,
            title=row.title,
            common_words=common_words.keys(),
        )
        for row in docs
    ]

    title_global = Counter()
    body_global = Counter()
    for row in docs:
        title_global.update(tokenize(row.title, keyword=keyword))
        body_global.update(tokenize(row.body, keyword=keyword))

    recommendation = build_recommendation(keyword=keyword, titles=titles, bodies=bodies, raw_bodies=[row.body for row in docs])
    return SearchSEOAnalysis(
        keyword=keyword,
        document_count=len(docs),
        title_analyses=titles,
        body_analyses=bodies,
        title_global_repeated_words={word: count for word, count in title_global.most_common(50) if count >= 2},
        body_global_repeated_words={word: count for word, count in body_global.most_common(100) if count >= 2},
        common_words=common_words,
        recommendation=recommendation,
    )


def load_crawled_contents_json(path: str | Path) -> list[CrawledContent]:
    """search_content_crawler.save_crawled_contents(...json) 결과를 다시 읽습니다."""

    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [CrawledContent(**row) for row in data]


def save_analysis_json(analysis: SearchSEOAnalysis, output_path: str | Path) -> Path:
    """분석 전체 결과를 JSON으로 저장합니다. 대량 작업/후속 LLM 요약용 원본입니다."""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(analysis), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def save_analysis_summary_csv(analysis: SearchSEOAnalysis, output_path: str | Path) -> Path:
    """원고별 핵심 수치만 CSV로 저장합니다."""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    body_by_url = {row.url: row for row in analysis.body_analyses}
    with path.open("w", newline="", encoding="utf-8-sig") as fp:
        writer = csv.DictWriter(
            fp,
            fieldnames=[
                "rank",
                "content_type",
                "url",
                "title",
                "title_char_count",
                "title_keyword_count",
                "body_char_count",
                "body_word_count",
                "body_keyword_count",
                "keyword_density_per_1000_chars",
                "top_repeated_words",
                "common_word_counts",
            ],
        )
        writer.writeheader()
        for title_row in analysis.title_analyses:
            body_row = body_by_url.get(title_row.url)
            writer.writerow(
                {
                    "rank": title_row.rank,
                    "content_type": title_row.content_type,
                    "url": title_row.url,
                    "title": title_row.title,
                    "title_char_count": title_row.char_count,
                    "title_keyword_count": title_row.keyword_count,
                    "body_char_count": body_row.char_count if body_row else 0,
                    "body_word_count": body_row.word_count if body_row else 0,
                    "body_keyword_count": body_row.keyword_count if body_row else 0,
                    "keyword_density_per_1000_chars": body_row.keyword_density_per_1000_chars if body_row else 0,
                    "top_repeated_words": json.dumps(dict(list((body_row.repeated_words if body_row else {}).items())[:10]), ensure_ascii=False),
                    "common_word_counts": json.dumps(body_row.common_word_counts if body_row else {}, ensure_ascii=False),
                }
            )
    return path


def build_llm_compact_context(analysis: SearchSEOAnalysis, *, top_n_words: int = 20) -> dict:
    """후속 LLM 원고 작성 지시문에 넣기 좋은 최소 토큰 컨텍스트를 생성합니다.

    본문 원문은 포함하지 않고, 숫자/상위 반복어/권장 범위만 포함합니다.
    """

    return {
        "keyword": analysis.keyword,
        "document_count": analysis.document_count,
        "recommendation": asdict(analysis.recommendation),
        "titles": [
            {
                "rank": row.rank,
                "type": row.content_type,
                "chars": row.char_count,
                "keyword_count": row.keyword_count,
                "title": row.title,
            }
            for row in analysis.title_analyses
        ],
        "bodies": [
            {
                "rank": row.rank,
                "type": row.content_type,
                "chars": row.char_count,
                "keyword_count": row.keyword_count,
                "density_per_1000": row.keyword_density_per_1000_chars,
                "top_words": dict(list(row.repeated_words.items())[:top_n_words]),
                "common_words": row.common_word_counts,
            }
            for row in analysis.body_analyses
        ],
        "global_title_words": dict(list(analysis.title_global_repeated_words.items())[:top_n_words]),
        "global_body_words": dict(list(analysis.body_global_repeated_words.items())[:top_n_words]),
        "common_words": dict(list(analysis.common_words.items())[:top_n_words]),
    }


def save_llm_compact_context(analysis: SearchSEOAnalysis, output_path: str | Path, *, top_n_words: int = 20) -> Path:
    """토큰 절약형 SEO 컨텍스트 JSON을 저장합니다."""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    compact = build_llm_compact_context(analysis, top_n_words=top_n_words)
    path.write_text(json.dumps(compact, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _safe_prefix(keyword: str) -> str:
    return re.sub(r"[^가-힣A-Za-z0-9]+", "_", keyword).strip("_") or "keyword"


def save_analysis_bundle(
    analysis: SearchSEOAnalysis,
    *,
    output_dir: str | Path = "output/seo_analysis",
    output_prefix: str | None = None,
) -> dict[str, Path]:
    """분석 결과를 원본 JSON/요약 CSV/토큰 절약 compact JSON으로 함께 저장합니다."""

    prefix = output_prefix or _safe_prefix(analysis.keyword)
    out_dir = Path(output_dir)
    return {
        "analysis_json": save_analysis_json(analysis, out_dir / f"{prefix}_seo_analysis.json"),
        "summary_csv": save_analysis_summary_csv(analysis, out_dir / f"{prefix}_seo_summary.csv"),
        "compact_context_json": save_llm_compact_context(analysis, out_dir / f"{prefix}_llm_compact_context.json"),
    }


def analyze_crawled_file(
    input_json_path: str | Path,
    *,
    keyword: str,
    output_dir: str | Path = "output/seo_analysis",
    output_prefix: str | None = None,
) -> SearchSEOAnalysis:
    """저장된 크롤링 JSON 파일을 읽어 SEO 분석 JSON/CSV/compact JSON을 함께 생성합니다."""

    rows = load_crawled_contents_json(input_json_path)
    analysis = analyze_crawled_contents(rows, keyword=keyword)
    save_analysis_bundle(analysis, output_dir=output_dir, output_prefix=output_prefix)
    return analysis


def crawl_and_analyze_search_seo(
    driver,
    keyword: str,
    *,
    max_items: int | None = None,
    delay_seconds: float = 1.0,
    output_dir: str | Path = "output/seo_analysis",
    output_prefix: str | None = None,
) -> tuple[list[CrawledContent], SearchSEOAnalysis, dict[str, Path]]:
    """검색 결과 크롤링과 SEO 분석 저장까지 한 번에 수행합니다.

    대량 작업에서는 이 함수만 호출하면 원고 원문 JSON, 분석 JSON, 요약 CSV,
    LLM용 compact JSON을 모두 만들 수 있어 후속 토큰 사용량을 줄일 수 있습니다.
    """

    rows = crawl_naver_search_blog_cafe(driver, keyword, max_items=max_items, delay_seconds=delay_seconds)
    analysis = analyze_crawled_contents(rows, keyword=keyword)
    prefix = output_prefix or _safe_prefix(keyword)
    out_dir = Path(output_dir)
    crawled_json = save_crawled_contents(rows, out_dir / f"{prefix}_crawled_contents.json")
    paths = {"crawled_json": crawled_json, **save_analysis_bundle(analysis, output_dir=out_dir, output_prefix=prefix)}
    return rows, analysis, paths
