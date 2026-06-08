# -*- coding: utf-8 -*-
"""
[모듈 04] 카페 회원 검색
=============================
닉네임 또는 네이버 ID로 카페 회원을 검색하여
등급 변경에 필요한 내부 memberid를 획득하는 모듈.

사용 API:
    - ManageMemberAutoCompleteSearchAjax.nhn : 회원 자동완성 검색
    - ManageWholeMember.nhn                  : 회원 관리 페이지 (보조)

※ 로그인된 requests.Session 이 필요합니다.
   Selenium 쿠키 → Session 변환 함수(get_session_from_driver)도 포함.

필요 패키지:
    pip install requests selenium
"""

import json
import re
from typing import Optional, Tuple

import requests

# ─────────────────────────────────────────────
# API 엔드포인트
# ─────────────────────────────────────────────

_SEARCH_URL = "https://cafe.naver.com/ManageMemberAutoCompleteSearchAjax.nhn"
_MANAGE_URL = "https://cafe.naver.com/ManageWholeMember.nhn"

_HEADERS_BASE = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/116.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
}


# ─────────────────────────────────────────────
# 공개 함수
# ─────────────────────────────────────────────

def search_member(
    session: requests.Session,
    cafe_id: str,
    query: str,
) -> Optional[Tuple[str, str]]:
    """
    닉네임 또는 네이버 ID로 카페 회원 검색.

    Args:
        session  : 로그인된 requests.Session
        cafe_id  : 카페 ID (clubid)
        query    : 검색할 닉네임 또는 네이버 ID

    Returns:
        (member_id, nickname) 튜플, 없으면 None
    """
    params = {
        "_callback":  "",
        "clubid":     cafe_id,
        "st":         "100",
        "r_format":   "json",
        "t_koreng":   "1",
        "q_enc":      "UTF-8",
        "r_enc":      "UTF-8",
        "r_unicode":  "0",
        "r_escape":   "1",
        "frm":        "cafe",
        "searchType": "1",
        "q":          query,
    }
    headers = {
        **_HEADERS_BASE,
        "Referer": f"{_MANAGE_URL}?clubid={cafe_id}",
    }

    try:
        resp = session.get(_SEARCH_URL, params=params, headers=headers, timeout=10)
        resp.raise_for_status()

        # 응답이 JSONP 형식( _callback({...}) )일 경우 JSON 부분만 추출
        text = resp.text.strip()
        json_match = re.search(r"\((\{.*\})\)", text, re.DOTALL)
        data = json.loads(json_match.group(1) if json_match else text)

        # 첫 번째 결과에서 id, nickname 추출
        member_id = _nested_list(data, "[0].id")
        nickname  = _nested_list(data, "[0].nickname")

        if member_id:
            print(f"회원 검색 성공: ID={member_id}, 닉네임={nickname}")
            return str(member_id), str(nickname or "")

        print(f"회원을 찾을 수 없음: {query}")
        return None

    except Exception as e:
        print(f"회원 검색 오류 ({query}): {e}")
        return None


def get_session_from_driver(driver) -> requests.Session:
    """
    Selenium WebDriver 의 쿠키를 requests.Session 으로 변환.

    사용 예:
        driver = create_driver()
        naver_login(driver, ID, PW)
        session = get_session_from_driver(driver)

    Args:
        driver: 로그인된 Selenium WebDriver

    Returns:
        네이버 인증 쿠키가 담긴 requests.Session
    """
    session = requests.Session()
    for cookie in driver.get_cookies():
        session.cookies.set(
            cookie["name"],
            cookie["value"],
            domain=cookie.get("domain", ""),
            path=cookie.get("path", "/"),
        )
    return session


# ─────────────────────────────────────────────
# 내부 헬퍼
# ─────────────────────────────────────────────

def _nested_list(data, key_path: str):
    """
    '[0].key' 형식의 경로로 리스트/딕셔너리 값 추출.
    경로가 없으면 None 반환.
    """
    parts = re.split(r"\.(?![^\[]*\])", key_path)
    current = data
    for part in parts:
        list_match = re.match(r"\[(\d+)\]", part)
        if list_match:
            idx = int(list_match.group(1))
            if isinstance(current, list) and idx < len(current):
                current = current[idx]
            else:
                return None
        elif isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current


# ─────────────────────────────────────────────
# 사용 예시
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("이 모듈은 로그인된 requests.Session 이 필요합니다.")
    print()
    print("[ 사용 예시 ]")
    print("  from 01_naver_login import create_driver, naver_login")
    print("  from 04_member_search import search_member, get_session_from_driver")
    print()
    print("  driver  = create_driver()")
    print("  naver_login(driver, 'your_id', 'your_pw')")
    print("  session = get_session_from_driver(driver)")
    print("  result  = search_member(session, '12345678', 'target_nickname')")
    print("  if result:")
    print("      member_id, nickname = result")
