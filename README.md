
# Naver Cafe Strategy Tool

네이버 카페 운영전략 수립을 위해 업로드된 파이썬 코드들을 재사용 가능한 구조로 정리한 저장소입니다.

## 주요 분류

- `src/naver_cafe_strategy/browser/`: Selenium Chrome WebDriver 생성
- `src/naver_cafe_strategy/google/`: Google Sheets 연동
- `src/naver_cafe_strategy/naver/`: 검색량, 검색노출, 검색결과 타입, 카페 게시글 조회수 분석
- `src/naver_cafe_strategy/cafe/`: 카페 정보, 회원 검색, 등급 변경 API
- `src/naver_cafe_strategy/auth/`: 네이버 로그인
- `src/naver_cafe_strategy/io/`: CSV/TXT 작업 파일과 작업 로그
- `apps/`: GUI 통합본
- `legacy/`: 기존 EXE 빌드/크롤러 GUI 코드 보관
- `current_use/`: 이번 네이버 카페 운영전략 프로젝트에 우선 사용할 코드만 별도 분류

## 이번 프로젝트 우선 사용 범위

우선은 게시글/댓글 반응 분석과 이벤트 기획에 직접 필요한 코드 위주로 사용합니다.

1. 카페 게시글 제목/조회수 수집
2. 네이버 검색 노출 여부 확인
3. 키워드 검색량 조회
4. 검색결과 타입/구좌 분석
5. Google Sheets 기반 히스토리 관리
6. 기존 게시글 크롤러 GUI/빌드 코드는 참고용으로 유지

회원 등급 변경 모듈은 실제 회원 상태를 바꾸는 관리자 기능이므로 `dry-run`, 최종 확인, 변경 전/후 로그를 추가하기 전에는 자동 실행하지 않는 것을 권장합니다.

## 보안

GitHub 업로드 전 다음을 제외/치환했습니다.

- 네이버 검색광고 API Key/Secret 하드코딩 값
- 로컬 설정 파일, 쿠키, 토큰, Google credentials, 수집 결과물은 `.gitignore` 처리

실제 운영 인증정보는 `.env` 또는 `config.local.json`에 저장하고 GitHub에 올리지 마세요.

## 설치

```bash
uv venv
uv pip install -e .
```

또는 일반 Python 환경에서:

```bash
python -m pip install -e .
```

## 필요한 외부 설정

- Chrome 브라우저
- 네이버 관리자 또는 스탭 권한 계정
- Google Sheets API 서비스 계정 JSON 파일
- 네이버 검색광고 API 인증정보
