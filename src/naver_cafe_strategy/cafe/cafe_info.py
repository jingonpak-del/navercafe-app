# -*- coding: utf-8 -*-
"""
[모듈 03] 카페 정보 조회
=============================
카페 URL → cafeId(clubid) 변환 및 카페 등급 목록 조회.

사용 API:
    - CafeGateInfo.json   : 카페명 → cafeId
    - CafeMemberLevelInfo : cafeId → 등급 목록 (1~6단계, 등급명)

필요 패키지:
    pip install requests
"""

import re
from typing import Dict, List, Optional

import requests

# ─────────────────────────────────────────────
# API 엔드포인트
# ─────────────────────────────────────────────

_GATE_INFO_URL   = "https://apis.naver.com/cafe-web/cafe2/CafeGateInfo.json?cluburl="
_LEVEL_INFO_URL  = "https://apis.naver.com/cafe-web/cafe-mobile/CafeMemberLevelInfo?cafeId="
_MOBILE_CAFE_URL = "https://m.cafe.naver.com/ca-fe/web/cafes/"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/113.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "x-cafe-product": "mobile",
}


# ─────────────────────────────────────────────
# 공개 함수
# ─────────────────────────────────────────────

def extract_cafe_name(cafe_url: str) -> Optional[str]:
    """
    카페 URL에서 카페명(cluburl) 추출.

    예) "https://cafe.naver.com/mycafe" → "mycafe"
    """
    match = re.search(r"cafe\.naver\.com/([^/?#]+)", cafe_url)
    return match.group(1) if match else None


def get_cafe_id(cafe_url: str,
                session: Optional[requests.Session] = None) -> Optional[str]:
    """
    카페 URL로 cafeId(숫자) 조회.

    Args:
        cafe_url : 네이버 카페 URL
        session  : 로그인 쿠키가 담긴 requests.Session (없으면 비로그인 요청)

    Returns:
        cafeId 문자열 (예: "12345678"), 실패 시 None
    """
    cafe_name = extract_cafe_name(cafe_url)
    if not cafe_name:
        print(f"카페 URL 파싱 실패: {cafe_url}")
        return None

    req = session or requests
    try:
        resp = req.get(_GATE_INFO_URL + cafe_name, headers=_HEADERS, timeout=10)
        resp.raise_for_status()
        cafe_id = _nested(resp.json(), "message.result.cafeInfoView.cafeId")
        if cafe_id:
            print(f"cafeId 조회 성공 [{cafe_name}] → {cafe_id}")
            return str(cafe_id)
        print(f"cafeId를 찾을 수 없음: {cafe_name}")
        return None
    except requests.RequestException as e:
        print(f"카페 정보 조회 오류: {e}")
        return None


def get_grade_list(cafe_id: str,
                   session: Optional[requests.Session] = None) -> List[Dict]:
    """
    카페 등급 목록 조회.

    Returns:
        [{"memberlevel": 1, "memberlevelname": "등급명"}, ...] 형식 리스트.
        실패 시 빈 리스트.
    """
    req = session or requests
    headers = {
        **_HEADERS,
        "Referer": f"{_MOBILE_CAFE_URL}{cafe_id}/member-level",
    }
    try:
        resp = req.get(_LEVEL_INFO_URL + cafe_id, headers=headers, timeout=10)
        resp.raise_for_status()
        grade_list = _nested(resp.json(), "message.result.memberLevelList") or []

        print(f"등급 목록 [{cafe_id}]:")
        for g in grade_list:
            print(f"  {g.get('memberlevel')}등급: {g.get('memberlevelname')}")
        return grade_list

    except requests.RequestException as e:
        print(f"등급 목록 조회 오류: {e}")
        return []


def get_grade_name(grade_list: List[Dict], level: int) -> Optional[str]:
    """
    등급 번호로 등급명 반환.

    Args:
        grade_list : get_grade_list() 결과
        level      : 등급 번호 (1~6)

    Returns:
        등급명 문자열, 없으면 None
    """
    for g in grade_list:
        if g.get("memberlevel") == level:
            return g.get("memberlevelname")
    return None


# ─────────────────────────────────────────────
# 내부 헬퍼
# ─────────────────────────────────────────────

def _nested(data: dict, key_path: str):
    """점(.)으로 구분된 경로로 중첩 dict 값 추출. 없으면 None."""
    current = data
    for key in key_path.split("."):
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return None
    return current


# ─────────────────────────────────────────────
# 사용 예시
# ─────────────────────────────────────────────

if __name__ == "__main__":
    # 비로그인 상태로도 카페 ID·등급 조회 가능 (일부 카페는 로그인 필요)
    TEST_CAFE_URL = "https://cafe.naver.com/testcafe"

    cafe_id = get_cafe_id(TEST_CAFE_URL)
    if cafe_id:
        grades = get_grade_list(cafe_id)
        # 특정 등급명 조회
        name = get_grade_name(grades, 2)
        print(f"2등급 이름: {name}")
