---
name: wbs-dashboard
description: "WBS 데이터를 로컬 웹 대시보드로 시각화하는 스킬. 단일 HTML 파일 + Python 내장 서버로 브라우저에서 일별 실적, 페이즈별 진척률, 추이 차트, 태스크 상세를 조회. '대시보드 열어줘', '웹으로 보여줘', '로컬 웹', '브라우저에서 보기', '대시보드 실행', '대시보드 업데이트', '차트 보여줘', '웹 대시보드', '시각화' 등의 표현에 반드시 트리거."
---

# WBS 웹 대시보드 스킬

`wbs_data.json`을 로컬 웹 브라우저에서 시각화한다. 파일 최소화 원칙에 따라 `dashboard.html` 단일 파일로 구현한다.

## 파일 구성

| 파일 | 용도 |
|------|------|
| `dashboard.html` | 대시보드 전체 (HTML+CSS+JS 인라인) |

별도 CSS, JS, 이미지 파일을 만들지 않는다. Chart.js는 CDN으로 로드한다.

## 대시보드 구현 사양

### 레이아웃

```
┌──────────────────────────────────────────────────┐
│  디지털 고도화 WBS 대시보드          [날짜선택]    │
├──────────────────────────────────────────────────┤
│  [전체현황] [일별실적] [추이차트] [태스크목록]      │
├──────────────────────────────────────────────────┤
│                                                  │
│  (선택된 탭의 콘텐츠)                              │
│                                                  │
└──────────────────────────────────────────────────┘
```

### 탭 1: 전체 현황
- **전체 진척률**: 큰 숫자 + 원형 프로그레스
- **페이즈별 진척률**: 가로 프로그레스 바 (분석/설계/개발/테스트/이행)
- **상태 분포**: 도넛 차트 (대기/진행중/완료/지연/보류)
- **요약 카드**: 총 태스크 수, 완료 수, 지연 수, 금일 변동 수

### 탭 2: 일별 실적 (핵심 뷰)
- **날짜 선택기**: `<input type="date">`, 기본값 오늘
- **실적 테이블**:

| ID | 페이즈 | 태스크명 | 담당자 | 실적(%) | 전일비 | 상태 | 비고 |
|----|--------|---------|--------|---------|--------|------|------|

- **색상 코딩**: 지연=빨강 배경, 완료=초록 배경, 보류=주황 배경
- **필터**: 페이즈별, 상태별, 담당자별 드롭다운

### 탭 3: 추이 차트
- **기간 선택**: 시작일/종료일
- **라인 차트** (Chart.js):
  - 전체 진척률 추이 (굵은 선)
  - 페이즈별 추이 (얇은 선, 토글 가능)
- **일별 변동량 바 차트**: 각 날짜별 진척률 증감

### 탭 4: 태스크 목록
- 전체 태스크 테이블 (정렬/필터 가능)
- 행 클릭 시 해당 태스크의 `daily_log` 히스토리를 모달/확장 행으로 표시
- 검색 기능 (태스크명, ID, 담당자)

## 데이터 로딩 로직 (JavaScript)

```javascript
async function loadData() {
  try {
    const res = await fetch('wbs_data.json');
    if (!res.ok) throw new Error('데이터 파일을 찾을 수 없습니다.');
    return await res.json();
  } catch (e) {
    showError(e.message);
    return null;
  }
}
```

## 진척률 계산 (JavaScript)

```javascript
// 특정 날짜의 태스크 진척률
function getTaskPercent(task, date) {
  const logs = task.daily_log
    .filter(l => l.date <= date)
    .sort((a, b) => b.date.localeCompare(a.date));
  return logs.length > 0 ? logs[0].percent : 0;
}

// 가중 평균 진척률
function weightedAverage(tasks, date) {
  let sumWP = 0, sumW = 0;
  tasks.forEach(t => {
    const p = getTaskPercent(t, date);
    sumWP += p * (t.weight || 1);
    sumW += (t.weight || 1);
  });
  return sumW > 0 ? (sumWP / sumW).toFixed(1) : 0;
}
```

## 서버 실행

대시보드 생성 후 자동으로 서버를 시작한다:

```bash
cd /프로젝트루트 && python -m http.server 8080
```

사용자에게 `http://localhost:8080/dashboard.html` 접속 안내.

포트 충돌 시 8081, 8082 순으로 시도.

## 스타일

- 폰트: system-ui (시스템 기본)
- 색상 팔레트:
  - Primary: #1976D2 (파란색)
  - 완료: #4CAF50, 진행중: #2196F3, 지연: #F44336, 대기: #9E9E9E, 보류: #FF9800
- 테이블: 줄무늬(striped), hover 하이라이트
- 반응형: min-width 320px 지원
