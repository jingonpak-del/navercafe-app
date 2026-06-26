from __future__ import annotations

import argparse
import subprocess
import sys
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DIST_ROOT = PROJECT_ROOT / "dist" / "fe_board_archive"
APP_NAME = "NaverCafeBoardArchive"
APP_DIR = DIST_ROOT / APP_NAME
EXE_PATH = APP_DIR / f"{APP_NAME}.exe"
ZIP_PATH = DIST_ROOT / f"{APP_NAME}_portable.zip"

README_TEXT = """Naver Cafe 게시판 아카이브 - 포터블 실행 안내
=================================================

1. 폴더 전체를 원하는 PC에 복사합니다.
2. Chrome이 설치되어 있어야 합니다.
3. NaverCafeBoardArchive.exe를 실행합니다.
4. 목록만 테스트는 로그인 없이 가능합니다.
5. 본문/사진 저장은 네이버 로그인이 필요합니다.
   - GUI의 '로그인 갱신' 버튼을 누릅니다.
   - 열린 Chrome에서 CAPTCHA/2FA가 나오면 직접 완료합니다.
   - 로그인 상태가 유효해지면 '목록만 테스트' 체크를 끄고 수집을 시작합니다.

저장 위치
---------
- 기본 수집 결과: output/naver_cafe_archive
- 프리셋: data/fe_board_archive_presets.json
- 로그인 쿠키: data/session/naver_cookies.json

주의
----
- data/ 폴더에는 로그인 쿠키가 저장될 수 있으므로 다른 사람에게 공유하지 마세요.
- 카페/네이버 정책과 저작권/개인정보 보호 기준을 지켜 내부 보관 목적으로만 사용하세요.
"""


def run_build(clean: bool) -> None:
    cmd = [sys.executable, str(PROJECT_ROOT / "scripts" / "build_fe_board_archive_exe.py")]
    if clean:
        cmd.append("--clean")
    subprocess.run(cmd, cwd=PROJECT_ROOT, check=True)


def write_portable_files(app_dir: Path) -> None:
    (app_dir / "README_FIRST.txt").write_text(README_TEXT, encoding="utf-8")
    (app_dir / "start.cmd").write_text(
        '@echo off\r\ncd /d "%~dp0"\r\nstart "" "NaverCafeBoardArchive.exe"\r\n',
        encoding="utf-8",
    )
    (app_dir / "data").mkdir(exist_ok=True)
    (app_dir / "output").mkdir(exist_ok=True)


def make_zip(app_dir: Path, zip_path: Path) -> None:
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in app_dir.rglob("*"):
            if path.is_file():
                zf.write(path, path.relative_to(app_dir.parent))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a portable ZIP for the Naver Cafe board archive GUI.")
    parser.add_argument("--skip-build", action="store_true", help="Use an existing PyInstaller output folder.")
    parser.add_argument("--clean", action="store_true", help="Clean build/dist before rebuilding the exe.")
    args = parser.parse_args(argv)

    if not args.skip_build:
        run_build(clean=args.clean)
    if not EXE_PATH.exists():
        print(f"exe를 찾지 못했습니다: {EXE_PATH}")
        return 1

    write_portable_files(APP_DIR)
    make_zip(APP_DIR, ZIP_PATH)
    print(f"portable_dir: {APP_DIR}")
    print(f"portable_zip: {ZIP_PATH}")
    print(f"zip_size_mb: {ZIP_PATH.stat().st_size / 1024 / 1024:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
