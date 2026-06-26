@echo off
setlocal
cd /d "%~dp0.."

where uv >nul 2>nul
if errorlevel 1 (
  echo uv가 설치되어 있지 않습니다. https://docs.astral.sh/uv/ 를 참고해 설치한 뒤 다시 실행하세요.
  pause
  exit /b 1
)

uv run python -m navercafe_app.cli.acquire_naver_session ^
  --env .env ^
  --driver undetected ^
  --input-method auto ^
  --profile-dir data/chrome-profile/naver-login ^
  --warmup-url https://cafe.naver.com/f-e/cafes/14793916/menus/1556?viewType=L ^
  --force

if errorlevel 1 (
  echo.
  echo 로그인 쿠키 저장에 실패했습니다. 열린 Chrome에서 CAPTCHA/2FA를 완료했는지 확인하세요.
) else (
  echo.
  echo 로그인 쿠키 저장 완료. 이제 GUI에서 '본문/사진 저장'을 실행할 수 있습니다.
)
pause
