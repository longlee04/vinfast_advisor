# A7-5 — Không đánh giá lại khi khách chỉ xác nhận báo giá cũ

Ghi chú kèm PR. Nối tiếp [A7-4](a7-4-hitl-quote-risk.md).

## Bug

Mọi lượt đều chạy lại toàn bộ pipeline đánh giá báo giá. Một lượt xác nhận ("ok
xe có vẻ được đấy") không mang thông tin nào, nên mọi cờ `QuoteEvaluation` dựng
được đều `None` — và `None` theo default-deny của A7-4 là **rủi ro**. Kết quả:
một lời khen bị đẩy sang tư vấn viên duyệt.

**Biểu hiện đo được trên codebase này nhẹ hơn mô tả, cùng gốc.** Chạy thật trước
khi sửa, lượt xác nhận **không** bị chặn HITL: `quote_gate` xếp nó vào
`NON_QUOTE` (không có giá trong câu trả lời, không cờ rủi ro nào) nên nó đi tiếp,
rồi rơi xuống `ask_or_retrieve` và bị hỏi lại slot từ đầu:

```
>>> vf3 giá bao nhiêu
    VinFast VF 3 All New: giá niêm yết từ 270.750.000 đồng…
>>> ok xe có vẻ được đấy
    Xe thường chở mấy người anh/chị nhỉ?      ← mất ngữ cảnh
```

Cùng một nguyên nhân gốc: hệ thống không phân biệt "lượt mang yêu cầu mới" với
"lượt xác nhận thứ vừa gửi".

## Cách sửa

**Không dựng subsystem history mới.** Mở rộng state phiên đã có và thêm một bước
phân loại rule-based, không tốn thêm lần gọi LLM nào.

| Thành phần | File |
| --- | --- |
| `TurnType`, `ACK_PATTERNS`, `classify_turn()` | `src/agents/domain/turn_classification.py` |
| `FormState` (view gom form + retry + bộ nhớ báo giá) | `src/agents/domain/inquiry_form.py` |
| Nhánh acknowledgment ở cổng | `src/agents/services/quote_gate.py` |
| Câu dẫn bước tiếp theo (template) | `src/agents/prompts/next_step.py` |
| Nạp/ghi bộ nhớ báo giá | `src/agents/chain.py` |
| 2 cột `last_quote_evaluation` / `last_quote_sent_at` | `migrations/agents/versions/agent_0011_session_quote_memory.py` |

Bộ nhớ nằm trên `conversation_sessions` chứ không phải bảng mới: đó đã là nguồn
sự thật của phiên (mục 6.9). Cũng **không** đọc lại từ `quote_audit_log` — audit
ghi bất đồng bộ nên lượt kế tiếp có thể tới trước khi dòng audit kịp commit, mà
điều khiển luồng thì không được phụ thuộc vào bản ghi có thể chưa có.

Nhánh mới trong graph: `quote_gate --answered--> END`. Lượt xác nhận trả lời
ngay tại cổng, không chảy tiếp vào chuỗi hỏi slot.

Kết quả sau khi sửa (chạy thật):

```
>>> vf3 giá bao nhiêu       → VinFast VF 3 All New: giá niêm yết từ 270.750.000 đồng…
>>> ok xe có vẻ được đấy    → Dạ vâng anh/chị ạ. Em có thể đặt lịch lái thử…
>>> ok                      → (như trên)
>>> được đấy                → (như trên)
>>> có màu đỏ không         → Anh/chị dự tính khoảng bao nhiêu…   ← vẫn là yêu cầu mới
```

## Một chỗ cố ý lệch khỏi thiết kế trong đặc tả

Đặc tả đặt `has_new_info = form_before != form_after` làm dấu hiệu **đầu tiên**.
Chạy thật cho thấy dấu hiệu đó không dùng được nguyên như vậy: **bước trích slot
bằng LLM ghi ra slot mà khách chưa từng nói.**

```
>>> ok xe có vẻ được đấy   slots: {} → {'vehicle_type': 'CAR'}        (vì có chữ "xe")
>>> được đấy               slots: {…} → {…, 'passenger_count': 5}     (câu không có số nào)
```

Tin vào delta form thì đúng hai câu xác nhận điển hình nhất đều bị đọc thành yêu
cầu mới, và bug còn nguyên. Nên thứ tự cuối cùng đọc các dấu hiệu **lấy thẳng từ
lời khách** trước, rồi mới tới delta form:

1. có dấu hỏi / từ để hỏi → `NEW_REQUEST`
2. có động từ nêu nhu cầu ("muốn", "cần", "cho em xem"…) → `NEW_REQUEST`
3. có chữ số → `NEW_REQUEST`
4. khớp whitelist xác nhận → `ACKNOWLEDGMENT`
5. form đổi → `NEW_REQUEST`
6. câu rất ngắn → `ACKNOWLEDGMENT`
7. còn lại → `NEW_REQUEST` (mặc định an toàn)

Delta form vẫn xét **trước** độ dài câu, đúng yêu cầu của mục 5: "7 chỗ" ngắn
nhưng lấp được slot.

> Việc extractor bịa `passenger_count=5` từ "được đấy" là một bug **riêng** của
> bước trích slot, nằm ngoài phạm vi PR này. A7-5 chỉ ngừng phụ thuộc vào nó.

## Không bao giờ reset bộ nhớ

Nhánh acknowledgment trả `evaluation_to_remember=None`, và `chain.run_turn` chỉ
ghi database khi field đó khác `None`. Không có nhánh nào ghi `None` xuống
`last_quote_evaluation`. Nhờ vậy xác nhận bao nhiêu lượt liên tiếp cũng không
làm mất đánh giá gốc — mất nó chính là cách bug tái sinh. Có test riêng cho việc
này (4 lượt xác nhận liên tiếp).

Lượt xác nhận khi báo giá cũ **đang chờ duyệt** trả `requires_hitl=False` nhưng
với câu đáp khác: tư vấn viên đã có đúng nội dung đó trên bàn, đẩy thêm một mục
nữa cho một tiếng "ok" chỉ làm hàng đợi dài ra.

## Test

- `tests/agents/unit/domain/test_turn_classification.py` — 20 test, gồm cả hai ca
  extractor bịa slot ở trên.
- `tests/agents/integration/test_quote_acknowledgment.py` — 7 test trên `run_turn`:
  bug gốc, ack khi đang chờ duyệt, câu hỏi tiếp theo, câu ngắn nhưng là câu hỏi,
  nhiều ack liên tiếp không mất state, và ack khi chưa có báo giá nào.

## [GIẢ ĐỊNH] cần tinh chỉnh theo log thật

1. **`ACK_PATTERNS`** — whitelist tối thiểu (17 cụm). Bổ sung khi log lộ biến thể mới.
2. **`SHORT_TURN_MAX_CHARS = 15`** — ngưỡng "câu rất ngắn thì coi là xác nhận".
3. **`_REQUEST_MARKERS`** — động từ nêu nhu cầu, dùng để tách "ok" khỏi "ok em
   muốn xe chở được nhiều đồ". Ưu tiên bắt nhầm sang `NEW_REQUEST`.
4. **`_QUESTION_MARKERS`** — từ để hỏi tiếng Việt; khớp theo chuỗi con nên có thể
   bắt nhầm ở từ ghép. Chiều bắt nhầm là chiều an toàn.
5. **Chỉ giữ báo giá GẦN NHẤT**, không giữ lịch sử cả phiên — đủ để một lượt xác
   nhận biết nó đang xác nhận cái gì.
6. **`next_step_reply()` dùng template, không gọi LLM** — câu này không chứa con
   số và không phụ thuộc ngữ cảnh sâu, một lần gọi LLM chỉ thêm độ trễ và thêm
   một chỗ có thể bịa. Đổi thân hàm được, chữ ký giữ nguyên.
7. **Chỉ báo giá THẬT mới được ghi nhớ** (`is_quote=True`). Lượt tra thông số
   không ghi đè bộ nhớ, nếu không tiếng "ok" sau đó sẽ xác nhận nhầm thứ khác.
