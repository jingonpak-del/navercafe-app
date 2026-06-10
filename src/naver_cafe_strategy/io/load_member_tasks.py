# -*- coding: utf-8 -*-
"""
[모듈 02] 세팅 파일 로드
=============================
CSV 또는 TXT 세팅 파일을 읽어 작업 대상 목록을 반환하는 모듈.

파일 형식 (쉼표 구분):
    카페URL , 네이버ID , 닉네임 , 변경등급(1~6)

규칙:
    - 네이버ID와 닉네임 중 하나만 입력해도 됨
    - TXT: 한 줄에 하나씩, 쉼표로 구분
    - CSV: 셀 단위로 구분 (엑셀 저장 형식 그대로 사용 가능)
"""

import csv
import os
from dataclasses import dataclass
from typing import List, Optional


# ─────────────────────────────────────────────
# 데이터 클래스
# ─────────────────────────────────────────────

@dataclass
class MemberTask:
    """작업 대상 멤버 한 건."""
    cafe_url:     str
    member_id:    Optional[str]   # 네이버 ID (없으면 None)
    nickname:     Optional[str]   # 카페 닉네임 (없으면 None)
    target_grade: int             # 변경할 등급 번호 (1~6)


# ─────────────────────────────────────────────
# 공개 함수
# ─────────────────────────────────────────────

def load_file(file_path: str) -> List[MemberTask]:
    """
    확장자(.txt / .csv)를 자동 감지하여 파일 로드.

    Args:
        file_path: 세팅 파일 경로

    Returns:
        MemberTask 리스트
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {file_path}")

    ext = os.path.splitext(file_path)[1].lower()

    if ext == ".csv":
        return _load_csv(file_path)
    elif ext == ".txt":
        return _load_txt(file_path)
    else:
        raise ValueError(f"지원하지 않는 형식: {ext}  (.csv 또는 .txt 만 가능)")


def print_tasks(tasks: List[MemberTask]) -> None:
    """작업 목록을 콘솔에 출력."""
    print(f"\n{'='*60}")
    print(f"총 {len(tasks)}건 로드")
    print(f"{'='*60}")
    for i, t in enumerate(tasks, 1):
        ident = t.member_id or t.nickname
        print(f"[{i:4d}] {t.cafe_url}  |  {ident}  |  등급 {t.target_grade}")
    print(f"{'='*60}\n")


# ─────────────────────────────────────────────
# 내부 파서
# ─────────────────────────────────────────────

def _load_txt(file_path: str) -> List[MemberTask]:
    """TXT 파일 파싱 (쉼표 구분)."""
    tasks = []
    with open(file_path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            parts = [p.strip() for p in line.split(",")]
            task = _parse_row(parts, line_num)
            if task:
                tasks.append(task)

    print(f"[TXT] {len(tasks)}건 로드 완료: {file_path}")
    return tasks


def _load_csv(file_path: str) -> List[MemberTask]:
    """CSV 파일 파싱 (셀 구분)."""
    tasks = []
    with open(file_path, "r", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        for line_num, row in enumerate(reader, 1):
            if not row or all(c.strip() == "" for c in row):
                continue
            parts = [c.strip() for c in row]
            task = _parse_row(parts, line_num)
            if task:
                tasks.append(task)

    print(f"[CSV] {len(tasks)}건 로드 완료: {file_path}")
    return tasks


def _parse_row(parts: List[str], line_num: int) -> Optional[MemberTask]:
    """
    컬럼 리스트 → MemberTask 변환.
    유효하지 않으면 경고 출력 후 None 반환.
    """
    if len(parts) < 4:
        print(f"  [경고 L{line_num}] 컬럼 부족 (건너뜀): {parts}")
        return None

    cafe_url  = parts[0]
    member_id = parts[1] or None
    nickname  = parts[2] or None

    # ID / 닉네임 둘 다 없으면 스킵
    if not member_id and not nickname:
        print(f"  [경고 L{line_num}] ID·닉네임 모두 비어있음 (건너뜀)")
        return None

    # 등급 유효성 검사
    try:
        grade = int(parts[3])
        assert 1 <= grade <= 6
    except (ValueError, AssertionError):
        print(f"  [경고 L{line_num}] 등급 값 오류 — 1~6 사이 정수여야 함: '{parts[3]}' (건너뜀)")
        return None

    # 카페 URL 형식 검사
    if not cafe_url.startswith("https://cafe.naver.com/"):
        print(f"  [경고 L{line_num}] URL 형식 오류: {cafe_url} (건너뜀)")
        return None

    return MemberTask(
        cafe_url=cafe_url,
        member_id=member_id,
        nickname=nickname,
        target_grade=grade,
    )


# ─────────────────────────────────────────────
# 사용 예시
# ─────────────────────────────────────────────

if __name__ == "__main__":
    # 테스트용 TXT 파일 생성
    sample_txt = "sample_tasks.txt"
    with open(sample_txt, "w", encoding="utf-8") as f:
        f.write("https://cafe.naver.com/testcafe,testid1,,2\n")
        f.write("https://cafe.naver.com/testcafe,testid2,테스트닉네임,3\n")
        f.write("https://cafe.naver.com/testcafe,,닉네임만,1\n")

    tasks = load_file(sample_txt)
    print_tasks(tasks)

    os.remove(sample_txt)
