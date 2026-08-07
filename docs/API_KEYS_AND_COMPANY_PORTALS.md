# API 키 및 자산 2조원 이상 기업 포털 확장 계획

## 1. 실제 키 발급이 필요한 API

| API | 환경변수 | 발급처 | 용도 |
|-----|----------|--------|------|
| 공공데이터포털 서비스키 | `DATA_GO_KR_SERVICE_KEY` | <https://www.data.go.kr/> | 나라장터 입찰공고, 공공 조달 데이터 |
| OpenDART 인증키 | `OPENDART_API_KEY` | <https://opendart.fss.or.kr/uss/umt/EgovMberInsertView.do> | 기업 식별, 공시, 재무제표 기반 자산총액 필터 |

키 상태 확인:

```powershell
python -m rfp_tracker api-keys
```

중요:

- 실제 키는 `.env` 또는 PowerShell 환경변수에만 둡니다.
- `.env`는 `.gitignore`에 포함되어 GitHub에 올라가지 않습니다.
- 제가 키를 대신 발급받거나 로그인할 수는 없습니다.

## 2. 자산총액 2조원 이상 기업 기준

“자산총액 2조원 이상”은 기업지배구조보고서 의무공시가 2019년 처음 시작될 때의 코스피 상장회사 기준으로 자주 쓰였습니다. 다만 2026년부터는 코스피 전체 상장회사로 기업지배구조보고서 공시 의무가 확대되었습니다.

따라서 이 프로젝트에서는 기준을 두 단계로 분리합니다.

1. KRX 공개 상장법인 목록으로 전체 회사/홈페이지 후보를 확보
2. OpenDART 또는 KIND 재무 데이터를 이용해 `asset_total_krw >= 2,000,000,000,000` 필터 적용

현재 구현된 범위:

- KRX 공개 상장법인 목록 다운로드
- 회사 홈페이지 후보 CSV 생성
- 홈페이지에서 구매/입찰/협력사 링크 후보 탐색

키가 있어야 하는 후속 범위:

- OpenDART 재무제표 기반 자산총액 2조원 이상 필터
- 기업별 공시/보고서 원문 수집

## 3. 실행 순서

### 3.1 KRX 상장회사 목록 받기

```powershell
python -m rfp_tracker companies-fetch-krx --out data\krx_listed_companies.csv
```

### 3.2 회사 홈페이지 source 설정 생성

처음에는 100개만 생성:

```powershell
python -m rfp_tracker company-sources --input data\krx_listed_companies.csv --out configs\company_homepages.generated.json --limit 100
```

전체 생성:

```powershell
python -m rfp_tracker company-sources --input data\krx_listed_companies.csv --out configs\company_homepages.generated.json --limit 0
```

생성된 source는 모두 `enabled: false`입니다. 검토 후 필요한 출처만 켜세요.

### 3.3 공개 홈페이지에서 포털 후보 찾기

안전한 소량 검증:

```powershell
python -m rfp_tracker portal-discover --input data\krx_listed_companies.csv --out reports\portal_candidates.csv --limit 20
```

더 많이 확인:

```powershell
python -m rfp_tracker portal-discover --input data\krx_listed_companies.csv --out reports\portal_candidates.csv --limit 100
```

주의:

- 이 결과는 “후보”입니다.
- 실제 입찰/구매 포털인지, 수집해도 되는지 약관 확인이 필요합니다.
- 로그인/협력사 등록이 필요한 포털은 자동 수집 대상에서 제외해야 합니다.

## 4. API 키 설정 예시

PowerShell 현재 세션에만 설정:

```powershell
$env:DATA_GO_KR_SERVICE_KEY="발급받은_공공데이터포털_서비스키"
$env:OPENDART_API_KEY="발급받은_OpenDART_인증키"
```

확인:

```powershell
python -m rfp_tracker api-keys
```

## 5. 왜 바로 “모든 민간 포털 크롤링”을 하지 않는가

국내 대기업 구매/입찰 포털은 대개 다음 중 하나입니다.

- 공개 공고 페이지
- 협력사 등록 후 접근
- 로그인 필요
- JavaScript 렌더링
- robots/약관상 자동 수집 제한
- 첨부파일 다운로드 권한 필요

그래서 운영상 안전한 순서는 다음입니다.

1. 공개 홈페이지에서 포털 후보 탐색
2. 약관/권한 확인
3. source를 수동 활성화
4. 소량 수집 테스트
5. 출처별 전용 어댑터 구현

