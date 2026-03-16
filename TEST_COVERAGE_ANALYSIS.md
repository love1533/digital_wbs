# Test Coverage Analysis

**Date:** 2026-03-16
**Branch:** `claude/analyze-test-coverage-a6BN8`
**Tool:** `pytest-cov` with branch coverage enabled

## Current State

```
Name                   Stmts   Miss Branch BrPart  Cover
---------------------------------------------------------
repo_llm/__init__.py       6      0      0      0   100%
repo_llm/cache.py         74     30     18      3    55%
repo_llm/chain.py         40     26      8      0    29%
repo_llm/client.py        80     28     16      3    64%
repo_llm/memory.py        49      5     12      4    85%
repo_llm/prompt.py        31     13     10      0    54%
repo_llm/utils.py         68     20     40      7    71%
---------------------------------------------------------
TOTAL                    348    122    104     17    63%
```

34 tests pass. The headline figure of **63 % statement coverage** (and lower
branch coverage in several modules) hides some critical gaps. Below is a
prioritised breakdown.

---

## Priority 1 — Critical Gaps (highest risk / lowest coverage)

### `chain.py` — 29% coverage

`Chain` is one of the most complex and user-facing components and is almost
entirely untested.

| Gap | Risk |
|-----|------|
| `Chain.__init__` with empty `steps` raises `ValueError` | Untested; regression-prone |
| `Chain.run()` happy path — variables flow between steps | Core behaviour, zero tests |
| `Chain.run()` with a `transform` function on a step | Transform silently skipped if broken |
| `Chain.run()` propagates `LLMClient` exceptions | Unknown failure mode |
| `Chain.add_step()` returns `self` and mutates `steps` | Fluent API contract untested |
| `Chain.verbose=True` prints intermediate output | Side-effect path uncovered |
| `ChainStep.__repr__` | Minor but untested |

**Recommended action:** Add `tests/test_chain.py` using a mock `LLMClient`
(`unittest.mock.MagicMock`) that returns canned `CompletionResponse` objects.

```python
# Example scaffold
from unittest.mock import MagicMock
from repo_llm.chain import Chain, ChainStep
from repo_llm.prompt import PromptTemplate
from repo_llm.client import CompletionResponse

def _mock_client(reply="ok"):
    client = MagicMock()
    client.complete.return_value = CompletionResponse(
        text=reply, model="m", prompt_tokens=5,
        completion_tokens=10, latency_ms=50.0,
    )
    return client

def test_chain_run_single_step():
    step = ChainStep("greet", PromptTemplate("Say hi to {name}"), output_key="greeting")
    chain = Chain(_mock_client("Hello, Alice!"), [step])
    result = chain.run(name="Alice")
    assert result["greeting"] == "Hello, Alice!"

def test_chain_run_multi_step_variable_passing():
    step1 = ChainStep("s1", PromptTemplate("Topic: {topic}"), output_key="summary")
    step2 = ChainStep("s2", PromptTemplate("Expand: {summary}"), output_key="expanded")
    client = _mock_client()
    client.complete.side_effect = [
        CompletionResponse("Short summary", "m", 5, 10, 50.0),
        CompletionResponse("Long expansion", "m", 10, 20, 60.0),
    ]
    chain = Chain(client, [step1, step2])
    ctx = chain.run(topic="AI")
    assert ctx["summary"] == "Short summary"
    assert ctx["expanded"] == "Long expansion"
```

---

### `cache.py` — 55% coverage

`DiskCache` is 0% tested. `InMemoryCache` TTL and LRU behaviour are untested.

| Gap | Risk |
|-----|------|
| `DiskCache.get` / `.set` / `.clear` | Entire class untested |
| `DiskCache` TTL expiry removes stale file | Silent data staleness |
| `DiskCache` handles corrupted JSON without crashing | Crash on bad disk state |
| `InMemoryCache` TTL expiry returns `None` | Silent cache poisoning |
| `InMemoryCache` LRU — recently accessed key survives eviction | Incorrect eviction order |
| `InMemoryCache.invalidate()` return value | API contract untested |
| `InMemoryCache(max_size=0)` raises `ValueError` | Constructor guard untested |

**Recommended action:**

```python
import time, pytest
from unittest.mock import patch
from repo_llm.cache import InMemoryCache, DiskCache

def test_in_memory_cache_ttl_expiry():
    cache = InMemoryCache(ttl_seconds=0.05)
    cache.set("k", _response())
    time.sleep(0.1)
    assert cache.get("k") is None

def test_disk_cache_roundtrip(tmp_path):
    cache = DiskCache(tmp_path)
    r = _response("disk-hit")
    cache.set("dk", r)
    result = cache.get("dk")
    assert result.text == "disk-hit"

def test_disk_cache_corrupted_json(tmp_path):
    cache = DiskCache(tmp_path)
    (tmp_path / "badkey.json").write_text("NOT JSON")
    assert cache.get("badkey") is None  # should not raise
```

---

## Priority 2 — Significant Gaps (medium risk)

### `client.py` — 64% coverage (branch coverage lower)

The retry machinery in `LLMClient.complete` is untested despite being complex
control flow.

| Gap | Risk |
|-----|------|
| `RateLimitError` triggers retry with exponential back-off | Broken retry → cascading failures |
| `AuthenticationError` is **not** retried | Wrong: could retry forever |
| Retries exhausted → `LLMError` raised | Users get silent hang instead of error |
| `temperature < 0.0` raises `ValueError` | Only the upper bound is tested |
| `max_tokens <= 0` raises `ValueError` | Guard untested |
| `max_retries < 0` raises `ValueError` in `__init__` | Guard untested |
| `timeout <= 0` raises `ValueError` in `__init__` | Guard untested |
| `_call_count` increments on each `_send` | Observability feature untested |

**Recommended action:** Mock `_send` to raise `RateLimitError` / `LLMError`
and verify retry behaviour without real HTTP calls, and use `pytest.mark.parametrize`
for the boundary value checks.

```python
from unittest.mock import patch, MagicMock
from repo_llm.client import LLMClient, Message, RateLimitError, AuthenticationError, LLMError

def test_rate_limit_retried(monkeypatch):
    client = LLMClient("openai", "sk-test", "gpt-4o", max_retries=2)
    responses = [RateLimitError(), RateLimitError(), _good_response()]
    call_iter = iter(responses)

    def fake_send(*args, **kwargs):
        r = next(call_iter)
        if isinstance(r, Exception):
            raise r
        return r

    monkeypatch.setattr(client, "_send", fake_send)
    monkeypatch.setattr("time.sleep", lambda _: None)  # skip waits
    result = client.complete([Message("user", "hi")])
    assert result.text == "ok"

def test_auth_error_not_retried(monkeypatch):
    client = LLMClient("openai", "sk-bad", "gpt-4o", max_retries=3)
    call_count = 0

    def fake_send(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        raise AuthenticationError("bad key")

    monkeypatch.setattr(client, "_send", fake_send)
    with pytest.raises(AuthenticationError):
        client.complete([Message("user", "hi")])
    assert call_count == 1  # must NOT retry

@pytest.mark.parametrize("temp", [-0.1, 2.1, -100])
def test_temperature_out_of_range(temp):
    client = LLMClient("openai", "sk-test", "gpt-4o")
    with pytest.raises(ValueError, match="temperature"):
        client.complete([Message("user", "hi")], temperature=temp)
```

---

### `prompt.py` — 54% coverage

`partial()` and `load_template_from_file()` are entirely untested.

| Gap | Risk |
|-----|------|
| `partial()` renders known variables | Core feature untested |
| `partial()` with unknown variable raises `KeyError` | Silent wrong key stored |
| `partial()` result is a proper `PromptTemplate` | Type contract untested |
| `__eq__` returns `False` for different templates | Equality logic untested |
| `__eq__` returns `NotImplemented` for non-`PromptTemplate` | Protocol untested |
| `load_template_from_file` reads file content correctly | File I/O path untested |
| `load_template_from_file` propagates `FileNotFoundError` | Error propagation untested |

**Recommended action:**

```python
def test_partial_fills_known_variable():
    t = PromptTemplate("Hello {name}, speak {language}.")
    partial = t.partial(language="French")
    assert partial.render(name="Alice") == "Hello Alice, speak French."

def test_partial_unknown_variable_raises():
    t = PromptTemplate("Hello {name}.")
    with pytest.raises(KeyError):
        t.partial(unknown_var="x")

def test_load_template_from_file(tmp_path):
    p = tmp_path / "tpl.txt"
    p.write_text("Dear {recipient},\n{body}")
    t = load_template_from_file(str(p))
    assert t.render(recipient="Bob", body="Hi") == "Dear Bob,\nHi"
```

---

## Priority 3 — Minor Gaps (lower risk / good-to-have)

### `utils.py` — 71% coverage

Branch coverage on `chunk_text` and `extract_json` is the main weakness.

| Gap | Notes |
|-----|-------|
| `chunk_text` with `overlap_tokens > 0` | Overlap logic completely untested |
| `chunk_text` produces multiple chunks | Only error paths tested |
| `extract_json` with markdown code fence | Regex branch never hit |
| `extract_json` with nested objects | Bracket-depth logic untested |
| `extract_json` with malformed JSON raises `json.JSONDecodeError` | Not `ValueError` — wrong exception type exposed? |
| `truncate` with `max_chars <= 0` | Guard raises `ValueError` — untested |
| `truncate` exactly at `max_chars` | Off-by-one boundary untested |
| `estimate_tokens` returns minimum of `1` for single char | Minimum clamp untested |

### `memory.py` — 85% coverage (best covered module)

| Gap | Notes |
|-----|-------|
| `to_messages()` with `system_prompt` set | System message prepended — untested |
| `_trim()` evicts oldest turn to stay in budget | Token budget enforcement untested |
| Custom `token_counter` is invoked | Dependency injection contract untested |
| Blank `user` / `assistant` raises `ValueError` | Two guards, both untested |

---

## Summary Table

| Module | Coverage | Priority | Primary Action |
|---|---|---|---|
| `chain.py` | 29% | **P1** | Add `test_chain.py` with mock client |
| `cache.py` | 55% | **P1** | Add `DiskCache` tests; TTL + LRU for `InMemoryCache` |
| `prompt.py` | 54% | **P2** | Test `partial()` and `load_template_from_file` |
| `client.py` | 64% | **P2** | Test retry logic (mock `_send`); parametrize boundary values |
| `utils.py` | 71% | **P3** | Branch coverage for `chunk_text` overlap and `extract_json` fence |
| `memory.py` | 85% | **P3** | System prompt, trim logic, blank-message guards |

---

## Recommended Next Steps

1. **Target 90 %+ branch coverage** on `chain.py` and `cache.py` first —
   they contain the most complex untested logic.

2. **Introduce a shared `conftest.py`** with reusable fixtures:
   - `mock_client` fixture returning a configurable `MagicMock`
   - `tmp_cache_dir` fixture wrapping `pytest`'s `tmp_path`

3. **Add integration tests** under `tests/integration/` that exercise
   `Chain → LLMClient → (mocked HTTP)` end-to-end with `responses` or
   `httpretty` to intercept actual HTTP calls.

4. **Enable branch coverage in CI** (`--cov-branch`) and set a minimum
   threshold gate (e.g. `--cov-fail-under=85`) to prevent regressions.

5. **Property-based tests** (with `hypothesis`) are well-suited to
   `estimate_tokens`, `chunk_text`, and `extract_json` to catch edge cases
   that example-based tests miss.
