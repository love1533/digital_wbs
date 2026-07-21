# Digital WBS

디지털 고도화 프로젝트의 **WBS(Work Breakdown Structure) 관리 시스템**입니다.
로컬에서 WBS를 관리·시각화하고, Jira와 연동해 매일 자동으로 진척 데이터를 수집·백업합니다.

---

## 주요 기능

- 📋 **WBS 관리** — 태스크 구조 생성/수정, 일별 실적 기록 (`wbs_data.json`)
- 📊 **로컬 대시보드** — 페이즈별 진척률, 추이 차트, 태스크 상세를 브라우저에서 조회 (`dashboard.html`)
- 🔄 **Jira 연동** — Jira 이슈를 수집하여 간트 뷰 HTML 자동 생성 (`docs/index.html`)
- 🗂 **일별 스냅샷 백업** — GitHub Actions가 매일 Jira 데이터를 스냅샷으로 저장 (`docs/data/snapshots/`)
- 🤖 **자동화** — 매일 오전 9시(KST) Jira 동기화, 모든 push/PR에 CI 실행

---

## 시스템 구성

이 프로젝트는 **2개의 WBS 시스템**이 공존합니다.

| 구분 | 로컬 WBS | Jira 연동 WBS |
|------|----------|---------------|
| 데이터 | `wbs_data.json` | `docs/data/snapshots/*.json` |
| 뷰어 | `dashboard.html` | `docs/index.html` + `docs/history.html` |
| 자동화 | 수동 | GitHub Actions (매일 9시 KST) |
| 백업 | 없음 | 일별 스냅샷 자동 저장 |

---

## 기술 스택

- **Python 3.11+**, pytest, pytest-cov
- 메인 패키지: `repo_llm/` (LLM 유틸리티 라이브러리)
- 웹 데모: FastAPI (`app.py`)
- Jira 연동: `scripts/generate_wbs.py` + GitHub Actions
- 대시보드: Chart.js (CDN) + 순수 JavaScript

---

## 빠른 시작

### 1. 저장소 클론

```bash
git clone https://github.com/love1533/digital_wbs.git
cd digital_wbs
```

### 2. 로컬 대시보드 실행

WBS 대시보드(`dashboard.html`)를 로컬 HTTP 서버로 서빙합니다.

```bash
./startup.sh              # 기본 포트 8000
./startup.sh --port 9000  # 포트 지정
```

실행 후 브라우저에서 접속:

```
http://localhost:8000/dashboard.html
```

서버 종료:

```bash
./stop.sh
```

### 3. 개발 환경 설정 (테스트/패키지)

```bash
pip install -e ".[dev]"
pytest                    # 커버리지 90% 미만 시 실패
```

### 4. Jira 연동 (선택)

`.env.example`을 복사해 인증 정보를 채웁니다.

```bash
cp .env.example .env
# .env에 JIRA_URL, JIRA_EMAIL, JIRA_API_TOKEN 등 입력
python scripts/generate_wbs.py   # Jira → docs/index.html 생성
```

---

## 프로젝트 구조

```
digital_wbs/
├── wbs_data.json          # 로컬 WBS 데이터 (단일 파일)
├── dashboard.html         # 로컬 웹 대시보드 (단일 HTML, Chart.js)
├── startup.sh / stop.sh   # 대시보드 서버 시작/종료 스크립트
├── app.py                 # repo_llm 데모 웹앱 (FastAPI)
├── repo_llm/              # LLM 유틸리티 라이브러리
├── tests/                 # pytest 테스트
├── docs/
│   ├── index.html         # Jira 연동 WBS 간트 뷰 (비밀번호 보호)
│   ├── history.html       # Jira 이슈 이력 조회 뷰어
│   └── data/snapshots/    # 일별 Jira 스냅샷 백업 (자동 생성)
├── scripts/
│   ├── generate_wbs.py    # Jira → HTML 생성 스크립트
│   └── requirements.txt
├── .github/workflows/
│   ├── ci.yml             # 테스트 + 서버 헬스체크
│   ├── update-wbs.yml     # 매일 Jira 동기화 + 스냅샷
│   └── update-password.yml
└── .env.example           # 환경변수 템플릿 (Jira 인증)
```

---

## GitHub Actions 자동화

| 워크플로 | 트리거 | 동작 |
|---------|--------|------|
| `update-wbs.yml` | 매일 09:00 KST (UTC 00:00) | Jira 데이터 수집 → `docs/index.html` 재생성 + 일별 스냅샷 백업 |
| `ci.yml` | 모든 push / PR | 테스트 실행 + 서버 헬스체크 |
| `update-password.yml` | 수동 | WBS 대시보드 비밀번호 업데이트 |

**필수 Secrets:** `JIRA_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`, `JIRA_PROJECT_KEY`, `WBS_PASSWORD`

---

## 라이선스 / 문의

내부 프로젝트 관리용 저장소입니다. 자세한 운영 규칙은 [`CLAUDE.md`](./CLAUDE.md)를 참고하세요.
