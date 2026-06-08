# SECURITY: hardcoded SearchAd credentials were removed during project organization.
# -*- coding: utf-8 -*-
"""
[모듈 03] 네이버 검색량 조회 (E열)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
역할:
    네이버 검색광고 API를 통해 키워드의 월간 검색량을 조회합니다.
    PC 검색량 + 모바일 검색량의 합계를 반환합니다.
    → 스프레드시트 E열에 기록됩니다.

작동 방식:
    1. 네이버 검색광고 API의 /keywordstool 엔드포인트를 호출합니다.
    2. HMAC-SHA256 방식으로 요청 서명(Signature)을 생성합니다.
    3. 응답에서 PC 검색량(monthlyPcQcCnt)과 모바일(monthlyMobileQcCnt)을 합산합니다.
    4. 네이버는 검색량을 "<10", "10" 등 형태로 반환하므로 '<' 기호를 제거합니다.

API 서명(Signature) 생성 규칙:
    message = f"{타임스탬프(ms)}.{HTTP메서드}.{API경로}"
    signature = Base64(HMAC-SHA256(secret_key_as_utf8_bytes, message))

    ※ 주의: secret_key는 Base64 디코딩 없이 UTF-8 바이트 그대로 사용합니다.

API 인증 정보 발급 방법:
    1. https://searchad.naver.com 접속 (네이버 검색광고 관리자)
    2. [설정] → [API 관리] 메뉴
    3. 고객ID, Access License(API Key), Secret Key 확인

반환값 예시:
    "강남 맛집" 검색 시 → PC 1200 + 모바일 8500 = 9700 반환

사전 준비:
    pip install requests
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import time
import hmac
import hashlib
import base64

import requests


# 네이버 검색광고 API 기본 URL
BASE_URL = "https://api.searchad.naver.com"


def _api_sig(secret: str, ts: str, method: str, path: str) -> str:
    """
    HMAC-SHA256 방식으로 API 요청 서명을 생성합니다.

    Args:
        secret : 비밀키 (Secret Key) 문자열
        ts     : 타임스탬프 (밀리초 단위, 예: "1705300000000")
        method : HTTP 메서드 대문자 (예: "GET")
        path   : API 경로 (예: "/keywordstool")

    Returns:
        str: Base64 인코딩된 HMAC-SHA256 서명 문자열
    """
    # 서명 대상 메시지: "타임스탬프.메서드.경로"
    msg = f"{ts}.{method}.{path}".encode("utf-8")
    # secret_key는 UTF-8 바이트 그대로 사용 (Base64 디코딩 X)
    return base64.b64encode(
        hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).digest()
    ).decode("utf-8")


def _parse_cnt(val) -> int:
    """
    네이버 API의 검색량 값을 정수로 변환합니다.
    네이버는 검색량이 10 미만이면 "<10"처럼 '<' 기호를 붙여 반환합니다.

    Args:
        val: API 응답 값 (예: 1200, "<10", "8500")

    Returns:
        int: 정수 검색량 (최소 0)
    """
    s = str(val).strip().lstrip("<").strip()
    try:
        return max(int(s) - 1, 0)  # -1은 네이버 API의 미만 표기 보정
    except ValueError:
        return 0


def get_search_volume(keyword: str, customer: str, api_key: str, secret: str) -> int:
    """
    키워드의 월간 검색량(PC + 모바일 합계)을 반환합니다.

    Args:
        keyword  (str): 조회할 키워드 (예: "강남 맛집")
        customer (str): 네이버 검색광고 고객 ID (숫자, 예: "1800335")
        api_key  (str): 엑세스 라이선스(API Key)
        secret   (str): 비밀키(Secret Key)

    Returns:
        int: 월간 PC 검색량 + 모바일 검색량 합계.
             API 오류 또는 키워드 없음 시 0 반환.

    동작 상세:
        - hintKeywords=키워드로 요청 시 관련 키워드 목록이 반환됨
        - 요청 키워드와 정확히 일치하는 항목을 우선 선택
        - 정확한 일치가 없으면 첫 번째 항목 사용
    """
    path = "/keywordstool"
    ts   = str(int(time.time() * 1000))  # 현재 시각 (밀리초)

    headers = {
        "X-Timestamp":  ts,
        "X-API-KEY":    api_key,
        "X-Customer":   customer,
        "X-Signature":  _api_sig(secret, ts, "GET", path),
        "Content-Type": "application/json; charset=UTF-8",
    }

    resp = requests.get(
        BASE_URL + path,
        headers=headers,
        params={"hintKeywords": keyword, "showDetail": "1"},
        timeout=10,
    )

    if not resp.ok:
        print(f"  API 오류: {resp.status_code} - {resp.text[:100]}")
        return 0

    kws    = resp.json().get("keywordList", [])
    # 정확히 일치하는 키워드 우선 선택
    exact  = [k for k in kws if k.get("relKeyword", "").strip() == keyword.strip()]
    target = exact[0] if exact else (kws[0] if kws else None)

    if not target:
        return 0

    pc     = _parse_cnt(target.get("monthlyPcQcCnt",     0))
    mobile = _parse_cnt(target.get("monthlyMobileQcCnt", 0))
    return pc + mobile


# ──────────────────────────────────────────────
# 단독 실행 테스트
# ──────────────────────────────────────────────
if __name__ == "__main__":
    # 실제 네이버 검색광고 API 인증 정보로 교체하세요
    CUSTOMER = "1800335"
    API_KEY  = "YOUR_NAVER_SEARCHAD_API_KEY"
    SECRET   = "YOUR_NAVER_SEARCHAD_SECRET"

    test_keywords = ["강남 맛집", "카페 인테리어", "네이버 블로그"]

    print("네이버 검색량 조회 테스트")
    print("=" * 40)

    for kw in test_keywords:
        vol = get_search_volume(kw, CUSTOMER, API_KEY, SECRET)
        print(f"  [{kw}] 월간 검색량: {vol:,}회")
