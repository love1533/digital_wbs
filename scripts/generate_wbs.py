#!/usr/bin/env python3
"""
JIRA Cloud → WBS HTML Generator
────────────────────────────────────────────────────────────
지원 프로젝트 유형:
  • JIRA Software  : Epic → Phase, Story/Task → WBS 작업
  • JIRA Work Management (Core) : 최상위 Task → Phase, 하위 Task → WBS 작업

필수 환경변수:
  JIRA_URL          예) https://gcgfmobile.atlassian.net
  JIRA_EMAIL        JIRA 계정 이메일
  JIRA_API_TOKEN    JIRA API 토큰
  JIRA_PROJECT_KEY  프로젝트 키  예) GCGF0323
  WBS_PASSWORD      HTML 접근 비밀번호 (기본값: wbs2026)

선택 환경변수:
  WBS_OUTPUT        출력 경로 (기본값: docs/index.html)
  WBS_TITLE         페이지 제목 (기본값: 프로젝트 WBS)
"""

import os
import sys
import json
import hashlib
from datetime import datetime

try:
    import requests
    from requests.auth import HTTPBasicAuth
except ImportError:
    print("❌ requests 모듈이 필요합니다: pip install requests")
    sys.exit(1)

# ── Configuration ─────────────────────────────────────────────────────────────
JIRA_URL     = os.environ.get("JIRA_URL", "").rstrip("/")
JIRA_EMAIL   = os.environ.get("JIRA_EMAIL", "")
JIRA_TOKEN   = os.environ.get("JIRA_API_TOKEN", "")
PROJECT_KEY  = os.environ.get("JIRA_PROJECT_KEY", "")
WBS_PASSWORD = os.environ.get("WBS_PASSWORD", "wbs2026")
OUTPUT_PATH  = os.environ.get("WBS_OUTPUT", "docs/index.html")
WBS_TITLE    = os.environ.get("WBS_TITLE", "프로젝트 WBS")

# 업무영역 자동 감지 키워드
AREA_KEYWORDS = {
    "이지원": ["이지원", "ezwon", "document", "문서", "전자결재", "결재", "기안"],
    "사이버": ["사이버", "cyber", "security", "보안", "인증", "취약점", "iam"],
    "콜센터": ["콜센터", "callcenter", "call", "cti", "ivr", "상담", "녹취"],
    "인프라": ["인프라", "infra", "infrastructure", "server", "서버", "네트워크", "db", "배포"],
}

JIRA_FIELDS = [
    "summary", "status", "priority", "assignee", "duedate",
    "labels", "components", "subtasks", "parent",
    "customfield_10014",   # Epic Link (classic Software)
    "customfield_10016",   # Story Points
    "issuetype", "created", "updated",
]


# ── Helpers ────────────────────────────────────────────────────────────────────
def detect_area(components: list, labels: list, summary: str) -> str:
    texts = [s.lower() for s in components + labels + [summary]]
    for area, keywords in AREA_KEYWORDS.items():
        if any(kw in text for kw in keywords for text in texts):
            return area
    return "PMO"


def map_status(jira_status: str) -> str:
    s = jira_status.lower()
    if any(x in s for x in ["done", "complete", "closed", "resolved", "완료", "종료"]):
        return "done"
    if any(x in s for x in ["review", "qa", "test", "검토", "리뷰", "테스트", "in review"]):
        return "review"
    if any(x in s for x in ["progress", "develop", "in_progress", "진행", "개발", "in progress"]):
        return "doing"
    return "todo"


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ── JIRA API Client ────────────────────────────────────────────────────────────
class JiraClient:
    def __init__(self):
        if not all([JIRA_URL, JIRA_EMAIL, JIRA_TOKEN, PROJECT_KEY]):
            raise ValueError(
                "JIRA_URL / JIRA_EMAIL / JIRA_API_TOKEN / JIRA_PROJECT_KEY "
                "환경변수를 모두 설정해주세요."
            )
        self.auth    = HTTPBasicAuth(JIRA_EMAIL, JIRA_TOKEN)
        self.base    = f"{JIRA_URL}/rest/api/3"
        self.headers = {"Accept": "application/json"}

    def _get(self, path: str, params: dict = None) -> dict:
        r = requests.get(
            f"{self.base}/{path}",
            auth=self.auth, headers=self.headers, params=params, timeout=30,
        )
        r.raise_for_status()
        return r.json()

    def search(self, jql: str, max_results: int = 1000) -> list:
        issues, start = [], 0
        while True:
            batch = min(100, max_results - len(issues))
            data  = self._get("search", {
                "jql": jql, "startAt": start, "maxResults": batch,
                "fields": ",".join(JIRA_FIELDS),
            })
            issues.extend(data["issues"])
            if not data["issues"] or len(issues) >= data["total"] or len(issues) >= max_results:
                break
            start += len(data["issues"])
        return issues

    def project_type(self) -> str:
        """'software' 또는 'business' (Work Management) 반환"""
        try:
            data = self._get(f"project/{PROJECT_KEY}")
            return data.get("projectTypeKey", "business")
        except Exception:
            return "business"


# ── Task 객체 생성 헬퍼 ────────────────────────────────────────────────────────
def make_task(issue: dict, phase_idx: int, task_idx: int) -> dict:
    sf      = issue["fields"]
    comps   = [c["name"] for c in (sf.get("components") or [])]
    labels  = sf.get("labels") or []
    subs    = []
    for st in (sf.get("subtasks") or []):
        stf = st.get("fields") or {}
        subs.append({
            "key":    st["key"],
            "name":   stf.get("summary", ""),
            "status": map_status((stf.get("status") or {}).get("name", "To Do")),
        })
    return {
        "id":       f"{phase_idx}.{task_idx}",
        "jiraKey":  issue["key"],
        "jiraUrl":  f"{JIRA_URL}/browse/{issue['key']}",
        "name":     sf.get("summary", "Unknown"),
        "area":     detect_area(comps, labels, sf.get("summary", "")),
        "status":   map_status(sf["status"]["name"]),
        "assignee": (sf.get("assignee") or {}).get("displayName", ""),
        "duedate":  sf.get("duedate") or "",
        "priority": (sf.get("priority") or {}).get("name", "Medium"),
        "labels":   labels[:5],
        "subs":     subs,
    }


# ── JIRA Software (Epic 기반) ──────────────────────────────────────────────────
def build_phases_software(client: JiraClient) -> list:
    epics = client.search(
        f'project = "{PROJECT_KEY}" AND issuetype = Epic ORDER BY rank ASC, created ASC'
    )
    print(f"  • 에픽(Phase): {len(epics)}개")

    all_issues = client.search(
        f'project = "{PROJECT_KEY}" AND issuetype not in (Epic, "Sub-task") '
        f'ORDER BY rank ASC, created ASC'
    )
    print(f"  • 이슈: {len(all_issues)}개")

    epic_map: dict = {e["key"]: [] for e in epics}
    unassigned = []
    for issue in all_issues:
        f = issue["fields"]
        epic_key = f.get("customfield_10014")
        if not epic_key:
            parent = f.get("parent") or {}
            if (parent.get("fields") or {}).get("issuetype", {}).get("name") == "Epic":
                epic_key = parent.get("key")
        (epic_map[epic_key] if epic_key in epic_map else unassigned).append(issue)

    phases = []
    for i, epic in enumerate(epics):
        ef    = epic["fields"]
        tasks = [make_task(iss, i + 1, j + 1) for j, iss in enumerate(epic_map.get(epic["key"], []))]
        phases.append(_phase_obj(f"P{i+1}", ef.get("summary", "Unknown Epic"),
                                 epic["key"], ef["status"]["name"],
                                 ef.get("duedate") or "", tasks))

    if unassigned:
        tasks = [make_task(iss, 0, j + 1) for j, iss in enumerate(unassigned)]
        phases.insert(0, _phase_obj("P0", "미분류 이슈", "", "To Do", "", tasks))

    return phases


# ── JIRA Work Management (Task 계층 기반) ─────────────────────────────────────
def build_phases_workmanagement(client: JiraClient) -> list:
    """
    최상위 Task (parent 없음) → Phase
    하위 Task / Subtask         → WBS 작업
    """
    all_issues = client.search(
        f'project = "{PROJECT_KEY}" ORDER BY created ASC'
    )
    print(f"  • 전체 이슈: {len(all_issues)}개")

    # key → issue 맵
    issue_map = {iss["key"]: iss for iss in all_issues}

    # 부모-자식 분류
    top_level = []
    children: dict = {}   # parent_key → [child_issue, ...]

    for issue in all_issues:
        f          = issue["fields"]
        itype      = (f.get("issuetype") or {}).get("name", "").lower()
        parent_obj = f.get("parent")

        if parent_obj:
            pk = parent_obj["key"]
            children.setdefault(pk, []).append(issue)
        else:
            # subtask 타입이면 건너뜀 (부모 없는 subtask는 비정상)
            if "sub" not in itype:
                top_level.append(issue)

    print(f"  • 최상위 Task(Phase): {len(top_level)}개")

    phases = []
    for i, parent in enumerate(top_level):
        pf       = parent["fields"]
        kids     = children.get(parent["key"], [])
        tasks    = [make_task(child, i + 1, j + 1) for j, child in enumerate(kids)]

        # 자식이 없는 최상위 Task는 자기 자신을 작업으로도 등록
        if not tasks:
            tasks = [make_task(parent, i + 1, 1)]

        phases.append(_phase_obj(
            f"P{i+1}",
            pf.get("summary", "Unknown"),
            parent["key"],
            pf["status"]["name"],
            pf.get("duedate") or "",
            tasks,
        ))

    # 고아 이슈 (어느 최상위 Task의 자식도 아닌 것)
    top_keys     = {p["key"] for p in top_level}
    child_keys   = {iss["key"] for kids in children.values() for iss in kids}
    orphan_keys  = set(issue_map) - top_keys - child_keys
    orphans      = [issue_map[k] for k in orphan_keys]

    if orphans:
        tasks = [make_task(iss, 0, j + 1) for j, iss in enumerate(orphans)]
        phases.insert(0, _phase_obj("P0", "기타 이슈", "", "To Do", "", tasks))

    return phases


def _phase_obj(pid, name, jira_key, status_name, duedate, tasks) -> dict:
    done_c = sum(1 for t in tasks if t["status"] == "done")
    return {
        "id":        pid,
        "name":      name,
        "jiraKey":   jira_key,
        "jiraUrl":   f"{JIRA_URL}/browse/{jira_key}" if jira_key else "",
        "status":    map_status(status_name),
        "duedate":   duedate,
        "tasks":     tasks,
        "taskCount": len(tasks),
        "doneCount": done_c,
    }


# ── 진입점: 프로젝트 유형 자동 감지 ──────────────────────────────────────────
def build_phases(client: JiraClient) -> list:
    ptype = client.project_type()
    print(f"  • 프로젝트 유형: {ptype}")

    if ptype == "software":
        # JIRA Software: Epic 존재 여부로 2차 판단
        epics = client.search(
            f'project = "{PROJECT_KEY}" AND issuetype = Epic', max_results=1
        )
        if epics:
            return build_phases_software(client)

    # JIRA Work Management 또는 Epic 없는 Software 프로젝트
    return build_phases_workmanagement(client)


# ── HTML 생성 ──────────────────────────────────────────────────────────────────
def build_html(phases: list, ptype: str = "business") -> str:
    pw_hash     = sha256_hex(WBS_PASSWORD)
    last_update = datetime.now().strftime("%Y-%m-%d %H:%M")
    total       = sum(p["taskCount"] for p in phases)
    done_total  = sum(p["doneCount"]  for p in phases)
    doing_total = sum(1 for p in phases for t in p["tasks"] if t["status"] == "doing")
    phases_json = json.dumps(phases, ensure_ascii=False)
    pct         = round(done_total / total * 100) if total else 0

    # JIRA 보드 링크 (프로젝트 유형별)
    if ptype == "software":
        board_url = f"{JIRA_URL}/jira/software/projects/{PROJECT_KEY}/boards"
    else:
        board_url = f"{JIRA_URL}/jira/core/projects/{PROJECT_KEY}/board"

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>{WBS_TITLE}</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'Segoe UI',system-ui,sans-serif;background:#0f172a;color:#e2e8f0;font-size:13px}}

/* ─ Overlay ─ */
#overlay{{position:fixed;inset:0;background:#0a0f1e;display:flex;align-items:center;justify-content:center;z-index:9999}}
.gate{{background:#1e293b;border:1px solid #334155;border-radius:1rem;padding:2.5rem 3rem;width:360px;text-align:center;box-shadow:0 25px 50px rgba(0,0,0,.6)}}
.gate h2{{font-size:1.2rem;color:#38bdf8;margin-bottom:.4rem}}
.gate p{{font-size:.78rem;color:#475569;margin-bottom:1.5rem}}
.gate input{{width:100%;padding:.7rem 1rem;background:#0f172a;border:1px solid #334155;border-radius:.5rem;color:#e2e8f0;font-size:.9rem;outline:none;margin-bottom:.85rem;transition:border .15s}}
.gate input:focus{{border-color:#38bdf8;box-shadow:0 0 0 3px rgba(56,189,248,.1)}}
.gate button{{width:100%;padding:.72rem;background:#1d4ed8;color:#fff;border:none;border-radius:.5rem;font-size:.9rem;cursor:pointer;font-weight:600;transition:background .15s}}
.gate button:hover{{background:#2563eb}}
.gate .err{{font-size:.72rem;color:#f87171;margin-top:.6rem;min-height:1.1rem}}
.gate .lock{{font-size:2.2rem;margin-bottom:.85rem}}
.gate .hint{{font-size:.65rem;color:#1e3a5f;margin-top:.5rem}}

/* ─ Layout ─ */
#main{{display:none}}
header{{background:#1e293b;border-bottom:1px solid #334155;padding:.8rem 1.5rem;display:flex;align-items:center;gap:.55rem;flex-wrap:wrap}}
header h1{{font-size:1.1rem;font-weight:700;color:#38bdf8;flex:1;min-width:0}}
.badge{{font-size:.63rem;padding:.13rem .5rem;border-radius:9999px;border:1px solid;white-space:nowrap}}
.b-blue{{background:#1e3a5f;color:#38bdf8;border-color:#1d4ed8}}
.b-green{{background:#052e16;color:#4ade80;border-color:#166534}}
.b-amber{{background:#2d1a00;color:#fbbf24;border-color:#92400e}}
.sync-info{{font-size:.63rem;color:#475569;display:flex;align-items:center;gap:.35rem}}
.dot{{width:6px;height:6px;border-radius:50%;background:#4ade80;animation:pulse 2s infinite;flex-shrink:0}}
@keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:.3}}}}
.jira-link{{display:inline-flex;align-items:center;gap:.3rem;color:#94a3b8;font-size:.68rem;text-decoration:none;border:1px solid #334155;padding:.2rem .5rem;border-radius:.3rem;transition:all .15s;white-space:nowrap}}
.jira-link:hover{{color:#38bdf8;border-color:#38bdf8}}
.jira-logo{{fill:currentColor}}

/* ─ Stats ─ */
.stats{{display:grid;grid-template-columns:repeat(5,1fr);gap:.55rem;padding:.75rem 1.5rem}}
@media(max-width:640px){{.stats{{grid-template-columns:repeat(3,1fr)}}}}
.sc{{background:#1e293b;border:1px solid #334155;border-radius:.45rem;padding:.55rem .75rem}}
.sc-l{{font-size:.58rem;color:#475569;text-transform:uppercase;letter-spacing:.04em;margin-bottom:.2rem}}
.sc-v{{font-size:1.1rem;font-weight:700;color:#38bdf8}}

/* ─ Progress bar ─ */
.progress-bar-wrap{{padding:.5rem 1.5rem .1rem;display:flex;align-items:center;gap:.75rem}}
.pbar-full{{flex:1;height:6px;background:#1e293b;border-radius:3px;overflow:hidden}}
.pfill-full{{height:100%;background:linear-gradient(90deg,#166534,#22c55e,#38bdf8);border-radius:3px;transition:width .5s}}
.pbar-label{{font-size:.7rem;color:#64748b;white-space:nowrap}}

/* ─ Toolbar ─ */
.toolbar{{background:#1a2332;border-bottom:1px solid #334155;padding:.45rem 1.5rem;display:flex;gap:.38rem;flex-wrap:wrap;align-items:center}}
.tb{{background:#0f172a;color:#94a3b8;border:1px solid #334155;border-radius:.25rem;padding:.22rem .5rem;font-size:.68rem;cursor:pointer;transition:all .15s}}
.tb:hover,.tb.on{{color:#38bdf8;border-color:#38bdf8;background:#1e3a5f}}
.sep{{width:1px;height:13px;background:#334155;margin:0 .1rem}}

/* ─ Phase blocks ─ */
.wbs{{padding:.75rem 1.5rem 2.5rem}}
.ph{{background:#1e293b;border:1px solid #334155;border-radius:.55rem;margin-bottom:.65rem;overflow:hidden}}
.ph-hdr{{display:flex;align-items:center;gap:.55rem;padding:.65rem .9rem;cursor:pointer;user-select:none;transition:background .15s}}
.ph-hdr:hover{{background:#263347}}
.chv{{font-size:.6rem;color:#64748b;transition:transform .2s;width:11px;flex-shrink:0}}
.chv.o{{transform:rotate(90deg)}}
.ph-id{{font-size:.63rem;font-weight:700;padding:.1rem .38rem;border-radius:.2rem;min-width:2rem;text-align:center;flex-shrink:0}}
.ph-name{{font-weight:600;font-size:.83rem;flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.ph-meta{{display:flex;align-items:center;gap:.4rem;flex-shrink:0}}
.mbar{{width:44px;height:3px;background:#0f172a;border-radius:2px;overflow:hidden}}
.mfill{{height:100%;border-radius:2px}}

/* ─ Task rows ─ */
.rows{{border-top:1px solid #1a2332}}
.tr{{display:flex;align-items:flex-start;gap:.45rem;padding:.38rem .65rem;margin:.07rem .25rem;border-radius:.3rem;transition:background .1s}}
.tr:hover{{background:#1a2540}}
.status-dot{{width:7px;height:7px;border-radius:50%;flex-shrink:0;margin-top:.38rem}}
.s-done  {{background:#22c55e}}
.s-doing {{background:#38bdf8;animation:pulse 1.8s infinite}}
.s-review{{background:#fbbf24}}
.s-todo  {{background:#334155}}
.tbody{{flex:1;min-width:0}}
.tr1{{display:flex;align-items:center;gap:.38rem;flex-wrap:wrap}}
.tid{{color:#334155;font-size:.6rem;font-family:monospace;flex-shrink:0;min-width:2.8rem}}
.tkey{{font-size:.63rem;font-family:monospace;color:#475569;text-decoration:none;flex-shrink:0;transition:color .15s}}
.tkey:hover{{color:#38bdf8;text-decoration:underline}}
.tname{{font-size:.78rem;color:#cbd5e1;flex:1;min-width:0}}
.tname.done{{text-decoration:line-through;color:#475569}}
.area-tag{{font-size:.57rem;padding:.06rem .3rem;border-radius:.2rem;font-weight:600;flex-shrink:0;border:1px solid;white-space:nowrap}}
.stag{{font-size:.57rem;padding:.06rem .3rem;border-radius:.2rem;font-weight:600;flex-shrink:0;white-space:nowrap}}
.stag-done  {{background:#052e16;color:#4ade80}}
.stag-doing {{background:#1e3a5f;color:#38bdf8}}
.stag-review{{background:#2d1a00;color:#fbbf24}}
.stag-todo  {{background:#1a1a2e;color:#475569}}
.tassign{{font-size:.6rem;color:#334155;flex-shrink:0}}
.tdate  {{font-size:.6rem;color:#334155;flex-shrink:0;margin-left:auto}}
.subs{{margin:.18rem 0 .05rem 1rem;border-left:1px dashed #1e293b;padding-left:.55rem}}
.sub{{display:flex;align-items:center;gap:.3rem;padding:.13rem .1rem;font-size:.68rem;color:#475569}}
.sdot{{width:4px;height:4px;border-radius:50%;background:#334155;flex-shrink:0}}
.sdot.done{{background:#22c55e}}.sdot.doing{{background:#38bdf8}}
.sub a{{color:#475569;font-size:.6rem;font-family:monospace;text-decoration:none}}
.sub a:hover{{color:#38bdf8}}
.empty-msg{{color:#334155;text-align:center;padding:2rem;font-size:.8rem}}

/* ─ Area colors ─ */
.a-이지원{{background:#1a2d4a;color:#60a5fa;border-color:#1e3a5f}}
.a-사이버{{background:#2d1a2d;color:#c084fc;border-color:#4c1d95}}
.a-콜센터{{background:#1a2d2d;color:#34d399;border-color:#065f46}}
.a-인프라{{background:#2d2a1a;color:#fbbf24;border-color:#92400e}}
.a-PMO  {{background:#1a1a2d;color:#94a3b8;border-color:#334155}}
</style>
</head>
<body>

<!-- ═══ 비밀번호 오버레이 ═══ -->
<div id="overlay">
  <div class="gate">
    <div class="lock">🔒</div>
    <h2>{WBS_TITLE}</h2>
    <p>접근하려면 비밀번호를 입력하세요</p>
    <input type="password" id="pw" placeholder="비밀번호 입력"
           onkeydown="if(event.key==='Enter')doAuth()"/>
    <button onclick="doAuth()">확인</button>
    <div class="err" id="err"></div>
    <div class="hint">JIRA 데이터 자동 동기화 · 최종: {last_update}</div>
  </div>
</div>

<!-- ═══ 메인 콘텐츠 ═══ -->
<div id="main">
<header>
  <h1>📋 {WBS_TITLE}</h1>
  <span class="badge b-blue">{PROJECT_KEY}</span>
  <span class="badge b-green">● {done_total}/{total} 완료</span>
  <span class="badge b-amber">{pct}%</span>
  <span class="sync-info"><span class="dot"></span>동기화: {last_update}</span>
  <a class="jira-link" href="{board_url}" target="_blank">
    <svg class="jira-logo" width="11" height="11" viewBox="0 0 24 24">
      <path d="M11.571 11.513H0a5.218 5.218 0 0 0 5.232 5.215h2.13v2.058A5.215 5.215 0 0 0 12.575 24V12.518a1.005 1.005 0 0 0-1.004-1.005zm5.723-5.756H5.757a5.215 5.215 0 0 0 5.214 5.214h2.129v2.058a5.218 5.218 0 0 0 5.215 5.214V6.762a1.005 1.005 0 0 0-1.021-1.005zM23.013 0H11.442a5.215 5.215 0 0 0 5.215 5.215h2.129v2.058A5.215 5.215 0 0 0 24 12.487V1.005A1.005 1.005 0 0 0 23.013 0z"/>
    </svg>
    JIRA 보드
  </a>
</header>

<div class="stats">
  <div class="sc"><div class="sc-l">전체 이슈</div><div class="sc-v">{total}</div></div>
  <div class="sc"><div class="sc-l">완료</div><div class="sc-v" style="color:#4ade80">{done_total}</div></div>
  <div class="sc"><div class="sc-l">진행중</div><div class="sc-v" style="color:#38bdf8">{doing_total}</div></div>
  <div class="sc"><div class="sc-l">Phase 수</div><div class="sc-v" style="color:#c084fc">{len(phases)}</div></div>
  <div class="sc"><div class="sc-l">달성률</div><div class="sc-v" style="color:#fbbf24">{pct}%</div></div>
</div>

<div class="progress-bar-wrap">
  <div class="pbar-full"><div class="pfill-full" style="width:{pct}%"></div></div>
  <span class="pbar-label">{done_total} / {total} tasks · {pct}%</span>
</div>

<div class="toolbar">
  <button class="tb on" id="f-all"    onclick="setF('all',this)">전체</button>
  <button class="tb"    id="f-todo"   onclick="setF('todo',this)">대기</button>
  <button class="tb"    id="f-doing"  onclick="setF('doing',this)">진행중</button>
  <button class="tb"    id="f-review" onclick="setF('review',this)">검토중</button>
  <button class="tb"    id="f-done"   onclick="setF('done',this)">완료</button>
  <div class="sep"></div>
  <button class="tb" onclick="expAll()">전체 펼치기</button>
  <button class="tb" onclick="colAll()">전체 접기</button>
</div>

<div class="wbs" id="wbs"></div>
</div>

<script>
const PW_HASH   = "{pw_hash}";
const PHASES    = {phases_json};
const JIRA_BASE = "{JIRA_URL}";
const AREA_CLS  = {{'이지원':'a-이지원','사이버':'a-사이버','콜센터':'a-콜센터','인프라':'a-인프라','PMO':'a-PMO'}};
const SL = {{done:'완료',doing:'진행중',review:'검토중',todo:'대기'}};
const SC = {{done:'stag-done',doing:'stag-doing',review:'stag-review',todo:'stag-todo'}};

// ─ Auth ─────────────────────────────────────────────────────
async function sha256(msg) {{
  const buf  = new TextEncoder().encode(msg);
  const hash = await crypto.subtle.digest('SHA-256', buf);
  return Array.from(new Uint8Array(hash)).map(b=>b.toString(16).padStart(2,'0')).join('');
}}
async function doAuth() {{
  const v = document.getElementById('pw').value;
  if (!v) {{ showErr('비밀번호를 입력해주세요'); return; }}
  const h = await sha256(v);
  if (h === PW_HASH) {{
    sessionStorage.setItem('wbs_ok','1');
    document.getElementById('overlay').style.display = 'none';
    document.getElementById('main').style.display    = 'block';
  }} else {{
    showErr('비밀번호가 올바르지 않습니다');
    document.getElementById('pw').value = '';
    document.getElementById('pw').focus();
  }}
}}
function showErr(m) {{
  const el = document.getElementById('err');
  el.textContent = m;
  setTimeout(()=>el.textContent='', 2500);
}}
if (sessionStorage.getItem('wbs_ok')==='1') {{
  document.getElementById('overlay').style.display = 'none';
  document.getElementById('main').style.display    = 'block';
}}
document.getElementById('pw').focus();

// ─ Render ────────────────────────────────────────────────────
let curF = 'all';
const open = {{}};
PHASES.forEach(p => open[p.id] = true);

function setF(f, btn) {{
  curF = f;
  ['all','todo','doing','review','done'].forEach(x=>
    document.getElementById('f-'+x)?.classList.toggle('on', x===f));
  render();
}}
function expAll() {{ PHASES.forEach(p=>open[p.id]=true);  render(); }}
function colAll() {{ PHASES.forEach(p=>open[p.id]=false); render(); }}
function tog(id)  {{ open[id]=!open[id]; render(); }}

function render() {{
  let html = '';
  PHASES.forEach(p => {{
    const tasks = curF==='all' ? p.tasks : p.tasks.filter(t=>t.status===curF);
    if (!tasks.length && curF!=='all') return;

    const pct2  = p.taskCount ? Math.round(p.doneCount/p.taskCount*100) : 0;
    const isOpen = open[p.id];

    html += `<div class="ph">
      <div class="ph-hdr" onclick="tog('${{p.id}}')">
        <span class="chv ${{isOpen?'o':''}}">▶</span>
        <span class="ph-id" style="background:#1e3a5f;color:#38bdf8">${{p.id}}</span>
        <span class="ph-name">${{p.name}}</span>
        ${{p.jiraKey ? `<a class="tkey" href="${{p.jiraUrl}}" target="_blank"
              onclick="event.stopPropagation()">${{p.jiraKey}}</a>` : ''}}
        <div class="ph-meta">
          ${{p.duedate ? `<span style="font-size:.6rem;color:#334155">🗓 ${{p.duedate}}</span>` : ''}}
          <span style="font-size:.63rem;color:#475569">${{p.doneCount}}/${{p.taskCount}}</span>
          <div class="mbar"><div class="mfill" style="width:${{pct2}}%;background:#38bdf8"></div></div>
        </div>
      </div>`;

    if (isOpen) {{
      html += `<div class="rows">`;
      if (!tasks.length) {{
        html += `<div class="empty-msg">이슈 없음</div>`;
      }} else {{
        tasks.forEach(t => {{
          const ac    = AREA_CLS[t.area] || 'a-PMO';
          const subs  = t.subs || [];
          const subsH = subs.length ? `<div class="subs">` + subs.map(s=>`
            <div class="sub">
              <div class="sdot ${{s.status}}"></div>
              <a href="${{JIRA_BASE}}/browse/${{s.key}}" target="_blank">${{s.key}}</a>
              <span>${{s.name}}</span>
            </div>`).join('') + `</div>` : '';

          html += `<div class="tr">
            <div class="status-dot s-${{t.status}}"></div>
            <div class="tbody">
              <div class="tr1">
                <span class="tid">${{t.id}}</span>
                <a class="tkey" href="${{t.jiraUrl}}" target="_blank">${{t.jiraKey}}</a>
                <span class="tname${{t.status==='done'?' done':''}}">${{t.name}}</span>
                <span class="area-tag ${{ac}}">${{t.area}}</span>
                <span class="stag ${{SC[t.status]}}">${{SL[t.status]}}</span>
                ${{t.assignee ? `<span class="tassign">👤 ${{t.assignee}}</span>` : ''}}
                ${{t.duedate  ? `<span class="tdate">🗓 ${{t.duedate}}</span>` : ''}}
              </div>
              ${{subsH}}
            </div>
          </div>`;
        }});
      }}
      html += `</div>`;
    }}
    html += `</div>`;
  }});

  document.getElementById('wbs').innerHTML =
    html || `<div class="empty-msg">조건에 맞는 이슈가 없습니다</div>`;
}}

render();
</script>
</body>
</html>"""


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    client = JiraClient()
    ptype  = client.project_type()
    print(f"📡 JIRA [{PROJECT_KEY}] 데이터 수집 중... (유형: {ptype})")

    phases = build_phases(client)

    total = sum(p["taskCount"] for p in phases)
    done  = sum(p["doneCount"]  for p in phases)
    print(f"✅ 수집 완료: Phase {len(phases)}개 / 이슈 {total}개 (완료 {done}개)")

    html = build_html(phases, ptype)
    os.makedirs(os.path.dirname(OUTPUT_PATH) or ".", exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"📄 생성: {OUTPUT_PATH}  ({len(html):,} bytes)")


if __name__ == "__main__":
    main()
