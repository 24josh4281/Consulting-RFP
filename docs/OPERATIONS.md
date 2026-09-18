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
- `reports/briefing.html`
- `reports/briefing.md`

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

## 4. 신규 공고 메일, 매일 17:00, 주간 브리핑

수신자와 SMTP 정보가 없으면 메일은 보내지지 않습니다. 먼저 수신자를 로컬 설정에 저장하고, `.env`를 준비합니다.

```powershell
python -m rfp_tracker notifications setup --recipient "sejinkim@inng.co.kr"
Copy-Item .env.example .env
notepad .env
python -m rfp_tracker notifications status --db data\rfp_tracker_official.db --config configs\notifications.local.json
```

준비 상태에서 `smtp=MISSING`이 보이면 아래 값 중 누락된 것을 `.env`에 채워야 합니다.

- `SMTP_HOST`
- `SMTP_PORT` (일반적으로 `587`)
- `SMTP_USERNAME`
- `SMTP_PASSWORD` (가능하면 앱 비밀번호)
- `SMTP_FROM`

실제 수신 전에 테스트 메일을 한 번만 보냅니다.

```powershell
python -m rfp_tracker notifications dispatch --mode test --db data\rfp_tracker_official.db --config configs\notifications.local.json --send
```

테스트가 성공하면 알림 실행 스크립트를 먼저 미리보기로 확인합니다.

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_notification_cycle.ps1 -Mode immediate
```

`-Send`를 넣어야 실제 메일을 보냅니다. 이 스크립트는 수집, RFP 문서목록, 브리핑 생성, 메일 발송을 순서대로 실행합니다.

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_notification_cycle.ps1 -Mode immediate -Send
```

SMTP 테스트 후 다음 명령으로 Windows 작업 스케줄러를 등록할 수 있습니다.

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install_notification_tasks.ps1 -Send
```

기본 일정은 다음과 같습니다.

| 목적 | 일정 | 실제 메일 조건 |
|------|------|----------------|
| 신규 공고 | 30분마다 | 새로 수집된 관련 공고가 있을 때만 |
| 일일 브리핑 | 매일 17:00 KST | 당일 집계가 아직 전송되지 않았을 때 |
| 주간 브리핑 | 매주 금요일 18:00 KST | 해당 주 집계가 아직 전송되지 않았을 때 |

첫 실행은 기준시각만 저장하므로 기존 공고를 신규 공고처럼 대량 발송하지 않습니다. "즉시"는 웹훅이 아닌 30분 폴링 기준입니다.

공식 상세 수집용 기본 DB는 `data/rfp_tracker_official.db`입니다. 이전 범용 수집 결과가 남은 `data/rfp_tracker_live.db`는 보존되며, 두 결과를 섞지 않습니다.

## 5. 실제 나라장터 API 연결

서비스키는 환경변수로만 설정합니다.

```powershell
$env:DATA_GO_KR_SERVICE_KEY="발급받은_서비스키"
```

또는 `.env.example`을 `.env`로 복사한 뒤 `.env` 안에 키를 넣어도 됩니다. `.env`는 git에 올라가지 않습니다.

```powershell
Copy-Item .env.example .env
notepad .env
```

그 다음 원본 예시 파일을 직접 바꾸지 말고 로컬 설정 파일을 생성합니다.

```powershell
python -m rfp_tracker source-toggle --source-id g2b_service_bids --enable --out configs\sources.local.json
```

실시간 실행 준비 상태를 확인합니다.

```powershell
python -m rfp_tracker doctor --config configs\sources.local.json
```

처음에는 기간을 짧게 테스트하세요.

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_live_g2b_check.ps1 -Days 3
```

## 6. 공식 출처 상태 확인

```powershell
python -m rfp_tracker sources --config configs\sources.local.json
```

- GIR 공개 입찰 게시판은 현재 상세 공고와 공개 RFP/과업 문서 링크 연결까지 확인되었습니다.
- 나라장터는 서비스키가 있어야 API 수집을 시작합니다. 활성화 시 용역 공고를 환경·기후·온실가스·배출권·ETS·LCA·탄소발자국·환경영향평가 기준으로 필터링합니다.
- 환경부 및 민간 포털은 이용 정책과 페이지 구조 검토 전까지 비활성화로 둡니다.
- 출처 전체 현황은 `docs/SOURCE_CATALOG_STATUS.md`를 확인하세요.

## 7. 운영 주의사항

- 민간 사이트는 약관과 로그인 권한 확인 전 기본 비활성화 상태를 유지하세요.
- 첨부파일 대량 다운로드는 별도 승인 후 구현하는 것이 안전합니다.
- 공고 원문 데이터는 임의 수정하지 말고, 검토 판단은 `review_status`, `review_note`에 남기세요.
