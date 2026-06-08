# -*- coding: utf-8 -*-
"""
[모듈 06] 작업 로그
=============================
작업 결과를 콘솔에 실시간 출력하고 CSV 파일로 저장하는 모듈.

저장 파일 형식:
    {YYYYMMDD HHmmss}.csv
    컬럼: 카페URL, ID, 닉네임, 등급, 결과, 메시지, 시간
"""

import csv
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


# ─────────────────────────────────────────────
# 데이터 클래스
# ─────────────────────────────────────────────

@dataclass
class WorkResult:
    """작업 결과 한 건."""
    cafe_url:     str
    member_id:    Optional[str]
    nickname:     Optional[str]
    target_grade: int
    status:       str            # "성공" / "실패" / "오류"
    message:      str = ""
    timestamp:    datetime = field(default_factory=datetime.now)


# ─────────────────────────────────────────────
# 로거 클래스
# ─────────────────────────────────────────────

class WorkLogger:
    """
    작업 결과 수집 및 저장 클래스.

    사용 예:
        logger = WorkLogger(save_dir="./작업 내역")
        logger.success(cafe_url, member_id, nickname, grade)
        logger.failure(cafe_url, member_id, nickname, grade, "회원 없음")
        logger.save()
        logger.summary()
    """

    def __init__(self, save_dir: str = "."):
        """
        Args:
            save_dir: 결과 CSV를 저장할 디렉토리 경로
        """
        self.save_dir = save_dir
        self.results: List[WorkResult] = []

    # ── 로그 기록 ─────────────────────────────

    def success(self, cafe_url: str, member_id: Optional[str],
                nickname: Optional[str], grade: int, message: str = "") -> None:
        """성공 로그."""
        self._add(cafe_url, member_id, nickname, grade, "성공", message)

    def failure(self, cafe_url: str, member_id: Optional[str],
                nickname: Optional[str], grade: int, message: str = "") -> None:
        """실패 로그."""
        self._add(cafe_url, member_id, nickname, grade, "실패", message)

    def error(self, cafe_url: str, member_id: Optional[str],
              nickname: Optional[str], grade: int, message: str = "") -> None:
        """오류 로그."""
        self._add(cafe_url, member_id, nickname, grade, "오류", message)

    # ── 저장 / 출력 ───────────────────────────

    def save(self, filename: Optional[str] = None) -> str:
        """
        전체 결과를 CSV 파일로 저장.

        Args:
            filename: 저장 파일명 (None이면 타임스탬프로 자동 생성)

        Returns:
            저장된 파일의 전체 경로
        """
        os.makedirs(self.save_dir, exist_ok=True)

        if not filename:
            filename = f"{datetime.now():%Y%m%d %H%M%S}.csv"

        path = os.path.join(self.save_dir, filename)

        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["카페URL", "ID", "닉네임", "등급", "결과", "메시지", "시간"])
            for r in self.results:
                writer.writerow([
                    r.cafe_url,
                    r.member_id  or "",
                    r.nickname   or "",
                    r.target_grade,
                    r.status,
                    r.message,
                    r.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                ])

        print(f"\n결과 저장 완료: {path}")
        return path

    def summary(self) -> None:
        """작업 요약 콘솔 출력."""
        total   = len(self.results)
        success = sum(1 for r in self.results if r.status == "성공")
        failure = sum(1 for r in self.results if r.status == "실패")
        error   = sum(1 for r in self.results if r.status == "오류")

        print(f"\n{'='*40}")
        print(f" 작업 완료 요약")
        print(f"{'='*40}")
        print(f" 총 작업 : {total}건")
        print(f"   성공  : {success}건")
        print(f"   실패  : {failure}건")
        print(f"   오류  : {error}건")
        print(f"{'='*40}\n")

    def failed_list(self) -> List[WorkResult]:
        """실패 및 오류 건만 반환 (재처리 용도)."""
        return [r for r in self.results if r.status in ("실패", "오류")]

    # ── 내부 헬퍼 ─────────────────────────────

    def _add(self, cafe_url: str, member_id: Optional[str], nickname: Optional[str],
             grade: int, status: str, message: str) -> None:
        result = WorkResult(
            cafe_url=cafe_url,
            member_id=member_id,
            nickname=nickname,
            target_grade=grade,
            status=status,
            message=message,
        )
        self.results.append(result)
        self._print(result)

    @staticmethod
    def _print(r: WorkResult) -> None:
        """단일 결과를 콘솔에 출력."""
        ident = r.member_id or r.nickname or "?"
        line  = f"[{r.timestamp:%H:%M:%S}] :: [{ident}] {r.status}"
        if r.message:
            line += f" — {r.message}"
        print(line)


# ─────────────────────────────────────────────
# 사용 예시
# ─────────────────────────────────────────────

if __name__ == "__main__":
    logger = WorkLogger(save_dir="./작업 내역")

    logger.success("https://cafe.naver.com/test", "testid1", "닉네임1", 2)
    logger.failure("https://cafe.naver.com/test", "testid2", None,      3, "회원을 찾을 수 없음")
    logger.success("https://cafe.naver.com/test", None,      "닉네임3", 1)
    logger.error(  "https://cafe.naver.com/test", "testid4", None,      2, "네트워크 오류")

    logger.summary()
    logger.save()

    # 실패/오류 건 재처리 예시
    failed = logger.failed_list()
    print(f"재처리 대상: {len(failed)}건")
