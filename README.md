# navercafe-app

네이버 카페 크롤러/운영 자동화 코드를 기능별로 모듈화한 저장소입니다.

이 저장소는 기존 원격 저장소의 `naver_cafe_strategy` 운영전략 도구와, 이번에 추가한 `navercafe_app` 크롤러 공통 모듈을 함께 보관합니다.

## 현재 정리 범위

1. **사용자 기존 코드 통합**: `C:/Users/USER/naver-cafe-strategy-tool` 및 원격 저장소의 Selenium 드라이버, 카페 게시글 제목/조회수 수집, 검색노출/검색량/Google Sheets 연동 구조를 유지했습니다.
2. **공개 GitHub 코드 조사**: 네이버 카페 게시판/키워드/댓글/이미지/출석 크롤러 공개 저장소를 조사하고, 라이선스가 불명확한 코드는 직접 복사하지 않고 패턴과 기능만 `docs/source_catalog.md`에 정리했습니다.
3. **재사용 가능한 신규 모듈**: `src/navercafe_app/` 아래에 Selenium iframe 처리, URL 파싱, 게시글/게시판/댓글/이미지/출석 크롤링 골격을 분리했습니다.

## 주요 분류

### 신규 공통 크롤러 모듈

```text
src/navercafe_app/
  browser.py              # Chrome WebDriver 생성 및 iframe 컨텍스트 헬퍼
  cafe_urls.py            # clubid/menuid/articleid 등 URL 파싱/생성
  models.py               # Article, Comment, ImageAsset 등 데이터 모델
  parsers.py              # HTML/텍스트 파서: 제목, 조회수, 날짜, 댓글, 이미지
  crawlers/
    article.py            # 단일 게시글 수집
    board.py              # 게시판/검색 결과 목록 수집 골격
    comments.py           # 댓글 수집
    images.py             # 게시글 이미지 URL 추출/다운로드
    attendance.py         # 회원 활동일/출석 판정용 유틸리티
```

### 기존 운영전략 도구

- `src/naver_cafe_strategy/browser/`: Selenium Chrome WebDriver 생성
- `src/naver_cafe_strategy/google/`: Google Sheets 연동
- `src/naver_cafe_strategy/naver/`: 검색량, 검색노출, 검색결과 타입, 카페 게시글 조회수 분석
- `src/naver_cafe_strategy/cafe/`: 카페 정보, 회원 검색, 등급 변경 API
- `src/naver_cafe_strategy/auth/`: 네이버 로그인
- `src/naver_cafe_strategy/io/`: CSV/TXT 작업 파일과 작업 로그
- `apps/`: GUI 통합본
- `legacy/`: 기존 EXE 빌드/크롤러 GUI 코드 보관
- `current_use/`: 네이버 카페 운영전략 프로젝트에 우선 사용할 코드만 별도 분류

## 이번 프로젝트 우선 사용 범위

1. 카페 게시글 제목/조회수 수집
2. 게시판 목록/댓글/이미지 크롤러 모듈화
3. 회원 활동일/출석 판정 유틸리티
4. 네이버 검색 노출 여부 확인
5. 키워드 검색량 조회
6. 검색결과 타입/구좌 분석
7. Google Sheets 기반 히스토리 관리

회원 등급 변경 모듈은 실제 회원 상태를 바꾸는 관리자 기능이므로 `dry-run`, 최종 확인, 변경 전/후 로그를 추가하기 전에는 자동 실행하지 않는 것을 권장합니다.

## 설치

```bash
uv venv
uv pip install -e .
# 개발/테스트까지
uv pip install -e ".[dev,excel]"
```

또는 일반 Python 환경에서:

```bash
python -m pip install -e .
```

## 기본 예시

### 단일 게시글 수집

```python
from navercafe_app.browser import build_driver
from navercafe_app.crawlers.article import ArticleCrawler

driver = build_driver(headless=False)  # 로그인 필요 카페는 수동 로그인 후 진행
try:
    article = ArticleCrawler(driver).crawl("https://cafe.naver.com/somecafe/123456")
    print(article.title, article.view_count)
finally:
    driver.quit()
```

### 회원전용 게시판 일일 크롤링 MVP

1. `config/.env.example`을 참고해 로컬 `.env`를 만듭니다.

```dotenv
NAVER_ID=your_naver_id
NAVER_PW=your_naver_password
NAVER_SESSION_KEY=local_random_key
# 선택: 기존 hotdeal crawler에서 검증한 로그인 안정화 옵션
NAVER_LOGIN_DRIVER=selenium          # selenium 또는 undetected
NAVER_LOGIN_INPUT_METHOD=auto        # auto, clipboard, send_keys
NAVER_KEEP_LOGIN=true
NAVER_USE_CURL_CFFI=true
NAVER_LOGIN_PROFILE_DIR=data/chrome-profile/naver-login
NAVER_LOGIN_WARMUP_URLS=https://cafe.naver.com/f-e/cafes/14793916/popular
```

2. `config/cafe_targets.example.yaml`을 복사해 `config/cafe_targets.yaml`을 만들고 카페/게시판을 등록합니다.
   - 일반 게시판은 `menu_id`를 입력합니다.
   - 인기글 영역(`/f-e/cafes/{cafe_id}/popular`)은 `menu_id`가 없으므로 `type: popular`, `menu_id: ""`, `board_url: https://cafe.naver.com/f-e/cafes/{cafe_id}/popular` 형식으로 등록합니다.

3. 최초 쿠키 획득은 CAPTCHA/2FA 대응을 위해 브라우저를 보이게 실행하는 것을 권장합니다. Slack 안에서 네이버 보안 챌린지를 직접 조작하기 어렵다면 Hermes가 설치된 Windows PC에 원격데스크톱/크롬 원격 데스크톱/AnyDesk 등으로 접속한 뒤 아래 명령으로 열린 Chrome 창에서 직접 로그인하세요.

```bash
uv run python -m navercafe_app.cli.acquire_naver_session \
  --env .env \
  --driver selenium \
  --input-method auto \
  --profile-dir data/chrome-profile/naver-login \
  --warmup-url https://cafe.naver.com/f-e/cafes/14793916/popular \
  --force
```

`NAVER_LOGIN_DRIVER=undetected`를 쓰려면 선택 의존성을 설치합니다.

```bash
uv pip install undetected-chromedriver pyperclip curl-cffi
```

4. 쿠키가 저장된 뒤 일일 크롤러를 실행합니다.

```bash
uv run python -m navercafe_app.cli.daily_crawl \
  --targets config/cafe_targets.yaml \
  --env .env \
  --db data/naver_cafe_daily.sqlite \
  --export output/daily \
  --headed
```

로그인 성공 후 쿠키는 `data/session/naver_cookies.json`에 저장되며, 이후 실행에서는 저장 쿠키로 로그인 상태를 먼저 검증합니다. 세션이 만료되거나 CAPTCHA/2FA가 발생하면 `--headed --force-login`으로 수동 갱신하세요.

## 보안/운영 원칙

- 네이버 약관, robots 정책, 카페 운영 정책을 준수하세요.
- 로그인 쿠키/ID/PW/API 키는 `.env` 또는 `config.local.json`에만 두고 GitHub에 커밋하지 마세요.
- Google credentials, 네이버 검색광고 API Key/Secret, 수집 결과물은 `.gitignore`로 제외합니다.
- 비공개 카페/개인정보/회원정보 수집은 권한과 목적을 먼저 확인하세요.
