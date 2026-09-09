# Multi-slot extraction — ghi chú cho PR

## Thay đổi kiến trúc

Gộp form tư vấn xe thành một schema duy nhất, tách dialogue manager khỏi
extraction, và thêm trần số lần hỏi cho từng field.

| Thành phần | File | Vai trò |
|---|---|---|
| `VehicleInquiryForm`, `SlotAnswer`, `get_next_missing_field` | `src/agents/domain/inquiry_form.py` | Schema tổng hợp + chọn field kế tiếp, thuần logic |
| `QUESTION_VARIANTS`, `get_question_variant` | `src/agents/prompts/question_variants.py` | 3 biến thể/slot, chống lặp y nguyên khi hỏi lại |
| `generate_question_for_field` | `src/agents/services/question_generation.py` | Cá nhân hoá optional, fallback về template khi lỗi |
| `next_field`, `question_for`, `MAX_ASK_ATTEMPTS` | `src/agents/services/slot_planning.py` | Bỏ qua field đã hỏi quá 2 lần |
| `AskTrackingServiceImpl` | `src/agents/services/conversation.py` | Đếm số lần hỏi, bền vững qua các lượt |
| `slot_ask_attempts` | `migrations/agents/versions/agent_0009_slot_ask_attempts.py` | Bảng lưu đếm |

## Lý do

Bug gốc là vòng lặp vô hạn khi khách nói "tiền không thành vấn đề". Khi đo trên
103 hội thoại thật, nguyên nhân **không** phải single-slot extraction — extraction
đã là multi-slot sẵn:

```
'tôi muốn mua ô tô điện 5 chỗ' → slots={vehicle_type: CAR, passenger_count: 5}
```

Ba nguyên nhân thật, đã sửa trước PR này:

1. `ask_or_retrieve` coi `intents=[]` là "chưa rõ khách muốn gì" rồi hỏi lại câu
   định tuyến, xoá sạch tiến độ. Câu trả lời cho câu hỏi của agent gần như luôn
   về với intent rỗng, nên vòng lặp không có lối ra. Chiếm 42% số lượt agent nói.
2. `NO_BUDGET_LIMIT_VND` đúng bằng `10^11`, tràn cột `NUMERIC(14,3)`, mọi lượt
   "bao nhiêu cũng được" đều vỡ ở INSERT.
3. `NO_BUDGET_LIMIT_PATTERN` thiếu chính cụm "tiền không thành vấn đề".

PR này xử lý phần UX còn lại mà ba fix trên không chạm tới: agent lặp **nguyên
văn** câu hỏi, và không bao giờ bỏ cuộc với một field khách không trả lời được.

## Danh sách [GIẢ ĐỊNH]

1. **Không thay `dict[SlotName, SlotValue]` ở tầng lưu trữ.** `VehicleInquiryForm`
   là view có kiểu, có `from_slots`/`to_slots`. Prompt yêu cầu giữ tên field cũ để
   không phá downstream, mà `slot_mapping`, `recommendation`, `slot_policy` và
   toàn bộ repository đều đọc dict đó.
2. **Tên là `SlotAnswer`, không phải `SlotValue`.** `SlotValue` đã là union nguyên
   thuỷ trong `domain/values.py`, bị hàng chục module import. Trùng tên gây nhầm
   lẫn im lặng.
3. **`vehicle_type` giữ `VehicleType` (CAR / ELECTRIC_MOTORBIKE)** thay vì
   `Literal["gasoline","electric","hybrid"]`: catalog chỉ có xe điện.
4. **Slot văn bản tự do (`purpose`, `habit_need_tags`) không bọc `SlotAnswer`** —
   `kind` của chúng luôn là exact/unknown nên bọc không thêm thông tin.
5. **Template tĩnh cho chống-lặp, không dùng LLM rewrite** — thêm một call mỗi
   lượt chỉ để đổi cách nói là đánh đổi tệ về độ trễ và chi phí.
6. **Biến thể [0] giữ nguyên văn câu cũ** để thay đổi chỉ ảnh hưởng hành vi hỏi lại.
7. **Cá nhân hoá chỉ bật cho `budget_max_vnd`, `purpose`, `habit_need_tags`** —
   các slot có ngữ cảnh đáng nhắc; bật tràn lan sẽ cộng một LLM call vào gần như
   mọi lượt.
8. **`MAX_ASK_ATTEMPTS = 2`**, đếm là "số lần ĐÃ hỏi" nên bỏ qua khi `count > MAX`,
   tức không có lần hỏi thứ 4.
9. **`AskTrackingService` tách khỏi `ConversationService`.** Phiên/slot là NỘI DUNG
   khách nói; đếm số lần hỏi là hành vi của agent. Tách ra cũng khiến `None` nghĩa
   là "tắt tính năng", không bắt mọi test double phải cài thêm 3 method.
10. **Đếm lưu ở DB, không ở bộ nhớ.** Mỗi lượt là một request riêng; giữ trong
    process thì lượt sau luôn thấy 0 và trần retry không chặn được gì.
11. **Quá trần thì GHI giá trị "mở" thật vào slot**, không chỉ bỏ qua khi chọn câu
    hỏi — `require_complete`/`build_criteria` đọc slot từ DB.
12. **Giá trị "mở" của ngân sách là số (`NO_BUDGET_LIMIT_VND`), của slot khác là
    `DECLINED_SLOT_VALUE`** — `to_filter_criteria` so ngân sách với giá xe nên
    sentinel dạng chuỗi sẽ vỡ ở tầng lọc.

## Test

- `tests/agents/unit/domain/test_inquiry_form.py` — multi-slot 1 câu, single-slot
  không ghi đè, open-ended budget, round-trip giữ hình dạng downstream.
- `tests/agents/unit/services/test_question_generation.py` — 3 lần hỏi ra 3 câu
  khác nhau, biến thể đầu không đổi, hết biến thể không lỗi index, trần retry,
  fallback khi personalize raise/trả rỗng.
- `tests/agents/integration/test_ask_attempt_cap.py` — đếm sống qua nhiều lượt,
  quá trần thì ghi giá trị mở, lấp được field thì đếm về 0. **Cần PostgreSQL.**
