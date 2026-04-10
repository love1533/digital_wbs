---
name: wbs-jira-sync
description: "Jira 프로젝트의 중복 이슈를 감지하고 하나로 병합하는 스킬. WBS 데이터와 Jira 이슈 간 동기화도 지원. 'Jira 중복 정리', '중복 이슈 합쳐줘', 'Jira 동기화', '중복 확인', 'Jira 정리', '이슈 병합', '중복 제거', 'Jira에서 중복', 'Jira 이슈 정리', '중복 이슈 찾아줘' 등의 표현에 반드시 트리거."
---

# WBS Jira 동기화 스킬

Jira 프로젝트에서 중복 이슈를 찾아 하나로 병합한다. 이슈를 삭제하지 않고, 링크+종료 방식으로 안전하게 처리한다.

## 병합 원칙

1. **삭제 금지**: 어떤 이슈도 삭제하지 않는다
2. **사전 승인**: 중복 목록을 먼저 보여주고 사용자 승인 후 실행한다
3. **이력 보존**: 모든 병합은 코멘트로 기록한다
4. **되돌리기 가능**: 링크와 코멘트만 추가하므로 수동으로 되돌릴 수 있다

## 워크플로우

### Phase 1: Jira 연결 확인

1. `getAccessibleAtlassianResources`로 접근 가능한 사이트 확인
2. cloudId 획득
3. 사용자에게 대상 프로젝트 키 확인 (모르면 `getVisibleJiraProjects`로 목록 표시)

### Phase 2: 이슈 수집

```
searchJiraIssuesUsingJql:
  cloudId: {cloudId}
  jql: "project = {KEY} AND status != Done ORDER BY created DESC"
  fields: [summary, description, status, issuetype, priority, created, assignee]
  maxResults: 100
  responseContentFormat: "markdown"
```

100건 초과 시 `nextPageToken`으로 페이징.

### Phase 3: 중복 감지

**비교 알고리즘:**

1. 모든 이슈 쌍(N*(N-1)/2)을 비교한다
2. 유사도 점수 계산:

```
유사도 = (제목유사도 × 0.7) + (타입일치 × 0.2) + (기간근접 × 0.1)
```

**제목 유사도 판단:**
- 공백/특수문자 제거 후 비교
- 핵심 명사 추출하여 겹침 비율 계산
- 접두사(`[WBS]`, `[분석]` 등) 제거 후 비교
- 80% 이상이면 중복 후보

**추가 확인:**
- 같은 issuetype인지 (Task-Task, Story-Story)
- 생성일이 30일 이내인지
- 이미 "Duplicate" 링크가 있는지 (있으면 제외)

### Phase 4: 중복 리포트 출력

```markdown
## Jira 중복 이슈 감지 결과 — {PROJECT_KEY}

총 이슈: {N}건 | 중복 후보: {M}쌍

| # | 메인 이슈 | 제목 | 중복 이슈 | 제목 | 유사도 | 판단 근거 |
|---|----------|------|----------|------|--------|----------|
| 1 | DIG-10 | 현행 시스템 분석 | DIG-25 | 현행시스템 분석 | 95% | 제목 동일 |

**메인 이슈 선택 기준:** 더 오래된 이슈 또는 진행률이 높은 이슈를 메인으로 유지

→ 병합을 진행하시겠습니까?
```

### Phase 5: 병합 실행 (승인 후)

각 중복 쌍에 대해:

1. **메인 이슈에 코멘트 추가:**
   ```
   addCommentToJiraIssue:
     issueIdOrKey: {메인이슈}
     commentBody: "[중복 병합] {중복이슈}의 내용이 이 이슈로 병합되었습니다.\n\n원본 제목: {중복이슈 제목}\n원본 설명 요약: {설명 앞 200자}"
     contentFormat: "markdown"
   ```

2. **중복 링크 생성:**
   ```
   createIssueLink:
     inwardIssue: {메인이슈}
     outwardIssue: {중복이슈}
     type: "Duplicate"
   ```

3. **중복 이슈에 코멘트 추가:**
   ```
   addCommentToJiraIssue:
     issueIdOrKey: {중복이슈}
     commentBody: "[중복 종료] 이 이슈는 {메인이슈}와 중복으로 판단되어 병합되었습니다."
     contentFormat: "markdown"
   ```

4. **중복 이슈 종료:**
   ```
   getTransitionsForJiraIssue → Done/Closed 전환 ID 확인
   transitionJiraIssue:
     issueIdOrKey: {중복이슈}
     transition: {id: "종료전환ID"}
   ```

### Phase 6: 결과 보고

```markdown
## 병합 완료 결과

| # | 메인 이슈 | 병합된 이슈 | 상태 |
|---|----------|-----------|------|
| 1 | DIG-10 | DIG-25 | 완료 |
| 2 | DIG-12 | DIG-30 | 완료 |
| 3 | DIG-15 | DIG-33 | 실패 (전환 불가) |

성공: {N}건 | 실패: {M}건
```

## 에러 처리

| 에러 | 대응 |
|------|------|
| Jira 미연결 | `getAccessibleAtlassianResources` 재시도, 실패 시 연결 안내 |
| 프로젝트 없음 | 접근 가능 프로젝트 목록 표시 |
| "Duplicate" 링크 타입 없음 | `getIssueLinkTypes`로 가용 타입 표시, 유사한 것 제안 |
| 전환 불가 | 해당 이슈 건너뛰고 수동 처리 안내 |
| 중복 0건 | "중복 이슈가 없습니다" 출력 |
