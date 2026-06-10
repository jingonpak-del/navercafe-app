# 네이버 카페 크롤링 코드 수집 카탈로그

## 사용자 소유/로컬 코드

| 출처 | 주요 기능 | 이번 저장소 반영 방식 |
|---|---|---|
| `C:/Users/USER/naver-cafe-strategy-tool/src/naver_cafe_strategy/browser/webdriver.py` | Selenium Chrome 드라이버 생성, 이미지 차단, headless 옵션 | `navercafe_app.browser.build_driver`로 일반화 |
| `.../naver/cafe_post_info.py` | `#cafe_main` iframe 전환 후 게시글 제목/조회수 추출 | `ArticleCrawler`, `parsers.extract_title`, `extract_view_count`로 분리 |
| `.../naver/exposure_check.py` | 네이버 검색 결과에서 카페글 노출 여부 확인 | 추후 `search/exposure.py` 후보 |
| `.../naver/search_volume.py` | 네이버 검색광고 API 검색량 조회 | 추후 `ads/search_volume.py` 후보, 인증정보는 `.env` 유지 |
| `.../google/sheets.py` | Google Sheets 히스토리 관리 | 추후 `integrations/google_sheets.py` 후보 |
| `.../cafe/cafe_info.py`, `member_search.py`, `grade_change.py` | 카페 ID/등급/회원/관리 API | 관리자 기능은 dry-run/로그 추가 후 별도 모듈화 권장 |

## 공개 GitHub 조사 결과

> 라이선스가 없거나 불명확한 공개 코드는 저장소에 그대로 복사하지 않았습니다. 기능 패턴만 분석해 신규 구현 모듈에 반영했습니다.

| 저장소 | 라이선스 | 확인한 기능 | 적용한 모듈/아이디어 |
|---|---:|---|---|
| `rsh1994/naver_cafe_crawl` | 없음 | 특정 게시판, 기간 필터, 공지 제외, 제목/본문/작성일/조회수, Excel 저장 | `BoardCrawler`, `ArticleCrawler`, 공지 제외 옵션 |
| `kisoo95/Naver-cafe-crawling-ver240115` | 없음 | 키워드 검색 기반 카페글 수집, 페이지 단위 수집 | 추후 `SearchCrawler` 후보, `clubid` 개념 문서화 |
| `ryanproback/naver-cafe-image-crawler` | 없음 | 게시글 이미지 URL 추출 및 다운로드 | `ImageCrawler`, `download_image` |
| `dev-jaemin/Naver-Cafe-Crawling` | 없음 | 댓글을 질문-답변 row로 DB 저장, PostgreSQL 사용 | `CommentCrawler`, 댓글 모델 분리 |
| `GBS-Skile/NaverCafeAttendanceCrawler` | MIT | 특정 회원의 게시글/댓글/출석 활동일 평가 | `attendance.parse_korean_date`, `evaluate_activity` 유틸리티 |
| `sirius-mhlee/naver-cafe-crawler` | 없음 | pandas/tqdm/Selenium/BS4 기반 게시글 수집 파이프라인 | 추후 배치 진행률/CSV 출력 후보 |

## 공통 구조 패턴

1. 네이버 카페 본문은 대부분 메인 문서 안의 `iframe#cafe_main` 내부에 있으므로 iframe 전환 헬퍼가 필수입니다.
2. 공개/비공개/회원등급 제한에 따라 결과가 달라지므로, 로그인 세션을 직접 주입하는 구조가 필요합니다.
3. 게시글 수집은 `게시판 목록 → 게시글 상세 → 댓글/이미지 부가 수집 → 저장소 출력` 파이프라인으로 나누는 것이 유지보수에 좋습니다.
4. 라이선스 불명확 저장소의 소스 복사는 피하고, API/HTML 선택자/흐름만 참고해 재구현합니다.
