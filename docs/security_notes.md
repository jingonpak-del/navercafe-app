
# 보안 메모

## GitHub에 올리지 않을 파일

- `.env`
- `config.local.json`
- `settings.json`
- `config.json`
- `naver_cookies.json`
- `credentials.json`
- `token.json`
- `token_monitor.json`
- `monitor_db.json`
- 서비스 계정 JSON 키 파일
- 회원 목록 CSV/TXT
- 작업 결과 CSV/TSV/XLSX

## 회원 등급 변경 모듈 주의

`grade_change.py`는 실제 회원 등급을 바꾸는 관리자 API를 호출합니다.
자동 실행 전에 반드시 다음 안전장치를 추가하세요.

- dry-run 모드
- 실행 전 대상 요약
- 운영자 최종 확인
- 변경 전/후 등급 기록
- 실패 건 재처리 CSV 분리
- 요청 간 딜레이 및 일일 처리량 제한
