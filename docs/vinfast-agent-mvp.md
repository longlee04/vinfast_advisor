# Kế hoạch thi công Agent — VinFast AI Sales Advisor MVP

Bám PRD v1.2 (`docs/VinFast_AI_Sales_Advisor_PRD_v1_2.docx`), schema catalog (`docs/vehicle-catalog-schema.md`) và API Admin catalog (`docs/vehicle-catalog-api.md`).

Bản trước lưu tại `docs/vinfast-agent-mvp.old.md`.

## 1. TL;DR

Module `agent` là module thứ ba sau `auth` và `document`. Mục tiêu MVP: một Agent hội thoại **hỏi đủ slot trước khi đề xuất**, truy xuất dữ liệu qua **hai lớp** (SQL hard filter → Need & Feature Retriever), tính TCO bằng **structured tool**, tổng hợp câu trả lời **có trích dẫn**, chặn số liệu bịa bằng **guardrail**, và **không gửi gì cho khách trước khi tư vấn viên duyệt**.

Chia thành **11 gate** (A0–A10), mỗi gate gồm **các task nhỏ độc lập**, mỗi task **một commit** trên nhánh hiện tại. Tổng 50 task.

A0–A9 xây **năng lực**, A10 nạp **nội dung** từ brochure PDF (đầu vào thật của dự án là một PDF cho mỗi mẫu xe). Không có A10 thì hệ thống chạy trên catalog rỗng.

Sáu migration Alembic cho module `agent` (ban đầu bốn, tách `agent_0004`/`agent_0005`/`agent_0006` ở mục 5 để không ai sửa migration người khác đã commit), không phải tám như bản plan cũ. Mọi thứ không nằm trong PRD 6.1 đều bị cắt và ghi rõ ở mục 3. Module `product`/`document` mà `agent` đọc vào đã có migration riêng, đã chạy — không tính vào sáu migration này.

## 2. Phạm vi

### 2.1. Trong phạm vi (map PRD 6.1)

| Hạng mục PRD 6.1 | PRD mục | Gate |
|---|---|---|
| Agent hội thoại thu thập nhu cầu | 5.1 | A2, A3 |
| Tra cứu catalog hai lớp (ô tô + xe máy điện) | 5.2, 8.7 | A1, A4 |
| Đề xuất 1–3 mẫu kèm lý do | 5.3 | A5 |
| So sánh 2–3 mẫu | 5.4 | A5 |
| Bảng ước tính TCO | 5.5 | A5 |
| Lưu hồ sơ + lịch sử tư vấn | 5.8 | A2, A8 |
| Hàng đợi HITL | 5.6 | A7 |
| Nút chuyển đặt lịch lái thử | 5.7 | A8 |
| Trả lời an toàn khi thiếu dữ liệu / ngoài phạm vi | 5.9 | A6 |
| Quản lý catalog Admin | 5.11 | A1 (đọc), module `products`/`document` (ghi, đã dựng), A10 (nạp brochure + duyệt đề xuất) |
| Thông báo chính sách nội bộ | 5.12 | A8 |
| Dashboard phễu mức cơ bản | 5.10 | A9 |

### 2.2. Ngoài phạm vi

Từ PRD 6.2: memory dài hạn, so sánh chuyên sâu đa tiêu chí cá nhân hoá, LLM-as-Judge tự động, dashboard chi tiết, tối ưu retrieval/rerank quy mô lớn, trạm sạc / thuê pin / đặt lịch bảo dưỡng.

**Phân biệt hai loại LLM-as-Judge** (hay bị lẫn khi đọc dòng trên):

| | Trong sản phẩm | Trong CI |
|---|---|---|
| Vị trí | node cuối graph, chấm trước khi trả lời | script trong `eval/`, chạy hàng đêm |
| PRD 6.2 | **ngoài phạm vi** | không liên quan — là công cụ test, cùng loại `pytest` |
| MVP | không làm | A9-3 |

Judge **online** bị loại không chỉ vì PRD. Cuối luồng đã có bốn cửa — synthesis bằng placeholder (A5-6, LLM không được gõ chữ số nào), guardrail (A6-1), scope classifier (A6-2), và HITL (A7, con người). Judge chỉ bắt thêm được nhóm "giọng thô / lạc đề", mà nhóm đó **A7 đang bắt bằng người** và người đó là bắt buộc theo tiêu chí hoàn thành 3. Đặt máy chấm trước mặt người chấm thì không bỏ được người, chỉ cộng thêm: lần gọi LLM thứ tư phá ngân sách A4-2, và một gate phi tất định phá tính tái lập của E2E đóng băng A9-2. Judge là **thứ thay thế HITL** nếu sau này có luồng gửi thẳng cho khách, không phải thứ bổ sung cho HITL.

Cắt thêm so với bản plan cũ, lý do ở mục 3: outbox dispatch với retry, revalidation digest + reapproval conflict, broadcast fan-out, governance test quét repo, admin policy versioning.

Corpus kiến thức chung cấp hãng (Global RAG — trả lời câu không gắn xe cụ thể) cũng **ngoài MVP** vì không thuộc PRD 6.1, nhưng đã được đặc tả đủ để thi công ngay sau MVP ở **mục 11**.

## 3. Những gì bị cắt so với bản plan cũ

| Bản cũ | Quyết định | Lý do |
|---|---|---|
| Outbox `dispatch_state` + 4 lần retry + `FOR UPDATE SKIP LOCKED` | Cắt. Ghi thẳng `internal_notices` / thông báo in-app trong cùng transaction | PRD 5.7 AC chỉ yêu cầu "xác nhận trong ứng dụng, tối thiểu MVP". Không có kênh ngoài (email/SMS) ở MVP nên không có gì để retry |
| Revalidation digest + `409` reapproval + transaction SERIALIZABLE | Cắt. Thay bằng snapshot tại thời điểm truy vấn | PRD 5.11 AC: "các phiên đang tra cứu dở dùng dữ liệu tại thời điểm truy vấn". Snapshot bất biến là đủ, không cần so digest |
| Policy broadcast fan-out theo audience + versioning | Cắt. Hai bảng `internal_notices` + `notice_reads` | Đúng nguyên văn PRD 5.12 phần Dữ liệu liên quan |
| Test governance quét repo tìm provider E5 | Cắt hoàn toàn | Không tồn tại provider E5 nào trong repo. Bản cũ dựng hàng rào cho thứ không có |
| Tám migration `agent_0001`…`0008` | Gộp còn bốn lúc viết lại lần đầu, sau đó tách lại thành sáu (mục 5) khi phát hiện A8-1 phải sửa migration A7-1 đã commit | Mỗi migration cũ mở một bảng lẻ; gộp theo ranh giới nghiệp vụ giúp rollback có nghĩa, nhưng gộp quá tay lại phạm nguyên tắc không sửa migration đã commit |
| Báo cáo cả 7 KPI | Chỉ KPI-1, KPI-2, KPI-4 | PRD 12.5 chỉ yêu cầu baseline ba KPI này ở Sprint 4. KPI-3/5/6/7 cần dữ liệu vận hành thật |
| Ma trận ~25 endpoint HTTP dàn đều mọi gate | Rút về đúng endpoint có AC PRD | Endpoint không có AC thì không có cách nghiệm thu |
| Rerank bằng BGE-reranker-v2-m3 (đang ghi trong `ARCHITECTURE.md`) | Cắt khỏi MVP. Nhánh đọc tài liệu (2e) dừng ở hybrid dense + FTS hợp nhất RRF | Cùng lý do với embedding local ở mục 4: reranker là model cần GPU, thuộc "tối ưu retrieval quy mô lớn" — PRD 6.2 xếp ngoài phạm vi. Nhánh 2e của MVP chỉ chạy trên `vehicle_documents` của candidate còn sống sau Lớp 1 + nhánh 2c, tập rất nhỏ, nên rerank gần như không thêm giá trị. A4-5 sửa tài liệu cho khớp |
| Ba lớp truy xuất tuần tự (SQL → flags → RAG), RAG bị **cấm** khi feature đã có mã | Gộp còn **hai lớp**: Lớp 1 giữ nguyên; flags + RAG hợp thành Lớp 2 "Need & Feature Retriever" (mục 7.2 schema). Điều kiện đọc tài liệu đặt lại theo "flags có kết luận được hay không" thay vì "feature có mã hay không" | Ba lỗ của thiết kế cũ: (a) xe `UNKNOWN` kẹt vĩnh viễn vì feature có mã nên RAG bị cấm, không có đường nâng lên `YES`; (b) nhu cầu mềm ("hay đi trong phố") không khớp `feature_code` nào nên rơi mất hoàn toàn; (c) đọc tài liệu xong thì vứt, lượt sau đọc lại. Gộp lớp giải quyết cả ba và mở đường cho vòng ghi ngược. Chi tiết mục 7.2 schema |

Bốn nhóm việc **thêm mới** vì bản cũ không có todo nào phụ trách, dù PRD coi là MVP: A3 slot engine, phần synthesis + citation ở A5, A6 guardrail + xử lý ngoài phạm vi, A4 wiring LangGraph thật.

**Bổ sung ở lần cập nhật này** (theo nguyên tắc mở rộng bằng dữ liệu, mục 6.7b), phục vụ hai mục tiêu "giới thiệu theo nhu cầu, không chào hàng" và "sau này thêm feature dễ dàng":

| Task mới | Việc | Vì sao |
|---|---|---|
| A1-4b | Seed `feature_need_tags` + tập `need_tag` đóng | Cho phép Agent chọn feature đáng giới thiệu theo nhu cầu, truy vết được (PRD 5.3). Gắn tag vào `feature_code` nên khối lượng là phép cộng, xe mới thừa hưởng |
| A2-4 | Vocabulary feature build từ DB, không nằm trong prompt | Thêm feature là `INSERT` + restart, không sửa prompt, không regression test cũ |
| A5-7 | Giới thiệu feature theo nhu cầu (mục 7.4 schema) | Quy tắc 6: không có feature đủ điều kiện thì im lặng, không rơi về lời khen chung — đây là ranh giới giữa tư vấn và chào hàng |
| A1-7 | Khớp từ vựng + khớp nhu cầu (nhánh 2a/2b), vector nạp vào RAM lúc khởi động | Không có bước này thì Lớp 2 không khởi động được — "cửa sổ trời" không thành `PANORAMIC_ROOF`, "hay đi trong phố" không thành `URBAN_TRAFFIC`. Đây là việc quan trọng nhất của retriever, không phải diễn giải |

Ba thay đổi **tăng cường** task cũ, không thêm task: A5-6 chuyển sang synthesis bằng placeholder (mục 7.5), làm số bịa không thể xuất hiện thay vì bắt sau khi sinh; A4-1 gộp intent vào cùng lần gọi `extract_slots`, bớt một round trip; A4-2 nhận ngân sách độ trễ dời từ A9-3 lên, cộng short-circuit lượt chỉ hỏi slot. `agent_0001` co lại chỉ còn `CREATE EXTENSION vector` vì `content_tsv` và `feature_need_tags` là của catalog.

## 4. Điều kiện tiên quyết (phải xong trước A1)

Ba việc chặn thi công, làm ở A0. Hai việc đầu **đã xong** (không còn là việc phải làm, giữ lại mục này để executor biết trạng thái xuất phát):

1. ~~**pgvector.**~~ **Đã xong.** `docker-compose.yml` đã đổi sang `pgvector/pgvector:pg16`; `CREATE EXTENSION vector` đã chạy thật trên container `postgres` (qua migration `d4e5f6a7b8c9` và `d0cument0002`).
2. ~~**Dependency embedding.**~~ **Đã xong.** `pgvector` đã có trong `pyproject.toml` (`uv add pgvector`) cho SQLAlchemy type. Không thêm model local ở MVP: dùng embedding qua API provider đã có (`langchain-openai`) sau một port `EmbeddingPort`. Model local là bài toán tối ưu chi phí, thuộc PRD 6.2 — vẫn chưa làm, đúng kế hoạch.
3. ~~**Alembic agent — còn phải làm.**~~ **Đã xong.** `alembic-agent.ini` + `migrations/agents/` (6 revision, `agent_0001`…`agent_0006`) đã viết và **đã chạy thật** lên Postgres — xác nhận `agent_alembic_version = agent_0006` trên DB `p150_auth`. `version_table = agent_alembic_version`, cùng DB URL với auth/document/product (một database vật lý `p150_auth`, bốn version table độc lập). Thứ tự upgrade đã áp đúng: auth → document → product → agent. Chi tiết per-task ở `docs/agent-schema-build-plan.md` (trạng thái: hoàn thành). Lưu ý: đây chỉ là **schema** (15 bảng + view) — phần logic domain/services/graph/adapters/api của agent (mục 6.0) vẫn là việc A0–A9 chưa làm.

## 5. Migration

DDL đầy đủ cho từng bảng ở `docs/agent-schema.md` — mục này chỉ liệt kê migration nào tạo bảng nào.

Sáu revision, chain tuyến tính. Trước đây là bốn, nhưng gộp HITL và lái thử/thông báo vào chung `agent_0004` làm A8-1 phải sửa migration mà A7-1 đã tạo và commit trước đó — vi phạm chính nguyên tắc "mỗi migration ship kèm commit dùng nó, không ai sửa migration người khác đã commit" ở mục 7. Tách `agent_0004`/`agent_0005`, cộng thêm `agent_0006` cho view `funnel_metrics` (A9-1) vì tạo view cũng là DDL, không nên lẫn vào code Python không qua Alembic:

| Revision | Nội dung | Bảng |
|---|---|---|
| `agent_0001` | Chỉ `CREATE EXTENSION vector` | không đụng bảng nào của catalog |
| `agent_0002` | Hội thoại và hồ sơ nhu cầu | `conversation_sessions`, `conversation_slots`, `pending_feature_mentions`, `customer_profiles`, `out_of_scope_log` |
| `agent_0003` | Lượt chạy, snapshot bằng chứng, chấm điểm, TCO | `agent_runs`, `run_snapshots`, `run_candidates`, `run_evidence`, `scoring_result`, `tco_estimates` |
| `agent_0004` | HITL (A7) | `review_queue` |
| `agent_0005` | Lái thử, thông báo nội bộ (A8) | `test_drive_bookings`, `internal_notices`, `notice_reads` |
| `agent_0006` | Dashboard phễu (A9) | `VIEW funnel_metrics` |

**Đã thi công thật, không còn là kế hoạch:** `vehicles`, `cars`, `motorbikes`, `vehicle_prices`, `feature_definitions`, `vehicle_feature_flags`, `feature_need_tags`, `promotions`, `battery_policies`, `tco_assumptions` (11 bảng) thuộc module **`products`** — `src/products/{domain,application,infrastructure,presentation}`, migration `d4e5f6a7b8c9`, version table `alembic_version_products`, đã `upgrade head` trên Postgres thật. Riêng `vehicle_documents` thuộc module **`document`** — `src/document/{domain,infrastructure}`, migration `d0cument0002`, version table `document_alembic_version`, cũng đã chạy. Cả hai dùng chung database vật lý với `agent` (mục §5.2 `docs/vehicle-catalog-schema.md` giải thích vì sao tách bảng theo module dù chung DB). Module `agent` chỉ **đọc** hai module này qua repository, không tạo lại, không migrate — không còn tình huống "chưa có migration khi tới A1" như bản kế hoạch cũ giả định.

**Schema của chính module `agent` cũng đã thi công thật:** 15 bảng (`conversation_sessions`…`notice_reads`) + view `funnel_metrics` trong `src/agents/models.py` (`AgentBase`), 6 migration `agent_0001`…`agent_0006` đã `upgrade head` trên Postgres thật, version table `agent_alembic_version`. Chi tiết ở `docs/agent-schema-build-plan.md`. Đây **chỉ là schema** — domain/services/graph/adapters/api (mục 6.0) chưa có, vẫn là việc A0 trở đi.

Ánh xạ tên PRD sang tên thi công: `vehicle_specs_oto` → `cars`, `vehicle_specs_xe_may_dien` → `motorbikes`, `vehicle_feature_docs` → `vehicle_documents`.

`vehicle_documents` đã được đặc tả đầy đủ ở mục 4.10 `docs/vehicle-catalog-schema.md`, gồm cả cột `content_tsv` (generated), GIN index phục vụ nhánh full-text của hybrid search ở nhánh 2e (Lớp 2), và `source_document_id`/`source_content_hash`/`source_revision` trỏ ngược về `documents` (file gốc, cùng module `document`). **Cột `content_tsv` thuộc bảng `vehicle_documents`, tức thuộc module `document`, không phải `agent`**: cả vector lẫn full-text đều là cách đọc corpus, nên cột phục vụ chúng thuộc về bảng. `agent_0001` khi được tạo (A1-1) chỉ còn `CREATE EXTENSION vector` — extension đã tồn tại sẵn từ khi `product`/`document` migrate, nên câu lệnh này là no-op an toàn nhờ `CREATE EXTENSION IF NOT EXISTS`.

## 6. Ranh giới kiến trúc

Tên gọi kiến trúc: **modular monolith, module `agents` theo layout graph-centric** (bám scaffold `src/agents/` có sẵn: `graph.py` + `state.py` + `nodes/` + `tools/` ở gốc), **vẫn giữ Clean Architecture bằng luật phụ thuộc một chiều** chứ không bằng số tầng thư mục. Mô hình điều phối là state machine tường minh (state khai báo riêng, node chỉ nối service, graph chỉ lắp thứ tự).

Mạch lạc **không** đến từ việc chôn sâu bốn tầng, mà từ bốn nhóm trách nhiệm tách bạch + luật import một chiều chỉ vào trong (mục 6.5b): **điều phối** (`graph.py`/`state.py`/`routing.py`/`nodes/`) → **nghiệp vụ** (`services/`) → **thuần** (`domain/`, `tools/`) ; **I/O** (`adapters/`, `prompts/`) implement `ports.py`. Mũi tên phụ thuộc luôn chỉ vào trong; có test cưỡng chế biên (A0-3) giữ nó không trôi.

**Theo Kiến trúc B đã duyệt:** layout này là **Kiến trúc B (Agent graph-centric)** trong `docs/backend-module-standard.md` mục 11 — biến thể chính thức bên cạnh Kiến trúc A bốn tầng (auth/document/product). Khác A ở *cách trình bày tầng* (phẳng, graph/state/nodes ở gốc), **không** nới lỏng ràng buộc phụ thuộc nào. Đổi lại được sự trực quan graph-centric và tái dùng đúng scaffold `src/agents/` (số nhiều) đang có. Module dựng **tại chỗ** trong `src/agents/`, thay dần nội dung scaffold ví dụ (không xoá folder).

### 6.0. Cây thư mục đầy đủ

Ô `[Ax-y]` là task sở hữu file đó. File không ghi task nào thuộc khung A0-3.

```text
src/agents/
├── __init__.py
├── composition.py                composition root: settings → adapters → services → build_graph()
│
│  ── ĐIỀU PHỐI (ở GỐC, tái dùng scaffold). Không SQL, không công thức, không prompt (mục 6.5)
├── graph.py                      [A4-2] build_graph: add_node/add_edge/add_conditional_edges/compile/ainvoke
├── state.py                      AgentState (TypedDict + reducer). CHỈ khai báo
├── routing.py                    [A4-1/3, A6-1] hàm điều kiện rẽ nhánh: thuần, đọc state, trả tên nhánh
├── chain.py                      dựng initial state từ repository, invoke, trả DTO cho api/
├── protocol.py                   kiểu node dùng chung: (AgentState) -> dict
├── nodes/                        12 node MỎNG ≤15 câu, mỗi node gọi ĐÚNG một service
│   ├── __init__.py               AgentNodes: nhận AgentServices qua constructor
│   ├── extract_slots.py          [A2-3]
│   ├── route_intent.py           [A4-1]
│   ├── ask_or_retrieve.py        [A3-2]
│   ├── layer1.py                 [A1-2] ADVISORY: hard filter theo nhu cầu. CATALOG_LOOKUP: resolve theo tên xe [A4-1]
│   ├── relax.py                  [A4-3]
│   ├── narrow.py                 [A4-3]
│   ├── layer2.py                 [A1-3/6/7] Need & Feature Retriever: gọi ĐÚNG một port, 5 nhánh ẩn bên trong
│   ├── score.py                  [A5-3]
│   ├── tco.py                    [A5-5]
│   ├── synthesize.py             [A5-6]
│   ├── guardrail.py              [A6-1]
│   └── enqueue_hitl.py           [A7-1]
│
│  ── HỢP ĐỒNG (public seams, node/service/adapter đều trỏ vào)
├── ports.py                      LLMPort, EmbeddingPort, CatalogReadPort, FeatureRetrievalPort,
│                                 ClockPort, UnitOfWorkPort,
│                                 SessionRepository, RunRepository, ReviewQueueRepository, NoticeRepository
├── contracts.py                  DTO vào/ra + tool schema trích slot (mục 6.7) + FeatureAssertion [A1-3]
├── errors.py                     lỗi application-level
├── models.py                     SQLAlchemy cho 15 bảng agent (AgentBase)
├── settings.py                   prefix AGENT_*
│
├── services/                     ── NGHIỆP VỤ. Biết domain + port; KHÔNG biết LangGraph/SQLAlchemy (mục 6.2)
│   ├── __init__.py
│   ├── registry.py               AgentServices — 12 use case nhóm advisory (mục 6.3)
│   ├── conversation.py           [A2-2] nạp/ghi phiên + slot; nguồn sự thật của state
│   ├── slot_extraction.py        [A2-3] LLM function calling, validate Pydantic
│   ├── slot_planning.py          [A3-2] gọi domain.slot_policy, trả tối đa 1 câu hỏi
│   ├── intent_routing.py         [A4-1] ADVISORY / CATALOG_LOOKUP
│   ├── retrieval.py              [A1-2/3/6/7] điều phối Lớp 1 → Lớp 2, áp pending feature
│   ├── candidate_tuning.py       [A4-3] relax tối đa 2 lần, narrow ngưỡng 1–5
│   ├── snapshotting.py           [A5-2] ghi run_snapshots bất biến
│   ├── recommendation.py         [A5-3/4/7] scoring + so sánh + giới thiệu feature, đọc từ snapshot
│   ├── tco_estimation.py         [A5-5] nạp tco_assumptions, gọi adapter tools.tco
│   ├── synthesis.py              [A5-6] prompt chỉ từ snapshot, mỗi số kèm evidence_id
│   ├── verification.py           [A6-1] guardrail hậu-synthesis, retry tối đa 2 lần
│   ├── scope_classifier.py       [A6-2] gán nhãn, ghi out_of_scope_log, luôn kèm lối thoát
│   └── operations/               ── CHỈ route HTTP gọi, KHÔNG đi qua graph (mục 6.2)
│       ├── __init__.py
│       ├── review.py             [A7-2/3] claim CAS + lease 15 phút, duyệt/sửa/từ chối
│       ├── booking.py            [A8-2] lái thử từ run đã duyệt
│       ├── history.py            [A8-3] lịch sử + phân quyền theo người phụ trách
│       ├── notices.py            [A8-4] thông báo nội bộ, trạng thái đã đọc riêng từng người
│       └── analytics.py          [A9-1] phễu funnel_metrics
│
├── domain/                       ── THUẦN. KHÔNG import FastAPI/SQLAlchemy/LangGraph/LLM SDK
│   ├── __init__.py
│   ├── entities.py               Session, CustomerProfile, AgentRun, Candidate, Evidence
│   ├── values.py                 SlotName, SlotValue, VehicleType, Intent, RunState, ScopeLabel, Money
│   ├── errors.py                 TcoUnavailable, FeatureNotApplicable, MissingRequiredSlot, TerminalReason
│   ├── slot_tree.py              [A3-1] cây phân nhánh CAR / ELECTRIC_MOTORBIKE
│   ├── slot_policy.py            [A3-2] next_question, bộ slot bắt buộc
│   ├── slot_mapping.py           [A3-3] slot → cột schema; preference vs hard filter
│   ├── need_tags.py              [A1-4b] tập need_tag ĐÓNG + mô tả tiếng Việt để khớp ngữ nghĩa
│   ├── scoring.py               [A5-3] xếp hạng, tối đa 3 mẫu, ≥2 lý do/mẫu
│   ├── comparison.py            [A5-4] bảng so sánh, chặn so chéo loại xe
│   ├── guardrail.py             [A6-1] trích số trong câu trả lời, đối chiếu snapshot
│   └── scope.py                 [A6-2] IN_SCOPE / MISSING_DATA / OUT_OF_SCOPE
│
├── tools/                        ── STRUCTURED TOOL tính toán deterministic (tái dùng scaffold tools/)
│   ├── __init__.py
│   └── tco.py                    [A5-5] adapter vinfast_tco_v1 gọi calculator Products, test golden vector
│
├── adapters/                     ── IMPLEMENT port. Nơi DUY NHẤT biết SQLAlchemy/LLM SDK
│   ├── __init__.py
│   ├── repositories.py           implement repository port; KHÔNG tự mở session (mục 6.4)
│   ├── unit_of_work.py           [A0-5] implement UnitOfWorkPort
│   ├── catalog_read.py           [A1-2/5] Lớp 1 SQL builder, differentiator query
│   ├── feature_retrieval.py      [A1-3/6/7] implement FeatureRetrievalPort — 5 nhánh của Lớp 2:
│   │                             2a/2b khớp vector in-memory, 2c/2d SQL flags + need tags,
│   │                             2e hybrid dense + FTS hợp nhất RRF k=60 + ghi ngược PENDING
│   ├── llm.py                    implement LLMPort
│   ├── embedding.py              implement EmbeddingPort qua langchain-openai (không model local)
│   ├── clock.py                  implement ClockPort
│   └── migrations_check.py       kiểm tra migration lúc startup
│
├── prompts/                      ── câu chữ gửi LLM. Hình dạng slot ở contracts.py
│   ├── __init__.py
│   ├── slot_extraction_prompts.py    [A2-3]
│   ├── intent_prompts.py             [A4-1]
│   ├── synthesis_prompts.py          [A5-6]
│   └── scope_prompts.py              [A6-2]
│
└── api/                          ── HTTP boundary
    ├── __init__.py
    ├── routes.py                 [A4-4] endpoint hội thoại, thay /chat cũ
    ├── review_routes.py          [A7-3]
    ├── booking_routes.py         [A8-2]
    ├── history_routes.py         [A8-3]
    ├── notice_routes.py          [A8-4]
    ├── analytics_routes.py       [A9-1]
    ├── schemas.py
    └── dependencies.py
```

Ba file scaffold ví dụ bị thay khi module thật đáp xuống: `graph.py` (2 node ví dụ → build_graph thật, A4-2), `state.py` (4 field demo → AgentState thật, A0-3), `nodes/example_node.py` + `tools/example_tool.py` (xoá, A0-3/A4-4). `__init__.py` giữ.

Ngoài `src/agents/`:

```text
docker-compose.yml                   [A0-1] pgvector/pgvector:pg16
pyproject.toml                       [A0-1] thêm pgvector; KHÔNG thêm torch/FlagEmbedding
alembic-agent.ini                    [A0-2]
migrations/agents/
├── env.py                           [A0-2] version_table = agent_alembic_version, import AgentBase từ src.agents.models
├── script.py.mako
└── versions/
    ├── agent_0001_vector_extension.py       [A1-1] ✅ chỉ CREATE EXTENSION vector; content_tsv/GIN/feature_need_tags thuộc catalog
    ├── agent_0002_conversation_schema.py    [A2-1] ✅ 5 bảng
    ├── agent_0003_run_schema.py             [A5-1] ✅ 6 bảng
    ├── agent_0004_review_queue.py           [A7-1] ✅ review_queue
    ├── agent_0005_booking_notice.py         [A8-1] ✅ test_drive_bookings, internal_notices, notice_reads
    └── agent_0006_funnel_metrics.py         [A9-1] ✅ VIEW funnel_metrics

src/api/router.py                    [A4-4] include agents router, bỏ legacy /chat
src/agents/nodes/example_node.py     [A0-3/A4-4] XOÁ — node ví dụ scaffold
src/agents/tools/example_tool.py     [A0-3/A4-4] XOÁ — tool ví dụ scaffold
ARCHITECTURE.md                      [A4-5] bỏ ReAct, bỏ rerank, vẽ lại sơ đồ theo A4-2
docs/architecture_diagram.md         [A4-5] cùng nội dung trên

tests/agents/
├── __init__.py
├── conftest.py
├── unit/
│   ├── domain/                      slot_tree, slot_policy, slot_mapping, scoring,
│   │                                comparison, guardrail, scope
│   ├── tools/                       tco golden vector — không DB, không LLM
│   └── services/                    advisory + operations/, dùng fake adapter — không DB, không LLM
└── integration/
    ├── conftest.py
    ├── test_api_registration.py     chuẩn module mục 6
    ├── test_http.py
    ├── test_lifespan.py
    ├── test_migrations.py           upgrade head → downgrade base sạch
    ├── test_repositories.py
    ├── test_unit_of_work.py         [A0-5] rollback, commit, không repository nào tự begin()
    ├── test_layer_boundary.py       [A0-3] domain không import framework
    ├── test_graph_boundary.py       [A0-3] nodes/ không import sqlalchemy/adapters/domain;
    │                                node ≤ 15 câu lệnh; AgentServices chỉ có advisory
    ├── test_retrieval_layers.py     [A1] Lớp 1 + 5 nhánh Lớp 2; spy assert 2e không bị gọi oan;
    │                                DOCUMENT không bao giờ phát NO từ im lặng; DOCUMENT không đổi
    │                                thứ hạng; ≤ 1 vector search mỗi lượt; ghi ngược đúng PENDING
    ├── test_graph_flow.py           [A4-2] thứ tự node cho cả hai nhánh intent
    └── test_e2e_frozen.py           [A9-2] CAR + ELECTRIC_MOTORBIKE, seed cố định

tests/api/test_legacy_contracts.py   [A0-4] đóng băng /chat cũ; A4-4 chuyển sang endpoint mới
data/seeds/feature_definitions.py    [A1-4] 7 feature ô tô + 5 feature xe máy điện
eval/datasets/kpi_questions.yaml     [A9-3] ≥50 câu hỏi
eval/results/                        [A9-3] baseline KPI-1/2/4 + báo cáo p95 ≤ 6s
```

Công thức TCO (`tools/tco.py`) và bảng quyết định slot (`domain/`) test được mà không cần DB và không cần LLM. Đây là điều kiện để A3 và A5 nghiệm thu bằng unit test thuần.

### 6.1. `domain/` và `services/` là một khối, không chia theo service

`domain/` của agent là **một** mô hình nghiệp vụ dùng chung: `scoring` cần `SlotName`/`VehicleType`, `tools.tco` cần `Money`/`VehicleType`, `guardrail` cần `Evidence` do `snapshotting` sinh ra. Không tách `domain/`, `services/` hay `adapters/` riêng cho từng chủ đề (kiểu `retrieval/{domain,service,adapter}`): làm vậy buộc phải nhân bản value object hoặc dựng thêm một `shared/domain/`, tức quay về đúng cấu trúc này nhưng thêm một lớp thư mục rỗng. Clean architecture định nghĩa tầng theo **chiều phụ thuộc**, không theo chủ đề; lặp bốn tầng cho mỗi service không tăng thêm tính chất đó. Đây là lý do layout giữ `domain/`/`services/`/`adapters/` mỗi cái **một** thư mục, không lồng theo feature.

### 6.2. `services/` chia hai nhóm theo luồng nghiệp vụ

Ranh giới có nghĩa thật, không phải chia cho gọn mắt:

| Nhóm | Nội dung | Ai gọi |
|---|---|---|
| `services/` (nhóm advisory) | conversation, slot_extraction, slot_planning, intent_routing, retrieval, candidate_tuning, snapshotting, recommendation, tco_estimation, synthesis, verification, scope_classifier | **chỉ** node trong graph |
| `services/operations/` | review, booking, history, notices, analytics | **chỉ** route HTTP, không đi qua graph |

`ports.py`, `contracts.py`, `errors.py` nằm ở **gốc** `src/agents/` vì cả node, service lẫn adapter đều trỏ vào. `AgentServices` ở `services/registry.py`.

### 6.3. `AgentServices` chỉ chứa nhóm advisory

`services/registry.py` khai báo `AgentServices` (frozen dataclass) — tập use case mà node được phép gọi, và **chỉ gồm 12 use case nhóm advisory**. Năm use case nhóm operations không bao giờ vào graph. `composition.py` là nơi duy nhất dựng `AgentServices`; nhờ vậy test graph chỉ cần một `AgentServices` toàn fake, không DB, không LLM.

### 6.4. Transaction boundary

Repository **không** tự mở session như quy ước hiện tại của `src/document/composition.py`. Agent cần `UnitOfWorkPort` ở `ports.py` + adapter `adapters/unit_of_work.py`, use case (`services/`) là nơi mở/đóng transaction (đúng tinh thần `docs/backend-module-standard.md` mục 5). Lý do bắt buộc: A7-2 claim bằng compare-and-set cần đọc-ghi trong một transaction; A8-2 đòi booking và xác nhận in-app ghi **cùng transaction** — đây là điều kiện thay thế cho cơ chế outbox đã cắt ở mục 3.

Quy tắc kèm theo: **một lượt hội thoại KHÔNG phải một transaction.** Node gọi LLM mất vài giây; giữ transaction mở suốt lượt sẽ treo connection pool và không đạt 50 phiên đồng thời (A9-3). Transaction bọc từng bước ghi, không bọc cả lượt.

### 6.5. Điều phối ở gốc — chỉ nối, không nghiệp vụ

```text
src/agents/
  state.py       # AgentState (TypedDict + reducer). CHỈ khai báo, không logic
  graph.py       # build_graph: add_node / add_edge / add_conditional_edges / compile / ainvoke
  routing.py     # hàm điều kiện rẽ nhánh: thuần, đọc state, trả tên nhánh
  chain.py       # dựng initial state từ repository, invoke, trả DTO cho api/
  protocol.py    # kiểu node dùng chung
  nodes/         # 12 node, mỗi node một file, mỗi node gọi ĐÚNG một service
```

Ràng buộc bắt buộc, có test cưỡng chế ở A0-3:

- `nodes/` không import `sqlalchemy`, không import `..adapters`, không import `..domain`. Node chỉ đọc state và gọi `AgentServices`.
- Thân mỗi node tối đa 15 câu lệnh. Dài hơn nghĩa là nghiệp vụ đang rơi vào graph, phải đẩy về `services/` hoặc `domain/`.
- `AgentState` chỉ đựng domain value và DTO. Tuyệt đối không đựng object SQLAlchemy hay session DB.
- Ba nhánh điều kiện (A4-1 intent, A4-3 relax/narrow, A6-1 guardrail) là hàm thuần ở `routing.py`, test được không cần compile graph.

### 6.5b. Luật phụ thuộc — cái tạo "mạch lạc"

Vì layout phẳng (không lồng bốn tầng), tính mạch lạc do **luật import một chiều** giữ, cưỡng chế bằng test A0-3:

| Thư mục | ĐƯỢC gọi | CẤM import |
|---|---|---|
| `nodes/`, `graph.py`, `routing.py`, `chain.py` | `services/` (qua `AgentServices`), đọc/ghi `state` | `sqlalchemy`, `adapters/`, `domain/` |
| `services/` (gồm `operations/`) | `domain/`, `tools/`, `ports.py`, `contracts.py` | `langgraph`, `adapters/` cụ thể, `nodes/` |
| `domain/`, `tools/` | thuần Python + `domain/values` | `langgraph`, `sqlalchemy`, `fastapi`, LLM SDK |
| `adapters/` | implement `ports.py`, biết `sqlalchemy`/LLM SDK | `nodes/`, `services/` |
| `api/` | `services/operations/` | đi qua graph cho operations |

Mũi tên phụ thuộc luôn chỉ vào trong (`nodes → services → domain`; `adapters → ports`). Đây là Clean Architecture trình bày phẳng: tầng vẫn tách theo chiều phụ thuộc, chỉ không lồng thư mục sâu.

### 6.6. Xử lý lỗi: `terminal_reason` là enum, chặn tại một chỗ

Khác `RAG-graph` (mỗi node `try/except` rồi nuốt lỗi vào `state["error"]`, node sau tự kiểm tra và bỏ qua): agent dùng `terminal_reason` là **enum của domain**, và `graph.py` rẽ thẳng về `END` khi nó khác rỗng. Lý do: A6-1 đòi LLM sai 3 lần → run `FAILED` và **không nội dung nào rời hệ thống**; nếu lỗi chỉ là chuỗi trong state thì `enqueue_hitl` vẫn chạy và vẫn đẩy được bản nháp lỗi vào hàng đợi. Việc chặn nằm ở một chỗ trong graph, không rải ra 12 node — không node nào có thể quên kiểm tra.

### 6.7. Tool schema tách khỏi prompt

`prompts/` giữ câu chữ (chi tiết của LLM cụ thể). Hình dạng slot mà A2-3 trích xuất bằng function calling là **hợp đồng dữ liệu**, nằm ở `contracts.py` (gốc `src/agents/`): đổi nhà cung cấp LLM thì prompt viết lại, tập slot cần trích xuất không đổi.

### 6.7b. Mở rộng bằng dữ liệu, không bằng code — bốn registry

Nguyên tắc bao trùm để "sau này thêm feature dễ dàng": **mỗi chiều mở rộng phải là một dòng dữ liệu, không phải một nhánh code, một dòng prompt, hay một migration.** Đặt ra vì đây là câu hỏi trực tiếp cần trả lời cho vòng đời sau MVP, và vì hệ thống hiện đã đúng nguyên tắc ở hai chỗ và có nguy cơ vi phạm ở hai chỗ.

Bốn registry, mỗi cái mở ra một chiều:

| Registry | Mở ra điều gì | Thêm một mục tốn gì |
|---|---|---|
| `feature_definitions` × `vehicle_feature_flags` | xe **có gì** | 1 dòng definition + N flag |
| `filter_behavior` trên definition | feature đó **lọc hay chỉ cộng điểm** | đã là cột, không tốn gì |
| `feature_need_tags` (mục 4.12 schema) | nhu cầu đã xác nhận **nghĩa là feature nào** | 1–3 dòng |
| allowlist `fact_code` (mục 7.5 schema) | con số nào **được phép render ra câu** | 1 dòng dict trong code |

Hai dòng đầu đã đúng: thêm feature là `INSERT`, không bao giờ `ALTER TABLE cars/motorbikes`. Hai dòng dưới là hai registry mới bổ sung vào schema lần này (mục 4.12 và 7.5), mỗi cái là bảng/dict 2–3 cột, không phải hệ thống.

**Hai chỗ có nguy cơ vi phạm, phải chặn bằng test:**

1. **Vocabulary feature không được nằm trong prompt.** Nếu `extract_slots` (A2-3) liệt kê cứng 12 `feature_code` trong function-calling schema để nhận ra khách đang nói feature nào, thì "thêm feature dễ dàng" là sai: thêm `HEAT_PUMP` sẽ phải sửa prompt và chạy lại toàn bộ test slot, có nguy cơ regression ở feature cũ vì đổi prompt là đổi hành vi cả hàm. Enum feature trong tool schema **phải build tại runtime** từ `SELECT feature_code, name FROM feature_definitions WHERE status='ACTIVE' AND vehicle_type=:type`. Sau đó thêm feature là `INSERT` rồi restart, prompt không ai chạm. Task A2-4 kiểm điều này.

2. **Con số không được lấy bằng tên cột viết cứng trong code synthesis.** Nếu A5-6 tự đọc `cars.range_km` bằng tên cột hardcode thì thêm một con số mới để nói cũng là sửa code. Cho đi qua allowlist mục 7.5 thì thêm số mới là 1 dòng.

Phép thử để kiểm bất kỳ thay đổi nào về sau: *sáu tháng nữa VinFast ra bơm nhiệt, muốn Agent lọc theo nó, giới thiệu nó cho khách miền Bắc, và nói được số liệu tiết kiệm điện — phải sửa bao nhiêu chỗ?* Với thiết kế này: 1 dòng `feature_definitions`, N flag, 1 dòng `feature_need_tags` (`COLD_CLIMATE`), 1 dòng allowlist. **Bốn `INSERT`, không migration, không sửa code, không sửa prompt, không chạy lại test cũ.**

### 6.8. Phân loại hệ thống: Agentic RAG, KHÔNG phải GraphRAG

Cách gọi chuẩn để dùng trong mọi tài liệu và báo cáo: **Agentic RAG dạng orchestrated workflow, có human-in-the-loop và multi-source retrieval.** Diễn giải một câu: *hệ tư vấn hội thoại đa nguồn, điều phối bằng state machine, LLM bị giới hạn ở vai hiểu ngôn ngữ và diễn đạt.*

#### Không phải GraphRAG

GraphRAG (nghĩa gốc) là RAG **trên một knowledge graph**: trích xuất entity + quan hệ từ tài liệu, dựng đồ thị, phát hiện community, tóm tắt theo cụm, truy vấn bằng traversal. Plan này **không có bước nào như vậy** — không bảng entity, không bảng relation, không traversal. Nhánh 2e của Lớp 2 (A1-6) là hybrid dense + FTS trên `vehicle_documents` hợp nhất bằng RRF, tức vector RAG cổ điển.

Chữ "graph" trong dự án là **LangGraph** — đồ thị của các **bước xử lý** (state machine), không phải đồ thị của **tri thức**. Đây là chỗ nhầm phổ biến vì trùng chữ; repo tham chiếu `RAG-graph` cũng vậy: `src/core/graphflow/graph.py` chỉ là `StateGraph` của LangGraph, không liên quan GraphRAG.

#### Vì sao là Agentic RAG

Năm dấu hiệu, mỗi dấu hiệu neo vào một task có mục nghiệm thu:

| Dấu hiệu | Task | RAG thuần thì sao |
|---|---|---|
| Truy xuất nhiều bước, **có điều kiện** — Lớp 1 SQL rồi Lớp 2 chọn nguồn rẻ trước, nhánh đắt chỉ nổ khi nguồn rẻ không trả lời được | A1-6: flags kết luận được (`YES`/`NO` đã duyệt) thì nhánh 2e **không** được gọi | Một câu hỏi = một lần truy xuất, hết |
| **Tự sửa hướng đi** theo kết quả trung gian | A4-3: 0 kết quả → nới ngân sách tối đa 2 lần; quá nhiều → hỏi thêm 1 slot lọc mạnh nhất | Pipeline một chiều, không vòng lặp |
| **Chủ động hỏi lại** trước khi trả lời | A3-2: thiếu slot bắt buộc → use case từ chối đề xuất | Không bao giờ hỏi lại người dùng |
| **Structured tool** cho phần tính toán | A5-5: `vinfast_tco_v1`, `Decimal`, golden vector khớp tới đồng | LLM tự tính trong văn bản |
| **Vòng tự kiểm** sau khi sinh | A6-1: đối chiếu mọi số với snapshot, sai → retry tối đa 2 lần → `FAILED` | Sinh xong là trả |

#### Nhưng KHÔNG phải agent tự trị — đây là lựa chọn cố ý

| Agentic RAG kiểu ReAct | Plan này |
|---|---|
| LLM tự chọn tool, tự quyết gọi bao nhiêu lần | Thứ tự node cố định ở `graph.py`; A4-2 có test kiểm đúng thứ tự |
| LLM tự quyết hỏi gì tiếp | Cây slot tường minh ở `domain/slot_tree.py`; A3-1: "**không** để LLM quyết định hỏi gì tiếp" |
| LLM sinh truy vấn (text-to-SQL) | A1-2: "query builder dựng sẵn trong code, LLM không viết SQL" |
| LLM tổng hợp tự do từ context | A5-6: LLM **chỉ diễn đạt**; mọi số từ `run_snapshots`, kèm `evidence_id` |

Vai của LLM bó lại còn ba việc: **hiểu ý khách** (trích slot A2-3), **phân loại** (intent A4-1, in/out of scope A6-2), **diễn đạt** (A5-6). Mọi quyết định nghiệp vụ nằm ở code.

Lý do bó chặt: PRD đòi truy vết được từng con số (tiêu chí hoàn thành 2) và đòi tư vấn viên duyệt trước khi gửi khách (tiêu chí 3). Agent tự trị không đảm bảo được hai điều đó — nó chọn đường đi khác nhau giữa các lần chạy, nên không có cách nghiệm thu ổn định và không tái lập được E2E đóng băng ở A9-2.

### 6.9. Một quyết định còn treo

Chưa chốt, không chặn A0 vì có khuyến nghị rõ và không cần dựng hạ tầng trước để quyết:

1. **Checkpointer LangGraph.** Đề xuất: **không bật ở MVP**; `conversation_sessions` + `conversation_slots` là nguồn sự thật duy nhất, `chain.py` nạp state từ repository mỗi lượt và ghi lại cuối lượt. Lý do: HITL (A7) và view `funnel_metrics` (A9-1) cần query được state đã chuẩn hoá; một blob checkpoint không đáp ứng. Bật cả hai thì phiên có hai nguồn sự thật và sẽ lệch.

**Đã chốt và đã thi công thật (không còn treo):**

- **Module `products` (catalog) + phần `vehicle_documents` của module `document` đã dựng xong, không phải việc A1 còn phải quyết.** `src/products/{domain,application,infrastructure,presentation}` chứa 11 bảng, migration `d4e5f6a7b8c9` đã chạy `upgrade head` trên Postgres thật (`pgvector/pgvector:pg16`, database `p150_auth`, version table `alembic_version_products`). `vehicle_documents` (bảng thứ 12 về mặt khái niệm, gồm cả `content_tsv`, `source_document_id`, allowlist `fact_code`) thuộc `src/document/{domain,infrastructure}`, migration `d0cument0002` đã chạy trên cùng database, version table `document_alembic_version`. Audit ID (`created_by`/`updated_by`/`approved_by`) đã đúng `VARCHAR(64)` khớp `auth_users.id`, không phải `UUID`. A1 (Hai lớp truy xuất) **đọc thẳng** hai module này qua repository, không tạo lại, không migrate — như mục 5 đã quy định. A0-1 (`pgvector/pgvector:pg16`, `CREATE EXTENSION vector`) cũng đã áp thật lên container `postgres`.
- `content_tsv` và `feature_need_tags` thuộc `product`, không phải `agent` — xem mục 5 và mục 4.10/4.12 `docs/vehicle-catalog-schema.md`. `agent_0001` (khi module `agent` được dựng) chỉ còn `CREATE EXTENSION vector` (đã tồn tại sẵn nên sẽ là no-op qua `CREATE EXTENSION IF NOT EXISTS`).

**Còn thiếu để A0 thật sự bắt đầu được:** module `src/agents/` hiện chỉ là scaffold ví dụ (graph 2 node demo, state 4 field, tool ví dụ); phần thật theo layout graph-centric mục 6.0 (`services/`, `domain/`, `adapters/`, `ports.py`, `contracts.py`, `models.py`, graph/state/nodes thật) và `migrations/agents/` (`alembic-agent.ini`, `env.py`, `agent_alembic_version`) chưa tồn tại — đây mới là phần việc của A0-2/A0-3, không phải A0-1 (đã xong) hay quyết định module catalog (đã xong).

### 6.10. Intent per-turn và chuyển nhánh giữa hội thoại

`route_intent` (A4-1) **chạy lại mỗi lượt**. Mỗi tin nhắn khách gửi = một lần `chain.py` nạp state từ repository → invoke graph → ghi lại (mục 6.9). Graph luôn bắt đầu `extract_slots → route_intent`, nên intent được phân loại lại từ đầu mỗi lượt, **không khoá** theo lượt trước và **không tốn thêm lần gọi LLM** — `route_intent` chỉ đọc field đã có trong output của `extract_slots`.

**Slot bền qua các lượt.** Việc khách chen ngang một câu `CATALOG_LOOKUP` giữa lúc đang thu thập slot **không** làm mất slot đã có: `conversation_slots` là nguồn sự thật (A2-2), persist trong DB. Lượt sau quay lại `ADVISORY`, `next_question` (A3-2) tính từ slot còn trong DB nên hỏi tiếp đúng chỗ đang dở, không hỏi lại từ đầu.

Hai quyết định thiết kế đã chốt cho tình huống chuyển nhánh giữa hội thoại:

1. **Intent là tập hợp, không phải một nhãn duy nhất.** Câu "lai" — khách vừa nêu nhu cầu vừa hỏi đích danh xe trong cùng một câu ("em cần xe 7 chỗ, mà VF 9 giá bao nhiêu?") — phải được phục vụ cả hai vế trong cùng lượt. `extract_slots` trả một **danh sách intent** (`intents: list[Intent]`, có thể chứa cả `ADVISORY` lẫn `CATALOG_LOOKUP`), không còn một field vô hướng. `route_intent` đọc danh sách này; graph chạy nhánh `CATALOG_LOOKUP` (resolve tên xe → trả giá/spec) **và** nhánh `ADVISORY` (ghi slot mới + tính câu hỏi slot còn thiếu) trong cùng lượt. Slot mới nêu ở câu lai vẫn được ghi vào `conversation_slots` dù lượt đó có trả lookup.

2. **Trả lookup xong thì nhắc lại một câu hỏi slot** — chỉ khi đang giữa flow advisory dở (còn slot bắt buộc thiếu). Sau khi trả nội dung lookup, nếu `next_question` khác `None`, câu trả lời đính kèm đúng **một** câu hỏi slot để kéo khách về flow tư vấn (không nhiều hơn một, đúng ràng buộc A3-2). Nếu không còn slot bắt buộc thiếu, hoặc lượt đó là `CATALOG_LOOKUP` thuần (chưa từng vào flow advisory), thì không nhắc.

Ràng buộc kèm theo: câu lai chạy hai nhánh nhưng **vẫn tối đa một lần gọi LLM để hiểu ý** (`extract_slots` gộp cả slot lẫn intent list) — ngân sách độ trễ ở A4-2 không đổi. Nhánh `CATALOG_LOOKUP` của câu lai vẫn phải qua HITL nếu có sinh số liệu (giá/spec), đúng ranh giới A7.

### 6.11. Giọng và độ tự nhiên — nội dung từ DB, cách nói từ LLM

Lo ngại "dự án chủ yếu query DB nên câu trả lời bị thô" xuất phát từ việc gộp hai thứ vốn tách bạch: **query DB quyết định NỘI DUNG** (con số, sự thật), **LLM + prompt quyết định CÁCH DIỄN ĐẠT** (giọng, mạch câu). Structured data **không** làm câu thô — thô đến từ prompt/persona kém. Ở `synthesize` (A5-6), LLM viết **cả câu văn tự nhiên**, chỉ *vị trí con số* là placeholder rồi code điền; câu vẫn mượt, khác agent bịa số ở chỗ mỗi số là bất biến và truy vết được. Ba điểm phải giữ để không rơi vào giọng robot:

1. **Synthesis phải có persona (A5-6).** `prompts/synthesis_prompts.py` khai báo giọng tư vấn viên thân thiện, xưng hô nhất quán, diễn đạt **lý do đề xuất** (A5-3, vốn là structured trỏ về slot) thành lời — **không** in thẳng tên cột/toán tử ("phù hợp vì `seat_count >= 7`"). Persona khai báo **một chỗ**; đổi giọng là sửa prompt, không sửa logic.
2. **Câu hỏi slot diễn đạt bằng template tự nhiên (A3-2), KHÔNG thêm lần gọi LLM.** `domain/slot_policy` chỉ quyết định *hỏi slot nào* (giữ A3-1: không để LLM quyết định hỏi gì tiếp); việc *render thành câu* dùng **template tự nhiên có sẵn** ở tầng trình bày (không phải label trần "Nhập ngân sách"). Lý do bắt buộc dùng template thay vì LLM: lượt chỉ hỏi slot bị chốt **≤ 1 lần gọi LLM** ở A4-2 (chỉ `extract_slots`); chèn một lần gọi LLM để diễn đạt câu hỏi sẽ đội thành 2 lần/lượt và phá p95 ≤ 6s. Diễn đạt câu hỏi động bằng LLM (gộp vào cùng lần gọi `extract_slots`, không thêm round trip) để **sau MVP**.
3. **Allowlist placeholder đủ rộng (A5-6/mục 7.5).** Hẹp quá thì LLM không được nhắc đủ số → câu nghèo thông tin (khác thô giọng nhưng cũng làm câu cụt).

Nghiệm thu độ tự nhiên là chỗ khó vì PRD 6.2 loại **LLM-as-Judge tự động**. Thay bằng hai lối khả thi: (a) test assert đầu ra **không** chứa token structured thô (tên cột, toán tử so sánh, mã slot/feature trần); (b) bộ **golden sample review thủ công** đính vào E2E đóng băng A9-2, để mỗi lần đổi prompt có mẫu đối chiếu giọng.

## 7. Quy trình cho mỗi task


Mỗi task trong mục 8 chạy đủ bốn bước, không nhảy bước:

**1. Phân tích.** Đọc phần PRD và phần schema mà task viện dẫn. Đối chiếu với code đang có để biết cái gì tái dùng được, cái gì phải viết mới. Nếu phát hiện đặc tả xung đột với schema hoặc với code hiện tại, dừng và báo trước khi viết code — không tự ý chọn một bên.

**2. Implement.** Chỉ viết phần thuộc task đó. Không tranh việc của task sau. Tôn trọng luật phụ thuộc một chiều ở mục 6.5b.

**3. Test.** Viết test cho đúng các mục nghiệm thu ghi trong task. Chạy `pytest`, `ruff`, `mypy` cho phạm vi đã sửa. Đỏ thì sửa và chạy lại tới khi xanh — không commit khi còn đỏ.

**4. Commit.** Một commit cho một task, trên **nhánh hiện tại**, message một dòng. Migration đi cùng commit dùng nó, không tách rời. Định dạng:

```text
feat(agent): <việc>       # thêm năng lực
test(agent): <việc>        # task chỉ có test
refactor(agent): <việc>    # đổi cấu trúc, không đổi hành vi
chore(agent): <việc>       # hạ tầng, config, dependency
```

Task nào có ô **Chặn** thì phải xong task được nêu ở đó trước.

## 8. Danh sách task

### A0 — Nền móng module

| ID | Task | Nội dung | Nghiệm thu | Chặn |
|---|---|---|---|---|
| A0-1 | Hạ tầng pgvector và dependency | Đổi `docker-compose.yml` sang `pgvector/pgvector:pg16`. Thêm `pgvector` vào `pyproject.toml`. Không thêm model embedding local. | `docker compose up -d postgres` lên được (service tên `postgres` trong `docker-compose.yml`, không phải `db`); `SELECT 1` qua asyncpg chạy; `CREATE EXTENSION vector` thành công | — |
| A0-2 | Alembic cho module agent | `alembic-agent.ini` + `migrations/agents/env.py`, `version_table = agent_alembic_version`, cùng DB URL với auth/document | `upgrade head` trên DB sạch sau auth+document; `downgrade base` sạch, không sót bảng | A0-1 |
| A0-3 | Khung graph-centric | Dựng phần thật trong `src/agents/` theo layout mục 6.0: `domain/`, `services/` (+ `operations/`), `adapters/`, `tools/`, `prompts/`, `api/`, và ở gốc `ports.py`/`contracts.py`/`errors.py`/`state.py`/`graph.py`/`routing.py`/`chain.py`/`protocol.py`/`nodes/`/`composition.py`. Thay `state.py` scaffold (4 field) bằng `AgentState` thật; xoá `nodes/example_node.py`, `tools/example_tool.py`. Khai báo port rỗng `LLMPort`, `EmbeddingPort`, `CatalogReadPort`, `ClockPort`, `UnitOfWorkPort`; khai báo `AgentServices` rỗng ở `services/registry.py` (mục 6.3) | Test import boundary (mục 6.5b): `domain` không import FastAPI / SQLAlchemy / LangGraph / LLM SDK. Test biên `nodes/`: không import `sqlalchemy`, không import `..adapters`, không import `..domain`; thân mỗi node ≤ 15 câu lệnh. Test: `AgentServices` chỉ chứa use case nhóm advisory, `nodes/` không import `services/operations/` | — |
| A0-4 | Đóng băng contract cũ | Ghi test bao quanh `/chat` hiện tại và `src/agents/graph.py` để A4 thay thế an toàn. `AgentState` cũ được đánh dấu là state ví dụ | Test `/chat` cũ xanh; có ghi chú rõ code nào sẽ bị A4 xoá | — |
| A0-5 | Unit of work | Adapter `adapters/unit_of_work.py` implement `UnitOfWorkPort` (mục 6.4). Repository **không** tự mở session; use case (`services/`) mở/đóng transaction. Nối vào `composition.py` | Test: hai lệnh ghi trong một unit of work → lỗi ở lệnh sau rollback cả lệnh trước. Test: commit rồi thì dữ liệu hiện diện ở session khác. Test: không có repository nào của agent tự gọi `session.begin()` | A0-3 |

### A1 — Hai lớp truy xuất

Hai lớp, mỗi lớp trả lời một loại câu hỏi khác nhau. Đặc tả đầy đủ ở mục 7.1/7.2 `docs/vehicle-catalog-schema.md`.

| Lớp | Lọc theo gì | Ví dụ | Nguồn |
|---|---|---|---|
| **1 — SQL hard filter** | Nhu cầu định lượng được: ngân sách, số người, quãng đường, tải trọng | "dưới 700 triệu, 7 chỗ, đi 300km/ngày" | `vehicles` + `cars`/`motorbikes` + `vehicle_prices` |
| **2 — Need & Feature Retriever** | Mọi thứ SQL không làm được: tính năng có tên gọi, nhu cầu mềm, câu diễn giải | "cửa sổ trời", "hay đi trong phố", "bảo hành pin có điều kiện gì" | `feature_definitions` + `vehicle_feature_flags` + `feature_need_tags` + `vehicle_documents` |

`vehicle_type` **không phải** mục đích của Lớp 1 — nó chỉ là điều kiện đầu tiên để biết join `cars` hay `motorbikes`, vì hai loại xe có cột specs khác nhau (`seat_count` chỉ có ở ô tô, `max_load_kg` chỉ có ở xe máy điện). Sau khi chọn đúng bảng, phần việc chính của Lớp 1 là lọc theo slot nhu cầu.

Lớp 2 là **một cửa duy nhất, năm nhánh**, chọn nguồn rẻ trước:

```text
2a  khớp tính năng   câu khách -> feature_code        [A1-7]  mọi lượt, vector in-memory
2b  khớp nhu cầu     câu khách -> need_tag            [A1-7]  mọi lượt, vector in-memory
2c  tra flags        feature_code -> YES/NO/UNKNOWN   [A1-3]  mọi lượt, SQL
2d  nở nhu cầu       need_tag -> feature_code[] -> 2c [A1-3]  mọi lượt, SQL
2e  đọc tài liệu     hybrid dense + FTS, scoped       [A1-6]  CÓ ĐIỀU KIỆN
```

Nhánh **2e chỉ nổ** khi (a) 2a và 2b đều không khớp mã nào, hoặc (b) 2c trả `UNKNOWN` cho đúng điều kiện khách đang nêu, hoặc (c) khách hỏi câu diễn giải. Flags đã trả `YES`/`NO` **đã duyệt** thì không mở tài liệu — đọc lại điều đã biết chắc là lãng phí và ăn vào ngân sách độ trễ A4-2. Tối đa **một** lần tìm kiếm vector mỗi lượt.

Đầu ra của Lớp 2 là `list[FeatureAssertion]` (mục 7.2 schema). Luật thẩm quyền bắt buộc: `source=DOCUMENT` **không** được loại xe, **không** được đổi thứ hạng, **không** được cấp con số, và chỉ được phát `NO` khi có bằng chứng dương — im lặng luôn là `UNKNOWN`.

> **Lệch PRD phải ký nhận trước khi bắt đầu A1.** PRD 5.2 AC hiện viết nguyên văn *"feature đã có mã thì Lớp 3 không được gọi"*. Điều kiện mới đặt theo "flags có kết luận được hay không" nên nhánh 2e **được** chạy cho feature đã có mã khi flag là `UNKNOWN`. Giữ đúng **ý** của AC (không tìm kiếm ngữ nghĩa vô ích) nhưng phá **chữ**. Không phải quyết định kỹ thuật — cần người sở hữu PRD đồng ý, nếu không A1-6 sẽ nghiệm thu bằng một tiêu chí đã lỗi thời.

| ID | Task | Nội dung | Nghiệm thu | Chặn |
|---|---|---|---|---|
| A1-1 | Migration `agent_0001` | Chỉ `CREATE EXTENSION vector`. Cột `content_tsv` (generated) + GIN index thuộc `vehicle_documents` (module `document`, migration `d0cument0002` đã chạy); bảng `feature_need_tags` thuộc module `products` (migration `d4e5f6a7b8c9` đã chạy). Cả hai đã tồn tại trước khi `agent_0001` chạy — không còn nhánh "tạo tạm rồi chuyển chủ" như bản kế hoạch cũ | `upgrade`/`downgrade` sạch; extension `vector` có mặt (idempotent, đã tồn tại sẵn từ trước); `content_tsv` sinh được và FTS query chạy trên seed khi đọc qua repository của `document` | A0-2 |
| A1-2 | Lớp 1 — SQL hard filter theo nhu cầu | Query builder dựng sẵn trong code, LLM không viết SQL. Lọc theo **slot nhu cầu đã khai thác**: ngân sách (`vehicle_prices.amount_vnd <= :budget_max_vnd`, chỉ `STARTING_PRICE` đang hiệu lực), số người (`cars.seat_count >= :passenger_count`), quãng đường (`cars.range_km` / `motorbikes.range_max_km >= :required_range_km`), tải trọng khi nhánh giao hàng (`motorbikes.max_load_kg`). `vehicles.vehicle_type` chỉ là điều kiện đầu tiên để chọn bảng specs: `CAR` → `cars`, `ELECTRIC_MOTORBIKE` → `motorbikes`. Chỉ xe `status='ACTIVE'`. SQL mẫu ở mục 7.1 schema | Test: ngân sách 700 triệu → xe 800 triệu bị loại. Test: 7 người → xe 5 chỗ bị loại. Test: quãng đường 300km/ngày → xe `range_km` 250 bị loại. Test: `vehicle_type='CAR'` không bao giờ sinh SQL chạm `motorbikes`, và ngược lại. Test: xe `DRAFT`/`ARCHIVED` không vào kết quả. Test: giá hết hiệu lực không được dùng để lọc | A0-3 |
| A1-3 | Lớp 2 nhánh 2c/2d — flags tri-state và nở nhu cầu | **2c:** lọc feature nổi bật đã có mã (ghế chỉnh điện, cửa sổ trời, ADAS, camera 360, pin tháo rời…). Chỉ đọc `vehicle_feature_flags` của candidate từ Lớp 1, chỉ `verification_status='APPROVED'` (mục 4.9 schema). Tôn trọng `filter_behavior`: `REQUIRED` thì lọc, `PREFERENCE` thì cộng điểm, `INFORMATIONAL` chỉ hiển thị. `UNKNOWN` **không** suy thành `NO`; xe `UNKNOWN` giữ lại kèm nhãn cần xác minh và mở đường cho 2e. **2d:** `need_tag` từ slot `habit_need_tags` → join `feature_need_tags` → `feature_code[]` → đi tiếp qua 2c, `relevance` thành trọng số. **Đầu ra đổi:** trả `list[FeatureAssertion]` (`contracts.py`) thay vì danh sách `vehicle_id` — mọi consumer phía sau chỉ biết kiểu này. Xe còn sống sau bước loại là `alive_vehicle_ids`, phạm vi của 2e | Test: yêu cầu "ghế chỉnh điện" → xe `status='NO'` bị loại, xe `YES` giữ lại. Test: feature `PREFERENCE` không loại xe nào, chỉ đổi điểm. Test: xe `UNKNOWN` cho feature bắt buộc vẫn trong kết quả, có cờ cảnh báo (PRD 5.2 AC). Test: seed `status='UNKNOWN', verification_status='APPROVED'` → 2c không trả rỗng. Test: flag `PENDING` bị loại. Test: mọi assertion từ 2c/2d mang `source=FLAG` và `evidence_ref` trỏ đúng `(vehicle_id, feature_code)`. Test: `need_tag` nở ra feature nào thì feature đó phải `ACTIVE` và khớp `vehicle_type` | A1-2 |
| A1-4 | Seed danh mục feature nổi bật | Seed `feature_definitions` cho các feature khách hay hỏi, kèm `category` và `filter_behavior` đúng. Ô tô: `POWER_ADJUST_SEAT` (ghế chỉnh điện), `PANORAMIC_ROOF`, `ADAS_LEVEL_2`, `CAMERA_360`, `HEATED_SEAT`, `WIRELESS_CHARGING`, `AUTO_PARK`. Xe máy điện: `BATTERY_REMOVABLE`, `BATTERY_SWAPPABLE`, `SMART_KEY`, `ANTI_THEFT_ALARM`, `USB_CHARGING_PORT`. Không thêm cột vào `cars`/`motorbikes` — feature mới luôn đi qua bảng này | Test: mọi `feature_code` seed đều `ACTIVE` và có `vehicle_type` khớp loại xe. Test: `filter_behavior` chỉ nhận `REQUIRED`/`PREFERENCE`/`INFORMATIONAL`. Test: gán feature ô tô cho xe máy điện → `FEATURE_NOT_APPLICABLE` | A1-3 |
| A1-4b | Seed `feature_need_tags` và tập `need_tag` đóng | Seed bảng nối `feature_need_tags` (mục 4.12 schema): mỗi `feature_code` của A1-4 gắn 1–3 `need_tag` kèm `relevance`. Tập `need_tag` là **đóng**, khai báo cùng chỗ với ánh xạ slot (mục 7.0/7.4): `LONG_DISTANCE`, `URBAN_TRAFFIC`, `HIGHWAY_SAFETY`, `FAMILY_LARGE`, `NO_HOME_CHARGING`, `DELIVERY_USE`, `LOW_OPERATING_COST`, `TIGHT_BUDGET`. Khoảng 25–30 dòng, nhập một lần, xe mới thừa hưởng qua `feature_code`. **Thêm:** mỗi `need_tag` phải có **mô tả tiếng Việt** khai báo cùng chỗ ở `domain/need_tags.py` — đây là văn bản mà nhánh 2b embed để khớp câu khách ("hay đi trong phố" → `URBAN_TRAFFIC`). Không có mô tả thì 2b không khớp được gì | Test: mọi `need_tag` trong seed thuộc tập đóng; tag ngoài tập bị từ chối. Test: mọi `feature_code` trong `feature_need_tags` tồn tại và `ACTIVE` ở `feature_definitions`. Test: `relevance` nằm trong `(0,1]`. Test: mọi tag trong tập đóng đều có mô tả tiếng Việt không rỗng | A1-4 |
| A1-5 | Differentiator query | Sau Lớp 1, tìm feature có giá trị khác nhau giữa các candidate còn lại. Chỉ nuôi câu hỏi chủ động, **không** dùng để lọc | Test: kết quả differentiator không làm thay đổi tập candidate | A1-4 |
| A1-6 | Lớp 2 nhánh 2e — đọc tài liệu, có điều kiện | Giới hạn trong `vehicle_documents` của `alive_vehicle_ids`, chỉ `status='ACTIVE'` và trong khoảng hiệu lực. Hybrid dense + FTS hợp nhất bằng RRF (k=60). SQL mẫu ở mục 7.2 schema. **Ba điều kiện nổ:** (a) 2a và 2b đều không khớp mã nào; (b) 2c trả `UNKNOWN` cho đúng điều kiện khách đang nêu; (c) khách hỏi câu diễn giải. **Phát `NO` chỉ khi có bằng chứng dương** — chunk khẳng định không có ("không trang bị", "chỉ có ở bản Plus", "tuỳ chọn"), hoặc ô trống/gạch ngang trong bảng trang bị; top-k rỗng luôn là `UNKNOWN`. **Ghi ngược:** kết luận về feature đã có mã được `UPSERT` vào `vehicle_feature_flags` ở `verification_status='PENDING'` kèm `confidence`, có mệnh đề `WHERE` chặn ghi đè dòng đã `APPROVED`/`REJECTED`. Trường hợp im lặng ghi đề xuất `NO` với `confidence` 0.3–0.5, chỉ khi brochure xe đó có mục trang bị rõ ràng | Test: flags kết luận được (`YES`/`NO` đã duyệt) → 2e **không** được gọi (assert trên spy). Test: flag `UNKNOWN` cho điều kiện đang hỏi → 2e **được** gọi (đảo chiều so với AC cũ, xem ghi chú lệch PRD ở đầu gate). Test: 2e không trả `vehicle_id` đã bị loại ở Lớp 1 hoặc 2c. Test: 2e không mở rộng lại candidate set, không đưa về xe vượt ngân sách. Test: top-k rỗng → `UNKNOWN`, **không bao giờ** `NO`. Test: chunk chứa "không trang bị" → `NO(DOCUMENT)`. Test: assertion `DOCUMENT` không làm đổi thứ tự candidate (bật/tắt 2e cho cùng một thứ hạng). Test: ghi ngược tạo đúng dòng `PENDING`, và dòng đó không lọt vào truy vấn tư vấn. Test: dòng đã `APPROVED` không bị ghi đè. Test: tối đa 1 lần vector search mỗi lượt | A1-1, A1-4, A1-7 |
| A1-7 | Nhánh 2a/2b — khớp từ vựng và khớp nhu cầu | Nạp vector vào **bộ nhớ** lúc khởi động: `feature_definitions` (`name` + `description`, lọc `status='ACTIVE'`) cho 2a, và mô tả tiếng Việt của tập `need_tag` đóng (`domain/need_tags.py`) cho 2b. Câu khách → embed một lần → cosine trên cả hai tập → lấy mã vượt ngưỡng. **Không** thêm cột `embedding` vào bảng ở MVP: danh mục cỡ vài chục dòng, embed lúc startup rẻ hơn một migration cộng một pipeline đồng bộ. Cache theo `updated_at`, làm mới khi Admin đổi danh mục. Kết quả 2b ghi vào slot `habit_need_tags` ở `conversation_slots` (mục 7.0 schema), không truyền thẳng xuống scoring — nhờ vậy quy tắc "suy `need_tag` từ slot đã xác nhận" của A5-7 giữ nguyên nghĩa đen | Test: "cửa sổ trời", "kính toàn cảnh", "nóc kính" đều ra `PANORAMIC_ROOF`. Test: "hay đi trong phố" ra `URBAN_TRAFFIC`. Test: thêm một `feature_definitions` mới rồi làm mới cache → khớp được ngay, không sửa file nào. Test: `need_tag` ngoài tập đóng bị từ chối. Test: dưới ngưỡng → không trả mã nào, không đoán bừa. Test: 2a/2b không phát sinh query DB nào mỗi lượt (vector ở RAM; spy trên session). Test: kết quả 2b hiện diện trong `conversation_slots` sau lượt đó | A1-4b, A0-3 |

### A2 — Hội thoại và hồ sơ nhu cầu

| ID | Task | Nội dung | Nghiệm thu | Chặn |
|---|---|---|---|---|
| A2-1 | Migration `agent_0002` | `conversation_sessions`, `conversation_slots` (unique `(session_id, slot_name)`), `pending_feature_mentions`, `customer_profiles`, `out_of_scope_log`. DDL đầy đủ ở `docs/agent-schema.md` §agent_0002 | `upgrade`/`downgrade` sạch; unique constraint chặn hàng trùng slot | A0-2 |
| A2-2 | Repository và use case phiên/slot | Tạo phiên, nạp phiên, đọc/ghi slot. Sửa slot là UPDATE, không append | Test: khách sửa ngân sách ở lượt sau → `conversation_slots` giữ **một** hàng với giá trị mới (PRD 5.1 AC) | A2-1 |
| A2-3 | Trích xuất slot bằng LLM function calling | Một tool schema cho từng loại phương tiện, output validate bằng Pydantic. Chuẩn hoá: map category, làm tròn range, parse ngân sách tiếng Việt ("700 triệu", "1 tỷ 2") | Test: LLM trả slot sai kiểu → reject, không ghi DB, không làm chết lượt. Test: khách nêu feature khi chưa đủ slot bắt buộc → ghi `pending_feature_mentions` | A2-2 |
| A2-4 | Vocabulary feature build từ DB, không nằm trong prompt | Enum `feature_code` trong tool schema của A2-3 **dựng tại runtime** từ `feature_definitions` theo `vehicle_type`, không viết cứng danh sách vào prompt (mục 6.7b). Thêm feature mới là `INSERT` + restart, không sửa prompt, không chạy lại test slot cũ | Test: thêm một `feature_definitions` mới rồi gọi lại builder → enum tool schema chứa `feature_code` mới mà không sửa file prompt nào. Test: prompt/schema không chứa danh sách `feature_code` viết cứng (assert bằng grep trên chuỗi prompt) | A2-3, A1-4 |

### A3 — Slot engine

Gate lõi. Bản plan cũ thiếu hoàn toàn.

| ID | Task | Nội dung | Nghiệm thu | Chặn |
|---|---|---|---|---|
| A3-1 | Cây slot phân nhánh | Bảng tra cứu tường minh ở `domain`, **không** để LLM quyết định hỏi gì tiếp. Slot 1 luôn là **loại phương tiện**. Nhánh `CAR`: số người → quãng đường → sạc tại nhà → ngân sách → mục đích → thói quen/ưu tiên bổ sung. Nhánh `ELECTRIC_MOTORBIKE`: mục đích cụ thể (đi làm/giao hàng/cá nhân) → quãng đường → sạc tại nhà → ngân sách → thói quen/ưu tiên bổ sung; **không** hỏi số người dùng, **không** hỏi lại mục đích. **Slot cuối đổi thành câu mở** — trước đây chỉ nhận tên tính năng ("anh/chị cần tính năng gì?"), nay hỏi cả thói quen ("anh/chị thường dùng xe thế nào, có gì đặc biệt không?"). Câu trả lời đi vào hai slot: tính năng có tên gọi → nhánh 2a; thói quen → nhánh 2b → `habit_need_tags`. Đây là lý do slot cũ để rơi mất nhu cầu mềm | Test: state rỗng → câu hỏi đầu là loại phương tiện, không phải ngân sách (PRD 4.3). Test: nhánh motorbike không bao giờ sinh câu hỏi số người dùng. Test: khách trả lời slot cuối bằng thói quen thuần ("tôi hay đi trong phố") → `habit_need_tags` được ghi, không bị bỏ rơi | A0-3 |
| A3-2 | `next_question` và bộ slot bắt buộc | Trả **tối đa một** câu hỏi; đủ slot bắt buộc thì trả `None`. Bắt buộc: `CAR` = {loại, ngân sách, mục đích, số người}; `ELECTRIC_MOTORBIKE` = {loại, ngân sách, mục đích cụ thể}. `domain/slot_policy` chỉ trả **slot cần hỏi**; câu hỏi được **render từ template tự nhiên** ở tầng trình bày (mục 6.11), không phải label trần, **không thêm lần gọi LLM** | Test: mọi state hợp lệ → trả 0 hoặc 1 câu, không bao giờ nhiều hơn (PRD 5.1 AC). Test: khách nêu loại phương tiện trong câu đầu → **không** hỏi lại. Test: thiếu slot bắt buộc → use case đề xuất từ chối. Test: câu hỏi render ra không phải label/mã slot trần (không chứa tên slot dạng máy); lượt hỏi slot không phát sinh lần gọi LLM nào ngoài `extract_slots` (spy) | A3-1, A2-2 |
| A3-3 | Ánh xạ slot sang cột schema | Theo mục 7.0 `docs/vehicle-catalog-schema.md`. Mục đích sử dụng là **preference khi xếp hạng**, không phải hard filter — trừ nhánh giao hàng của xe máy điện, nơi `max_load_kg` là điều kiện cứng. Thêm dòng `habit_need_tags` → `feature_need_tags` qua nhánh 2d: **chỉ xếp hạng**, không bao giờ hard filter, vì thói quen là suy luận về người dùng chứ không phải thuộc tính của xe | Test: mục đích "gia đình" không loại xe nào khỏi candidate, chỉ đổi điểm. Test: nhánh giao hàng lọc cứng theo `max_load_kg`. Test: `habit_need_tags` không loại xe nào khỏi candidate trong mọi trường hợp | A3-1, A1-2 |

### A4 — Wiring LangGraph

| ID | Task | Nội dung | Nghiệm thu | Chặn |
|---|---|---|---|---|
| A4-1 | Intent Router | Phân loại `ADVISORY` (tư vấn chọn xe) hay `CATALOG_LOOKUP` (tra cứu thuần tuý, khách đã nêu đích danh mẫu xe — "VF 8 giá bao nhiêu", "VF 6 đi được bao xa"). `ADVISORY` chạy Lớp 1→2 như cũ. `CATALOG_LOOKUP` **không** bỏ hẳn structured data — nó thay hard filter (Lớp 1 lọc theo *nhu cầu*) bằng resolve theo *danh tính*: match tên xe khách nêu vào `vehicles` (`brand`/`model_name`/`variant_name`/`slug`), lấy đúng `vehicle_id`, rồi đọc thẳng `cars`/`motorbikes` (specs) và `vehicle_prices` (giá `STARTING_PRICE` đang `ACTIVE`) theo `vehicle_id` đó — không phải chỉ Lớp 2 (feature) + Lớp 3 (RAG) như thiết kế trước. Không khớp được tên xe nào → trả lời không nhận diện được, không đoán. Khớp nhiều hơn một xe (ví dụ chỉ nói "VF" mà không rõ variant) → hỏi lại rõ mẫu. **Tối ưu:** intent nằm trong cùng function-calling schema của `extract_slots` (A2-3) dưới dạng **danh sách** `intents: list[Intent]` (mục 6.10, có thể chứa cả `ADVISORY` lẫn `CATALOG_LOOKUP` cho câu lai), không phải một lần gọi LLM riêng — `route_intent` chỉ đọc field đã có trong state, tiết kiệm một round trip mỗi lượt. Vẫn là node riêng trong graph để giữ thứ tự tường minh (§6.8), chỉ là không tự gọi LLM. Chi tiết per-turn và multi-intent ở mục 6.10 (task A4-6) | Test: `CATALOG_LOOKUP` bỏ qua Lớp 1 (hard filter theo nhu cầu, PRD 5.2) nhưng vẫn đọc được `cars`/`motorbikes`/`vehicle_prices` theo vehicle_id đã resolve — "VF 8 giá bao nhiêu" trả đúng số từ `vehicle_prices`, không phải bịa hay chỉ trả lời bằng RAG. Test: tên xe không khớp record nào → từ chối rõ ràng, không suy đoán. Test: `route_intent` không phát sinh lần gọi LLM nào (spy) | A1-6, A3-2 |
| A4-2 | State machine | `extract_slots` → `route_intent` → `ask_or_retrieve` → `layer1` → (`relax` \| `narrow` \| `layer2`) → `score` → `tco` → `synthesize` → `guardrail` → `enqueue_hitl`. Node `layer3` không còn tồn tại — nhánh đọc tài liệu (2e) nằm **bên trong** `layer2` sau `FeatureRetrievalPort`, nên rẽ nhánh của nó là chi tiết triển khai của adapter, không phải cạnh trong graph. Node `score`/`tco`/`synthesize`/`guardrail` để stub, A5/A6 điền. **Short-circuit lượt chỉ hỏi slot**: khi `ask_or_retrieve` xác định còn slot bắt buộc thiếu (A3-2 trả câu hỏi), graph rẽ thẳng về `END` sau khi phát câu hỏi — **không** chạy `layer1`/`score`/`synthesize`/`guardrail`. Nhánh CAR có 5–6 lượt đầu chỉ hỏi slot, mỗi lượt như vậy chỉ tốn 1 lần gọi LLM (`extract_slots`) thay vì cả chuỗi | Test: đi đúng thứ tự node cho cả hai nhánh intent. Test: lượt còn thiếu slot bắt buộc → spy xác nhận `layer1`/`synthesize`/`guardrail` **không** được gọi. **Ngân sách độ trễ (dời từ A9-3 lên đây)**: test đếm bằng spy số lần gọi LLM mỗi lượt — lượt hỏi slot ≤ 1, lượt đề xuất đầy đủ ≤ 3 (extract + synthesize + tối đa 1 retry ở đường thường), để p95 ≤ 6s (PRD 8.5) là hệ quả có kiểm từ đầu, không đợi tới task cuối | A4-1 |
| A4-3 | Nới lỏng và thu hẹp | Lớp 1 ra 0 kết quả → nới theo thứ tự ưu tiên ngân sách, **tối đa 2 lần**; hết 2 lần vẫn rỗng → thông báo rõ và đề xuất chuyển tư vấn viên. Ngưỡng đi tiếp: 1–5 candidate. Quá nhiều → hỏi **một** slot lọc mạnh nhất lấy từ A1-5 | Test: Lớp 1 rỗng → đúng 2 lần relax, lần 3 không xảy ra (PRD 5.2 AC). Test: 20 kết quả → phát sinh đúng một câu hỏi lọc | A4-2, A1-5 |
| A4-4 | Áp pending feature và thay `/chat` | `pending_feature_mentions` tự áp vào Lớp 2 ngay khi Lớp 1 xong, **không** hỏi lại khách. Endpoint agent thật (`api/routes.py`) thay `/chat` cũ; hoàn tất thay `graph.py`/`state.py` scaffold bằng bản thật và xoá nốt `nodes/example_node.py`, `tools/example_tool.py`. **Nối `AgentComposition` vào `src/main.py`**: thêm `agent = AgentComposition(...)`, `app.state.agent = agent`, gọi `await agent.start()`/`await agent.shutdown()` trong `lifespan`, cùng mẫu với `auth`/`document` đã có (`src/main.py` hiện tại) — thiếu bước này thì endpoint mới không có gì khởi tạo pool/engine khi app start | Test: feature nêu sớm được áp ở Lớp 2 và không sinh câu hỏi lặp (PRD 5.2 AC). Test cũ ở A0-4 được chuyển sang endpoint mới. Test: `TestClient` khởi động app thật (không mock lifespan) → gọi được endpoint agent mới, không lỗi "chưa khởi tạo" | A4-3, A2-3 |
| A4-6 | Multi-intent per-turn và nhắc slot sau lookup | Theo mục 6.10. `extract_slots` trả `intents: list[Intent]` thay vì một field vô hướng; `route_intent` đọc danh sách. Câu lai (vừa nêu nhu cầu vừa hỏi đích danh xe) chạy **cả** nhánh `CATALOG_LOOKUP` (resolve tên xe → giá/spec) lẫn `ADVISORY` (ghi slot mới + tính `next_question`) trong cùng lượt. Sau khi trả nội dung lookup, nếu còn slot bắt buộc thiếu thì đính kèm **đúng một** câu hỏi slot (A3-2). Slot nêu trong câu lai vẫn ghi vào `conversation_slots` dù lượt đó trả lookup | Test: câu lai → có cả kết quả lookup lẫn slot mới được ghi trong cùng lượt (spy DB). Test: `extract_slots` vẫn chỉ một lần gọi LLM cho câu lai (spy). Test: trả lookup giữa flow advisory dở → câu trả lời kèm tối đa 1 câu hỏi slot; `CATALOG_LOOKUP` thuần (chưa vào advisory) → không nhắc. Test: chen ngang lookup không xoá slot đã có; lượt sau `next_question` tiếp đúng chỗ dở. Test: nhánh lookup của câu lai có sinh số liệu vẫn qua HITL (A7) | A4-4 |
| A4-5 | Sửa tài liệu kiến trúc cho khớp agent thật | `ARCHITECTURE.md` và `docs/architecture_diagram.md` đang mô tả graph ví dụ mà A4-4 vừa xoá, mâu thuẫn trực tiếp với plan. Bốn nhóm phải sửa: (a) `ARCHITECTURE.md:79` "Agent Type: ReAct" → Agentic RAG orchestrated, dẫn mục 6.8; (b) `ARCHITECTURE.md:80-81` `AgentState` 4 node "parse input → retrieve → rerank → generate" → `AgentState` thật + 12 node của A4-2; đồng thời mọi mô tả "ba lớp truy xuất" → **hai lớp** (Lớp 1 SQL + Lớp 2 Need & Feature Retriever), dẫn mục 7.2 schema; (c) mọi tham chiếu rerank BGE-reranker-v2-m3 (`ARCHITECTURE.md` dòng 5, 19, 42, 57, 90, 106, 113, 161, 186, 202 và `docs/architecture_diagram.md` dòng 4, 17, 31, 47) → MVP **không** rerank, embedding qua API provider theo mục 4; (d) sơ đồ Mermaid luồng agent ở cả hai file vẽ lại theo state machine A4-2. Ghi rõ trong tài liệu rằng "graph" là LangGraph (đồ thị bước xử lý), không phải GraphRAG | Test: không còn chuỗi `ReAct`, `BGE-reranker`, `EMBEDDING_PROVIDER_URL` trong hai file. Test: tên node trong sơ đồ khớp đúng tên node đã đăng ký ở `graph.py`. Test `test_docs_contracts.py` mở rộng: mọi thành phần 🎯 trong bảng tech stack phải có task phụ trách hoặc bị đánh dấu ngoài phạm vi MVP | A4-4 |

### A5 — Đề xuất, so sánh, TCO, synthesis

> **TCO contract update (2026-08-09):** `src/products/domain/tco.py` là calculator chuẩn duy
> nhất. A5-5 giữ tên tool và contract Agent để tương thích nhưng chỉ chuẩn hóa input, gọi
> calculator Products rồi ánh xạ breakdown. Các mô tả promotion/thuê pin/công thức riêng trong
> hàng A5-5 cũ được thay thế bởi nguyên tắc này. Cùng input chuẩn hóa, Agent và API phải cùng tổng.

| ID | Task | Nội dung | Nghiệm thu | Chặn |
|---|---|---|---|---|
| A5-1 | Migration `agent_0003` | `agent_runs` (state `CAPTURING → SNAPSHOT_READY → PACKAGE_READY → PENDING_REVIEW → APPROVED → DELIVERED`, terminal `FAILED \| REJECTED`), `run_snapshots`, `run_candidates`, `run_evidence`, `scoring_result`, `tco_estimates`. DDL đầy đủ ở `docs/agent-schema.md` §agent_0003 | `upgrade`/`downgrade` sạch; CHECK constraint chặn state ngoài enum | A0-2 |
| A5-2 | Snapshot bất biến | Ghi bản sao số liệu tại thời điểm truy vấn vào `run_snapshots`; mọi con số về sau đọc từ snapshot, không query lại catalog | Test: sửa giá trong catalog sau khi snapshot → kết quả run không đổi (PRD 5.11 AC) | A5-1, A4-2 |
| A5-3 | Scoring và đề xuất | Ở `domain`. Đầu vào hồ sơ nhu cầu + candidate. Trả tối đa **3** mẫu giảm dần theo điểm, mỗi mẫu **≥ 2 lý do** trỏ trực tiếp tới slot đã khai thác. Xe vượt ngân sách chỉ xuất hiện khi có nhãn "vượt ngân sách X%". **Lý do sinh từ `need_tag`** (qua nhánh 2d) là loại lý do hợp lệ, dùng `feature_need_tags.relevance` làm trọng số — chuỗi truy vết là `slot habit_need_tags → need_tag → feature_code → flag → evidence`, vẫn trỏ về một slot cụ thể nên không phá ràng buộc. **Chỉ assertion `source=FLAG` được vào điểm**; `source=DOCUMENT` không đổi thứ hạng (luật thẩm quyền mục 7.2 schema) | Test: số mẫu luôn trong 1–3. Test: mỗi mẫu ≥ 2 lý do, mỗi lý do trỏ về một slot cụ thể. Test: xe vượt ngân sách không xuất hiện khi thiếu nhãn (PRD 5.3 AC). Test: lý do từ `need_tag` truy được về `habit_need_tags`. Test: thêm/bớt assertion `DOCUMENT` không làm đổi thứ tự đầu ra | A5-2, A3-3 |
| A5-4 | So sánh 2–3 mẫu | Dựng từ `run_snapshots`, không tính lại bằng LLM. Tiêu chí tối thiểu: giá, tầm hoạt động, số ghế, thời gian sạc, cộng tiêu chí gắn ưu tiên bổ sung. Mỗi hàng đánh dấu phương án tốt hơn. **Chặn so sánh chéo loại phương tiện** kèm lý do. **Ô lấy từ assertion `source=DOCUMENT` phải mang nhãn "theo tài liệu, chưa xác minh"** — người đọc phải phân biệt được đâu là dữ liệu đã duyệt, đâu là điều retriever suy ra từ brochure | Test: so sánh `CAR` với `ELECTRIC_MOTORBIKE` → bị chặn kèm lý do (PRD 5.4 AC). Test: so sánh và tra cứu cùng thời điểm ra cùng số liệu. Test: ô nguồn `DOCUMENT` luôn có nhãn; ô nguồn `FLAG` không có nhãn thừa | A5-2 |
| A5-5 | TCO structured adapter | `vinfast_tco_v1` giữ horizon 60 tháng và contract Agent nhưng gọi duy nhất `src/products/domain/tco.py`. Adapter đổi `daily_distance_km × 30` thành quãng đường tháng, ưu tiên `BATTERY_INCLUDED`/`BATTERY_INCLUDED_PRICE` rồi `STARTING_PRICE`, bỏ promotion và chính sách thuê/mua pin lịch sử, nạp đúng một assumption `ACTIVE`, sau đó ánh xạ breakdown canonical về component của Agent. Output luôn kèm giả định, thời điểm và cảnh báo đây là ước tính. | Test golden vector `CAR`/`ELECTRIC_MOTORBIKE`; thay đổi quãng đường cập nhật đúng energy; thiếu dữ liệu trả `TCO_UNAVAILABLE`; test trực tiếp Agent và calculator Products cùng input cho cùng tổng. | A5-1 |
| A5-6 | Synthesis bằng placeholder, không viết số | LLM **không viết chữ số nào**. LLM sinh câu có placeholder (`{CAR_RANGE_KM}`), code thay bằng giá trị từ `run_snapshots` theo allowlist mục 7.5 schema. Placeholder ngoài allowlist → reject trước khi render, không phải hỏi lại LLM. Đây là lý do guardrail A6-1 trở thành đường ngoại lệ thay vì đường chính: số bịa **không thể xuất hiện** vì LLM không có cơ hội gõ số. **Persona bắt buộc (mục 6.11):** `prompts/synthesis_prompts.py` định nghĩa giọng tư vấn viên thân thiện, xưng hô nhất quán; lý do đề xuất (A5-3, structured) phải được **diễn đạt thành lời**, không in thẳng tên cột/toán tử. Persona khai báo một chỗ, đổi giọng là sửa prompt | Test: prompt/đầu ra LLM không chứa chữ số nào ngoài placeholder. Test: placeholder ngoài allowlist bị reject. Test: mỗi placeholder được thay đúng bằng giá trị snapshot kèm `evidence_id`, truy vết được về bản ghi nguồn (PRD 5.2 AC). Test: đầu ra không chứa token structured thô (tên cột, toán tử so sánh, mã slot/feature trần); có bộ golden sample review giọng đính vào E2E A9-2 | A5-3, A5-4, A5-5 |
| A5-7 | Giới thiệu feature theo nhu cầu, không chào hàng | Sau xếp hạng, chọn feature **chủ động giới thiệu** theo mục 7.4 schema: suy `need_tag` từ slot đã xác nhận (không từ câu chữ), query `feature_need_tags` join `vehicle_feature_flags` chỉ `status='YES'`, `verification_status='APPROVED'`. Loại feature khách đã tự nêu (thuộc lý do đề xuất A5-3) và feature mọi candidate đều có (dùng A1-5). Giới hạn số câu mỗi lượt. Sáu quy tắc mục 7.4 | Test: không có feature đủ điều kiện → **trả rỗng**, không rơi về lời khen chung chung (quy tắc 6, mục 7.4). Test: feature khách đã nêu không xuất hiện trong nhóm giới thiệu. Test: feature mọi candidate đều có bị loại. Test: `UNKNOWN`/`PENDING` không được giới thiệu | A5-3, A1-4b, A1-5 |

### A6 — Guardrail và ngoài phạm vi

Gate lõi. Bản plan cũ thiếu hoàn toàn.

| ID | Task | Nội dung | Nghiệm thu | Chặn |
|---|---|---|---|---|
| A6-1 | Guardrail hậu-synthesis | PRD 8.4. Trích mọi số trong câu trả lời, đối chiếu `run_snapshots`. Số không khớp hoặc thiếu `evidence_id` → reject, retry LLM **tối đa 2 lần**; hết 2 lần → `FAILED` và đề xuất tư vấn viên, **không** gửi câu trả lời | Test: LLM chèn giá sai lệch → guardrail bắt, không lọt ra ngoài. Test: số không kèm citation → bị chặn. Test: LLM sai 3 lần → run `FAILED`, không nội dung nào rời hệ thống | A5-6 |
| A6-2 | Phân loại ngoài phạm vi | PRD 5.9. Ba nhãn `IN_SCOPE` / `MISSING_DATA` / `OUT_OF_SCOPE`, ghi `out_of_scope_log`. `MISSING_DATA` và `OUT_OF_SCOPE` nêu rõ giới hạn và **luôn** kèm lối thoát: chuyển tư vấn viên hoặc gợi ý câu hỏi trong phạm vi | Test: câu hỏi về đối thủ → nhãn `OUT_OF_SCOPE`, có log, có lối thoát. Test: mọi câu bị từ chối đều có lối thoát (PRD 5.9 AC) | A2-1, A4-2 |

### A7 — HITL

**Ranh giới bắt buộc:** HITL chặn trước khi gửi khách với mọi câu trả lời thuộc bốn loại — đề xuất mẫu xe, so sánh, TCO, chính sách/diễn giải từ tài liệu (nhánh 2e) — vì đây là những câu có số liệu hoặc cam kết cần người duyệt trước khi khách thấy. Lượt chỉ hỏi slot (short-circuit ở A4-2) đi thẳng `END`, không qua `enqueue_hitl`, vì chưa có nội dung số liệu nào được sinh ra để duyệt — đây là thiết kế cố ý, không phải lỗ hổng bỏ sót HITL.

| ID | Task | Nội dung | Nghiệm thu | Chặn |
|---|---|---|---|---|
| A7-1 | Migration `agent_0004` | `review_queue` (session_id, run_id, content, status `PENDING\|APPROVED\|EDITED\|REJECTED`, advisor_id, processed_at, edited_content). Chi tiết đầy đủ ở `docs/agent-schema.md` §review_queue | `upgrade`/`downgrade` sạch | A5-1 |
| A7-2 | Claim với CAS và lease | Claim mục trong hàng đợi bằng compare-and-set, lease 15 phút, dùng `claimed_by`/`claimed_at`/`lease_expires_at`/`version` của `review_queue` (`docs/agent-schema.md` §review_queue có câu UPDATE mẫu). Đọc-ghi trong một unit of work (mục 6.4) | Test: hai tư vấn viên claim đồng thời → đúng một người thắng, người thua nhận được thông báo "đã có người nhận" chứ không phải lỗi chung chung. Test: lease hết hạn → tư vấn viên khác claim lại được dù `claimed_by` cũ còn tồn tại | A7-1, A0-5 |
| A7-3 | Duyệt, sửa, từ chối | Approve nguyên trạng / edit rồi approve / reject kèm lý do. Tư vấn viên sửa **văn bản**, không sửa số liệu nguồn — đổi số liệu phải qua catalog Admin (PRD 5.11). Ghi log thời gian xử lý mỗi mục (dữ liệu cho KPI-6, chưa dựng báo cáo ở MVP) | Test: run chưa `APPROVED`/`EDITED` → endpoint gửi khách trả 409, không đường nào bypass (PRD 5.6 AC). Test: mọi hành động ghi `advisor_id` + `processed_at`. Test: payload edit chứa số liệu khác snapshot → bị từ chối | A7-2, A6-1 |

### A8 — Lái thử, lịch sử, thông báo nội bộ

| ID | Task | Nội dung | Nghiệm thu | Chặn |
|---|---|---|---|---|
| A8-1 | Migration `agent_0005` | `test_drive_bookings` (customer_id, vehicle_id, showroom, scheduled_at, status `REQUESTED\|CONFIRMED\|CANCELLED`, advisor_id), `internal_notices` (title, content, priority, created_by, created_at), `notice_reads` (notice_id, advisor_id, read_at). Migration riêng, không sửa `agent_0004` mà A7-1 đã commit. DDL đầy đủ ở `docs/agent-schema.md` §agent_0005 | `upgrade`/`downgrade` sạch | A7-1 |
| A8-2 | Đặt lịch lái thử | Từ đề xuất **đã duyệt**, tối đa 3 bước thao tác, mẫu xe mặc định là mẫu đang xem. Chặn trùng khung giờ/showroom nếu có cấu hình giới hạn slot. Xác nhận in-app cho cả khách và tư vấn viên phụ trách, ghi trong **cùng transaction** qua unit of work (mục 6.4) | Test: đặt lịch từ run chưa duyệt → bị chặn. Test: trùng slot đã đầy → từ chối (PRD 5.7 AC). Test: ghi `internal_notices` thất bại → booking rollback, không còn hàng mồ côi | A8-1, A7-3, A0-5 |
| A8-3 | Lịch sử tư vấn | Khách xem toàn bộ lịch sử của chính mình, sắp theo thời gian gần nhất; tư vấn viên chỉ xem khách được phân công | Test âm: tư vấn viên A đọc hồ sơ khách của tư vấn viên B → 403 (PRD 5.8 AC) | A8-1 |
| A8-4 | Thông báo chính sách nội bộ | Admin đăng; tư vấn viên thấy ở phiên đăng nhập kế tiếp; trạng thái đã đọc lưu riêng theo từng người | Test: hai tư vấn viên đọc cùng notice → hai hàng `notice_reads` độc lập (PRD 5.12 AC). Test: `CUSTOMER`/`ADVISOR` gọi API catalog Admin → 403 (PRD 5.11 AC) | A8-1 |

### A9 — Dashboard phễu và baseline KPI

| ID | Task | Nội dung | Nghiệm thu | Chặn |
|---|---|---|---|---|
| A9-1 | Migration `agent_0006` + view `funnel_metrics` | `CREATE VIEW` qua Alembic (`op.execute`), không tạo view bằng script Python ngoài migration. Từ `conversation_sessions`, `review_queue`, `test_drive_bookings`: bắt đầu hội thoại → hoàn thành hồ sơ nhu cầu → có đề xuất → được duyệt → đặt lịch. Lọc 7 ngày / 30 ngày / tuỳ chỉnh | Test: `upgrade`/`downgrade` sạch, `downgrade` có `DROP VIEW`. Test: số liệu khớp bảng nguồn khi kiểm chéo (PRD 5.10 AC) | A8-2 |
| A9-2 | E2E đóng băng | Bộ dữ liệu seed cố định; chạy hết luồng cho cả `CAR` và `ELECTRIC_MOTORBIKE`. Đính kèm **bộ golden sample review giọng** (mục 6.11) làm mẫu đối chiếu độ tự nhiên mỗi lần đổi prompt | Hai E2E xanh, chạy lại cho kết quả giống nhau; golden sample giọng có mẫu để review thủ công | A9-1 |
| A9-3 | Baseline KPI, hiệu năng, judge offline | KPI-1, KPI-2, KPI-4 theo PRD 12.5, trên bộ kiểm thử ≥ 50 câu hỏi. Đo p95 ≤ 6s và ≥ 50 phiên đồng thời (PRD 8.5) — **xác nhận** ở đây bằng tải thật, còn hợp đồng số lần gọi LLM đã được chốt sớm ở A4-2 nên đây không còn là lần đầu phát hiện nếu luồng sai chi phí. **Judge offline:** chạy 50 câu qua graph rồi chấm bằng LLM ba tiêu chí — đúng trọng tâm câu hỏi, giọng tư vấn viên, đủ ý — ghi điểm trung bình + danh sách câu tụt điểm so với lần trước vào `eval/results/`. Chạy hàng đêm / pre-merge, **không** nằm trên đường chạy thật, không đụng p95, không thêm node vào graph. Đây là công cụ test (cùng loại `pytest`), **không** phải LLM-as-Judge trong sản phẩm mà PRD 6.2 loại — phân biệt ở mục 2.2. Golden sample giọng của A9-2 làm mỏ neo hiệu chuẩn cho judge | Báo cáo ba KPI có số thật; báo cáo hiệu năng đính kèm. Test: judge không được import từ `src/agents/` runtime (assert biên: `eval/` một chiều, `src/` không biết `eval/`). Test: bật/tắt judge không đổi kết quả E2E đóng băng A9-2 | A9-2 |

### A10 — Nạp dữ liệu từ brochure PDF

Gate này **bản plan trước thiếu hoàn toàn**. Cả A1 giả định `cars`/`motorbikes`, `vehicle_prices` và `vehicle_documents` đã có dữ liệu, nhưng không task nào chịu trách nhiệm đưa dữ liệu vào. Thực tế đầu vào chỉ có **một brochure PDF cho mỗi mẫu xe**.

#### Ranh giới: cái gì gõ tay, cái gì tự động

| Dữ liệu | Đường vào | Vì sao |
|---|---|---|
| `vehicles`, `cars`/`motorbikes` specs | **Admin gõ tay** qua form CRUD đã có (mục 6.1/6.2 schema) | Sai một chữ số `seat_count`/`range_km` là Lớp 1 lọc sai; sai `energy_consumption` là TCO sai tới đồng. Vài chục dòng xe, gõ tay một–hai buổi và **chắc chắn đúng** |
| `vehicle_prices`, `battery_policies`, `promotions` | **Admin gõ tay** | Cùng lý do, cộng: đây là cam kết thương mại, không được để máy đoán |
| `tco_assumptions` | **Admin gõ tay** | Không nằm trong brochure (giá điện, phí đường bộ là dữ liệu ngoài) |
| `vehicle_documents` (chunk + embedding) | **tự động** — A10-2/A10-3 | Không gõ tay được: một brochure ra hàng chục chunk kèm vector |
| `vehicle_feature_flags` | **tự động đề xuất** `PENDING` → Admin duyệt — A10-4 | Đúng cơ chế §4.9 schema đã dành sẵn cho "pipeline tự động trích xuất từ brochure (có `confidence`)" |

Quyết định này bám §8 `docs/vehicle-catalog-schema.md`, nơi đã **cố ý hoãn** `catalog_import_jobs` khỏi MVP. Nếu về sau số mẫu xe tăng tới mức gõ tay không kham nổi thì mới dựng import job — lúc đó là bảng mới + migration, không sửa gì đã chạy.

#### Nguyên tắc

1. **Không có gì tự động vào `ACTIVE`.** Mọi thứ pipeline sinh ra là **đề xuất**: `vehicle_documents` vào `DRAFT`, `vehicle_feature_flags` vào `PENDING`. Admin duyệt mới được dùng cho tư vấn khách hàng.
2. **A10-4 và ghi ngược của A1-6 là *một* cơ chế, khác thời điểm chạy.** A10-4 chạy một lần khi nạp brochure; A1-6 chạy khi hội thoại chạm phải ô `UNKNOWN`. Cả hai `UPSERT` cùng bảng, cùng trạng thái `PENDING`, cùng mệnh đề `WHERE` chặn ghi đè dòng đã duyệt. **Không viết hai code path.**
3. **Giữ bảng trang bị nguyên khối khi chunk.** Bảng so sánh trang bị theo phiên bản là nguồn `NO` chất lượng cao nhất (mục 7.2 schema, phần "khi nào 2e được phát `NO`") và cũng là thứ dễ mất nhất khi chunker phá bảng thành văn xuôi.
4. **Một brochure một xe** — `vehicle_documents.vehicle_id` không được `NULL` ở đường này. Coverage đồng đều giữa các xe là điều kiện để so điểm retrieval giữa chúng có nghĩa.

| ID | Task | Nội dung | Nghiệm thu | Chặn |
|---|---|---|---|---|
| A10-1 | Nạp file gốc và chống nạp trùng | Mỗi PDF → một dòng `documents` (module `document`, bảng đã có): `content_hash`, `revision`, người nạp, thời điểm. Nạp lại cùng file → nhận ra bằng `content_hash`, không tạo bản sao. Nạp bản brochure mới của cùng xe → `revision` tăng, bản cũ giữ lại cho citation cũ | Test: nạp cùng file hai lần → đúng một dòng `documents`, không nhân bản `vehicle_documents`. Test: file khác nội dung cùng xe → `revision` tăng, chunk cũ không bị xoá. Test: `content_hash` khớp file trên đĩa | A0-2 |
| A10-2 | Trích text giữ cấu trúc | PDF → text theo trang, giữ `page_number` và `section_title` để phục vụ citation. **Bảng trang bị theo phiên bản phải giữ nguyên khối**, không để chunker cắt ngang hàng/cột; đánh dấu block đó bằng `section_title` cố định để nhánh 2e nhận ra được. Không OCR ở MVP — brochure là PDF text-layer; PDF scan ảnh thì báo lỗi rõ, không đoán | Test: bảng trang bị trong PDF mẫu ra đúng một block, không bị cắt. Test: mọi chunk giữ được `page_number`. Test: PDF không có text-layer → lỗi tường minh, không sinh chunk rỗng | A10-1 |
| A10-3 | Chunk, embed và nạp `vehicle_documents` | Chunk theo section, sinh embedding qua `EmbeddingPort` (mục 4 — API provider, không model local), ghi `vehicle_documents` với `status='DRAFT'`, `embedding_model`/`embedding_version`, và `source_document_id`/`source_content_hash`/`source_revision` trỏ về `documents`. `content_tsv` là generated column nên tự có. Admin duyệt → `ACTIVE` | Test: chunk sinh ra đều `DRAFT`, không dòng nào tự vào `ACTIVE`. Test: `source_content_hash` khớp `documents`. Test: FTS và vector query chạy được trên chunk vừa nạp. Test: đổi `embedding_version` → nạp lại được, không lẫn hai version trong cùng truy vấn | A10-2, A1-1 |
| A10-4 | Đề xuất feature flags từ brochure | Với mỗi `feature_code` `ACTIVE` khớp `vehicle_type` (A1-4), dò trong chunk của xe đó và `UPSERT` `vehicle_feature_flags` ở `verification_status='PENDING'` kèm `confidence`. **Dùng lại đúng hàm ghi ngược của A1-6**, gồm cả mệnh đề `WHERE` chặn ghi đè dòng đã `APPROVED`/`REJECTED` và quy tắc `NO` cần bằng chứng dương (im lặng → `UNKNOWN`, hoặc `NO` `confidence` thấp khi brochure có mục trang bị rõ ràng) | Test: mọi dòng sinh ra đều `PENDING`, không dòng nào `APPROVED`. Test: dòng đã `APPROVED` từ trước không bị ghi đè. Test: brochure không nhắc feature → **không** sinh `NO` `APPROVED` trong mọi trường hợp. Test: A10-4 và A1-6 gọi **cùng một** hàm ghi (assert bằng spy, không có code path thứ hai) | A10-3, A1-4, A1-6 |
| A10-5 | Màn hình duyệt hàng loạt cho Admin | Danh sách đề xuất `PENDING` nhóm theo xe, hiện `confidence` và **câu trích trong brochure đã dẫn tới đề xuất** — lấy bằng cách chạy lại truy vấn retriever lúc mở màn hình, không lưu thêm cột (mục "một chỗ đáng cân nhắc", §7.2 schema). Duyệt/từ chối từng dòng hoặc cả xe. Chỉ `ADMIN` | Test: `CUSTOMER`/`ADVISOR` gọi endpoint này → 403 (PRD 5.11 AC). Test: duyệt một dòng → `verification_status='APPROVED'`, dòng đó lập tức tham gia truy vấn tư vấn. Test: từ chối → `REJECTED`, không bao giờ vào truy vấn. Test: mỗi đề xuất hiện được ít nhất một câu trích nguồn | A10-4, A8-4 |

#### Vì sao gate này nằm ngoài đường tới hạn của phần mềm nhưng trong đường tới hạn của sản phẩm

A0–A9 xây **năng lực**; A10 nạp **nội dung**. Test của A0–A9 dùng seed fixture cố định nên không chờ A10. Nhưng không có A10 thì hệ thống chạy trên catalog rỗng: Lớp 1 trả 0 kết quả, nhánh 2e không có gì để đọc, và E2E A9-2 chạy trên dữ liệu thật không thực hiện được. A10 khởi động được ngay sau A1-4 và chạy song song với A5–A9.

## 9. Thứ tự và phụ thuộc

```text
A0 ──> A1 ──> A4 ──> A5 ──> A6 ──> A7 ──> A8 ──> A9
  │      └──────────> A10 ─────────────────────────┘
  └──> A2 ──> A3 ──┘
```

A1 và A2 chạy song song được sau A0. A3 cần A2. A4 cần cả A1 và A3. Từ A5 trở đi tuần tự. Trong một gate, cột **Chặn** quyết định thứ tự; task không bị chặn lẫn nhau thì làm theo số thứ tự.

**A10 là nhánh song song, không nối tiếp.** Khởi động được ngay sau A1-4 (cần danh mục feature để biết dò cái gì) và chạy song song với A5–A9, trừ A10-4 phải đợi A1-6 vì hai bên dùng chung một hàm ghi. Ràng buộc duy nhất về đích: **A10 phải xong trước khi A9-2 chạy trên dữ liệu thật** — E2E đóng băng dùng seed fixture nên không chờ, nhưng nghiệm thu sản phẩm thì cần catalog có nội dung.

## 10. Tiêu chí hoàn thành MVP

1. Mười hai hạng mục PRD 6.1 đều có task phụ trách và test nghiệm thu xanh.
2. Không có số liệu nào rời hệ thống mà không truy vết được về một bản ghi cụ thể.
3. Không có nội dung nào tới khách mà chưa qua `APPROVED` hoặc `EDITED`.
4. `alembic -c alembic-agent.ini upgrade head` rồi `downgrade base` sạch trên DB trắng.
5. Ranh giới mục 6 có test cưỡng chế và xanh: `domain` không import framework; `nodes/` không import SQLAlchemy / repository / domain và mỗi node ≤ 15 câu lệnh; `AgentServices` chỉ chứa nhóm advisory.
6. `ruff`, `mypy`, `pytest`, `pip-audit` xanh trong CI.
7. Baseline KPI-1/2/4 có số; bằng chứng p95 ≤ 6s và 50 phiên đồng thời đính kèm.
8. Catalog có nội dung thật: mỗi mẫu xe đang bán có specs + giá đã nhập, brochure đã nạp thành `vehicle_documents` `ACTIVE`, và các đề xuất `vehicle_feature_flags` đã được Admin duyệt xong (A10). Không dòng nào tự động vào `ACTIVE`/`APPROVED` mà chưa qua người.

## 11. Mở rộng sau MVP: Corpus kiến thức chung (Global RAG)

**Trạng thái: NGOÀI 44 task MVP.** Không thuộc PRD 6.1, nên theo nguyên tắc scope ở mục 2–3 (cái gì không nằm trong PRD 6.1 thì cắt) nó **không** được làm trong MVP. Ghi ở đây vì đã có đặc tả đủ để thi công ngay sau khi MVP xanh, không phải nghĩ lại từ đầu. Chỉ bắt đầu khi tiêu chí hoàn thành mục 10 đã đạt.

### 11.1. Vấn đề nó giải

Nhánh 2e hiện tại (A1-6) luôn cần `vehicle_id` — chỉ trả lời câu diễn giải về **một xe cụ thể** còn sống sau Lớp 1 và nhánh 2c. Câu hỏi **không gắn xe nào** rơi thẳng vào `MISSING_DATA`/`OUT_OF_SCOPE` (A6-2) và bị từ chối, dù nội dung vẫn trong lĩnh vực tư vấn:

- "Chính sách bảo hành VinFast nói chung thế nào?"
- "Sạc nhanh DC hoạt động ra sao, có hại pin không?"
- "Thủ tục trả góp, hồ sơ cần những gì?"

Đây là kiến thức phi cấu trúc, không mã hoá được thành cột hay flag — đúng bài của RAG. Corpus chung biến một phần các câu đang bị từ chối thành trả lời được, **mà không nới lỏng bất kỳ cam kết nào** (vẫn snapshot, vẫn guardrail, vẫn HITL).

### 11.2. Ranh giới bắt buộc (không được vi phạm)

| Ràng buộc | Vì sao |
|---|---|
| Corpus chung là **nguồn RAG thứ hai**, không thay Lớp 1 hay bất kỳ nhánh nào của Lớp 2 | Câu trả lời được bằng structured data vẫn phải đi structured — không RAG hoá giá/specs/feature |
| Chỉ kích hoạt khi **không resolve được xe cụ thể** và scope_classifier gán câu vào **tập chủ đề đóng** được hỗ trợ | Không mở cửa cho câu ngoài lĩnh vực; giữ đúng tinh thần A6-2 |
| Mọi số liệu vẫn qua **snapshot (A5-2) + guardrail (A6-1)**, `evidence_id` trỏ về tài liệu nguồn | Cam kết truy vết (tiêu chí hoàn thành 2) không có ngoại lệ |
| Câu trả lời vẫn qua **HITL (A7)** trước khi tới khách | Cam kết duyệt (tiêu chí 3) không có ngoại lệ |
| Thêm tài liệu chung là **`INSERT`**, thêm chủ đề là 1 dòng enum đóng — không sửa code, không migration | Nguyên tắc mở rộng bằng dữ liệu (mục 6.7b) |

### 11.3. Vị trí kiến trúc

- **Dữ liệu — bảng mới `knowledge_documents` thuộc module `document`** (không phải `agent`, giống `vehicle_documents`): `content`, `embedding vector`, `content_tsv` generated + GIN index, `topic` (enum đóng: `WARRANTY`, `CHARGING`, `FINANCING`, `COMPANY_POLICY`, `MAINTENANCE`…), `status='ACTIVE'`, khoảng hiệu lực, `source_document_id`/`source_content_hash`/`source_revision` trỏ về `documents`. **Không** có `vehicle_id` — đây là khác biệt cốt lõi với `vehicle_documents`. Migration mới (`d0cument0003`), **không** sửa `d0cument0002` đã chạy.
- **Truy xuất — nhánh retrieval thứ hai** trong `services/retrieval.py` (hoặc adapter `feature_retrieval.py`): hybrid dense + FTS hợp nhất RRF (k=60), y hệt nhánh 2e, chỉ đổi corpus và bỏ điều kiện `vehicle_id`, thêm lọc `topic`. Không đi qua `FeatureRetrievalPort` vì nó không sinh `FeatureAssertion` — corpus chung không nói về tính năng của một xe cụ thể.
- **Điều kiện kích hoạt — nối vào `scope_classifier` (A6-2)**: trước khi gán `MISSING_DATA`, nếu câu thuộc chủ đề hỗ trợ và không gắn xe cụ thể thì thử corpus chung; không có kết quả đủ tin cậy (ngưỡng điểm) → mới `MISSING_DATA` + lối thoát như cũ.

### 11.4. Task (đánh số G để không lẫn với A0–A9)

| ID | Task | Nội dung | Nghiệm thu | Chặn |
|---|---|---|---|---|
| G1-1 | Migration `knowledge_documents` | Bảng mới ở module `document`, migration `d0cument0003`, không sửa `d0cument0002`. Cột như mục 11.3, `topic` là enum đóng, không có `vehicle_id` | `upgrade`/`downgrade` sạch; `content_tsv` sinh được; FTS + vector query chạy trên seed | MVP xong (mục 10) |
| G1-2 | Retrieval corpus chung | Nhánh hybrid dense + FTS RRF trên `knowledge_documents`, lọc `topic` + `status='ACTIVE'` + khoảng hiệu lực. Không đụng candidate set của Lớp 1/2 | Test: chỉ trả tài liệu `ACTIVE`; không trộn với `vehicle_documents`; kết quả kèm điểm để áp ngưỡng tin cậy | G1-1 |
| G1-3 | Nối vào scope handling | `scope_classifier` (A6-2): câu chung + chủ đề hỗ trợ → thử corpus chung trước `MISSING_DATA`; dưới ngưỡng → `MISSING_DATA` + lối thoát như cũ | Test: câu chủ đề `WARRANTY` không gắn xe → trả lời từ corpus, có `evidence_id`. Test: câu ngoài tập chủ đề → vẫn `OUT_OF_SCOPE`. Test: dưới ngưỡng tin cậy → `MISSING_DATA` + lối thoát | G1-2, A6-2 |
| G1-4 | Seed chủ đề + tài liệu mẫu | Tập `topic` đóng khai báo cùng chỗ; vài tài liệu mẫu mỗi chủ đề | Test: mọi `topic` trong seed thuộc tập đóng; chủ đề ngoài tập bị từ chối | G1-1 |
| G1-5 | Guardrail + HITL cho câu trả lời chung | Tái dùng A6-1/A7 nguyên trạng, chỉ đảm bảo `evidence_id` trỏ về `knowledge_documents` và câu trả lời chung vẫn vào `review_queue` | Test: số trong câu trả lời chung không khớp nguồn → guardrail chặn. Test: câu trả lời chung không bao giờ tới khách trước khi `APPROVED`/`EDITED` | G1-3, A6-1, A7-3 |

### 11.5. Vì sao KHÔNG nhét vào MVP

PRD 6.1 không liệt kê "kiến thức chung cấp hãng". Đưa vào MVP sẽ: (a) phá nguyên tắc scope ở mục 2–3 mà cả plan bám theo; (b) thêm một migration và một nhánh retrieval vào đường tới hạn của 44 task, đội rủi ro tiến độ; (c) câu chung không có trong bộ nghiệm thu PRD nên không có cách chấm ổn định. Để sau MVP, nó là phép cộng thuần: bảng mới + nhánh retrieval mới + nối một điểm vào A6-2, **không sửa** gì đã chạy.
