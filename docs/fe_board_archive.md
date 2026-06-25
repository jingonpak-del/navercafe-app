# Naver Cafe f-e 게시판 아카이브

현대형 Naver Cafe URL(`/f-e/cafes/{cafeId}/menus/{menuId}`)의 게시글 목록을 API로 수집하고, 로그인 세션이 있을 때 각 게시글 본문과 첨부/본문 이미지를 게시글별 폴더에 저장하는 기능입니다.

## 대상 예시

```text
https://cafe.naver.com/f-e/cafes/14793916/menus/1556?viewType=L
```

## CLI 실행

### 1) 목록만 테스트

로그인이 없어도 동작합니다.

```bash
uv run python -m navercafe_app.crawlers.fe_board_archive \
  --url "https://cafe.naver.com/f-e/cafes/14793916/menus/1556?viewType=L" \
  --board-name "줌슐랭_리스트" \
  --output output/naver_cafe_archive \
  --list-only \
  --limit 3
```

저장 결과:

```text
output/naver_cafe_archive/줌슐랭_리스트_14793916_1556/
  board_manifest.json
  board_articles.jsonl
```

### 2) 본문/사진까지 저장

본문 상세 API는 로그인과 카페 읽기 권한이 필요합니다. `.env`에 `NAVER_ID`, `NAVER_PW`가 있으면 기존 `NaverSessionManager`가 저장 쿠키를 확인하고, 필요 시 Selenium 로그인을 수행합니다.

```bash
uv run python -m navercafe_app.crawlers.fe_board_archive \
  --url "https://cafe.naver.com/f-e/cafes/14793916/menus/1556?viewType=L" \
  --board-name "줌슐랭_리스트" \
  --output output/naver_cafe_archive \
  --limit 3 \
  --delay 1.0
```

CAPTCHA/2FA가 나오면 `--headless` 없이 실행해 열린 브라우저에서 직접 인증한 뒤 쿠키를 저장하는 방식을 권장합니다.

## PC 프로그램형 GUI MVP

```bash
uv run python scripts/run_fe_board_archive_gui.py
```

GUI에서 가능한 일:

- 게시판 URL 입력
- 저장 폴더 선택
- 시작/끝 페이지, 최대 글 수 제한
- 목록만 테스트
- 본문/사진 저장 실행
- 로그인 상태 확인
- 로그인 쿠키 삭제/강제 갱신
- 요청 간격 설정
- 실행 결과 표 확인
- 자주 쓰는 게시판 프리셋 저장/불러오기

프리셋은 기본적으로 `data/fe_board_archive_presets.json`에 저장됩니다. 로그인 쿠키는 기존 세션 관리 계층을 통해 `data/session/naver_cookies.json`에 저장되며 git에 커밋하면 안 됩니다.

## Windows exe 패키징

개발 PC에서 PyInstaller로 GUI 실행 파일을 만들 수 있습니다.

```bash
uv run --with pyinstaller python scripts/build_fe_board_archive_exe.py --clean
```

빌드 결과 예시:

```text
dist/fe_board_archive/NaverCafeBoardArchive/NaverCafeBoardArchive.exe
```

배포 시에는 위 폴더 전체를 압축해서 다른 PC로 옮기는 방식이 안전합니다. 다른 PC에도 Chrome이 설치되어 있어야 하며, 첫 실행 시 네이버 로그인/CAPTCHA/2FA는 사용자가 직접 완료해야 합니다.

## 저장 구조

```text
{output}/{board_name}_{cafeId}_{menuId}/
  board_manifest.json
  board_articles.jsonl
  failed_articles.jsonl
  {articleId}_{sanitized_title}/
    metadata.json
    body.html
    body.txt
    images_manifest.json
    images/
      001_xxx.jpg
```

## 알려진 접근 조건

- 게시글 목록 API는 비로그인으로 접근되는 경우가 많습니다.
- 게시글 상세 본문 API는 비로그인 상태에서 `0004 로그인하지 않았습니다`를 반환합니다.
- 계정이 해당 카페/게시판의 글 읽기 권한을 가져야 본문/사진 수집이 가능합니다.
- 네이버/카페 정책과 개인정보/저작권을 준수해 내부 보관 목적으로 사용하세요.
