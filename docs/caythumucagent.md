# Cây thư mục `src/agents/` — A1→A10 code ở đâu

> Trả lời đúng một câu hỏi: **"làm task Ax-y thì mở file nào?"**
> Nguồn: [vinfast-agent-mvp.md](vinfast-agent-mvp.md) mục 6.0 + mục 8. Trạng thái code tại commit `a546874`.
> Xem thêm: [node_agent.md](node_agent.md) (luồng graph, state, routing).

**Ký hiệu**

| | Nghĩa |
|---|---|
| ✅ | Đã có trong code, chạy được |
| 🟡 | Đã có nhưng là **STUB** — file tồn tại, thân rỗng/giả |
| 🔨 | **Chưa tồn tại** — phải tạo mới |
| `[Ax-y]` | Task sở hữu file đó (task khác đừng đụng vào) |

---

## 1. Cây đầy đủ

```text
src/agents/
│
├── ✅ __init__.py
├── ✅ composition.py                    composition root: settings → adapters → services → build_graph()
│                                        [A0-5] nối UnitOfWork · mọi gate đều đăng ký service mới ở đây
│
│ ═══ ĐIỀU PHỐI ═══ (ở gốc). Chỉ nối, KHÔNG nghiệp vụ. Cấm import sqlalchemy/adapters/domain
├── ✅ graph.py                          [A4-2] build_graph: add_node / add_edge / add_conditional_edges
├── ✅ state.py                          AgentState (TypedDict). CHỈ khai báo, không logic
├── ✅ routing.py                        [A4-1] [A4-3] [A6-1] hàm thuần: đọc state → trả tên nhánh
├── ✅ protocol.py                       kiểu node dùng chung: (AgentState) -> dict
├── 🔨 chain.py                          [A4-4] nạp state từ repo → invoke graph → trả DTO cho api/
│                                        ⚠️ THIẾU — đây là cầu nối duy nhất giữa HTTP và graph
├── 🟡 legacy_graph.py                   [A4-4] XOÁ khi endpoint thật lên
│
├── nodes/                               13 node MỎNG ≤15 câu lệnh, mỗi node gọi ĐÚNG một service
│   ├── ✅ __init__.py                   AgentNodes: nhận AgentServices qua constructor
│   ├── 🟡 extract_slots.py              [A2-3] [A2-4] → services.slot_extraction
│   ├── 🟡 route_intent.py               [A4-1] [A4-6] → đọc state['intents'], KHÔNG gọi LLM
│   ├── 🟡 ask_or_retrieve.py            [A3-2] → services.slot_planning.next_question
│   ├── 🟡 layer1.py                     [A1-2] ADVISORY hard filter · [A4-1] CATALOG_LOOKUP resolve tên xe
│   ├── 🟡 relax.py                      [A4-3] → services.candidate_tuning.relax
│   ├── 🟡 narrow.py                     [A4-3] [A1-5] → services.candidate_tuning.narrow
│   ├── 🟡 layer2.py                     [A1-3] [A1-6] [A1-7] Need & Feature Retriever — 5 nhánh ẩn bên trong
│   ├── 🟡 layer3.py                     ⚠️ GỘP VÀO layer2 (plan mục 3) — code còn theo bản plan cũ
│   ├── 🟡 score.py                      [A5-3] [A5-7] → services.recommendation
│   ├── 🟡 tco.py                        [A5-5] → services.tco_estimation
│   ├── 🟡 synthesize.py                 [A5-6] → services.synthesis
│   ├── 🟡 guardrail.py                  [A6-1] → services.verification
│   └── 🟡 enqueue_hitl.py               [A7-1] → ghi review_queue qua UnitOfWork
│
│ ═══ HỢP ĐỒNG ═══ (public seams — node/service/adapter đều trỏ vào). Ở GỐC, không lồng
├── 🔨 ports.py                          [A0-3] LLMPort, EmbeddingPort, CatalogReadPort,
│                                        FeatureRetrievalPort, ClockPort, UnitOfWorkPort,
│                                        SessionRepository, RunRepository, ReviewQueueRepository,
│                                        NoticeRepository
├── 🔨 contracts.py                      [A0-3] DTO vào/ra + tool schema trích slot + FeatureAssertion [A1-3]
├── 🔨 errors.py                         [A0-3] lỗi application-level
├── ✅ models.py                         SQLAlchemy 15 bảng agent (AgentBase) — ĐÃ MIGRATE THẬT
├── 🔨 settings.py                       [A0-3] prefix AGENT_*
│
│ ═══ NGHIỆP VỤ ═══ Biết domain + port. CẤM import langgraph / adapters cụ thể / nodes
├── services/
│   ├── ✅ __init__.py
│   ├── 🟡 registry.py                   AgentServices — 12 use case advisory (hiện RỖNG)
│   │
│   │  ── nhóm advisory: CHỈ node trong graph gọi
│   ├── 🔨 conversation.py               [A2-2] nạp/ghi phiên + slot; nguồn sự thật của state
│   ├── 🔨 slot_extraction.py            [A2-3] LLM function calling, validate Pydantic
│   ├── 🔨 slot_planning.py              [A3-2] gọi domain.slot_policy, trả TỐI ĐA 1 câu hỏi
│   ├── 🔨 intent_routing.py             [A4-1] [A4-6] ADVISORY / CATALOG_LOOKUP (list, không vô hướng)
│   ├── 🔨 retrieval.py                  [A1-2] [A1-3] [A1-6] [A1-7] điều phối Lớp 1 → Lớp 2,
│   │                                    [A4-4] áp pending_feature_mentions
│   ├── 🔨 candidate_tuning.py           [A4-3] relax ≤2 lần, narrow ngưỡng 1–5
│   ├── 🔨 snapshotting.py               [A5-2] ghi run_snapshots BẤT BIẾN
│   ├── 🔨 recommendation.py             [A5-3] [A5-4] [A5-7] scoring + so sánh + giới thiệu feature
│   ├── 🔨 tco_estimation.py             [A5-5] nạp tco_assumptions, gọi tools.tco
│   ├── 🔨 synthesis.py                  [A5-6] prompt chỉ từ snapshot, mỗi số kèm evidence_id
│   ├── 🔨 verification.py               [A6-1] guardrail hậu-synthesis, retry ≤2
│   ├── 🔨 scope_classifier.py           [A6-2] gán nhãn, ghi out_of_scope_log, luôn kèm lối thoát
│   │
│   └── operations/                      ⚠️ CHỈ route HTTP gọi — KHÔNG BAO GIỜ vào graph
│       ├── 🔨 __init__.py
│       ├── 🔨 review.py                 [A7-2] claim CAS + lease 15' · [A7-3] duyệt/sửa/từ chối
│       ├── 🔨 booking.py                [A8-2] lái thử từ run ĐÃ DUYỆT
│       ├── 🔨 history.py                [A8-3] lịch sử + phân quyền theo người phụ trách
│       ├── 🔨 notices.py                [A8-4] thông báo nội bộ + trạng thái đã đọc từng người
│       └── 🔨 analytics.py              [A9-1] phễu funnel_metrics
│
│ ═══ THUẦN ═══ CẤM import FastAPI / SQLAlchemy / LangGraph / LLM SDK. Test không cần DB, không cần LLM
├── domain/
│   ├── 🔨 __init__.py
│   ├── 🔨 entities.py                   [A0-3] Session, CustomerProfile, AgentRun, Candidate, Evidence
│   ├── 🔨 values.py                     [A0-3] SlotName, SlotValue, VehicleType, Intent, RunState,
│   │                                    ScopeLabel, Money
│   ├── 🔨 errors.py                     [A0-3] TcoUnavailable, FeatureNotApplicable,
│   │                                    MissingRequiredSlot, TerminalReason
│   ├── 🔨 slot_tree.py                  [A3-1] cây phân nhánh CAR / ELECTRIC_MOTORBIKE
│   ├── 🔨 slot_policy.py                [A3-2] next_question + bộ slot bắt buộc
│   ├── 🔨 slot_mapping.py               [A3-3] slot → cột schema; preference vs hard filter
│   ├── 🔨 need_tags.py                  [A1-4b] tập need_tag ĐÓNG + mô tả tiếng Việt
│   ├── 🔨 scoring.py                    [A5-3] xếp hạng, tối đa 3 mẫu, ≥2 lý do/mẫu
│   ├── 🔨 comparison.py                 [A5-4] bảng so sánh, chặn so chéo loại xe
│   ├── 🔨 guardrail.py                  [A6-1] trích số trong câu trả lời, đối chiếu snapshot
│   └── 🔨 scope.py                      [A6-2] IN_SCOPE / MISSING_DATA / OUT_OF_SCOPE
│
├── tools/                               STRUCTURED TOOL tính toán deterministic
│   ├── ✅ __init__.py
│   └── 🔨 tco.py                        [A5-5] vinfast_tco_v1, horizon 60 tháng, Decimal half-up,
│                                        test golden vector
│
│ ═══ I/O ═══ Nơi DUY NHẤT biết SQLAlchemy / LLM SDK. CẤM import nodes/ services/
├── adapters/
│   ├── 🔨 __init__.py
│   ├── 🔨 repositories.py               [A2-2] [A5-1] [A7-1] [A8-1] implement repository port;
│   │                                    KHÔNG tự mở session
│   ├── 🔨 unit_of_work.py               [A0-5] implement UnitOfWorkPort
│   ├── 🔨 catalog_read.py               [A1-2] Lớp 1 SQL builder · [A1-5] differentiator query
│   ├── 🔨 feature_retrieval.py          [A1-3] nhánh 2c/2d SQL flags + need tags
│   │                                    [A1-7] nhánh 2a/2b khớp vector in-memory
│   │                                    [A1-6] nhánh 2e hybrid dense+FTS, RRF k=60, ghi ngược PENDING
│   │                                    ⚠️ [A10-4] DÙNG LẠI hàm ghi ngược ở đây, không viết code path 2
│   ├── 🔨 llm.py                        [A0-3] implement LLMPort
│   ├── 🔨 embedding.py                  [A0-3] implement EmbeddingPort qua langchain-openai
│   ├── 🔨 clock.py                      [A0-3] implement ClockPort
│   └── 🔨 migrations_check.py           [A0-3] kiểm tra migration lúc startup
│
├── prompts/                             CÂU CHỮ gửi LLM. Hình dạng slot ở contracts.py, không ở đây
│   ├── 🔨 __init__.py
│   ├── 🔨 slot_extraction_prompts.py    [A2-3] ⚠️ [A2-4] KHÔNG viết cứng feature_code vào đây
│   ├── 🔨 intent_prompts.py             [A4-1]
│   ├── 🔨 synthesis_prompts.py          [A5-6] + persona giọng tư vấn viên (mục 6.11)
│   └── 🔨 scope_prompts.py              [A6-2]
│
└── api/                                 HTTP boundary. Gọi services/operations/, KHÔNG đi qua graph
    ├── 🔨 __init__.py
    ├── 🔨 routes.py                     [A4-4] endpoint hội thoại — THAY /chat cũ
    ├── 🔨 review_routes.py              [A7-3]
    ├── 🔨 booking_routes.py             [A8-2]
    ├── 🔨 history_routes.py             [A8-3]
    ├── 🔨 notice_routes.py              [A8-4]
    ├── 🔨 analytics_routes.py           [A9-1]
    ├── 🔨 schemas.py
    └── 🔨 dependencies.py
```

**Đếm nhanh:** 25 file `.py` đã có (14 trong đó là stub rỗng ruột), **~59 file phải tạo mới**. Nặng nhất là `services/` (18 file) và `domain/` (12 file) — hai thư mục chưa tồn tại một dòng nào.

---

## 2. Ngoài `src/agents/`

```text
migrations/agents/versions/
├── ✅ agent_0001_vector_extension.py    [A1-1] CREATE EXTENSION vector
├── ✅ agent_0002_conversation_schema.py [A2-1] 5 bảng hội thoại
├── ✅ agent_0003_run_schema.py          [A5-1] 6 bảng run/snapshot/scoring/tco
├── ✅ agent_0004_review_queue.py        [A7-1] review_queue
├── ✅ agent_0005_booking_notice.py      [A8-1] booking + notices
└── ✅ agent_0006_funnel_metrics.py      [A9-1] VIEW funnel_metrics
        ⚠️ Cả 6 ĐÃ upgrade head trên Postgres thật. KHÔNG SỬA — cần đổi thì thêm revision mới

src/api/router.py                  🟡 [A4-4] include agents router, bỏ legacy /chat  ⚠️ ĐANG VỠ (xem §5)
src/api/routes.py                  🟡 [A4-4] XOÁ — /chat legacy
ARCHITECTURE.md                    🔨 [A4-5] bỏ ReAct, bỏ rerank, vẽ lại theo A4-2
docs/architecture_diagram.md       🔨 [A4-5] cùng nội dung trên
data/seeds/feature_definitions.py  🔨 [A1-4] 7 feature ô tô + 5 feature xe máy điện
                                   🔨 [A1-4b] seed feature_need_tags
eval/datasets/kpi_questions.yaml   🔨 [A9-3] ≥50 câu hỏi
eval/results/                      🔨 [A9-3] baseline KPI-1/2/4 + báo cáo p95 ≤ 6s

tests/agents/
├── ✅ unit/test_graph_skeleton.py       khung graph (đang xanh)
├── 🔨 unit/domain/                      slot_tree, slot_policy, slot_mapping, scoring,
│                                        comparison, guardrail, scope
├── 🔨 unit/tools/                       tco golden vector — không DB, không LLM
├── 🔨 unit/services/                    advisory + operations, dùng fake adapter
├── ✅ integration/test_migrations.py
├── ✅ integration/test_constraints.py
├── 🔨 integration/test_unit_of_work.py  [A0-5]
├── 🔨 integration/test_layer_boundary.py  [A0-3] domain không import framework
├── 🔨 integration/test_graph_boundary.py  [A0-3] nodes/ không import sqlalchemy/adapters/domain
├── 🔨 integration/test_retrieval_layers.py [A1] Lớp 1 + 5 nhánh Lớp 2
├── 🔨 integration/test_graph_flow.py    [A4-2] thứ tự node cho cả hai nhánh intent
└── 🔨 integration/test_e2e_frozen.py    [A9-2] CAR + ELECTRIC_MOTORBIKE, seed cố định
```

---

## 3. Tra ngược: gate → file

Mở đúng những file này, không mở gì khác.

### A1 — Hai lớp truy xuất

| Task | File chính | File phụ |
|---|---|---|
| A1-1 | `migrations/agents/versions/agent_0001_*` ✅ đã xong | — |
| A1-2 | `adapters/catalog_read.py` | `services/retrieval.py`, `nodes/layer1.py` |
| A1-3 | `adapters/feature_retrieval.py` (2c/2d) | `contracts.py` (FeatureAssertion), `nodes/layer2.py` |
| A1-4 | `data/seeds/feature_definitions.py` | — (không đụng `src/agents/`) |
| A1-4b | `data/seeds/` + `domain/need_tags.py` | — |
| A1-5 | `adapters/catalog_read.py` (differentiator query) | `services/candidate_tuning.py` |
| A1-6 | `adapters/feature_retrieval.py` (2e hybrid RRF + ghi ngược) | — |
| A1-7 | `adapters/feature_retrieval.py` (2a/2b) + `adapters/embedding.py` | `composition.py` (nạp vector lúc khởi động) |

### A2 — Hội thoại và trích slot

| Task | File chính | File phụ |
|---|---|---|
| A2-1 | `migrations/.../agent_0002_*` ✅ đã xong | `models.py` ✅ |
| A2-2 | `services/conversation.py` + `adapters/repositories.py` | `ports.py` |
| A2-3 | `services/slot_extraction.py` + `prompts/slot_extraction_prompts.py` | `contracts.py`, `adapters/llm.py`, `nodes/extract_slots.py` |
| A2-4 | `services/slot_extraction.py` (build enum từ DB tại runtime) | `adapters/catalog_read.py` |

### A3 — Slot engine (thuần, không DB, không LLM)

| Task | File chính |
|---|---|
| A3-1 | `domain/slot_tree.py` |
| A3-2 | `domain/slot_policy.py` + `services/slot_planning.py` + `nodes/ask_or_retrieve.py` |
| A3-3 | `domain/slot_mapping.py` |

### A4 — Wiring LangGraph

| Task | File chính | File phụ |
|---|---|---|
| A4-1 | `services/intent_routing.py` + `routing.py` | `prompts/intent_prompts.py`, `nodes/route_intent.py` |
| A4-2 | `graph.py` ✅ khung đã có | `state.py` ✅ |
| A4-3 | `routing.py` (ngưỡng) + `services/candidate_tuning.py` | `nodes/relax.py`, `nodes/narrow.py` |
| A4-4 | `chain.py` 🔨 + `api/routes.py` 🔨 | xoá `src/api/routes.py`, sửa `src/api/router.py`, xoá `legacy_graph.py` |
| A4-5 | `ARCHITECTURE.md`, `docs/architecture_diagram.md` | (không đụng code) |
| A4-6 | `services/intent_routing.py` + `contracts.py` (`intents: list[Intent]`) | `nodes/route_intent.py` |

### A5 — Đề xuất, TCO, synthesis

| Task | File chính | File phụ |
|---|---|---|
| A5-1 | `migrations/.../agent_0003_*` ✅ đã xong | `models.py` ✅ |
| A5-2 | `services/snapshotting.py` | `adapters/repositories.py` |
| A5-3 | `domain/scoring.py` + `services/recommendation.py` | `nodes/score.py` |
| A5-4 | `domain/comparison.py` | `services/recommendation.py` |
| A5-5 | `tools/tco.py` + `services/tco_estimation.py` | `nodes/tco.py` |
| A5-6 | `services/synthesis.py` + `prompts/synthesis_prompts.py` | allowlist `fact_code`, `nodes/synthesize.py` |
| A5-7 | `services/recommendation.py` + `domain/need_tags.py` | — |

### A6 — Guardrail và phạm vi

| Task | File chính | File phụ |
|---|---|---|
| A6-1 | `domain/guardrail.py` + `services/verification.py` | `routing.py`, `nodes/guardrail.py` |
| A6-2 | `domain/scope.py` + `services/scope_classifier.py` + `prompts/scope_prompts.py` | `adapters/repositories.py` (out_of_scope_log) |

### A7 — HITL (từ đây trở đi: `operations/`, KHÔNG vào graph)

| Task | File chính | File phụ |
|---|---|---|
| A7-1 | `migrations/.../agent_0004_*` ✅ | `nodes/enqueue_hitl.py` (node duy nhất của A7 trong graph) |
| A7-2 | `services/operations/review.py` (CAS + lease) | `adapters/repositories.py`, `adapters/unit_of_work.py` |
| A7-3 | `services/operations/review.py` + `api/review_routes.py` | — |

### A8 — Lái thử, lịch sử, thông báo

| Task | File chính |
|---|---|
| A8-1 | `migrations/.../agent_0005_*` ✅ |
| A8-2 | `services/operations/booking.py` + `api/booking_routes.py` |
| A8-3 | `services/operations/history.py` + `api/history_routes.py` |
| A8-4 | `services/operations/notices.py` + `api/notice_routes.py` |

### A9 — Dashboard, E2E, KPI

| Task | File chính |
|---|---|
| A9-1 | `migrations/.../agent_0006_*` ✅ + `services/operations/analytics.py` + `api/analytics_routes.py` |
| A9-2 | `tests/agents/integration/test_e2e_frozen.py` + seed cố định |
| A9-3 | `eval/datasets/kpi_questions.yaml`, `eval/results/` |

### A10 — Nạp brochure PDF

⚠️ **A10 gần như KHÔNG nằm trong `src/agents/`.** Plan mục 6.0 không vẽ cây cho gate này.

| Task | Code ở đâu |
|---|---|
| A10-1 | module `document` — ghi bảng `documents`, chống trùng bằng `content_hash` |
| A10-2 | module `document` — PDF → text theo trang, giữ `page_number` / `section_title` |
| A10-3 | module `document` — chunk + embed → `vehicle_documents` `status='DRAFT'`. Dùng `EmbeddingPort` |
| A10-4 | **`src/agents/adapters/feature_retrieval.py`** — DÙNG LẠI đúng hàm ghi ngược của A1-6 |
| A10-5 | Admin endpoint duyệt hàng loạt (module `product`/`document`), chỉ role `ADMIN` |

---

## 4. Thứ tự thi công

```text
A0 ──> A1 ──> A4 ──> A5 ──> A6 ──> A7 ──> A8 ──> A9
  │      └──────────> A10 ────────────────────────┘
```

A2, A3 chen giữa A1 và A4 (A4-1 cần A2-3, A4-3 cần A3-2). A10 chạy song song ngay sau A1-4.

**Bốn nhóm file theo thứ tự nên viết trong mỗi gate:**

```
1. domain/         (thuần, test không cần DB/LLM)  →  viết trước, sai thì rẻ
2. ports.py        (khai báo hợp đồng)
3. adapters/       (implement port, biết SQL/LLM)
4. services/       (ghép domain + port)
5. nodes/          (≤15 câu lệnh, gọi 1 service)   →  viết sau cùng, chỉ là dây nối
```

---

## 5. Ba cảnh báo trước khi gõ dòng đầu tiên

**1. App đang KHÔNG chạy được.** [src/api/routes.py:3](../src/api/routes.py#L3) import `agent` từ `src.agents.graph` — symbol không tồn tại → `ImportError` → `src.main` fail. Sửa tạm: `from src.agents.legacy_graph import legacy_agent as agent`. Sửa đúng: làm A4-4.

**2. `layer3.py` sẽ bị xoá.** Plan hiện hành (mục 3) đã gộp `layer2` + `layer3` thành một node "Need & Feature Retriever" với 5 nhánh ẩn. Code còn theo bản plan cũ. Gộp trước, rồi hãy viết ruột A1.

**3. Luật import một chiều — vi phạm là hỏng kiến trúc, sửa lại rất đắt.**

| Thư mục | ĐƯỢC gọi | CẤM import |
|---|---|---|
| `nodes/`, `graph.py`, `routing.py`, `chain.py` | `services/` qua `AgentServices`, đọc/ghi `state` | `sqlalchemy`, `adapters/`, `domain/` |
| `services/` (gồm `operations/`) | `domain/`, `tools/`, `ports.py`, `contracts.py` | `langgraph`, `adapters/` cụ thể, `nodes/` |
| `domain/`, `tools/` | thuần Python | `langgraph`, `sqlalchemy`, `fastapi`, LLM SDK |
| `adapters/` | implement `ports.py`; biết `sqlalchemy`/LLM SDK | `nodes/`, `services/` |
| `api/` | `services/operations/` | đi qua graph cho việc operations |

Cộng thêm ba ràng buộc có test cưỡng chế ở A0-3:
- Thân mỗi node **≤ 15 câu lệnh** (dài hơn = nghiệp vụ đang rơi vào graph).
- `AgentServices` **chỉ** chứa 12 use case advisory — 5 use case `operations/` không bao giờ vào.
- `AgentState` **chỉ** đựng domain value và DTO — tuyệt đối không object SQLAlchemy hay DB session.
