
# 모듈 인벤토리

## 운영전략/분석에 우선 사용할 모듈

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
