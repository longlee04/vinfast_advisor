# Repository Map

## Module map

| Module | Entry point | Trách nhiệm | Phụ thuộc vào | Test chính |
| --- | --- | --- | --- | --- |
| API | `src/api/routes.py` | HTTP boundary | schemas, agent/service | `tests/test_api/` |
| Agent | `src/agents/graph.py` | orchestration/state | nodes, tools, LLM | `tests/test_agents/` |
| Auth | `src/auth/composition.py` | identity/session/policy | domain + infrastructure | `tests/auth/` |
| Document | `src/document/composition.py` | file metadata/storage | domain + repository | `tests/document/` |

## Dependency map

```text
src/main.py
  ├── src/api
  ├── src/auth
  └── src/document
src/api → src/agents → src/services
src/document/presentation → application → domain
src/document/infrastructure → application/domain
src/auth/presentation → application → domain
src/auth/infrastructure → application/domain
```

## Route-registration checkpoint

`src/main.py` creates the FastAPI application, includes the API router at
`/api/v1`, and registers `GET /health`.  During lifespan startup it creates
Auth and Document compositions; when Document is enabled it builds and includes
the Document router at `/api/v1` (the document route path is guarded against
duplicate registration).  Auth route registration is not directly visible in
the required file: `main.py` starts and shuts down `AuthComposition`, but does
not call `include_router` for Auth itself.

The designated test boundaries are `tests/test_api/`, `tests/test_agents/`,
`tests/auth/`, and `tests/document/`. The required API smoke-test command could
not run because the `uv` executable is unavailable, so it provides no executed
test evidence in this environment.

## Environment checkpoint

Both required `uv` commands failed before dependency synchronization or test
collection with: `/bin/bash: line 1: uv: command not found`.

## Audit trail

### Files read

- `README.md`
- `pyproject.toml`
- `src/main.py`
- `docs/architecture_diagram.md`
- `docs/guide/setup/quick-start.md`
- `tests/test_api/test_routes.py`
- `tests/test_agents/test_graph.py`
- `tests/auth/integration/test_lifespan.py` (representative Auth boundary tests)
- `tests/document/integration/test_lifespan.py` (representative Document boundary tests)

### Working-tree checkpoint

```text
$ git status --short
?? docs/superpowers/

$ git log -5 --oneline
a0c8276 Merge dev/datphung into dev/long: sync with pyproject.toml
e4ed23e save current work on dev/long
3f0d3a7 docs(document): complete final verification wave
3cf3599 docs(document): record final verification evidence
50bd9ca fix(document): preserve metadata and enforce download authorization
```

`docs/superpowers/` was already untracked when this task began and was treated
as out of scope, not as a roadmap result.

### Dependency and smoke-test checkpoints

```text
$ uv sync
/bin/bash: line 1: uv: command not found
```

Outcome: exit status 127; dependencies were not synchronized because `uv` is
not installed or is absent from `PATH`.

```text
$ uv run pytest tests/test_api/test_routes.py -v --tb=short
/bin/bash: line 1: uv: command not found
```

Outcome: exit status 127 before pytest collection; this environment has no
executed smoke-test result.

## Boundary-test evidence

| Boundary | Concrete test evidence | What it demonstrates | Execution status |
| --- | --- | --- | --- |
| API | `tests/test_api/test_routes.py::test_health`, `::test_chat_empty_message`, `::test_agent_status` | `/health` returns 200; the chat boundary rejects an empty message with 422; `/api/v1/status` returns 200. | Not run: `uv` unavailable. |
| Agent | `tests/test_agents/test_graph.py::test_agent_basic_flow`, `::test_agent_state_structure` | The compiled agent can be invoked and returns a state dictionary with `response` and `query`. | Not run: `uv` unavailable. |
| Auth | `tests/auth/integration/test_lifespan.py::TestLegacyApplicationRemainsUnchanged::test_lifespan_exposes_auth_composition_on_app_state` | Application lifespan exposes `AuthComposition` on `app.state.auth`; the companion health test preserves the legacy endpoint through the full lifespan. | Not run: `uv` unavailable. |
| Document | `tests/document/integration/test_lifespan.py::test_register_document_router_adds_enabled_routes_once` | `register_document_router` is idempotent and exposes `/api/v1/documents`, which returns 401 for an anonymous request. | Not run: `uv` unavailable. |

## Documentation scope and uncertainty

`README.md`, `docs/architecture_diagram.md`, and
`docs/guide/setup/quick-start.md` describe the broad AI20K template and are
therefore template-oriented context, not proof of this repository's runtime
behavior. Runtime conclusions above are grounded in the inspected
`src/main.py` source and the identified tests. This checkpoint does not use or
make claims from the VinFast-specific business-design document
`docs/kien-truc-du-lieu-va-rag-agent.md`; that document must be distinguished
from the generic template documentation in later business/RAG analysis.
