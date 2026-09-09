# Báo cáo evidence cho Conversation Memory và Slot Collection

## Kết luận

**Đạt:** 61/61 scenario (69 lượt hội thoại) vượt qua toàn bộ kỳ vọng trong bộ eval offline. Deliverable yêu cầu tối thiểu 5 test case được chứng minh bằng 5 case tiêu biểu ở phần dưới; kết quả đầy đủ nằm trong [`slot_conversation_report.md`](slot_conversation_report.md).

## Phạm vi và cách chạy

- Thời điểm chạy: `2026-08-16T10:29:52+07:00`
- Chế độ: offline, deterministic
- LLM đầu vào: scripted fixtures, `temperature=0`
- Thành phần thật được kiểm tra: `SlotExtractionServiceImpl`, conversation memory/reconciliation và `slot_policy.next_slot`
- Dataset: `eval/datasets/slot_conversations.json`
- Lệnh chạy:

```powershell
.\.venv\Scripts\python.exe scripts\evaluate_slot_conversations.py --output eval\results\slot_conversation_report.md
```

- Kết quả lệnh: exit code `0`

Đây là regression eval cho logic hội thoại, không phải phép đo câu trả lời end-to-end. Vì vậy báo cáo không suy diễn điểm response latency, user satisfaction hoặc độ đúng của nội dung tư vấn do LLM sinh ra.

## Chỉ số tổng hợp

| Chỉ số | Kết quả |
|---|---:|
| Scenario pass rate | 100.0% (61/61) |
| Số lượt được đánh giá | 69 |
| Slot precision | 100.0% |
| Slot recall | 100.0% |
| False-fill rate | 0.0% |
| Redundant-question rate | 0.0% |
| Next-question accuracy | 100.0% |
| Correction accuracy | 100.0% |
| Completion rate | 100.0% |
| Normalized intent exact match | 100.0% |
| Decision accuracy | 100.0% |
| Referent resolution accuracy | 100.0% |
| Context carry-over accuracy | 100.0% |
| False memory carry-over rate | 0.0% |

Raw intent và raw decision cùng đạt 82.6%; sau lớp reconciliation của production, cả intent và decision đều đạt 100.0%. Điều này cho thấy lớp reconciliation đang sửa các nhãn thiếu/thừa trong fixture đúng như thiết kế và hiện chưa thể loại bỏ.

## Evidence: 5 test case tiêu biểu

| ID | Input / ngữ cảnh | Kỳ vọng chính | Kết quả thực tế | Trạng thái |
|---|---|---|---|---|
| SC041 | “Nhà tôi bốn người, tài chính khoảng 500 triệu, chủ yếu đi nội thành và thỉnh thoảng về quê; VF 5 có hợp không?” | Ghi đủ 5 slot; nhận cả `ADVISORY` và `CATALOG_LOOKUP`; quyết định `HYBRID`; không hỏi thêm | Ghi đúng `CAR`, 4 người, 500 triệu, mục đích và 2 need tag; decision `HYBRID`; next slot `null` | **PASS** |
| SC045 | “VF 5 của tôi pin tụt từ 42% xuống 33% sau khoảng 10 km, xe bị sao?” | Không ghi nhầm số 5, 42%, 33% hoặc 10 km vào phiếu nhu cầu; lookup đúng VF 5 | Không có slot nào bị false-fill; vehicle mention `VF 5`; decision `LOOKUP` | **PASS** |
| SC054 | Memory: đã loại VF 5 vì chật, đang tiếp tục VF 7. User hỏi “Mẫu còn lại giá bao nhiêu?” | Giải tham chiếu “mẫu còn lại” thành VF 7 và giữ nhánh ô tô | Memory được dùng; vehicle mention `VF 7`; giữ `vehicle_type=CAR`; decision `LOOKUP` | **PASS** |
| SC058 | Đang tìm ô tô, ngân sách 500 triệu. User yêu cầu giữ ngân sách nhưng chuyển sang xe máy điện | Chuyển đúng nhánh xe máy điện, giữ ngân sách và tiếp tục tư vấn | `vehicle_type=ELECTRIC_MOTORBIKE`, `budget_max_vnd=500000000`; decision `RETRIEVE`; hoàn tất ở lượt 1 | **PASS** |
| SC061 | Memory xác định VF 7; raw fixture gán thừa `ADVISORY` cho câu hỏi giá “mẫu còn lại” | Loại intent thừa, giữ lookup thuần và tham chiếu VF 7 | Raw decision `HYBRID` được chuẩn hóa thành `LOOKUP`; intent còn `CATALOG_LOOKUP`; vehicle mention `VF 7` | **PASS** |

Tóm tắt 5 case evidence: **5/5 PASS**.

## Truy xuất bằng chứng

- Báo cáo đầy đủ 61 scenario: [`eval/results/slot_conversation_report.md`](slot_conversation_report.md)
- Golden dataset và expected output: [`eval/datasets/slot_conversations.json`](../datasets/slot_conversations.json)
- Hướng dẫn, định nghĩa metric và lệnh tái lập: [`eval/SLOT_CONVERSATION_EVAL.md`](../SLOT_CONVERSATION_EVAL.md)

## Giới hạn và bước kiểm tra tiếp theo

- Offline fixtures cho kết quả lặp lại được nhưng không đại diện cho độ dao động của LLM thật.
- Live eval có thể phát sinh chi phí nên không được chạy trong lần này. Kết quả live gần nhất đã lưu trong `combined_agent_report.md` chỉ bao phủ 6 critical scenario, lặp 3 lần.
- Khi thay đổi prompt/model hoặc logic memory, cần chạy lại toàn bộ offline suite; với thay đổi ảnh hưởng LLM, chạy thêm live critical suite sau khi chủ động bật `AGENT_SLOT_EVAL_LIVE=1`.
