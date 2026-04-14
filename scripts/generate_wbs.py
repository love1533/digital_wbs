#!/usr/bin/env python3
"""
JIRA Cloud → WBS Gantt HTML Generator  (v3)
────────────────────────────────────────────────────────────
지원 프로젝트 유형:
  • JIRA Software  : Epic → Phase, Story/Task → WBS Task
  • JIRA Work Management (Core) : 최상위 Task → Phase, 하위 Task → WBS Task

필수 환경변수:
  JIRA_URL          예) https://gcgfmobile.atlassian.net
  JIRA_EMAIL        JIRA 계정 이메일
  JIRA_API_TOKEN    JIRA API 토큰
  JIRA_PROJECT_KEY  프로젝트 키  예) GCGF0323
  WBS_PASSWORD      HTML 접근 비밀번호 (기본값: wbs2026)

선택 환경변수:
  WBS_OUTPUT           출력 경로   (기본: docs/index.html)
  WBS_TITLE            페이지 제목 (기본: 프로젝트 WBS)
  WBS_PROJECT_NAME     로그인 화면·헤더 제목 (기본: 경기신용보증재단 디지털고도화)
  WBS_GATE_SUB         로그인 화면 부가 문구 (기본: 이 페이지는 디지털고도화 프로젝트 팀원 전용입니다)
  PROJECT_START_DATE   프로젝트 시작일 YYYY-MM-DD (기본: 2026-03-23)
  TOTAL_WEEKS          총 주차 수  (기본: 32)
"""

import os, sys, json, hashlib, re
from datetime import datetime, timedelta

# 프로젝트 루트에서 .env 로드 (.env 값이 우선)
def _load_dotenv():
    for d in [os.path.dirname(os.path.dirname(os.path.abspath(__file__))), os.getcwd()]:
        env_path = os.path.join(d, ".env")
        if os.path.isfile(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, _, v = line.partition("=")
                        k = k.strip()
                        v = v.strip().strip('"').strip("'")
                        if "#" in v:
                            v = v.split("#")[0].strip()
                        if k:
                            os.environ[k] = v
            break
_load_dotenv()

try:
    import requests
    from requests.auth import HTTPBasicAuth
except ImportError:
    print("❌ requests 모듈이 필요합니다: pip install requests")
    sys.exit(1)

# ── 환경변수 ──────────────────────────────────────────────────────────────────
JIRA_URL        = os.environ.get("JIRA_URL", "").rstrip("/")
JIRA_EMAIL      = os.environ.get("JIRA_EMAIL", "")
JIRA_TOKEN      = os.environ.get("JIRA_API_TOKEN", "")
PROJECT_KEY     = os.environ.get("JIRA_PROJECT_KEY", "")
WBS_PASSWORD       = os.environ.get("WBS_PASSWORD", "")
# GitHub Actions vars.* 는 미설정 시 빈 문자열("")로 들어오므로 `or` 로 기본값 대체
OUTPUT_PATH        = os.environ.get("WBS_OUTPUT") or "docs/index.html"
WBS_TITLE          = os.environ.get("WBS_TITLE") or "프로젝트 WBS"
WBS_PROJECT_NAME   = os.environ.get("WBS_PROJECT_NAME") or "경기신용보증재단 디지털고도화"
WBS_GATE_SUB       = os.environ.get("WBS_GATE_SUB") or "이 페이지는 디지털고도화 프로젝트 팀원 전용입니다"
PROJECT_START_S    = os.environ.get("PROJECT_START_DATE") or "2026-03-23"
TOTAL_WEEKS        = int(os.environ.get("TOTAL_WEEKS") or "32")
SNAPSHOT_DIR       = os.environ.get("SNAPSHOT_DIR") or "docs/data/snapshots"
HISTORY_PATH       = os.environ.get("HISTORY_OUTPUT") or "docs/history.html"

try:
    PROJECT_START = datetime.strptime(PROJECT_START_S, "%Y-%m-%d")
except ValueError:
    print(f"⚠ PROJECT_START_DATE 형식 오류({PROJECT_START_S}), 2026-03-23 사용")
    PROJECT_START = datetime(2026, 3, 23)

# 업무영역 감지 키워드
AREA_KEYWORDS = {
    "이지원": [
        "이지원", "ezwon", "document", "문서", "전자결재", "결재", "기안", "모바일",
        "마이다스", "midas", "법인", "공동대표", "ocr", "챗봇", "chatbot",
        "팩토리", "상품", "app고도화", "앱", "ai", "고도화",
    ],
    "인터넷웹": [
        "사이버", "cyber", "security", "보안", "인증", "취약점", "iam", "방화벽",
        "사이버보증", "보증", "인터넷", "웹", "internet", "web",
    ],
    "콜센터": [
        "콜센터", "callcenter", "call", "cti", "ivr", "상담", "녹취",
        "ars", "보이는ars",
    ],
    "인프라": [
        "인프라", "infra", "infrastructure", "server", "서버", "네트워크", "db",
        "배포", "형상관리", "소스코드", "응답시간", "자원사용률", "성능",
    ],
}

# 시작일 커스텀 필드 후보 (우선순위 순)
START_DATE_CANDIDATES = [
    "startdate",          # Work Management 표준
    "customfield_10015",  # Software Start Date (일반)
    "customfield_10016",  # 일부 인스턴스
    "customfield_10032",  # BigGantt 흔한 필드
    "customfield_10116",
    "customfield_10133",
    "customfield_10200",
    "customfield_10300",
]

# JIRA 기본 필드 목록 (검색 시 사용)
JIRA_FIELDS = [
    "summary", "status", "priority", "assignee", "duedate",
    "labels", "components", "subtasks", "parent",
    "customfield_10014",  # Epic Link (classic Software)
    "customfield_10015",  # Start Date
    "customfield_10020",  # Sprint
    "issuetype", "created", "updated",
]


# ── 유틸 ──────────────────────────────────────────────────────────────────────
def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def detect_area(components: list, labels: list, summary: str) -> str:
    texts = [s.lower() for s in components + labels + [summary]]
    for area, kws in AREA_KEYWORDS.items():
        if any(kw in t for kw in kws for t in texts):
            return area
    return "PMO"


def map_status(jira_status: str) -> str:
    s = jira_status.lower()
    if any(x in s for x in ["done", "complete", "closed", "resolved", "완료", "종료"]):
        return "done"
    if any(x in s for x in ["review", "qa", "검토", "리뷰", "in review"]):
        return "review"
    if any(x in s for x in ["progress", "develop", "진행", "개발", "in progress"]):
        return "doing"
    return "todo"


def date_to_week(date_str: str) -> int | None:
    """날짜 문자열(YYYY-MM-DD) → 프로젝트 주차 (1-based, 범위 클램프)"""
    if not date_str:
        return None
    try:
        d = datetime.strptime(date_str[:10], "%Y-%m-%d")
        delta = (d - PROJECT_START).days
        if delta < 0:
            return 1
        w = delta // 7 + 1
        return min(w, TOTAL_WEEKS)
    except Exception:
        return None


def today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def today_week() -> int:
    delta = (datetime.now() - PROJECT_START).days
    if delta < 0:
        return 0
    return min(delta // 7 + 1, TOTAL_WEEKS)


# ── JIRA API 클라이언트 ────────────────────────────────────────────────────────
class JiraClient:
    def __init__(self):
        if not all([JIRA_URL, JIRA_EMAIL, JIRA_TOKEN, PROJECT_KEY]):
            raise ValueError(
                "JIRA_URL / JIRA_EMAIL / JIRA_API_TOKEN / JIRA_PROJECT_KEY 환경변수를 모두 설정해주세요."
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

    def _post(self, path: str, body: dict = None) -> dict:
        r = requests.post(
            f"{self.base}/{path}",
            auth=self.auth,
            headers={**self.headers, "Content-Type": "application/json"},
            json=body or {}, timeout=30,
        )
        r.raise_for_status()
        return r.json()

    def search(self, jql: str, max_results: int = 10000) -> list:
        """Jira Cloud REST v3: /rest/api/3/search/jql (POST 방식 우선, 실패 시 GET fallback)."""
        issues = []
        next_page_token = None
        while True:
            batch = min(100, max_results - len(issues))
            body = {"jql": jql, "maxResults": batch, "fields": JIRA_FIELDS}
            if next_page_token:
                body["nextPageToken"] = next_page_token
            try:
                data = self._post("search/jql", body)
            except requests.HTTPError as e:
                # POST 실패 시 GET 으로 한 번만 재시도 (구버전 호환)
                print(f"  ⚠ POST 실패 ({e}), GET 재시도...")
                params = {"jql": jql, "maxResults": batch, "fields": ",".join(JIRA_FIELDS)}
                if next_page_token:
                    params["nextPageToken"] = next_page_token
                data = self._get("search/jql", params)
            batch_issues = data.get("issues", [])
            # 첫 페이지에서만 진단 로그 출력
            if not issues:
                is_last = data.get("isLast")
                total   = data.get("total")
                print(f"  • JIRA 응답: issues={len(batch_issues)}개, "
                      f"total={total}, isLast={is_last}, "
                      f"nextPageToken={'있음' if data.get('nextPageToken') else '없음'}")
                if not batch_issues:
                    print(f"  ⚠ 첫 응답이 비어있음 — JQL: {jql!r}")
                    print(f"    응답 키: {list(data.keys())}")
            issues.extend(batch_issues)
            next_page_token = data.get("nextPageToken")
            if not batch_issues or len(issues) >= max_results or not next_page_token:
                break
        return issues

    def project_type(self) -> str:
        try:
            data = self._get(f"project/{PROJECT_KEY}")
            return data.get("projectTypeKey", "business")
        except Exception:
            return "business"

    def discover_start_field(self) -> str:
        """Jira 인스턴스에서 시작일 커스텀 필드 ID 자동 탐색"""
        try:
            fields = self._get("field")
            for f in fields:
                name   = (f.get("name") or "").lower()
                fid    = f.get("id", "")
                schema = (f.get("schema") or {}).get("type", "")
                if schema == "date" and fid.startswith("customfield_"):
                    if any(x in name for x in ["start", "begin", "시작", "착수", "from"]):
                        print(f"  • 시작일 필드 발견: {fid} ({f.get('name')})")
                        return fid
        except Exception as e:
            print(f"  ⚠ 필드 탐색 실패: {e}")
        return "customfield_10015"  # 기본값


# ── D-배열 항목 생성 ──────────────────────────────────────────────────────────
_DATE_RE = re.compile(r'202[4-9]-\d{2}-\d{2}')

def _extract_dates(fields: dict) -> tuple[int, int]:
    """JIRA fields → (start_week, end_week)
    여러 커스텀 필드 후보를 순서대로 시도하고, 없으면 customfield_* 전체 스캔.
    """
    start_raw = None

    # 1) 후보 필드 순서대로 확인
    for key in START_DATE_CANDIDATES:
        val = fields.get(key)
        if val and isinstance(val, str) and _DATE_RE.match(val):
            start_raw = val[:10]
            break

    # 2) 그래도 없으면 customfield_* 전체를 스캔해서 프로젝트 기간 내 날짜 찾기
    if not start_raw:
        for key in sorted(fields):
            if not key.startswith("customfield_"):
                continue
            val = fields[key]
            if val and isinstance(val, str) and _DATE_RE.match(val):
                start_raw = val[:10]
                break

    # 3) 최후 수단: 이슈 생성일
    if not start_raw:
        start_raw = (fields.get("created") or "")[:10]

    end_raw = fields.get("duedate") or ""

    sw = date_to_week(start_raw) or today_week() or 1
    ew = date_to_week(end_raw)   or sw
    if ew < sw:
        ew = sw
    return sw, min(ew, TOTAL_WEEKS)


def make_d_task(issue: dict, wbs_id: str) -> dict:
    f      = issue["fields"]
    comps  = [c["name"] for c in (f.get("components") or [])]
    labels = f.get("labels") or []
    sw, ew = _extract_dates(f)
    # 시작일: 후보 필드 순서대로 탐색
    start_raw = None
    for key in START_DATE_CANDIDATES:
        val = f.get(key)
        if val and isinstance(val, str) and _DATE_RE.match(val):
            start_raw = val[:10]
            break
    if not start_raw:
        start_raw = (f.get("created") or "")[:10]
    end_raw = f.get("duedate") or ""
    return {
        "id":      wbs_id,
        "jiraKey": issue["key"],
        "jiraUrl": f"{JIRA_URL}/browse/{issue['key']}",
        "n":       f.get("summary", "Unknown"),
        "t":       "t",
        "area":    detect_area(comps, labels, f.get("summary", "")),
        "owner":   (f.get("assignee") or {}).get("displayName", ""),
        "s":       sw,
        "e":       ew,
        "st":      map_status(f["status"]["name"]),
        "priority":(f.get("priority") or {}).get("name", "Medium"),
        "sd":      (start_raw or "")[:10],
        "ed":      (end_raw or "")[:10],
    }


def make_d_phase(phase_id: str, issue: dict, tasks: list) -> list[dict]:
    """Phase 헤더 + Task 목록 → D 배열 항목들"""
    f      = issue["fields"]
    comps  = [c["name"] for c in (f.get("components") or [])]
    labels = f.get("labels") or []
    sw, ew = _extract_dates(f)
    # 자식 범위로 phase 범위 보정
    if tasks:
        sw = min(t["s"] for t in tasks)
        ew = max(t["e"] for t in tasks)
    phase = {
        "id":      phase_id,
        "jiraKey": issue["key"],
        "jiraUrl": f"{JIRA_URL}/browse/{issue['key']}",
        "n":       f.get("summary", "Unknown"),
        "t":       "p",
        "area":    detect_area(comps, labels, f.get("summary", "")),
        "owner":   (f.get("assignee") or {}).get("displayName", "PM팀"),
        "s":       sw,
        "e":       ew,
        "st":      map_status(f["status"]["name"]),
    }
    return [phase] + tasks


# ── 스냅샷 저장 ────────────────────────────────────────────────────────────────
def _extract_snapshot_issue(issue: dict) -> dict:
    f = issue["fields"]
    start_raw = None
    for key in START_DATE_CANDIDATES:
        val = f.get(key)
        if val and isinstance(val, str) and _DATE_RE.match(val):
            start_raw = val[:10]; break
    if not start_raw:
        for key in sorted(f):
            val = f.get(key)
            if key.startswith("customfield_") and isinstance(val, str) and _DATE_RE.match(val or ""):
                start_raw = val[:10]; break
    parent = f.get("parent") or {}
    return {
        "key":        issue["key"],
        "summary":    f.get("summary", ""),
        "status":     (f.get("status") or {}).get("name", ""),
        "status_wbs": map_status((f.get("status") or {}).get("name", "")),
        "priority":   (f.get("priority") or {}).get("name", "Medium"),
        "assignee":   (f.get("assignee") or {}).get("displayName", ""),
        "start_date": start_raw or "",
        "due_date":   f.get("duedate") or "",
        "issue_type": (f.get("issuetype") or {}).get("name", ""),
        "parent_key": parent.get("key", ""),
        "epic_link":  f.get("customfield_10014") or "",
        "labels":     f.get("labels") or [],
        "components": [c["name"] for c in (f.get("components") or [])],
        "created":    (f.get("created") or "")[:10],
        "updated":    (f.get("updated") or "")[:10],
    }


def save_snapshot(issues: list) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    os.makedirs(SNAPSHOT_DIR, exist_ok=True)
    snapshot = {
        "date":        today,
        "project_key": PROJECT_KEY,
        "fetched_at":  datetime.now().isoformat(),
        "total":       len(issues),
        "issues":      [_extract_snapshot_issue(i) for i in issues],
    }
    path = os.path.join(SNAPSHOT_DIR, f"{today}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)
    _update_snapshot_index(today, len(issues))
    return path


def _update_snapshot_index(date: str, count: int):
    idx_path = os.path.join(SNAPSHOT_DIR, "index.json")
    if os.path.exists(idx_path):
        with open(idx_path, "r", encoding="utf-8") as f:
            idx = json.load(f)
    else:
        idx = {"project_key": PROJECT_KEY, "jira_url": JIRA_URL, "snapshots": []}
    existing = next((s for s in idx["snapshots"] if s["date"] == date), None)
    entry = {"date": date, "count": count, "file": f"{date}.json",
             "updated_at": datetime.now().isoformat()}
    if existing:
        existing.update(entry)
    else:
        idx["snapshots"].append(entry)
    idx["snapshots"].sort(key=lambda x: x["date"], reverse=True)
    idx["project_key"] = PROJECT_KEY
    idx["jira_url"] = JIRA_URL
    with open(idx_path, "w", encoding="utf-8") as f:
        json.dump(idx, f, ensure_ascii=False, indent=2)


# ── JIRA Software (Epic 기반) ──────────────────────────────────────────────────
def build_d_software(all_issues: list) -> list:
    epics     = [i for i in all_issues
                 if (i["fields"].get("issuetype") or {}).get("name", "").lower() == "epic"]
    non_epics = [i for i in all_issues
                 if (i["fields"].get("issuetype") or {}).get("name", "").lower() not in ("epic", "sub-task", "subtask")]
    print(f"  • 에픽: {len(epics)}개  이슈(Task/Story/기타): {len(non_epics)}개")

    epic_map: dict = {e["key"]: [] for e in epics}
    unassigned = []
    for iss in non_epics:
        fld = iss["fields"]
        epic_key = fld.get("customfield_10014")
        if not epic_key:
            parent = fld.get("parent") or {}
            parent_itype = (
                (parent.get("fields") or {}).get("issuetype", {}).get("name", "")
                or parent.get("typeName", "")
            )
            if "epic" in parent_itype.lower():
                epic_key = parent.get("key")
        if epic_key and epic_key in epic_map:
            epic_map[epic_key].append(iss)
        else:
            unassigned.append(iss)

    D = []
    for i, epic in enumerate(epics):
        pid   = f"P{i+1}"
        tasks = [make_d_task(iss, f"{i+1}.{j+1}") for j, iss in enumerate(epic_map.get(epic["key"], []))]
        D.extend(make_d_phase(pid, epic, tasks))

    if unassigned:
        tasks = [make_d_task(iss, f"0.{j+1}") for j, iss in enumerate(unassigned)]
        sw = min(t["s"] for t in tasks) if tasks else 1
        ew = max(t["e"] for t in tasks) if tasks else 1
        D.insert(0, {"id":"P0","jiraKey":"","jiraUrl":"","n":"미분류 이슈","t":"p","area":"PMO","owner":"","s":sw,"e":ew,"st":"todo"})
        D[1:1] = tasks
    return D


# ── JIRA Work Management (Task 계층) ──────────────────────────────────────────
def build_d_workmanagement(all_issues: list) -> list:
    print(f"  • 전체 이슈: {len(all_issues)}개")
    issue_map = {iss["key"]: iss for iss in all_issues}
    top_level, children = [], {}

    for iss in all_issues:
        fld    = iss["fields"]
        itype  = (fld.get("issuetype") or {}).get("name", "").lower()
        parent = fld.get("parent")
        if parent:
            children.setdefault(parent["key"], []).append(iss)
        elif "sub" not in itype:
            top_level.append(iss)

    print(f"  • 최상위 Task(Phase): {len(top_level)}개")
    D = []
    for i, par in enumerate(top_level):
        pid   = f"P{i+1}"
        kids  = children.get(par["key"], [])
        tasks = [make_d_task(child, f"{i+1}.{j+1}") for j, child in enumerate(kids)]
        if not tasks:
            tasks = [make_d_task(par, f"{i+1}.1")]
        D.extend(make_d_phase(pid, par, tasks))

    top_keys   = {p["key"] for p in top_level}
    child_keys = {iss["key"] for kids in children.values() for iss in kids}
    orphans    = [issue_map[k] for k in set(issue_map) - top_keys - child_keys]
    if orphans:
        tasks = [make_d_task(iss, f"0.{j+1}") for j, iss in enumerate(orphans)]
        sw, ew = min(t["s"] for t in tasks), max(t["e"] for t in tasks)
        D.insert(0, {"id":"P0","jiraKey":"","jiraUrl":"","n":"기타 이슈","t":"p","area":"PMO","owner":"","s":sw,"e":ew,"st":"todo"})
        D[1:1] = tasks
    return D


def build_d_array(all_issues: list, ptype: str) -> list:
    print(f"  • 프로젝트 유형: {ptype}")
    if ptype == "software":
        epics = [i for i in all_issues
                 if (i["fields"].get("issuetype") or {}).get("name", "").lower() == "epic"]
        if epics:
            return build_d_software(all_issues)
    return build_d_workmanagement(all_issues)


# ── HTML 생성 ──────────────────────────────────────────────────────────────────
def build_html(D: list, snapshot_date: str = None) -> str:
    pw_hash     = sha256_hex(WBS_PASSWORD)
    last_update = datetime.now().strftime("%Y-%m-%d %H:%M")
    td_str      = today_str()
    snapshot_date = snapshot_date or td_str  # index.html은 이 날짜 스냅샷 기준으로 구성
    tw          = today_week()
    ps_str      = PROJECT_START.strftime("%Y-%m-%d")
    d_json      = json.dumps(D, ensure_ascii=False)

    tasks  = [r for r in D if r["t"] == "t"]
    total  = len(tasks)
    done   = sum(1 for t in tasks if t["st"] == "done")
    doing  = sum(1 for t in tasks if t["st"] == "doing")
    review = sum(1 for t in tasks if t["st"] == "review")
    todo   = total - done - doing - review
    pct    = round(done / total * 100) if total else 0

    board_url = f"{JIRA_URL}/jira/core/projects/{PROJECT_KEY}/board" if JIRA_URL else "#"

    # MONTHS 범위 계산 (PROJECT_START 기준)
    months_json = _build_months_json(ps_str, TOTAL_WEEKS)

    # HTML 템플릿 (%%PLACEHOLDER%% 치환 방식)
    template = _html_template()
    html = (template
        .replace("%%WBS_TITLE%%",     WBS_TITLE)
        .replace("%%PW_HASH%%",       pw_hash)
        .replace("%%PROJECT_KEY%%",   PROJECT_KEY)
        .replace("%%LAST_UPDATE%%",   last_update)
        .replace("%%TODAY_STR%%",     td_str)
        .replace("%%TODAY_W%%",       str(tw))
        .replace("%%PROJECT_START%%", ps_str)
        .replace("%%TOTAL_WEEKS%%",   str(TOTAL_WEEKS))
        .replace("%%MONTHS_JSON%%",   months_json)
        .replace("%%D_JSON%%",        d_json)
        .replace("%%SNAPSHOT_DATE%%",   snapshot_date)
        .replace("%%WBS_PROJECT_NAME%%", WBS_PROJECT_NAME)
        .replace("%%WBS_GATE_SUB%%",     WBS_GATE_SUB)
        .replace("%%WBS_EXCEL_NAME%%",    re.sub(r'[^\w\u3131-\u318e\uac00-\ud7a3\-]', '_', WBS_PROJECT_NAME))
        .replace("%%JIRA_URL%%",         JIRA_URL)
        .replace("%%BOARD_URL%%",     board_url)
        .replace("%%TOTAL%%",         str(total))
        .replace("%%DONE%%",          str(done))
        .replace("%%DOING%%",         str(doing))
        .replace("%%REVIEW%%",        str(review))
        .replace("%%TODO%%",          str(todo))
        .replace("%%PCT%%",           str(pct))
        .replace("%%PHASES%%",        str(sum(1 for r in D if r["t"] == "p")))
        .replace("%%MILESTONES%%",    str(sum(1 for r in D if r["t"] == "m")))
    )
    return html


def build_history_html() -> str:
    pw_hash    = sha256_hex(WBS_PASSWORD)
    ps_str     = PROJECT_START.strftime("%Y-%m-%d")
    jira_url   = JIRA_URL
    proj_key   = PROJECT_KEY
    months_json = _build_months_json(ps_str, TOTAL_WEEKS)
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>{WBS_TITLE} — 이력 조회</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'Segoe UI',system-ui,sans-serif;background:#f0f4f8;color:#1e293b;font-size:13px}}
/* ── 게이트 ── */
#gate{{position:fixed;inset:0;background:#1e293b;display:flex;align-items:center;justify-content:center;z-index:9999}}
.gb{{background:#fff;border-radius:1rem;padding:2.5rem 3rem;width:360px;box-shadow:0 20px 60px rgba(0,0,0,.4)}}
.gb-title{{font-size:1.2rem;font-weight:700;color:#1e293b;margin-bottom:1.5rem;text-align:center}}
.gb-input{{width:100%;padding:.65rem .9rem;border:2px solid #e2e8f0;border-radius:.5rem;font-size:.95rem;margin-bottom:.8rem;outline:none}}
.gb-input:focus{{border-color:#2563eb}}
.gb-btn{{width:100%;padding:.7rem;background:#2563eb;color:#fff;border:none;border-radius:.5rem;font-size:.95rem;font-weight:600;cursor:pointer}}
.gb-btn:hover{{background:#1d4ed8}}
.gb-err{{color:#dc2626;font-size:.78rem;text-align:center;margin-top:.5rem;min-height:1em}}
/* ── 앱 ── */
#main{{display:none;flex-direction:column;min-height:100vh}}
.app-hdr{{background:#1e293b;color:#f8fafc;padding:.6rem 1.4rem;display:flex;align-items:center;gap:.8rem;position:sticky;top:0;z-index:200}}
.app-hdr-title{{font-weight:700;font-size:.95rem}}
.app-hdr-sub{{font-size:.72rem;color:#94a3b8}}
.hdr-link{{color:#60a5fa;text-decoration:none;font-size:.72rem}}
.hdr-link:hover{{color:#93c5fd}}
/* ── 컨트롤 바 ── */
.ctrl-bar{{padding:.5rem 1.4rem;background:#fff;border-bottom:1px solid #e2e8f0;display:flex;align-items:center;gap:.6rem;flex-wrap:wrap;position:sticky;top:40px;z-index:190}}
.ctrl-label{{font-size:.72rem;color:#64748b;font-weight:600}}
select.date-sel{{padding:.28rem .6rem;border:1.5px solid #e2e8f0;border-radius:.3rem;font-size:.73rem;background:#fff;cursor:pointer}}
.view-btn{{padding:.28rem .75rem;border:1.5px solid #e2e8f0;border-radius:.3rem;font-size:.72rem;cursor:pointer;background:#fff;color:#475569;font-weight:600}}
.view-btn.on{{background:#2563eb;border-color:#2563eb;color:#fff}}
.badge{{display:inline-block;font-size:.55rem;padding:.06rem .3rem;border-radius:99px;font-weight:700;white-space:nowrap;vertical-align:middle}}
.b-todo{{background:#f1f5f9;color:#64748b}}
.b-doing{{background:#dbeafe;color:#1d4ed8}}
.b-review{{background:#fef3c7;color:#92400e}}
.b-done{{background:#dcfce7;color:#166534}}
.b-high{{background:#fee2e2;color:#991b1b}}
.b-medium{{background:#fef9c3;color:#854d0e}}
.b-low{{background:#f1f5f9;color:#64748b}}
/* ── 이슈 테이블 ── */
#tbl-view{{overflow:auto;flex:1;min-height:0}}
.iss-tbl{{width:100%;border-collapse:collapse;font-size:.72rem}}
.iss-tbl th{{background:#1e293b;color:#94a3b8;padding:.4rem .6rem;text-align:left;position:sticky;top:0;font-weight:600;white-space:nowrap}}
.iss-tbl td{{padding:.35rem .6rem;border-bottom:1px solid #f1f5f9;vertical-align:middle}}
.iss-tbl tr:hover td{{background:#eff6ff}}
.iss-tbl .key-cell a{{color:#2563eb;text-decoration:none;font-family:Consolas,monospace;font-weight:700}}
.iss-tbl .key-cell a:hover{{text-decoration:underline}}
.sum-cell{{max-width:320px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.diff-add{{background:#dcfce7!important}}
.diff-del{{background:#fee2e2!important;text-decoration:line-through;opacity:.6}}
.diff-chg{{background:#fef9c3!important}}
/* ── Gantt ── */
#gantt-view{{overflow:auto;flex:1;min-height:0}}
.gtbl{{border-collapse:collapse;table-layout:fixed;font-size:.72rem}}
.gtbl th,.gtbl td{{border:1px solid #e2e8f0;padding:0;white-space:nowrap;overflow:hidden}}
.td-id{{position:sticky;left:0;z-index:10;width:90px;min-width:90px;background:#fff;padding:.25rem .4rem;font-size:.6rem;font-family:Consolas,monospace;color:#64748b}}
.td-nm{{position:sticky;left:90px;z-index:10;width:230px;min-width:230px;background:#fff;padding:.25rem .5rem}}
.td-ow{{position:sticky;left:320px;z-index:10;width:80px;min-width:80px;background:#fff;padding:.25rem .35rem;text-align:center}}
.th-id{{position:sticky;left:0;top:0;z-index:25;background:#1e293b;color:#94a3b8;font-size:.59rem;padding:.4rem .4rem;width:90px;min-width:90px;border-color:#334155!important}}
.th-nm{{position:sticky;left:90px;top:0;z-index:25;background:#1e293b;color:#94a3b8;font-size:.59rem;padding:.4rem .65rem;width:230px;min-width:230px;border-color:#334155!important}}
.th-ow{{position:sticky;left:320px;top:0;z-index:25;background:#1e293b;color:#94a3b8;font-size:.59rem;padding:.4rem .4rem;width:80px;min-width:80px;border-color:#334155!important;text-align:center}}
.th-mo{{background:#334155;color:#e2e8f0;font-size:.7rem;padding:.36rem .35rem;text-align:center;border-color:#475569!important;position:sticky;top:0;z-index:6}}
.th-w{{background:#f8fafc;text-align:center;width:52px;min-width:52px;max-width:52px;border-color:#e2e8f0!important;cursor:default;padding:.14rem .1rem;vertical-align:top;line-height:1;position:sticky;z-index:5}}
.th-w-num{{font-size:.63rem;font-weight:700;color:#475569;line-height:1.25}}
.th-w-dt{{font-size:.47rem;color:#94a3b8;line-height:1.25;letter-spacing:-.01em;white-space:nowrap}}
.bar{{height:12px;margin:10px 0;border-radius:4px;opacity:.85}}
.r-phase .td-id,.r-phase .td-nm,.r-phase .td-ow{{background:#f1f5f9!important}}
.r-phase .td-nm{{font-weight:700;color:#1e293b}}
.info-bar{{padding:.35rem 1.4rem;background:#f8fafc;border-bottom:1px solid #e2e8f0;font-size:.7rem;color:#475569;display:flex;gap:1rem;flex-wrap:wrap}}
.diff-legend{{display:flex;gap:.5rem;align-items:center;font-size:.68rem;color:#64748b}}
.dl-dot{{width:10px;height:10px;border-radius:2px;display:inline-block}}
</style>
</head>
<body>
<div id="gate">
  <div class="gb">
    <div class="gb-title">🗓 WBS 이력 조회</div>
    <input id="gpw" class="gb-input" type="password" placeholder="비밀번호" autocomplete="current-password"/>
    <button class="gb-btn" onclick="checkPw()">확인</button>
    <div id="gerr" class="gb-err"></div>
  </div>
</div>
<div id="main">
  <div class="app-hdr">
    <span class="app-hdr-title">📅 {WBS_TITLE} — 이력 조회</span>
    <span class="app-hdr-sub" id="snap-info">스냅샷 로딩 중...</span>
    <span style="flex:1"></span>
    <a href="index.html" class="hdr-link">← 현재 WBS</a>
  </div>
  <div class="ctrl-bar">
    <span class="ctrl-label">날짜 선택:</span>
    <select class="date-sel" id="date-sel" onchange="loadSnapshot(this.value)">
      <option value="">-- 날짜 선택 --</option>
    </select>
    <span class="ctrl-label" style="margin-left:.5rem">비교:</span>
    <select class="date-sel" id="date-sel2" onchange="renderCurrent()">
      <option value="">-- 없음 --</option>
    </select>
    <span style="flex:1"></span>
    <button class="view-btn on" id="vb-tbl" onclick="setView('tbl')">목록</button>
    <button class="view-btn" id="vb-gantt" onclick="setView('gantt')">WBS</button>
  </div>
  <div class="info-bar" id="info-bar">이슈를 선택해주세요</div>
  <div id="tbl-view"></div>
  <div id="gantt-view" style="display:none"></div>
</div>
<script>
const PW_HASH="{pw_hash}";
const JIRA_BASE="{jira_url}";
const PROJECT_KEY="{proj_key}";
const PROJECT_START=new Date("{ps_str}");
const TOTAL_WEEKS={TOTAL_WEEKS};
const MONTHS={months_json};
const AC={{'이지원':'#3b82f6','인터넷웹':'#8b5cf6','콜센터':'#10b981','인프라':'#f59e0b','PMO':'#94a3b8'}};
const BC={{'이지원':'#2563eb','인터넷웹':'#7c3aed','콜센터':'#059669','인프라':'#d97706','PMO':'#64748b'}};

// ── 인증 ──
async function sha256(msg){{
  const buf=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(msg));
  return Array.from(new Uint8Array(buf)).map(b=>b.toString(16).padStart(2,'0')).join('');
}}
async function checkPw(){{
  const h=await sha256(document.getElementById('gpw').value);
  if(h===PW_HASH){{document.getElementById('gate').style.display='none';document.getElementById('main').style.display='flex';init();}}
  else document.getElementById('gerr').textContent='비밀번호가 올바르지 않습니다.';
}}
document.getElementById('gpw').addEventListener('keydown',e=>{{if(e.key==='Enter')checkPw();}});

// ── 유틸 ──
function dateToWeek(ds){{
  if(!ds)return null;
  const d=new Date(ds),delta=Math.floor((d-PROJECT_START)/86400000);
  if(delta<0)return 1;
  return Math.min(Math.floor(delta/7)+1,TOTAL_WEEKS);
}}
function weekStartDate(w){{const d=new Date(PROJECT_START);d.setDate(d.getDate()+(w-1)*7);return d;}}
function fmtDate(d){{return(d.getMonth()+1)+'/'+(d.getDate());}}
function detectArea(summary,labels,components){{
  const txt=[summary,...(labels||[]),...(components||[])].join(' ').toLowerCase();
  if(['이지원','마이다스','법인','공동대표','ocr','챗봇','팩토리','상품','app','고도화'].some(k=>txt.includes(k)))return '이지원';
  if(['사이버','보안','사이버보증','인터넷','웹'].some(k=>txt.includes(k)))return '인터넷웹';
  if(['콜센터','상담','ars','보이는ars'].some(k=>txt.includes(k)))return '콜센터';
  if(['인프라','서버','소스코드','응답시간','성능','형상'].some(k=>txt.includes(k)))return '인프라';
  return 'PMO';
}}
function mapStatus(s){{
  s=(s||'').toLowerCase();
  if(['done','complete','closed','resolved','완료','종료'].some(x=>s.includes(x)))return 'done';
  if(['review','qa','검토','리뷰'].some(x=>s.includes(x)))return 'review';
  if(['progress','develop','진행','개발'].some(x=>s.includes(x)))return 'doing';
  return 'todo';
}}
const SL={{'done':'완료','doing':'진행','review':'검토','todo':'대기'}};
const SC={{'done':'b-done','doing':'b-doing','review':'b-review','todo':'b-todo'}};
const PL={{'High':'b-high','Medium':'b-medium','Low':'b-low'}};

// ── 상태 ──
let curSnap=null, cmpSnap=null, curView='tbl';

// ── 초기화 ──
async function init(){{
  try{{
    const r=await fetch('./data/snapshots/index.json');
    const idx=await r.json();
    const s1=document.getElementById('date-sel');
    const s2=document.getElementById('date-sel2');
    idx.snapshots.forEach(s=>{{
      [s1,s2].forEach(sel=>{{
        const o=document.createElement('option');
        o.value=s.date;o.textContent=s.date+' ('+s.count+'건)';sel.appendChild(o);
      }});
    }});
    document.getElementById('snap-info').textContent='스냅샷 '+idx.snapshots.length+'개 | 프로젝트: '+(idx.project_key||PROJECT_KEY);
    if(idx.snapshots.length>0){{s1.value=idx.snapshots[0].date;loadSnapshot(idx.snapshots[0].date);}}
  }}catch(e){{document.getElementById('snap-info').textContent='스냅샷 없음 (Actions 실행 후 생성됩니다)';}}
}}

async function loadSnapshot(date){{
  if(!date)return;
  try{{
    const r=await fetch('./data/snapshots/'+date+'.json');
    curSnap=await r.json();
    const date2=document.getElementById('date-sel2').value;
    if(date2){{
      const r2=await fetch('./data/snapshots/'+date2+'.json');
      cmpSnap=await r2.json();
    }}else cmpSnap=null;
    renderCurrent();
  }}catch(e){{alert('스냅샷 로드 실패: '+e.message);}}
}}

async function renderCurrent(){{
  const date2=document.getElementById('date-sel2').value;
  if(date2&&(!cmpSnap||cmpSnap.date!==date2)){{
    try{{const r=await fetch('./data/snapshots/'+date2+'.json');cmpSnap=await r.json();}}
    catch(e){{cmpSnap=null;}}
  }}
  if(!curSnap)return;
  updateInfoBar();
  if(curView==='tbl')renderTable();
  else renderGantt();
}}

function setView(v){{
  curView=v;
  document.getElementById('tbl-view').style.display=v==='tbl'?'block':'none';
  document.getElementById('gantt-view').style.display=v==='gantt'?'block':'none';
  document.getElementById('vb-tbl').className='view-btn'+(v==='tbl'?' on':'');
  document.getElementById('vb-gantt').className='view-btn'+(v==='gantt'?' on':'');
  renderCurrent();
}}

function updateInfoBar(){{
  if(!curSnap)return;
  const iss=curSnap.issues;
  const tot=iss.length,done=iss.filter(i=>i.status_wbs==='done').length;
  const doing=iss.filter(i=>i.status_wbs==='doing').length,review=iss.filter(i=>i.status_wbs==='review').length;
  const td=iss.filter(i=>i.status_wbs==='todo').length;
  let html=`<b>${{curSnap.date}}</b> | 전체 ${{tot}}건 | `;
  html+=`<span class="badge b-done">완료 ${{done}}</span> `;
  html+=`<span class="badge b-doing">진행 ${{doing}}</span> `;
  html+=`<span class="badge b-review">검토 ${{review}}</span> `;
  html+=`<span class="badge b-todo">대기 ${{td}}</span>`;
  if(cmpSnap)html+=` &nbsp;↔ 비교: <b>${{cmpSnap.date}}</b> <span style="color:#64748b;font-size:.65rem">(🟢추가 🔴삭제 🟡변경)</span>`;
  document.getElementById('info-bar').innerHTML=html;
}}

// ── 테이블 뷰 ──
function renderTable(){{
  if(!curSnap)return;
  const issues=curSnap.issues;
  const cmpMap=cmpSnap?Object.fromEntries(cmpSnap.issues.map(i=>[i.key,i])):{{}};
  let rows='';
  issues.forEach(iss=>{{
    const cmp=cmpMap[iss.key];
    let rowCls='';
    if(cmpSnap&&!cmp)rowCls='diff-add';
    else if(cmpSnap&&cmp&&(cmp.status!==iss.status||cmp.due_date!==iss.due_date||cmp.assignee!==iss.assignee))rowCls='diff-chg';
    const jiraLink=JIRA_BASE?`<a href="${{JIRA_BASE}}/browse/${{iss.key}}" target="_blank">${{iss.key}}</a>`:iss.key;
    rows+=`<tr class="${{rowCls}}">
      <td class="key-cell">${{jiraLink}}</td>
      <td class="sum-cell" title="${{iss.summary.replace(/"/g,'&quot;')}}">${{iss.summary}}</td>
      <td>${{iss.issue_type}}</td>
      <td><span class="badge ${{SC[iss.status_wbs]||'b-todo'}}">${{SL[iss.status_wbs]||iss.status}}</span></td>
      <td><span class="badge ${{PL[iss.priority]||'b-medium'}}">${{iss.priority||'-'}}</span></td>
      <td>${{iss.assignee||'-'}}</td>
      <td style="font-family:monospace;font-size:.65rem">${{iss.start_date||'-'}}</td>
      <td style="font-family:monospace;font-size:.65rem">${{iss.due_date||'-'}}</td>
    </tr>`;
  }});
  // 비교: 삭제된 이슈
  if(cmpSnap){{
    const curKeys=new Set(issues.map(i=>i.key));
    cmpSnap.issues.filter(i=>!curKeys.has(i.key)).forEach(iss=>{{
      const jiraLink=JIRA_BASE?`<a href="${{JIRA_BASE}}/browse/${{iss.key}}" target="_blank">${{iss.key}}</a>`:iss.key;
      rows+=`<tr class="diff-del">
        <td class="key-cell">${{jiraLink}}</td>
        <td class="sum-cell">${{iss.summary}}</td>
        <td>${{iss.issue_type}}</td>
        <td><span class="badge ${{SC[iss.status_wbs]||'b-todo'}}">${{SL[iss.status_wbs]||iss.status}}</span></td>
        <td><span class="badge ${{PL[iss.priority]||'b-medium'}}">${{iss.priority||'-'}}</span></td>
        <td>${{iss.assignee||'-'}}</td>
        <td style="font-family:monospace;font-size:.65rem">${{iss.start_date||'-'}}</td>
        <td style="font-family:monospace;font-size:.65rem">${{iss.due_date||'-'}}</td>
      </tr>`;
    }});
  }}
  document.getElementById('tbl-view').innerHTML=`
  <table class="iss-tbl">
    <thead><tr>
      <th>KEY</th><th>Summary</th><th>Type</th><th>Status</th>
      <th>Priority</th><th>Assignee</th><th>Start</th><th>Due</th>
    </tr></thead>
    <tbody>${{rows}}</tbody>
  </table>`;
}}

// ── Gantt 뷰 ──
function buildDArray(issues){{
  const epicIssues={{}};
  const nonEpics=[];
  issues.forEach(i=>{{
    if((i.issue_type||'').toLowerCase()==='epic')epicIssues[i.key]=i;
    else if((i.issue_type||'').toLowerCase()!=='sub-task')nonEpics.push(i);
  }});
  const hasEpics=Object.keys(epicIssues).length>0;
  const D=[];
  if(hasEpics){{
    const epicMap={{}};
    Object.keys(epicIssues).forEach(k=>epicMap[k]=[]);
    const unassigned=[];
    nonEpics.forEach(iss=>{{
      const ek=iss.epic_link||(iss.parent_key&&epicIssues[iss.parent_key]?iss.parent_key:null);
      if(ek&&epicMap[ek])epicMap[ek].push(iss);
      else unassigned.push(iss);
    }});
    let pi=1;
    Object.entries(epicIssues).forEach(([k,epic])=>{{
      const sw=dateToWeek(epic.start_date)||1,ew=dateToWeek(epic.due_date)||sw;
      const tasks=epicMap[k].map((iss,j)=>issueToTask(iss,pi+'.'+((j+1))));
      const tsw=tasks.length?Math.min(...tasks.map(t=>t.s)):sw;
      const tew=tasks.length?Math.max(...tasks.map(t=>t.e)):ew;
      D.push({{id:'P'+pi,jiraKey:k,jiraUrl:JIRA_BASE?JIRA_BASE+'/browse/'+k:'',n:epic.summary,t:'p',area:detectArea(epic.summary,epic.labels,epic.components),owner:epic.assignee,s:Math.min(sw,tsw),e:Math.max(ew,tew),st:mapStatus(epic.status)}});
      D.push(...tasks);pi++;
    }});
    if(unassigned.length){{
      const tasks=unassigned.map((iss,j)=>issueToTask(iss,'0.'+(j+1)));
      const sw2=Math.min(...tasks.map(t=>t.s)),ew2=Math.max(...tasks.map(t=>t.e));
      D.unshift({{id:'P0',n:'미분류',t:'p',area:'PMO',owner:'',s:sw2,e:ew2,st:'todo'}},...tasks);
    }}
  }}else{{
    // Work Management: parent → phase
    const topLevel=[],children={{}};
    issues.forEach(iss=>{{
      if(iss.parent_key)children[iss.parent_key]=(children[iss.parent_key]||[]).concat([iss]);
      else topLevel.push(iss);
    }});
    topLevel.forEach((par,i)=>{{
      const kids=children[par.key]||[];
      const tasks=kids.length?kids.map((k,j)=>issueToTask(k,(i+1)+'.'+(j+1))):[issueToTask(par,(i+1)+'.1')];
      const sw=dateToWeek(par.start_date)||1,ew=dateToWeek(par.due_date)||sw;
      const tsw=Math.min(...tasks.map(t=>t.s)),tew=Math.max(...tasks.map(t=>t.e));
      D.push({{id:'P'+(i+1),jiraKey:par.key,jiraUrl:JIRA_BASE?JIRA_BASE+'/browse/'+par.key:'',n:par.summary,t:'p',area:detectArea(par.summary,par.labels,par.components),owner:par.assignee,s:Math.min(sw,tsw),e:Math.max(ew,tew),st:mapStatus(par.status)}});
      D.push(...tasks);
    }});
  }}
  return D;
}}
function issueToTask(iss,wbsId){{
  const sw=dateToWeek(iss.start_date)||1,ew=dateToWeek(iss.due_date)||sw;
  return {{id:wbsId,jiraKey:iss.key,jiraUrl:JIRA_BASE?JIRA_BASE+'/browse/'+iss.key:'',n:iss.summary,t:'t',area:detectArea(iss.summary,iss.labels,iss.components),owner:iss.assignee||'',s:sw,e:ew,st:mapStatus(iss.status),sd:iss.start_date,ed:iss.due_date}};
}}

function renderGantt(){{
  if(!curSnap)return;
  const D=buildDArray(curSnap.issues);
  const div=document.getElementById('gantt-view');
  const tbl=document.createElement('table');tbl.className='gtbl';
  const thead=tbl.createTHead();
  const hr1=thead.insertRow(),hr2=thead.insertRow();
  hr1.innerHTML='<th class="th-id" rowspan="2">KEY</th><th class="th-nm" rowspan="2">작업명</th><th class="th-ow" rowspan="2">담당</th>';
  MONTHS.forEach(m=>{{
    const th=document.createElement('th');th.className='th-mo';th.colSpan=m.e-m.s+1;th.textContent='2026년 '+m.n;hr1.appendChild(th);
  }});
  for(let w=1;w<=TOTAL_WEEKS;w++){{
    const d=weekStartDate(w),de=new Date(d.getTime()+6*86400000);
    const th=document.createElement('th');th.className='th-w';
    th.innerHTML=`<div class="th-w-num">W${{w}}</div><div class="th-w-dt">${{fmtDate(d)}}~${{de.getDate()}}</div>`;
    hr2.appendChild(th);
  }}
  const tbody=tbl.createTBody();
  let curP=null;
  D.forEach(row=>{{
    const tr=tbody.insertRow();tr.className='r-'+{{p:'phase',t:'task',m:'ms'}}[row.t];
    if(row.t==='p')curP=row.id;
    // KEY
    const tdi=tr.insertCell();tdi.className='td-id';
    if(row.jiraKey&&JIRA_BASE){{
      const a=document.createElement('a');a.href=JIRA_BASE+'/browse/'+row.jiraKey;a.target='_blank';
      a.textContent=row.jiraKey;a.style.cssText='color:#2563eb;text-decoration:none;font-family:Consolas;font-size:.6rem';
      tdi.appendChild(a);
    }}else tdi.textContent=row.id;
    // 작업명
    const tdn=tr.insertCell();tdn.className='td-nm';
    const pip=document.createElement('span');pip.style.cssText=`display:inline-block;width:7px;height:7px;border-radius:50%;background:${{AC[row.area]||'#94a3b8'}};margin-right:.25rem;flex-shrink:0`;
    const sp=document.createElement('span');sp.textContent=row.n;
    if(row.t==='p')sp.style.cssText='font-weight:700;font-size:.78rem';
    else sp.style.cssText='font-size:.72rem;color:#334155';
    tdn.append(pip,sp);
    if(row.t==='t'){{
      const bd=document.createElement('span');bd.className='badge '+SC[row.st];bd.textContent=SL[row.st];
      bd.style.marginLeft='.25rem';tdn.appendChild(bd);
    }}
    // 담당
    const tdow=tr.insertCell();tdow.className='td-ow';
    if(row.owner){{const c=document.createElement('span');c.textContent=row.owner;c.style.cssText='font-size:.58rem;color:#64748b';tdow.appendChild(c);}}
    // 주차 셀
    for(let w=1;w<=TOTAL_WEEKS;w++){{
      const td=tr.insertCell();td.style.cssText='width:52px;min-width:52px;padding:0;';
      if(row.t!=='m'&&row.s<=w&&w<=row.e){{
        const isS=row.s===w,isE=row.e===w;
        const d=document.createElement('div');
        d.style.cssText=`height:12px;margin:10px 0;background:${{BC[row.area]||'#64748b'}};opacity:${{row.t==='p'?0.3:0.85}};border-radius:${{isS&&isE?'4px':isS?'4px 0 0 4px':isE?'0 4px 4px 0':'0'}};${{isS?'margin-left:2px':''}};${{isE?'margin-right:2px':''}};height:${{row.t==='p'?'5px':'12px'}};margin-top:${{row.t==='p'?'13.5px':'10px'}}`;
        td.appendChild(d);
      }}
    }}
  }});
  div.innerHTML='';div.appendChild(tbl);
  // sticky top 계산
  requestAnimationFrame(()=>{{
    const row1=tbl.querySelector('thead tr');
    const row1H=row1?Math.ceil(row1.getBoundingClientRect().height)||28:28;
    tbl.querySelectorAll('.th-w').forEach(th=>th.style.top=row1H+'px');
  }});
}}
</script>
</body>
</html>"""


def _build_months_json(ps_str: str, total_weeks: int) -> str:
    """주차 범위 → 월별 그룹 JSON"""
    ps = datetime.strptime(ps_str, "%Y-%m-%d")
    months = {}
    for w in range(1, total_weeks + 1):
        d = ps + timedelta(weeks=w - 1)
        key = (d.year, d.month)
        if key not in months:
            months[key] = {"n": f"{d.month}월", "s": w, "e": w}
        else:
            months[key]["e"] = w
    return json.dumps(list(months.values()), ensure_ascii=False)


# ── HTML 템플릿 ───────────────────────────────────────────────────────────────
def _html_template() -> str:
    return r"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>📋 %%WBS_PROJECT_NAME%%</title>
<script src="https://cdn.sheetjs.com/xlsx-0.20.3/package/dist/xlsx.full.min.js"></script>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Segoe UI',system-ui,sans-serif;background:#f0f4f8;color:#1e293b;font-size:13px}

/* ── 비밀번호 게이트 ── */
#gate{position:fixed;inset:0;background:linear-gradient(135deg,#0f172a 0%,#1e3a5f 50%,#1e1b4b 100%);display:flex;align-items:center;justify-content:center;z-index:9999}
.gb{background:#fff;border-radius:20px;padding:3rem 3.5rem;width:420px;text-align:center;box-shadow:0 40px 80px rgba(0,0,0,.5)}
.gb-logo{display:flex;align-items:center;justify-content:center;gap:.5rem;margin-bottom:1.5rem}
.gb-logo-icon{width:44px;height:44px;background:linear-gradient(135deg,#2563eb,#7c3aed);border-radius:12px;display:flex;align-items:center;justify-content:center;font-size:1.4rem}
.gb-logo-text{font-size:1.1rem;font-weight:800;color:#1e293b}
.gb-logo-sub{font-size:.65rem;color:#94a3b8;font-weight:500}
.gb-title{font-size:1rem;font-weight:700;margin-bottom:.3rem;color:#1e293b}
.gb-sub{font-size:.78rem;color:#94a3b8;margin-bottom:1.6rem}
.gb input{width:100%;padding:.82rem 1rem;border:2px solid #e2e8f0;border-radius:.6rem;font-size:.95rem;outline:none;transition:all .2s;margin-bottom:.9rem;color:#1e293b;background:#f8fafc}
.gb input:focus{border-color:#2563eb;box-shadow:0 0 0 4px rgba(37,99,235,.1);background:#fff}
.gb button{width:100%;padding:.82rem;background:linear-gradient(135deg,#2563eb,#1d4ed8);color:#fff;border:none;border-radius:.6rem;font-size:.95rem;font-weight:700;cursor:pointer;transition:all .2s}
.gb button:hover{opacity:.92;transform:translateY(-1px);box-shadow:0 6px 20px rgba(37,99,235,.35)}
.gb-err{font-size:.74rem;color:#ef4444;margin-top:.7rem;min-height:1.1rem}
.gb-footer{font-size:.65rem;color:#94a3b8;margin-top:1rem;display:flex;align-items:center;justify-content:center;gap:.3rem}

/* ── 메인 레이아웃 ── */
#main{display:none}
.app-hdr{background:linear-gradient(135deg,#1e293b,#1e3a5f);color:#fff;padding:.9rem 1.6rem;display:flex;align-items:center;gap:.75rem;flex-wrap:wrap;position:sticky;top:0;z-index:200;box-shadow:0 4px 20px rgba(0,0,0,.4)}
.app-hdr h1{font-size:1.15rem;font-weight:800;flex:1;min-width:0;letter-spacing:-.02em}
.hbadge{font-size:.7rem;padding:.28rem .65rem;border-radius:99px;font-weight:700;white-space:nowrap}
.hb-b{background:rgba(37,99,235,.45);color:#bfdbfe;border:1px solid rgba(96,165,250,.5)}
.hb-g{background:rgba(22,163,74,.4);color:#bbf7d0;border:1px solid rgba(34,197,94,.5)}
.hb-a{background:rgba(245,158,11,.35);color:#fef08a;border:1px solid rgba(251,191,36,.5)}
.sync{font-size:.72rem;color:#cbd5e1;display:flex;align-items:center;gap:.4rem;margin-left:auto;white-space:nowrap}
.sync select{background:rgba(255,255,255,.15);color:#f1f5f9;border:1px solid rgba(255,255,255,.25);border-radius:.35rem;padding:.3rem .55rem;font-size:.75rem;cursor:pointer;min-width:128px;font-weight:500}
.sync select:hover{background:rgba(255,255,255,.22)}
.sync select option{background:#1e293b;color:#e2e8f0}
.sdot{width:7px;height:7px;border-radius:50%;background:#4ade80;animation:blink 2s infinite;flex-shrink:0}
@keyframes blink{0%,100%{opacity:1}50%{opacity:.25}}
.jira-btn{display:inline-flex;align-items:center;gap:.28rem;color:#94a3b8;font-size:.66rem;text-decoration:none;border:1px solid #334155;padding:.22rem .5rem;border-radius:.3rem;transition:all .15s;white-space:nowrap;background:rgba(255,255,255,.05)}
.jira-btn:hover{color:#38bdf8;border-color:#38bdf8}

/* ── 전체 진척률 배너 ── */
.prog-banner{background:linear-gradient(135deg,#1e293b,#1e3a5f,#1e1b4b);color:#fff;padding:.9rem 1.4rem;display:flex;align-items:center;gap:1.5rem;flex-wrap:wrap}
.pb-pct{font-size:2.6rem;font-weight:900;color:#38bdf8;line-height:1;min-width:5rem;letter-spacing:-.04em}
.pb-info{flex:1;display:flex;flex-direction:column;gap:.25rem}
.pb-label{font-size:.62rem;color:#94a3b8;text-transform:uppercase;letter-spacing:.08em;font-weight:600}
.pb-bar{height:10px;background:rgba(255,255,255,.08);border-radius:5px;overflow:hidden;margin:.25rem 0}
.pb-fill{height:100%;background:linear-gradient(90deg,#22c55e,#38bdf8,#6366f1);border-radius:5px;transition:width .8s cubic-bezier(.4,0,.2,1)}
.pb-detail{font-size:.63rem;color:#64748b;display:flex;gap:.8rem;flex-wrap:wrap}
.pb-stat{display:flex;align-items:center;gap:.25rem}
.pbs-dot{width:7px;height:7px;border-radius:50%;flex-shrink:0}

/* ── 6 영역 진척 카드 ── */
.area-cards{display:grid;grid-template-columns:repeat(5,1fr);gap:.6rem;padding:.75rem 1.4rem;background:#fff;border-bottom:2px solid #e2e8f0}
@media(max-width:900px){.area-cards{grid-template-columns:repeat(3,1fr)}}
@media(max-width:500px){.area-cards{grid-template-columns:repeat(2,1fr)}}
.ac{border-radius:12px;padding:.7rem .85rem;cursor:pointer;transition:all .2s;border:2px solid transparent}
.ac:hover{transform:translateY(-2px);box-shadow:0 8px 24px rgba(0,0,0,.12)}
.ac.active{border-width:2px}
.ac-label{font-size:.6rem;font-weight:700;text-transform:uppercase;letter-spacing:.07em;opacity:.75;margin-bottom:.3rem}
.ac-pct{font-size:1.5rem;font-weight:900;line-height:1;margin-bottom:.3rem}
.ac-counts{font-size:.59rem;opacity:.65;margin-bottom:.4rem}
.ac-bar{height:5px;background:rgba(0,0,0,.08);border-radius:3px;overflow:hidden}
.ac-fill{height:100%;border-radius:3px;transition:width .8s ease}

/* ── 통계 스트립 ── */
.stats{display:grid;grid-template-columns:repeat(7,1fr);background:#f8fafc;border-bottom:2px solid #e2e8f0}
@media(max-width:700px){.stats{grid-template-columns:repeat(4,1fr)}}
.stat{text-align:center;padding:.55rem .4rem;border-right:1px solid #e2e8f0}
.stat:last-child{border:none}
.stat-v{font-size:1.3rem;font-weight:800;line-height:1}
.stat-l{font-size:.54rem;color:#94a3b8;text-transform:uppercase;letter-spacing:.06em;margin-top:.15rem}

/* ── 툴바 ── */
.toolbar{padding:.45rem 1.4rem;background:#fff;border-bottom:1px solid #e2e8f0;display:flex;align-items:center;gap:.3rem;flex-wrap:wrap;position:sticky;z-index:190;box-shadow:0 2px 8px rgba(0,0,0,.06)}
.tbtn{padding:.26rem .6rem;border:1.5px solid #e2e8f0;border-radius:.3rem;font-size:.69rem;font-weight:600;cursor:pointer;background:#fff;color:#64748b;transition:all .15s;white-space:nowrap;display:inline-flex;align-items:center;gap:.22rem}
.tbtn:hover{border-color:#2563eb;color:#2563eb;background:#eff6ff}
.tbtn.on{background:#2563eb;border-color:#2563eb;color:#fff}
.tbtn.excel{border-color:#166534;color:#166534;font-weight:700}
.tbtn.excel:hover{background:#f0fdf4}
.tbtn.accent{border-color:#0ea5e9;color:#0284c7}
.tbtn.accent:hover{background:#f0f9ff}
.tsep{width:1px;height:18px;background:#e2e8f0;margin:0 .1rem;flex-shrink:0}
.tb-grp{font-size:.6rem;color:#94a3b8;text-transform:uppercase;letter-spacing:.07em;font-weight:600}
.legend{display:flex;align-items:center;gap:.45rem;flex-wrap:wrap;margin-left:auto}
.leg{display:flex;align-items:center;gap:.22rem;font-size:.61rem;color:#64748b}
.leg-sq{width:12px;height:8px;border-radius:2px;flex-shrink:0}

/* ── 날짜 이동 ── */
.date-nav{padding:.35rem 1.4rem;background:#f8fafc;border-bottom:1px solid #e2e8f0;display:flex;align-items:center;gap:.5rem;flex-wrap:wrap;font-size:.7rem;color:#475569;position:sticky;z-index:180}
.week-jump select,.week-jump label{font-size:.68rem}
.week-jump{display:flex;align-items:center;gap:.3rem}
.week-jump select{padding:.2rem .5rem;border:1.5px solid #e2e8f0;border-radius:.28rem;background:#fff;color:#1e293b;cursor:pointer}

/* ── 간트 테이블 ── */
.gantt-scroll{overflow:auto;background:#fff;min-height:300px}
.gtbl{border-collapse:collapse;table-layout:fixed;white-space:nowrap}
.gtbl thead th{border:1px solid #e2e8f0;font-weight:600;user-select:none}
.th-id{position:sticky;left:0;top:0;z-index:25;background:#1e293b;color:#94a3b8;font-size:.59rem;padding:.4rem .4rem;width:62px;min-width:62px;border-color:#334155!important;text-align:left}
.th-nm{position:sticky;left:62px;top:0;z-index:25;background:#1e293b;color:#94a3b8;font-size:.59rem;padding:.4rem .65rem;width:var(--col-nm-w,320px);min-width:260px;max-width:600px;border-color:#334155!important;text-align:left}
.th-nm .col-resize{position:absolute;right:0;top:0;bottom:0;width:6px;cursor:col-resize;background:transparent}
.th-nm .col-resize:hover{background:rgba(56,189,248,.3)}
.th-ow{position:sticky;left:calc(62px + var(--col-nm-w,320px));top:0;z-index:25;background:#1e293b;color:#94a3b8;font-size:.59rem;padding:.4rem .4rem;width:72px;min-width:72px;border-color:#334155!important;text-align:center}
.th-sd{position:sticky;left:calc(134px + var(--col-nm-w,320px));top:0;z-index:25;background:#1e293b;color:#94a3b8;font-size:.59rem;padding:.4rem .35rem;width:92px;min-width:92px;border-color:#334155!important;text-align:center}
.th-ed{position:sticky;left:calc(226px + var(--col-nm-w,320px));top:0;z-index:25;background:#1e293b;color:#94a3b8;font-size:.59rem;padding:.4rem .35rem;width:92px;min-width:92px;border-color:#334155!important;text-align:center}
.th-mo{background:#334155;color:#e2e8f0;font-size:.7rem;padding:.36rem .35rem;text-align:center;border-color:#475569!important;position:sticky;top:0;z-index:6}
.th-w{background:#f8fafc;text-align:center;width:52px;min-width:52px;max-width:52px;border-color:#e2e8f0!important;cursor:default;padding:.14rem .1rem;vertical-align:top;line-height:1;position:sticky;z-index:5}
.th-w-num{font-size:.63rem;font-weight:700;color:#475569;line-height:1.25}
.th-w-dt{font-size:.47rem;color:#94a3b8;line-height:1.25;letter-spacing:-.01em;white-space:nowrap}
.th-w-now .th-w-num{color:#b45309!important}
.th-w-now .th-w-dt{color:#ca8a04!important}
.th-w-past .th-w-num{color:#cbd5e1!important}
.th-w-past .th-w-dt{color:#dde4ed!important}
.th-w-now{background:#fef3c7!important}
.th-w-past{background:#f9fafb!important}
.task-dts{font-size:.5rem;color:#94a3b8;margin-left:auto;padding-left:.3rem;flex-shrink:0;white-space:nowrap;letter-spacing:.01em}

.td-id{position:sticky;left:0;z-index:10;background:#fff;border:1px solid #f1f5f9;border-right:1px solid #e2e8f0;padding:.2rem .4rem;font-size:.6rem;font-family:Consolas,monospace;color:#94a3b8;width:62px;min-width:62px;vertical-align:middle}
.td-nm{position:sticky;left:62px;z-index:10;background:#fff;border:1px solid #f1f5f9;border-right:1px solid #e2e8f0;padding:.35rem .55rem;width:var(--col-nm-w,320px);min-width:260px;max-width:600px;word-break:keep-all;overflow:hidden;text-overflow:ellipsis;vertical-align:middle;line-height:1.35}
.td-ow{position:sticky;left:calc(62px + var(--col-nm-w,320px));z-index:10;background:#fff;border:1px solid #f1f5f9;border-right:1px solid #e2e8f0;padding:.15rem .35rem;width:72px;min-width:72px;vertical-align:middle;text-align:center}
.td-sd{position:sticky;left:calc(134px + var(--col-nm-w,320px));z-index:10;background:#fff;border:1px solid #f1f5f9;border-right:1px solid #e2e8f0;padding:.2rem .35rem;width:92px;min-width:92px;font-size:.65rem;font-family:Consolas,monospace;color:#475569;vertical-align:middle;text-align:center}
.td-ed{position:sticky;left:calc(226px + var(--col-nm-w,320px));z-index:10;background:#fff;border:1px solid #f1f5f9;border-right:2px solid #d1d5db;padding:.2rem .35rem;width:92px;min-width:92px;font-size:.65rem;font-family:Consolas,monospace;color:#475569;vertical-align:middle;text-align:center}
.td-w{border:1px solid #f1f5f9;width:52px;min-width:52px;max-width:52px;padding:0;vertical-align:middle;height:34px}
.td-w.col-now{background:#fefce8}
.td-w.col-past{background:#fafafa}

tr.r-phase .td-id,.tr.r-phase .td-nm,.tr.r-phase .td-ow,.tr.r-phase .td-sd,.tr.r-phase .td-ed{background:#f1f5f9}
tr.r-phase .td-w{background:#f5f5f5}
tr.r-ms .td-id,tr.r-ms .td-nm,tr.r-ms .td-ow,tr.r-ms .td-sd,tr.r-ms .td-ed{background:#fffbeb}
.gtbl tbody tr:hover .td-id,.gtbl tbody tr:hover .td-nm,.gtbl tbody tr:hover .td-ow,.gtbl tbody tr:hover .td-sd,.gtbl tbody tr:hover .td-ed{background:#eff6ff!important}

/* 간트 바 */
.bar{height:12px;margin:10px 0;border-radius:0}
.bar-s{border-radius:4px 0 0 4px;margin-left:2px}
.bar-e{border-radius:0 4px 4px 0;margin-right:2px}
.bar-se{border-radius:4px;margin:10px 3px}
.bph{height:5px;margin:13.5px 0;opacity:.25;border-radius:0}
.bph.bar-s{border-radius:2px 0 0 2px;margin-left:1px}
.bph.bar-e{border-radius:0 2px 2px 0;margin-right:1px}
.bph.bar-se{border-radius:2px;margin:13.5px 1px}
.bar-done{opacity:.4;background-image:repeating-linear-gradient(45deg,rgba(255,255,255,.25) 0,rgba(255,255,255,.25) 3px,transparent 3px,transparent 7px)}
.ms-cell{text-align:center;line-height:32px;font-size:14px;color:#dc2626;font-weight:900}

/* 상태 배지 */
.sbadge{font-size:.5rem;padding:.04rem .26rem;border-radius:99px;font-weight:700;margin-left:.25rem;vertical-align:middle;white-space:nowrap}
.sb-done{background:#dcfce7;color:#166534}.sb-doing{background:#dbeafe;color:#1d4ed8}
.sb-review{background:#fef3c7;color:#92400e}.sb-todo{background:#f1f5f9;color:#94a3b8}

/* 담당자 칩 */
.owner-chip{display:inline-flex;align-items:center;font-size:.57rem;padding:.1rem .32rem;border-radius:99px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:78px}

/* JIRA 키 링크 */
.jkey{font-size:.55rem;font-family:Consolas,monospace;color:#94a3b8;text-decoration:none;transition:color .15s}
.jkey:hover{color:#2563eb}

.rl{display:flex;align-items:center;gap:.25rem;min-width:0}
.rpip{width:7px;height:7px;border-radius:50%;flex-shrink:0}
.rtxt{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1;min-width:0}
.chv{font-size:.55rem;cursor:pointer;user-select:none;transition:transform .2s;color:#94a3b8;flex-shrink:0}
.chv.o{transform:rotate(90deg)}
.hidden{display:none!important}
</style>
</head>
<body>

<!-- ══ 비밀번호 게이트 ══ -->
<div id="gate">
  <div class="gb">
    <div class="gb-logo">
      <div class="gb-logo-icon">📋</div>
      <div>
        <div class="gb-logo-text">%%WBS_PROJECT_NAME%%</div>
        <div class="gb-logo-sub">프로젝트 WBS 관리 시스템</div>
      </div>
    </div>
    <div class="gb-title">보안 로그인</div>
    <div class="gb-sub">%%WBS_GATE_SUB%%</div>
    <input type="password" id="pw" placeholder="비밀번호 입력" onkeydown="if(event.key==='Enter')auth()"/>
    <button onclick="auth()">입장하기 →</button>
    <div class="gb-err" id="gerr"></div>
    <div class="gb-footer">🔄 JIRA 전체 수집 · 데이터 기준일: %%SNAPSHOT_DATE%% · 최종: %%LAST_UPDATE%%</div>
  </div>
</div>

<!-- ══ 메인 ══ -->
<div id="main">

<header class="app-hdr">
  <h1>📋 %%WBS_PROJECT_NAME%%</h1>
  <span class="hbadge hb-b">%%WBS_PROJECT_NAME%% 프로젝트</span>
  <span class="hbadge hb-g" id="h-done">%%DONE%%/%%TOTAL%% 완료</span>
  <span class="hbadge hb-a" id="h-pct">%%PCT%%%</span>
  <a class="jira-btn" href="%%BOARD_URL%%" target="_blank">↗ JIRA 보드</a>
  <div class="sync">
    <span class="sdot"></span>
    <span>기준일</span>
    <select id="hdr-snap-sel" onchange="loadSnapshotByDate(this.value)" title="최근 10회 스냅샷 중 선택">
      <option value="">— 로딩 중 —</option>
    </select>
  </div>
</header>

<!-- 전체 진척률 배너 -->
<div class="prog-banner">
  <div class="pb-pct" id="pb-pct">%%PCT%%%</div>
  <div class="pb-info">
    <div class="pb-label">전체 진척률 (JIRA Task 기준)</div>
    <div class="pb-bar"><div class="pb-fill" id="pb-fill" style="width:%%PCT%%%"></div></div>
    <div class="pb-detail" id="pb-detail">
      <span class="pb-stat"><span class="pbs-dot" style="background:#22c55e"></span>완료 %%DONE%%</span>
      <span class="pb-stat"><span class="pbs-dot" style="background:#38bdf8"></span>진행 %%DOING%%</span>
      <span class="pb-stat"><span class="pbs-dot" style="background:#fbbf24"></span>검토 %%REVIEW%%</span>
      <span class="pb-stat"><span class="pbs-dot" style="background:#e2e8f0"></span>대기 %%TODO%%</span>
    </div>
  </div>
</div>

<!-- 6 영역 진척 카드 -->
<div class="area-cards" id="area-cards"></div>

<!-- 통계 스트립 -->
<div class="stats">
  <div class="stat"><div class="stat-v" id="s-t" style="color:#2563eb">%%TOTAL%%</div><div class="stat-l">전체 Task</div></div>
  <div class="stat"><div class="stat-v" id="s-d" style="color:#16a34a">%%DONE%%</div><div class="stat-l">완료</div></div>
  <div class="stat"><div class="stat-v" id="s-g" style="color:#2563eb">%%DOING%%</div><div class="stat-l">진행중</div></div>
  <div class="stat"><div class="stat-v" id="s-r" style="color:#d97706">%%REVIEW%%</div><div class="stat-l">검토중</div></div>
  <div class="stat"><div class="stat-v" id="s-n" style="color:#94a3b8">%%TODO%%</div><div class="stat-l">대기</div></div>
  <div class="stat"><div class="stat-v" style="color:#dc2626">%%MILESTONES%%</div><div class="stat-l">마일스톤</div></div>
  <div class="stat"><div class="stat-v" style="color:#7c3aed">%%TOTAL_WEEKS%%주</div><div class="stat-l">전체 기간</div></div>
</div>

<!-- 툴바 -->
<div class="toolbar">
  <span class="tb-grp">상태</span>
  <button class="tbtn on" id="f-all"    onclick="setF('all',this)">전체</button>
  <button class="tbtn"    id="f-todo"   onclick="setF('todo',this)">대기</button>
  <button class="tbtn"    id="f-doing"  onclick="setF('doing',this)">진행중</button>
  <button class="tbtn"    id="f-review" onclick="setF('review',this)">검토중</button>
  <button class="tbtn"    id="f-done"   onclick="setF('done',this)">완료</button>
  <div class="tsep"></div>
  <span class="tb-grp">영역</span>
  <button class="tbtn on" id="fa-all"    onclick="setA('all',this)">전체</button>
  <button class="tbtn"    id="fa-이지원" onclick="setA('이지원',this)">이지원</button>
  <button class="tbtn"    id="fa-인터넷웹" onclick="setA('인터넷웹',this)">인터넷웹</button>
  <button class="tbtn"    id="fa-콜센터" onclick="setA('콜센터',this)">콜센터</button>
  <button class="tbtn"    id="fa-인프라" onclick="setA('인프라',this)">인프라</button>
  <button class="tbtn"    id="fa-PMO"   onclick="setA('PMO',this)">PMO</button>
  <div class="tsep"></div>
  <button class="tbtn" onclick="expAll()">전체 펼치기</button>
  <button class="tbtn" onclick="colAll()">전체 접기</button>
  <div class="tsep"></div>
  <button class="tbtn accent" onclick="goToday()">📅 이번 주</button>
  <button class="tbtn excel" onclick="exportExcel()">📊 Excel</button>
  <div class="legend">
    <div class="leg"><div class="leg-sq" style="background:#3b82f6"></div>이지원</div>
    <div class="leg"><div class="leg-sq" style="background:#7c3aed"></div>인터넷웹</div>
    <div class="leg"><div class="leg-sq" style="background:#10b981"></div>콜센터</div>
    <div class="leg"><div class="leg-sq" style="background:#f59e0b"></div>인프라</div>
    <div class="leg"><div class="leg-sq" style="background:#64748b"></div>PMO</div>
    <div class="leg"><span style="color:#dc2626;font-size:11px">◆</span>마일스톤</div>
  </div>
</div>

<!-- 날짜 이동 -->
<div class="date-nav">
  <span class="tb-grp">WBS 기준일</span>
  <select id="snap-date-sel" onchange="loadSnapshotByDate(this.value)" style="padding:.25rem .5rem;border:1.5px solid #e2e8f0;border-radius:.28rem;font-size:.75rem;background:#fff;color:#1e293b;cursor:pointer;min-width:140px">
    <option value="">— 로딩 중 —</option>
  </select>
  <span class="tb-grp" style="margin-left:.2rem">(최근 10회, 최신순)</span>
  <div class="tsep"></div>
  📅 프로젝트: <strong id="date-range-label"></strong>
  <div class="tsep"></div>
  <div class="week-jump">
    <label>주차 이동:</label>
    <select id="weekSel" onchange="jumpToWeek(this.value)"></select>
  </div>
  <div class="tsep"></div>
  기간 필터:
  <select id="wfrom" onchange="renderReset()" style="padding:.2rem .5rem;border:1.5px solid #e2e8f0;border-radius:.28rem;font-size:.68rem;background:#fff;color:#1e293b;cursor:pointer"></select>
  ~
  <select id="wto"   onchange="render()" style="padding:.2rem .5rem;border:1.5px solid #e2e8f0;border-radius:.28rem;font-size:.68rem;background:#fff;color:#1e293b;cursor:pointer"></select>
  <button class="tbtn" onclick="resetWRange()" style="padding:.15rem .4rem;font-size:.62rem">전체보기</button>
  <div class="tsep"></div>
  <span id="today-info" style="color:#059669;font-weight:600"></span>
</div>

<!-- 간트 -->
<div class="gantt-scroll" id="gscroll">
  <table class="gtbl" id="gtbl"></table>
</div>

</div><!-- /main -->

<script>
// ═══ 상수 ════════════════════════════════════════════════════
const HASH          = "%%PW_HASH%%";
const TW            = %%TOTAL_WEEKS%%;
const PROJECT_START = new Date('%%PROJECT_START%%');
const TODAY         = new Date('%%TODAY_STR%%');
const TODAY_W_INIT  = %%TODAY_W%%;
const JIRA_BASE     = "%%JIRA_URL%%";
const MONTHS        = %%MONTHS_JSON%%;
const D             = %%D_JSON%%;

// ═══ 인증 ════════════════════════════════════════════════════
async function sha256(s){
  const b=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(s));
  return [...new Uint8Array(b)].map(x=>x.toString(16).padStart(2,'0')).join('');
}
async function auth(){
  const v=document.getElementById('pw').value;
  if(!v){setErr('비밀번호를 입력해주세요');return;}
  if(await sha256(v)===HASH){sessionStorage.setItem('wbs','1');open_main();}
  else{setErr('비밀번호가 올바르지 않습니다');document.getElementById('pw').value='';document.getElementById('pw').focus();}
}
function setErr(m){const e=document.getElementById('gerr');e.textContent=m;setTimeout(()=>e.textContent='',2500)}
function open_main(){
  document.getElementById('gate').style.display='none';
  document.getElementById('main').style.display='block';
  init();
}
if(sessionStorage.getItem('wbs')==='1') open_main();
else document.getElementById('pw').focus();

// ═══ 유틸 ════════════════════════════════════════════════════
function weekStartDate(w){const d=new Date(PROJECT_START);d.setDate(d.getDate()+(w-1)*7);return d;}
function fmtDate(d){return `${d.getMonth()+1}/${d.getDate()}`;}
function fmtDateFull(d){return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;}

const AC   ={이지원:'#3b82f6',인터넷웹:'#7c3aed',콜센터:'#10b981',인프라:'#f59e0b',PMO:'#64748b'};
const ACbg ={이지원:'#eff6ff',인터넷웹:'#f5f3ff',콜센터:'#ecfdf5',인프라:'#fffbeb',PMO:'#f8fafc'};
const ACtc ={이지원:'#1d4ed8',인터넷웹:'#6d28d9',콜센터:'#065f46',인프라:'#b45309',PMO:'#475569'};
const SL   ={done:'완료',doing:'진행중',review:'검토중',todo:'대기'};
const SC   ={done:'sb-done',doing:'sb-doing',review:'sb-review',todo:'sb-todo'};

// 스냅샷 이슈 → D 배열 (이력과 동일 로직, 기존 스냅샷으로 조회)
function dateToWeek(ds){ if(!ds)return null; const d=new Date(ds),delta=Math.floor((d-PROJECT_START)/86400000); if(delta<0)return 1; return Math.min(Math.floor(delta/7)+1,TW); }
function detectAreaSnap(summary,labels,components){ const txt=[summary,...(labels||[]),...(components||[])].join(' ').toLowerCase(); if(['이지원','마이다스','법인','ocr','챗봇','팩토리','상품','app','고도화'].some(k=>txt.includes(k)))return '이지원'; if(['사이버','보안','사이버보증','인터넷','웹'].some(k=>txt.includes(k)))return '인터넷웹'; if(['콜센터','상담','ars','보이는ars'].some(k=>txt.includes(k)))return '콜센터'; if(['인프라','서버','소스코드','응답시간','성능','형상'].some(k=>txt.includes(k)))return '인프라'; return 'PMO'; }
function mapStatusSnap(s){ s=(s||'').toLowerCase(); if(['done','complete','closed','resolved','완료','종료'].some(x=>s.includes(x)))return 'done'; if(['review','qa','검토','리뷰'].some(x=>s.includes(x)))return 'review'; if(['progress','develop','진행','개발'].some(x=>s.includes(x)))return 'doing'; return 'todo'; }
function issueToTaskSnap(iss,wbsId){ const sw=dateToWeek(iss.start_date)||1,ew=dateToWeek(iss.due_date)||sw; return {id:wbsId,jiraKey:iss.key,jiraUrl:JIRA_BASE?JIRA_BASE+'/browse/'+iss.key:'',n:iss.summary,t:'t',area:detectAreaSnap(iss.summary,iss.labels,iss.components),owner:iss.assignee||'',priority:iss.priority||'',s:sw,e:ew,st:mapStatusSnap(iss.status),sd:iss.start_date,ed:iss.due_date}; }
function buildDFromSnapshot(issues){ const epicIssues={},nonEpics=[]; issues.forEach(i=>{ if((i.issue_type||'').toLowerCase()==='epic')epicIssues[i.key]=i; else if((i.issue_type||'').toLowerCase()!=='sub-task')nonEpics.push(i); }); const hasEpics=Object.keys(epicIssues).length>0; const D=[]; if(hasEpics){ const epicMap={}; const unassigned=[]; Object.keys(epicIssues).forEach(k=>epicMap[k]=[]); nonEpics.forEach(iss=>{ const ek=iss.epic_link||(iss.parent_key&&epicIssues[iss.parent_key]?iss.parent_key:null); if(ek&&epicMap[ek])epicMap[ek].push(iss); else unassigned.push(iss); }); if(unassigned.length){ const tasks=unassigned.map((iss,j)=>issueToTaskSnap(iss,'0.'+(j+1))); const sw2=Math.min(...tasks.map(t=>t.s)),ew2=Math.max(...tasks.map(t=>t.e)); D.push({id:'P0',n:'미분류',t:'p',area:'PMO',owner:'',s:sw2,e:ew2,st:'todo'}); D.push(...tasks); } let pi=1; Object.entries(epicIssues).forEach(([k,epic])=>{ const tasks=epicMap[k]||[]; const taskRows=tasks.map((iss,j)=>issueToTaskSnap(iss,pi+'.'+(j+1))); const sw=dateToWeek(epic.start_date)||1,ew=dateToWeek(epic.due_date)||sw; const tsw=taskRows.length?Math.min(...taskRows.map(t=>t.s)):sw,tew=taskRows.length?Math.max(...taskRows.map(t=>t.e)):ew; D.push({id:'P'+pi,jiraKey:k,jiraUrl:JIRA_BASE?JIRA_BASE+'/browse/'+k:'',n:epic.summary,t:'p',area:detectAreaSnap(epic.summary,epic.labels,epic.components),owner:epic.assignee,priority:epic.priority||'',s:Math.min(sw,tsw),e:Math.max(ew,tew),st:mapStatusSnap(epic.status)}); D.push(...taskRows); pi++; }); }else{ const topLevel=[],children={}; issues.forEach(iss=>{ if(iss.parent_key)children[iss.parent_key]=(children[iss.parent_key]||[]).concat([iss]); else topLevel.push(iss); }); topLevel.forEach((par,i)=>{ const kids=children[par.key]||[]; const tasks=kids.length?kids.map((k,j)=>issueToTaskSnap(k,(i+1)+'.'+(j+1))):[issueToTaskSnap(par,(i+1)+'.1')]; const sw=dateToWeek(par.start_date)||1,ew=dateToWeek(par.due_date)||sw; const tsw=Math.min(...tasks.map(t=>t.s)),tew=Math.max(...tasks.map(t=>t.e)); D.push({id:'P'+(i+1),jiraKey:par.key,jiraUrl:JIRA_BASE?JIRA_BASE+'/browse/'+par.key:'',n:par.summary,t:'p',area:detectAreaSnap(par.summary,par.labels,par.components),owner:par.assignee,priority:par.priority||'',s:Math.min(sw,tsw),e:Math.max(ew,tew),st:mapStatusSnap(par.status)}); D.push(...tasks); }); } return D; }

// ═══ 초기화 ══════════════════════════════════════════════════
function initSelects(){
  const sel=document.getElementById('weekSel');
  const wf=document.getElementById('wfrom');
  const wt=document.getElementById('wto');
  sel.innerHTML='<option value="">주차 선택</option>';
  wf.innerHTML=''; wt.innerHTML='';
  MONTHS.forEach(m=>{
    for(let w=m.s;w<=m.e;w++){
      const d=weekStartDate(w);
      const lbl=`W${w} — ${m.n} ${fmtDate(d)}`;
      sel.insertAdjacentHTML('beforeend',`<option value="${w}">${lbl}</option>`);
      wf.insertAdjacentHTML('beforeend',`<option value="${w}">W${w} (${fmtDate(d)}~)</option>`);
      wt.insertAdjacentHTML('beforeend',`<option value="${w}">W${w} (~${fmtDate(new Date(d.getTime()+6*86400000))})</option>`);
    }
  });
  document.getElementById('wto').value=TW;
  // 날짜 범위 레이블
  const ps=weekStartDate(1), pe=weekStartDate(TW); pe.setDate(pe.getDate()+6);
  document.getElementById('date-range-label').textContent=`${fmtDateFull(ps)} ~ ${fmtDateFull(pe)} (${TW}주)`;
  // 현재 주 표시
  const ti=document.getElementById('today-info');
  if(TODAY_W_INIT>=1&&TODAY_W_INIT<=TW)
    ti.textContent=`🗓 현재: W${TODAY_W_INIT} (${fmtDate(TODAY)})`;
  else if(TODAY_W_INIT<1)
    ti.textContent=`🗓 프로젝트 시작 전`,ti.style.color='#7c3aed';
}

// ═══ 스냅샷 기준 통계 갱신 ═════════════════════════════════════
function updateStats(){
  const tasks=D.filter(r=>r.t==='t');
  const total=tasks.length;
  const done=tasks.filter(r=>r.st==='done').length;
  const doing=tasks.filter(r=>r.st==='doing').length;
  const review=tasks.filter(r=>r.st==='review').length;
  const todo=tasks.filter(r=>r.st==='todo').length;
  const pct=total?Math.round(done/total*100):0;
  const el=(id)=>document.getElementById(id);
  if(el('s-t'))el('s-t').textContent=total;
  if(el('s-d'))el('s-d').textContent=done;
  if(el('s-g'))el('s-g').textContent=doing;
  if(el('s-r'))el('s-r').textContent=review;
  if(el('s-n'))el('s-n').textContent=todo;
  if(el('pb-pct'))el('pb-pct').textContent=pct+'%';
  if(el('pb-fill'))el('pb-fill').style.width=pct+'%';
  if(el('h-done'))el('h-done').textContent=done+'/'+total+' 완료';
  if(el('h-pct'))el('h-pct').textContent=pct+'%';
  const pd=el('pb-detail');
  if(pd)pd.innerHTML='<span class="pb-stat"><span class="pbs-dot" style="background:#22c55e"></span>완료 '+done+'</span><span class="pb-stat"><span class="pbs-dot" style="background:#38bdf8"></span>진행 '+doing+'</span><span class="pb-stat"><span class="pbs-dot" style="background:#fbbf24"></span>검토 '+review+'</span><span class="pb-stat"><span class="pbs-dot" style="background:#e2e8f0"></span>대기 '+todo+'</span>';
}

// ═══ 영역 카드 ═══════════════════════════════════════════════
function renderAreaCards(){
  const tasks=D.filter(r=>r.t==='t');
  const AREAS=['이지원','인터넷웹','콜센터','인프라','PMO'];
  const NAMES={이지원:'이지원 시스템',인터넷웹:'인터넷웹',콜센터:'콜센터',인프라:'공통 인프라',PMO:'PMO'};
  const el=document.getElementById('area-cards');
  el.innerHTML='';
  AREAS.forEach(area=>{
    const at=tasks.filter(r=>r.area===area);
    const adn=at.filter(r=>r.st==='done').length;
    const adg=at.filter(r=>r.st==='doing').length;
    const ap=at.length?Math.round(adn/at.length*100):0;
    const col=AC[area]||'#64748b', bg=ACbg[area]||'#f8fafc', tc=ACtc[area]||'#475569';
    const isActive=(curArea===area);
    const card=document.createElement('div');
    card.className='ac'+(isActive?' active':'');
    card.style.cssText=`background:${bg};color:${tc};${isActive?'border-color:'+col:'border-color:transparent'}`;
    card.onclick=()=>setA(curArea===area?'all':area,null);
    card.innerHTML=`<div class="ac-label">${NAMES[area]||area}</div><div class="ac-pct" style="color:${col}">${ap}%</div><div class="ac-counts">${adn}/${at.length} 완료 · 진행 ${adg}</div><div class="ac-bar"><div class="ac-fill" style="width:${ap}%;background:${col}"></div></div>`;
    el.appendChild(card);
  });
}

// ═══ 간트 렌더링 ═════════════════════════════════════════════
const pOpen={};
D.filter(r=>r.t==='p').forEach(r=>pOpen[r.id]=true);
let flt='all', curArea='all';

function getWRange(){
  return{from:parseInt(document.getElementById('wfrom')?.value||1),to:parseInt(document.getElementById('wto')?.value||TW)};
}
function resetWRange(){document.getElementById('wfrom').value=1;document.getElementById('wto').value=TW;render();}

function render(){
  renderAreaCards();
  const tbl=document.getElementById('gtbl');
  tbl.innerHTML='';
  const{from,to}=getWRange();
  const thead=tbl.createTHead();

  // 헤더 행1 : 월
  const hr1=thead.insertRow();
  hr1.innerHTML='<th class="th-id" rowspan="2">ID</th><th class="th-nm" rowspan="2">작업명 / JIRA 이슈</th><th class="th-ow" rowspan="2">담당</th><th class="th-sd" rowspan="2">시작일</th><th class="th-ed" rowspan="2">종료일</th>';
  MONTHS.forEach(m=>{
    const vs=Math.max(m.s,from), ve=Math.min(m.e,to);
    if(vs>ve) return;
    const th=document.createElement('th');
    th.className='th-mo'; th.colSpan=ve-vs+1; th.textContent='2026년 '+m.n;
    hr1.appendChild(th);
  });

  // 작업명 열 리사이즈 핸들
  const thNm=tbl.querySelector('.th-nm');
  if(thNm){
    thNm.style.position='relative';
    let handle=thNm.querySelector('.col-resize');
    if(!handle){handle=document.createElement('div');handle.className='col-resize';handle.title='드래그하여 작업명 열 너비 조절';thNm.appendChild(handle);}
    handle.onmousedown=function(e){e.preventDefault();const startX=e.clientX;const startW=parseInt(getComputedStyle(document.documentElement).getPropertyValue('--col-nm-w')||'320',10)||320;function move(e2){const dx=e2.clientX-startX;let w=Math.max(260,Math.min(600,startW+dx));document.documentElement.style.setProperty('--col-nm-w',w+'px');}function up(){document.removeEventListener('mousemove',move);document.removeEventListener('mouseup',up);}document.addEventListener('mousemove',move);document.addEventListener('mouseup',up);};
  }

  // 헤더 행2 : 주차
  const hr2=thead.insertRow();
  for(let w=from;w<=to;w++){
    const d=weekStartDate(w);
    const th=document.createElement('th');
    const de=new Date(d.getTime()+6*86400000);
    const eSuffix=d.getMonth()===de.getMonth()?`${de.getDate()}`:`${de.getMonth()+1}/${de.getDate()}`;
    th.className='th-w'+(w===TODAY_W_INIT?' th-w-now':w<TODAY_W_INIT?' th-w-past':'');
    th.innerHTML=`<div class="th-w-num">W${w}</div><div class="th-w-dt">${fmtDate(d)}~${eSuffix}</div>`;
    th.title=`W${w}: ${fmtDate(d)} ~ ${fmtDate(de)}`;
    hr2.appendChild(th);
  }

  // 바디
  const tbody=tbl.createTBody();
  let curP=null;
  D.forEach(row=>{
    if(row.t==='p') curP=row.id;
    if(curArea!=='all'&&row.t==='t'&&row.area!==curArea) return;
    if(curArea!=='all'&&row.t==='m') return;
    if(flt!=='all'&&row.t==='t'&&row.st!==flt) return;
    if(flt!=='all'&&row.t==='m') return;
    if(row.t==='t'&&(row.e<from||row.s>to)) return;
    if(row.t==='m'&&(row.s<from||row.s>to)) return;

    const isChild=row.t==='t'||row.t==='m';
    const hide=isChild&&curP&&!pOpen[curP];
    const tr=tbody.insertRow();
    tr.className='r-'+{p:'phase',t:'task',m:'ms'}[row.t]+(hide?' hidden':'');
    if(isChild) tr.dataset.ph=curP;

    // ID 셀
    const tdi=tr.insertCell(); tdi.className='td-id';
    if(row.t==='p'){
      const cv=document.createElement('span');
      cv.className='chv'+(pOpen[row.id]?' o':'');
      cv.textContent='▶'; cv.onclick=()=>togP(row.id);
      tdi.appendChild(cv);
      tdi.append(' '+row.id);
      tdi.style.cssText='color:#475569;font-weight:700';
    } else {
      tdi.innerHTML=`<span style="color:#e2e8f0">└</span> ${row.id}`;
    }

    // Name 셀
    const tdn=tr.insertCell(); tdn.className='td-nm';
    const c=AC[row.area]||'#94a3b8';
    const rl=document.createElement('div'); rl.className='rl';
    const pip=document.createElement('div'); pip.className='rpip';
    if(row.t==='m'){
      pip.style.cssText='background:#fbbf24;border-radius:2px';
      rl.appendChild(pip);
      const sp=document.createElement('span');
      sp.style.cssText='color:#b45309;font-weight:700;font-size:.76rem';
      sp.textContent='◆ '+row.n.replace('◆ ','');
      rl.appendChild(sp);
    } else {
      pip.style.background=c; rl.appendChild(pip);
      const sp=document.createElement('span'); sp.className='rtxt';
      if(row.t==='p') sp.style.cssText='font-weight:700;font-size:.79rem;color:#1e293b';
      else sp.style.color='#334155';
      sp.textContent=row.n;
      rl.appendChild(sp);
      if(row.jiraKey&&row.jiraUrl){
        const a=document.createElement('a');
        a.className='jkey'; a.href=row.jiraUrl; a.target='_blank';
        a.textContent=row.jiraKey; a.title='JIRA에서 열기';
        a.onclick=e=>e.stopPropagation();
        rl.appendChild(a);
      }
      if(row.t==='t'){
        const bd=document.createElement('span');
        bd.className='sbadge '+SC[row.st]; bd.textContent=SL[row.st];
        rl.appendChild(bd);
      }
    }
    tdn.title=row.n+(row.jiraKey?' ['+row.jiraKey+']':'');
    tdn.appendChild(rl);

    // 담당 셀
    const tdow=tr.insertCell(); tdow.className='td-ow';
    if(row.owner){
      const chip=document.createElement('span');
      chip.className='owner-chip';
      chip.style.cssText=`background:${ACbg[row.area]||'#f8fafc'};color:${ACtc[row.area]||'#475569'}`;
      chip.textContent=row.owner; chip.title=row.owner;
      tdow.appendChild(chip);
    }

    // 시작일 셀
    const tdsd=tr.insertCell(); tdsd.className='td-sd';
    const startStr=row.sd||(row.s?fmtDateFull(weekStartDate(row.s)):'');
    tdsd.textContent=startStr; if(startStr)tdsd.title=startStr;

    // 종료일 셀
    const tded=tr.insertCell(); tded.className='td-ed';
    const endStr=row.ed||(row.e?fmtDateFull(new Date(weekStartDate(row.e).getTime()+6*86400000)):'');
    tded.textContent=endStr; if(endStr)tded.title=endStr;

    // 주차 셀
    for(let w=from;w<=to;w++){
      const td=tr.insertCell();
      const isPast=w<TODAY_W_INIT, isNow=w===TODAY_W_INIT;
      td.className='td-w'+(isNow?' col-now':isPast?' col-past':'');
      if(row.t==='m'){
        if(w===row.s){td.className+=' ms-cell';td.textContent='◆';td.title=`◆ ${row.n}\n${fmtDate(weekStartDate(w))}`;}
      } else if(w>=row.s&&w<=row.e){
        const isSE=row.s===row.e, isS=w===row.s, isE=w===row.e, isP=row.t==='p';
        const div=document.createElement('div');
        let cls=isP?'bph':'bar';
        if(isSE) cls+=' bar-se'; else if(isS) cls+=' bar-s'; else if(isE) cls+=' bar-e';
        div.className=cls; div.style.background=c;
        if(!isP&&row.st==='done') div.classList.add('bar-done');
        td.appendChild(div);
        if(isS){
          const sd=weekStartDate(row.s), ed=new Date(weekStartDate(row.e));
          ed.setDate(ed.getDate()+6);
          const jiraDate=row.sd?`\nJIRA 날짜: ${row.sd} ~ ${row.ed||'미정'}`:'';
          td.title=`${row.id}: ${row.n}${row.jiraKey?' ['+row.jiraKey+']':''}\n담당: ${row.owner||'-'}${jiraDate}\nWBS: W${row.s}~W${row.e} (${fmtDate(sd)}~${fmtDate(ed)}, ${row.e-row.s+1}주)\n영역: ${row.area} | 상태: ${SL[row.st]||''}`;
          td.style.cursor='help';
        }
      }
    }
  });
  requestAnimationFrame(updateLayout);
}

// ═══ 컨트롤 ══════════════════════════════════════════════════
function togP(pid){pOpen[pid]=!pOpen[pid];render();}
function setF(f,btn){flt=f;['all','todo','doing','review','done'].forEach(x=>document.getElementById('f-'+x)?.classList.toggle('on',x===f));render();}
function setA(a,btn){curArea=a;['all','이지원','인터넷웹','콜센터','인프라','PMO'].forEach(x=>document.getElementById('fa-'+x)?.classList.toggle('on',x===a));render();}
function expAll(){D.filter(r=>r.t==='p').forEach(r=>pOpen[r.id]=true);render();}
function colAll(){D.filter(r=>r.t==='p').forEach(r=>pOpen[r.id]=false);render();}
function renderReset(){render();document.getElementById('gscroll').scrollLeft=0;}

// ═══ 레이아웃 (sticky + 반응형) ════════════════════════════
function updateLayout(){
  const hdrEl=document.querySelector('.app-hdr');
  const tbEl=document.querySelector('.toolbar');
  const dnEl=document.querySelector('.date-nav');
  const gs=document.getElementById('gscroll');
  if(!hdrEl||!tbEl||!dnEl||!gs) return;
  const hdrH=hdrEl.offsetHeight;
  const tbH=tbEl.offsetHeight;
  const dnH=dnEl.offsetHeight;
  tbEl.style.top=hdrH+'px';
  dnEl.style.top=(hdrH+tbH)+'px';
  const total=hdrH+tbH+dnH;
  gs.style.height='calc(100vh - '+total+'px)';
  gs.style.minHeight='300px';
  const row1El=document.querySelector('.gtbl thead tr');
  if(row1El){
    const row1H=Math.ceil(row1El.getBoundingClientRect().height)||28;
    document.querySelectorAll('.th-w').forEach(th=>th.style.top=row1H+'px');
  }
}
window.addEventListener('resize',updateLayout);

function goToday(){jumpToWeek(Math.max(1,TODAY_W_INIT||1));}
function jumpToWeek(w){
  w=parseInt(w); if(!w) return;
  const{from}=getWRange();
  document.getElementById('gscroll').scrollTo({left:Math.max(0,(w-from)*52-100),behavior:'smooth'});
  document.getElementById('weekSel').value=w;
}

// ═══ Excel 내보내기 (웹 화면 그대로: ID·작업명·담당·시작일·종료일 순) ═══════════════════════════════════════════
function exportExcel(){
  if(typeof XLSX==='undefined'){alert('SheetJS 로딩 중입니다.');return;}
  const wb=XLSX.utils.book_new();
  // Sheet1: 웹 보기와 동일 — 화면 테이블과 같은 열 순서
  const h1=['ID','작업명','JIRA Key','담당','시작일','종료일','구분','업무영역','상태','기간(주)'];
  const rows=D.map(r=>{
    const sd=r.sd||(r.s?fmtDateFull(weekStartDate(r.s)):''),ed=r.ed||(r.e?fmtDateFull(new Date(weekStartDate(r.e).getTime()+6*86400000)):'');
    return[r.id,r.n,r.jiraKey||'',r.owner||'',sd,ed,{p:'Phase',t:'Task',m:'Milestone'}[r.t],r.area,SL[r.st]||r.st,r.t==='m'?0:r.e-r.s+1];
  });
  const ws1=XLSX.utils.aoa_to_sheet([h1,...rows]);
  ws1['!cols']=[{wch:10},{wch:48},{wch:14},{wch:12},{wch:12},{wch:12},{wch:8},{wch:10},{wch:8},{wch:8}];
  ws1['!freeze']={xSplit:0,ySplit:1};
  XLSX.utils.book_append_sheet(wb,ws1,'웹 보기와 동일');
  // Sheet2: 상세 (기존 WBS 전체)
  const h2=['ID','JIRA Key','구분','작업명','업무영역','담당자','우선순위','상태','시작주','종료주','기간(주)','시작일','종료일'];
  const rows2=D.map(r=>{
    const sd=weekStartDate(r.s),ed=new Date(weekStartDate(r.e));ed.setDate(ed.getDate()+6);
    return[r.id,r.jiraKey||'',{p:'Phase',t:'Task',m:'Milestone'}[r.t],r.n,r.area,r.owner||'',r.priority||'',SL[r.st]||r.st,r.s,r.e,r.e-r.s+1,fmtDateFull(sd),fmtDateFull(ed)];
  });
  const ws2=XLSX.utils.aoa_to_sheet([h2,...rows2]);
  ws2['!cols']=[{wch:10},{wch:14},{wch:8},{wch:48},{wch:10},{wch:14},{wch:10},{wch:8},{wch:7},{wch:7},{wch:8},{wch:12},{wch:12}];
  XLSX.utils.book_append_sheet(wb,ws2,'WBS 상세');
  // Sheet3: Phase별
  const hPhase=['Phase','JIRA Key','Phase명','전체','완료','진행중','검토중','대기','진척률(%)'];
  let cp=null;const pm={};
  D.forEach(r=>{if(r.t==='p'){cp=r.id;pm[r.id]={ph:r,kids:[]};}else if(r.t==='t'&&cp)pm[cp].kids.push(r);});
  const pr2=Object.values(pm).map(({ph,kids})=>{
    const tot=kids.length,dn=kids.filter(k=>k.st==='done').length,dg=kids.filter(k=>k.st==='doing').length,rv=kids.filter(k=>k.st==='review').length,td=kids.filter(k=>k.st==='todo').length;
    return[ph.id,ph.jiraKey||'',ph.n,tot,dn,dg,rv,td,tot?Math.round(dn/tot*100):0];
  });
  const wsPhase=XLSX.utils.aoa_to_sheet([hPhase,...pr2]);
  wsPhase['!cols']=[{wch:6},{wch:12},{wch:20},{wch:6},{wch:6},{wch:6},{wch:6},{wch:6},{wch:8}];
  XLSX.utils.book_append_sheet(wb,wsPhase,'Phase 진척');
  // Sheet4: 담당자별
  const h3=['담당자','소속영역','담당 Task수','완료','진행중','대기','진척률(%)'];
  const om={};
  D.filter(r=>r.t==='t').forEach(r=>{const k=r.owner||'미지정';if(!om[k])om[k]={owner:k,area:r.area,tasks:[]};om[k].tasks.push(r);});
  const pr3=Object.values(om).map(({owner,area,tasks})=>{
    const tot=tasks.length,dn=tasks.filter(k=>k.st==='done').length,dg=tasks.filter(k=>k.st==='doing').length,td=tasks.filter(k=>k.st==='todo').length;
    return[owner,area,tot,dn,dg,td,tot?Math.round(dn/tot*100):0];
  });
  const ws3=XLSX.utils.aoa_to_sheet([h3,...pr3]);
  ws3['!cols']=[{wch:14},{wch:10},{wch:10},{wch:6},{wch:6},{wch:6},{wch:8}];
  XLSX.utils.book_append_sheet(wb,ws3,'담당자별');
  // Sheet5: 마일스톤
  const h4=['ID','JIRA Key','마일스톤명','주차','예정일','담당','상태'];
  const pr4=D.filter(r=>r.t==='m').map(r=>[r.id,r.jiraKey||'',(r.n||'').replace(/^◆\\s*/, ''),r.s,fmtDateFull(weekStartDate(r.s)),r.owner||'',SL[r.st]||r.st]);
  const ws4=XLSX.utils.aoa_to_sheet([h4,...pr4]);
  ws4['!cols']=[{wch:10},{wch:14},{wch:45},{wch:6},{wch:12},{wch:12},{wch:8}];
  XLSX.utils.book_append_sheet(wb,ws4,'마일스톤');
  XLSX.writeFile(wb,'WBS_%%WBS_EXCEL_NAME%%_'+new Date().toISOString().slice(0,10)+'.xlsx');
}

// ═══ 스냅샷 날짜 선택 시 해당 WBS 로드 ══════════════════════════════════════════════════
async function loadSnapshotByDate(date){
  if(!date)return;
  try{
    const r=await fetch('./data/snapshots/'+date+'.json');
    const snap=await r.json();
    if(snap.issues&&snap.issues.length>0){
      const newD=buildDFromSnapshot(snap.issues);
      D.length=0; D.push(...newD);
      D.filter(r=>r.t==='p').forEach(r=>pOpen[r.id]=true);
      updateStats();
      render();
      const hdrSel=document.getElementById('hdr-snap-sel');
      const navSel=document.getElementById('snap-date-sel');
      if(hdrSel&&hdrSel.value!==date)hdrSel.value=date;
      if(navSel&&navSel.value!==date)navSel.value=date;
      if(TODAY_W_INIT>=1&&TODAY_W_INIT<=TW) setTimeout(()=>jumpToWeek(TODAY_W_INIT),100);
    }
  }catch(e){ console.error('스냅샷 로드 실패:',e); }
}

// ═══ 초기화 (snapshots 폴더 최근 10개 날짜 중 선택해 조회) ══════════════════════════════════════════════════
function fillSnapshotSelects(list){
  const hdrSel=document.getElementById('hdr-snap-sel');
  const navSel=document.getElementById('snap-date-sel');
  const opts=[]; list.forEach(s=>{opts.push({value:s.date,text:s.date+' ('+(s.count||0)+'건)'});});
  [hdrSel,navSel].filter(Boolean).forEach(sel=>{
    sel.innerHTML='';
    if(!opts.length){sel.innerHTML='<option value="">— 스냅샷 없음 —</option>';return;}
    opts.forEach(({value,text})=>{const o=document.createElement('option');o.value=value;o.textContent=text;sel.appendChild(o);});
  });
}
async function init(){
  const hdrSel=document.getElementById('hdr-snap-sel');
  const navSel=document.getElementById('snap-date-sel');
  try{
    const r=await fetch('./data/snapshots/index.json');
    const idx=await r.json();
    const list=idx.snapshots&&idx.snapshots.length?idx.snapshots.slice(0,10):[];
    fillSnapshotSelects(list);
    if(list.length>0){
      const firstDate=list[0].date;
      if(hdrSel)hdrSel.value=firstDate;
      if(navSel)navSel.value=firstDate;
      await loadSnapshotByDate(firstDate);
    }
  }catch(e){
    if(hdrSel)hdrSel.innerHTML='<option value="">— 로드 실패 —</option>';
    if(navSel)navSel.innerHTML='<option value="">— 로드 실패 —</option>';
  }
  initSelects();
  if(D.length>0){ updateStats(); render(); }
  if(TODAY_W_INIT>=1&&TODAY_W_INIT<=TW) setTimeout(()=>jumpToWeek(TODAY_W_INIT),400);
}
</script>
</body>
</html>"""


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    client = JiraClient()
    ptype  = client.project_type()
    print(f"📡 JIRA [{PROJECT_KEY}] 데이터 수집 중... (유형: {ptype})")

    # 시작일 커스텀 필드 자동 탐색
    start_field = client.discover_start_field()
    if start_field not in JIRA_FIELDS:
        JIRA_FIELDS.append(start_field)
        START_DATE_CANDIDATES.insert(0, start_field)

    # JIRA 프로젝트 전체 이슈 1회 fetch (날짜별 이력용 스냅샷 + index.html 구성)
    # MCP 테스트 결과 따옴표 없는 JQL이 안정적
    all_issues = client.search(
        f'project = {PROJECT_KEY} ORDER BY created ASC',
        max_results=10000
    )
    print(f"  • JIRA 전체 이슈: {len(all_issues)}개")

    # 일별 스냅샷 저장
    snap_path = save_snapshot(all_issues)
    print(f"📸 스냅샷 저장: {snap_path}")

    # WBS D 배열 생성
    D = build_d_array(all_issues, ptype)

    tasks = [r for r in D if r["t"] == "t"]
    done  = sum(1 for t in tasks if t["st"] == "done")
    print(f"✅ 수집 완료: Phase {sum(1 for r in D if r['t']=='p')}개 / Task {len(tasks)}개 (완료 {done}개)")

    # docs/index.html 생성 (데이터는 스냅샷에서 로드하므로 초기 D는 빈 배열로 생성해 용량 절감)
    snapshot_date = today_str()
    html = build_html([], snapshot_date=snapshot_date)
    os.makedirs(os.path.dirname(OUTPUT_PATH) or ".", exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"📄 생성: {OUTPUT_PATH}  ({len(html):,} bytes)")

    # docs/history.html 생성
    history_html = build_history_html()
    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
        f.write(history_html)
    print(f"📅 이력 뷰어: {HISTORY_PATH}  ({len(history_html):,} bytes)")


if __name__ == "__main__":
    main()
