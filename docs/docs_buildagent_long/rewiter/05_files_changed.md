# Danh sách file đã tạo mới / đã sửa

## Tổng quan

| Nhóm | Tạo mới | Đã sửa |
|---|---:|---:|
| `src/agents/domain/` | 6 | 0 |
| `src/agents/services/` | 3 | 3 |
| `src/agents/adapters/` | 1 | 1 |
| `src/agents/nodes/` | 1 | 2 |
| `src/agents/prompts/` | 2 | 0 |
| `src/agents/` (gốc) | 0 | 6 |
| `migrations/` | 1 | 0 |
| `tests/` | 7 | 4 |
| Tài liệu | 8 | 2 |
| Dependency | 0 | 2 |
| **Tổng** | **29** | **20** |

---

## 1. Domain — thuần Python, không I/O (6 file mới)

| File | Vai trò |
|---|---|
| `domain/text_normalization.py` | Chuẩn hoá tiếng Việt: NFC → bỏ dấu qua NFD → casefold → tokenize. Một định nghĩa duy nhất của "hai chuỗi này là một" cho cả bốn lớp. Kèm `digits_from_words` (số đếm ↔ chữ số). |
| `domain/entity_catalog.py` | Ba danh mục thực thể tĩnh (157 alias). Thuộc tính **sinh từ** `FIELD_KEYWORDS` chứ không chép tay. Alias số-đếm tiếng Việt cho tên xe. |
| `domain/fuzzy_match.py` | Lớp 2. Khớp cửa sổ token bằng `rapidfuzz`, hai luật an toàn cho token ngắn. |
| `domain/rewrite.py` | Lớp 1 phần thuần: cổng `rewrite_trigger` (giữ ngân sách A4-2) + guard `evaluate_rewrite` (chặn mô hình sáng tác). |
| `domain/nlu_confidence.py` | Lớp 3 + Lớp 4: `classify_intent`, `route_confidence`, `advisory_flow_active`, `ConfidenceThresholds`. |
| `domain/pending_intent_confirmation.py` | Vòng đời câu xác nhận ý định (TTL 15 phút, đọc "đúng"/"không phải"). |
| `domain/fuzzy_slot_extractors.py` | **Điểm nối 2**: bộ trích slot khớp mờ, dự phòng cho A7-10. Ngưỡng riêng 88. |

## 2. Services (3 mới, 3 sửa)

| File | Trạng thái | Thay đổi |
|---|---|---|
| `services/rewrite.py` | **MỚI** | Lớp 1: quyết định có gọi LLM → gọi → áp guard. Nuốt lỗi hạ tầng nhưng luôn log. |
| `services/nlu_pipeline.py` | **MỚI** | Điều phối Lớp 1→4, `NluPipelineConfig.from_env()`, `NluDecision`, `build_known_tokens`. |
| `services/pending_intent_confirmation.py` | **MỚI** | Tiêu thụ câu trả lời cho câu xác nhận. |
| `services/registry.py` | sửa | Thêm 2 Protocol (`NluPipelineService`, `PendingIntentConfirmationService`) + 2 field vào `AgentServices`. Thuần cộng — không đổi chữ ký nào đang có. |
| `services/pending_slot.py` | sửa | Thêm `fallback_extractors` + `_extract()` (bộ chính trước, bộ mờ sau). **Không đổi hành vi cũ**: không nối bộ dự phòng thì chạy y như trước. |
| `services/conversation.py` | sửa | Thêm `load/save_pending_intent_confirmation`. |

## 3. Adapters (1 mới, 1 sửa)

| File | Trạng thái | Thay đổi |
|---|---|---|
| `adapters/rewrite_source.py` | **MỚI** | `LlmTextRewriter` (tái dùng `LLMPort.synthesize`, **không** đổi Protocol) + `parse_rewrite_payload` (gỡ rào ```` ``` ````, chặn `bool` lọt vào ô confidence). |
| `adapters/conversation_repository.py` | sửa | Thêm `load/save_pending_intent_confirmation` trên `SqlAlchemySessionRepository`. |

## 4. Nodes (1 mới, 2 sửa)

| File | Trạng thái | Thay đổi |
|---|---|---|
| `nodes/recognize_intent.py` | **MỚI** | Node đầu graph. Thin wrapper gọi `nlu_pipeline`, map vào state. Không import `domain/` (so tier bằng chuỗi). Nuốt lỗi → lượt chạy như cũ. |
| `nodes/__init__.py` | sửa | Đăng ký `recognize_intent` (15 → 16 node). |
| `state.py` | sửa | Thêm `rewritten_or_original(state)` — hai điểm DUY NHẤT bản rewrite chảy vào pipeline cũ dùng chung một hàm, để scope và extraction không bao giờ chấm hai câu khác nhau. Đặt cạnh field chứ không trong `nodes/`: `test_graph_boundary` bắt mọi file `nodes/` phải là node có `__call__`. |
| `nodes/extract_slots.py` | sửa | Gọi `rewritten_or_original()` thay vì `state["user_message"]`. |
| `nodes/classify_scope.py` | sửa | Gọi `rewritten_or_original()`. Sau khi gộp với `build-agent`, node này đứng ngay sau `recognize_intent`; chấm trên câu thô thì thứ tự đó không mua lại được gì. |

## 5. Prompts (2 mới)

| File | Vai trò |
|---|---|
| `prompts/rewrite_prompts.py` | Prompt Lớp 1: 3 việc được phép, 5 điều cấm, 5 ví dụ (kể cả ví dụ phủ định), danh mục xe để đối chiếu chính tả. |
| `prompts/nlu_replies.py` | Template CONFIRM/CLARIFY. Nhãn+giá trị nút bấm khớp với `_AFFIRMATIONS`/`_DENIALS`. |

## 6. `src/agents/` gốc (6 sửa)

| File | Thay đổi |
|---|---|
| `state.py` | +10 field `total=False`. **Không đụng field nào có sẵn** — đặc biệt không đụng `user_message`, `intents`, `awaiting_review`, `terminal_reason`. |
| `graph.py` | `START → recognize_intent → {confirm: END, clarify: END, proceed: extract_slots}`. Cạnh `START → extract_slots` cũ chuyển thành cạnh từ node mới. |
| `routing.py` | `route_after_recognize_intent`. Thiếu `nlu_confidence_tier` → `"proceed"` (chưa nối service thì chạy như cũ). |
| `chain.py` | `_resume_intent_confirmation` (đặt sau `_resume_pending_slot`, trước `_resume_active_task`), `_remember_intent_confirmation`, `_handoff_active`, `_quick_replies`. |
| `contracts.py` | `QuickReplyView` + `TurnResult.quick_replies` (default rỗng). |
| `ports.py` | `SessionRepository` +2 method mới; **và +2 method của A7-10 vốn bị sót khai báo** (`load/save_pending_slot`) — bản cài đặt đã có sẵn, chỉ Protocol thiếu nên mypy không kiểm được. |
| `api/routes.py` | `QuickReply` model + `TurnResponse.quick_replies` (default rỗng → client cũ không vỡ). |
| `models.py` | `ConversationSessionRow.pending_intent_confirmation` (JSONB nullable). |

## 7. Migration (1 mới)

| File | Nội dung |
|---|---|
| `migrations/agents/versions/agent_0019_pending_intent_confirmation.py` | `down_revision = "agent_0018"`. Thêm cột JSONB `pending_intent_confirmation` vào `conversation_sessions`. `downgrade` drop sạch. |

> **Vì sao cần migration** (plan ghi "ưu tiên file cấu hình tĩnh"): danh mục
> thực thể **đúng là** file tĩnh, không vào DB. Cột này lưu thứ khác hẳn —
> **state của một phiên cụ thể** (câu xác nhận đang chờ khách trả lời), sống qua
> nhiều lượt. Không có chỗ nào khác để nó ở, và `pending_slot_request` không
> dùng chung được (khác ngữ nghĩa, khác vòng đời, khác service tiêu thụ).

## 8. Tests (7 mới, 4 sửa)

### Mới
| File | Test |
|---|---:|
| `tests/agents/unit/domain/test_text_normalization.py` | 9 |
| `tests/agents/unit/domain/test_fuzzy_match.py` | 13 |
| `tests/agents/unit/domain/test_rewrite_guards.py` | 16 |
| `tests/agents/unit/domain/test_nlu_confidence.py` | 16 |
| `tests/agents/unit/domain/test_fuzzy_slot_extractors.py` | 10 |
| `tests/agents/unit/services/test_nlu_pipeline.py` | 17 |
| `tests/agents/unit/services/test_pending_intent_confirmation.py` | 11 |
| `tests/agents/integration/test_recognize_intent_node.py` | 10 |
| **Tổng** | **102** |

### Sửa — đều là test "chốt danh sách kiến trúc"
| File | Vì sao phải sửa |
|---|---|
| `test_architecture_docs.py` | `NODE_NAMES` chốt danh sách node — thêm `recognize_intent`. |
| `test_graph_boundary.py` | Chốt danh sách field `AgentServices` — thêm 2 field mới. |
| `test_guardrail_graph.py` | `SimpleNamespace` nodes giả cần attribute `recognize_intent`. |
| `test_migrations.py` | Chốt head migration — `agent_0017` → `agent_0019`. |

## 9. Tài liệu (8 mới, 2 sửa)

| File | Trạng thái |
|---|---|
| `docs/docs_buildagent_long/rewiter/00…07*.md` | **MỚI** (8 file) |
| `ARCHITECTURE.md` | sửa — 15→16 node, mục "Nhận diện ý định bốn lớp", vai LLM 3→4 việc, sơ đồ mermaid |
| `docs/architecture_diagram.md` | sửa — 15→16 node, sơ đồ mermaid |

> Hai file này **bắt buộc** phải sửa: `test_document_mentions_every_registered_node`
> assert mọi node đã đăng ký đều được nhắc trong tài liệu kiến trúc.

## 10. Dependency (2 sửa)

| File | Thay đổi |
|---|---|
| `pyproject.toml` | `+ rapidfuzz>=3.0.0` |
| `uv.lock` | `rapidfuzz==3.14.5` (đã cài, license MIT) |

---

## Điểm nối vào hệ thống cũ — tóm tắt

| # | Vị trí | Vì sao ở đó |
|---|---|---|
| 1 | Node `recognize_intent`, đầu graph | Câu phải sạch trước `extract_slots` (gọi LLM) và trước `classify_scope` (gắn OUT_OF_SCOPE) |
| 2 | `PendingSlotServiceImpl.fallback_extractors` | `chain._resume_pending_slot` bypass graph — node không bao giờ thấy lượt trả lời slot |
| 3 | `chain._resume_intent_confirmation` | "đúng rồi" đứng riêng bị `classify_scope` gắn OUT_OF_SCOPE — đúng bug gốc của A7-10 |
| 4 | `state.rewritten_or_original` | Hai chỗ DUY NHẤT bản rewrite chảy vào pipeline cũ: `classify_scope` và `extract_slots` |
