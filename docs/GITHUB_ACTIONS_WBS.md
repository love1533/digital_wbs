# WBS GitHub Actions 가이드

JIRA WBS 자동 업데이트 워크플로가 **GitHub Secrets**를 사용해 안전하게 동작하도록 설정하는 방법입니다.  
`.env`는 로컬 전용이며, **커밋하지 마세요.** Actions에서는 Repository Secrets만 사용합니다.

---

## 1. Repository Secrets 등록

**GitHub 저장소** → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

아래 5개를 **이름 그대로** 등록합니다.

| Secret 이름 | 설명 | 예시 |
|-------------|------|------|
| `JIRA_URL` | JIRA Cloud URL (끝에 `/` 제거) | `https://gcgfmobile.atlassian.net` |
| `JIRA_EMAIL` | JIRA 로그인 이메일 | `your@email.com` |
| `JIRA_API_TOKEN` | JIRA API 토큰 ([발급 방법](https://id.atlassian.com/manage-profile/security/api-tokens)) | `ATATT3x...` |
| `JIRA_PROJECT_KEY` | 프로젝트 키 | `GCGF0323` |
| `WBS_PASSWORD` | WBS HTML 접속 비밀번호 | 원하는 비밀번호 |

- `.env.example`을 복사해 `.env`를 만든 뒤 **로컬에서만** 사용하고, **절대 커밋하지 마세요.**
- Actions에서는 위 Secret 이름이 같아야 워크플로가 정상 동작합니다.

---

## 2. (선택) Variables 설정

**Settings** → **Secrets and variables** → **Actions** → **Variables** 탭에서 아래를 넣을 수 있습니다. 없으면 스크립트 기본값 사용.

| Variable 이름 | 설명 | 기본값 |
|---------------|------|--------|
| `WBS_TITLE` | 페이지 제목 | 프로젝트 WBS |
| `PROJECT_START_DATE` | 프로젝트 시작일 | `2026-03-23` |
| `TOTAL_WEEKS` | 총 주차 수 | `32` |

---

## 3. 워크플로 실행 조건

**파일:** `.github/workflows/update-wbs.yml`

| 트리거 | 설명 |
|--------|------|
| **스케줄** | 매일 **UTC 00:00** (한국시간 오전 9시)에 실행 |
| **Push** | `main` 또는 `claude/**` 브랜치에 `scripts/generate_wbs.py`가 변경되면 실행 |
| **수동** | **Actions** 탭 → **JIRA WBS 자동 업데이트** → **Run workflow** |

실행 시 JIRA에서 이슈를 가져와 다음을 생성·갱신합니다.

- `docs/data/snapshots/YYYY-MM-DD.json` (당일 스냅샷)
- `docs/data/snapshots/index.json` (스냅샷 목록)
- `docs/index.html`, `docs/history.html`

**변경이 있을 때만** 해당 파일들을 자동 커밋 후 **현재 브랜치**에 푸시합니다.

---

## 4. Push가 실패할 때

### "refusing to allow a Personal Access Token to create or publish"

- **Settings** → **Actions** → **General** → **Workflow permissions**
- **Read and write permissions**를 선택한 뒤 저장합니다.

### 특정 브랜치만 푸시 허용되어 있을 때

- 워크플로는 **트리거된 브랜치**에 그대로 푸시합니다.
- `main`에만 푸시하고 싶다면: 스케줄/수동 실행 시 기본 브랜치가 `main`이면 `main`에 푸시됩니다.
- **Branch protection**이 켜져 있으면: **Allow specified actors to bypass required pull requests**에 `github-actions[bot]`을 추가하거나, WBS 업데이트용 브랜치(예: `wbs/auto`)를 만들어 그쪽에만 푸시하도록 워크플로를 수정할 수 있습니다.

### JIRA 인증 실패 (401 / 403)

- `JIRA_EMAIL`과 `JIRA_API_TOKEN`이 맞는지 확인하세요.
- JIRA API 토큰은 [Atlassian 계정 보안](https://id.atlassian.com/manage-profile/security/api-tokens)에서 새로 발급할 수 있습니다.

---

## 5. 스냅샷 파일 (예: 2026-03-19)

- **수동 생성:** 로컬에서 `python scripts/generate_wbs.py`를 실행하면 **당일 날짜**의 `docs/data/snapshots/YYYY-MM-DD.json`과 `index.json`이 생성·갱신됩니다.
- **Actions:** 매일 스케줄 또는 수동 실행 시 당일 스냅샷이 생성되고, 변경분이 자동 커밋·푸시됩니다.
- 특정 날짜(예: 2026-03-19) JSON은 기존 스냅샷을 복사해 날짜만 바꾼 뒤 `index.json`에 해당 날짜를 추가해 두었습니다. 필요하면 같은 방식으로 다른 날짜도 추가하면 됩니다.

---

## 6. 요약

1. **Secrets 5개** (`JIRA_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`, `JIRA_PROJECT_KEY`, `WBS_PASSWORD`) 등록.
2. **Workflow permissions**를 Read and write로 설정.
3. `.env`는 로컬용으로만 쓰고 **커밋하지 않기** (이미 `.gitignore`에 포함됨).
4. 푸시 실패 시 위 4번을 참고해 권한·브랜치 설정 확인.

이렇게 설정하면 Actions가 JIRA 데이터를 가져와 HTML과 스냅샷을 갱신한 뒤, 같은 브랜치에 자동으로 푸시합니다.
