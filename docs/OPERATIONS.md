# Climate RFP Tracker 운영 가이드

## 1. 매일/매시간 실행

PowerShell에서 아래처럼 실행합니다.

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_tracker.ps1 -Days 14
```

결과물:

- `data/rfp_tracker.db`
- `reports/dashboard.html`
- `reports/notices.csv`

## 2. 공고 후보 검토

후보 목록 확인:

```powershell
python -m rfp_tracker list --db data\rfp_tracker.db --limit 20
```

상태 변경:

```powershell
python -m rfp_tracker review --db data\rfp_tracker.db --id 1 --status interesting --note "CDP/Scope 3 제안 가능성 높음"
```

사용 가능한 상태:

- `new`
- `watch`
- `interesting`
- `not_relevant`
- `submitted`
- `won`
- `lost`
- `closed`

상태별 요약:

```powershell
python -m rfp_tracker stats --db data\rfp_tracker.db
```

## 3. Windows 작업 스케줄러 등록 방향

처음에는 자동 등록보다 수동 등록을 권장합니다.

1. Windows “작업 스케줄러” 열기
2. 기본 작업 만들기
3. 트리거: 매일 또는 1시간마다
4. 동작: 프로그램 시작
5. 프로그램: `powershell.exe`
6. 인수:

```text
-ExecutionPolicy Bypass -File "B:\CODEX\RFP\scripts\run_tracker.ps1" -Days 14
```

## 4. 실제 나라장터 API 연결

서비스키는 환경변수로만 설정합니다.

```powershell
$env:DATA_GO_KR_SERVICE_KEY="발급받은_서비스키"
```

그 다음 `configs/sources.example.json`에서 `g2b_service_bids`의 `enabled`를 `true`로 바꿉니다.

처음에는 기간을 짧게 테스트하세요.

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_tracker.ps1 -Days 3
```

## 5. 운영 주의사항

- 민간 사이트는 약관과 로그인 권한 확인 전 기본 비활성화 상태를 유지하세요.
- 첨부파일 대량 다운로드는 별도 승인 후 구현하는 것이 안전합니다.
- 공고 원문 데이터는 임의 수정하지 말고, 검토 판단은 `review_status`, `review_note`에 남기세요.
