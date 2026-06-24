# 네이버 카페 회원전용 게시판 일일 크롤링 아키텍처

작성일: 2026-06-24
대상 저장소: `C:/Users/USER/projects/navercafe-app`

## 1. 점검 결과 요약

현재 저장소에는 네이버 로그인, Selenium 브라우저 생성, 카페 게시판/게시글/댓글 파싱의 기초 모듈이 이미 분리되어 있다. 다만 “`.env`에 네이버 ID/PW를 넣고 → 자동 로그인 → 쿠키/세션 저장 → 매일 지정 카페/게시판의 신규 게시글과 댓글 수집”까지 이어지는 운영형 파이프라인은 아직 완성되어 있지 않다.

실행 점검:

```text
uv run pytest -q
22 passed in 1.94s
```

현재 브랜치/상태:

```text
repo: C:/Users/USER/projects/navercafe-app
branch: feature/naver-cafe-post-metrics...origin/feature/naver-cafe-post-metrics
modified: uv.lock
untracked: scripts/collect_comment_counts_from_file.py, scripts/collect_comment_counts_parallel.py, scripts/resume_comment_counts.py
```

## 2. 기존 코드 자산

### 2.1 로그인/브라우저

- `src/naver_cafe_strategy/auth/naver_login.py`
  - Selenium으로 `https://nid.naver.com/nidlogin.login` 접속 후 ID/PW 입력.
  - CAPTCHA 감지 시 수동 처리 대기.
  - 로그인 성공 여부를 URL 변경으로 간단히 판단.
  - 현재 한계: `.env` 로딩 없음, 쿠키/세션 파일 저장 없음, CDP 기반 붙여넣기 입력 없음, 로그인 세션 재검증 로직이 약함.

- `src/naver_cafe_strategy/browser/webdriver.py`
- `src/navercafe_app/browser.py`
  - Selenium Manager 기반 ChromeDriver 자동 생성.
  - `--disable-blink-features=AutomationControlled`, 임시 `user-data-dir`, 이미지 비활성화, `page_load_strategy=eager` 설정.
  - `navercafe_app.browser.cafe_main_frame()`은 네이버 카페의 `#cafe_main` iframe 전환 헬퍼를 제공.
  - 현재 한계: 임시 프로필을 매번 새로 만들기 때문에 Chrome 프로필 기반 세션 지속성은 없음.

### 2.2 Selenium 쿠키 → requests.Session 변환

- `src/naver_cafe_strategy/cafe/member_search.py`
  - `get_session_from_driver(driver)` 함수가 `driver.get_cookies()`를 `requests.Session().cookies`로 이관.
  - `search_member()`는 로그인된 `requests.Session`을 전제로 카페 관리 API를 호출.
  - 현재 한계: 세션을 디스크에 저장/복원하는 계층은 없음. 쿠키 domain/path만 복사하므로 만료/검증/재로그인 흐름이 별도로 필요.

### 2.3 카페 정보/API

- `src/naver_cafe_strategy/cafe/cafe_info.py`
  - `CafeGateInfo.json`으로 `cluburl` → `cafeId` 조회.
  - `CafeMemberLevelInfo`로 등급 목록 조회.
  - `session` 선택 인자를 받으므로 로그인 세션 주입 가능.

### 2.4 게시판/게시글/댓글 크롤러

- `src/navercafe_app/crawlers/board.py`
  - `club_id`, `menu_id`, `page`로 classic `ArticleList.nhn` URL 생성 후 게시판 목록 파싱.

- `src/navercafe_app/crawlers/article.py`
  - 단일 게시글 URL 접속, `#cafe_main` 전환, 제목/본문/조회수/댓글수/이미지 URL 수집.

- `src/navercafe_app/crawlers/comments.py`
  - 게시글 페이지의 HTML에서 visible comment DOM 파싱.

- `src/navercafe_app/parsers.py`, `src/navercafe_app/models.py`
  - `Article`, `ArticleListItem`, `Comment` 모델과 HTML 파서.
  - 현재 한계: 게시판 목록 파서가 아직 기본형이고 `article_id`, `author`, `written_at` 추출이 충분하지 않음. 댓글은 보이는 DOM 기준이라 더보기/페이지네이션/비동기 댓글 API 대응이 필요.

## 3. 목표 아키텍처

```text
.env / targets.yaml
      │
      ▼
[Config Loader]
  - NAVER_ID, NAVER_PW
  - 대상 카페/게시판 목록
  - 수집 범위, 주기, 출력 위치
      │
      ▼
[Auth & Session Layer]
  - Selenium 자동 로그인
  - CAPTCHA/2FA 필요 시 수동 개입 지점
  - 쿠키 암호화 저장: data/session/naver_cookies.enc.json
  - requests.Session 복원
  - 로그인 상태 검증 및 만료 시 재로그인
      │
      ▼
[Target Resolver]
  - cafe slug/url → cafeId(clubid)
  - menuId/board URL 검증
  - 게시판 URL 형태 분류: classic ArticleList vs ca-fe SPA/API
      │
      ▼
[Collectors]
  1) BoardCollector
     - 지정 게시판의 최신 목록 수집
     - 마지막 수집 시점/마지막 article_id 이후 신규 글만 선별
  2) ArticleCollector
     - 제목, 본문, 작성자, 작성일, 조회수, 이미지
  3) CommentCollector
     - 댓글/대댓글, 작성자, 작성일, 본문
     - DOM 방식 + API 방식 병행
      │
      ▼
[Normalizer & Storage]
  - SQLite 권장: data/naver_cafe_daily.sqlite
  - tables: cafes, boards, articles, comments, crawl_runs
  - article_id + cafe_id unique key로 중복 방지
      │
      ▼
[Exporter]
  - CSV/JSON 백업
  - Google Sheets/Drive 선택 연동
  - Slack/Notion 요약 선택 연동
      │
      ▼
[Scheduler]
  - Windows 작업 스케줄러 또는 Hermes cronjob
  - 매일 1회 실행
  - 실패/로그인만료/캡챠 발생 시 Slack 알림
```

## 4. 추천 설정 파일 형태

### `.env`

```dotenv
NAVER_ID=your_id
NAVER_PW=your_password
NAVER_SESSION_KEY=로컬_암호화용_랜덤키_선택
GOOGLE_SERVICE_ACCOUNT_JSON=
GOOGLE_SHEET_URL=
```

주의: `.env`, 쿠키 파일, 원문 수집 DB는 GitHub에 커밋 금지.

### `config/cafe_targets.yaml`

```yaml
defaults:
  max_pages_per_board: 3
  include_comments: true
  include_images: false
  since_mode: last_seen_article_id
  delay_seconds:
    min: 2
    max: 5

targets:
  - name: 샘플카페
    cafe_url: https://cafe.naver.com/samplecafe
    cafe_slug: samplecafe
    cafe_id: "12345678"      # 비워두면 CafeGateInfo로 자동 조회
    boards:
      - name: 자유게시판
        menu_id: "12"
        board_url: https://cafe.naver.com/ArticleList.nhn?search.clubid=12345678&search.menuid=12
      - name: 가입인사
        menu_id: "34"
```

## 5. 핵심 모듈 설계

### 5.1 `navercafe_app.auth.session_store`

역할:
- 쿠키를 파일에 저장/복원.
- 쿠키 만료 시간을 기록.
- 가능하면 Windows DPAPI 또는 `cryptography.Fernet`으로 암호화.

주요 함수:

```python
class SessionStore:
    def load_cookies(self) -> list[dict]: ...
    def save_cookies(self, cookies: list[dict]) -> None: ...
    def is_available(self) -> bool: ...
```

### 5.2 `navercafe_app.auth.naver_session`

역할:
- `.env`에서 계정 로드.
- 기존 쿠키로 로그인 검증.
- 실패 시 Selenium 로그인 수행.
- Selenium 쿠키를 `requests.Session`으로 변환.

주요 함수:

```python
class NaverSessionManager:
    def get_driver(self, headless: bool = True): ...
    def get_requests_session(self) -> requests.Session: ...
    def ensure_login(self) -> AuthState: ...
    def validate_login(self, session: requests.Session) -> bool: ...
```

로그인 검증 후보:
- `https://www.naver.com/` 접속 후 로그인 영역 확인.
- `https://mail.naver.com/` 또는 카페 API 호출 후 로그인 오류 메시지 확인.
- 특정 대상 카페 게시판/글에 접근해서 권한 에러/로그인 에러 구분.

### 5.3 `navercafe_app.config.targets`

역할:
- `config/cafe_targets.yaml` 파싱.
- `cafe_url`, `cafe_slug`, `cafe_id`, `menu_id` 정규화.
- 잘못된 board 설정을 실행 전에 검증.

### 5.4 `navercafe_app.collectors.board_session`

역할:
- 로그인 세션이 필요한 게시판을 수집.
- 우선순위:
  1. 발견 가능한 API endpoint + `requests.Session`
  2. classic `ArticleList.nhn` + Selenium iframe 파싱
  3. SPA/iframe 페이지 + Selenium 렌더링 파싱

수집 필드:
- `cafe_id`, `menu_id`, `article_id`, `url`, `title`, `author`, `written_at`, `view_count`, `comment_count`, `is_notice`, `raw`.

### 5.5 `navercafe_app.collectors.article_session`

역할:
- 게시글 상세 본문/이미지/메타 수집.
- 회원전용 글은 Selenium driver에 쿠키 주입 후 접근.
- API가 있으면 requests API 우선.

### 5.6 `navercafe_app.collectors.comment_session`

역할:
- 댓글/대댓글 수집.
- 초기 구현은 기존 `parse_comments()` 재사용.
- 2차 구현에서 네이버 카페 댓글 API를 endpoint discovery 후 붙이는 방식 권장.

수집 필드:
- `comment_id`, `article_id`, `parent_comment_id`, `author`, `text`, `written_at`, `is_reply`, `raw`.

### 5.7 `navercafe_app.storage.sqlite_store`

권장 DB: `data/naver_cafe_daily.sqlite`

테이블:

```sql
cafes(cafe_id primary key, cafe_slug, cafe_url, name, created_at)
boards(id primary key, cafe_id, menu_id, name, board_url, unique(cafe_id, menu_id))
articles(id primary key, cafe_id, menu_id, article_id, url, title, author, written_at, body_text, view_count, comment_count, raw_json, first_seen_at, last_seen_at, unique(cafe_id, article_id))
comments(id primary key, cafe_id, article_id, comment_id, parent_comment_id, author, text, written_at, raw_json, first_seen_at, unique(cafe_id, article_id, comment_id))
crawl_runs(id primary key, started_at, finished_at, status, target_summary, error)
```

### 5.8 CLI/스케줄러

CLI 예시:

```bash
uv run python -m navercafe_app.cli.daily_crawl \
  --targets config/cafe_targets.yaml \
  --env .env \
  --db data/naver_cafe_daily.sqlite \
  --export output/daily \
  --headless
```

스케줄:
- 개발/테스트: 수동 CLI 실행.
- 운영: Hermes cronjob 또는 Windows 작업 스케줄러.
- CAPTCHA/2FA가 뜨면 headless 자동 실행은 실패 처리하고 Slack에 “수동 로그인 필요” 알림.

## 6. 구현 순서

1. **세션 계층 먼저 구현**
   - `.env` 로딩.
   - 쿠키 저장/복원.
   - 로그인 상태 검증.
   - 기존 `naver_login.py`의 단순 로그인 함수를 `NaverSessionManager`가 감싸도록 구성.

2. **대상 설정/검증 구현**
   - `config/cafe_targets.yaml` 스키마 정의.
   - `cafe_url → cafe_id` 자동 조회.
   - `menu_id`가 비었을 때는 board URL에서 추출하거나 오류 처리.

3. **게시판 목록 수집 고도화**
   - 기존 `BoardCrawler` 재사용.
   - `article_id`, 작성자, 작성일 추출 보강.
   - 마지막 수집 이후 신규 글만 선별.

4. **상세글/댓글 수집**
   - 기존 `ArticleCrawler`, `CommentCrawler` 재사용.
   - 댓글 더보기/페이지네이션 대응.
   - API endpoint는 실제 대상 게시판으로 discovery 후 추가.

5. **SQLite 저장/중복 방지**
   - `unique(cafe_id, article_id)`로 중복 저장 방지.
   - 같은 글을 다시 보면 조회수/댓글수/last_seen_at 업데이트.

6. **일일 실행 CLI + 리포트**
   - 신규 글 개수, 댓글 개수, 실패 게시판 목록 요약.
   - CSV/JSON export.
   - 필요 시 Google Sheets/Drive/Notion 연동.

7. **운영화**
   - Hermes cronjob 또는 Windows 작업 스케줄러 등록.
   - 실패 시 Slack 알림.
   - 로그/DB 백업.

## 7. 리스크와 운영 원칙

- 네이버 로그인은 CAPTCHA, 2FA, 새 기기 확인, 비정상 로그인 탐지에 걸릴 수 있다. 완전 무인 자동 로그인을 전제로 하기보다 “쿠키 재사용 + 만료 시 수동 갱신”을 기본 운영 모델로 잡는 것이 안정적이다.
- 회원전용 게시글/댓글에는 개인정보성 내용이 포함될 수 있으므로 수집 권한과 사용 목적을 명확히 해야 한다.
- 과도한 병렬 요청은 계정/카페 접근 제한 위험을 높인다. 게시판별 delay, 일일 횟수 제한, 실패 시 backoff가 필요하다.
- 로그인 ID/PW, 쿠키, 원문 DB는 GitHub에 커밋하지 않는다.
- 게시글 작성/댓글 작성/삭제/등급 변경 같은 mutation 기능과 이번 읽기 전용 크롤러는 분리한다.

## 8. 다음 작업의 최소 단위

MVP 기준으로는 아래 6개 파일/기능을 추가하면 된다.

```text
src/navercafe_app/auth/session_store.py
src/navercafe_app/auth/naver_session.py
src/navercafe_app/config/targets.py
src/navercafe_app/storage/sqlite_store.py
src/navercafe_app/cli/daily_crawl.py
config/cafe_targets.example.yaml
```

테스트:

```text
tests/test_session_store.py
tests/test_targets_config.py
tests/test_sqlite_store.py
tests/test_daily_crawl_pipeline.py
```

MVP 완료 조건:
- `.env`에 `NAVER_ID`, `NAVER_PW`를 넣으면 최초 1회 Selenium 로그인 시도.
- 로그인 성공 시 쿠키 저장.
- 다음 실행부터 쿠키 복원 후 로그인 검증.
- `config/cafe_targets.yaml`에 등록한 게시판의 신규 게시글 목록/상세/댓글을 SQLite와 CSV로 저장.
- 실패/권한없음/로그인만료를 명확히 구분해서 로그에 남김.
