# LLM service, runtime configuration, and external boundary

## Checkpoint conclusion

The repository has an LLM factory (`src/services/llm.py::get_llm`) that can construct a `ChatOpenAI` client from cached Pydantic settings.  The currently compiled LangGraph does **not** call that factory or any LLM invocation method.  Therefore the current HTTP-to-graph execution traced in [02-agent-trace.md](02-agent-trace.md) is deterministic template logic, not an OpenAI-backed call.

This distinction matters: the `ChatOpenAI` code establishes a prospective provider boundary, whereas the graph and node source establishes the current runtime path.  The illustrative `ChatOpenAI`/`ainvoke` example in `docs/guide/chapter-04.md` is documentation, not evidence that this graph uses it.

## Runtime configuration boundary

`Settings` in `src/config.py:8-32` is a `pydantic_settings.BaseSettings` model.  It loads `.env` as UTF-8, ignores undeclared extra variables, and is constructed by the process-local, `@lru_cache`-decorated `get_settings()` factory (`src/config.py:35-37`).  Pydantic Settings maps the fields below to their usual uppercase environment-variable names.  Defaults are source defaults; environment values, if present, override them.  No secret value is reproduced here.

| Environment/config field | Type and validation | Source default | Read by current source |
| --- | --- | --- | --- |
| `APP_NAME` / `app_name` | `str` | `AI20K Agent` | Defined in `Settings`; not read by `get_llm`. |
| `APP_ENV` / `app_env` | `Literal[development, production, test]` | `development` | Defined in `Settings`; not read by `get_llm`. |
| `APP_PORT` / `app_port` | `int`, 1–65535 | `8000` | Defined in `Settings`; not read by `get_llm`. |
| `APP_HOST` / `app_host` | `str` | `0.0.0.0` | Defined in `Settings`; not read by `get_llm`. |
| `LOG_LEVEL` / `log_level` | `Literal[DEBUG, INFO, WARNING, ERROR]` | `INFO` | Defined in `Settings`; not read by `get_llm`. |
| `CORS_ORIGINS` / `cors_origins` | `str` | `http://localhost:3000` | Defined in `Settings`; not read by `get_llm`. |
| `OPENAI_API_KEY` / `openai_api_key` | `str` | empty string | Read only when `get_llm()` constructs `ChatOpenAI`. Secret: do not log or return it. |
| `MODEL_NAME` / `model_name` | `str` | `gpt-4o-mini` | Passed as `model` by `get_llm()`. |
| `LLM_TEMPERATURE` / `llm_temperature` | `float`, 0.0–2.0 | `0.7` | Passed as `temperature` by `get_llm()`. |
| `DATABASE_URL` / `database_url` | `str` | `sqlite:///./data/app.db` | Defined in `Settings`; not read by `get_llm`. |
| `CHROMA_PERSIST_DIR` / `chroma_persist_dir` | `str` | `./data/chroma` | Defined in `Settings`; not read by `get_llm`. |

`LANGCHAIN_*`, `GEMINI_*`, and other provider variables shown in `.env.example` are not fields in this `Settings` model.  With `extra="ignore"`, this particular model neither validates nor consumes them.  `pyproject.toml` declares `langchain`, `langchain-openai`, and `langgraph`; no Gemini client dependency is declared.

No LLM timeout setting is defined in `src/config.py`, and `get_llm()` does not pass a timeout to `ChatOpenAI`.  Any client-library default is outside the inspected repository source and is not asserted as application policy.

## Source-backed LLM boundary map

```text
prospective caller
  → src.services.llm.get_llm()
  → src.config.get_settings() [cached Settings from .env/environment]
  → ChatOpenAI(model, api_key, temperature)
  → caller would await llm.ainvoke(...)
  → caller would normalize the provider message/result
```

Only the first four symbols exist in the present LLM service.  There is no caller of `get_llm`, no `ChatOpenAI.ainvoke`/`invoke` call, and no normalized provider result in `src/`.  The agent nodes make formatted local strings instead: `analyze_node` returns `analysis`, then `respond_node` returns `response` (`src/agents/nodes/example_node.py:4-26`).  `src/agents/graph.py:14-29` wires only those two nodes.  The trace from Task 3 confirms the HTTP handler awaits the **graph** (`agent.ainvoke`), not an LLM client.

Consequently, a truthful current call trace is:

```text
POST /api/v1/chat → compiled LangGraph.ainvoke → analyze_node → respond_node → response state
```

It contains no external LLM request.  The requested `node/tool → service function → client construction → await invoke → normalized result` chain is not wired in the current graph.

## Error classification

| Lỗi | Boundary phát hiện | HTTP/runtime mapping | Có retry không |
| --- | --- | --- | --- |
| Invalid `ChatRequest` input | FastAPI/Pydantic request validation (`message` is a required 1–5000-character string) | FastAPI returns HTTP 422 before `chat()` runs. | Không. |
| Provider timeout | LLM adapter/client, if a future caller invokes it | No provider-specific service error type, timeout configuration, or normalization exists.  If it reaches the current `agent.ainvoke` call, the `/chat` route catches it as a generic exception and returns HTTP 500 with `detail=str(e)`. | Theo policy; no policy is implemented. |
| Provider auth failure | Provider/client after `ChatOpenAI` is used; missing/invalid configuration may also surface when client/service is used | `docs/guide/troubleshooting.md` describes `openai.AuthenticationError`; source has no provider-specific startup/service mapping.  A failure from the current graph invocation is caught by `/chat` and returned as HTTP 500 with `detail=str(e)`. | Không. |
| Node/template exception | Current graph node/runtime | Nodes have no local catch, but `/chat` catches exceptions from `await agent.ainvoke(...)` and raises HTTP 500 with `detail=str(e)`. | Không được triển khai. |

The guide's provider-auth troubleshooting instructions are operational guidance only.  They do not add provider-specific validation, retry, timeout, or exception normalization to the production source.  The route's current generic catch is observable HTTP behavior, but it exposes `str(e)` in the 500 response rather than providing a dedicated provider-error contract.

## Secret hygiene checkpoint

The required tracked-file scan was run.  It found placeholder/example strings and prose/test matches; no scanned match was copied into this note.  Independently, `.env.example` contains a non-empty credential-like AI-logging field at line 40.  Its value is deliberately omitted.  It was not validated, so its authenticity is uncertain; it should be treated as potentially sensitive and reviewed/rotated by an authorized maintainer if it is active.  No files were changed to remediate it.

## Why routes must not create the LLM client or read environment directly

Keeping client construction in `get_llm()` centralizes configuration loading, defaulting, validation, secret handling, and provider selection at one external boundary.  A route that creates `ChatOpenAI` or calls `os.environ` directly would duplicate those decisions, scatter secret access across presentation code, make provider failures harder to normalize/test, and bypass the cached settings composition point.  The current route-to-graph boundary should remain independent of a concrete provider; a future node/use case can receive the configured service through composition instead.

## Evidence and limits

- Required config search completed with exit 0; it found `Settings` in `src/config.py`, plus separate Auth and Document settings not used by this LLM factory.
- Required hygiene scan completed with exit 0 because of `|| true`; it reported matches in tracked examples, guides, plans, and tests.  No credential value is repeated.
- `rg -n 'get_llm|ChatOpenAI|\\.ainvoke\\(|\\.invoke\\(|openai_api_key|model_name|llm_temperature' src tests` completed with exit 0.  It found `get_llm` only in the factory, client construction only there, and `agent.ainvoke` in the HTTP route/tests—not a `ChatOpenAI` invocation.
- No automated test was run: this task is a source-backed architecture note, and the required brief commands are searches rather than a test command.

Uncertainties: provider-library behavior (including default timeouts and when it validates credentials) was not executed; no real provider request was made; and no statement about the authenticity of the credential-like example value is possible from source inspection alone.
