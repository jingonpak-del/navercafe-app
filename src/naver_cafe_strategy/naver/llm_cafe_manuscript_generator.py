# -*- coding: utf-8 -*-
"""LLM prompt and optional OpenAI-compatible generation for Naver Cafe manuscripts."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import os
import re
from typing import Any, Callable

import requests

from .cafe_manuscript_generator import GeneratedCafeManuscript
from .manuscript_brief_builder import ManuscriptBrief, brief_to_dict


DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_BASE_URL = "https://api.openai.com/v1"


@dataclass(slots=True)
class LLMGenerationConfig:
    provider: str = "openai-compatible"
    model: str = DEFAULT_MODEL
    base_url: str = DEFAULT_BASE_URL
    api_key: str | None = None
    temperature: float = 0.7
    max_tokens: int = 1600
    timeout_seconds: float = 60.0

    @classmethod
    def from_env(
        cls,
        *,
        model: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 1600,
        timeout_seconds: float = 60.0,
    ) -> "LLMGenerationConfig":
        return cls(
            model=model or os.getenv("OPENAI_MODEL") or DEFAULT_MODEL,
            base_url=(base_url or os.getenv("OPENAI_BASE_URL") or DEFAULT_BASE_URL).rstrip("/"),
            api_key=api_key or os.getenv("OPENAI_API_KEY"),
            temperature=temperature,
            max_tokens=max_tokens,
            timeout_seconds=timeout_seconds,
        )


@dataclass(slots=True)
class LLMPromptBundle:
    system: str
    user: str
    response_schema: dict[str, Any]
    brief: dict[str, Any]
    generation_notes: list[str] = field(default_factory=list)


def build_llm_prompt_bundle(brief: ManuscriptBrief) -> LLMPromptBundle:
    """Build a compact, schema-bound LLM prompt from the deterministic manuscript brief."""

    response_schema = {
        "type": "object",
        "required": ["Title", "Content", "Comment"],
        "additionalProperties": False,
        "properties": {
            "Title": {"type": "string", "description": "네이버 카페 게시글 제목"},
            "Content": {"type": "string", "description": "본문. 3~6문단, 자연스러운 카페 말투"},
            "Comment": {
                "type": "string",
                "description": "댓글 묶음. 예: 계정1|... \\t작성자[답글]|... \\t계정2|...",
            },
        },
    }
    type_instruction = {
        "question": "질문성: 검색해본 흔적과 본인 고민을 자연스럽게 드러내고, 마지막은 경험자에게 묻는다.",
        "review": "후기성: 개인 경험처럼 보이되 과장하지 않고, 좋았던 점/불안했던 점/개인차를 함께 남긴다.",
        "info": "정보성: 기준을 정리하지만 블로그식 설명문이 아니라 카페 공유글처럼 풀어쓴다.",
    }.get(brief.selected_type, "카페 게시글처럼 자연스럽게 쓴다.")

    system = "\n".join(
        [
            "너는 네이버 카페용 한국어 원고를 작성하는 편집자다.",
            "입력 브리프의 검색 의도, 형태소 패턴, 권장 어미를 반영하되 기계적인 나열은 피한다.",
            "반드시 JSON 객체만 출력하고, 마크다운 코드블록이나 설명 문장을 붙이지 않는다.",
            "특정 병원/업체 추천, 효과 보장, 의료·법률·금융 결과 단정 표현은 금지한다.",
        ]
    )
    user_payload = {
        "task": "네이버 검색 의도와 형태소 분석 브리프를 바탕으로 카페 원고 JSON을 작성한다.",
        "output_schema": response_schema,
        "brief": brief_to_dict(brief),
        "writing_rules": [
            type_instruction,
            "Title은 검색 키워드를 자연스럽게 1회 포함하고, 광고 문구처럼 과장하지 않는다.",
            "Content는 3~6문단으로 작성하고 문단 사이에는 빈 줄을 넣는다.",
            "Content에서 핵심 키워드는 2~4회 정도만 자연스럽게 사용한다.",
            "must_include_terms는 가능한 한 자연스럽게 분산하되 모든 단어를 억지로 넣지 않는다.",
            "avoid_overuse_terms는 반복을 피하고 대체 표현으로 분산한다.",
            "recommended_endings 중 일부를 섞어 쓰되 같은 종결어미를 연속 반복하지 않는다.",
            "Comment는 최소 3개 댓글/답글을 탭 구분 형식으로 만든다: 계정1|댓글 \\t작성자[답글]|답글 \\t계정2|댓글",
            "카페 회원이 직접 쓴 듯한 말투를 사용하고, AI가 요약한 듯한 표현은 피한다.",
        ],
        "forbidden_patterns": [
            "100%", "무조건", "반드시 효과", "완치", "최고의 병원", "추천 병원", "저렴한 이벤트", "지금 예약",
        ],
    }
    user = json.dumps(user_payload, ensure_ascii=False, indent=2)
    return LLMPromptBundle(
        system=system,
        user=user,
        response_schema=response_schema,
        brief=brief_to_dict(brief),
        generation_notes=[
            "LLM 출력은 Title/Content/Comment 세 필드 JSON으로 검증됩니다.",
            "API 키가 없는 환경에서는 prompt artifact만 저장해 외부 LLM에 붙여넣을 수 있습니다.",
        ],
    )


def prompt_bundle_to_dict(bundle: LLMPromptBundle) -> dict[str, Any]:
    return asdict(bundle)


def build_prompt_markdown(bundle: LLMPromptBundle) -> str:
    return f"""# LLM 카페 원고 생성 프롬프트

## System
```text
{bundle.system}
```

## User
```json
{bundle.user}
```

## 응답 규칙
- JSON 객체만 출력합니다.
- 필수 키는 `Title`, `Content`, `Comment`입니다.
- 코드블록, 설명, 주석을 붙이지 않습니다.
"""


def _extract_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.IGNORECASE)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        try:
            data = json.loads(stripped, strict=False)
        except json.JSONDecodeError:
            start = stripped.find("{")
            end = stripped.rfind("}")
            if start < 0 or end <= start:
                raise ValueError("LLM 응답에서 JSON 객체를 찾지 못했습니다.") from None
            json_slice = stripped[start : end + 1]
            try:
                data = json.loads(json_slice)
            except json.JSONDecodeError:
                data = json.loads(json_slice, strict=False)
    if not isinstance(data, dict):
        raise ValueError("LLM 응답 JSON은 객체여야 합니다.")
    return data


def parse_llm_manuscript_response(text: str, brief: ManuscriptBrief) -> GeneratedCafeManuscript:
    data = _extract_json_object(text)
    missing = [key for key in ("Title", "Content", "Comment") if not isinstance(data.get(key), str) or not data[key].strip()]
    if missing:
        raise ValueError(f"LLM 응답에 필수 문자열 필드가 없습니다: {', '.join(missing)}")
    return GeneratedCafeManuscript(
        Title=data["Title"].strip(),
        Content=data["Content"].strip(),
        Comment=data["Comment"].strip(),
        manuscript_type=brief.selected_type_label,
        brief_keyword=brief.keyword,
    )


def _call_openai_compatible_chat(bundle: LLMPromptBundle, config: LLMGenerationConfig) -> str:
    if not config.api_key:
        raise ValueError("OPENAI_API_KEY 또는 --llm-api-key가 필요합니다. API 없이 사용하려면 --generation-mode prompt를 쓰세요.")
    payload = {
        "model": config.model,
        "messages": [
            {"role": "system", "content": bundle.system},
            {"role": "user", "content": bundle.user},
        ],
        "temperature": config.temperature,
        "max_tokens": config.max_tokens,
        "response_format": {"type": "json_object"},
    }
    response = requests.post(
        f"{config.base_url.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {config.api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=config.timeout_seconds,
    )
    response.raise_for_status()
    data = response.json()
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError(f"알 수 없는 LLM API 응답 구조입니다: {data}") from exc


def generate_cafe_manuscript_with_llm(
    brief: ManuscriptBrief,
    *,
    config: LLMGenerationConfig | None = None,
    chat_caller: Callable[[LLMPromptBundle, LLMGenerationConfig], str] | None = None,
) -> GeneratedCafeManuscript:
    bundle = build_llm_prompt_bundle(brief)
    resolved = config or LLMGenerationConfig.from_env()
    caller = chat_caller or _call_openai_compatible_chat
    text = caller(bundle, resolved)
    return parse_llm_manuscript_response(text, brief)
