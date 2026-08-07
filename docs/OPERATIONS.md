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
- `reports/rfp_documents.html`
- `reports/rfp_documents.csv`

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

## 3. RFP / 과업지시서 / 제출서식 확인

공고별 첨부 문서를 따로 확인하려면 아래 파일을 엽니다.

- `reports/rfp_documents.html`: 브라우저에서 검색/필터링하는 문서 확인 화면
- `reports/rfp_documents.csv`: Excel에서 열 수 있는 문서 체크리스트

수동으로 다시 생성하려면:

```powershell
python -m rfp_tracker render-documents --db data\rfp_tracker.db --html reports\rfp_documents.html --csv reports\rfp_documents.csv
```

콘솔에서 빠르게 보려면:

```powershell
python -m rfp_tracker rfp-documents --db data\rfp_tracker.db --limit 50
```

문서 유형:

- `rfp`: 제안요청서/RFP
- `scope`: 과업지시서/Scope of Work
- `notice`: 입찰공고문
- `forms`: 제출서식/양식
- `pricing`: 가격/산출내역서
- `contract`: 계약서/약관
- `missing`: 공고는 있으나 문서 링크가 아직 수집되지 않음

`missing`은 오류가 아니라 운영상 확인이 필요한 신호입니다. 사이트가 로그인, JavaScript, 상세 페이지 권한, 또는 별도 파일 API를 요구할 수 있습니다.

## 4. Windows 작업 스케줄러 등록 방향

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

## 5. 실제 나라장터 API 연결

서비스키는 환경변수로만 설정합니다.

```powershell
$env:DATA_GO_KR_SERVICE_KEY="발급받은_서비스키"
```

그 다음 `configs/sources.example.json`에서 `g2b_service_bids`의 `enabled`를 `true`로 바꿉니다.

처음에는 기간을 짧게 테스트하세요.

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_tracker.ps1 -Days 3
```

## 6. 운영 주의사항

- 민간 사이트는 약관과 로그인 권한 확인 전 기본 비활성화 상태를 유지하세요.
- 첨부파일 대량 다운로드는 별도 승인 후 구현하는 것이 안전합니다.
- 공고 원문 데이터는 임의 수정하지 말고, 검토 판단은 `review_status`, `review_note`에 남기세요.
