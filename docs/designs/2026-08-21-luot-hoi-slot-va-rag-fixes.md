# Tổng hợp phiên 2026-08-21/22: fix luồng hỏi slot + RAG + kiến trúc hiểu-ý/quyết-định

Session dài, liên tục — ghi lại toàn bộ để phiên sau không phải hỏi lại các bug đã gặp.
Branch: `feature/tong-hop-uu-dai`. Chưa commit gì trong phiên này — mọi thay đổi còn nằm ở
working tree, cần review + commit theo git flow trước khi làm tiếp.

## 1. Đã sửa xong, có test, verify tay qua DB thật

Thứ tự thời gian, mỗi mục: bug → root cause → file sửa → cách verify.

### 1.1 Lượt 1 không hỏi km/ngày, sạc tại nhà nữa
- **Yêu cầu**: chỉ hỏi tài chính, mục đích, số người ở lượt 1.
- **Sửa**: `domain/slot_tree.py` — bỏ `REQUIRED_RANGE_KM`, `HOME_CHARGING` khỏi
  `OPENING_GROUP`/`_PURPOSE_OPENING_GROUP`.

### 1.2 Câu hỏi số người lặp lại vế mục đích dù khách đã nói rồi
- **Bug**: câu ghép "chở mấy người, hoặc dùng để đi làm/giao hàng/cá nhân" vẫn hỏi cả mục
  đích dù khách đã trả lời trước đó.
- **Sửa**: `services/slot_planning.py::question_for_group` — khi `PURPOSE` đã có trong
  `known_slots`, đổi sang câu hỏi CHỈ về số người (`_PASSENGER_COUNT_ONLY_VARIANTS`).

### 1.3 Lượt 2 (hỏi tính năng) chưa từng chạy — dead code do bug routing
- **Bug**: `routing.py::route_after_layer1` gate bằng `_has_discriminating_feature(state)`
  đọc `candidate["features"]`, nhưng `layer1` node không bao giờ gắn field đó vào candidate
  → luôn `False` → không bao giờ rẽ "narrow".
- **Quyết định của Sếp**: đủ lượt 1 (ngân sách) là lượt 2 LUÔN hỏi, không phụ thuộc còn
  feature phân biệt được hay không.
- **Sửa**: `routing.py` — bỏ hẳn `_has_discriminating_feature`, `route_after_layer1` chỉ
  còn xét `_turn_added_a_slot(state) and not narrow_asked`.
- **Sửa kèm**: `services/candidate_tuning.py::CatalogDifferentiator.ask` — không còn feature
  nào phân biệt được thì KHÔNG bỏ lượt 2 nữa, fallback hỏi mở toàn bộ allowlist.

### 1.4 Câu ghi nhận thông tin ("Em đã ghi nhận...")
- **Yêu cầu**: mọi lượt hỏi SAU lượt 1 phải mở đầu bằng câu xác nhận lại thông tin đã có.
- **Sửa**: `services/slot_planning.py::captured_recap()` — liệt kê ngân sách (đổi ra
  "triệu"/"tỷ"), mục đích, số người đã biết. Nối vào MỌI điểm phát câu hỏi: nhóm slot lượt 1
  (`nodes/ask_or_retrieve.py`), hỏi đơn lẻ, câu xác nhận đơn vị quãng đường, câu hỏi lượt 2
  (`nodes/narrow.py`).

### 1.5 Tính năng khách chọn ở lượt 2 không được dùng làm lý do đề xuất
- **Bug 2 lớp**:
  1. `domain/scoring.py` chưa có cơ chế nào đọc `feature_mentions`/`pending_feature_codes`
     để thêm lý do.
  2. Khi thêm cơ chế đó, phát hiện bug CÓ SẴN TỪ TRƯỚC ở `domain/claim_policy.py`:
     `SLOT_TRACE_PATTERN` chỉ khớp `[slot=x]` trơn, nhưng `ScoringReason.render()` của
     `_need_tag_reasons`/`_document_reasons` luôn nối thêm `need_tag=`/`feature_code=`/
     `source=`/`evidence=` trước dấu `]` — nên 2 nguồn lý do đó CHƯA TỪNG sinh được claim
     nào, từ trước phiên này. Sửa xong thì nhu cầu suy từ thói quen sử dụng (habit_need_tags)
     cũng bắt đầu được cite trong đề xuất — không riêng lượt 2.
- **Sửa**:
  - `domain/scoring.py::_feature_mention_reasons` (mới) — xe có tính năng khách chọn (FLAG
    đã duyệt YES) → thêm lý do, đặt TRƯỚC `_need_tag_reasons` để thắng khi trùng feature.
  - `domain/claim_policy.py` — sửa regex nhận multi-field trace; khoá claim theo
    `slot:feature_code` (không gộp mất nhiều feature khác nguồn vào 1 claim); tính năng
    khách CHỦ ĐỘNG chọn có claim text riêng ("có đúng X mà anh/chị vừa xác nhận quan tâm ở
    lượt trước"), không dùng chung câu chung chung của need-tag.
  - `services/recommendation.py`/`nodes/score.py` — nối `feature_mentions` (lượt này) +
    `pending_feature_codes` (lượt trước) từ state xuống `ScoringProfile`.

### 1.6 Nhãn tính năng lẫn tiếng Anh ("Anti Theft" thay vì "khoá chống trộm")
- **Bug**: `feature_definitions.name` trong DB cho `ANTI_THEFT`/`BATTERY_REMOVABLE` là tiếng
  Anh (chưa dịch) — code cũ ưu tiên tên catalog trước `FEATURE_LABELS` (bảng tiếng Việt curated).
- **Sửa**: `services/candidate_tuning.py::_first_name` — đảo ưu tiên, `FEATURE_LABELS` trước,
  catalog chỉ dùng cho mã lạ ngoài allowlist.

### 1.7 Chỉ có "khoá chống trộm" được gợi ý — allowlist quá hẹp
- **Root cause**: `ASKABLE_FEATURES` chỉ khai 3 mã (`BATTERY_REMOVABLE`, `HIGH_PAYLOAD`,
  `ANTI_THEFT`) trong khi catalog có 17 mã ACTIVE. `HIGH_PAYLOAD` (đang trong allowlist) có
  **0 xe nào có dữ liệu** — hỏi vô nghĩa.
- **Query DB xác nhận dữ liệu thật đáng thêm**:
  - `TOWING`: 5 xe YES / 6 NO (ô tô) — tách đôi tốt.
  - `BATTERY_SWAPPABLE`: 15 YES / 22 NO (xe máy điện) — tách đôi tốt.
  - `FAST_CHARGING`: 10 YES / 0 NO (ô tô) — không tách đôi nhưng dữ liệu XÁC THỰC.
  - `PANORAMIC_ROOF` (cửa sổ trời): 0/0 — **không thêm**, catalog chưa duyệt cho xe nào.
- **Sửa**: `prompts/feature_askable.py` — thêm 3 mã trên vào `ASKABLE_FEATURES` theo đúng
  bucket, thêm nhãn tiếng Việt vào `FEATURE_LABELS`.

### 1.8 Bug thật: hỏi ô tô lại gợi ý tính năng xe máy
- **Root cause**: `askable_for()` fallback khi bucket không khớp (vd mục đích rơi ngoài
  FAMILY/WORK/SERVICE cho ô tô) dùng CHUNG `ALL_ASKABLE` — gộp CẢ hai nhánh xe. Ô tô có thể
  nhận về `BATTERY_REMOVABLE`/`BATTERY_SWAPPABLE` (chỉ xe máy điện có).
- **Sửa**: `prompts/feature_askable.py` — `_ALL_ASKABLE_BY_VEHICLE_TYPE`, fallback tách riêng
  theo loại xe, hợp đúng mã đã khai cho loại xe đó.

### 1.9 RAG hoàn toàn trống — 0 dòng `vehicle_documents`
- **Phát hiện**: DB có `vehicle_documents` nhưng 0 dòng — không có tài liệu nào để trích dẫn,
  bất kể code đúng hay sai.
- **Đã có sẵn nhưng chưa từng chạy**: `data-p150/car_pdf/*.md` (brochure ô tô đã crawl,
  9 model) + `data-p150/catalog/vehicle_documents_car_review.csv` (nội dung đã duyệt) +
  script chính thức `scripts/build_car_documents.py` (lọc rác bán hàng, sinh embedding thật,
  ghi `status=ACTIVE`).
- **Đã chạy** (không sửa code, chỉ chạy tool có sẵn):
  ```bash
  uv run python scripts/seed_catalog_data.py        # nạp lại catalog gốc, ON CONFLICT DO NOTHING
  uv run python scripts/build_car_documents.py --load --dsn "postgresql+asyncpg://p150_auth:p150_local_dev@localhost:5432/p150_auth"
  ```
  → 362 dòng `vehicle_documents` ACTIVE, embedding thật (`text-embedding-3-large`).
- **Verify**: full-text `content_tsv @@ plainto_tsquery('khóa chống trộm')` khớp đúng VF3.
  Test hội thoại thật sau đó CÓ trích dẫn RAG thật trong câu đề xuất VF2.

### 1.10 Công thức điểm ngân sách thưởng xe RẺ thay vì xe GẦN ngân sách
- **Bug** (Sếp báo, verify công thức): `_budget_reasons` dùng `headroom = (budget-price)/budget`
  — giá càng THẤP, headroom càng lớn, điểm càng cao. Khách nói "500 triệu" mà xe 188tr được
  cộng điểm CAO HƠN xe 496tr.
- **Quyết định của Sếp**: không loại xe rẻ hơn (khách có thể vẫn thích tiết kiệm), chỉ đổi ưu
  tiên xếp hạng — xe GẦN ngân sách nhất (từ dưới lên) điểm cao nhất.
- **Sửa**: `domain/scoring.py::_budget_reasons` — đổi `headroom` thành `closeness = price/budget`.

### 1.11 "Còn tính năng nào khác không" bị lờ đi, đi thẳng tới đề xuất
- **Bug**: câu này không nêu tên xe (→ `CATALOG_LOOKUP` không nhận, cần `vehicle_mentions`)
  và không sinh slot mới (→ `_turn_added_a_slot` không tự bắt được) → hệ thống bỏ qua hoàn
  toàn, đi thẳng route "proceed" → đề xuất luôn mà không trả lời câu hỏi.
- **Sửa**:
  - `domain/feature_followup.py` (mới) — `wants_more_features()`, regex nhận diện câu hỏi
    kiểu này (có/không dấu).
  - `routing.py::route_after_layer1` — nhận diện được thì quay lại "narrow" dù không sinh
    slot mới.
  - `nodes/narrow.py` + `services/candidate_tuning.py` — thêm `force_full_list: bool`, khi
    `True` thì BỎ tiêu chí "phải phân biệt được", liệt kê thẳng TOÀN BỘ allowlist (không cắt
    ở `MAX_DIFFERENTIATORS_PER_QUESTION=3` nữa — khách đã hỏi thẳng thì không giới hạn).

### 1.12 `derive_need_tags` (A5-7, cơ chế "giới thiệu tính năng chủ động") purpose không bao giờ khớp
- **Bug**: so `purpose == "kinh_doanh"`/`"giao_hang"` (snake_case đóng) trong khi `purpose`
  trích xuất thật LUÔN là câu tự nhiên ("kinh doanh", "giao hàng") — 2 điều kiện đó chưa từng
  khớp, không riêng mục đích lạ.
- **Sửa**: `domain/feature_introduction.py` — dùng lại `purpose_bucket()` (cùng cơ chế lượt 2).
- **⚠️ Lưu ý quan trọng**: cụm `derive_need_tags`/`select_feature_introductions`/
  `introduce_features` (A5-7) **CHƯA ĐƯỢC NỐI VÀO GRAPH HAY API NÀO** — code chết, không ảnh
  hưởng hội thoại thật hiện tại. Sửa xong vẫn chưa chạy sống cho tới khi có ai nối dây.

### 1.13 Guardrail đẩy sang tư vấn viên (HITL) khi khách nói nhu cầu bình thường ("cần xe nhỏ gọn")
- **Đây là bug nặng nhất phiên này — hỏng cả lượt, không chỉ thiếu gợi ý.**
- **Root cause**: `COMPACT_SIZE` có dữ liệu nhưng `verification_status='PENDING'` (chưa
  `APPROVED`). Code cũ gộp MỌI nhãn tính năng khách nhắc (kể cả không có claim hợp lệ) thẳng
  vào `customer_wording` gửi cho LLM. LLM cố nhắc tới "nhỏ gọn" trong câu trả lời mà không có
  claim backing → `reject_unstructured_claims` từ chối draft liên tục → hết
  `MAX_SYNTHESIS_ATTEMPTS` (nội bộ) → hết `MAX_GUARDRAIL_RETRIES=2` (graph) → handoff người.
- **Sửa**: tách `customer_wording` (purpose/habit tags, giữ nguyên) khỏi tính năng — tính
  năng giờ truyền dưới dạng MÃ THÔ (`feature_mention_codes`) tới tận
  `synthesis.py::_pitch_for`, nơi DUY NHẤT biết claim thật của TỪNG xe. Chỉ giải nhãn + đưa
  vào ngữ cảnh LLM nếu xe ĐÓ thật sự có `CLAIM_<code>`.
  - `nodes/synthesize.py` — `_customer_wording` bỏ phần feature; thêm `_feature_mention_codes`.
  - `services/synthesis.py` — `synthesize()`/`_pitch_for()` nhận `feature_mention_codes`, lọc
    theo `claim_by_key` trước khi merge vào `customer_wording` cuối.

## 2. Đã phát hiện, CHƯA sửa — cần quyết định trước khi làm

| # | Vấn đề | Vì sao chưa làm | Gợi ý hướng đi |
|---|---|---|---|
| 1 | RAG quote không xuất hiện đều — VF2 có quote thật trong câu đề xuất, VF3/VF5 (cùng lượt) không thấy | Chưa điều tra — có thể do `load_quotes`/retrieval chỉ trả evidence cho 1 xe, hoặc do LLM chỉ chọn trích cho xe đầu | Kiểm tra `RunEvidenceRow` sau 1 lượt thật — có evidence cho cả 3 xe không, hay chỉ VF2 |
| 2 | `COMPACT_SIZE` (và các mã PENDING khác) chưa được duyệt | Việc duyệt là quy trình admin (`vehicle_feature_flags.verification_status`), không phải code | Duyệt tay qua DB, hoặc build UI/endpoint duyệt (chưa có) |
| 3 | `services/slot_planning.py::_is_rejected`/`_rejection_reason` (regex nhận "loại VF6, giữ VF8") | Fragility tương tự các bug đã sửa, nhưng chưa có bug report cụ thể trong phiên | Ứng viên tốt cho Bước 1 (mục 3) — đưa vào tool schema extraction thay vì regex |
| 4 | `"500 home_charging slot must be boolean"` — `DECLINED_SLOT_VALUE`/`__declined__` gặp parser strict | Chỉ là mục trong bảng bug Sếp paste, CHƯA tự kiểm chứng/tái hiện trong phiên này | Cần tái hiện trước khi sửa — grep chỗ nào ép kiểu `bool`/`int` không guard `__declined__` trước |
| 5 | `document/application/brochure_ingestion.py::BrochureIngestionService` chưa có API endpoint | Ngoài phạm vi yêu cầu ban đầu | Cần route HTTP nếu muốn admin tự upload brochure qua UI thay vì chạy script |
| 6 | `introduce_features` (A5-7) dead code — xem mục 1.12 | Chưa ai yêu cầu nối vào graph | Quyết định có cần tính năng "giới thiệu chủ động" hay không trước khi đầu tư thêm |

## 3. Nguyên tắc kiến trúc đã thống nhất (cho việc tiếp theo)

Bối cảnh: nhìn lại 10+ bug thật trong 2 ngày, phần lớn gãy ở **tầng rule** (regex/keyword
match trên free text) chứ không phải tầng LLM hay tầng deterministic (scoring/guardrail).

### 3.1 Ranh giới 2 lớp — không đổi hết, chỉ đổi lớp "hiểu ý"

- **Lớp hiểu ý** (ngôn ngữ tự nhiên → enum đóng) → nên chuyển dần sang LLM: phân loại
  `purpose_bucket`, nhận diện "muốn hỏi thêm tính năng khác", nhận diện loại/giữ mẫu xe.
  Input vô hạn, regex hữu hạn → luôn crack được, chỉ là sớm hay muộn.
- **Lớp quyết định** (enum → hành động có hậu quả thật) → **giữ deterministic, không đụng**:
  scoring/ranking, budget filter, chọn feature phân biệt (`select_discriminating_features`),
  quote gate, guardrail/HITL, claim có evidence. Sai ở đây là sai GIÁ/TÍNH NĂNG BỊA/SAI NHÓM
  SẢN PHẨM — hậu quả thật, không sửa được bằng prompt.
- **Ca ngoại lệ đáng nhớ**: `domain/vehicle_type_inference.py` NHÌN giống "hiểu ý" (suy loại
  xe từ câu nói) nhưng thực chất là **quyết định** — sai loại xe = lọc sai nhóm sản phẩm.
  Đây là rule đã được chốt từ 1 phiên office-hours thật (ngưỡng 188tr/100tr, khoảng trống
  passenger_count=1,2 cố ý), có test khoá từng ca âm — **không nên** chuyển sang LLM.
- Tương tự: chọn feature nào để HỎI (lượt 2) là quyết định (ranking), không phải hiểu ý — dù
  đề xuất ban đầu có ý định giao cho LLM chọn, đã bị gạt lại: giữ
  `select_discriminating_features` deterministic, chỉ nới INPUT (allowlist) của nó.

### 3.2 3 luật hạn chế "crack" — áp cho MỌI bộ phân loại, kể cả LLM

1. **Không có nhánh "phân loại thất bại → treo/lặp vô hạn"**. Mọi bộ phân loại phải có trần
   số lần thử (giống `MAX_ASK_ATTEMPTS`) + fallback rõ ràng khi không quyết được. Đây là chỗ
   crack nguy hiểm nhất — không phải bản thân việc phân loại sai (xem mục 2.4, bug
   `range_clarify_reason` không có trần retry, khác các nhánh khác).
2. **LLM không bao giờ output tự do vào chỗ downstream cần chắc chắn**. Tool schema ép
   `enum: [...]`, LLM chọn 1 trong N, không viết câu tự do rồi code parse lại (quay về đúng
   vấn đề rule).
3. **Ranh giới theo HẬU QUẢ SAI, không theo ĐỘ KHÓ**. Sai gây phiền (hỏi lại, câu cụt) → LLM
   được. Sai gây hậu quả thật (giá sai, tính năng bịa, sai nhóm sản phẩm) → deterministic,
   không đàm phán.

### 3.3 LLM chỉ "diễn đạt lại", không quyết định nội dung

Pattern đã CÓ SẴN và hoạt động đúng ở `synthesis.py`: code tính claim (deterministic), LLM
chỉ sắp câu quanh placeholder, không tự bịa (`reject_unstructured_claims` chặn). Việc hỏi
slot (`slot_planning.py`) hiện CHƯA có LLM — 100% template tĩnh, đây là lý do câu hỏi lặp
nguyên văn khi hết 3 variant. Bước 3 (bên dưới) là mở rộng ĐÚNG pattern này sang chỗ hỏi slot,
không phải kiểu mới.

## 4. Kế hoạch triển khai — theo file, theo thứ tự ưu tiên

### Bước 1 — Mở rộng schema trích xuất (`prompts/slot_extraction_prompts.py`)
- Thêm enum `purpose_bucket` vào tool schema → LLM tự phân loại. `slot_mapping.py::purpose_bucket()`
  (keyword match) lùi thành fallback khi LLM bỏ trống field.
- Thêm giá trị intent mới (`MORE_FEATURES` hoặc tương đương) vào enum `intents` sẵn có → thay
  `domain/feature_followup.py::wants_more_features()` làm nguồn chính, regex lùi fallback.
- **KHÔNG đụng** `domain/vehicle_type_inference.py` (xem mục 3.1).

### Bước 2 — Allowlist lượt 2 đọc DB (`prompts/feature_askable.py`)
- Thay `ASKABLE_FEATURES`/`ALL_ASKABLE` (dict cứng) bằng đọc `feature_definitions` theo
  `vehicle_type` — tái dùng pattern `adapters/feature_vocabulary.py::list_active_features()`.
- **Giữ nguyên** `select_discriminating_features` deterministic — chỉ nới allowlist đầu vào.

### Bước 3 (thấp ưu tiên hơn) — An toàn hoá các nhánh "treo vô hạn" hiện có
- `nodes/ask_or_retrieve.py` nhánh `range_clarify_reason` — thêm trần retry.
- Soát `DECLINED_SLOT_VALUE` chạm parser strict ở đâu chưa guard (mục 2.4).

### Bước 4 — Eval (`eval/datasets/slot_conversations.json` + `scripts/slot_conversation_runner.py`)
- Case đi qua đường LLM-classify mới → đổi kỳ vọng từ so khớp CÂU CHỮ sang so khớp KẾT QUẢ
  (enum/slot/next_group đúng, không phải `expected_question` y nguyên).
- `ScriptedLlm`/fixture cần trả thêm field `purpose_bucket`/intent mới.

### KHÔNG làm (đã cân nhắc, chủ động hoãn/từ chối)
- **Câu hỏi do LLM sinh hoàn toàn** (thay vì template + LLM diễn đạt lại) — thêm 1 lệnh gọi
  LLM/lượt (~1-2s latency), phải làm lại toàn bộ eval (exact-match → semantic-match). Chi phí
  sửa eval CÓ THỂ LỚN HƠN chi phí code — kinh nghiệm thật từ phiên này (mỗi lần đổi wording
  phải regen hàng chục scenario trong golden dataset).
- **LLM router thay `routing.py`** — phá chính bảo đảm mà lớp "quyết định" cần: guardrail/
  quote_gate LUÔN chạy trước khi trả lời, `MAX_RELAX`/`MAX_GUARDRAIL_RETRIES` LUÔN chặn đúng.
  LangGraph conditional edges là structural guarantee; LLM router biến nó thành xác suất. Nên
  coi là "không làm", không phải "để sau".

## 5. Trạng thái test lúc kết thúc phiên

`pytest tests/agents` — 1476 pass. Đúng **9 fail có sẵn từ trước phiên này**, đã xác nhận
KHÔNG liên quan tới mọi thay đổi trong phiên (verify nhiều lần qua các lần chạy):
- `tests/agents/integration/test_brochure_ingestion_integration.py` (3 test)
- `tests/agents/integration/test_comparison_endpoint.py` (3 test)
- `tests/agents/integration/test_graph_boundary.py::test_nodes_do_not_import_sqlalchemy_adapters_or_domain`
  (đã có từ trước — `nodes/ask_or_retrieve.py` import `domain/` trực tiếp, vi phạm rule kiến
  trúc "nodes không import domain"; nhiều node khác trong phiên này — `narrow.py`, `routing.py`
  — cũng theo pattern này, chưa dọn)
- `tests/agents/integration/test_scope_node.py` (2 test)

Ruff sạch trên mọi file đã sửa trong phiên. **Chưa commit gì** — cần review + squash theo git
flow (`feature/tong-hop-uu-dai` → `develop`) trước khi bắt đầu việc mới ở Bước 1-4.

**Server dev**: uvicorn chạy `--reload` (tự nạp code khi lưu file) — nhưng session hội thoại
CŨ trong DB không tự cập nhật câu chữ, phải mở hội thoại MỚI để thấy fix.
