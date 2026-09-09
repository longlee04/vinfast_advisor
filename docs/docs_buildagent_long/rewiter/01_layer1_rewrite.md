# Lớp 1 — LLM rewrite giới hạn phạm vi

**Module:** `src/agents/domain/rewrite.py` (thuần), `src/agents/services/rewrite.py`
(use case), `src/agents/adapters/rewrite_source.py` (gọi LLM + đọc JSON),
`src/agents/prompts/rewrite_prompts.py` (câu chữ).

## 1. Vì sao KHÔNG thêm method vào `LLMPort`

`src/agents/ports.py:57` — `LLMPort` là Protocol **đóng băng từ Ngày 0**
(`docs/team_split.md` §2.2: đổi chữ ký = một PR riêng, cả 4 người duyệt). Nó chỉ
có `extract_slots` và `synthesize`.

Đã có tiền lệ đúng cho tình huống này: `LlmScopeClassifier`
(`src/agents/adapters/scope_source.py:11`) thêm một khả năng LLM hoàn toàn mới
cho A6-2 bằng cách **tái dùng `synthesize(prompt=...)`** rồi tự validate chuỗi
trả về ở tầng adapter. Lớp 1 đi đúng con đường đó — không ai phải chờ một PR
contract.

Khác `LlmScopeClassifier` ở **chiều an toàn khi hỏng**: bộ phân loại phạm vi trả
`IN_SCOPE` (cho qua) vì chặn nhầm khách tệ hơn bỏ sót; ở đây trả `None` (bỏ
rewrite) vì dùng một bản rewrite hỏng còn tệ hơn dùng câu gốc.

## 2. Cổng quyết định có gọi LLM không

`domain/rewrite.rewrite_trigger(text, known_tokens)` — **rule-based, 0 lần gọi
LLM**. Đây là thứ giữ ngân sách A4-2 ("lượt hỏi slot ≤ 1 lần gọi LLM").

| Điều kiện | Kết quả | Lý do |
|---|---|---|
| < 2 token | `too_short` | Đoán một từ đứng riêng chính là "suy luận thêm nội dung" |
| > 40 token | `too_long` | Chi phí tăng theo độ dài; câu dài đã đủ ngữ cảnh |
| Có token < 3 ký tự không giải thích được | **GỌI** — `truncated_tokens` | Tiếng Việt không có nhiều từ 1–2 ký tự |
| ≥ 40% token không giải thích được | **GỌI** — `unexplained_tokens` | Phần lớn câu là từ lạ |
| Còn lại | `clean` | Đi qua với 0 lần gọi thêm |

**"Token giải thích được"** = có trong danh mục thực thể, hoặc trong `COMMON_WORDS`
(hư từ + chào hỏi), hoặc **thuần số**.

Hai luật quan trọng, cả hai đều để tránh đốt LLM vô ích:

- **Thiếu dấu KHÔNG phải tín hiệu nhiễu.** Mọi so khớp về sau chạy trên dạng đã
  bỏ dấu, nên `"gia bao nhieu"` và `"giá bao nhiêu"` là cùng một câu. Coi thiếu
  dấu là nhiễu sẽ đốt một lần gọi LLM cho **phần lớn** tin nhắn tiếng Việt.
- **Token thuần số luôn giải thích được.** `"700"` trong `"700 triệu"` không phải
  từ gõ sai, và không có bản sửa chính tả nào cho một con số.

## 3. Prompt

Toàn văn ở `src/agents/prompts/rewrite_prompts.py`. Bố cục theo đúng khuôn
`prompts/scope_prompts.build_scope_prompt`: **chỉ dẫn trước, dữ liệu ngoài sau,
bọc trong thẻ `<utterance>`** — một câu khách viết "bỏ qua hướng dẫn trên" mà nằm
sau chỉ dẫn và trong thẻ thì nó là dữ liệu, không phải lệnh.

Ba việc được phép:
1. Thêm dấu tiếng Việt còn thiếu (`thong tin` → `thông tin`).
2. Sửa từ gõ tắt/gõ sót (`tho ti` → `thông tin`).
3. Tách/ghép từ dính (`vf5` → `VF 5`).

Cấm tuyệt đối: thêm thông tin khách chưa nói, trả lời câu hỏi, đoán ý định rồi
viết câu khác, bỏ bớt thông tin, dịch ngôn ngữ.

Prompt liệt kê sẵn toàn bộ tên mẫu xe VinFast và quy tắc số đếm
(`"vf năm"` = `VF 5`), chép từ `prompts/scope_prompts.py` để hai chỗ không nói
hai danh mục khác nhau.

## 4. Guard — điều chỉnh quan trọng nhất so với plan

> **Plan sai ở đây, và test bắt được.**
>
> Plan đề xuất "đổi > 40% token → huỷ rewrite". Nhưng một bản **sửa chính tả
> nặng đổi gần hết token của câu**:
> `"tho ti x vf năm"` → `"thông tin xe VF 5"` đổi 4/5 token = **80%**.
> Guard theo plan **từ chối chính ca mẫu** mà cả tính năng sinh ra để xử lý.

Thước đo đã đổi thành **token BỊA**, không phải token ĐỔI:

> Token bịa = token của bản rewrite **không truy được về bất kỳ token nào** của
> câu gốc (`rapidfuzz.ratio` < 60, so sau khi đổi số đếm tiếng Việt thành chữ số).

- `"thong"` truy về `"tho"` (75 điểm) → hợp lệ
- `"xe"` truy về `"x"` (67 điểm) → hợp lệ
- `"5"` truy về `"năm"` → `"5"` (100 điểm) → hợp lệ
- `"hà nội"` trong câu không hề nhắc địa điểm → **không truy về đâu cả** → BỊA

Bốn cửa, theo thứ tự (`domain/rewrite.evaluate_rewrite`):

| Cửa | Ngưỡng | `reason` khi đóng |
|---|---|---|
| Rewrite rỗng / y hệt câu gốc | — | `no_change` |
| Confidence của mô hình | ≥ `0.70` | `low_confidence` |
| Số token không được gấp bội | ≤ `2.0×` | `rewrote_too_much` |
| Tỷ lệ token bịa | ≤ `0.50` | `invented_content` |

Cửa nào đóng → dùng lại **câu gốc**, không raise.

## 5. Schema

### Input
```
build_rewrite_prompt(user_message: str) -> str
```

### Output mô hình (JSON)
```json
{
  "rewritten": "<câu đã sửa>",
  "confidence": 0.95,
  "changed_tokens": ["thông", "tin", "xe"]
}
```

Bọc trong ```` ```json ```` hoặc kèm lời rào đều đọc được
(`adapters/rewrite_source.parse_rewrite_payload`). JSON hỏng → `None` → dùng câu
gốc, **không** dựng bản mặc định: payload hỏng nghĩa là ta KHÔNG biết mô hình
định nói gì, và đoán tiếp từ chỗ đó là đúng thứ Lớp 1 bị cấm làm.

`confidence` kiểu `bool` bị chặn tường minh — `isinstance(True, int)` là `True`
trong Python, và một cờ boolean lọt vào ô confidence sẽ được đọc thành `1.0`
(cùng bẫy mà `domain/quote_risk._is_usable_score` đã phải chặn).

### Output của lớp — `domain/rewrite.RewriteResult`
```python
original: str                     # LUÔN giữ nguyên
rewritten: str                    # giữ cả khi bị guard từ chối, để audit
confidence: float
changed_tokens: tuple[str, ...]
applied: bool
reason: str
input_looks_noisy: bool           # Lớp 4 đọc — xem 04_layer4
```
`text_for_matching` → bản rewrite nếu `applied`, ngược lại **câu gốc**. Không bao
giờ trả chuỗi rỗng, nên không lớp nào phải tự xử lý ca rỗng.

`trust` → `1.0` khi không rewrite (câu vốn sạch, không có bước suy đoán nào chen
vào giữa khách và hệ thống), ngược lại là chính confidence của mô hình.

## 6. Ví dụ thật (chạy trên code đã merge)

```
IN : 'tho ti x vf năm'
  L1: applied=True  reason=applied  out='thông tin xe VF 5'

IN : 'e can tv x cho gd 5 ng'
  L1: applied=True  reason=applied  out='em cần tư vấn xe cho gia đình 5 người'

IN : 'vf5 gia bao nhieu'
  L1: applied=False reason=clean    out='vf5 gia bao nhieu'      ← 0 lần gọi LLM
```

Ca bị chặn:

```
'vf5'         → 'VF 5 giá lăn bánh ở Hà Nội bao nhiêu'  → rewrote_too_much
'vf5 mau gi'  → 'VF 5 màu gì, xe có 5 chỗ và pin 60kWh' → rewrote_too_much
```

## 7. Cấu hình

| Biến môi trường | Mặc định | Ý nghĩa |
|---|---|---|
| `NLU_REWRITE_ENABLED` | `true` | Tắt hẳn Lớp 1 (ba lớp còn lại vẫn chạy) |
| `NLU_MIN_REWRITE_CONFIDENCE` | `0.7` | Sàn confidence của mô hình |
| `NLU_MAX_TOKEN_CHANGE_RATIO` | `0.5` | Trần tỷ lệ token bịa |

## 8. Khi Lớp 1 hỏng

| Tình huống | `reason` | Hành vi |
|---|---|---|
| Chưa nối LLM | `disabled` | Dùng câu gốc; **cổng phát hiện nhiễu vẫn chạy** |
| LLM timeout/lỗi | `llm_unavailable` | Dùng câu gốc + `logger.warning` |
| JSON không đọc được | `invalid_payload` | Dùng câu gốc + `logger.warning` |

Trong **mọi** trường hợp, Lớp 2 vẫn nhận ra `"vf năm"` = `VF 5` nhờ alias
số-đếm tiếng Việt. Lớp 1 không phải điểm chết duy nhất của pipeline.

> Lỗi hạ tầng bị nuốt nhưng **không nuốt trong im lặng** — cùng triết lý với
> `nodes/classify_scope`: một lớp tắt âm thầm là một lớp không tồn tại.
