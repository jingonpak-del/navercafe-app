# 2026 댓글 마스터 프로그램 추출 기능 적용 노트

분석 대상: `C:\Users\USER\program lab\2026-06-18 네이버 카페 댓글 작성 프로그램 마스터 프로그램`

이 문서는 디컴파일 분석 결과 중 현재 `navercafe-app`에 안전하게 재사용 가능한 부분과 제외한 부분을 정리한다.

## 이번에 반영한 기능

### 1. 로그인/세션 안정화

반영 파일:

- `src/navercafe_app/auth/naver_login.py`
- `src/navercafe_app/auth/naver_session.py`
- `src/navercafe_app/auth/__init__.py`

변경 내용:

- 기존 `naver_cafe_strategy.auth.naver_login` 의존 대신 `navercafe_app.auth.safe_naver_login`을 기본 로그인 함수로 사용한다.
- 로그인 전/후 상태 판별을 `LoginStateDetector`로 분리했다.
- 디컴파일 프로그램에서 확인된 상태 셀렉터를 반영했다.
  - CAPTCHA: `#captchaimg`
  - 로그인 오류: `#err_common`
  - 보호조치/본인확인: `div.protection_content`, `ul.protection_list`, warning/action 영역
  - 휴면/추가 확인: `div.warning.warning_v2 ...`
- 저장 쿠키 검증은 단순 페이지 접근보다 안정적인 `https://mail.naver.com/json/initData` POST를 먼저 사용한다.
- CAPTCHA/보호조치/휴면 상태는 자동 우회하지 않고 사용자 수동 처리 대기 상태로만 처리한다.

### 2. 재사용 모듈화

반영 파일:

- `src/navercafe_app/reusable/comment_master.py`
- `src/navercafe_app/reusable/__init__.py`

포함 기능:

- `2. 작업 카페.txt` 유사 포맷 파서: 카페 URL/슬러그, 메뉴 ID, 추출 제한 수
- 카페 ID 조회 URL 빌더: `CafeGateInfo.json`
- 게시판 글 목록 API URL 빌더: `ArticleListV3.json`
- 댓글 원고 파일 로더: `$` 줄바꿈 마커 처리
- 게시글별 댓글 원고 우선 선택: `댓글원고/{cafeSlug}_{articleId}.txt` → 전역 원고 fallback
- `작업DB.txt` 스타일 append-only 중복 방지 DB
- 게시글 필터: 제목/작성자 포함·제외, 댓글 수 범위, 이미 처리한 URL 제외
- 게시판별 새글 탐지: `{카페}_{메뉴}` 기준 최신 작성 timestamp baseline 저장/비교

## 의도적으로 제외한 기능

다음 기능은 플랫폼 정책/계정 보안/운영 리스크가 높아 이번 코드에는 넣지 않았다.

- CAPTCHA 자동 풀이 또는 보호조치 우회
- 로그인 전 무작위 마우스 이동/스크롤 등 봇탐지 회피성 행동
- IP 변경/ADB 테더링/ALT+P 라우터 제어
- 자동 댓글 등록, 자동 좋아요, 조회 이벤트 생성
- 다계정 대량 작업 실행 로직

대신 현재 구현은 **로그인 상태 검증, 쿠키 재사용, 수동 챌린지 처리, 읽기/준비 단계 모듈화**에 집중했다.

## 다음 프로그램 제작 시 재사용 순서

1. `NaverSessionManager`로 저장 쿠키를 검증한다.
2. 만료된 경우 `safe_naver_login(..., headless=False)` 흐름으로 사용자 표시 브라우저에서 로그인한다.
3. 수집 대상은 `parse_cafe_board_targets()`로 로드한다.
4. 카페 ID는 `cafe_gate_info_url()`로 조회하고, 게시판 글 목록은 `article_list_v3_url()`로 가져온다.
5. `NewPostTracker`로 새글만 감지한다.
6. 댓글/이미지/작업 실행 전에는 `WorkDatabase`와 `filter_articles()`로 중복·조건 필터링을 먼저 수행한다.
