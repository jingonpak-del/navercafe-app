# 모듈 인벤토리

## 신규 공통 크롤러 모듈 (`navercafe_app`)

| 기능 | 모듈 | 설명 | 상태 |
|---|---|---|---|
| 브라우저 생성 | `navercafe_app.browser` | Chrome WebDriver 생성, `#cafe_main` iframe 컨텍스트 관리 | 구현 |
| URL 파싱/생성 | `navercafe_app.cafe_urls` | 카페 slug, clubId, menuId, articleId 파싱 및 게시판 URL 생성 | 구현 |
| 공통 데이터 모델 | `navercafe_app.models` | 게시글, 목록 항목, 댓글, 이미지, 출석 결과 dataclass | 구현 |
| HTML 파서 | `navercafe_app.parsers` | 제목/조회수/본문/댓글/이미지/목록 파싱 | 구현 + 단위 테스트 |
| 단일 게시글 크롤링 | `navercafe_app.crawlers.article.ArticleCrawler` | URL 접속, iframe 처리, 제목/본문/조회수/이미지 추출 | 구현 |
| 게시판 목록 크롤링 | `navercafe_app.crawlers.board.BoardCrawler` | clubId/menuId/page 기반 목록 수집, 공지 제외 | 1차 구현 |
| 댓글 크롤링 | `navercafe_app.crawlers.comments.CommentCrawler` | 현재 페이지에 노출된 댓글 파싱 | 1차 구현 |
| 이미지 크롤링 | `navercafe_app.crawlers.images.ImageCrawler` | 이미지 URL 추출 및 다운로드 함수 | 구현 |
| 출석/활동일 판정 | `navercafe_app.crawlers.attendance` | 날짜 문자열 파싱과 기간 내 활동일 평가 | 유틸 구현 |
| 검색노출 확인 | 예정: `navercafe_app.search.exposure` | 기존 로컬 코드 기반으로 검색 결과 내 카페글 노출 확인 | TODO |
| 검색량 조회 | 예정: `navercafe_app.ads.search_volume` | 네이버 검색광고 API 연동 | TODO |
| Google Sheets | 예정: `navercafe_app.integrations.google_sheets` | 수집 결과/히스토리 저장 | TODO |
| 관리자 기능 | 예정: `navercafe_app.admin.*` | 회원 검색/등급 변경. 반드시 dry-run과 변경 로그 필요 | 보류 |

## 기존 운영전략/분석에 우선 사용할 모듈

| 경로 | 용도 |
|---|---|
| `current_use/browser/webdriver.py` | Selenium 드라이버 생성 |
| `current_use/google/sheets.py` | Google Sheets 읽기/쓰기 및 히스토리 열 관리 |
| `current_use/naver/cafe_post_info.py` | 네이버 카페 게시글 제목/조회수 추출 |
| `current_use/naver/exposure_check.py` | 특정 카페글의 네이버 검색 노출 여부 확인 |
| `current_use/naver/search_volume.py` | 네이버 검색광고 API 검색량 조회 |
| `current_use/naver/naver_type.py` | 네이버 검색결과 A/B 타입 판별 |
| `current_use/naver/result_types.py` | 검색결과 카페/블로그/지식iN/외부사이트 구좌 카운트 |
| `current_use/cafe/cafe_info.py` | 카페 URL에서 cafeId 조회 및 등급 목록 조회 |
| `current_use/legacy_crawler_gui/메인프로그램.py` | 기존 게시글 크롤러 GUI 참고용 |

## 보관/추후 활용 모듈

- `src/naver_cafe_strategy/cafe/member_search.py`: 회원 검색
- `src/naver_cafe_strategy/cafe/grade_change.py`: 회원 등급 변경 API
- `src/naver_cafe_strategy/io/load_member_tasks.py`: 회원 작업 CSV/TXT 파서
- `src/naver_cafe_strategy/io/work_log.py`: 작업 결과 CSV 로깅
- `apps/cafe_marketing_gui.py`: 검색노출/조회수/검색량 GUI 통합본
- `legacy/build_scripts/`: 기존 Windows EXE 빌드 스크립트
