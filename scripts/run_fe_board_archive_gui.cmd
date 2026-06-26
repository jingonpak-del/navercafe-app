@echo off
setlocal
cd /d "%~dp0.."

if exist "dist\fe_board_archive\NaverCafeBoardArchive\NaverCafeBoardArchive.exe" (
  start "" "dist\fe_board_archive\NaverCafeBoardArchive\NaverCafeBoardArchive.exe"
  exit /b 0
)

where uv >nul 2>nul
if errorlevel 1 (
  echo uv가 설치되어 있지 않고 빌드된 exe도 없습니다.
  echo 먼저 개발 PC에서 다음 명령으로 exe를 빌드하세요:
  echo uv run --with pyinstaller python scripts/build_fe_board_archive_exe.py --clean
  pause
  exit /b 1
)

uv run python scripts/run_fe_board_archive_gui.py
pause
