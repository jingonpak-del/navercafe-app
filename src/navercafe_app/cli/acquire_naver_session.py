from __future__ import annotations

import argparse
from pathlib import Path

from navercafe_app.auth.naver_session import NaverSessionManager


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Open a visible browser, log in to Naver, and persist cookies.")
    parser.add_argument("--env", default=".env", help="Path to .env containing NAVER_ID/NAVER_PW/NAVER_SESSION_KEY")
    parser.add_argument("--driver", default=None, help="selenium or undetected. Overrides NAVER_LOGIN_DRIVER.")
    parser.add_argument("--input-method", default=None, help="auto, clipboard, or send_keys. Overrides NAVER_LOGIN_INPUT_METHOD.")
    parser.add_argument("--profile-dir", default=None, help="Persistent Chrome profile directory for manual login renewal.")
    parser.add_argument(
        "--warmup-url",
        action="append",
        default=[],
        help="Cafe URL to visit after login before saving cookies. Can be repeated.",
    )
    parser.add_argument("--force", action="store_true", help="Force browser login even if stored cookies validate.")
    args = parser.parse_args(argv)

    manager = NaverSessionManager(env_path=args.env)
    if args.driver:
        manager.login_driver_mode = args.driver
    if args.input_method:
        manager.login_input_method = args.input_method
    if args.profile_dir:
        manager.login_profile_dir = args.profile_dir
    if args.warmup_url:
        manager.login_warmup_urls = args.warmup_url

    print("Naver session acquisition starting.")
    print(f"- env: {Path(args.env).resolve()}")
    print(f"- driver: {manager.login_driver_mode}")
    print(f"- input_method: {manager.login_input_method}")
    print(f"- profile_dir: {manager.login_profile_dir}")
    if manager.login_warmup_urls:
        print("- warmup_urls:")
        for url in manager.login_warmup_urls:
            print(f"  - {url}")
    print("Visible Chrome will open. Complete CAPTCHA/2FA manually if Naver asks.")

    state = manager.ensure_login(force_login=args.force, headless=False)
    print(f"result: logged_in={state.logged_in} source={state.source} message={state.message}")
    if state.logged_in:
        print(f"cookies_saved: {manager.session_store.path.resolve()}")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
