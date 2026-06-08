# -*- coding: utf-8 -*-
"""
[00] 전체 흐름 예시 (메인)
=============================
각 모듈을 조합하여 네이버 카페 멤버 등급 일괄 변경 작업을 수행하는 예시.

전체 흐름:
    1. 세팅 파일(CSV/TXT) 로드
    2. Chrome 실행 + 네이버 로그인
    3. Selenium 쿠키 → requests.Session 변환
    4. 카페별로 cafeId 및 등급 목록 캐싱
    5. 각 회원 검색 → memberid 획득
    6. 등급 변경 API 호출
    7. 결과 CSV 저장 + 요약 출력

필요 패키지:
    pip install selenium requests

모듈 구성:
    01_naver_login.py   - Chrome 드라이버 생성 / 네이버 로그인
    02_load_settings.py - CSV / TXT 세팅 파일 파싱
    03_cafe_info.py     - cafeId 조회 / 등급 목록 조회
    04_member_search.py - 회원 검색 (memberid 획득)
    05_grade_change.py  - 등급 변경 API 호출
    06_work_log.py      - 결과 로그 및 CSV 저장
"""

import os
import time

# ── 모듈 임포트 ──────────────────────────────
from naver_cafe_strategy.auth.naver_login import create_driver, naver_login         # 01
from naver_cafe_strategy.io.load_member_tasks import load_file, MemberTask              # 02
from naver_cafe_strategy.cafe.cafe_info import get_cafe_id, get_grade_list, get_grade_name  # 03
from naver_cafe_strategy.cafe.member_search import search_member, get_session_from_driver       # 04
from naver_cafe_strategy.cafe.grade_change import change_grade_with_retry            # 05
from naver_cafe_strategy.io.work_log import WorkLogger                         # 06

# ─────────────────────────────────────────────
# 설정값
# ─────────────────────────────────────────────

NAVER_ID   = "your_naver_id"      # 등급 변경 권한이 있는 관리자 계정
NAVER_PW   = "your_naver_pw"

SETTINGS_FILE  = "텍스트 세팅 파일.txt"   # 또는 "CSV 세팅 파일.csv"
RESULT_DIR     = "./작업 내역"
DELAY_BETWEEN  = 0.5               # 회원 간 요청 딜레이 (초)


# ─────────────────────────────────────────────
# 메인
# ─────────────────────────────────────────────

def main():
    # 1) 세팅 파일 로드
    tasks = load_file(SETTINGS_FILE)
    if not tasks:
        print("작업 목록이 비어있습니다.")
        return

    print(f"\n총 {len(tasks)}건 작업 시작\n")

    # 2) Chrome 실행 + 로그인
    driver = create_driver()
    try:
        if not naver_login(driver, NAVER_ID, NAVER_PW):
            print("로그인 실패. 종료합니다.")
            return

        # 3) Selenium 쿠키 → requests.Session
        session = get_session_from_driver(driver)

        # 4) 로거 초기화
        logger = WorkLogger(save_dir=RESULT_DIR)

        # 카페별 cafeId / 등급 목록 캐시 (같은 카페 반복 조회 방지)
        cafe_cache: dict[str, tuple] = {}  # {cafe_url: (cafe_id, grade_list)}

        # 5) 작업 루프
        for i, task in enumerate(tasks, 1):
            print(f"\n[{i}/{len(tasks)}] {task.cafe_url} | "
                  f"{task.member_id or task.nickname} | 등급→{task.target_grade}")

            # 카페 정보 캐싱
            if task.cafe_url not in cafe_cache:
                cafe_id = get_cafe_id(task.cafe_url, session)
                if not cafe_id:
                    logger.error(task.cafe_url, task.member_id, task.nickname,
                                 task.target_grade, "cafeId 조회 실패")
                    continue
                grade_list = get_grade_list(cafe_id, session)
                cafe_cache[task.cafe_url] = (cafe_id, grade_list)

            cafe_id, grade_list = cafe_cache[task.cafe_url]

            # 등급명 조회
            grade_name = get_grade_name(grade_list, task.target_grade)
            if not grade_name:
                logger.error(task.cafe_url, task.member_id, task.nickname,
                             task.target_grade, f"{task.target_grade}등급 정보 없음")
                continue

            # 회원 검색 (ID 우선, 없으면 닉네임으로 검색)
            query  = task.member_id or task.nickname
            result = search_member(session, cafe_id, query)
            if not result:
                logger.failure(task.cafe_url, task.member_id, task.nickname,
                               task.target_grade, "회원을 찾을 수 없음")
                continue

            member_id, nickname = result

            # 등급 변경
            success = change_grade_with_retry(
                session, cafe_id, member_id,
                task.target_grade, grade_name,
                max_retries=3, delay=1.0,
            )

            if success:
                logger.success(task.cafe_url, task.member_id, nickname,
                               task.target_grade, grade_name)
            else:
                logger.failure(task.cafe_url, task.member_id, nickname,
                               task.target_grade, "등급 변경 API 실패")

            time.sleep(DELAY_BETWEEN)

        # 6) 결과 저장 및 요약
        logger.summary()
        logger.save()

        # 실패 건 재확인
        failed = logger.failed_list()
        if failed:
            print(f"실패/오류 {len(failed)}건은 결과 CSV에서 확인하세요.")

    finally:
        driver.quit()


if __name__ == "__main__":
    main()
