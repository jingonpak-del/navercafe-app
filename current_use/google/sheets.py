# -*- coding: utf-8 -*-
"""
[모듈 02] 구글 시트 연동
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
역할:
    Google Sheets API를 통해 스프레드시트에 접속하고,
    데이터를 읽고 쓰는 기능을 제공합니다.

인증 방식:
    Google Cloud의 '서비스 계정(Service Account)'을 사용합니다.
    서비스 계정은 사람이 아닌 프로그램을 위한 구글 계정으로,
    JSON 키 파일(예: cafemarketingkey.json)을 통해 인증합니다.

    ※ 사용 전 준비:
       1. Google Cloud Console에서 서비스 계정 생성
       2. JSON 키 파일 다운로드
       3. 해당 스프레드시트를 서비스 계정 이메일 주소로 '편집자' 공유

스프레드시트 열 구조 (이 프로그램 기준):
    A열: 순번
    B열: 키워드 (처리 기준, 비어있으면 해당 행 처리 종료)
    C열: 카페 게시글 링크
    D열: 게시글 제목 [자동 입력]
    E열: 월간 검색량 [자동 입력]
    F열: 노출구좌 (카X블X지X기X 형식) [자동 입력]
    G열: 검색결과 타입 (A 또는 B) [자동 입력]
    H열: A박스 섹션 목록 [자동 입력]
    I열: 일반 섹션 목록 [자동 입력]
    J열: 노출 여부 (O 또는 X) [자동 입력]
    K열~: 조회수 히스토리 (실행마다 새 열 추가) [자동 입력]

J,K열 히스토리 관리 방식:
    - 첫 실행: K1 헤더가 '조회수' 또는 비어있으면 → J1,K1 헤더를 날짜시간으로 변경만 함
    - 재실행: J(index=9),K(index=10) 위치에 새 열 2개 삽입 → 최신 데이터가 항상 J,K열
    - 이전 J,K 데이터는 L,M 열로 밀려나 히스토리 유지 (2열 쌍으로 보존)

사전 준비:
    pip install gspread google-auth
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import re
import json
from datetime import datetime

import gspread
from google.oauth2.service_account import Credentials


# 구글 API 접근 권한 범위
GSCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",  # 시트 읽기/쓰기
    "https://www.googleapis.com/auth/drive",          # 드라이브 접근
]


def extract_sheet_id(url: str) -> str:
    """
    구글 시트 URL에서 Sheet ID를 추출합니다.

    지원 URL 형식:
        https://docs.google.com/spreadsheets/d/{ID}/edit
        https://docs.google.com/spreadsheets/d/{ID}/edit?usp=sharing
        https://docs.google.com/spreadsheets/d/{ID}/edit?gid=0#gid=0

    Returns:
        str: Sheet ID 문자열, 추출 실패 시 빈 문자열
    """
    m = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", url)
    return m.group(1) if m else ""


def get_service_email(key_path: str) -> str:
    """
    JSON 키 파일에서 서비스 계정 이메일을 읽어 반환합니다.
    스프레드시트 공유 시 이 이메일 주소를 편집자로 추가해야 합니다.

    Returns:
        str: 이메일 주소 (예: cafemarketing@project.iam.gserviceaccount.com)
    """
    try:
        with open(key_path, encoding="utf-8") as f:
            return json.load(f).get("client_email", "")
    except Exception:
        return ""


def open_sheet(key_path: str, sheet_url: str, sheet_name: str):
    """
    구글 스프레드시트에 연결하여 Spreadsheet, Worksheet 객체를 반환합니다.

    Args:
        key_path   (str): 서비스 계정 JSON 키 파일 경로
        sheet_url  (str): 구글 시트 URL (어떤 형식이든 가능)
        sheet_name (str): 시트 탭 이름 (예: '시트1', 'Sheet1')

    Returns:
        tuple: (Spreadsheet 객체, Worksheet 객체)

    Raises:
        ValueError: URL에서 Sheet ID를 추출할 수 없을 때
        gspread.exceptions.SpreadsheetNotFound: 시트를 찾을 수 없을 때
        gspread.exceptions.WorksheetNotFound: 탭 이름이 없을 때
    """
    sheet_id = extract_sheet_id(sheet_url)
    if not sheet_id:
        raise ValueError("유효하지 않은 구글 시트 URL입니다.")

    creds = Credentials.from_service_account_file(key_path, scopes=GSCOPES)
    gc    = gspread.authorize(creds)
    sh    = gc.open_by_key(sheet_id)
    ws    = sh.worksheet(sheet_name)
    return sh, ws


def get_data_rows(ws) -> list:
    """
    시트에서 2행부터 B열(키워드)이 있는 모든 행을 읽어 반환합니다.
    1행은 헤더로 간주하여 건너뜁니다.

    Returns:
        list of dict: [{"row_idx": 2, "B": "키워드", "C": "링크"}, ...]
    """
    rows   = ws.get_all_values()
    result = []
    for i, row in enumerate(rows[1:], start=2):
        while len(row) < 11:
            row.append("")
        keyword = row[1].strip()  # B열
        link    = row[2].strip()  # C열
        if keyword:
            result.append({"row_idx": i, "B": keyword, "C": link})
    return result


def prepare_history_columns(ws, sh, now: datetime) -> tuple:
    """
    J열(노출여부)과 K열(조회수) 히스토리 열을 준비합니다.

    동작:
        - K1 헤더가 '조회수' 또는 비어있음 → J1,K1 헤더를 날짜시간으로 교체만 (삽입 없음)
        - K1 헤더에 이미 날짜가 있음 → J(index=9),K(index=10) 위치에 새 열 2개 삽입 후 헤더 설정
          (기존 J,K 데이터는 L,M 열로 밀려 히스토리 보존)

    헤더 형식:
        J열: "노출(MMDD HH:MM)"  예: 노출(0512 12:00)
        K열: "조회(MMDD)"        예: 조회(0512)

    Args:
        ws  : Worksheet 객체
        sh  : Spreadsheet 객체
        now : datetime 객체 (헤더 날짜시간 생성용)

    Returns:
        tuple: (j_col, k_col) 열 번호 (1-indexed, 항상 (10, 11) = J,K열)
    """
    j_hdr = f"노출({now.strftime('%m%d %H:%M')})"   # 예: 노출(0512 12:00)
    k_hdr = f"조회({now.strftime('%m%d')})"           # 예: 조회(0512)
    current_k = ws.cell(1, 11).value or ""

    if current_k in ("조회수", ""):
        # 첫 실행: 헤더만 변경
        ws.update_cell(1, 10, j_hdr)  # J1
        ws.update_cell(1, 11, k_hdr)  # K1
    else:
        # 재실행: J·K 위치에 새 열 2개 삽입
        sh.batch_update({"requests": [
            {"insertDimension": {
                "range": {"sheetId": ws.id, "dimension": "COLUMNS",
                          "startIndex": 9, "endIndex": 10},
                "inheritFromBefore": False,
            }},
            {"insertDimension": {
                "range": {"sheetId": ws.id, "dimension": "COLUMNS",
                          "startIndex": 10, "endIndex": 11},
                "inheritFromBefore": False,
            }},
        ]})
        ws.update_cell(1, 10, j_hdr)  # 새 J1
        ws.update_cell(1, 11, k_hdr)  # 새 K1

    return 10, 11  # j_col, k_col (1-indexed)


def write_row(ws, row_idx: int, vals: dict, k_col: int):
    """
    한 행의 결과값을 시트에 기록합니다.
    D~J열을 일괄 업데이트하고, K열에 조회수를 기록합니다.

    Args:
        ws       : Worksheet 객체
        row_idx  : 기록할 행 번호 (1-indexed, 예: 2)
        vals     : 결과 딕셔너리. 키: 'd','e','f','g','h','i','j','k'
                   없는 키는 빈 문자열로 처리
        k_col    : 조회수 열 번호 (1-indexed, 보통 11)

    열-키 매핑:
        D=d(제목), E=e(검색량), F=f(노출구좌), G=g(타입),
        H=h(A박스), I=i(일반섹션), J=j(노출여부), K=k(조회수)
    """
    cells_dj = [
        vals.get("d", ""),  # D: 게시글 제목
        vals.get("e", ""),  # E: 월간 검색량
        vals.get("f", ""),  # F: 노출구좌
        vals.get("g", ""),  # G: A/B 타입
        vals.get("h", ""),  # H: A박스 목록
        vals.get("i", ""),  # I: 일반 섹션 목록
        vals.get("j", ""),  # J: 노출 여부
    ]
    # D열~J열 일괄 업데이트
    ws.update(
        values=[[str(v) for v in cells_dj]],
        range_name=f"D{row_idx}:J{row_idx}",
    )
    # K열(조회수) 별도 업데이트
    if "k" in vals:
        ws.update_cell(row_idx, k_col, str(vals["k"]))


# ──────────────────────────────────────────────
# 단독 실행 테스트
# ──────────────────────────────────────────────
if __name__ == "__main__":
    import os

    # 테스트용 설정 (실제 값으로 교체 필요)
    KEY_PATH   = "cafemarketingkey.json"   # 서비스 계정 JSON 키 파일
    SHEET_URL  = "여기에_구글시트_URL_입력"
    SHEET_NAME = "시트1"

    print("구글 시트 연동 테스트")
    print("=" * 40)

    # 서비스 계정 이메일 확인
    email = get_service_email(KEY_PATH)
    print(f"서비스 계정 이메일: {email}")
    print(f"→ 위 이메일을 시트에 편집자로 공유해야 합니다.")
    print()

    # 시트 연결
    print("시트 연결 중...")
    sh, ws = open_sheet(KEY_PATH, SHEET_URL, SHEET_NAME)
    print("연결 성공!")

    # 데이터 행 읽기
    rows = get_data_rows(ws)
    print(f"처리 대상: {len(rows)}행")
    for r in rows[:3]:  # 처음 3행만 출력
        print(f"  행{r['row_idx']}: 키워드={r['B']}, 링크={r['C'][:30] if r['C'] else '없음'}")
