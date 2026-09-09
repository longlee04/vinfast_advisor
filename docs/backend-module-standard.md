# Backend Module Standard

Guideline này định nghĩa cách xây dựng module backend mới trong `src/`.

## 0. Hai kiến trúc được duyệt

Tài liệu định nghĩa **hai** layout, chọn theo bản chất module — không trộn lẫn trong cùng một module:

| Kiến trúc | Dùng cho | Layout |
|---|---|---|
| **A. Standard 4 tầng** (mục 1–10) | Module CRUD/nghiệp vụ tuyến tính: `auth`, `document`, `product` | `domain/` `application/` `infrastructure/` `presentation/`, thư mục tên số ít |
| **B. Agent graph-centric** (mục 11) | Module điều phối hội thoại bằng LangGraph state machine: `agents` | `graph.py`/`state.py`/`nodes/` ở gốc + `services/` `domain/` `adapters/`, thư mục tên số nhiều |

**Điểm chung bất biến — cả hai kiến trúc phải giữ:** dependency hướng vào trong (mục 3), composition root có `start()`/`shutdown()`, router qua `src/api/router.py`, settings có prefix riêng, schema change qua Alembic, test isolation, và toàn bộ Definition of Done (mục 9) + Review checklist (mục 10). Kiến trúc B **chỉ** khác A ở *cách trình bày tầng* (phẳng, graph-centric), **không** nới lỏng bất kỳ ràng buộc phụ thuộc nào.

Phần dưới (mục 1–10) đặc tả **Kiến trúc A**. Mục 11 đặc tả **Kiến trúc B** và ánh xạ ngược về A.

## 1. Mục tiêu và phạm vi

Mỗi module mới phải:

- Có boundary rõ ràng giữa nghiệp vụ, use case, adapter hạ tầng và HTTP.
- Có composition boundary để wire dependency.
- Đăng ký API qua router aggregator trung tâm.
- Có unit test và integration test phù hợp với capability.
- Quản lý lifecycle, migration, resource cleanup và error mapping rõ ràng.
- Không làm thay đổi hành vi của module hiện có nếu task không yêu cầu.

Guideline này là **core contract**. Các yêu cầu như cookie, CSRF, token rotation, MinIO hoặc multipart upload chỉ bắt buộc khi module có capability tương ứng.

## 2. Cấu trúc thư mục chuẩn

Module đặt tại `src/<module>/`:

```text
src/<module>/
├── __init__.py
├── composition.py
├── domain/
│   ├── __init__.py
│   ├── entities.py
│   ├── values.py
│   └── errors.py
├── application/
│   ├── __init__.py
│   ├── contracts.py
│   ├── ports.py
│   └── errors.py
├── infrastructure/
│   ├── __init__.py
│   ├── models.py
│   ├── repositories.py
│   ├── settings.py
│   └── migrations.py
└── presentation/
    ├── __init__.py
    ├── routes.py
    ├── dependencies.py
    └── schemas.py
```

Không phải file nào cũng bắt buộc. Chỉ tạo layer hoặc file khi module thực sự có trách nhiệm tương ứng. Không tạo file rỗng chỉ để đủ cấu trúc.

### `domain/`

Chứa logic nghiệp vụ thuần:

- Entity và invariant.
- Value object.
- Domain policy.
- Domain error.
- Clock hoặc hashing abstraction nếu nghiệp vụ cần nhưng không chứa implementation cụ thể.

Không import FastAPI, SQLAlchemy, Alembic, MinIO, SendGrid, HTTP transport, `src.main`, hoặc module `infrastructure`/`presentation`.

### `application/`

Chứa use case và abstraction:

- Use case orchestration.
- Input/output contract.
- Repository, storage, email hoặc external-service port.
- Application error.
- Transaction boundary ở mức use case/application boundary.

Application có thể phụ thuộc vào `domain`, nhưng không phụ thuộc vào FastAPI, SQLAlchemy session/model cụ thể, MinIO, SendGrid hoặc HTTP request/response.

### `infrastructure/`

Chứa implementation cụ thể:

- SQLAlchemy model và repository.
- Database/session adapter.
- Object storage hoặc external API client.
- Email provider.
- Typed settings adapter.
- Migration support.

Infrastructure implement các port trong `application`; không đưa adapter cụ thể vào domain hoặc application.

### `presentation/`

Chứa HTTP boundary:

- FastAPI `APIRouter`.
- Pydantic request/response schema.
- FastAPI dependency.
- Authentication/authorization bridge.
- Query, header, cookie, multipart handling.
- Mapping domain/application errors sang HTTP response ổn định.

Presentation gọi application use case, không chứa SQL query hoặc business rule chính.

### `composition.py`

Là composition root của module:

- Đọc typed settings.
- Tạo infrastructure adapter.
- Wire adapter vào application port/use case.
- Expose resources hoặc route services cho presentation.
- Có `start()` và `shutdown()` khi module sở hữu resource runtime.
- Cho phép inject resource/service trong test.
- Không để `src/main.py` tự xây repository và use case chi tiết.

## 3. Dependency direction

Dependency phải hướng vào trong:

```text
presentation ───────┐
infrastructure ─────┼──> application ───> domain
composition ────────┘
```

Quy tắc bắt buộc:

- Domain không biết application, infrastructure hoặc presentation.
- Application chỉ biết domain và port/contract.
- Infrastructure implement application port.
- Presentation phụ thuộc application/domain qua interface phù hợp.
- Concrete adapter được wire tại composition boundary.
- Module mới không được tạo import ngược vào `src/main.py` từ domain/application.

## 4. Router và application lifecycle

Mỗi module có router riêng, ví dụ:

```python
router = APIRouter(
    prefix="/orders",
    tags=["orders"],
)
```

Luồng đăng ký API:

```text
src/<module>/presentation/routes.py
        ↓
src/api/router.py
        ↓
src/main.py
```

`src/api/router.py` là nơi tập trung include các module router. `src/main.py` chỉ include API aggregator, không đăng ký rải rác từng module và không tự tạo route infrastructure.

`lifespan` chỉ quản lý lifecycle:

```text
startup:
    create composition
    store composition in app.state
    await composition.start()

request:
    dependency resolves services from app.state

shutdown:
    await composition.shutdown()
```

Nếu module có thể disabled hoặc unavailable:

- Router vẫn xuất hiện trong OpenAPI để API contract ổn định.
- Request trả `503 Service Unavailable`.
- Response dùng thông báo ổn định, không chứa stack trace, credentials, connection string hoặc exception nội bộ.
- Disabled module không tạo database, storage hoặc external resource.

## 5. Settings, resource và migration

Mỗi module dùng settings có type rõ ràng và prefix riêng:

```python
class ModuleSettings(BaseSettings):
    enabled: bool = True
```

Yêu cầu:

- Không hardcode secret, token hoặc credential.
- Resource chỉ được tạo khi feature enabled.
- Composition phải đóng mọi resource do mình sở hữu.
- Test phải inject fake/in-memory adapter khi không cần external service.
- Nếu có relational database, schema change phải dùng Alembic.
- Migration phải có upgrade deterministic và downgrade an toàn khi change reversible.
- Không dùng `metadata.create_all()` làm đường triển khai schema production.
- Transaction boundary phải rõ ràng và có test rollback khi phù hợp.

## 6. Test architecture

Test đặt tại `tests/<module>/`:

```text
tests/<module>/
├── __init__.py
├── conftest.py
├── unit/
│   ├── __init__.py
│   ├── domain/
│   └── application/
└── integration/
    ├── __init__.py
    ├── conftest.py
    ├── test_http.py
    ├── test_api_registration.py
    ├── test_lifespan.py
    ├── test_migrations.py
    └── test_repositories.py
```

### Unit test bắt buộc

- Entity/value object hợp lệ.
- Boundary input và invalid input.
- Domain error.
- Use case success path.
- Use case failure path.
- Authorization policy nếu module có quyền truy cập.
- Port được gọi qua fake adapter.
- Không gọi database hoặc paid external service trong unit test.

### HTTP và OpenAPI test bắt buộc

- Endpoint xuất hiện trong OpenAPI trước startup resource initialization.
- Success response và response schema.
- Request validation failure.
- Authentication missing/invalid nếu endpoint cần auth.
- Authorization denied.
- Disabled/unavailable module trả `503`.
- Error body ổn định và không leak internal exception.
- Các endpoint không bị duplicate khi include qua `src/api/router.py`.

### Lifecycle test bắt buộc

- Startup thành công.
- Startup fail khi required configuration sai.
- Disabled module không tạo resource.
- Shutdown đóng resource đã sở hữu.
- Injected resources/services hoạt động trong test.
- Không đăng ký router nhiều lần.

### Database và migration test

Chỉ áp dụng nếu module có database:

- Alembic upgrade.
- Downgrade nếu reversible.
- Repository CRUD.
- Transaction rollback.
- Data isolation giữa test.
- Cleanup database sau test.
- Không dùng production database.

### External integration test

Chỉ áp dụng nếu module gọi external service:

- Dùng deterministic fake/test adapter.
- Test timeout và provider failure.
- Test retry policy nếu có.
- Cleanup resource sau test.
- Skip rõ ràng khi local infrastructure không khả dụng.
- Không gọi SendGrid, OpenAI hoặc paid service thật trong automated tests.

## 7. Capability-specific checklist

### Database

- `infrastructure/models.py`.
- `infrastructure/repositories.py`.
- Alembic config/migration.
- Explicit transaction boundary.
- Repository, migration và rollback tests.

### Authentication và security

- Password/token/session behavior.
- CSRF/cookie nếu dùng cookie authentication.
- Role/permission authorization.
- Rate limiting.
- Expiry, revocation và replay rejection.
- Generic error responses chống account/state disclosure.
- Security-focused tests.

### File upload và storage

- File size/type validation.
- Safe object key/path handling.
- Private storage mặc định.
- Authorization trước download.
- Compensation khi persistence/storage thất bại.
- Storage cleanup fixture.
- Download expiry/presigned URL tests nếu có.

### External API và email

- Port cho external client.
- Deterministic fake trong test.
- Timeout và provider-failure mapping.
- Không log credential hoặc payload nhạy cảm.

### Background processing

- Idempotency.
- Retry và failure state.
- Cancellation nếu hỗ trợ.
- Duplicate job behavior.
- Partial/interrupted execution tests.

## 8. API và error contract

Mỗi module phải ghi rõ:

- Prefix và tags.
- HTTP method/path.
- Request/response schema.
- Authentication requirement.
- Authorization requirement.
- Expected status codes.
- Disabled/unavailable behavior.
- Sensitive data policy.

Không được thay đổi public HTTP contract, cookie name, environment variable name, database schema hoặc dependency nếu chưa được ghi trong approved plan.

## 9. Definition of Done

- [ ] Module có package dưới `src/<module>/`.
- [ ] Layer boundaries phù hợp với phạm vi module.
- [ ] Domain/application không phụ thuộc concrete infrastructure hoặc transport.
- [ ] Có composition boundary và lifecycle ownership rõ ràng.
- [ ] Router được đăng ký qua `src/api/router.py`.
- [ ] OpenAPI có đầy đủ endpoint và không duplicate.
- [ ] Có unit tests cho domain/application.
- [ ] Có HTTP/OpenAPI và lifecycle integration tests.
- [ ] Có migration/repository tests nếu dùng database.
- [ ] Có capability-specific tests.
- [ ] Disabled/unavailable behavior đã định nghĩa và test.
- [ ] Không leak credentials, stack trace hoặc internal exception.
- [ ] Không thay đổi Chat, Auth, Document, health hoặc agent-status ngoài phạm vi được duyệt.
- [ ] `ruff check src/ tests/` pass.
- [ ] `pytest tests/ -v --tb=short` pass.
- [ ] Migration, type, security và external-service checks bổ sung pass khi áp dụng.
- [ ] `git diff --check` pass.
- [ ] Tài liệu API/module được cập nhật khi public contract thay đổi.

## 10. Review checklist

Reviewer cần kiểm tra:

1. Module boundary có rõ không?
2. Dependency có hướng vào trong không?
3. Composition có tạo và đóng đúng resource không?
4. Router có đi qua central aggregator không?
5. Disabled state có response ổn định không?
6. Error response có leak thông tin không?
7. Tests có bao phủ success, failure, lifecycle và external boundary không?
8. Migration có deterministic không?
9. Test fixture có cleanup và isolation không?
10. Full lint/test gate có pass không?
11. Có thay đổi ngoài scope hoặc phá legacy behavior không?
12. Capability-specific checklist đã được áp dụng đúng chưa?
13. Nếu là module agent: layout có theo mục 11 không, và luật import một chiều (mục 11.3) có test cưỡng chế không?

## 11. Kiến trúc B — Agent graph-centric

Áp dụng cho module điều phối hội thoại bằng **LangGraph state machine** (hiện tại: `src/agents/`). Khác Kiến trúc A ở chỗ orchestration (graph, node, state) là ngôn ngữ trung tâm của module, không phải một chi tiết hạ tầng — nên đặt ở **gốc** package thay vì chôn trong `infrastructure/`. Tái dùng scaffold LangGraph có sẵn (`graph.py` + `state.py` + `nodes/` + `tools/`).

### 11.1. Khi nào chọn B thay vì A

Chọn B **chỉ khi** cả ba đúng:

- Module là một **luồng xử lý nhiều bước có điều kiện** điều phối bằng state machine (LangGraph), không phải request→response tuyến tính.
- Có **≥ 8 bước xử lý** (node) chia sẻ chung một state và một bộ từ vựng nghiệp vụ — tách mỗi bước thành module 4 tầng riêng sẽ buộc nhân bản value object.
- LLM/graph là thành phần chính, cần `graph.py`/`state.py`/`nodes/` là API đọc-hiểu đầu tiên của module.

Nếu không thoả cả ba → dùng Kiến trúc A. Không dùng B cho module CRUD chỉ vì "có gọi LLM".

### 11.2. Cấu trúc thư mục

```text
src/agents/
├── __init__.py
├── composition.py            composition root: settings → adapters → services → build_graph()
│
│  ── ĐIỀU PHỐI (ở gốc) ──
├── graph.py                  build_graph: add_node/edge/conditional_edges/compile/ainvoke
├── state.py                  AgentState (TypedDict + reducer), CHỈ khai báo
├── routing.py                hàm điều kiện rẽ nhánh: thuần, đọc state, trả tên nhánh
├── chain.py                  dựng initial state, invoke, trả DTO cho api/
├── protocol.py               kiểu node dùng chung: (AgentState) -> dict
├── nodes/                    node MỎNG ≤15 câu, mỗi node gọi ĐÚNG một service
│
│  ── HỢP ĐỒNG (public seams, ở gốc) ──
├── ports.py                  interface: LLMPort, CatalogReadPort, repo ports, UnitOfWorkPort
├── contracts.py              DTO vào/ra + tool schema
├── errors.py                 lỗi application-level
├── models.py                 SQLAlchemy model + Base
├── settings.py               prefix riêng
│
├── services/                 use case; biết domain + port; KHÔNG biết LangGraph/SQLAlchemy
│   ├── registry.py           AgentServices — tập use case mà node được phép gọi
│   └── operations/           use case CHỈ route HTTP gọi, KHÔNG qua graph
├── domain/                   nghiệp vụ thuần: values, entities, policy, rule
├── tools/                    structured tool tính toán deterministic (test thuần)
├── adapters/                 implement port; nơi DUY NHẤT biết SQLAlchemy/LLM SDK; UnitOfWork
├── prompts/                  câu chữ gửi LLM
└── api/                      HTTP boundary: routes, schemas, dependencies
```

### 11.3. Dependency direction — luật import một chiều

Vì layout phẳng, tính mạch lạc do **luật import** giữ, phải có test cưỡng chế (tương đương mục 3 của Kiến trúc A):

| Thư mục | ĐƯỢC gọi | CẤM import |
|---|---|---|
| `nodes/`, `graph.py`, `routing.py`, `chain.py` | `services/` (qua `AgentServices`), đọc/ghi `state` | `sqlalchemy`, `adapters/`, `domain/` |
| `services/` (gồm `operations/`) | `domain/`, `tools/`, `ports.py`, `contracts.py` | `langgraph`, `adapters/` cụ thể, `nodes/` |
| `domain/`, `tools/` | thuần Python | `langgraph`, `sqlalchemy`, `fastapi`, LLM SDK |
| `adapters/` | implement `ports.py`, biết `sqlalchemy`/LLM SDK | `nodes/`, `services/` |
| `api/` | `services/operations/` | đi qua graph cho operations |

Mũi tên luôn chỉ vào trong (`nodes → services → domain`; `adapters → ports`). `AgentState` chỉ đựng domain value/DTO, tuyệt đối không đựng object SQLAlchemy hay session.

### 11.4. Ánh xạ ngược về Kiến trúc A

Bản chất vẫn là tách tầng theo chiều phụ thuộc — chỉ đổi vị trí và tên:

| Tầng A | Tương ứng ở B |
|---|---|
| `domain/` | `domain/` + `tools/` (tính toán thuần) |
| `application/` (use case + port) | `services/` (+ `operations/`) + `ports.py` + `contracts.py` |
| `infrastructure/` | `adapters/` + `prompts/` + `models.py` + `settings.py` |
| `presentation/` | `api/` |
| (không có ở A) orchestration | `graph.py` + `state.py` + `routing.py` + `chain.py` + `nodes/` — riêng của B |

### 11.5. Ràng buộc bổ sung cho B

- **Node mỏng:** thân mỗi node ≤ 15 câu lệnh, gọi đúng **một** use case. Dài hơn nghĩa là nghiệp vụ rơi vào graph → đẩy về `services/` hoặc `domain/`.
- **Thứ tự node cố định** ở `graph.py`; LLM không tự chọn tool/không tự quyết thứ tự. Có test kiểm đúng thứ tự.
- **`AgentServices`** (`services/registry.py`) chỉ chứa use case được phép vào graph; use case nhóm `operations/` không bao giờ vào graph. Dựng ở `composition.py`, cho phép inject toàn fake khi test graph.
- **Transaction:** một lượt hội thoại KHÔNG phải một transaction; transaction bọc từng bước ghi qua `UnitOfWorkPort`, không bọc cả lượt (tránh treo pool khi node gọi LLM).
- **Test** đặt tại `tests/agents/` với `unit/{domain,tools,services}` + `integration/`; bắt buộc thêm `test_layer_boundary.py` (domain sạch framework) và `test_graph_boundary.py` (nodes/ tuân luật 11.3, node ≤15 câu, AgentServices chỉ advisory).
