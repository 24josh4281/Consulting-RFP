# Climate RFP Tracker MVP

한국 공공/민간 입찰 공고 중 기후, 온실가스, 배출권거래제, ESG 보고/검증 컨설팅과 관련된 공고를 수집·필터링·관리하기 위한 로컬 MVP입니다.

현재 버전은 “안전한 1차 자동화”에 집중합니다.

- 나라장터 입찰공고정보서비스 OpenAPI 연동 구조 준비
- 민간 대기업/계열사 입찰 페이지용 범용 HTML 수집기
- 기후·GHG·ETS·ESG 키워드 기반 관련성 점수화
- SQLite DB 저장
- CSV 내보내기
- 로컬 HTML 대시보드 생성
- 샘플 공고로 실행 검증 가능

## 빠른 실행

```powershell
python -m rfp_tracker sync --config configs\sources.example.json --db data\rfp_tracker.db --days 30
python -m rfp_tracker render --db data\rfp_tracker.db --out reports\dashboard.html
python -m rfp_tracker export-csv --db data\rfp_tracker.db --out reports\notices.csv
```

또는 한 번에 실행:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_tracker.ps1 -Days 14
```

생성 결과:

- `data/rfp_tracker.db`: 수집 DB
- `reports/dashboard.html`: 공고 확인용 대시보드
- `reports/notices.csv`: Excel에서 열 수 있는 공고 목록

## 공고 검토 상태 관리

후보 목록 확인:

```powershell
python -m rfp_tracker list --db data\rfp_tracker.db --limit 20
```

관심 공고 표시:

```powershell
python -m rfp_tracker review --db data\rfp_tracker.db --id 1 --status interesting --note "제안 검토 필요"
```

상태별 요약:

```powershell
python -m rfp_tracker stats --db data\rfp_tracker.db
```

## 나라장터 실제 연동

나라장터 공공데이터 API는 공공데이터포털 서비스키가 필요합니다.

```powershell
$env:DATA_GO_KR_SERVICE_KEY="발급받은_서비스키"
```

그 다음 `configs/sources.example.json`에서 `g2b_service_bids`의 `enabled` 값을 `true`로 바꾼 뒤 실행하세요.

주의:

- 서비스키를 코드 파일에 직접 저장하지 마세요.
- API 호출량 제한이 있으므로 처음에는 `--days 3`, `max_pages: 1`처럼 작게 테스트하세요.
- 공고 원문/RFP/과업지시서 첨부파일은 사이트·API별 구조가 달라서, 2차 단계에서 출처별 상세 어댑터를 추가하는 방식이 안전합니다.

## API 키와 대기업 포털 확장

필요한 키와 국내 기업 포털 확장 절차는 [docs/API_KEYS_AND_COMPANY_PORTALS.md](docs/API_KEYS_AND_COMPANY_PORTALS.md)를 확인하세요.

키 상태 확인:

```powershell
python -m rfp_tracker api-keys
```

KRX 공개 상장회사 목록 다운로드:

```powershell
python -m rfp_tracker companies-fetch-krx --out data\krx_listed_companies.csv
```

회사 홈페이지에서 구매/입찰/협력사 링크 후보 탐색:

```powershell
python -m rfp_tracker portal-discover --input data\krx_listed_companies.csv --out reports\portal_candidates.csv --limit 20
```

## 민간 사이트 실제 연동

민간 기업 입찰 사이트는 다음 이슈가 자주 있습니다.

- 로그인 필요
- 협력사 등록 필요
- JavaScript 렌더링
- 첨부파일 다운로드 권한
- 무단 수집/재배포 제한 문구

그래서 MVP는 무리한 크롤링 대신, 공개 HTML 페이지에 한해 `generic_html` 수집기를 제공합니다. 실제 운영 전에는 각 사이트의 이용약관과 robots 정책을 확인해야 합니다.

## 추천 운영 흐름

1. `configs/sources.example.json`에 출처 추가
2. 샘플/소수 출처로 `sync` 실행
3. `reports/dashboard.html`에서 관련성 점수 확인
4. 놓친 공고가 있으면 `configs/keywords.json`에 키워드 추가
5. 안정화 후 Windows 작업 스케줄러로 30~60분 간격 실행

## GitHub 연동

이 폴더는 로컬 git 저장소로 초기화되어 있습니다. GitHub 원격 저장소 URL을 받은 뒤 아래처럼 연결할 수 있습니다.

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\connect_github.ps1 -RepoUrl "https://github.com/YOUR_ACCOUNT/climate-rfp-tracker.git"
```

자세한 방법은 [docs/GITHUB_SETUP.md](docs/GITHUB_SETUP.md)를 확인하세요.

## 프로젝트 구조

```text
configs/
  keywords.json              # ESG/기후/GHG/ETS 키워드
  sources.example.json       # 출처 설정 예시
docs/
  01-plan/features/          # PDCA 계획 문서
  02-design/features/        # PDCA 설계 문서
rfp_tracker/
  cli.py                     # 명령어 진입점
  fetchers.py                # 나라장터/API/HTML 수집기
  keyword_matcher.py         # 키워드 점수화
  models.py                  # 데이터 구조
  render.py                  # HTML 대시보드
  storage.py                 # SQLite 저장
samples/
  sample_notices.html        # 실행 검증용 샘플 공고
tests/
  test_keyword_matcher.py    # 기본 테스트
```

## RFP / task document index

The tracker now creates a separate document-check report so RFPs and related files can be reviewed without opening each notice one by one.

```powershell
python -m rfp_tracker render-documents --db data\rfp_tracker.db --html reports\rfp_documents.html --csv reports\rfp_documents.csv
python -m rfp_tracker rfp-documents --db data\rfp_tracker.db --limit 50
```

Generated outputs:

- `reports/rfp_documents.html`: searchable browser report for RFP, task statement, notice, submission form, pricing and contract links
- `reports/rfp_documents.csv`: Excel-ready document checklist

Rows marked as `missing` mean the notice exists, but no RFP/task-document link has been collected yet. This can happen when a portal requires login, uses JavaScript, hides files behind a detail page, or needs a source-specific adapter.
