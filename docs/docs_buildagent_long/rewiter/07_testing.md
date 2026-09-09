# Testing

## 1. Kết quả thật (chạy trên máy, `2026-08-18`)

### 1.1 Test mới

```
$ .venv/bin/python -m pytest tests/agents/unit/domain/test_text_normalization.py \
    tests/agents/unit/domain/test_fuzzy_match.py \
    tests/agents/unit/domain/test_rewrite_guards.py \
    tests/agents/unit/domain/test_nlu_confidence.py \
    tests/agents/unit/domain/test_fuzzy_slot_extractors.py \
    tests/agents/unit/services/test_nlu_pipeline.py \
    tests/agents/unit/services/test_pending_intent_confirmation.py \
    tests/agents/integration/test_recognize_intent_node.py \
    tests/agents/unit/domain/test_diacritic_insensitive_keywords.py -q

129 passed in 0.30s
```

### 1.2 Toàn bộ suite — so với baseline

| | Trước (baseline `git stash`) | Sau |
|---|---|---|
| Passed | 2107 | **2226** |
| Failed | **11** | **0** |
| Skipped | 0 | 23 (đều cần Postgres, có lý do rõ ràng) |
| Thời gian | 3:14 | 3:10 |

**Không có hồi quy mới.** Đã xác minh bằng cách stash toàn bộ thay đổi, chạy
baseline, rồi `diff` danh sách `FAILED`:

```
$ diff baseline.txt after.txt
(không khác biệt)
```

11 lỗi có sẵn từ trước đã được xử lý trong một đợt riêng — xem
`08_preexisting_failures.md`. 23 test còn lại là SKIP có chủ đích: chúng cần
Postgres thật và giờ báo skip kèm lý do thay vì đỏ vì thiếu hạ tầng.

### 1.3 Linter

```
$ .venv/bin/python -m ruff check src/agents/ tests/agents/
All checks passed!

$ .venv/bin/python -m mypy src/agents/   # lọc file của tính năng này
0 lỗi
```

(70 lỗi mypy còn lại trong repo đều nằm ở module khác và có sẵn từ trước; 12 lỗi
ruff còn lại nằm ở `src/products/domain/values.py`.)

---

## 2. Cách chạy

```bash
# Chỉ tính năng này
.venv/bin/python -m pytest tests/agents/unit/domain/test_text_normalization.py \
  tests/agents/unit/domain/test_fuzzy_match.py \
  tests/agents/unit/domain/test_rewrite_guards.py \
  tests/agents/unit/domain/test_nlu_confidence.py \
  tests/agents/unit/domain/test_fuzzy_slot_extractors.py \
  tests/agents/unit/services/test_nlu_pipeline.py \
  tests/agents/unit/services/test_pending_intent_confirmation.py \
  tests/agents/integration/test_recognize_intent_node.py \
  tests/agents/unit/domain/test_diacritic_insensitive_keywords.py -v

# Toàn bộ module agents
.venv/bin/python -m pytest tests/agents/ -q

# Migration (cần AGENT_DATABASE_URL)
.venv/bin/python -m pytest tests/agents/integration/test_migrations.py -q
```

**Không test nào cần LLM thật hay mạng.** Lớp 1 dùng `SpyRewriter`/`StubRewriter`
trả JSON cố định; ba lớp còn lại vốn không gọi LLM.

---

## 3. Test case theo lớp

### 3.1 Chuẩn hoá tiếng Việt — 9 test

| Test | Bảo vệ điều gì |
|---|---|
| `precomposed_and_decomposed_forms_normalize_to_the_same_string` | Chữ "ế" có 2 cách mã hoá Unicode; bàn phím tiếng Việt sinh cả hai |
| `strip_diacritics_handles_every_vietnamese_tone` | Kể cả `đ`/`Đ` (chữ cái riêng, NFD không tách) |
| `normalize_drops_punctuation_so_it_does_not_split_tokens` | `"VF5,"` và `"VF5"` phải là một |
| `squash_matches_the_catalog_reader_convention` | Cùng quy ước `adapters/catalog_reader._squash` |
| `digits_from_words_only_converts_standalone_tokens` | `"chính sách pin"` không được thành `"9h sách pin"` |
| +4 test biên (rỗng, tỷ lệ đổi token) | |

### 3.2 Lớp 1 — 16 test

**Cổng giữ ngân sách A4-2:**

| Test | Khẳng định |
|---|---|
| `a_clean_message_never_reaches_the_model` | `"vf5 gia bao nhieu"` → `reason="clean"`, 0 lần gọi |
| `missing_diacritics_alone_is_not_noise` | Thiếu dấu ≠ nhiễu (mọi khớp đều bỏ dấu) |
| `digits_are_always_explained` | `"700 trieu"` không phải từ gõ sai |
| `greetings_are_not_treated_as_noise` | `"chao em"` — câu chào đầu MỌI hội thoại |
| `truncated_tokens_are_the_strongest_noise_signal` | `"tho ti x vf nam"` → `truncated_tokens` |
| `a_single_token_is_never_rewritten` / `a_very_long_message_is_not_rewritten` | Biên |

**Guard chặn sáng tác:**

| Test | Khẳng định |
|---|---|
| `a_heavy_but_legitimate_spelling_fix_is_accepted` | **Ca mẫu** `"tho ti x vf năm"` → `"thông tin xe VF 5"` phải qua được |
| `invented_content_is_rejected` | `"vf5"` → `"VF 5 giá lăn bánh ở Hà Nội bao nhiêu"` bị chặn |
| `vietnamese_number_words_count_as_traceable` | `"năm"` → `"5"` không phải token bịa |
| `low_model_confidence_falls_back_to_the_original` | |
| `the_original_survives_every_rejection_path` | Câu gốc sống qua cả 4 nhánh từ chối |
| `trust_is_highest_when_no_rewrite_was_needed` | |

### 3.3 Lớp 2 — 13 test

| Test | Khẳng định |
|---|---|
| `vietnamese_number_word_resolves_a_model_without_any_llm` | **Ca mẫu**, không cần Lớp 1 |
| `a_bare_brand_token_never_resolves_to_a_model` | A4-1: `"vf"` một mình không ra xe nào |
| `a_short_token_only_matches_exactly` | `"mua"` ≠ `"màu"` |
| `a_short_token_inside_a_multi_word_alias_must_match_exactly` | `"cac xe"` ≠ `"can xe"` (83 điểm) |
| `a_real_typo_inside_a_long_token_still_matches` | `"klaraa"` → `Klara` @91 |
| `rewritten_text_can_only_help_never_hurt` | Rewrite làm hỏng tên xe → câu gốc vẫn thắng |
| `source_span_only_contains_characters_the_customer_wrote` | Không bịa ký tự |
| `custom_catalog_keeps_the_canonical_name_verbatim` | `canonical` dùng để tra catalog |
| +5 test biên/ngưỡng | |

### 3.4 Lớp 3 + 4 — 16 test

| Test | Khẳng định |
|---|---|
| `every_conclusion_carries_the_evidence_that_produced_it` | Nhãn sai truy được về entity gây ra |
| `a_model_name_outranks_a_type_name` | A4-7: tên mẫu > tên loại |
| `evidence_found_only_after_rewriting_is_penalised` | Kết luận đứng trên suy đoán của mô hình |
| `a_pending_slot_takes_absolute_priority` | **Tương thích A7-10** |
| `a_clean_message_is_never_hijacked_by_a_clarifying_question` | **Guard `input_looks_noisy`** |
| `an_active_handoff_silences_the_bot` | **`PENDING_HANDOFF`** |
| `an_active_advisory_flow_silences_the_bot` | **Guard `slot_flow_active`** |
| `a_declined_slot_does_not_count_as_an_active_flow` | `DECLINED_SLOT_VALUE` là ô đã đóng |
| `thresholds_split_the_three_tiers` | Biên 0.85 / 0.60 |
| +7 test khác | |

### 3.5 Pipeline (service) — 17 test

| Test | Khẳng định |
|---|---|
| `a_clean_message_costs_zero_extra_llm_calls` | **Ngân sách A4-2** — spy đếm |
| `a_garbled_message_spends_exactly_one_call` | Đúng 1, không 2 |
| `a_model_outage_still_recognises_the_vehicle` | **Lớp 1 không phải điểm chết duy nhất** |
| `an_unreadable_payload_falls_back_to_the_original` | |
| `a_fenced_json_payload_is_still_read` | LLM hay bọc ```` ```json ```` |
| `the_original_message_is_always_preserved` | |
| `a_medium_confidence_turn_asks_the_customer_to_confirm` | Nhánh CONFIRM + 2 nút |
| `an_unintelligible_message_asks_for_clarification_with_buttons` | PRD 5.9 lối thoát |
| `shadow_mode_keeps_the_logs_but_changes_no_behaviour` | Nút lùi |
| `inverted_thresholds_are_rejected` / `a_broken_threshold_keeps_the_default` | Config hỏng |
| `intent_hint_never_invents_a_label_outside_the_existing_enum` | Không tạo tập nhãn thứ hai |
| +6 test khác | |

### 3.6 Câu xác nhận — 11 test

| Test | Khẳng định |
|---|---|
| `confirming_substitutes_the_message_and_lets_the_turn_continue` | **Không dừng lượt** khi khách gật |
| `denying_ends_the_turn_with_an_open_question` | Không đề xuất suy đoán thứ hai |
| `a_negation_inside_a_longer_sentence_is_not_a_denial` | `"xe không cần sạc nhà"` |
| `an_expired_record_is_cleaned_up_on_read` | TTL, dọn lúc đọc |
| `a_corrupt_payload_is_treated_as_no_record` | Không raise → không chết lượt |
| `a_record_without_a_timestamp_is_treated_as_expired` | Chiều an toàn |
| +5 test khác | |

### 3.7 Bộ trích slot dự phòng (điểm nối 2) — 10 test

| Test | Khẳng định |
|---|---|
| `the_exact_matcher_runs_first_and_its_accuracy_is_unchanged` | Thứ tự là điều kiện an toàn |
| `the_fallback_rescues_a_turn_the_exact_matcher_would_have_dropped` | `"hà nôi"` → `HN` |
| `a_wrong_letter_is_deliberately_left_unresolved` | `"ha nol"` → `None` (sai tỉnh = sai phí) |
| `without_the_fallback_the_old_behaviour_is_preserved` | Không nối → A7-10 chạy y như trước |
| `a_two_letter_code_only_matches_exactly` | `"hm"` không thành `HN` |
| +5 test khác | |

### 3.8 Từ khoá bỏ dấu (bug người dùng báo) — 27 test

| Test | Khẳng định |
|---|---|
| `an_on_road_price_question_is_recognised_with_or_without_diacritics` | **Ca người dùng báo**: `"gia lan banh cua vf 5"` |
| `a_message_with_diacritics_is_matched_strictly` | `"cho"` (giới từ) không được đọc thành `"chỗ"` (ghế) |
| `the_stripped_path_matches_on_word_boundaries` | `"o to"` không nằm trong `"cho toi"` |
| `a_family_compound_is_not_read_as_a_price_question` | `"gia đình"` ≠ câu hỏi giá |
| `a_real_price_question_still_wins_over_a_nearby_compound` | Câu hỏi thật vẫn thắng |
| `a_plain_list_price_question_is_not_an_on_road_question` | Giá niêm yết ≠ giá lăn bánh |
| +21 test tham số hoá (thuộc tính, TCO, trả góp) | |

### 3.9 Node trong graph thật — 10 test

| Test | Khẳng định |
|---|---|
| `a_garbled_message_reaches_slot_extraction_already_fixed` | Điểm nối 4 |
| `the_state_still_carries_the_original_message` | Câu gốc sống đến cuối lượt |
| `an_unintelligible_message_stops_the_turn_with_a_question` | Nhánh CLARIFY rẽ END, **`extract_slots` không chạy** |
| `the_clarify_branch_never_claims_a_human_is_involved` | **Không đụng `awaiting_review`/`terminal_reason`** |
| `an_active_advisory_flow_is_never_interrupted` | |
| `an_active_handoff_is_never_interrupted` | |
| `shadow_mode_leaves_behaviour_identical_to_before_the_feature` | |
| `an_unwired_pipeline_leaves_the_turn_exactly_as_before` | `AGENT_ENABLED=false` |
| `a_pipeline_failure_falls_back_to_the_original_message` | Lỗi hạ tầng không vỡ lượt |

---

## 4. Hai bug do chính test phát hiện

### 4.1 Guard Lớp 1 từ chối chính ca mẫu

`test_token_change_ratio_counts_new_tokens_against_the_original_length` cho thấy
`"vf5 gia bao nhieu"` → `"VF 5 giá bao nhiêu"` đổi **50%** token. Kiểm tiếp:

```python
evaluate_rewrite(original='tho ti x vf năm', rewritten='thông tin xe VF 5', confidence=0.95)
# applied=False, reason='rewrote_too_much'   ← ca mẫu bị chính guard chặn
```

→ Đổi thước đo từ **token ĐỔI** sang **token BỊA**. Xem `01_layer1_rewrite.md` §4.

### 4.2 Bảng từ khoá mù với câu thiếu dấu (bug CÓ SẴN, người dùng báo)

`"gia lan banh cua vf 5"` — chỉ thiếu dấu, không sai chính tả — trả về bảng
thông số thay vì giá lăn bánh:

```python
classify_pricing_intent('gia lan banh cua vf 5')   # NONE  (phải là ON_ROAD_PRICE_LOOKUP)
classify_query_attribute('vf5 gia bao nhieu')      # UNKNOWN (phải là PRICE)
```

→ Thêm `contains_keyword` với quy tắc "câu có dấu thì khớp chặt, câu không dấu
thì bỏ dấu + ranh giới từ". Xem `06_assumptions_and_risks.md` §A4.

### 4.3 `RewriteServiceImpl(rewriter=None)` tắt âm thầm cả Lớp 4

Nhánh `rewriter is None` return trước khi tính `rewrite_trigger`, nên
`input_looks_noisy` luôn `False` → mọi câu bị coi là sạch → hai nhánh hỏi lại
**không bao giờ chạy** mà không dòng log nào cho biết.

→ Chuyển `rewrite_trigger` lên trước nhánh tắt. Hàm thuần và rẻ, không tốn lần
gọi LLM nào.

---

## 5. Ca đã kiểm thủ công (chạy trên code đã merge)

| Input | Tier | Confidence | Intent | Entity |
|---|---|---:|---|---|
| `tho ti x vf năm` | AUTO | 0.985 | CATALOG_LOOKUP | VF 5, OVERVIEW |
| `VF5 giá bao nhiêu` | AUTO | 1.000 | CATALOG_LOOKUP | VF 5, PRICE |
| `vf 8 có mấy chỗ ngồi` | AUTO | 1.000 | CATALOG_LOOKUP | VF 8, SEAT_COUNT |
| `klaraa gia bao nhieu` | AUTO | 1.000 | CATALOG_LOOKUP | Klara@91, PRICE |
| `so sanh vf6 va vf7` | AUTO | 1.000 | CATALOG_LOOKUP | VF 6, VF 7 |
| `cho tôi xem các xe máy điện` | AUTO | 0.900 | CATALOG_BROWSE | CATALOG_BROWSE |
| `e can tv x cho gd 5 ng` | AUTO | 0.873 | ADVISORY | ADVISORY |
| `chào em` | AUTO | 0.000 | — | (câu sạch → không hỏi lại) |
| `700 triệu` | AUTO | 0.000 | — | (số → không nhiễu) |
| `hà nội` | AUTO | 0.000 | — | (tỉnh → không nhiễu) |
| `zxcv qwer asdf` | **CLARIFY** | 0.000 | — | — |

---

## 6. Khoảng trống test — chưa phủ

| Khoảng trống | Vì sao | Rủi ro |
|---|---|---|
| **LLM thật** | Test dùng stub | Chất lượng prompt chưa đo — xem `06_*.md` A4 |
| **E2E qua HTTP** | Cần Postgres | `TurnResponse.quick_replies` chưa test qua route thật |
| **Migration `agent_0019`** | Cần `AGENT_DATABASE_URL` | `upgrade`/`downgrade` chưa chạy thật; test head đã cập nhật |
| **Tải/p95** | Cần môi trường tải | Xem `06_*.md` A1 |
| **`handoff_active=True` thật** | State machine chưa tồn tại | Đã test ở mức đơn vị bằng cờ; xem `06_*.md` A2 |
