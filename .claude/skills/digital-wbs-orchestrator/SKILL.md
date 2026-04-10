---
name: digital-wbs-orchestrator
description: "디지털 고도화 WBS 프로젝트 관리 오케스트레이터. WBS 생성, 태스크 관리, 일별 실적 기록, 진척률 리포트, 로컬 웹 대시보드, Jira 중복 정리 등 WBS 관련 모든 작업을 처리. 'WBS 만들어줘', '태스크 추가', '오늘 실적 입력', '진척률 보여줘', '리포트 생성', '일별 현황', '주간 보고', 'WBS 수정', '지연 태스크', '담당자별 현황', '실적 조회', '대시보드 열어줘', '웹으로 보여줘', '로컬웹', 'Jira 중복 정리', '중복 이슈 합쳐줘', 'Jira 동기화', 'WBS 업데이트', '다시 실행', '결과 수정', '보완' 등의 표현에 반드시 이 스킬을 사용."
---

# Digital WBS Orchestrator

디지털 고도화 WBS 프로젝트의 에이전트를 조율하여 WBS 관리 및 리포팅을 수행하는 통합 스킬.

## 실행 모드: 서브 에이전트

## 에이전트 구성

| 에이전트 | 역할 | 스킬 | 출력 |
|---------|------|------|------|
| wbs-manager | WBS 구조 생성/수정, 실적 기록 | wbs-manage | `wbs_data.json` |
| wbs-reporter | 진척률 분석, 리포트 생성 | wbs-report | 텍스트 출력 |
| wbs-dashboard | 로컬 웹 대시보드 생성/실행 | wbs-dashboard | `dashboard.html` + 서버 실행 |
| wbs-jira-sync | Jira 중복 이슈 감지 및 병합 | wbs-jira-sync | Jira 이슈 병합 결과 |

## 워크플로우

### Phase 0: 요청 분류

사용자 요청을 분석하여 적절한 에이전트를 선택한다:

| 요청 유형 | 에이전트 | 예시 |
|----------|---------|------|
| WBS 구조 생성/수정 | wbs-manager | "WBS 만들어줘", "태스크 추가해줘" |
| 실적 기록 | wbs-manager | "오늘 실적 입력", "AN-001 30%" |
| 리포트 조회 | wbs-reporter | "오늘 실적 보여줘", "진척률 현황" |
| 웹 대시보드 | wbs-dashboard | "대시보드 열어줘", "웹으로 보여줘", "로컬웹" |
| Jira 중복 정리 | wbs-jira-sync | "Jira 중복 합쳐줘", "중복 이슈 정리", "Jira 동기화" |
| 복합 요청 | 순차 호출 | "실적 입력하고 리포트 보여줘" |

**단순 질문/확인은 에이전트 없이 직접 응답:**
- "WBS가 뭐야?", "태스크 ID 규칙이 뭐야?" 등

### Phase 1: 컨텍스트 확인

1. `wbs_data.json` 존재 여부 확인
2. 존재하면 현재 상태 파악 (태스크 수, 최근 기록 날짜 등)
3. 실행 모드 결정:
   - **`wbs_data.json` 미존재 + WBS 생성 요청** → wbs-manager로 초기 생성
   - **`wbs_data.json` 존재 + 수정/기록 요청** → wbs-manager로 부분 수정
   - **`wbs_data.json` 존재 + 조회 요청** → wbs-reporter로 리포트

### Phase 2: 에이전트 호출

**wbs-manager 호출 시:**
```
Agent(
  prompt: "에이전트 정의: .claude/agents/wbs-manager.md 를 읽고 역할을 수행하라.
           스킬: .claude/skills/wbs-manage/SKILL.md 를 읽고 지침을 따르라.

           [사용자 요청 내용]

           데이터 파일: wbs_data.json",
  model: "opus"
)
```

**wbs-reporter 호출 시:**
```
Agent(
  prompt: "에이전트 정의: .claude/agents/wbs-reporter.md 를 읽고 역할을 수행하라.
           스킬: .claude/skills/wbs-report/SKILL.md 를 읽고 지침을 따르라.

           [사용자 요청 내용]

           데이터 파일: wbs_data.json",
  model: "opus"
)
```

**wbs-dashboard 호출 시:**
```
Agent(
  prompt: "에이전트 정의: .claude/agents/wbs-dashboard.md 를 읽고 역할을 수행하라.
           스킬: .claude/skills/wbs-dashboard/SKILL.md 를 읽고 지침을 따르라.

           [사용자 요청 내용]

           데이터 파일: wbs_data.json
           대시보드 파일: dashboard.html",
  model: "opus"
)
```

**wbs-jira-sync 호출 시:**
```
Agent(
  prompt: "에이전트 정의: .claude/agents/wbs-jira-sync.md 를 읽고 역할을 수행하라.
           스킬: .claude/skills/wbs-jira-sync/SKILL.md 를 읽고 지침을 따르라.

           [사용자 요청 내용]

           중요: 중복 목록을 먼저 보여주고 사용자 승인 후 병합을 실행하라.",
  model: "opus"
)
```

### Phase 3: 결과 전달

- wbs-manager 결과: `wbs_data.json` 변경 내역을 요약하여 사용자에게 보고
- wbs-reporter 결과: 리포트 내용을 그대로 사용자에게 출력
- 복합 요청: manager 완료 후 reporter 순차 실행, 두 결과를 통합 보고

## 데이터 흐름

```
[사용자 요청]
     ↓
[오케스트레이터: 요청 분류]
     ↓
┌─ 구조/실적 ──→ [wbs-manager]   → wbs_data.json 업데이트 → 변경 요약 출력
├─ 리포트 ────→ [wbs-reporter]  → wbs_data.json 읽기 → 리포트 텍스트 출력
├─ 대시보드 ──→ [wbs-dashboard] → dashboard.html 생성 → 서버 실행
└─ Jira 정리 ─→ [wbs-jira-sync] → 중복 감지 → 승인 → 병합 실행
```

## 파일 관리 원칙

이 프로젝트의 핵심 원칙은 **파일 최소화**이다:

| 파일 | 용도 | 생성 시점 |
|------|------|----------|
| `wbs_data.json` | WBS 전체 데이터 (유일한 데이터 파일) | 최초 WBS 생성 시 |
| `wbs_data.backup.json` | 백업 | JSON 오류 발생 시에만 |
| `dashboard.html` | 웹 대시보드 (단일 HTML) | 대시보드 최초 생성 시 |
| `_workspace/report_*.md` | 리포트 파일 | 사용자가 명시적으로 파일 저장 요청 시에만 |

**절대 하지 말 것:**
- 태스크별 별도 파일 생성
- 날짜별 별도 파일 생성
- 자동으로 리포트 파일 저장
- 임시 파일 생성

## 에러 핸들링

| 에러 상황 | 대응 |
|----------|------|
| `wbs_data.json` 미존재 + 리포트 요청 | "WBS를 먼저 생성해주세요" 안내 |
| JSON 파싱 실패 | 백업 생성 후 사용자에게 복구 방법 안내 |
| 에이전트 실행 실패 | 에러 내용을 사용자에게 보고, 1회 재시도 |
| 잘못된 태스크 ID | 유사 ID 제안 |

## 테스트 시나리오

### 정상 흐름
1. "디지털 고도화 WBS 만들어줘. 분석/설계/개발/테스트/이행 5단계로." → wbs-manager가 wbs_data.json 생성
2. "AN-001 오늘 30% 진행, 현행 시스템 문서 수집 완료" → wbs-manager가 daily_log 추가
3. "오늘 실적 보여줘" → wbs-reporter가 일별 리포트 출력
4. "대시보드 열어줘" → wbs-dashboard가 dashboard.html 생성 + 서버 실행
5. "Jira 중복 정리해줘, 프로젝트 DIG" → wbs-jira-sync가 중복 감지 → 사용자 승인 → 병합

### 에러 흐름
1. WBS 없이 "실적 보여줘" → "WBS를 먼저 생성해주세요" 안내
2. 존재하지 않는 ID "XX-999 50%" → "해당 태스크를 찾을 수 없습니다" + 유사 ID 제안
3. WBS 없이 "대시보드 열어줘" → "WBS 데이터가 없어 대시보드를 생성할 수 없습니다" 안내
4. Jira 미연결 시 중복 정리 요청 → "Jira 연결을 확인해주세요" 안내
