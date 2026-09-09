# Benchmark của P-150 — đo cái gì, ở đâu, đọc số ra sao

Bốn lớp, từ rẻ → đắt. Lớp trên xanh không thay được lớp dưới.

| Lớp | Đo gì | LLM | Chạy | Gate |
|---|---|---|---|---|
| **1. Offline slot/planning** | trích slot, hỏi slot nào tiếp, intent, nhớ tham chiếu | giả (payload có sẵn) | `uv run pytest tests/agents/unit/eval` (~1s) | `test_offline_golden_dataset_passes_without_network_calls` = **1.0** |
| **2. Live probe (hội thoại thật)** | thứ khách nhìn thấy: lượt chết, 500, câu cụt, đề xuất có/không, chữ trong câu | thật | `python scripts/live_probe_eval.py` (~5 phút) | **34/34 kịch bản** |
| **3. Judge** | chất lượng văn bản đề xuất theo tiêu chí | LLM giám khảo | `eval/judge/runner.py`, báo cáo `eval/results/report.md`, `combined_agent_report.md` | so before/after |
| **4. Hợp đồng kiến trúc (Ngọc)** | 14 lớp hành vi bắt buộc + stage được/cấm | không | `pytest tests/agents/unit/eval/test_architecture_golden.py` | cấu trúc, chưa gate hành vi |

## Lớp 1 — `eval/conversation` + `eval/datasets/slot_conversations.json`

91 kịch bản, mỗi lượt kèm payload LLM giả và kỳ vọng (slot, câu hỏi kế, intent,
decision, mention). Chạy qua đúng `SlotExtractionServiceImpl` / `SlotPlanningServiceImpl`
của production. Chỉ số trong `MetricReport`: slot precision/recall, false-fill,
hỏi thừa, referent resolution, memory carry-over. Sửa code làm rơi một kịch bản →
test đỏ.

Chạy live cùng dataset (LLM thật, opt-in, chọn tập nhỏ):
`uv run python scripts/evaluate_slot_conversations.py --live --scenario SC041 SC046`.

## Lớp 2 — `eval/datasets/live_probe_scenarios.json` + `scripts/live_probe_eval.py`

34 kịch bản: 16 do Sếp bắn tay 2026-08-28 (`source: sep`) + 9 lấy nguyên câu từ
log prod 25–28/08 (`source: prod`) + 5 kịch bản "thiếu thông tin / chen ngang" của khung việc theo intent (`source: khung-viec`, 2026-08-29) + 3 kịch bản "liên hệ tính năng với nhu cầu" (`source: feature-fit`, 2026-08-29). Mỗi lượt có tiêu chí tất định (`expect`):
`asks`, `alive`, `recs_min`, `text_any`, `text_none`, `terminal_none`, `no_500`.

Cần server đang chạy (export `.env` trước — `AgentComposition` đọc `os.environ`),
tài khoản `customer@gmail.com`. Bị 429 thì xoá `agent_rate_limit_counters`.

Kết quả: `eval/results/live-probe/<timestamp>.json` + `.md` + `latest.md`.
Số đầu bảng: **kịch bản đạt / lượt đạt / lỗi HTTP / lượt chết / p50–p95**.
Exit code ≠ 0 khi có kịch bản đỏ → gắn được vào CI theo lịch.

Thêm kịch bản: chép một câu khách thật vào `scenarios`, viết `expect` theo điều
ĐÃ kiểm bằng mắt là đúng — benchmark khoá hành vi đúng, không mô tả hành vi mong ước.

## Lớp 4 — `eval/datasets/architecture_golden.json`

Bộ của Ngọc, giữ nguyên văn kỳ vọng của "kiến trúc mới" (hướng 1, 2026-08-28).
Runner lớp 1 **không** đọc file này. Muốn nó gate hành vi develop thì phải sửa kỳ
vọng theo develop (hướng 2) — xem PR #20 để biết 12/19 ca lệch ở đâu.

## Đọc nhanh khi có PR

1. Lớp 1 đỏ → sửa code hoặc chứng minh kỳ vọng cũ sai, sửa dataset kèm lý do.
2. Lớp 2 đỏ ở `terminal[OUT_OF_SCOPE]`/`alive` → lượt chết, ưu tiên cao nhất.
3. Lớp 2 đỏ ở `text_any` → đổi lời; kiểm bằng mắt rồi cập nhật cụm.
4. p95 tăng gấp đôi → có thêm lần gọi LLM, hỏi tại sao.
