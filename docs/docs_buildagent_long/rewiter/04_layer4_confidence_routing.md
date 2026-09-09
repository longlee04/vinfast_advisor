# Lớp 4 — Confidence routing

**Module:** `src/agents/domain/nlu_confidence.py` (`route_confidence`),
`src/agents/services/nlu_pipeline.py` (dựng câu trả lời),
`src/agents/domain/pending_intent_confirmation.py` + service cùng tên (vòng đời
câu xác nhận), `src/agents/prompts/nlu_replies.py` (câu chữ).

**Không gọi LLM.** Câu chữ là template deterministic — cùng lý do với
`domain/catalog_browse.py`: nội dung ghép từ chính thứ hệ thống vừa nhận ra, nên
không mang khẳng định sự thật nào cần kiểm chứng, và A7-4 cho đi thẳng tới khách.

## 1. Bảng ngưỡng

| Tier | Điều kiện | Hành vi | Biến môi trường |
|---|---|---|---|
| `AUTO` | `confidence ≥ 0.85` | Đi tiếp vào `extract_slots` với **câu đã sửa** | `NLU_AUTO_THRESHOLD` |
| `CONFIRM` | `0.60 ≤ confidence < 0.85` | Hỏi xác nhận + 2 quick-reply, lưu `pending_intent_confirmation`, kết thúc lượt | `NLU_CONFIRM_THRESHOLD` |
| `CLARIFY` | `confidence < 0.60` | Hỏi làm rõ + nút bấm gợi ý mẫu xe phổ biến, kết thúc lượt | — |

`NLU_CONFIRM_THRESHOLD > NLU_AUTO_THRESHOLD` bị **từ chối, giữ mặc định** kèm
`logger.warning`: đảo ngưỡng thì dải "xác nhận" biến mất và mọi câu lửng lơ rơi
thẳng xuống nhánh hỏi làm rõ — một cấu hình vô nghĩa mà không ai nhận ra.

## 2. Bốn lối tắt bắt buộc trả `AUTO`

`route_confidence` trả `AUTO` **ngay, không xét ngưỡng**, khi bất kỳ điều nào
sau đây đúng. Cả bốn đều là ràng buộc tương thích ngược, không phải tính năng.

### 2.1 `handoff_active` — `PENDING_HANDOFF`

Phiên đang chờ NGƯỜI xử lý. Khách vừa được báo *"em đã chuyển sang tư vấn viên
hỗ trợ ạ"* mà lượt sau lại nhận *"ý anh/chị là gì ạ?"* thì hai câu phủ định
nhau, và câu sau **xoá mất** câu trước. Lượt vẫn chạy tiếp như cũ để luồng HITL
giữ nguyên quyền quyết định.

### 2.2 `slot_flow_active` — đang giữa cuộc tư vấn

> Guard quan trọng nhất về mặt hồi quy.

Bot hỏi *"ngân sách khoảng bao nhiêu ạ?"*, khách đáp *"700 triệu"*. Câu đó
**không khớp entity nào** trong ba danh mục — không tên xe, không thuộc tính,
không từ khoá intent — nên confidence rơi về 0 và nhánh CLARIFY sẽ cướp lượt,
trả lại *"em chưa nắm rõ ý anh/chị"* cho một câu trả lời hoàn toàn rõ ràng.

`advisory_flow_active(known_slots)` dùng **cùng tập slot** với
`intent_reconciliation._has_active_advisory_context` — hai chỗ hỏi cùng một câu
hỏi ("phiên này đã bắt đầu tư vấn chưa") nên phải cùng một câu trả lời.
`DECLINED_SLOT_VALUE` **không** tính: nó đánh dấu một ô đã đóng, không phải
thông tin đã thu được.

### 2.3 `resolved_via_pending_slot` — đang trả lời một slot cụ thể

Xem `03_layer3_intent_classifier.md` §6.

### 2.4 `not input_looks_noisy` — câu sạch

Bốn lớp này sinh ra để cứu input **bị nhiễu**. Một câu sạch không khớp entity
nào không phải câu gõ hỏng — nó chỉ là câu mà bảng keyword tĩnh không phủ:
`"chào em"`, `"tôi muốn mua xe"`, `"cho tôi hỏi chút"`. Những câu đó đã có
`classify_scope` (A6-2, nhãn `SOCIAL`) và `extract_slots` xử lý bằng LLM, tốt
hơn hẳn một bảng keyword.

Bỏ guard này thì **câu chào đầu tiên của mọi cuộc hội thoại** nhận về "em chưa
nắm rõ ý anh/chị" — hồi quy nặng hơn hẳn vấn đề đang đi sửa.

Cờ này đến từ `RewriteResult.input_looks_noisy`, do cổng rule-based
`rewrite_trigger` đặt. Nó **vẫn được tính kể cả khi Lớp 1 tắt** — nếu không, tắt
Lớp 1 sẽ báo "mọi câu đều sạch" và tắt âm thầm luôn hai nhánh hỏi lại.

## 3. Shadow-mode — nút lùi một bước

`NLU_ROUTING_ENABLED=false`: bốn lớp **vẫn chạy và vẫn ghi log đầy đủ**, nhưng
tier luôn `AUTO` nên hành vi hệ thống y hệt trước khi có tính năng này. Dùng để
thu số liệu tinh chỉnh ngưỡng trước khi bật thật — cùng khuôn với
`QuoteGateConfig.shadow_mode_enabled` của A7-4.

## 4. Nhánh CONFIRM — vòng đời câu xác nhận

### 4.1 Lượt N — bot hỏi

```
answer:        "Dạ, có phải anh/chị đang hỏi về VF 5 không ạ?"
quick_replies: [{"label": "Đúng rồi",   "value": "đúng"},
                {"label": "Không phải", "value": "không phải"}]
```

Câu hỏi nêu **đúng thứ vừa hiểu**, không hỏi chung chung: *"anh/chị nói rõ hơn
được không ạ"* vứt bỏ thông tin vừa suy ra và bắt khách gõ lại.

Đồng thời ghi `conversation_sessions.pending_intent_confirmation`:
```json
{"proposed_text": "thông tin xe VF 5", "intent_hint": "CATALOG_LOOKUP",
 "vehicle_names": ["VF 5"], "confidence": 0.72,
 "asked_at": "...", "turn_count": 0}
```

`proposed_text` phải lưu vì lượt sau khách chỉ gõ "đúng" — câu đó không mang nội
dung nào để chạy lại pipeline.

### 4.2 Lượt N+1 — khách trả lời

Xử lý ở `chain._resume_intent_confirmation`, **TRƯỚC `graph.ainvoke`** — cùng vị
trí và cùng lý do với A7-10: `"đúng rồi"` đứng riêng cũng là một tin nhắn hai
chữ mà `classify_scope` sẽ gắn `OUT_OF_SCOPE` rồi kết thúc lượt.

| Khách trả lời | Kết cục |
|---|---|
| `"đúng"`, `"vâng"`, `"ok"`, `"chuẩn"`… | **Thay** câu "đúng" bằng `proposed_text`, **lượt chạy tiếp toàn bộ pipeline** |
| `"không phải"`, `"sai"`, `"ko"`… | Kết thúc lượt bằng câu hỏi làm rõ MỞ |
| Câu khác | Bỏ bản ghi, câu mới chạy pipeline thường |
| Quá 15 phút | Bỏ bản ghi (dọn ngay lúc đọc, không cần cron) |

**Khác A7-10 ở kết cục quan trọng nhất:** khách xác nhận thì lượt **KHÔNG dừng**.
Dừng ở đây sẽ khiến khách gật đầu xong không nhận được gì.

Khi khách phủ nhận, bot hỏi bằng câu **MỞ**, không đề xuất tiếp một suy đoán thứ
hai từ cùng bộ bằng chứng vừa bị bác — bằng chứng không đổi thì suy đoán thứ hai
cũng sai theo đúng kiểu đó.

`read_confirmation` so khớp trên **TOÀN BỘ** câu đã chuẩn hoá, không tìm chuỗi
con: `"không"` nằm trong `"cho tôi xem xe không cần sạc nhà"`, và đọc câu đó
thành lời phủ nhận sẽ vứt mất nội dung khách vừa cung cấp.

## 5. Nhánh CLARIFY

```
answer:        "Dạ em chưa nắm rõ ý anh/chị. Anh/chị cho em xin tên mẫu xe cần
                tra cứu, hoặc mô tả nhu cầu (số người thường chở, ngân sách,
                quãng đường mỗi ngày) để em tư vấn giúp ạ.

                Anh/chị cũng có thể chọn nhanh một mẫu đang được quan tâm:"
quick_replies: [{"label": "VF 3", "value": "VF 3"}, ... ]
```

PRD 5.9 đòi mọi câu từ chối phải kèm **lối thoát**; một danh sách mẫu xe bấm được
là lối thoát rẻ nhất cho khách.

Danh sách gợi ý được **lọc theo danh mục đang có** — gợi ý một mẫu xe không còn
trong catalog thì khách bấm vào sẽ nhận "chưa tìm thấy mẫu này": một lối thoát
dẫn vào ngõ cụt còn tệ hơn không có lối thoát nào.

## 6. Hai cơ chế confidence KHÔNG xung đột

| | `nlu_confidence` (Lớp 4) | `quote_risk.CONFIDENCE_THRESHOLD` (A7-4) |
|---|---|---|
| Đo | Độ chắc chắn **hiểu đúng ý khách** | Độ tin cậy **dữ liệu của một báo giá** |
| Ngưỡng | 0.85 / 0.60 | 0.85 |
| State | `nlu_confidence`, `nlu_confidence_tier` | `quote_tier`, `delivery_action`, `quote_requires_hitl` |
| Module | `domain/nlu_confidence.py` | `domain/quote_risk.py` |
| Chạy khi nào | Node ĐẦU graph | Sau `route_intent` và sau `guardrail` |

Trùng con số 0.85 là **ngẫu nhiên**. Hai field riêng, hai module riêng, không
đường nào đọc chéo.

**Ràng buộc cứng:** node `recognize_intent` **không bao giờ** ghi
`awaiting_review` hay `terminal_reason`.

- `awaiting_review = True` nghĩa CHÍNH XÁC là "đã tạo một mục trong `review_queue`
  chờ TƯ VẤN VIÊN duyệt" (`chain.py:183`).
- `terminal_reason` nghĩa là "guardrail đã chặn nội dung" (A6-1).

Tái dùng chúng cho một câu hỏi mà **chính bot vừa đặt và tự trả lời được** sẽ
dựng màn "đang chờ tư vấn viên" trên một lượt hoàn toàn tự động. Có test khoá:
`test_the_clarify_branch_never_claims_a_human_is_involved`.

## 7. Hợp đồng API

`TurnResponse` (`src/agents/api/routes.py`) thêm **một** field:

```json
{
  "answer": "Dạ, có phải anh/chị đang hỏi về VF 5 không ạ?",
  "pending_question": null,
  "awaiting_review": false,
  "quick_replies": [
    {"label": "Đúng rồi", "value": "đúng"},
    {"label": "Không phải", "value": "không phải"}
  ]
}
```

`quick_replies` **rỗng ở mọi lượt khác**, nên client cũ không đổi gì vẫn chạy
đúng như trước.

`value` là chuỗi client gửi lại như một **tin nhắn bình thường** qua chính
`POST /agent/turn` — không phải mã lệnh riêng. Nên không cần endpoint mới, và
client chưa hỗ trợ nút bấm vẫn dùng được: khách đọc câu hỏi rồi tự gõ "đúng" cho
kết quả y hệt.

**[GIẢ ĐỊNH]** Hình dạng `{label, value}` là tối thiểu và chưa thống nhất với
FE — xem `06_assumptions_and_risks.md`.

## 8. Bảng cấu hình đầy đủ

| Biến | Mặc định | Lớp |
|---|---|---|
| `NLU_ROUTING_ENABLED` | `true` | 4 (shadow-mode) |
| `NLU_AUTO_THRESHOLD` | `0.85` | 4 |
| `NLU_CONFIRM_THRESHOLD` | `0.60` | 4 |
| `NLU_REWRITE_ENABLED` | `true` | 1 |
| `NLU_MIN_REWRITE_CONFIDENCE` | `0.70` | 1 |
| `NLU_MAX_TOKEN_CHANGE_RATIO` | `0.50` | 1 |
| `NLU_FUZZY_SINGLE_TOKEN_SCORE` | `85` | 2 |
| `NLU_FUZZY_MULTI_TOKEN_SCORE` | `80` | 2 |
| `NLU_FUZZY_WEAK_FLOOR` | `70` | 2 |

Giá trị hỏng hoặc ngoài dải → **giữ mặc định** kèm `logger.warning`, cùng khuôn
với `services/quote_gate._env_float`: một biến gõ sai không được lặng lẽ đẩy
ngưỡng nhận diện về 0 — ở mức đó mọi câu đều "đủ tin cậy" và cả bốn lớp trở
thành trang trí.
