# -*- coding: utf-8 -*-
"""
게시글크롤러 EXE 재빌드 스크립트
실행: python 빌드_게시글크롤러.py
"""

import os
import shutil
import subprocess
import sys

BASE  = os.path.dirname(os.path.abspath(__file__))
SRC   = os.path.join(BASE, "dist", "게시글크롤러", "_internal")
MAIN  = os.path.join(BASE, "메인프로그램.py")  # 루트 소스 파일 우선 사용
DEST  = os.path.join(BASE, "dist", "게시글크롤러")
NEW   = os.path.join(BASE, "dist_new", "게시글크롤러")
BAK   = os.path.join(BASE, "dist_data_bak")

DATA_FILES = [
    "settings.json",
    "naver_cookies.json",
    "credentials.json",
    "token.json",
    "token_monitor.json",
    "monitor_db.json",
    "업체목록.txt",
]

def step(msg):
    print(f"\n{'='*50}\n  {msg}\n{'='*50}")

# 1. 데이터 파일 백업
step("1/4  기존 데이터 파일 백업")
os.makedirs(BAK, exist_ok=True)
for fname in DATA_FILES:
    src = os.path.join(DEST, fname)
    if os.path.exists(src):
        shutil.copy2(src, os.path.join(BAK, fname))
        print(f"  백업: {fname}")
for fname in os.listdir(DEST):
    if fname.endswith(".tsv"):
        shutil.copy2(os.path.join(DEST, fname), os.path.join(BAK, fname))
        print(f"  백업: {fname}")

# 2. PyInstaller 빌드
step("2/4  PyInstaller 빌드")
for d in ["build", "dist_new"]:
    target = os.path.join(BASE, d)
    if os.path.exists(target):
        shutil.rmtree(target)

cmd = [
    sys.executable, "-m", "PyInstaller",
    "--onedir",
    "--windowed",
    "--name", "게시글크롤러",
    "--distpath", os.path.join(BASE, "dist_new"),
    "--add-data", os.path.join(SRC, "01_자동설치.py") + ";.",
    "--add-data", os.path.join(SRC, "02_네이버로그인.py") + ";.",
    "--add-data", os.path.join(SRC, "03_게시글수집.py") + ";.",
    "--add-data", os.path.join(SRC, "04_댓글수집.py") + ";.",
    "--add-data", os.path.join(SRC, "05_구글시트업로드.py") + ";.",
    "--add-data", os.path.join(SRC, "06_설정관리.py") + ";.",
    "--add-data", os.path.join(SRC, "07_자동스케줄러.py") + ";.",
    "--add-data", os.path.join(SRC, "08_모니터링.py") + ";.",
    "--collect-all", "undetected_chromedriver",
    "--collect-all", "selenium",
    "--collect-all", "bs4",
    "--hidden-import", "pyperclip",
    "--hidden-import", "requests",
    "--hidden-import", "google.oauth2.credentials",
    "--hidden-import", "google.auth.transport.requests",
    "--hidden-import", "google_auth_oauthlib.flow",
    "--hidden-import", "googleapiclient.discovery",
    "--hidden-import", "googleapiclient.http",
    "--hidden-import", "googleapiclient._helpers",
    MAIN,
]

result = subprocess.run(cmd, cwd=BASE)
if result.returncode != 0:
    print("\n[오류] 빌드 실패!")
    sys.exit(1)

# 3. 기존 폴더 교체
step("3/4  dist\\게시글크롤러 교체")
if os.path.exists(DEST):
    shutil.rmtree(DEST)
shutil.move(NEW, DEST)

# 4. 데이터 파일 복원
step("4/4  데이터 파일 복원")
for fname in os.listdir(BAK):
    shutil.copy2(os.path.join(BAK, fname), os.path.join(DEST, fname))
    print(f"  복원: {fname}")
shutil.rmtree(BAK)

step("빌드 완료!")
print(f"  → {os.path.join(DEST, '게시글크롤러.exe')}")
input("\nEnter 키를 누르면 종료합니다...")
