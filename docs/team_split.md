# Chia việc 4 người — module `agent`

Tài liệu này chia 50 task của `docs/vinfast-agent-mvp.md` thành **4 khối chạy song song**, sao cho đầu vào/đầu ra của người này không chặn người kia. Khi khối phụ thuộc chưa xong, mỗi người **mock** đầu vào và vẫn hoàn thành được phần của mình.

Đọc kèm: `docs/vinfast-agent-mvp.md` (đặc tả task), `docs/vehicle-catalog-schema.md` (schema catalog), `docs/backend-module-standard.md` (chuẩn module).

---

## 1. Nguyên tắc chia

**Chia theo trách nhiệm, không chia theo gate.** Gate A0→A10 là thứ tự *xây*, không phải ranh giới *sở hữu*. Luật phụ thuộc một chiều ở §6.5b (`nodes → services → domain`, `adapters → ports`) mới là thứ tạo ra đường cắt sạch.

**Ba điều kiện để song song hoá được, cả ba đều đã sẵn:**

| Điều kiện | Trạng thái |
|---|---|
| Có seam tường minh giữa các phần | `ports.py` + `contracts.py` + `AgentServices` — §6.2, §6.3 |
| Test không cần hệ thống thật | §6.3: *"test graph chỉ cần một `AgentServices` toàn fake, không DB, không LLM"* |
| Không tranh nhau migration | **0 migration mới** trong cả 50 task — `agent_0001`…`0006`, `d4e5f6a7b8c9`, `d0cument0002` đã `upgrade head` trên Postgres thật |

Điều kiện thứ ba là thứ thường phá hỏng mọi kế hoạch chia việc song song (hai người cùng `alembic revision` → xung đột thứ tự). Dự án này đã thoát khỏi nó.

**Mỗi thư mục có đúng một chủ.** Ba file buộc phải dùng chung được xử lý riêng ở mục 3.

---

## 2. Ngày 0 — việc chung, không chia được

**A0 (5 task) không thuộc khối nào.** Cả nhóm làm cùng, 1–2 ngày. Lý do: A0 định nghĩa chính các đường ráp; chia A0 ra là mỗi người tự định nghĩa một cái ráp riêng, xong không khớp.

| Task | Việc |
|---|---|
| A0-1 | Hạ tầng pgvector + dependency — **đã xong** (§4 plan) |
| A0-2 | Alembic cho module agent — **đã xong**, `agent_alembic_version = agent_0006` |
| A0-3 | Khung graph-centric — **đang dở**: đã có 13 node stub, `graph.py`, `state.py`, `routing.py`, `composition.py`, `services/registry.py`, `models.py`; **còn thiếu** `ports.py`, `contracts.py`, `errors.py`, `domain/`, `adapters/`, `api/`, `prompts/` |
| A0-4 | Đóng băng contract `/chat` cũ |
| A0-5 | Unit of work |

### 2.1. Năm file phải đóng băng trước khi tách nhóm

Tất cả đều là **stub** — chữ ký đầy đủ, thân hàm `raise NotImplementedError`.

| File | Phải khai báo gì |
|---|---|
| `src/agents/contracts.py` | `FeatureAssertion`, DTO slot, `Intent`, DTO đề xuất, DTO kết quả TCO, DTO câu trả lời |
| `src/agents/ports.py` | `LLMPort`, `EmbeddingPort`, `CatalogReadPort`, `FeatureRetrievalPort`, `ClockPort`, `UnitOfWorkPort` + 4 repository — **chữ ký**, không phải thân |
| `src/agents/state.py` | toàn bộ field của `AgentState` (kể cả field khối khác sẽ dùng) |
| `src/agents/domain/values.py` | `SlotName`, `SlotValue`, `VehicleType`, `Intent`, `RunState`, `ScopeLabel`, `Money` |
| `src/agents/services/registry.py` | `AgentServices` đủ **12 field** nhóm advisory (§6.3) |

### 2.2. Luật sau đóng băng

> **Đổi một chữ ký = một PR riêng, cả 4 người duyệt. Đổi thân hàm = tự do.**

PR đổi contract phải nêu: ai đang phụ thuộc vào chữ ký cũ, và họ phải sửa gì. Nếu một khối phải viết lại logic vì contract đổi, đó là tín hiệu contract ban đầu sai — dừng lại và bàn, đừng vá.

### 2.3. Nợ phải trả trước hoặc song song A0

| Nợ | Ảnh hưởng ai | Mức |
|---|---|---|
| `src/api/routes.py:3` import `agent` từ `src.agents.graph` (không còn tồn tại) → **toàn bộ `pytest` không chạy** | cả 4 khối | chặn, sửa ngay, ~1 dòng |
| §4.12 / §7.4 / §7.5 `vehicle-catalog-schema.md` chưa viết, plan dẫn 13 lần | Khối 1 (A1-4b), Khối 3 (A5-6, A5-7) | chặn 4 task |
| `docs/vehicle-catalog-api.md`, `docs/agent-schema-build-plan.md` được dẫn nhưng không tồn tại | Khối 1, Khối 4 | vừa, xác nhận mất thật hay đổi tên |

---

## 3. Ba file dùng chung

Không tránh được, nhưng làm cho conflict chỉ còn một dòng:

| File | Cách xử lý |
|---|---|
| `src/agents/nodes/__init__.py` | A0 khai báo **đủ 12 attribute** ngay từ đầu, trỏ vào node stub. Về sau mỗi người chỉ thay stub bằng bản thật — **không** thêm/bớt dòng |
| `src/agents/composition.py` | A0 dựng đủ khung `settings → adapters → services → build_graph()`, mọi adapter là stub. Mỗi khối thay stub của mình bằng bản thật |
| `src/agents/services/registry.py` | Đóng băng ở A0. Sau đó **không ai sửa** trừ PR contract |

Quy ước commit: mỗi task một commit, message theo §7 plan (`feat(agent):` / `test(agent):` / `refactor(agent):` / `chore(agent):`), làm trên nhánh riêng của khối, merge vào nhánh tích hợp.

---

## 4. Khối 1 — Dữ liệu & truy xuất

**Gate A1 + A10 · 13 task**

### Mục tiêu

Biến câu khách và bộ slot thành **danh sách xe kèm bằng chứng**. Và đưa nội dung thật từ brochure PDF vào catalog — không có khối này thì cả hệ thống chạy trên dữ liệu rỗng.

### Task

| ID | Việc | Chặn |
|---|---|---|
| A1-1 | Migration `agent_0001` — **file đã chạy thật**, còn lại phần test nghiệm thu | A0-2 |
| A1-2 | Lớp 1 SQL hard filter theo slot nhu cầu | A0-3 |
| A1-3 | Lớp 2 nhánh 2c/2d — flags tri-state + nở nhu cầu | A1-2 |
| A1-4 | Seed `feature_definitions` (7 feature ô tô + 5 xe máy điện) | A1-3 |
| A1-4b | Seed `feature_need_tags` + tập `need_tag` đóng + mô tả tiếng Việt | A1-4 |
| A1-5 | Differentiator query | A1-4 |
| A1-6 | Lớp 2 nhánh 2e — đọc tài liệu có điều kiện + ghi ngược `PENDING` | A1-1, A1-4, A1-7 |
| A1-7 | Nhánh 2a/2b — khớp từ vựng + khớp nhu cầu, vector in-memory | A1-4b, A0-3 |
| A10-1 | Nạp file gốc, chống nạp trùng bằng `content_hash` | A0-2 |
| A10-2 | Trích text giữ cấu trúc, **bảng trang bị nguyên khối** | A10-1 |
| A10-3 | Chunk + embed → `vehicle_documents` `DRAFT` | A10-2, A1-1 |
| A10-4 | Đề xuất feature flags `PENDING` — **dùng lại đúng hàm ghi ngược của A1-6** | A10-3, A1-4, A1-6 |
| A10-5 | Màn hình Admin duyệt hàng loạt | A10-4, A8-4 |

### File sở hữu

```text
src/agents/adapters/catalog_read.py        Lớp 1 SQL builder + differentiator
src/agents/adapters/feature_retrieval.py   5 nhánh Lớp 2, implement FeatureRetrievalPort
src/agents/adapters/embedding.py           implement EmbeddingPort qua langchain-openai
src/agents/services/retrieval.py           điều phối Lớp 1 → Lớp 2
src/agents/domain/need_tags.py             tập need_tag đóng + mô tả tiếng Việt
src/agents/nodes/layer1.py
src/agents/nodes/layer2.py
data/seeds/feature_definitions.py
data/seeds/feature_need_tags.py
<module ingestion A10>                     nạp PDF → documents → vehicle_documents
tests/agents/integration/test_retrieval_layers.py
```

### Input

| Cần gì | Từ đâu | Mock thế nào |
|---|---|---|
| Schema catalog (12 bảng) | **đã có thật** trên Postgres | không cần mock |
| Schema agent (15 bảng) | **đã có thật** | không cần mock |
| Bộ slot đã khai thác | Khối 2 (A2/A3) | **dict viết cứng** — `{"vehicle_type": "CAR", "budget_max_vnd": 700_000_000, "passenger_count": 5}` |
| Brochure PDF | người dùng cung cấp | 2–3 file mẫu là đủ để làm A10 |

Khối 1 **không chờ ai**. Bắt tay được ngay ngày 0.

### Output — hợp đồng phải giao

```python
class CatalogReadPort(Protocol):
    async def hard_filter(self, criteria: FilterCriteria) -> list[UUID]: ...
    async def differentiators(self, vehicle_ids: list[UUID]) -> list[FeatureCode]: ...

class FeatureRetrievalPort(Protocol):
    async def resolve(
        self, utterance: str, vehicle_type: VehicleType,
        candidate_ids: list[UUID],
    ) -> list[FeatureAssertion]: ...
```

Ba bảo đảm mà khối khác được phép tin vào:

1. `FeatureAssertion.source == DOCUMENT` **không bao giờ** loại xe, **không bao giờ** đổi thứ hạng, **không bao giờ** cấp con số.
2. Không tìm thấy gì → `status = UNKNOWN`, **không bao giờ** `NO`.
3. Mọi assertion có `evidence_ref` truy được về một bản ghi cụ thể.

### Xong là gì

- Truyền một bộ slot vào → nhận về `list[FeatureAssertion]` từ DB thật, không mock
- Nạp một brochure PDF thật → sinh `vehicle_documents` `DRAFT` + đề xuất flag `PENDING`, Admin duyệt được
- Test: `≤ 1` vector search mỗi lượt; A10-4 và A1-6 gọi **cùng một** hàm ghi (assert bằng spy)

---

## 5. Khối 2 — Hội thoại & điều phối

**Gate A2 + A3 + A4 · 13 task**

### Mục tiêu

Hiểu khách nói gì, quyết định hỏi tiếp hay đi tra cứu, và **lắp toàn bộ graph**. Đây là khối sở hữu luồng — người khác cắm module vào luồng này.

### Task

| ID | Việc | Chặn |
|---|---|---|
| A2-1 | Migration `agent_0002` — **đã chạy**, còn phần test | A0-2 |
| A2-2 | Repository + use case phiên/slot (sửa slot là UPDATE, không append) | A2-1 |
| A2-3 | Trích slot bằng LLM function calling + parse tiếng Việt ("700 triệu", "1 tỷ 2") | A2-2 |
| A2-4 | Vocabulary feature build từ DB, **không** viết cứng trong prompt | A2-3, A1-4 |
| A3-1 | Cây slot phân nhánh CAR / ELECTRIC_MOTORBIKE | A0-3 |
| A3-2 | `next_question` — tối đa **một** câu hỏi mỗi lượt | A3-1, A2-2 |
| A3-3 | Ánh xạ slot sang cột schema | A3-1, A1-2 |
| A4-1 | Intent Router — gộp vào cùng lần gọi LLM của A2-3 | A1-6, A3-2 |
| A4-2 | State machine — lắp 12 node, short-circuit lượt hỏi slot | A4-1 |
| A4-3 | Nới lỏng (≤2 lần) và thu hẹp (ngưỡng 1–5) | A4-2, A1-5 |
| A4-4 | Áp pending feature + thay `/chat` cũ + nối vào `src/main.py` | A4-3, A2-3 |
| A4-6 | Multi-intent per-turn + nhắc slot sau lookup | A4-4 |
| A4-5 | Sửa `ARCHITECTURE.md` + `docs/architecture_diagram.md` cho khớp | A4-4 |

### File sở hữu

```text
src/agents/graph.py                     src/agents/routing.py
src/agents/chain.py                     src/agents/protocol.py
src/agents/nodes/extract_slots.py       src/agents/nodes/route_intent.py
src/agents/nodes/ask_or_retrieve.py     src/agents/nodes/relax.py
src/agents/nodes/narrow.py
src/agents/services/conversation.py     src/agents/services/slot_extraction.py
src/agents/services/slot_planning.py    src/agents/services/intent_routing.py
src/agents/services/candidate_tuning.py
src/agents/domain/slot_tree.py          src/agents/domain/slot_policy.py
src/agents/domain/slot_mapping.py
src/agents/prompts/slot_extraction_prompts.py
src/agents/prompts/intent_prompts.py
src/agents/api/routes.py                src/agents/api/dependencies.py
tests/agents/integration/test_graph_flow.py
```

### Input

| Cần gì | Từ đâu | Mock thế nào |
|---|---|---|
| `FeatureRetrievalPort` | Khối 1 | `FakeFeatureRetrieval` trả `list[FeatureAssertion]` viết cứng |
| `CatalogReadPort` | Khối 1 | `FakeCatalogRead` trả 3 UUID cố định |
| `feature_definitions` cho A2-4 | Khối 1 (A1-4) | list 12 dict trong fixture |
| Node `score`/`tco`/`synthesize`/`guardrail` | Khối 3 | **stub trả dict rỗng** — A4-2 đã ghi rõ là stub |

§6.3 bảo đảm điều này chạy được: `AgentServices` toàn fake, không DB, không LLM. Khối 2 xây và test **toàn bộ** graph mà không cần một dòng SQL nào của Khối 1.

### Output — hợp đồng phải giao

```python
# chain.py — điểm vào duy nhất cho HTTP
async def run_turn(session_id: UUID, utterance: str) -> TurnResult: ...

# AgentState — mọi khối đọc/ghi qua đây
class AgentState(TypedDict):
    slots: dict[str, Any]
    intents: list[Intent]
    pending_question: str | None
    do_retrieve: bool
    candidates: list[UUID]
    assertions: list[FeatureAssertion]
    relax_count: int
    ...
```

Ba bảo đảm:

1. Mỗi lượt gọi LLM đúng **1 lần** khi chỉ hỏi slot, **≤ 3 lần** khi đề xuất đầy đủ.
2. Thứ tự node cố định, test được không cần compile graph (`routing.py` là hàm thuần).
3. Slot bền qua các lượt — `conversation_slots` là nguồn sự thật duy nhất, không dùng checkpointer (§6.9).

### Xong là gì

- Gọi endpoint thật → hội thoại nhiều lượt, hỏi đúng thứ tự slot, không hỏi lại thứ đã biết
- `graph.py` compile được, `test_graph_flow.py` xanh cho cả hai nhánh intent
- Gỡ fake của Khối 1 → luồng chạy trên dữ liệu thật, **không sửa dòng logic nào**

---

## 6. Khối 3 — Đề xuất & kiểm chứng

**Gate A5 + A6 · 9 task**

### Mục tiêu

Từ candidate ra **câu trả lời có thể gửi cho khách**: xếp hạng, so sánh, TCO, viết thành lời, và chặn mọi số bịa. Ít task nhất nhưng khó nhất về logic.

### Task

| ID | Việc | Chặn |
|---|---|---|
| A5-1 | Migration `agent_0003` — **đã chạy**, còn phần test | A0-2 |
| A5-2 | Snapshot bất biến — mọi số về sau đọc từ snapshot | A5-1, A4-2 |
| A5-3 | Scoring — tối đa 3 mẫu, mỗi mẫu ≥2 lý do trỏ về slot | A5-2, A3-3 |
| A5-4 | So sánh 2–3 mẫu, chặn so chéo loại xe | A5-2 |
| A5-5 | TCO structured adapter `vinfast_tco_v1`; gọi calculator chuẩn trong Products, `Decimal`, golden vector và test hai luồng cùng tổng | A5-1 |
| A5-6 | Synthesis bằng **placeholder** — LLM không viết chữ số nào | A5-3, A5-4, A5-5 |
| A5-7 | Giới thiệu feature theo nhu cầu, không chào hàng | A5-3, A1-4b, A1-5 |
| A6-1 | Guardrail hậu-synthesis, retry ≤2 → `FAILED` | A5-6 |
| A6-2 | Phân loại ngoài phạm vi, luôn kèm lối thoát | A2-1, A4-2 |

### File sở hữu

```text
src/agents/services/snapshotting.py      src/agents/services/recommendation.py
src/agents/services/tco_estimation.py    src/agents/services/synthesis.py
src/agents/services/verification.py      src/agents/services/scope_classifier.py
src/agents/domain/scoring.py             src/agents/domain/comparison.py
src/agents/domain/guardrail.py           src/agents/domain/scope.py
src/agents/tools/tco.py                    # adapter contract, không chứa calculator thứ hai
src/agents/prompts/synthesis_prompts.py  src/agents/prompts/scope_prompts.py
src/agents/nodes/score.py                src/agents/nodes/tco.py
src/agents/nodes/synthesize.py           src/agents/nodes/guardrail.py
tests/agents/unit/domain/                tests/agents/unit/tools/
```

### Input

| Cần gì | Từ đâu | Mock thế nào |
|---|---|---|
| `list[FeatureAssertion]` | Khối 1 | **fixture JSON** — 3 xe, mỗi xe vài assertion, đủ cả `FLAG`/`DOCUMENT` và `YES`/`NO`/`UNKNOWN` |
| Bộ slot đã xác nhận | Khối 2 | dict viết cứng |
| `AgentState` sau `layer2` | Khối 2 | dựng tay `AgentState` trong test |
| `tco_assumptions` | Admin nhập (A10) | 2 dòng fixture — một cho `CAR`, một cho `ELECTRIC_MOTORBIKE` |

**`tools/tco.py` và `domain/` test được hoàn toàn không cần DB, không cần LLM** — đây là điều kiện plan đã đặt ra để A5 nghiệm thu bằng unit test thuần. Nghĩa là Khối 3 có thể hoàn thành gần như toàn bộ mà **không chờ ai**.

### Output — hợp đồng phải giao

```python
# vào AgentState
recommendations: list[Recommendation]   # ≤3, mỗi cái ≥2 lý do trỏ về slot
tco: TcoResult | None                   # hoặc TCO_UNAVAILABLE + tên field thiếu
draft_answer: str                       # đã thay placeholder, mỗi số kèm evidence_id
guardrail_ok: bool
terminal_reason: TerminalReason | None
```

Ba bảo đảm:

1. Mọi con số trong `draft_answer` truy được về một `evidence_id` trong `run_snapshots`.
2. LLM **không có cơ hội gõ số** — nó sinh placeholder, code điền. Số bịa là bất khả thi, không phải khó.
3. Guardrail sai 3 lần → `terminal_reason` khác rỗng → graph rẽ thẳng `END`, **không nội dung nào rời hệ thống**.

### Xong là gì

- Golden vector TCO khớp **tới đồng** cho cả `CAR` và `ELECTRIC_MOTORBIKE`
- Đưa fixture assertion vào → ra câu trả lời tiếng Việt tự nhiên, mọi số có nguồn
- Test: đầu ra không chứa tên cột, toán tử so sánh, hay mã slot/feature trần

---

## 7. Khối 4 — Vận hành & HTTP

**Gate A7 + A8 + A9 · 10 task**

### Mục tiêu

Mọi thứ **không đi qua graph**: hàng đợi duyệt, lái thử, lịch sử, thông báo, dashboard, và bộ nghiệm thu cuối.

### Task

| ID | Việc | Chặn |
|---|---|---|
| A7-1 | Migration `agent_0004` — **đã chạy**, còn phần test | A5-1 |
| A7-2 | Claim bằng compare-and-set + lease 15 phút | A7-1, A0-5 |
| A7-3 | Duyệt / sửa / từ chối; tư vấn viên sửa **văn bản**, không sửa số | A7-2, A6-1 |
| A8-1 | Migration `agent_0005` — **đã chạy**, còn phần test | A7-1 |
| A8-2 | Đặt lịch lái thử từ run **đã duyệt**, cùng transaction với thông báo | A8-1, A7-3, A0-5 |
| A8-3 | Lịch sử tư vấn + phân quyền theo người phụ trách | A8-1 |
| A8-4 | Thông báo nội bộ, trạng thái đã đọc riêng từng người | A8-1 |
| A9-1 | Migration `agent_0006` + view `funnel_metrics` — **đã chạy**, còn phần test | A8-2 |
| A9-2 | E2E đóng băng + golden sample review giọng | A9-1 |
| A9-3 | Baseline KPI-1/2/4, p95 ≤ 6s, judge offline trong `eval/` | A9-2 |

### File sở hữu

```text
src/agents/services/operations/review.py     src/agents/services/operations/booking.py
src/agents/services/operations/history.py    src/agents/services/operations/notices.py
src/agents/services/operations/analytics.py
src/agents/api/review_routes.py              src/agents/api/booking_routes.py
src/agents/api/history_routes.py             src/agents/api/notice_routes.py
src/agents/api/analytics_routes.py           src/agents/api/schemas.py
src/agents/nodes/enqueue_hitl.py
src/agents/adapters/repositories.py          src/agents/adapters/unit_of_work.py
eval/datasets/kpi_questions.yaml             eval/results/
tests/agents/integration/test_e2e_frozen.py
```

### Input

| Cần gì | Từ đâu | Mock thế nào |
|---|---|---|
| Bảng `agent_runs`, `review_queue`, `test_drive_bookings`, `internal_notices` | **đã có thật** trên Postgres | không cần mock |
| Run ở trạng thái `PENDING_REVIEW` | Khối 3 | **`INSERT` tay** một dòng `agent_runs` + `review_queue` |
| `draft_answer` để tư vấn viên duyệt | Khối 3 | chuỗi bất kỳ |

**Khối 4 độc lập nhất trong cả bốn.** §6.2 đã tách sẵn: `services/operations/` **không đi qua graph**, chỉ route HTTP gọi. Nó chỉ cần 15 bảng agent — mà cả 6 migration đã chạy thật rồi. Bắt tay được ngay ngày 0, không chờ một dòng code nào của ai.

### Output — hợp đồng phải giao

```python
# services/operations/* — route HTTP gọi thẳng, KHÔNG qua graph
async def claim(queue_id: UUID, advisor_id: str) -> ClaimResult: ...
async def approve(queue_id: UUID, advisor_id: str, edited: str | None) -> None: ...
async def book_test_drive(run_id: UUID, ...) -> Booking: ...
```

Ba bảo đảm:

1. Run chưa `APPROVED`/`EDITED` → endpoint gửi khách trả **409**, không đường nào bypass.
2. Hai tư vấn viên claim đồng thời → đúng một người thắng, người thua nhận thông báo rõ ràng chứ không phải lỗi chung chung.
3. Booking và thông báo in-app ghi **cùng một transaction** — đây là thứ thay thế cơ chế outbox đã cắt (§3).

### Xong là gì

- Tư vấn viên đăng nhập, thấy hàng đợi, claim, sửa, duyệt, khách nhận được
- Dashboard phễu ra số khớp bảng nguồn khi kiểm chéo
- Test âm: tư vấn viên A đọc hồ sơ khách của tư vấn viên B → **403**

---

## 8. Ma trận phụ thuộc chéo

Chỉ 8 chỗ một khối cần khối khác. Tất cả đều mock được:

| Task | Thuộc khối | Cần | Mock |
|---|---|---|---|
| A2-4 | 2 | A1-4 (Khối 1) | list 12 dict feature |
| A3-3 | 2 | A1-2 (Khối 1) | bảng ánh xạ viết tay |
| A4-1 | 2 | A1-6 (Khối 1) | `FakeFeatureRetrieval` |
| A4-3 | 2 | A1-5 (Khối 1) | list differentiator cứng |
| A5-2 | 3 | A4-2 (Khối 2) | dựng `AgentState` tay |
| A5-3 | 3 | A3-3 (Khối 2) | dict slot cứng |
| A5-7 | 3 | A1-4b, A1-5 (Khối 1) | fixture need tags |
| A7-3 | 4 | A6-1 (Khối 3) | `INSERT` tay `agent_runs` |
| A10-5 | 1 | A8-4 (Khối 4) | theo quy ước route của Khối 4 |

### Ba điểm ráp

```
Ngày 0-1  CẢ NHÓM: A0 + đóng băng contract
          ↓
song song K1 ──────────────────────────────► A1 → A10
          K2 ─────────────────────► A2, A3 → A4
          K3 ──────────► A5, A6         (chạy trên fixture)
          K4 ──────────► A7, A8, A9-1   (chạy trên INSERT tay)
          ↓
  ráp 1   K2 xoá FakeFeatureRetrieval  → graph chạy dữ liệu thật
  ráp 2   K3 xoá fixture assertion     → luồng đề xuất chạy thật
  ráp 3   K4 xoá INSERT tay            → HITL nhận run thật
          ↓
cuối      A9-2 E2E + A9-3 KPI — cần cả 4 khối
```

> **Mỗi lần ráp là *xoá* một fake, không phải viết lại gì.** Nếu phải viết lại logic thì contract đã sai — dừng, mở PR contract, đừng vá tại chỗ.

---

## 9. Cân bằng khối lượng

| Khối | Task | Ghi chú |
|---|---:|---|
| 1 — Dữ liệu & truy xuất | 13 | nặng nhất; A10 nhiều việc tay chân (xử lý PDF) |
| 2 — Hội thoại & điều phối | 13 | nhiều task nhưng A4 phần lớn là nối, không nghiệp vụ |
| 3 — Đề xuất & kiểm chứng | 9 | ít task nhất, **khó nhất về logic** — TCO tới đồng, guardrail, placeholder |
| 4 — Vận hành & HTTP | 10 | nhiều CRUD, độc lập nhất, khởi động sớm nhất |

Muốn cân hơn: chuyển **A10-5 sang Khối 4** (nó là màn hình Admin, cùng loại với A8-4) và **A1-5 sang Khối 3** (differentiator nuôi scoring và A5-7). Thành 11 / 13 / 11 / 11.

Sáu task migration (`A1-1`, `A2-1`, `A5-1`, `A7-1`, `A8-1`, `A9-1`) đã có file chạy thật trên Postgres — phần còn lại chỉ là test nghiệm thu `upgrade`/`downgrade`. Thực chi khoảng **44 task mới**, không phải 50.
