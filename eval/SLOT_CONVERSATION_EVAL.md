# Hướng dẫn eval hội thoại thu thập slot

## Mục tiêu

Bộ eval này kiểm tra việc Agent **ghi nhớ thông tin khách đã nói** và **chọn đúng câu hỏi tiếp theo** qua nhiều lượt. Nó chạy trực tiếp qua `SlotExtractionServiceImpl` và `slot_policy.next_slot`, nên kiểm tra đúng luồng nghiệp vụ thay vì mô phỏng lại luật trong test.

`Slot` là một trường thông tin có cấu trúc, ví dụ `vehicle_type` (loại xe), `passenger_count` (số chỗ/người), `budget_max_vnd` (ngân sách) và `purpose` (mục đích sử dụng). `Golden data` là trạng thái đúng được con người ghi sẵn để so với kết quả thực tế.

## Thành phần

- `datasets/slot_conversations.json`: 62 kịch bản, 70 lượt hội thoại, có nhãn nhóm để biết nhóm lỗi nào đang yếu.
- `evidence/vinfast_forum_scenarios.md`: URL, ngày truy cập và mapping các câu paraphrase từ cách khách nói thật; không dùng diễn đàn làm nguồn giá/thông số.
- `conversation/models.py`: schema Pydantic kiểm tra cấu trúc và chống ID trùng hoặc kỳ vọng mâu thuẫn.
- `scripts/slot_conversation_runner.py`: adapter runner trong bộ nhớ; mỗi kịch bản là một session độc lập và các lượt trong cùng kịch bản dùng chung trạng thái. Adapter nằm ngoài `eval/` để giữ đúng ranh giới kiến trúc: dữ liệu/công thức eval không phụ thuộc runtime Agent.
- `conversation/metrics.py`: tính các chỉ số tổng và tỷ lệ đạt theo từng nhóm.
- `conversation/reporting.py`: xuất Markdown cho người đọc hoặc JSON cho CI/dashboard.
- `scripts/evaluate_slot_conversations.py`: lệnh chạy offline mặc định và live khi chủ động bật.
- `tests/agents/unit/eval/`: test schema/độ phủ, công thức chỉ số, runner và khóa an toàn cho live eval.

## Phạm vi tình huống

Bộ dữ liệu bao phủ hai nhánh ô tô/xe máy điện; câu trả lời ngắn; nhiều slot trong một câu; nhiều lượt; sửa câu trả lời; đổi nhánh xe; nhắc tính năng sớm; tra cứu xen giữa; câu không có thông tin; phủ định; phân vân; câu hỏi so sánh; hybrid advisory + lookup; intent rỗng; trả góp theo tháng; điều kiện sạc chung cư; câu kỹ thuật sau mua; và kiểm tra không ghi nhầm slot từ tên mẫu xe.

Không có tập hữu hạn nào chứng minh đã bao phủ mọi câu tiếng Việt có thể xuất hiện. Vì vậy đây là **bộ hồi quy đại diện**: mỗi lỗi mới ở production cần được rút gọn thành một scenario mới, gắn đúng nhóm, rồi mới sửa code.

## Các chỉ số

| Chỉ số | Ý nghĩa dễ hiểu | Tốt khi |
|---|---|---|
| Slot precision | Trong các slot Agent đã ghi, tỷ lệ ghi đúng cả tên lẫn giá trị | Cao |
| Slot recall | Trong các slot khách đã cung cấp, tỷ lệ Agent lấy được đúng | Cao |
| False-fill rate | Tỷ lệ slot bị tự điền sai hoặc điền khi khách chưa chốt | Thấp |
| Redundant-question rate | Tỷ lệ câu hỏi tiếp theo hỏi lại đúng slot khách vừa cung cấp | Thấp |
| Next-question accuracy | Tỷ lệ chọn đúng slot tiếp theo theo `slot_policy` | Cao |
| Correction accuracy | Tỷ lệ cập nhật đúng khi khách đổi ý/sửa thông tin | Cao |
| Completion rate | Tỷ lệ kịch bản yêu cầu hoàn tất đã thu đủ slot bắt buộc | Cao |
| Average turns to completion | Số lượt trung bình để hoàn tất các kịch bản có mục tiêu hoàn tất | Thấp, nhưng không đánh đổi độ đúng |
| Scenario/group pass rate | Tỷ lệ toàn bộ kịch bản hoặc từng nhóm đạt tất cả kỳ vọng | Cao |
| Raw intent exact match | LLM thô trả đúng tập nhãn hay chưa, trước khi code bảo vệ | Cao nhưng có thể thấp hơn normalized |
| Normalized intent exact match | Intent sau lớp reconcile có đúng tập nhãn không | Cao |
| Intent false positive/negative | Tỷ lệ thêm thừa hoặc bỏ thiếu nhãn | Thấp |
| Decision accuracy | Graph chọn đúng ask, lookup, retrieve, hybrid hay clarify | Cao |
| Raw decision accuracy | Quyết định nếu chỉ tin intent LLM, dùng làm nhánh A | Cao |
| Referent resolution accuracy | Giải đúng “mẫu còn lại/thứ hai/vừa loại” thành tên xe | Cao |
| Context carry-over accuracy | Giữ đúng lựa chọn và ràng buộc từ memory | Cao |
| False memory carry-over rate | Kéo nhầm mẫu/slot từ ngữ cảnh hoặc phiên khác | Thấp |

Khi mẫu số bằng 0, chỉ số trả `N/A` thay vì `0%`; `0%` sẽ tạo cảm giác hệ thống làm sai dù thực tế chưa có mẫu để đo.

## Cách chạy

Chế độ offline không gọi mạng hay LLM trả phí; payload LLM đã được cố định trong dataset để kết quả lặp lại được:

```powershell
.\.venv\Scripts\python.exe scripts\evaluate_slot_conversations.py
```

Xuất JSON hoặc ghi báo cáo ra file:

```powershell
.\.venv\Scripts\python.exe scripts\evaluate_slot_conversations.py --format json
.\.venv\Scripts\python.exe scripts\evaluate_slot_conversations.py --output eval\results\slot_conversation_report.md
```

Live eval dùng LLM thật, có thể tốn phí và dao động giữa các lần chạy. Lệnh bị khóa mặc định và chỉ chạy khi bật rõ biến môi trường:

```powershell
$env:AGENT_SLOT_EVAL_LIVE = "1"
.\.venv\Scripts\python.exe scripts\evaluate_slot_conversations.py --mode live
```

Chạy ba lần chỉ trên nhóm critical để kiểm tra dao động mà không gọi toàn bộ tập:

```powershell
$env:AGENT_SLOT_EVAL_LIVE = "1"
.\.venv\Scripts\python.exe scripts\evaluate_slot_conversations.py --mode live `
  --scenario SC041 --scenario SC042 --scenario SC046 --scenario SC047 `
  --scenario SC049 --repeat 3 --output eval\results\combined_agent_report.md
```

Script tự tắt LangChain/LangSmith tracing trong riêng process eval, đồng thời ghi mode,
model, temperature, số lần chạy, thời gian và raw/normalized intent; không ghi API key.

CLI trả exit code `0` khi 100% scenario đạt và `1` khi có regression, nên có thể dùng làm quality gate trong CI. Báo cáo sẽ liệt kê scenario/lượt lỗi để truy ngược nhanh.

## Conversation Memory và A/B reconciliation

Các turn memory khai báo `memory_summary`, `recent_messages` và
`expected_vehicle_mentions`. Runner dựng Working Memory theo thứ tự
`Slot -> Summary -> recent transcript -> current message`, rồi truyền nó qua đúng
đường extraction production.

Một lần chạy tạo đồng thời hai nhánh đo trên cùng input:

- `raw_*`: quyết định trực tiếp từ intent LLM;
- `actual_*`/normalized: quyết định sau `reconcile_intents` production.

Không có feature flag bỏ reconciliation trong production. Chỉ cân nhắc loại lớp
này khi raw bằng normalized trên cả offline và live critical.

```powershell
$env:AGENT_SLOT_EVAL_LIVE = "1"
uv run python scripts/evaluate_slot_conversations.py --mode live `
  --scenario SC054 --scenario SC055 --scenario SC056 `
  --scenario SC060 --scenario SC061 --repeat 3
```

### Smoke test thủ công sáu lượt

1. `Tôi đang cân nhắc VF 5 và VF 7, nhưng loại VF 5 vì hơi chật.` — memory giữ VF 5 đã loại, VF 7 đang xem.
2. `Mẫu còn lại giá bao nhiêu?` — lookup đúng duy nhất VF 7, không hỏi lại nhu cầu.
3. `Giữ ngân sách 500 triệu lúc nãy nhưng chuyển sang xe máy điện.` — đổi loại xe, giữ ngân sách.
4. `Quay lại ô tô nhé.` — đổi lại CAR, không hỏi lại ngân sách đã biết.
5. `VF 5 và VF 7 khác nhau thế nào?` — lookup/so sánh thuần, không thêm ADVISORY.
6. `Không, tôi đổi ý, xem lại mẫu tôi vừa loại.` — referent quay lại VF 5.

## Cách bổ sung một lỗi mới

1. Thêm scenario có ID kế tiếp vào `datasets/slot_conversations.json`.
2. Ghi câu khách nói, payload trích xuất, toàn bộ trạng thái slot đúng sau lượt đó, expected intents/decision và slot tiếp theo cần hỏi.
3. Dùng `forbidden_slots` cho thông tin tuyệt đối không được ghi; `provided_slots` để bắt lỗi hỏi lại; `correction_slots` cho lượt khách đổi ý.
4. Chạy offline và xác nhận scenario mới thất bại trước khi sửa code.
5. Sửa theo quy tắc tổng quát, chạy lại toàn bộ dataset và test.
