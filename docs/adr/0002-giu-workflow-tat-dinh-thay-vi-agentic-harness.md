# ADR 0002 — Giữ workflow tất định, vá lỗi routing thay vì chuyển sang agentic harness

**Ngày:** 2026-09-22 · **Trạng thái:** đã chọn hướng đi (Phương án A) — **chưa lên kế hoạch triển khai chi tiết** · **Loại:** quyết định kiến trúc, dựa trên phân tích đọc code, không có thay đổi code nào đi kèm ADR này

## Bối cảnh

Đề xuất ban đầu: đổi harness hiện tại (workflow cố định: LLM rewrite → fuzzy entity
match rapidfuzz → intent classification → confidence-based routing → tool/handler)
sang **agentic loop** (LLM tự lập kế hoạch, tự chọn/kết hợp tool, quan sát kết quả
rồi quyết định bước tiếp theo), với lý do quan sát được: bot không xử lý tốt các
câu tham chiếu ngữ cảnh, câu meta, câu ngắn/viết tắt, và team đang phải vá bằng
rule-base liên tục cho từng case.

### Ba case log thật dùng làm bằng chứng

**Case 1 — hai lượt liên tiếp, log từ bot đang chạy:**

- Lượt 1: `"vf5 có giá bao nhiêu"` → bot trả bảng chi phí VF 5 All New, tiêu đề nổi
  bật nhất là **"Chi phí sử dụng 5 năm — 536.533.000 đồng"** (không phải giá xe/giá
  lăn bánh), câu dẫn kết bằng *"...hay anh/chị muốn xem chi phí 5 năm trước?"* dù
  bảng vừa hiển thị đúng con số đó.
- Lượt 2: `"tôi vừa hỏi cái j đấy"` → bot trả lời như thể mở hội thoại mới
  (*"Để em gợi ý mẫu phù hợp nhất... mình dự tính khoảng bao nhiêu, mua xe để dùng
  vào việc gì..."*), không nhắc lại được câu hỏi/đáp án của lượt 1.

**Case 2 — tham chiếu thay thế:**

- `"tôi muốn tư vấn xe A"` → bot tư vấn A → `"xe khác đi"` → bot không hiểu là xin
  xem mẫu thay thế A, route sai hoặc rơi fallback.

**Case 3 — tổng quát:** câu ngắn, viết tắt, thiếu dấu, tham chiếu ngược ("cái đó",
"rẻ hơn", "so với con kia"), câu meta, đổi ý giữa chừng — team vá bằng rule-base
liên tục, mỗi case mới lại thêm một pattern/regex.

## Khảo sát hiện trạng (tóm tắt các phát hiện chính)

### Lõi thật khác `ARCHITECTURE.md`

`ARCHITECTURE.md` mô tả lõi LangGraph 20-node — **tài liệu này đã lỗi thời**.
Ngày 2026-08-31, đội đã **xoá hoàn toàn** lõi v1 (`src/agents/chain.py`, từ
~3.900 dòng còn 77 dòng wrapper mỏng) theo lệnh "Sếp", chuyển 100% production
sang **core v2** — một pipeline 7 bước, quyết định bằng bảng luật thuần Python,
**không LLM ở bước quyết định**, và **không đi qua LangGraph**
(`src/agents/chain.py:1-14`, `src/agents/core/run_turn.py:103`). Lý do xoá,
ghi trong `ARCHITECTURE.md`: agent tự trị "chọn đường khác nhau giữa các lần
chạy nên không tái lập được E2E đóng băng (A9-2) và không truy vết được từng
con số".

### Luồng 1 tin nhắn (core v2)

`api/routes.py` → `chain.run_turn` (wrapper) → `core/run_turn.py` (7 bước, một
transaction ghi duy nhất):

1. Nạp `CoreState` từ Postgres (`_load_state`) + chiếu ownership (`_project_ownership`).
2. Kiểm duyệt trước khi text vào transcript.
3. `understand()` — **đúng một call LLM/lượt** (`core/understand.py`), nhận
   transcript **6 tin nhắn gần nhất** (`_TRANSCRIPT_LIMIT = 6`,
   `core/run_turn.py:75`) + toàn bộ `CoreState` (slots, `chosen_vehicle_id`,
   `recommended_ids` — không giới hạn theo số lượt, sống suốt phiên).
4. `validate()` — chuẩn hoá tất định, fuzzy entity match (rapidfuzz,
   `domain/fuzzy_match.py`).
5. `policy.decide()` (`core/policy.py`, 1083 dòng) — **bảng quyết định thuần,
   không I/O, không LLM**, ~28 luật thứ tự cố định, mỗi luật gắn comment trích
   đúng lượt log prod nó vá.
6. `act()` (`core/act.py`, 2518 dòng) — thực thi action, gọi service/tool.
7. `render` + ghi state/outcome/trace/HITL trong một transaction.

### Bộ nhớ hội thoại — hai kênh, phạm vi khác nhau

- **State có cấu trúc** (`CoreState.slots`, `chosen_vehicle_id`,
  `recommended_ids`, `ask_counts`, `pending`, `stage`): không giới hạn theo số
  lượt, sống suốt phiên.
- **Transcript thô đưa vào LLM hiểu ý**: giới hạn cứng 6 tin nhắn gần nhất.
- Phát hiện phụ: có một cơ chế "working memory projection" phức tạp hơn
  (`ConversationSummary` tóm tắt dần bởi LLM, `services/conversation_memory.py`
  `_update_summary` + `build_working_memory_projection`) — nhưng khi lần theo
  nơi tiêu thụ, nó **không được dùng bởi bước hiểu ý đang chạy thật**
  (`composition.py:604` nối `services.understanding = OpenAIUnderstander()`,
  không phải `SlotExtractionServiceImpl` — nơi duy nhất gọi
  `render_working_memory_projection`, `services/slot_extraction.py:190`).
  Có vẻ là hạ tầng mồ côi, cần xác nhận thêm với đội.

### Câu trả lời cuối: LLM hay template?

Không đồng nhất theo loại nội dung:

- **Giá/TCO/giá lăn bánh**: 100% template Python thuần (`core/render.py`
  `on_road_card_lead`, `tco_summary`, `closing_question`), không LLM.
- **Tư vấn/so sánh (recommend, synthesis)**: LLM diễn đạt (không sinh số) từ
  snapshot đã qua guardrail — tier `EVIDENCE_BACKED_AUTO` của
  `domain/quote_risk.py`.

### HITL — hai máy trạng thái tách biệt

- **Ownership phiên**: `AI → PENDING_HANDOFF → HUMAN`
  (`core/run_turn.py:565-597, 431-457`).
- **Quote risk gate** (A7-4, `domain/quote_risk.py`) — **rule-based,
  default-deny, cố ý KHÔNG gọi LLM**: *"một quyết định an toàn không được
  phụ thuộc vào thứ có thể bịa"*.
- Không có field tên đúng `lockedAttributes`; cơ chế tương đương gần nhất là
  `domain/vehicle_type_lock.py` (giữ loại xe/xe đã chọn trừ khi khách đổi ý
  rõ ràng).

### Tool

`src/agents/tools/{compare_vehicles,tco,on_road_price,policy_search,
numeric_constraint}.py` — thuần Python, không DB, không LLM. Tool nào chạy
do `policy.decide` chọn, **không phải LLM tự chọn**. Đã có sẵn khuôn mẫu
"LLM ép chọn 1 tool cố định, chỉ điền tham số" (`bind_tools(...,
tool_choice=<tên tool>)`) ở `adapters/spec_tool_llm.py`, `tco_tool_llm.py`,
`location_tool_llm.py` — LLM không bao giờ tự chọn *tool nào* chạy, chỉ điền
*tham số* cho tool policy đã quyết định gọi.

### Session/lưu trữ

Không có Redis trong `src/` (đã grep xác nhận). Toàn bộ state nằm ở Postgres
(`conversation_sessions`, `conversation_slots`, `conversation_core_state`,
`agent_turn_outcomes`, `agent_runs`, `quote_audit_log`).

### E2E đóng băng (A9-2)

`docs/docs_buildagent_long/khoi4/A9-2.md` yêu cầu tường minh *"chạy lại cho
kết quả giống nhau"*, CI chạy 2 lần để bắt phi tất định. Đây là ràng buộc
kiến trúc cứng nhất đối với bất kỳ đề xuất agentic nào.

## Chẩn đoán từng case — root cause cụ thể

### Lượt 1, lỗi phụ #1 — tiêu đề "chi phí 5 năm" thay vì giá xe

**Là quyết định sản phẩm có chủ đích, không phải bug.**
`core/act.py:2061-2111` (`_on_road_price`), comment dòng 2064-2076: *"giá lăn
bánh với TCO là MỘT"* (Sếp chốt 2026-08-31) — ON_ROAD_PRICE và COST dùng
**chung một `build_tco_card`**, nên tiêu đề luôn nhấn tổng chi phí 5 năm dù
khách chỉ hỏi "giá bao nhiêu". Cân nhắc lại là quyết định UX, không phải sửa
kỹ thuật.

### Lượt 1, lỗi phụ #2 — câu dẫn mâu thuẫn với card vừa hiện

**Bug state-propagation xác định chính xác, 1 dòng.**
`core/act.py:2110` — `_on_road_price` gọi
`_closing(services, state, vehicle_name=name, after_on_road=True)`
**không truyền `has_tco`**. Hàm `_closing()` (`core/act.py:277-303`) khi
thiếu `has_tco` tự suy `has_tco=(state.stage is Stage.COSTING)` — nhưng tại
thời điểm gọi, `state.stage = CHOSEN` (chưa kịp lên COSTING vì đây là lượt
hỏi giá đầu tiên), nên `has_tco` tính ra `False` dù dòng ngay phía trên
(`build_tco_card`, dòng 2102) vừa dựng đúng một card chi phí 5 năm cho cùng
response. Kết quả: `render.closing_question(..., has_tco=False,
after_on_road=True)` chạy nhánh `core/render.py:101-106`, mời khách xem thứ
đang hiện ngay trên màn hình.

**Fix:** truyền `has_tco=True` tường minh ở lời gọi `_closing()` dòng 2110.

### Lượt 2 — "tôi vừa hỏi cái j đấy"

**Tính năng chưa tồn tại, không phải lỗi phân loại.** `understand()` *có*
nhận transcript 6 tin nhắn + `CoreState` — không phải "thiếu ngữ cảnh".
Nhưng `DialogueAct` (`core/state.py:45-54`) và `Intent` (`core/state.py:28-42`)
là liệt kê đóng, **không có phạm trù nào đại diện cho "khách hỏi lại chính
câu hỏi trước của họ"**. Grep toàn bộ `core/` cho "vừa hỏi" chỉ ra mọi cơ chế
hiện có đều là *"câu BOT vừa hỏi"* (theo dõi để hiểu câu trả lời tiếp theo),
không có chiều ngược lại. Không có Action/service nào đọc lại
`TurnResult.answer` của lượt trước để dựng câu "nhắc lại". Dù phân loại
"hoàn hảo" tới đâu, không có code path nào để đi tới sau khi phân loại đúng
— **thiếu tính năng**, không phải thiếu khả năng suy luận. Dữ liệu cần
(`TurnResult` lượt 1) **đã được lưu** trong `agent_turn_outcomes` qua
`_commit()`.

### Case 2 — "xe khác đi"

**Khe hở thứ tự luật + lưới an toàn tất định bị mồ côi.**

1. `understand._refine_question()` (`core/understand.py:349-372`) **tất
   định** (không qua LLM) chép nguyên văn "xe khác đi" vào `u.question` khi
   slot không đổi, stage ∈ {RECOMMENDED, CHOSEN}, dialogue_act ∈ {REQUEST,
   SLOT_ANSWER} — lưới an toàn hoạt động đúng.
2. Nhưng nếu LLM tag `u.intent = NONE` (rủi ro đã biết cho lớp câu "X
   khác/hơn" trơn — xem `domain/comparative_revision.py:6-10`, ghi lại một
   câu tương tự LLM trả `intents: []` hai lần trên prod), **luật 6a**
   (`core/policy.py:498-512`) chạy trước, chỉ nhìn `u.intent` thô, **không
   đọc `u.question`**, và trả về `TEMPLATE_CHOSEN_SUMMARY` — nuốt mất câu xin
   đổi xe.
3. Nếu LLM tag đúng `u.intent = ADVISORY`, nhánh chung (dòng 530-536) gọi
   `_advise(refine="xe khác đi")` (dòng 1009-1038) → xử lý **đúng**: loại
   `recommended_ids` cũ, đề xuất lại.
4. Trước khi xoá lõi v1, có một cửa tiền xử lý tất định —
   `domain/conversation_control.py` — với `_REVISE_TASK_PATTERN` khớp thẳng
   "xe/mẫu/phương án khác" (dòng 43-47), chạy **trước cả LLM**. Grep xác
   nhận `classify_conversation_control()`/`classify_advisory_flow()`
   (`domain/advisory_restart.py`) **chỉ còn được gọi trong unit test**,
   không có lời gọi nào trong `src/agents/core/` hay `services/` —
   **code mồ côi**, rơi rớt từ lần xoá lõi v1 mà không được cấy lại vào
   core v2.

## Phương án đã cân nhắc

| | A. Giữ workflow, vá khe hở + bổ sung Action | B. Hybrid — agent loop hẹp cho câu mở | C. Thay hẳn bằng agent loop |
|---|---|---|---|
| Giải quyết 3 case trên | Trực tiếp, từng điểm vỡ đã định vị | Không đảm bảo — vẫn cần vá đúng những điểm này trước, agent loop không tự sửa bug state/rule-ordering | Như B, thêm rủi ro |
| Rủi ro HITL/hallucination giá | Không đổi | Thấp nếu ép output qua guardrail/quote-risk gate | Cao nếu không ép nghiêm ngặt |
| Ảnh hưởng E2E đóng băng (A9-2) | Không | Không nếu cô lập + tiêu chí đánh giá riêng | Vỡ hoàn toàn |
| Mức thay đổi | Thấp (vài chục dòng) | Trung bình | Cao |

**Lý do loại B/C ở giai đoạn này:** cả 3 case đều là bug định vị được (state
bug, tính năng thiếu, rule-ordering + code mồ côi) — không phải triệu chứng
"kiến trúc không đủ khả năng thinking". Agent loop không sửa các lỗi này, chỉ
có thể che chúng bằng may rủi của một prompt tốt hơn, trong khi đánh đổi toàn
bộ tính tất định (HITL, E2E đóng băng, chống hallucination giá) đội vừa mới
củng cố (xoá lõi v1 LangGraph, 2026-08-31, chính vì lý do tái lập/truy vết).

Với câu hỏi rộng hơn "làm sao bao phủ hết mọi intent, trả lời đúng nhu cầu":
domain này là tập hữu hạn (~10 intent, vài chục biến thể cách hỏi), không
phải bài toán mở cần agent tự suy luận. Cách tăng coverage đúng là đo (qua
`turn_trace`/`quote_audit_log` đã có sẵn) rồi vá luật có định hướng — mỗi
luật đúng thì đúng 100% mọi lần, còn LLM tự quyết định lại chỉ đúng phần lớn
thời gian, không đảm bảo. Chỉ khi đo được một phần dư thực sự không
enumerate nổi mới cân nhắc mở một nhánh B hẹp cho đúng phần dư đó.

## Quyết định

**Chọn Phương án A** — giữ nguyên kiến trúc workflow tất định (core v2), vá
các điểm vỡ cụ thể đã định vị, tiếp tục dùng `turn_trace`/`quote_audit_log`
để đo phần dư thật trước khi cân nhắc mở rộng sang B.

## Các điểm sửa đã xác định (chưa lên kế hoạch triển khai chi tiết)

1. `core/act.py:2110` — truyền `has_tco=True` tường minh trong lời gọi
   `_closing()` bên trong `_on_road_price`.
2. Cân nhắc lại với đội sản phẩm việc tiêu đề card ON_ROAD_PRICE luôn nhấn
   tổng chi phí 5 năm — quyết định UX, không bắt buộc sửa.
3. `core/policy.py:498-512` (luật 6a) — thêm điều kiện `and not
   u.question.strip()` trước khi trả `TEMPLATE_CHOSEN_SUMMARY`, để không
   nuốt mất câu xin đổi xe đã được `_refine_question` salvage.
4. Quyết định số phận `domain/conversation_control.py` /
   `domain/advisory_restart.py`: hồi sinh làm tín hiệu tất định phụ trong
   `understand.py`, hoặc xoá hẳn nếu xác nhận không cần.
5. Thêm một Action/Intent mới hẹp (tạm gọi `RECALL_LAST_ANSWER`) cho lớp câu
   meta ("vừa hỏi cái gì", "nói lại giúp em", "nãy nói gì") — kích hoạt bằng
   tín hiệu tất định (regex, tương tự khuôn `conversation_control.py` cũ),
   đọc lại `TurnResult`/`agent_turn_outcomes` của lượt gần nhất từ Postgres
   (dữ liệu đã có sẵn), ghép template nhắc lại — không cần LLM suy luận lại
   số liệu.

## Cách đo cải thiện (đề xuất, chưa triển khai)

- Bộ test hội thoại nhiều lượt, `tests/agents/integration/
  test_multi_turn_reference.py`, lấy 3 case trong ADR này làm test đầu tiên:
  - Case 1 (2 lượt: giá VF5 → "tôi vừa hỏi cái j đấy") — assert lượt 2 chứa
    lại đúng con số của lượt 1, không rơi vào `PENDING_PROFILE`.
  - Case 1 lỗi phụ #2 — assert `closing_question` không mời xem lại nội dung
    đã hiện trong cùng response.
  - Case 2 ("tư vấn xe A" → "xe khác đi") — assert `Recommend(reason=
    REASON_REVISED, exclude_ids=(A,))`, không rơi vào `TEMPLATE_CHOSEN_SUMMARY`.
- Baseline trước khi vá: lọc `turn_trace` cho các lượt có `action_name` thuộc
  {`Reply(TEMPLATE_CHOSEN_SUMMARY)`, `Reply(TEMPLATE_CLARIFY)`,
  `_ask_capped(PENDING_PROFILE)`} ngay sau một lượt đã có `chosen_vehicle_id`/
  `recommended_ids` — đây là tỷ lệ "rơi vào fallback không đúng ý" thật, đo
  lại sau khi vá để so sánh.

## `[GIẢ ĐỊNH]` tồn đọng, cần xác nhận với đội

- `ConversationSummary`/`build_working_memory_projection` có thật sự mồ côi
  hay phục vụ một mục đích khác (hiển thị cho tư vấn viên khi HITL?) — chưa
  trace hết.
- Vai trò hiện tại (nếu còn) của `domain/conversation_control.py` /
  `domain/advisory_restart.py` — giữ, hồi sinh, hay xoá.
- Phạm vi chính xác của `RECALL_LAST_ANSWER` — chỉ recall câu ngay trước, hay
  cho phép "3 câu trước tôi hỏi gì".
- Nguyên nhân chính xác LLM tag `u.intent` gì cho "tôi vừa hỏi cái j đấy" ở
  Case 1 lượt 2 (UNCLEAR hay ADVISORY/NONE) — không ảnh hưởng kết luận chính
  (thiếu tính năng), nhưng cần xác nhận bằng log/eval thật trước khi thiết
  kế luật kích hoạt `RECALL_LAST_ANSWER`.

## Nguồn

Toàn bộ phân tích trong ADR này đến từ việc đọc trực tiếp code trong phiên
làm việc 2026-09-22 (không sửa code, không chạy migration) — không có bộ
test/PR nào đi kèm. Bước tiếp theo (chưa thực hiện): lên kế hoạch triển khai
chi tiết cho 5 điểm sửa ở mục "Các điểm sửa đã xác định".
