# -*- coding: utf-8 -*-
"""Quality evaluation and revision loop for generated Naver Cafe manuscripts."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import re
from typing import Callable

from .cafe_manuscript_generator import GeneratedCafeManuscript
from .llm_cafe_manuscript_generator import LLMGenerationConfig, LLMPromptBundle, build_llm_prompt_bundle, parse_llm_manuscript_response
from .manuscript_brief_builder import ManuscriptBrief
from .morphological_analyzer import analyze_text_morphology, morph_analysis_to_dict
from .seo_content_analyzer import count_keyword


DEFAULT_FORBIDDEN_PATTERNS = (
    "100%",
    "무조건",
    "반드시 효과",
    "완치",
    "최고의 병원",
    "추천 병원",
    "저렴한 이벤트",
    "지금 예약",
    "상담 예약",
)


@dataclass(slots=True)
class QualityCheck:
    name: str
    passed: bool
    score: float
    message: str
    severity: str = "medium"


@dataclass(slots=True)
class ManuscriptQualityReport:
    passed: bool
    score: float
    threshold: float
    checks: list[QualityCheck]
    issues: list[str]
    suggestions: list[str]
    morphology: dict
    keyword_count: int
    content_char_count_without_spaces: int
    ending_diversity: int
    generator_attempts: int = 1


@dataclass(slots=True)
class QualityLoopResult:
    manuscript: GeneratedCafeManuscript
    report: ManuscriptQualityReport
    attempts: int
    revision_history: list[ManuscriptQualityReport] = field(default_factory=list)


def _count_comment_items(comment: str) -> int:
    return len([part for part in re.split(r"\\t|\t", comment or "") if part.strip()])


def _keyword_range(brief: ManuscriptBrief) -> tuple[int, int]:
    # Naver Cafe manuscripts should keep the exact keyword visible but not mechanical.
    if brief.selected_type == "info":
        return (1, 5)
    return (1, 4)


def _append_check(checks: list[QualityCheck], name: str, passed: bool, message: str, *, severity: str = "medium") -> None:
    checks.append(QualityCheck(name=name, passed=passed, score=1.0 if passed else 0.0, message=message, severity=severity))


def evaluate_generated_manuscript(
    manuscript: GeneratedCafeManuscript,
    brief: ManuscriptBrief,
    *,
    threshold: float = 0.8,
    forbidden_patterns: tuple[str, ...] = DEFAULT_FORBIDDEN_PATTERNS,
) -> ManuscriptQualityReport:
    """Evaluate generated Title/Content/Comment against deterministic Naver Cafe quality rules."""

    checks: list[QualityCheck] = []
    text_all = f"{manuscript.Title}\n{manuscript.Content}\n{manuscript.Comment}"
    content_morph = analyze_text_morphology(
        manuscript.Content,
        keyword=brief.keyword,
        content_type="generated_manuscript",
        title=manuscript.Title,
    )
    keyword_count = count_keyword(text_all, brief.keyword)
    min_kw, max_kw = _keyword_range(brief)
    _append_check(
        checks,
        "keyword_count",
        min_kw <= keyword_count <= max_kw,
        f"키워드 '{brief.keyword}' 사용 {keyword_count}회; 권장 {min_kw}~{max_kw}회",
        severity="high",
    )

    title_keyword_count = count_keyword(manuscript.Title, brief.keyword)
    _append_check(
        checks,
        "title_keyword",
        title_keyword_count == 1,
        f"제목 키워드 사용 {title_keyword_count}회; 권장 1회",
    )
    _append_check(
        checks,
        "content_length",
        300 <= content_morph.char_count_without_spaces <= 1200,
        f"본문 공백 제외 {content_morph.char_count_without_spaces}자; 권장 300~1200자",
    )
    _append_check(
        checks,
        "paragraph_count",
        3 <= content_morph.paragraph_count <= 6,
        f"본문 문단 {content_morph.paragraph_count}개; 권장 3~6개",
    )
    _append_check(
        checks,
        "comment_count",
        _count_comment_items(manuscript.Comment) >= 3,
        f"댓글/답글 {_count_comment_items(manuscript.Comment)}개; 권장 3개 이상",
    )

    endings = content_morph.surface_ending_counts
    ending_diversity = len(endings)
    _append_check(
        checks,
        "ending_diversity",
        ending_diversity >= 2,
        f"본문 종결 표현 {ending_diversity}종; 권장 2종 이상",
    )
    recommended_hit = any(ending in manuscript.Content for ending in brief.recommended_endings)
    _append_check(
        checks,
        "recommended_endings",
        recommended_hit,
        "권장 종결 어미가 본문에 반영됨" if recommended_hit else "권장 종결 어미 반영이 약함",
    )

    forbidden_hits = [pattern for pattern in forbidden_patterns if pattern in text_all]
    _append_check(
        checks,
        "forbidden_patterns",
        not forbidden_hits,
        "금지/위험 표현 없음" if not forbidden_hits else f"금지/위험 표현 발견: {', '.join(forbidden_hits)}",
        severity="high",
    )

    must_terms = [term for term in brief.must_include_terms[:5] if term]
    included_terms = [term for term in must_terms if term in manuscript.Content]
    _append_check(
        checks,
        "must_include_terms",
        len(included_terms) >= min(2, len(must_terms)),
        f"상위 반영 표현 {len(included_terms)}/{len(must_terms)}개 반영: {', '.join(included_terms) or '없음'}",
    )

    overused = [term for term in brief.avoid_overuse_terms if term and count_keyword(text_all, term) > max_kw]
    _append_check(
        checks,
        "avoid_overuse_terms",
        not overused,
        "과반복 주의 표현 과다 없음" if not overused else f"과반복 표현: {', '.join(overused)}",
    )

    type_markers = {
        "question": ["궁금", "어떻게", "할까요", "부탁"],
        "review": ["느꼈", "더라고요", "개인차", "경험"],
        "info": ["기준", "확인", "정리", "비교"],
    }.get(brief.selected_type, [])
    marker_hits = [marker for marker in type_markers if marker in text_all]
    _append_check(
        checks,
        "type_tone_markers",
        bool(marker_hits),
        f"{brief.selected_type_label} 톤 단서: {', '.join(marker_hits) or '없음'}",
    )

    score = round(sum(check.score for check in checks) / len(checks), 3) if checks else 0.0
    issues = [check.message for check in checks if not check.passed]
    suggestions = build_revision_suggestions(checks, brief)
    return ManuscriptQualityReport(
        passed=score >= threshold and not any((not check.passed and check.severity == "high") for check in checks),
        score=score,
        threshold=threshold,
        checks=checks,
        issues=issues,
        suggestions=suggestions,
        morphology=morph_analysis_to_dict(content_morph),
        keyword_count=keyword_count,
        content_char_count_without_spaces=content_morph.char_count_without_spaces,
        ending_diversity=ending_diversity,
    )


def build_revision_suggestions(checks: list[QualityCheck], brief: ManuscriptBrief) -> list[str]:
    suggestions: list[str] = []
    failed = {check.name: check for check in checks if not check.passed}
    if "keyword_count" in failed:
        suggestions.append(f"'{brief.keyword}'는 제목 포함 1~4회 정도로 조정하고 나머지는 대체 표현으로 분산하세요.")
    if "content_length" in failed:
        suggestions.append("본문은 공백 제외 300~1200자 범위로, 너무 짧으면 고민 배경/확인 기준/질문을 보강하세요.")
    if "paragraph_count" in failed:
        suggestions.append("본문은 3~6문단으로 나누고 문단 사이에 빈 줄을 넣으세요.")
    if "ending_diversity" in failed or "recommended_endings" in failed:
        suggestions.append(f"권장 어미({', '.join(brief.recommended_endings)})를 2종 이상 섞고 같은 어미 연속 반복을 피하세요.")
    if "forbidden_patterns" in failed:
        suggestions.append("효과 보장, 특정 병원 추천, 예약 유도, 과장 광고 표현을 제거하세요.")
    if "must_include_terms" in failed:
        suggestions.append(f"상위 노출 표현({', '.join(brief.must_include_terms[:5])}) 중 2개 이상을 자연스럽게 반영하세요.")
    if "comment_count" in failed:
        suggestions.append("댓글은 계정 댓글/작성자 답글/추가 댓글이 보이도록 최소 3개 이상 작성하세요.")
    return suggestions or ["현재 품질 기준을 충족합니다. 과도한 수정 없이 자연스러움만 유지하세요."]


def quality_report_to_dict(report: ManuscriptQualityReport) -> dict:
    return asdict(report)


def build_quality_report_markdown(report: ManuscriptQualityReport) -> str:
    status = "통과" if report.passed else "수정 필요"
    checks_md = "\n".join(
        f"| {check.name} | {'PASS' if check.passed else 'FAIL'} | {check.message} |" for check in report.checks
    )
    issues_md = "\n".join(f"- {issue}" for issue in report.issues) if report.issues else "- 없음"
    suggestions_md = "\n".join(f"- {suggestion}" for suggestion in report.suggestions)
    return f"""# 생성 원고 품질 평가 리포트

## 종합
- 상태: {status}
- 점수: {report.score:.3f}
- 통과 기준: {report.threshold:.3f}
- 키워드 반복: {report.keyword_count}회
- 본문 공백 제외 글자수: {report.content_char_count_without_spaces}자
- 종결 표현 다양성: {report.ending_diversity}종
- 생성/수정 시도: {report.generator_attempts}회

## 체크 결과
| 항목 | 결과 | 설명 |
|---|---|---|
{checks_md}

## 이슈
{issues_md}

## 수정 제안
{suggestions_md}
"""


def generate_with_quality_loop(
    brief: ManuscriptBrief,
    *,
    config: LLMGenerationConfig,
    chat_caller: Callable[[LLMPromptBundle, LLMGenerationConfig], str],
    threshold: float = 0.8,
    max_revisions: int = 1,
) -> QualityLoopResult:
    """Generate with an injected LLM caller and retry with deterministic QA feedback."""

    history: list[ManuscriptQualityReport] = []
    feedback: list[str] = []
    attempts = max(1, max_revisions + 1)
    latest_manuscript: GeneratedCafeManuscript | None = None
    latest_report: ManuscriptQualityReport | None = None

    for attempt in range(1, attempts + 1):
        bundle = build_llm_prompt_bundle(brief)
        if feedback:
            bundle.user += "\n\n이전 원고 QA 피드백:\n" + "\n".join(f"- {item}" for item in feedback)
        raw = chat_caller(bundle, config)
        latest_manuscript = parse_llm_manuscript_response(raw, brief)
        latest_report = evaluate_generated_manuscript(latest_manuscript, brief, threshold=threshold)
        latest_report.generator_attempts = attempt
        history.append(latest_report)
        if latest_report.passed:
            break
        feedback = latest_report.suggestions

    assert latest_manuscript is not None and latest_report is not None
    return QualityLoopResult(
        manuscript=latest_manuscript,
        report=latest_report,
        attempts=latest_report.generator_attempts,
        revision_history=history,
    )
