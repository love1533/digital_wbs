"""Demo web app for repo_llm library."""

from __future__ import annotations

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import json

from repo_llm.prompt import PromptTemplate, load_template_from_file
from repo_llm.memory import ConversationMemory
from repo_llm.utils import estimate_tokens, chunk_text, extract_json, truncate
from repo_llm.cache import InMemoryCache
from repo_llm.client import CompletionResponse

app = FastAPI(title="repo_llm Demo")

# Global in-memory conversation store per session (demo only)
_memory = ConversationMemory(max_tokens=500, system_prompt="You are a helpful assistant.")
_cache: InMemoryCache = InMemoryCache(max_size=32, ttl_seconds=300)

HTML = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>repo_llm Demo</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: 'Segoe UI', system-ui, sans-serif; background: #0f172a; color: #e2e8f0; min-height: 100vh; }
  header { background: linear-gradient(135deg, #1e293b, #0f172a); border-bottom: 1px solid #334155; padding: 1.5rem 2rem; display: flex; align-items: center; gap: 1rem; }
  header h1 { font-size: 1.5rem; font-weight: 700; color: #38bdf8; }
  header span { color: #64748b; font-size: 0.875rem; }
  .badge { background: #1e3a5f; color: #38bdf8; font-size: 0.75rem; padding: 0.25rem 0.75rem; border-radius: 9999px; border: 1px solid #1d4ed8; }
  .container { max-width: 1100px; margin: 0 auto; padding: 2rem; display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; }
  .card { background: #1e293b; border: 1px solid #334155; border-radius: 0.75rem; padding: 1.5rem; }
  .card h2 { font-size: 1rem; font-weight: 600; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 1rem; display: flex; align-items: center; gap: 0.5rem; }
  .card h2 .tag { background: #0f172a; border: 1px solid #334155; border-radius: 0.375rem; padding: 0.125rem 0.5rem; font-size: 0.65rem; color: #64748b; }
  label { display: block; font-size: 0.8rem; color: #94a3b8; margin-bottom: 0.4rem; margin-top: 0.8rem; }
  input, textarea, select { width: 100%; background: #0f172a; border: 1px solid #334155; border-radius: 0.375rem; color: #e2e8f0; padding: 0.5rem 0.75rem; font-size: 0.875rem; font-family: inherit; }
  textarea { resize: vertical; min-height: 80px; }
  input:focus, textarea:focus { outline: none; border-color: #38bdf8; }
  button { margin-top: 1rem; background: #1d4ed8; color: #fff; border: none; border-radius: 0.375rem; padding: 0.6rem 1.25rem; font-size: 0.875rem; cursor: pointer; font-weight: 600; transition: background 0.15s; }
  button:hover { background: #2563eb; }
  .result { margin-top: 1rem; background: #0f172a; border: 1px solid #334155; border-radius: 0.375rem; padding: 0.75rem 1rem; font-size: 0.85rem; color: #a5f3fc; white-space: pre-wrap; word-break: break-all; min-height: 3rem; font-family: 'Cascadia Code', 'Fira Code', monospace; }
  .result.error { color: #f87171; border-color: #7f1d1d; }
  .stat { display: inline-block; background: #0f172a; border: 1px solid #334155; border-radius: 0.375rem; padding: 0.25rem 0.75rem; margin: 0.25rem; font-size: 0.8rem; color: #94a3b8; }
  .stat strong { color: #38bdf8; }
  .full-width { grid-column: 1 / -1; }
  .tabs { display: flex; gap: 0.5rem; margin-bottom: 1rem; }
  .tab { background: #0f172a; border: 1px solid #334155; border-radius: 0.375rem; padding: 0.35rem 0.9rem; font-size: 0.8rem; cursor: pointer; color: #64748b; transition: all 0.15s; }
  .tab.active { background: #1d4ed8; color: #fff; border-color: #1d4ed8; }
  .msg-list { display: flex; flex-direction: column; gap: 0.5rem; max-height: 200px; overflow-y: auto; }
  .msg { padding: 0.5rem 0.75rem; border-radius: 0.5rem; font-size: 0.85rem; }
  .msg.user { background: #1e3a5f; color: #bae6fd; align-self: flex-end; max-width: 80%; }
  .msg.assistant { background: #1e293b; border: 1px solid #334155; color: #e2e8f0; align-self: flex-start; max-width: 80%; }
  .msg.system { background: #1a1a2e; border: 1px solid #4c1d95; color: #a78bfa; font-size: 0.75rem; text-align: center; }
</style>
</head>
<body>
<header>
  <h1>⚡ repo_llm</h1>
  <span>LLM 유틸리티 라이브러리 데모</span>
  <span class="badge">v0.1.0</span>
  <span class="badge">테스트 커버리지 98%</span>
</header>
<div class="container">

  <!-- PromptTemplate -->
  <div class="card">
    <h2>🔤 PromptTemplate <span class="tag">prompt.py</span></h2>
    <form action="/prompt/render" method="post">
      <label>템플릿 (예: "Hello {name}, speak {language}.")</label>
      <textarea name="template" rows="3">Translate the following {content_type} from {source_lang} to {target_lang}:\n\n{text}</textarea>
      <label>변수 (JSON 형식)</label>
      <textarea name="variables" rows="3">{"content_type": "sentence", "source_lang": "English", "target_lang": "Korean", "text": "Hello, world!"}</textarea>
      <button type="submit">렌더링</button>
    </form>
    <div class="result" id="prompt-result">{{PROMPT_RESULT}}</div>
  </div>

  <!-- Utils -->
  <div class="card">
    <h2>🛠️ 텍스트 유틸리티 <span class="tag">utils.py</span></h2>
    <form action="/utils/analyze" method="post">
      <label>분석할 텍스트</label>
      <textarea name="text" rows="4">The quick brown fox jumps over the lazy dog. This is a sample text to demonstrate token estimation and chunking capabilities of the repo_llm library.</textarea>
      <label>청크 최대 토큰 수</label>
      <input name="max_tokens" type="number" value="10" min="1" max="100"/>
      <button type="submit">분석</button>
    </form>
    <div class="result" id="utils-result">{{UTILS_RESULT}}</div>
  </div>

  <!-- JSON Extraction -->
  <div class="card">
    <h2>🔍 JSON 추출 <span class="tag">utils.extract_json</span></h2>
    <form action="/utils/extract-json" method="post">
      <label>LLM 응답 텍스트 (JSON 포함)</label>
      <textarea name="text" rows="5">Sure! Here is the result:\n\n```json\n{"score": 9.2, "label": "positive", "keywords": ["good", "excellent"]}\n```\n\nHope this helps!</textarea>
      <button type="submit">JSON 추출</button>
    </form>
    <div class="result" id="json-result">{{JSON_RESULT}}</div>
  </div>

  <!-- Cache -->
  <div class="card">
    <h2>💾 InMemoryCache <span class="tag">cache.py</span></h2>
    <form action="/cache/set" method="post">
      <label>키</label>
      <input name="key" value="my-response-key"/>
      <label>캐시할 텍스트</label>
      <input name="text" value="이것은 캐시된 LLM 응답입니다."/>
      <button type="submit">저장 (SET)</button>
    </form>
    <form action="/cache/get" method="post" style="margin-top:0.75rem">
      <label>조회할 키</label>
      <input name="key" value="my-response-key"/>
      <button type="submit">조회 (GET)</button>
    </form>
    <div class="result" id="cache-result">{{CACHE_RESULT}}</div>
  </div>

  <!-- ConversationMemory -->
  <div class="card full-width">
    <h2>💬 ConversationMemory <span class="tag">memory.py</span></h2>
    <div class="msg-list" id="msg-list">
      {{MESSAGES}}
    </div>
    <form action="/memory/add" method="post" style="display:grid;grid-template-columns:1fr 1fr;gap:1rem;margin-top:1rem">
      <div>
        <label>User 메시지</label>
        <input name="user" value="LLM이란 무엇인가요?"/>
      </div>
      <div>
        <label>Assistant 응답 (시뮬레이션)</label>
        <input name="assistant" value="LLM은 Large Language Model의 약자로, 대규모 텍스트 데이터로 학습된 AI 모델입니다."/>
      </div>
      <button type="submit" style="grid-column:1/-1">대화 추가</button>
    </form>
    <form action="/memory/clear" method="post" style="margin-top:0.5rem">
      <button type="submit" style="background:#7f1d1d">대화 초기화</button>
    </form>
    <div style="margin-top:0.75rem">
      <span class="stat">turns: <strong>{{TURN_COUNT}}</strong></span>
      <span class="stat">tokens≈<strong>{{TOKEN_COUNT}}</strong></span>
      <span class="stat">max_tokens: <strong>500</strong></span>
    </div>
  </div>

</div>
</body>
</html>
"""


def render_page(
    prompt_result="",
    utils_result="",
    json_result="",
    cache_result="",
):
    msgs_html = ""
    if _memory.system_prompt:
        msgs_html += f'<div class="msg system">system: {_memory.system_prompt}</div>'
    for turn in _memory._turns:
        msgs_html += f'<div class="msg user">{turn.user}</div>'
        msgs_html += f'<div class="msg assistant">{turn.assistant}</div>'
    if not _memory._turns:
        msgs_html = '<div class="msg system">대화 기록이 없습니다.</div>'

    return (
        HTML
        .replace("{{PROMPT_RESULT}}", prompt_result)
        .replace("{{UTILS_RESULT}}", utils_result)
        .replace("{{JSON_RESULT}}", json_result)
        .replace("{{CACHE_RESULT}}", cache_result)
        .replace("{{MESSAGES}}", msgs_html)
        .replace("{{TURN_COUNT}}", str(_memory.turn_count))
        .replace("{{TOKEN_COUNT}}", str(_memory.token_count))
    )


@app.get("/", response_class=HTMLResponse)
async def index():
    return render_page()


@app.post("/prompt/render", response_class=HTMLResponse)
async def prompt_render(template: str = Form(...), variables: str = Form(...)):
    try:
        t = PromptTemplate(template.replace("\\n", "\n"))
        kwargs = json.loads(variables)
        result = t.render(**kwargs)
        info = f"변수: {t.variables}\n\n렌더링 결과:\n{result}"
        return render_page(prompt_result=info)
    except Exception as e:
        return render_page(prompt_result=f"오류: {e}")


@app.post("/utils/analyze", response_class=HTMLResponse)
async def utils_analyze(text: str = Form(...), max_tokens: int = Form(10)):
    try:
        tokens = estimate_tokens(text)
        chunks = chunk_text(text, max_tokens=max_tokens)
        truncated = truncate(text, max_chars=50)
        result = (
            f"추정 토큰 수: {tokens}\n"
            f"청크 수 (max_tokens={max_tokens}): {len(chunks)}\n\n"
            f"청크 목록:\n"
            + "\n".join(f"  [{i}] {c}" for i, c in enumerate(chunks))
            + f"\n\n50자 트런케이트: {truncated}"
        )
        return render_page(utils_result=result)
    except Exception as e:
        return render_page(utils_result=f"오류: {e}")


@app.post("/utils/extract-json", response_class=HTMLResponse)
async def utils_extract_json(text: str = Form(...)):
    try:
        result = extract_json(text.replace("\\n", "\n"))
        pretty = json.dumps(result, ensure_ascii=False, indent=2)
        return render_page(json_result=f"추출 성공:\n{pretty}")
    except Exception as e:
        return render_page(json_result=f"오류: {e}")


@app.post("/cache/set", response_class=HTMLResponse)
async def cache_set(key: str = Form(...), text: str = Form(...)):
    resp = CompletionResponse(
        text=text, model="demo-model",
        prompt_tokens=estimate_tokens(text),
        completion_tokens=estimate_tokens(text) // 2,
        latency_ms=42.0,
    )
    _cache.set(key, resp)
    result = f"저장 완료!\n키: {key}\n텍스트: {text}\ncache size: {_cache.size}"
    return render_page(cache_result=result)


@app.post("/cache/get", response_class=HTMLResponse)
async def cache_get(key: str = Form(...)):
    hit = _cache.get(key)
    if hit:
        result = f"캐시 HIT ✓\n키: {key}\n텍스트: {hit.text}\n모델: {hit.model}\n토큰: {hit.total_tokens}"
    else:
        result = f"캐시 MISS ✗\n키 '{key}'가 캐시에 없습니다."
    return render_page(cache_result=result)


@app.post("/memory/add", response_class=HTMLResponse)
async def memory_add(user: str = Form(...), assistant: str = Form(...)):
    try:
        _memory.add_turn(user, assistant)
    except ValueError as e:
        pass
    return render_page()


@app.post("/memory/clear", response_class=HTMLResponse)
async def memory_clear():
    _memory.clear()
    return render_page()
