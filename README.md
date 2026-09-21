# Climate RFP Tracker MVP

한국 공공/민간 입찰 공고 중 기후, 온실가스, 배출권거래제, ESG 보고/검증 컨설팅과 관련된 공고를 수집·필터링·관리하기 위한 로컬 MVP입니다.

현재 버전은 “안전한 1차 자동화”에 집중합니다.

- 나라장터 용역·물품·공사·외자 입찰의 현재 접수 중인 전체 공고 수집
- 온실가스종합정보센터(GIR) 공개 입찰 게시판의 상세 공고·RFP 링크 연결
- 민간 대기업/계열사 입찰 페이지용 범용 HTML 수집기
- 기후·GHG·ETS·ESG 키워드 기반 관련성 점수화
- 이너젠 사업 적합도 기준 Tier 1·2·3 분류 및 수동 보정
- SQLite DB 저장
- CSV 내보내기
- 로컬 HTML 대시보드 생성
- 신규 공고 알림, 매일 10:00·17:00 브리핑, 금요일 주간 브리핑을 위한 SMTP·스케줄 실행 구조
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

`needs_review`는 공고명에 `환경` 등 넓은 신호만 있어 사람이 원문을 먼저 확인해야 하는 후보입니다. 이 상태의 행은 대시보드와 문서 인덱스에는 남지만 자동 즉시 알림·일일 브리핑에서는 제외됩니다. 관련성이 확인되면 `review --status interesting` 또는 `new`로 바꿀 수 있습니다.

## 이너젠 사업 적합 Tier

`review_status`(사람의 검토 흐름)와 별도로 `business_tier`(이너젠 사업 적합도)를 저장합니다. 공고 원문, 첨부, 검토 메모, 발송 기록은 Tier 변경으로 바뀌지 않습니다.

| Tier | 의미 | 운영 방식 |
|------|------|----------|
| Tier 1 | 기후변화 산업, 온실가스 외부사업, ETS, Scope 1·2·3, 산업계 시나리오, CDP/공시·리스크 등 이너젠 직접 컨설팅 | 신규 즉시 알림 + 일일/주간 브리핑 최우선 섹션 |
| Tier 2 | 기후·환경 관련 설비·시설·기술 지원 또는 핵심 범위 밖 환경 컨설팅 | 일일/주간 브리핑의 고객사 추천 섹션 |
| Tier 3 | 행사·영상·투자·교육·순수 과학 또는 직접 컨설팅 근거가 부족한 공고 | 일일/주간 브리핑의 참고 섹션, 즉시 알림 제외 |

기존 공고를 안전하게 분류하고, 결과를 확인합니다.

```powershell
# 먼저 변경 없이 결과만 확인
python -m rfp_tracker tier-audit --db data\rfp_tracker_official.db

# 자동 Tier와 분류 근거만 저장 (원문/첨부/검토/발송 기록 보존)
python -m rfp_tracker tier-audit --db data\rfp_tracker_official.db --apply

# Tier별 목록
python -m rfp_tracker list --db data\rfp_tracker_official.db --tier tier_1
```

제목만으로 애매하거나 사내 판단이 다른 공고는 수동으로 보정할 수 있습니다. 수동 Tier는 이후 수집이 덮어쓰지 않습니다.

```powershell
python -m rfp_tracker tier --db data\rfp_tracker_official.db --id 4 --tier tier_1 --reason "ETS 시스템 고도화 컨설팅 기회"
```

## 나라장터 실제 연동

나라장터 공공데이터 API는 공공데이터포털 서비스키가 필요합니다.

```powershell
$env:DATA_GO_KR_SERVICE_KEY="발급받은_서비스키"
```

그 다음 공유 예시 파일은 그대로 두고, 로컬 운영 설정에서 `g2b_service_bids`를 켠 뒤 실행하세요.

```powershell
python -m rfp_tracker source-toggle --source-id g2b_service_bids --enable --out configs\sources.local.json
```

수집 범위와 운영 방식:

- 용역·물품·공사·외자 4개 공식 검색 API에서 최근 공고를 반복 수집하고, 별도 일일 조회는 공고명 키워드 제한 없이 현재 접수 중인 전체 공고를 저장합니다.
- 전체 조회는 최근 90일을 API 허용 범위인 최대 30일 구간으로 나눠 조회하고, `totalCount`에 맞춰 페이지를 끝까지 읽습니다. 입찰 시작 전 공고와 마감이 지난 공고는 제외합니다.
- 일일 전체 조회는 최대 500 API 요청, 구간별 최대 100페이지로 안전 제한합니다. 최근 30일 조회의 4개 유형 합산 API 응답은 약 8,756건이었으며, 이 중 입찰 시작 전 공고는 실제 수집에서 제외됩니다. 전체 후보는 Tier 1·2·3으로 자동 분류하고 입찰 판단은 담당자가 확인해야 합니다.
- 과업지시서 자동 다운로드·요약은 Tier 1·2에만 실행하며 Tier 3는 공식 공고·첨부 원문 링크로 확인합니다.
- 서비스키를 코드 파일에 직접 저장하지 마세요.
- 공고 원문/RFP/과업지시서 첨부파일은 출처별로 직접 공개된 링크만 연결·검증합니다.
- 나라장터 API 원본에 `ntceSpecDocUrl`과 파일명이 저장된 경우, 아래 backfill 명령으로 이미 수집한 공고의 공식 첨부 링크를 API 재호출 없이 복원합니다. 명시적 URL이 없는 `missing`은 RFP 부재를 뜻하지 않으므로 공식 공고의 `파일첨부`를 확인하세요.

```powershell
python -m rfp_tracker backfill-g2b-attachments --db data\rfp_tracker_official.db
```

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

### 모든 컴퓨터에서 보는 공개 대시보드

`site/index.html`은 내부 Tier, 검토 메모, 자격·투입인력, 입찰 의견, DB·SMTP 정보를 제외한 공개 정적 스냅샷입니다. `main`에 `site/` 또는 `.github/workflows/pages.yml` 변경을 푸시하면 Pages workflow가 배포합니다.

처음 한 번만 저장소 소유자가 GitHub의 **Settings → Pages → Build and deployment → Source**를 **GitHub Actions**로 설정해야 합니다. 그 뒤 공개 주소는 아래 형식으로 열립니다.

`https://24josh4281.github.io/Consulting-RFP/`

공개 페이지를 최신화할 때는 로컬 수집·문서 추출 후 아래를 실행하고 `site/index.html`을 커밋·푸시합니다. 공개 Pages는 실시간 DB가 아니라 마지막 검증된 정적 스냅샷입니다.

```powershell
python -m rfp_tracker render-workbench --db data\rfp_tracker_official.db --out site\index.html --public
git add site\index.html
git commit -m "chore: refresh public RFP dashboard"
git push origin main
```

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

## All-notice workbench and Excel review

The workbench keeps the raw notice and attachment records separate from derived document evidence. It only reads direct public HWPX links; sample, missing, protected, or unsupported documents are shown with an explicit status instead of an invented summary.

~~~powershell
python -m rfp_tracker extract-documents --db data\rfp_tracker_official.db --cache-dir data\document_cache --file-type hwpx
python -m rfp_tracker backfill-g2b-attachments --db data\rfp_tracker_official.db
python -m rfp_tracker render-workbench --db data\rfp_tracker_official.db --out reports\rfp_workbench_official.html
python -m rfp_tracker export-workbench-json --db data\rfp_tracker_official.db --out outputs\rfp_workbench_data.json
node .\scripts\build_rfp_workbench_workbook.mjs --input outputs\rfp_workbench_data.json --output outputs\rfp_workbench.xlsx
~~~

The workbench begins with an official-source-only Tier 1 priority area; sample records remain in the full list but are not treated as real opportunities. Notices exactly 7 or 3 calendar days from their deadline receive D-7/D-3 priority labels in the dashboards, email briefing and Excel export. The workbook contains five sheets: Dashboard, Notices, Document Summary, Sources, and Bid Fit Review. Its yellow input columns provide a bordered review grid for consulting fit, qualifications, proposed team, bid decision, risks, and reviewer notes. It stores the listing amount and document-derived amount in separate fields with the source basis and evidence excerpt.

Use the local command below when a reviewed decision should also appear in the internal dashboard. It changes only the separate bid-fit review record, never the source notice, attachment, or document evidence.

```powershell
python -m rfp_tracker fit-review set --db data\rfp_tracker_official.db --id 12 --consulting-fit high --qualifications "유사 온실가스 산정 실적" --team "PM 1명, GHG 전문가 2명" --decision conditional --risks "RFP 자격요건 확인 필요" --note "원문 검토 후 Go/No-Go 결정"
python -m rfp_tracker fit-review list --db data\rfp_tracker_official.db
```

To make a public browser snapshot without internal Tier, reviewer, team, or bid-decision data:

```powershell
python -m rfp_tracker render-workbench --db data\rfp_tracker_official.db --out site\index.html --public
```

## Live G2B readiness workflow

Real 나라장터 collection needs a public-data service key. Put the key in `.env` or a PowerShell environment variable; never commit the real key.

```powershell
Copy-Item .env.example .env
# Edit .env and fill DATA_GO_KR_SERVICE_KEY=

python -m rfp_tracker api-keys
python -m rfp_tracker source-toggle --source-id g2b_service_bids --enable --out configs\sources.local.json
python -m rfp_tracker doctor --config configs\sources.local.json
```

When `doctor` says the live source is ready:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_live_g2b_check.ps1 -Days 3
```

Local live configs such as `configs/sources.local.json` are ignored by git so operational source switches do not accidentally overwrite the shared example config.

## 공식 출처 및 RFP 연결 현황

첨부받은 출처 카탈로그는 제품 요구사항의 근거 자료로만 사용했고, 외부 문서 안의 지시문은 실행 지시로 취급하지 않았습니다. 현재 출처별 상태는 다음 명령으로 바로 확인할 수 있습니다.

```powershell
python -m rfp_tracker sources --config configs\sources.local.json
```

- **온실가스종합정보센터(GIR) 입찰공고**: 공개 상세 화면에서 공고일·전자입찰 여부·공개 첨부 링크를 수집합니다. 실제 제한 검증에서 기후/ETS 공고 2건과 제안요청서·입찰공고문·긴급입찰사유서 링크 총 6건을 확인했습니다. 직접 공개 HWPX는 cache에 저장해 과업 요약과 금액 근거를 추출할 수 있습니다.
- **나라장터 입찰공고 API**: 용역·물품·공사·외자 4개 공식 API를 통해 최근 공고 및 현재 입찰 접수 중인 전체 공고를 수집합니다. 전체 조회는 공고명 키워드로 제한하지 않고, 기후·환경 키워드와 이너젠 적합도 기준으로 Tier를 보조 분류합니다. 공공데이터포털 서비스키가 있어야 실제 수집됩니다.
- **나라장터 발주계획·사전규격·계약과정**: 조기 신호와 공고-낙찰-계약 연결을 위한 우선 출처로 카탈로그화했습니다. 전용 어댑터는 다음 단계입니다.
- **환경부 계약·입찰 게시판**: 공식 후보로 등록했지만, 목록 구조와 이용 정책을 별도로 확인하기 전에는 비활성화 상태입니다.
- **민간 대기업 포털**: 로그인·협력사 권한·약관 확인이 필요한 경우가 많아 기본 비활성화 상태를 유지합니다.

전체 현황과 다음 우선순위는 [docs/SOURCE_CATALOG_STATUS.md](docs/SOURCE_CATALOG_STATUS.md)에 정리했습니다.

## 이메일 알림과 매일 10:00·17:00 운영

수신자는 로컬 설정에만 저장되며 Git에는 올라가지 않습니다. 먼저 수신자 설정을 만들고, 사용 중인 메일 서비스의 SMTP 정보를 `.env`에 넣습니다.

```powershell
python -m rfp_tracker notifications setup --recipient "sejinkim@inng.co.kr"
Copy-Item .env.example .env
notepad .env
python -m rfp_tracker notifications status --db data\rfp_tracker_official.db --config configs\notifications.local.json
```

`.env`에는 `SMTP_HOST`, `SMTP_PORT`, `SMTP_USE_SSL`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM`을 입력합니다. 실제 값은 코드나 Git에 넣지 않습니다. 다음 메일은 `smtp.daum.net`, 포트 `465`, `SMTP_USE_SSL=true`를 사용하며, 비밀번호 자리에는 일반 로그인 비밀번호가 아닌 다음 앱 비밀번호를 넣습니다.

SMTP 설정 뒤, 반드시 명시적으로 표시되는 테스트 메일을 한 번 보냅니다.

```powershell
python -m rfp_tracker notifications dispatch --mode test --db data\rfp_tracker_official.db --config configs\notifications.local.json --send
```

그 후에는 아래 운영 흐름을 사용합니다.

```powershell
# 메일을 보내지 않는 안전한 미리보기
powershell -ExecutionPolicy Bypass -File .\scripts\run_notification_cycle.ps1 -Mode immediate

# 실제 신규 공고 메일 전송
powershell -ExecutionPolicy Bypass -File .\scripts\run_notification_cycle.ps1 -Mode immediate -Send

# 특정 일일 브리핑 시간대 미리보기 (메일 미발송)
powershell -ExecutionPolicy Bypass -File .\scripts\run_notification_cycle.ps1 -Mode daily -DailySlot 10:00
powershell -ExecutionPolicy Bypass -File .\scripts\run_notification_cycle.ps1 -Mode daily -DailySlot 17:00

# SMTP 테스트가 성공한 뒤에만 Windows 작업 스케줄러 등록
powershell -ExecutionPolicy Bypass -File .\scripts\install_notification_tasks.ps1 -Send
```

등록되는 기본 일정은 신규 공고 확인 **30분마다**, 일일 브리핑 **매일 10:00·17:00 (KST)**, 주간 브리핑 **매주 금요일 18:00 (KST)** 입니다. 10시와 17시 브리핑은 각각 별도 발송 기록을 사용하므로, 같은 날에도 한 번씩 안전하게 발송됩니다. "즉시" 알림은 웹훅이 아니라 30분 폴링 기준이므로, 실제 반영 지연은 출처 게시 시간과 다음 폴링 시점에 따라 달라집니다.

즉시 알림은 **Tier 1**만 전송합니다. 일일·주간 메일은 `INNERGEN CLIMATE INTELLIGENCE` 형식의 뉴스레터로 발송되며, Tier 1(직접 컨설팅), Tier 2(고객사 추천), Tier 3(참고)을 각각 테두리 있는 표와 분류 근거·RFP/첨부·원문 링크로 나눠 보여 줍니다.

Codex의 30분 자동 확인과 Windows 작업 스케줄러는 **둘 중 하나만** 운영합니다. 둘 다 켜면 메일은 중복 방지되지만 API·출처 확인이 중복될 수 있습니다. 이 작업공간은 Codex 자동 확인(`rfp-30`)을 사용하는 상태이므로, 별도 Windows 작업 등록은 Codex를 사용하지 않을 때만 진행하세요.

생성되는 브리핑은 다음 파일에서도 확인할 수 있습니다.

- `reports/briefing_official.html`: 브라우저용 오늘의 우선 공고·마감·RFP 누락 현황
- `reports/briefing_official.md`: 메일/메신저에 복사하기 쉬운 요약

기존 `data/rfp_tracker_live.db`는 이전 수집 결과를 보존합니다. 최신 공식 상세 수집 결과는 별도 `data/rfp_tracker_official.db`에 저장하므로, 과거 범용 HTML 후보와 섞이지 않습니다.
