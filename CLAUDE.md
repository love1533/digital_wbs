# Digital WBS Project

디지털 고도화 WBS 프로젝트 관리 시스템. 로컬 WBS 관리 + Jira 연동 자동화를 지원한다.

## 기술 스택

- Python 3.11+, pytest, pytest-cov
- 메인 패키지: `repo_llm/` (LLM 유틸리티 라이브러리)
- 웹 데모: FastAPI (`app.py`)
- Jira 연동: `scripts/generate_wbs.py` + GitHub Actions
- 대시보드: Chart.js CDN + 순수 JS

## 프로젝트 구조

이 프로젝트는 **2개의 WBS 시스템**이 공존한다:

| 구분 | 로컬 WBS | Jira 연동 WBS |
|------|----------|---------------|
| 데이터 | `wbs_data.json` | `docs/data/snapshots/*.json` |
| 뷰어 | `dashboard.html` | `docs/index.html` + `docs/history.html` |
| 자동화 | 수동 | GitHub Actions 매일 9시 KST |
| 백업 | 없음 | 일별 스냅샷 자동 저장 |
| 프로젝트 | GCGF0323 | GCGF0323 |

## 하네스: 디지털 고도화 WBS

**목표:** 디지털 고도화 프로젝트의 WBS를 관리하고, 일별 실적을 기록/조회하며, 로컬 웹 대시보드로 시각화하고, Jira 중복 이슈를 정리한다. 파일 수를 최소화한다.

**에이전트 팀:**
| 에이전트 | 역할 |
|---------|------|
| wbs-manager | WBS 구조 생성/수정, 일별 실적 기록 |
| wbs-reporter | 진척률 분석, 일별/주별/페이즈별 리포트 생성 |
| wbs-dashboard | 로컬 웹 대시보드 생성 및 서버 실행 |
| wbs-jira-sync | Jira 중복 이슈 감지 및 병합 |

**스킬:**
| 스킬 | 용도 | 사용 에이전트 |
|------|------|-------------|
| digital-wbs-orchestrator | WBS 관련 모든 요청의 진입점, 에이전트 조율 | 오케스트레이터 |
| wbs-manage | WBS 구조/실적 데이터 관리 | wbs-manager |
| wbs-report | 진척률 리포트 생성 | wbs-reporter |
| wbs-dashboard | 로컬 웹 대시보드 시각화 | wbs-dashboard |
| wbs-jira-sync | Jira 중복 이슈 감지/병합 | wbs-jira-sync |

**실행 규칙:**
- WBS 관련 작업 요청 시 `digital-wbs-orchestrator` 스킬을 통해 에이전트로 처리하라
- 단순 질문/확인은 에이전트 없이 직접 응답해도 무방
- 모든 에이전트는 `model: "opus"` 사용
- **파일 최소화 원칙:** 데이터는 `wbs_data.json` 단일 파일, 대시보드는 `dashboard.html` 단일 파일, 리포트는 텍스트 출력 (파일 저장은 명시적 요청 시에만)
- Jira 중복 병합은 삭제 없이 링크+종료 방식. 반드시 사용자 승인 후 실행

**디렉토리 구조:**
```
.claude/
├── agents/
│   ├── wbs-manager.md
│   ├── wbs-reporter.md
│   ├── wbs-dashboard.md
│   └── wbs-jira-sync.md
└── skills/
    ├── digital-wbs-orchestrator/
    │   └── SKILL.md
    ├── wbs-manage/
    │   └── SKILL.md
    ├── wbs-report/
    │   └── SKILL.md
    ├── wbs-dashboard/
    │   └── SKILL.md
    └── wbs-jira-sync/
        └── SKILL.md
wbs_data.json          ← 로컬 WBS 데이터 (단일 파일)
dashboard.html         ← 로컬 웹 대시보드 (단일 HTML, Chart.js)
app.py                 ← repo_llm 데모 웹앱 (FastAPI)
docs/
├── index.html         ← Jira 연동 WBS 간트 뷰 (비밀번호 보호)
├── history.html       ← Jira 이슈 이력 조회 뷰어
├── data/snapshots/    ← 일별 Jira 스냅샷 백업 (자동 생성)
│   ├── index.json     ← 스냅샷 인덱스
│   └── YYYY-MM-DD.json
├── GITHUB_ACTIONS_WBS.md  ← GitHub Actions 설정 가이드
scripts/
├── generate_wbs.py    ← Jira → HTML 생성 스크립트
└── requirements.txt   ← 스크립트 의존성
.github/workflows/
├── ci.yml             ← CI (테스트 + 서버 헬스체크)
├── update-wbs.yml     ← 매일 Jira 데이터 동기화 + 스냅샷
└── update-password.yml ← WBS 비밀번호 업데이트
.env.example           ← 환경변수 템플릿 (Jira 인증)
```

**GitHub Actions 자동화:**
- `update-wbs.yml`: 매일 오전 9시 KST (UTC 00:00) Jira 데이터를 수집하여 `docs/index.html` 재생성 + `docs/data/snapshots/` 일별 백업
- `ci.yml`: 모든 브랜치 push/PR 시 테스트 + 서버 헬스체크
- 필수 Secrets: `JIRA_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`, `JIRA_PROJECT_KEY`, `WBS_PASSWORD`

**변경 이력:**
| 날짜 | 변경 내용 | 대상 | 사유 |
|------|----------|------|------|
| 2026-04-10 | 초기 구성 | 전체 | 디지털 고도화 WBS 프로젝트 하네스 신규 구축 |
| 2026-04-10 | 로컬 웹 대시보드 추가 | agents/wbs-dashboard, skills/wbs-dashboard | 일별 실적을 브라우저에서 시각화 |
| 2026-04-10 | Jira 중복 정리 추가 | agents/wbs-jira-sync, skills/wbs-jira-sync | Jira 중복 이슈 감지/병합 기능 |
| 2026-04-10 | 하네스 구조 업데이트 | CLAUDE.md | Jira 연동 WBS, GitHub Actions, 스냅샷 백업 구조 반영 |
