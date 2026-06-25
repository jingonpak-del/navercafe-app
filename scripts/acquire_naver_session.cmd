@echo off
setlocal
cd /d "%~dp0.."
echo Starting Naver session acquisition...
echo Complete Naver login, CAPTCHA, or 2FA in the Chrome window.
uv run python -m navercafe_app.cli.acquire_naver_session --env .env --driver undetected --input-method auto --profile-dir data/chrome-profile/naver-login --force
echo.
echo Finished. Press any key to close.
pause >nul
