# Giả định và rủi ro còn tồn đọng

> Mọi mục dưới đây cần Long xác nhận hoặc test kỹ trước khi merge lên nhánh
> chung. Xếp theo mức độ nghiêm trọng.

---

## PHẦN A — Rủi ro cần xử lý trước khi bật thật

### A1. [CAO] Ngân sách LLM-call của A4-2 giờ phụ thuộc tỷ lệ input nhiễu

`docs/vinfast-agent-mvp.md` §A4-2 chốt **"lượt hỏi slot ≤ 1 lần gọi LLM, lượt đề
xuất đầy đủ ≤ 3"** và có test spy canh con số đó. Lớp 1 nằm **trước**
`extract_slots`, nên hợp đồng đó giờ phải đọc là:

> lượt hỏi slot ≤ 1 lần gọi LLM **nếu không trigger rewrite**; ≤ 2 nếu có.

**Đã làm để kiểm soát:** cổng `rewrite_trigger` rule-based, câu sạch tốn 0 lần
gọi thêm. Có test khoá (`test_a_clean_message_costs_zero_extra_llm_calls`).

**Còn phải làm:**
1. Đo tỷ lệ lượt bị trigger trên traffic thật (chạy `NLU_ROUTING_ENABLED=false`
   để thu log mà không đổi hành vi).
2. Đo lại p95 trên tập có tỷ lệ câu nhiễu thực tế, không phải tập sạch cũ.
3. Cập nhật con số trong `docs/vinfast-agent-mvp.md` §A4-2 và báo cáo A9-3.

**Khuyến nghị:** bật shadow-mode ít nhất một tuần trước khi bật routing thật.

### A2. [CAO] Ownership state machine `AI → PENDING_HANDOFF → HUMAN → AI` CHƯA TỒN TẠI

**[GIẢ ĐỊNH]** Đã grep toàn `src/`: không có enum hay cột nào mang nghĩa "ai đang
sở hữu hội thoại". Thứ gần nhất:
- `awaiting_review: bool` — cờ của **một lượt**, không sống qua lượt;
- `review_queue.status` — trạng thái của **một mục duyệt**, không phải của phiên;
- `DeliveryAction.ADVISOR_HANDOFF` — quyết định của một lượt.

**Đã làm:** `chain._handoff_active()` viết theo hình dạng nó SẼ có — dò qua
`getattr(conversation, "load_handoff_state", None)`. Chưa ai cài method đó nên
**luôn trả `False`**, tức hành vi y như hiện tại. `route_confidence` đã có nhánh
`handoff_active` và **test đã khoá nó lại**.

**Còn phải làm:** khi state machine thật được dựng, nối vào là **một hàm**
(`ConversationService.load_handoff_state`), không phải sửa Lớp 4.

**Rủi ro nếu bỏ qua:** trong khi chưa có state machine, một khách đang chờ tư vấn
viên mà gửi tin nhắn gõ hỏng vẫn có thể nhận câu hỏi làm rõ của bot. Ba guard còn
lại (`slot_flow_active`, `input_looks_noisy`, shadow-mode) thu hẹp ca này rất
nhiều nhưng **không đóng hẳn**.

### A3. [TRUNG BÌNH] Mở rộng viết tắt không phân biệt được với bịa nội dung bằng khoảng cách ký tự

Lớp 1 **được yêu cầu** mở rộng viết tắt (`"gd"` → `"gia đình"`). Nhưng
`rapidfuzz.ratio("gd", "gia")` chỉ được **40 điểm** — không khoảng cách ký tự nào
tách được "mở rộng viết tắt hợp lệ" khỏi "bịa từ mới".

**Đã làm:** nới `MAX_TOKEN_CHANGE_RATIO` lên `0.5` và **không** dựa vào nó làm
rào chắn chính. Rào chắn thật là bốn lớp khác:
1. `MAX_TOKEN_GROWTH = 2.0` — cấu trúc, không phải ký tự. Bắt được cả hai ca bịa
   trong test.
2. Sàn confidence của mô hình (`0.70`).
3. Bản rewrite **chỉ** đi vào `extract_slots` — guardrail A6-1 và audit A7-4 vẫn
   đọc câu gốc.
4. Lớp 2 vẫn phải khớp entity với catalog thật.

**Còn phải làm:** soi log `reason="invented_content"` và `reason="rewrote_too_much"`
sau một tuần chạy thật để xem có chặn nhầm ca hợp lệ nào không.

### A4. [ĐÃ SỬA] Bảng từ khoá mù với câu thiếu dấu

**Bug quan sát trên hệ thống thật:** khách gõ `"gia lan banh cua vf 5"` — chỉ
thiếu dấu, **không sai chính tả nào** — và nhận về bảng thông số đầy đủ kèm giá
niêm yết 496 triệu, trong khi họ hỏi giá **lăn bánh**. Đó không phải trả lời
thiếu mà là trả lời **sai** một con số nhỏ hơn thực tế hàng chục triệu (thiếu
phí trước bạ, biển số, bảo hiểm).

**Bug này CÓ SẴN, không do bốn lớp mới gây ra.** Nguyên nhân: mọi bảng từ khoá
chỉ `casefold()` chứ không bỏ dấu, nên `"lan banh"` không bao giờ khớp
`"lăn bánh"`. Bốn lớp mới nhận diện đúng câu này ở Lớp 2, nhưng **không có gì ở
downstream tiêu thụ kết quả đó** — `classify_pricing_intent` (A7-9) và
`classify_query_attribute` vẫn tự khớp trên chuỗi thô.

Dấu hiệu bug đã tồn tại từ trước: `_CUSTOM_FINANCING_KEYWORDS` có **cả**
`"kỳ hạn"` lẫn `"ky han"` — ai đó đã vá tay đúng một từ khoá cho ca không dấu
rồi dừng.

**Đã sửa:** thêm `domain/text_normalization.contains_keyword` và dùng ở cả hai
hàm phân loại.

**Quy tắc — điểm tinh tế nhất:** bỏ dấu **vô điều kiện** hỏng theo hướng nặng
hơn, vì tiếng Việt có những cặp từ chỉ khác nhau ở dấu mà **đều rất thông dụng**:

| Cặp | Hậu quả nếu bỏ dấu vô điều kiện |
|---|---|
| `"chỗ"` (ghế) ↔ `"cho"` (giới từ) | *"giá bao nhiêu **cho** gia đình tôi"* → đọc thành câu hỏi số **chỗ** ngồi |
| `"giá"` (tiền) ↔ `"gia"` (gia đình) | *"hợp với **gia** đình không"* → đọc thành câu hỏi **giá** |

Nên quy tắc là **khách gõ có dấu thì tin dấu họ gõ**:

- Câu **CÓ** dấu → khớp chặt, giữ nguyên dấu = **đúng hành vi cũ**, không lượt
  nào đang chạy bị đổi kết quả.
- Câu **KHÔNG** dấu → khớp trên dạng bỏ dấu, theo **ranh giới từ** (chuỗi con
  nguy hiểm hơn hẳn sau khi bỏ dấu: `"o to"` nằm trong `"cho toi"`).

Người ta gõ tiếng Việt theo một trong hai kiểu nhất quán. Câu có dấu mà một từ
không mang dấu thì đó là chủ ý, không phải gõ sót.

**Còn phải làm:** rà các bảng từ khoá còn lại chưa chuyển sang `contains_keyword`
— `domain/catalog_browse` (đã tự có ranh giới từ nhưng chưa bỏ dấu),
`domain/intent_reconciliation` (regex đã có sẵn biến thể không dấu cho phần lớn
cue), `domain/quote_risk.detect_risk_flags`.

### A5. [TRUNG BÌNH] Chưa test với LLM thật

Toàn bộ test Lớp 1 dùng stub trả JSON cố định. Chất lượng thật của prompt
(`prompts/rewrite_prompts.py`) trên `gpt-4o-mini` **chưa đo**.

**Còn phải làm:** chạy bộ ~30 câu gõ hỏng thật qua LLM thật, đo tỷ lệ
`applied` / `low_confidence` / `invented_content`. Nếu tỷ lệ `applied` thấp thì
vấn đề ở prompt, không ở guard.

---

## PHẦN B — Giả định đã đánh dấu `[GIẢ ĐỊNH]` trong code

### B1. Danh mục xe dùng seed tĩnh, chưa đọc DB

`domain/entity_catalog.SEED_CAR_MODELS` / `SEED_MOTORBIKE_MODELS`.

**Vì sao:** prompt triển khai yêu cầu *"file cấu hình tĩnh trước, DB sau"*.
`default_catalog(vehicle_names=...)` **đã nhận sẵn tham số**, nên nối DB về sau
là một dòng ở `composition.py`, không phải một thiết kế khác.

**Rủi ro:** thêm mẫu xe mới vào catalog mà quên cập nhật seed → Lớp 2 không nhận
ra tên xe đó. Tra cứu vẫn chạy (nhánh cũ), chỉ mất khả năng khớp mờ.

**Xử lý khi cần:** `CatalogReadAdapter` thêm `list_vehicle_display_names()`, cache
trong tiến trình (KHÔNG query mỗi lượt — sẽ cộng round-trip DB vào p95).

### B2. `VF e34` vẫn nhận diện được dù không còn trong catalog

**Cố ý.** Khách hỏi một xe đã ngừng bán thì câu trả lời đúng là "mẫu này không
còn trong danh mục hiện hành" (nhánh `unmatched_mentions` của A4-1 đã làm sẵn),
chứ không phải im lặng coi như khách chưa nêu tên xe nào.

### B3. Bảng `INTENT_KEYWORDS` tách khỏi `intent_reconciliation`

**Cố ý, không phải trùng lặp bỏ sót.** `intent_reconciliation` là bộ hoà giải
nhãn cuối cùng, chạy trên câu đã sạch, và vẫn là **nguồn sự thật duy nhất** của
`state["intents"]`. Bảng ở `entity_catalog` chỉ đo "câu này trông giống ý định
nào" trên câu **còn nhiễu**, phục vụ tính confidence.

**Rủi ro:** hai bảng có thể lệch nhau theo thời gian. **Giảm thiểu:**
`intent_hint` không bao giờ ghi vào `state["intents"]`, nên lệch chỉ ảnh hưởng
confidence, không ảnh hưởng nhãn cuối cùng.

### B4. `COMMON_WORDS` chưa phủ hết tiếng Việt đời thường

`domain/rewrite.COMMON_WORDS` — gom từ cách hỏi thường gặp.

- **Thiếu một từ** → một câu sạch bị đưa đi rewrite (tốn 1 lần gọi LLM, kết quả
  vẫn đúng).
- **Thừa một từ** → bỏ sót câu cần sửa.

Chiều an toàn nằm về phía "thiếu". Đã phải thêm nhóm chào hỏi
(`chao/alo/cam/on/...`) sau khi phát hiện `"chào em"` bị chấm là nhiễu.

### B5. Ngưỡng số — toàn bộ là phỏng đoán khởi đầu

| Hằng số | Giá trị | Ghi chú |
|---|---:|---|
| `DEFAULT_AUTO_THRESHOLD` | 0.85 | Theo yêu cầu nghiệp vụ |
| `DEFAULT_CONFIRM_THRESHOLD` | 0.60 | Theo yêu cầu nghiệp vụ |
| `DEFAULT_SINGLE_TOKEN_SCORE` | 85 | Chưa hiệu chuẩn |
| `DEFAULT_MULTI_TOKEN_SCORE` | 80 | Chưa hiệu chuẩn |
| `DEFAULT_WEAK_FLOOR` | 70 | Chưa hiệu chuẩn |
| `MIN_FUZZY_LENGTH` | 4 | Chưa hiệu chuẩn |
| `MIN_TOKEN_TRACE_SCORE` | 60 | Chưa hiệu chuẩn |
| `MAX_TOKEN_GROWTH` | 2.0 | Chưa hiệu chuẩn |
| `SLOT_MATCH_THRESHOLD` | 88 | Cao hơn Lớp 2 — sai tỉnh = sai phí trước bạ |
| `WEIGHT_*` (7 trọng số) | — | Chưa hiệu chuẩn |

Cùng tinh thần với `domain/quote_risk.py`: *"phải tinh chỉnh bằng số liệu
shadow-mode trước khi coi là chốt"*. Chín ngưỡng đầu chỉnh được qua **biến môi
trường**, không phải sửa code. Bảy trọng số thì chưa.

### B6. `POPULAR_MODEL_SUGGESTIONS` là phỏng đoán theo dải giá

Không có cột doanh số nào trong catalog để xếp hạng. Khi có dữ liệu bán hàng
thật thì thay bằng truy vấn, không phải sửa logic.

### B7. Hợp đồng API quick-reply chưa thống nhất với FE

**[GIẢ ĐỊNH]** Hình dạng `{label, value}` là tối thiểu và **chưa có tài liệu hợp
đồng nào** giữa BE-FE.

**Giảm thiểu đã làm:** `value` là chuỗi gửi lại như tin nhắn bình thường qua
chính `POST /agent/turn` — không endpoint mới, và client chưa hỗ trợ nút bấm vẫn
dùng được (khách tự gõ "đúng" cho kết quả y hệt).

**Cần Long xác nhận với FE trước khi bật `NLU_ROUTING_ENABLED=true`.**

### B8. `FUZZY_FALLBACK_EXTRACTORS` chỉ có `province`

Vì `DEFAULT_EXTRACTORS` của A7-10 cũng chỉ có `province` — không slot nào khác
từng được dựng thành pending. Thêm slot mới vào pending thì thêm một dòng.

### B9. TTL và số lần hỏi lại của câu xác nhận

- `CONFIRMATION_TTL` = **dùng chung** `PENDING_TTL` (15 phút) của A7-10: hai bản
  ghi cùng trả lời một câu hỏi bot vừa đặt.
- `MAX_CONFIRMATION_TURNS = 1` — hỏi xác nhận đúng một lần. Hỏi lại lần hai câu
  "ý anh/chị là VF 5 phải không" không thêm thông tin nào cho khách.

---

## PHẦN C — Sai khác so với `plan_intent_recognition.md`

| Plan | Thực tế | Vì sao |
|---|---|---|
| Ngưỡng 0.75 / 0.45 | **0.85 / 0.60** | Prompt triển khai chỉ định rõ |
| Guard "đổi > 40% token" | **Đếm token BỊA** | Guard theo plan **từ chối chính ca mẫu** — phát hiện bằng test, xem `01_layer1_rewrite.md` §4 |
| Chỉ node graph | **+ điểm nối thứ hai** vào `PendingSlotServiceImpl` | Rủi ro #5 của plan thành hiện thực |
| — | **+ guard `input_looks_noisy`** | Không có nó thì "chào em" bị CLARIFY cướp lượt |
| — | **+ guard `slot_flow_active`** | Không có nó thì "700 triệu" bị CLARIFY cướp lượt |
| Lớp 2 chỉ ngưỡng % | **+ luật token ngắn khớp tuyệt đối** | "cac xe" khớp mờ "can xe" ở 83 điểm |
| `EntityMatch` là Pydantic | **dataclass frozen** | Value object nội bộ, không validate từ payload ngoài — cùng khuôn `PendingSlotRequest` |
| Không nêu | **+ 2 method A7-10 vào `SessionRepository` port** | Bản cài đặt đã có, chỉ Protocol bị sót nên mypy không kiểm được |

---

## PHẦN D — Việc bàn giao cho team

| Task | Ảnh hưởng | Hành động |
|---|---|---|
| **A9-2** (E2E đóng băng) | Mọi input mẫu giờ đi qua thêm một node | Đã xác nhận toàn bộ 2107 test cũ giữ nguyên kết quả. Nếu thêm case E2E mới, kiểm nó rơi vào tier `AUTO`. |
| **A9-3** (KPI, p95, ngân sách LLM) | **Nặng nhất** | Xem A1. Phải đo lại và cập nhật hợp đồng số lần gọi LLM. |
| **A9-1** (`funnel_metrics`) | Không bắt buộc | Nếu muốn đo "% lượt bị hỏi lại vì hiểu nhầm", cần event log riêng đếm `nlu_confidence_tier != AUTO`. Việc của A9, không phải của plan này. |
| **A7-1/2/3** (review_queue) | **Không đổi** | Plan này không tạo mục `review_queue` nào. Node `recognize_intent` không bao giờ ghi `awaiting_review` — có test khoá. |
| **A8-*** (booking, lịch sử, notice) | **Không đổi** | Nằm sau toàn bộ pipeline này trong luồng nghiệp vụ. |
| **Frontend** | Cần biết | `TurnResponse.quick_replies` — xem B7. |
| **DevOps** | Cần biết | Migration `agent_0019` + 9 biến môi trường mới (đều có mặc định an toàn). |
