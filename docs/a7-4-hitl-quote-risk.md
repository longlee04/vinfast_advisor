# A7-4 — Tối giản HITL: chỉ chặn báo giá có rủi ro thực sự

Ghi chú kèm PR. Phần cuối liệt kê **toàn bộ [GIẢ ĐỊNH]** cần chỉnh lại bằng số liệu
thực nghiệm sau khi chạy shadow-mode.

## Vấn đề

Luồng cũ chặn theo **loại thao tác**: cạnh `ask_or_retrieve --lookup--> enqueue_hitl`
trong `graph.py` đưa mọi lượt đọc catalog vào hàng đợi duyệt. Tra giá niêm yết hay hỏi
số chỗ ngồi — thứ không mang rủi ro nào — cũng phải chờ người.

## Chính sách mới

Chặn theo **rủi ro của nội dung sắp gửi khách**. Một báo giá bị chặn khi có ≥1 trong 5
yếu tố: cá nhân hoá, thương lượng, ưu đãi ngoài chính sách chuẩn, cam kết tài chính,
confidence dưới ngưỡng. Giá niêm yết sinh deterministic từ catalog đi thẳng tới khách.

Quyết định là **rule-based, không gọi LLM** (`domain/quote_risk.py`) và **default-deny**:
chỉ đúng một đường dẫn tới auto-approve, và nó đòi mọi điều kiện an toàn bật tường minh.
Mọi field `None`/hỏng đều tính là rủi ro.

## Thay đổi chính

| Thành phần | File |
| --- | --- |
| `QuoteEvaluation`, `requires_sync_hitl()`, nhận diện rủi ro, tier | `src/agents/domain/quote_risk.py` |
| Use case: config, shadow-mode, audit | `src/agents/services/quote_gate.py` |
| Node điều phối (≤15 câu lệnh, không nghiệp vụ) | `src/agents/nodes/quote_gate.py` |
| Rẽ nhánh | `src/agents/routing.py`, `src/agents/graph.py` |
| DTO / port | `src/agents/contracts.py`, `src/agents/ports.py` |
| Ghi audit (transaction riêng + task nền) | `src/agents/adapters/unit_of_work.py`, `src/agents/adapters/quote_audit.py` |
| Bảng `quote_audit_log` | `migrations/agents/versions/agent_0010_quote_audit_log.py` |

### Điểm gắn vào graph

```
route_intent → quote_gate → (hitl → enqueue_hitl | continue → ask_or_retrieve)
ask_or_retrieve --lookup--> END          # trước đây: --lookup--> enqueue_hitl
guardrail --pass--> draft_quote_gate → (hitl → enqueue_hitl | continue → END)
```

Cổng đặt **trước** `ask_or_retrieve` chứ không phải sau: câu "anh giảm cho em 20 triệu"
không kèm tên xe sẽ rẽ vào nhánh `ask` và được đáp bằng một câu hỏi slot nếu cổng đứng
sau — đúng quy trình tư vấn nhưng bỏ qua hẳn phần cần người quyết định.

`draft_quote_gate` giữ nguyên cam kết A7-1: bản nháp qua LLM có
`is_deterministic_standard=False` nên **luôn** vào hàng đợi duyệt. Cạnh `continue` vẫn
khai tường minh để chính sách nằm ở một chỗ duy nhất; và
`route_after_draft_quote_gate` chỉ thả khi có `False` tường minh — quên wiring cũng là
chặn, không phải thả.

### Audit bất đồng bộ

Mọi quyết định của cổng (kể cả auto-approve) ghi `quote_audit_log`: input, `QuoteEvaluation`
phẳng hoá, output, lý do chặn, và **kết quả luồng cũ trên cùng lượt**. Ghi qua
`asyncio.create_task` nên không cộng vào thời gian khách chờ; sink hỏng thì log rồi đi
tiếp, không bao giờ làm chết lượt.

- `sampled_for_review`: chọn ngẫu nhiên trong các case auto-approve để người phụ trách
  đọc định kỳ (log thì 100%, cờ này chỉ chọn phần phải đọc).
- `near_threshold`: confidence trong `[THRESHOLD - MARGIN, THRESHOLD)` — gắn cờ **kể cả
  khi đã bị chặn**, vì đó chính là tập dữ liệu để biết hạ ngưỡng tới đâu thì còn an toàn.
- Lượt không phải báo giá **và** không chạm dữ liệu (khách vừa trả lời một câu hỏi slot)
  không được đếm: cả hai luồng đều cho đi thẳng, đếm vào chỉ làm loãng mẫu số KPI.

### Shadow-mode

`ShadowComparison` đếm trong process (`total`, `legacy_blocked`, `new_blocked`,
`released_by_new_policy`, `release_rate`); cột `legacy_requires_hitl` trong
`quote_audit_log` cho cùng số liệu ở mức bền vững, dùng cho báo cáo A9:

```sql
SELECT count(*) FILTER (WHERE legacy_requires_hitl AND NOT requires_hitl)::float
       / NULLIF(count(*) FILTER (WHERE legacy_requires_hitl), 0) AS release_rate
FROM quote_audit_log;
```

### Feature flag

| Biến môi trường | Mặc định | Tác dụng |
| --- | --- | --- |
| `QUOTE_RISK_POLICY_ENABLED` | `true` | `false` → lùi hẳn về luồng cũ (chạm dữ liệu là chặn) |
| `QUOTE_HITL_SHADOW_MODE` | `true` | Gắn cờ `shadow_mode` trên dòng audit; tắt khi đã đủ dữ liệu |
| `QUOTE_HITL_CONFIDENCE_THRESHOLD` | `0.85` | Ngưỡng confidence |
| `QUOTE_HITL_NEAR_THRESHOLD_MARGIN` | `0.10` | Độ rộng dải cận ngưỡng |
| `QUOTE_AUDIT_SAMPLE_RATE` | `0.10` | Tỷ lệ case auto-approve gắn cờ review định kỳ |
| `QUOTE_STANDARD_PROMOTIONS` | rỗng | Danh sách ưu đãi đã duyệt, phân tách bằng dấu phẩy |

Giá trị gõ sai (không phải số, ngoài `[0,1]`) bị bỏ qua và giữ mặc định — một biến môi
trường sai chính tả không được lặng lẽ hạ ngưỡng an toàn về 0.

## Test

- `tests/agents/unit/domain/test_quote_risk.py` — 36 test cho quy tắc default-deny.
- `tests/agents/unit/services/test_quote_gate.py` — audit, sampling, dải cận ngưỡng,
  shadow counters, feature flag, config hỏng.
- `tests/agents/integration/test_quote_gate_flow.py` — toàn luồng qua `run_turn`.

Sáu case bắt buộc ở đặc tả đều có test riêng, cộng thêm các case biên đáng ngờ:
confidence đúng bằng ngưỡng (được phép), `True` lọt vào ô confidence (`isinstance(True, int)`
là `True` trong Python — không chặn tường minh thì nó thành 1.0 và mở cửa auto-approve),
và ưu đãi nằm trong bảng đã duyệt (không phải "ngoài chính sách chuẩn").

## [GIẢ ĐỊNH] — cần chỉnh bằng số liệu thực nghiệm

1. **`CONFIDENCE_THRESHOLD = 0.85`** — phỏng đoán khởi đầu. Dùng cột `near_threshold`
   của `quote_audit_log` sau shadow-mode để tìm ngưỡng thật. **Ưu tiên số một khi tune.**
2. **`AUDIT_SAMPLE_RATE = 0.10`** — 10% case auto-approve gắn cờ review định kỳ. Chọn
   theo năng lực đọc của người phụ trách, chưa có căn cứ.
3. **`NEAR_THRESHOLD_MARGIN = 0.10`** — dải `[0.75, 0.85)`.
4. **`STANDARD_PROMOTIONS` rỗng** — mọi lời nhắc tới khuyến mãi hiện bị coi là ngoài
   chính sách chuẩn. Chiều an toàn (thà chặn nhầm một ưu đãi hợp lệ còn hơn để agent tự
   hứa một ưu đãi không tồn tại), nhưng **sẽ chặn thừa** cho tới khi phòng kinh doanh
   chốt bảng ưu đãi và đổ tên chương trình vào biến này.
5. **Nguồn `confidence_score`** — pipeline hiện **chưa có** điểm tin cậy nào ở bước trích
   slot (`ExtractedSlots` không mang field đó) và `SynthesisService.synthesize` chỉ trả
   chuỗi. Nên: nhánh catalog suy confidence từ độ trọn vẹn của việc resolve tên xe
   (resolve sạch → `1.0`; còn tên mập mờ/không khớp trong một câu có giá → `0.70`, dưới
   ngưỡng, vì báo giá kèm một mẫu xe chưa xác định là báo nhầm giá). Nhánh bản nháp để
   `None` (chiều an toàn; nhánh đó vốn luôn chặn). Khi A2-3/A5-6 trả confidence thật thì
   thay nguồn này.
6. **Bộ từ khoá nhận diện rủi ro** (`_NEGOTIATION_PATTERNS` và ba bộ còn lại) — khớp từ
   khoá tiếng Việt có dấu, ưu tiên bắt nhầm hơn bỏ sót. Cần siết lại bằng log thật.
   Đáng chú ý: **"giá lăn bánh"** bị xếp vào `is_personalized` (là số tính riêng theo
   tỉnh/phí trước bạ, không phải giá niêm yết) — cụm này rất phổ biến nên sẽ đẩy khá
   nhiều lượt vào HITL; kiểm lại tỷ lệ này trước tiên khi đọc số liệu shadow-mode.
7. **Ranh giới "không phải báo giá"** — tra thông số/tồn kho/so sánh xe không đi qua
   `requires_sync_hitl()` (đặc tả mục 3, gạch đầu dòng 3). Dấu hiệu nhận biết đang dùng:
   nội dung sắp gửi không chứa con số giá nào **và** lời khách không chạm 4 chủ đề rủi ro.
8. **"giá xe VF3 bao nhiêu"** — đặc tả mô tả case này hai chỗ hơi lệch nhau (mục 3 nói
   catalog lookup có giá thì build `QuoteEvaluation` rồi gọi `requires_sync_hitl()`; mục 6
   nói nó "không đi qua `requires_sync_hitl`"). Bản này theo mục 3: lượt có giá **được
   đánh giá** và ra `False` → `tier=DETERMINISTIC_AUTO`, khách nhận giá ngay trong lượt.
   Kết quả quan sát được ("trả lời ngay, không ai phải duyệt") giống hệt cách đọc kia;
   chỉ lượt **không có giá** mới thật sự không đi qua hàm quyết định (`tier=NON_QUOTE`).
9. **Audit chạy nền trong process** (`asyncio.create_task`) — dự án chưa có message
   broker. Đủ cho quy mô hiện tại; khi cần bền hơn thì đổi `BackgroundQuoteAuditSink`
   sang hàng đợi thật, `QuoteAuditPort` không phải đổi.
