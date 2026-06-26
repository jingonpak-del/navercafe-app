# Naver Cafe 게시판 아카이브 사용자 가이드

이 문서는 `NaverCafeBoardArchive.exe`를 다른 PC에서 실행하는 사용자를 위한 안내입니다.

## 빠른 시작

1. 개발 PC에서 포터블 패키지를 만듭니다.

   ```bash
   uv run --with pyinstaller python scripts/package_fe_board_archive_release.py --clean
   ```

2. 생성된 ZIP 파일을 사용할 PC로 옮깁니다.

   ```text
   dist/fe_board_archive/NaverCafeBoardArchive_portable.zip
   ```

3. ZIP을 풀고 아래 파일을 실행합니다.

   ```text
   NaverCafeBoardArchive.exe
   ```

4. 먼저 `목록만 테스트` 상태로 1~3개 글을 테스트합니다.

5. 본문/사진까지 저장하려면:
   - `목록만 테스트` 체크를 끕니다.
   - `로그인 갱신`을 누릅니다.
   - 열린 Chrome에서 네이버 로그인/CAPTCHA/2FA를 직접 완료합니다.
   - GUI의 로그인 상태가 유효하면 `수집 시작`을 누릅니다.

## 기본 대상 게시판

```text
https://cafe.naver.com/f-e/cafes/14793916/menus/1556?viewType=L
```

## 저장 구조

게시글별 폴더에 본문과 이미지를 보관합니다.

```text
output/naver_cafe_archive/줌슐랭_리스트_14793916_1556/
  board_manifest.json
  board_articles.jsonl
  failed_articles.jsonl
  {articleId}_{제목}/
    metadata.json
    body.html
    body.txt
    images_manifest.json
    images/
```

## 로그인/쿠키

- 로그인 쿠키는 `data/session/naver_cookies.json`에 저장됩니다.
- 이 파일은 네이버 로그인 세션과 연결될 수 있으므로 다른 사람에게 공유하지 마세요.
- CAPTCHA/2FA/보호조치는 자동 우회하지 않고 사용자가 직접 처리해야 합니다.

## 다른 PC에서 필요한 것

- Windows
- 인터넷 연결
- 대상 카페/게시판을 읽을 수 있는 네이버 계정

포터블 ZIP에는 Python 런타임, 필요한 라이브러리, Chrome for Testing, matching ChromeDriver가 함께 들어갑니다. 따라서 일반 사용자는 `uv`, Python, 일반 Chrome을 별도로 설치하지 않아도 됩니다.
