from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENTRY_SCRIPT = PROJECT_ROOT / "scripts" / "run_fe_board_archive_gui.py"
DIST_DIR = PROJECT_ROOT / "dist" / "fe_board_archive"
BUILD_DIR = PROJECT_ROOT / "build" / "fe_board_archive"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the Naver Cafe board archive GUI as a Windows executable.")
    parser.add_argument("--clean", action="store_true", help="Remove previous build/dist output before packaging.")
    parser.add_argument("--name", default="NaverCafeBoardArchive", help="Executable base name.")
    args = parser.parse_args(argv)

    if args.clean:
        shutil.rmtree(DIST_DIR, ignore_errors=True)
        shutil.rmtree(BUILD_DIR, ignore_errors=True)

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--windowed",
        "--name",
        args.name,
        "--distpath",
        str(DIST_DIR),
        "--workpath",
        str(BUILD_DIR),
        "--paths",
        str(PROJECT_ROOT / "src"),
        str(ENTRY_SCRIPT),
    ]
    print("Running:", " ".join(cmd))
    try:
        subprocess.run(cmd, cwd=PROJECT_ROOT, check=True)
    except ModuleNotFoundError:
        print("PyInstaller가 설치되어 있지 않습니다. 예: uv run --with pyinstaller python scripts/build_fe_board_archive_exe.py")
        return 2
    except subprocess.CalledProcessError as exc:
        print(f"빌드 실패: exit={exc.returncode}")
        return exc.returncode

    exe = DIST_DIR / args.name / f"{args.name}.exe"
    print(f"빌드 완료: {exe}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
