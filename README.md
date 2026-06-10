# navercafe-app

네이버 카페 크롤러/운영 자동화 코드를 기능별로 모듈화한 저장소입니다.

## 현재 정리 범위

1. **사용자 기존 코드 통합**: `C:/Users/USER/naver-cafe-strategy-tool`의 Selenium 드라이버, 카페 게시글 제목/조회수 수집, 검색노출/검색량/Google Sheets 연동 구조를 기준으로 모듈화했습니다.
2. **공개 GitHub 코드 조사**: 네이버 카페 게시판/키워드/댓글/이미지/출석 크롤러 공개 저장소를 조사하고, 라이선스가 불명확한 코드는 직접 복사하지 않고 패턴과 기능만 `docs/source_catalog.md`에 정리했습니다.
3. **재사용 가능한 신규 모듈**: `src/navercafe_app/` 아래에 Selenium iframe 처리, URL 파싱, 게시글/게시판/댓글/이미지/출석 크롤링 골격을 분리했습니다.

## 디렉터리

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
docs/
  source_catalog.md       # 사용자 코드 + 공개 GitHub 조사 결과
  module_inventory.md     # 기능별 모듈 설명
  legal_notes.md          # 라이선스/운영 주의사항
examples/
  crawl_article.py        # 단일 게시글 수집 예시
```

## 설치

```bash
uv venv
uv pip install -e .
# 개발/테스트까지
uv pip install -e ".[dev,excel]"
```

## 기본 예시

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

## 운영 원칙

- 네이버 약관, robots 정책, 카페 운영 정책을 준수하세요.
- 로그인 쿠키/ID/PW/API 키는 `.env` 또는 `config.local.json`에만 두고 GitHub에 커밋하지 마세요.
- 비공개 카페/개인정보/회원정보 수집은 권한과 목적을 먼저 확인하세요.
