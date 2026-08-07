# GitHub 연동 가이드

이 프로젝트는 로컬 git 저장소로 초기화되어 있으며, 첫 커밋이 완료되어 있습니다.

현재 상태:

- Branch: `main`
- Initial commit: `Build climate RFP tracker MVP`
- DB/CSV/HTML 산출물, `.env`, `.bkit`, Python cache는 `.gitignore`로 제외

## 1. GitHub에서 새 저장소 만들기

GitHub 웹사이트에서 새 repository를 만듭니다.

추천 이름:

```text
climate-rfp-tracker
```

처음 만들 때 아래 옵션은 선택하지 않는 것을 권장합니다.

- README 생성 안 함
- `.gitignore` 생성 안 함
- License 생성 안 함

이미 로컬에 README와 `.gitignore`가 있기 때문입니다.

## 2. 원격 저장소 연결

GitHub 저장소 URL이 예를 들어 아래와 같다면:

```text
https://github.com/YOUR_ACCOUNT/climate-rfp-tracker.git
```

PowerShell에서 실행:

```powershell
git remote add origin https://github.com/YOUR_ACCOUNT/climate-rfp-tracker.git
git remote -v
```

## 3. GitHub로 push

```powershell
git push -u origin main
```

## 4. GitHub CLI를 사용할 경우

현재 환경에는 `gh` 명령이 설치되어 있지 않습니다. 설치하면 PR 생성, 인증 확인, Actions 확인이 쉬워집니다.

설치 후 확인:

```powershell
gh --version
gh auth login
gh auth status
```

이미 GitHub CLI 인증이 완료된 경우:

```powershell
gh repo create climate-rfp-tracker --private --source . --remote origin --push
```

공개 저장소로 만들고 싶다면 `--private` 대신 `--public`을 사용합니다.

## 5. 보안 주의사항

- `DATA_GO_KR_SERVICE_KEY`는 절대 GitHub에 올리지 마세요.
- 서비스키는 환경변수 또는 로컬 `.env`에만 둡니다.
- `.env`, DB, CSV/HTML 산출물은 현재 `.gitignore`로 제외되어 있습니다.
- 실제 민간 사이트 수집 설정을 켤 때는 사이트 약관/권한을 먼저 확인하세요.

