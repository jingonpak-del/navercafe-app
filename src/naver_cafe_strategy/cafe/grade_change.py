# -*- coding: utf-8 -*-
"""
[모듈 05] 등급 변경
=============================
네이버 카페 회원의 등급을 변경하는 모듈.

사용 API:
    - ManageLevelDownCount.nhn : 등급 하향 가능 횟수 확인
    - ManageLevelUp.nhn        : 등급 변경 실행 (상향·하향 모두 이 API 사용)

응답 파싱:
    서버 응답 HTML 내 alert('...') 메시지를 정규식으로 추출하여
    성공/실패 여부를 판단.

필요 패키지:
    pip install requests
"""

import re
import time
from typing import Optional

import requests

# ─────────────────────────────────────────────
# API 엔드포인트
# ─────────────────────────────────────────────

_LEVEL_UP_URL        = "https://cafe.naver.com/ManageLevelUp.nhn"
_LEVEL_DOWN_CNT_URL  = "https://cafe.naver.com/ManageLevelDownCount.nhn"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/116.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,image/apng,*/*;q=0.8,"
        "application/signed-exchange;v=b3;q=0.7"
    ),
    "Content-Type": "application/x-www-form-urlencoded",
    "Origin": "https://cafe.naver.com",
}

# 오류로 판단할 키워드
_FAIL_KEYWORDS = ("실패", "오류", "error", "fail", "권한", "없습니다")


# ─────────────────────────────────────────────
# 공개 함수
# ─────────────────────────────────────────────

def check_level_down_count(
    session: requests.Session,
    cafe_id: str,
    member_id: str,
) -> Optional[dict]:
    """
    등급 하향 가능 횟수 확인.

    Args:
        session   : 로그인된 requests.Session
        cafe_id   : 카페 ID
        member_id : 회원 내부 ID

    Returns:
        서버 응답 dict, 실패 시 None
    """
    headers = {
        **_HEADERS,
        "Referer": f"https://cafe.naver.com/ManageWholeMember.nhn?clubid={cafe_id}",
    }
    payload = {
        "model.clubid":   cafe_id,
        "model.memberid": member_id,
    }
    try:
        resp = session.post(_LEVEL_DOWN_CNT_URL, data=payload, headers=headers, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"등급 하향 횟수 확인 오류: {e}")
        return None


def change_member_grade(
    session: requests.Session,
    cafe_id: str,
    member_id: str,
    target_level: int,
    target_level_name: str,
    comment: str = "",
) -> bool:
    """
    카페 회원 등급 변경.

    Args:
        session           : 로그인된 requests.Session
        cafe_id           : 카페 ID (clubid)
        member_id         : 회원 내부 ID (ManageMemberAutoCompleteSearchAjax 에서 획득)
        target_level      : 변경할 등급 번호 (1~6)
        target_level_name : 변경할 등급명 (예: "정회원")
        comment           : 등급 변경 사유 메모 (선택)

    Returns:
        bool: 변경 성공 여부
    """
    headers = {
        **_HEADERS,
        "Referer": f"https://cafe.naver.com/ManageWholeMember.nhn?clubid={cafe_id}",
    }
    payload = {
        "m":                    "update",
        "model.clubid":         cafe_id,
        "model.acceptType":     "1",
        "fromUpService":        "member",
        "model.memberid":       member_id,
        "model.memberLevelName": target_level_name,
        "callback":             "nhn.cafemanage.member.refreshMemberList",
        "model.memberLevel":    str(target_level),
        "model.comment":        comment,
    }

    try:
        resp = session.post(_LEVEL_UP_URL, data=payload, headers=headers, timeout=10)
        resp.raise_for_status()

        alert_msg = _parse_alert(resp.text)
        if alert_msg:
            print(f"  서버 메시지: {alert_msg}")
            if any(kw in alert_msg for kw in _FAIL_KEYWORDS):
                print(f"  [실패] memberid={member_id}")
                return False

        print(f"  [성공] memberid={member_id} → {target_level}등급({target_level_name})")
        return True

    except Exception as e:
        print(f"  [오류] 등급 변경 중 예외: {e}")
        return False


def change_grade_with_retry(
    session: requests.Session,
    cafe_id: str,
    member_id: str,
    target_level: int,
    target_level_name: str,
    max_retries: int = 3,
    delay: float = 1.0,
) -> bool:
    """
    재시도 로직이 포함된 등급 변경.

    Args:
        max_retries : 최대 재시도 횟수 (기본 3)
        delay       : 재시도 간격 (초, 기본 1.0)

    Returns:
        bool: 최종 성공 여부
    """
    for attempt in range(1, max_retries + 1):
        print(f"  시도 [{attempt}/{max_retries}] memberid={member_id}")
        if change_member_grade(session, cafe_id, member_id, target_level, target_level_name):
            return True
        if attempt < max_retries:
            time.sleep(delay)

    print(f"  [최종 실패] memberid={member_id}")
    return False


# ─────────────────────────────────────────────
# 내부 헬퍼
# ─────────────────────────────────────────────

def _parse_alert(html: str) -> Optional[str]:
    """HTML 응답에서 alert('...') 메시지 추출."""
    match = re.search(r"alert\('([^']*)'\)", html)
    return match.group(1) if match else None


# ─────────────────────────────────────────────
# 사용 예시
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("이 모듈은 로그인된 requests.Session 이 필요합니다.")
    print()
    print("[ 사용 예시 ]")
    print("  from 04_member_search import get_session_from_driver")
    print("  from 05_grade_change  import change_member_grade")
    print()
    print("  session = get_session_from_driver(driver)")
    print("  change_member_grade(session, '12345678', '987654', 2, '정회원')")
