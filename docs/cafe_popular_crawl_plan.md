# 네이버 카페 인기글 2페이지 수집 계획

## 대상

사용자가 지정한 10개 네이버 카페의 `/popular` 인기글 목록을 수집한다.

- `https://cafe.naver.com/f-e/cafes/14793916/popular`
- `https://cafe.naver.com/f-e/cafes/10912875/popular`
- `https://cafe.naver.com/f-e/cafes/29434212/popular`
- `https://cafe.naver.com/f-e/cafes/10094499/popular`
- `https://cafe.naver.com/f-e/cafes/12182370/popular`
- `https://cafe.naver.com/f-e/cafes/23593632/popular`
- `https://cafe.naver.com/f-e/cafes/20655292/popular`
- `https://cafe.naver.com/f-e/cafes/10050813/popular`
- `https://cafe.naver.com/f-e/cafes/23451561/popular`
- `https://cafe.naver.com/f-e/cafes/22897837/popular`

## 구현 방식

1. `f-e` 공개 URL에서 `cafe_id`를 추출한다.
2. Selenium은 iframe wrapper보다 안정적인 내부 URL로 이동한다.
   - 입력: `https://cafe.naver.com/f-e/cafes/{cafe_id}/popular`
   - 렌더링 URL: `https://cafe.naver.com/ca-fe/cafes/{cafe_id}/popular`
3. 인기글 테이블 `.ArticleBoard tbody tr`에서 목록을 추출한다.
4. 페이지당 20개를 기준으로 현재 페이지를 저장한다.
5. 페이지네이션 버튼이 있으면 2페이지까지 클릭해서 추가 수집한다.
6. 결과를 CSV/JSON으로 저장한다.

## 수집 필드

- `cafe_id`
- `page`
- `rank_on_page`
- `global_rank`
- `article_id`
- `title`
- `url`
- `author`
- `written_at`
- `view_count`
- `comment_count`

## 실행 명령

기본 10개 카페, 2페이지 수집:

```bash
uv run python -m navercafe_app.cli.popular_crawl --pages 2 --output output/popular
```

로컬 URL 파일을 지정해서 수집:

```bash
uv run python -m navercafe_app.cli.popular_crawl \
  --urls config/cafe_popular_targets.txt \
  --pages 2 \
  --output output/popular
```

디버깅이 필요하면 브라우저를 보이게 실행:

```bash
uv run python -m navercafe_app.cli.popular_crawl --pages 2 --headed
```

## 2페이지 정리 운영 계획

1. **1차: 목록 수집**
   - 10개 카페 × 최대 2페이지 × 페이지당 20개 = 최대 400개 목록 수집.
   - 카페별 실제 페이지 수가 1페이지뿐이면 20개 내외에서 종료한다.
2. **2차: 공개 게시글 본문 확인**
   - 목록 CSV의 `url`을 기존 `ArticleCrawler`로 순회한다.
   - 비회원 공개글은 본문/이미지/댓글까지 저장한다.
   - 멤버공개/권한제한 글은 `detail_unavailable` 상태로 분류한다.
3. **3차: 요약/분류**
   - 제목 기준으로 주제 태그를 부여한다.
   - 댓글 수/조회 수 기준 상위글을 우선 정리한다.
   - 본문이 열리는 글은 본문 핵심 요약과 댓글 반응을 별도 컬럼으로 추가한다.
4. **4차: 일일 자동화**
   - 현재 목록 수집 코드를 검증한 뒤 기존 daily crawler의 로그인 세션/SQLite 저장 구조와 합친다.
   - 비회원 공개 인기글은 로그인 없이 수집, 멤버공개 게시글 상세만 로그인 세션으로 재시도한다.

## 주의점

- `/popular`는 일반 게시판 `menu_id` 기반 목록이 아니다.
- 네이버가 인기글 API/DOM을 바꾸면 Selenium selector 보강이 필요하다.
- 인기글 목록은 조회 가능해도 게시글 본문은 카페별 공개 설정에 따라 멤버공개일 수 있다.
- 너무 잦은 수집을 피하기 위해 카페 사이 지연과 일일 스케줄을 둔다.
