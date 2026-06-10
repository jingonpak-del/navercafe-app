# -*- coding: utf-8 -*-
"""
카페게시판게시글크롤러 v2 EXE 빌드 스크립트
=========================================
실행: python 빌드_카페게시판게시글크롤러_v2.py

■ 빌드 결과
    dist\카페게시판게시글크롤러_v2_빌드\
        카페게시판게시글크롤러.exe    ← 실행 파일
        _internal\                    ← 런타임 의존 파일 (PyInstaller 6.x)
        config\                       ← 첫 실행 시 자동 생성 (설정 파일)
        logs\                         ← 첫 실행 시 자동 생성 (로그)

■ 포함 기능
    - 네이버 카페 게시판 실시간 수집
    - 구글 드라이브 / 스프레드시트 자동 업로드
    - 게시글 제목 변경 모니터링 (D+1 / D+3 / D+5)
"""

import os
import shutil
import subprocess
import sys

# ── 경로 설정 ─────────────────────────────────────────────────────────
BASE      = os.path.dirname(os.path.abspath(__file__))
SRC_DIR   = os.path.join(BASE, "dist", "카페게시판게시글크롤러_v2")       # 소스 루트
SRC_MOD   = os.path.join(SRC_DIR, "src")                                   # 모듈 폴더
MAIN      = os.path.join(SRC_DIR, "main.py")                               # 진입점
DEST      = os.path.join(BASE, "dist", "카페게시판게시글크롤러_v2_빌드")   # 최종 출력
WORK_DIR  = os.path.join(BASE, "_build_v2_work")                           # PyInstaller work
DIST_TMP  = os.path.join(BASE, "_build_v2_dist")                           # PyInstaller dist 임시
BAK_DIR   = os.path.join(BASE, "_build_v2_config_bak")                     # 설정 백업

# 백업할 설정 파일 목록 (DEST/config/ 안에 있는 파일들)
CONFIG_FILES = [
    "settings.json",
    "naver_cookies.json",
    "credentials.json",
    "token.json",
    "monitor_db.json",
]

EXE_NAME = "카페게시판게시글크롤러"


# ─────────────────────────────────────────────────────────────────────
def step(n: int, total: int, msg: str):
    print(f"\n{'='*55}\n  [{n}/{total}] {msg}\n{'='*55}")


def rmdir(path: str):
    if os.path.exists(path):
        shutil.rmtree(path)
        print(f"  삭제: {path}")


# ─────────────────────────────────────────────────────────────────────
# 1. 소스 검증
# ─────────────────────────────────────────────────────────────────────
step(1, 6, "소스 파일 검증")

if not os.path.exists(MAIN):
    print(f"\n[오류] 소스 파일 없음: {MAIN}")
    print("  dist\\카페게시판게시글크롤러_v2\\ 폴더가 있는지 확인하세요.")
    sys.exit(1)

print(f"  ✓ 소스 루트  : {SRC_DIR}")
print(f"  ✓ 진입점     : {MAIN}")
print(f"  ✓ 모듈 폴더  : {SRC_MOD}")


# ─────────────────────────────────────────────────────────────────────
# 2. 기존 설정 파일 백업
# ─────────────────────────────────────────────────────────────────────
step(2, 6, "기존 설정 파일 백업")

os.makedirs(BAK_DIR, exist_ok=True)
backed_up = []
for fname in CONFIG_FILES:
    src = os.path.join(DEST, "config", fname)
    if os.path.exists(src):
        shutil.copy2(src, os.path.join(BAK_DIR, fname))
        backed_up.append(fname)
        print(f"  백업: {fname}")

if not backed_up:
    print("  (백업할 기존 설정 파일 없음)")


# ─────────────────────────────────────────────────────────────────────
# 3. 임시 빌드 폴더 정리
# ─────────────────────────────────────────────────────────────────────
step(3, 6, "임시 빌드 폴더 정리")

rmdir(WORK_DIR)
rmdir(DIST_TMP)


# ─────────────────────────────────────────────────────────────────────
# 4. PyInstaller 빌드
# ─────────────────────────────────────────────────────────────────────
step(4, 6, "PyInstaller 빌드")

cmd = [
    sys.executable, "-m", "PyInstaller",

    # ── 기본 옵션 ────────────────────────────────────────────────────
    "--onedir",                  # 폴더형 (빠른 실행, config/ 관리 용이)
    "--console",                 # 콘솔 창 표시 (로그 출력)
    "--name", EXE_NAME,

    # ── 출력 경로 ────────────────────────────────────────────────────
    "--distpath", DIST_TMP,
    "--workpath", WORK_DIR,
    "--specpath", WORK_DIR,

    # ── 모듈 탐색 경로 (src/ 안의 모듈들을 찾기 위해) ────────────────
    "--paths", SRC_MOD,

    # ── 명시적 hidden import (동적 import 등 자동 감지 불가 항목) ─────
    "--hidden-import", "installer",
    "--hidden-import", "config_manager",
    "--hidden-import", "login",
    "--hidden-import", "crawler",
    "--hidden-import", "gdrive",
    "--hidden-import", "scheduler",
    "--hidden-import", "monitor_register",
    "--hidden-import", "monitor_checker",
    "--hidden-import", "requests",
    "--hidden-import", "bs4",
    "--hidden-import", "pyperclip",
    "--hidden-import", "google.oauth2.credentials",
    "--hidden-import", "google.auth.transport.requests",
    "--hidden-import", "google_auth_oauthlib.flow",
    "--hidden-import", "googleapiclient.discovery",
    "--hidden-import", "googleapiclient.http",
    "--hidden-import", "googleapiclient.errors",
    "--hidden-import", "selenium.webdriver.common.by",
    "--hidden-import", "selenium.webdriver.common.keys",

    # ── 패키지 전체 수집 (데이터 파일 포함) ──────────────────────────
    "--collect-all", "undetected_chromedriver",
    "--collect-all", "selenium",
    "--collect-all", "bs4",
    "--collect-all", "certifi",

    MAIN,
]

print("  PyInstaller 실행 중... (수분 소요)")
print(f"  명령: {' '.join(cmd[:6])} ...\n")

result = subprocess.run(cmd, cwd=BASE)
if result.returncode != 0:
    print("\n[오류] PyInstaller 빌드 실패!")
    print("  → 위 오류 메시지를 확인하고 필요한 패키지를 설치하세요.")
    print("  → pip install pyinstaller")
    rmdir(BAK_DIR)
    sys.exit(1)

print("\n  ✓ PyInstaller 빌드 완료")


# ─────────────────────────────────────────────────────────────────────
# 5. 출력 폴더 교체
# ─────────────────────────────────────────────────────────────────────
step(5, 6, "출력 폴더 교체")

built = os.path.join(DIST_TMP, EXE_NAME)
if not os.path.exists(built):
    print(f"\n[오류] 빌드 결과 폴더 없음: {built}")
    sys.exit(1)

rmdir(DEST)
shutil.move(built, DEST)
print(f"  ✓ 이동 완료: {DEST}")

# 임시 폴더 정리
rmdir(WORK_DIR)
rmdir(DIST_TMP)


# ─────────────────────────────────────────────────────────────────────
# 6. 설정 파일 복원
# ─────────────────────────────────────────────────────────────────────
step(6, 6, "설정 파일 복원")

if backed_up:
    config_dest = os.path.join(DEST, "config")
    os.makedirs(config_dest, exist_ok=True)
    for fname in backed_up:
        shutil.copy2(os.path.join(BAK_DIR, fname), os.path.join(config_dest, fname))
        print(f"  복원: {fname}")
else:
    print("  (복원할 설정 파일 없음 — 첫 실행 시 자동 생성됩니다)")

rmdir(BAK_DIR)


# ─────────────────────────────────────────────────────────────────────
# 완료
# ─────────────────────────────────────────────────────────────────────
print("\n" + "=" * 55)
print("  빌드 완료!")
print("=" * 55)
print(f"\n  실행 파일 위치:")
print(f"  {os.path.join(DEST, EXE_NAME + '.exe')}")
print(f"\n  처음 실행 시:")
print(f"  1. 카페게시판게시글크롤러.exe 실행")
print(f"  2. 네이버 ID/PW 입력 (로그인 창 자동 오픈)")
print(f"  3. 구글 드라이브 폴더 ID 입력")
print(f"  4. 카페 주소명 / 카페 ID / 게시판 ID 입력")
print(f"  ※ config\\credentials.json 을 config\\ 폴더에 넣어야 합니다.")

input("\n  Enter 키를 누르면 종료합니다...")
