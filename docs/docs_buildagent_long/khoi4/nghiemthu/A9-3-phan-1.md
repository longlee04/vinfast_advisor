# Nghiệm thu A9-3 (phần 1) — Khung KPI + judge offline, chưa có số thật

> **Đây là nghiệm thu một phần.** A9-3 có 4 dòng Test bắt buộc; phần này hoàn thành **2/4**.
> Hai dòng còn lại chờ A9-2, mà A9-2 chờ Khối 1/2/3 — xem mục 5.

File test: `tests/agents/unit/test_eval_boundary.py`, `tests/agents/unit/test_eval_judge.py`, `tests/agents/unit/test_kpi_dataset.py`
File code mới: `eval/__init__.py`, `eval/kpi.py`, `eval/judge/{__init__,ports,scoring,runner}.py`, `eval/datasets/kpi_questions.yaml`

## 1. Đối chiếu Test bắt buộc → bằng chứng

| Điều kiện (nguyên văn từ `phan-cong-thanh-vien.md`) | Tên hàm test | Kết quả |
|---|---|---|
| **judge không được import từ `src/agents/` runtime** (assert biên một chiều) | `test_eval_does_not_import_the_agent_runtime` | PASSED |
| — chiều ngược lại của cùng biên đó | `test_the_agent_runtime_does_not_import_eval` | PASSED |
| Báo cáo KPI-1/2/4 có **số thật** trên ≥50 câu | *(bộ câu hỏi đã có — xem dưới; phần "số thật" CHƯA LÀM)* | **CHƯA ĐẠT** |
| p95 ≤6s + 50 phiên đồng thời có bằng chứng | *(chưa làm)* | **CHƯA ĐẠT** |
| **bật/tắt judge không đổi kết quả E2E A9-2** | *(chưa làm — cần A9-2)* | **CHƯA ĐẠT** |

Phần đã dựng xong, có test:

| Việc | Tên hàm test | Kết quả |
|---|---|---|
| Bộ câu hỏi có ≥50 câu | `test_the_dataset_has_at_least_fifty_questions` | PASSED (55 câu) |
| Mã câu hỏi không trùng | `test_every_question_identifier_is_unique` | PASSED |
| Mọi câu khai `vehicle_type` hợp lệ | `test_every_question_declares_a_known_vehicle_type` | PASSED |
| Mọi câu khai `intent` hợp lệ | `test_every_question_declares_a_known_intent` | PASSED |
| Không câu nào rỗng | `test_no_question_text_is_empty` | PASSED |
| Cả hai nhánh xe đều được phủ (≥10 câu mỗi nhánh) | `test_both_vehicle_branches_are_covered` | PASSED |
| Có câu ngoài phạm vi để nghiệm thu A6-2 | `test_out_of_scope_questions_are_present` | PASSED |
| KPI-1 Factual Accuracy tính đúng | `test_factual_accuracy_is_the_share_of_answers_with_every_number_sourced` | PASSED |
| KPI-2 tính trên mẫu số là số đề xuất vượt ngân sách | `test_unwarned_over_budget_rate_counts_only_recommendations_without_a_warning` | PASSED |
| Đề xuất vượt ngân sách **có** cảnh báo không bị tính | `test_a_warned_over_budget_recommendation_does_not_count_against_the_kpi` | PASSED |
| KPI-4 = slot đã thu / slot đã hỏi | `test_required_slot_completion_is_filled_over_asked` | PASSED |
| Judge mặc định TẮT | `test_the_judge_is_off_unless_the_environment_variable_says_otherwise` | PASSED |
| Bật bằng biến môi trường | `test_the_judge_turns_on_with_the_environment_variable` | PASSED |
| Điểm trung bình ba tiêu chí | `test_the_average_score_is_the_mean_of_the_three_criteria` | PASSED |
| Liệt kê câu tụt điểm so với lần trước | `test_questions_that_lost_points_since_the_last_run_are_listed` | PASSED |
| Spy đếm: judge gọi đúng một lần mỗi câu | `test_running_the_judge_calls_the_injected_port_once_per_question` | PASSED |

Test âm (DoD điều 2):

| Nhánh | Tên hàm test | Kết quả |
|---|---|---|
| Tập rỗng → KPI-1 "không tính được", **không phải 100%** | `test_factual_accuracy_of_an_empty_run_is_unavailable_not_perfect` | PASSED |
| Không có đề xuất nào → KPI-2 "không tính được" | `test_unwarned_over_budget_rate_is_unavailable_without_any_recommendation` | PASSED |
| Chưa hỏi slot nào → KPI-4 "không tính được", không chia cho 0 | `test_required_slot_completion_is_unavailable_when_nothing_was_asked` | PASSED |
| Thu nhiều hơn hỏi → lỗi dữ liệu, không cho ra KPI > 1 | `test_more_filled_than_asked_is_a_data_error` | PASSED |
| Giá trị môi trường lạ → judge vẫn tắt | `test_an_unrecognised_environment_value_leaves_the_judge_off` | PASSED |
| Câu mới thêm không bị báo là tụt điểm | `test_a_question_absent_from_the_previous_run_is_not_a_regression` | PASSED |
| Câu không có đáp án → không tốn lần gọi nào | `test_a_question_without_an_answer_is_not_sent_to_the_judge` | PASSED |
| Bộ kiểm biên tự bắt được import vi phạm (2 dạng cú pháp) | `test_the_boundary_check_catches_a_violating_import`, `test_the_boundary_check_catches_a_plain_import_statement` | PASSED |

## 2. Bẫy dễ sai đã xử lý thế nào

Cột "Bẫy dễ sai" của A9-3 trong `phan-cong-thanh-vien.md` là `—` (không có bẫy nào được ghi).

Ba đột biến để chứng minh test không xanh giả:

| Đột biến | Kết quả | Test bắt được |
|---|---|---|
| KPI-1 trả `1.0` cho tập rỗng (thay vì `None`) | 1 test đỏ | `test_factual_accuracy_of_an_empty_run_is_unavailable_not_perfect` |
| KPI-2 chia cho **tổng số câu** thay vì số đề xuất vượt ngân sách | 2 test đỏ | test tính KPI-2 và test "không tính được" |
| `judge_enabled` bật với **mọi** giá trị khác rỗng | 1 test đỏ | `test_an_unrecognised_environment_value_leaves_the_judge_off` |

Khôi phục code → 28 passed.

Bộ kiểm biên còn có hai test **tự kiểm chính nó** (`test_the_boundary_check_catches_*`): nếu hàm quét AST hỏng, hai test biên kia sẽ xanh vô nghĩa.

## 3. Kết quả 3 lệnh kiểm tra

```
$ uv run pytest tests/agents -q
245 passed, 1 warning in 196.72s (0:03:16)

$ uv run ruff check src/agents tests/agents eval
All checks passed!

$ uv run mypy src/agents
src/agents/adapters/feature_retriever.py:131: error: Argument "status" to "FeatureAssertion" has incompatible type "str"; expected "Literal['YES', 'NO', 'UNKNOWN']"  [arg-type]
src/agents/adapters/feature_retriever.py:282: error: Incompatible types in assignment (expression has type "float", variable has type "SQLCoreOperations[Decimal | None] | Decimal | None")  [assignment]
Found 2 errors in 1 file (checked 63 source files)

$ uv run mypy eval
Success: no issues found in 6 source files
```

Đã chạy thêm `ruff` và `mypy` trên thư mục `eval/` vì code mới nằm ở đó — cả hai sạch.

Ghi chú về mypy `src/agents`: vẫn đúng 2 lỗi tồn đọng của Khối 1 (Dương), không phải do A9-3.

## 4. Toàn bộ suite

Đã chạy `uv run pytest -q` (toàn repo):

| Mốc | Kết quả |
|---|---|
| Sau A9-1 | `6 failed, 969 passed, 4 skipped, 102 errors` |
| Sau A9-3 phần 1 | `6 failed, 997 passed, 4 skipped, 102 errors` |

- Chênh lệch đúng **+28 passed**. `failed` và `errors` **không đổi**.
- `eval/` không import gì từ `src/agents` và ngược lại — có test cưỡng chế cả hai chiều.

## 5. Điểm lệch so với plan

Mục "Cần chốt trước khi code" của `A9-3.md` có 6 điểm:

| # | Điểm | Quyết định cuối | Trạng thái |
|---|---|---|---|
| 1 | Định nghĩa KPI-1/2/4 | Anh Long cấp tên chính thức: **KPI-1 Factual Accuracy**, **KPI-2 Unwarned Over-Budget Recommendation Rate**, **KPI-4 Required-Slot Completion**. Em cài công thức theo tên đó (xem docstring `eval/kpi.py`) | Công thức **chưa được xác nhận**, **ngưỡng đạt chưa có** |
| 2 | Bộ câu hỏi từ đâu | Em soạn, anh duyệt sau | 55 câu, chờ anh rà nghiệp vụ |
| 3 | Đo p95 bằng gì, ở môi trường nào, bằng chứng dạng gì | **Chưa chốt** | Chưa làm |
| 4 | Judge dùng LLM nào, ngân sách bao nhiêu | Dựng khung + `JudgePort`, test bằng fake trả điểm cứng; LLM thật cắm sau, không đổi logic | Model **chưa chốt** |
| 5 | Mức nghiêm của "assert biên một chiều" | Quét import bằng AST (bắt cả import không dùng tới), cả hai chiều | Xong |
| 6 | Bật/tắt judge bằng gì | Biến môi trường `AGENT_EVAL_JUDGE`, mặc định **tắt** | Xong |

Hai điều phát sinh:

1. **`pyyaml` chưa được khai trong `pyproject.toml`** nhưng có sẵn trong môi trường (6.0.3, kéo theo qua phụ thuộc gián tiếp). Test đọc dataset đang dựa vào đó. Nếu muốn chắc chắn thì phải khai làm dev-dependency — em **chưa tự thêm** vì đó là đổi phụ thuộc dự án.
2. **Một test của em sai ngay từ đầu, không phải code sai.** Test KPI-2 ban đầu kỳ vọng `0.5` (tính trên 4 câu hỏi) trong khi mẫu số đúng phải là 3 đề xuất vượt ngân sách → `2/3`. Đã sửa test, giữ nguyên code.

## Còn lại của A9-3 (chưa làm được)

| Việc | Chặn bởi | Cần thêm gì |
|---|---|---|
| Chạy 55 câu qua graph → số thật cho 3 KPI | A9-2, mà A9-2 chờ Khối 1/2/3 | Graph chạy được thật |
| Đo p95 ≤6s + 50 phiên đồng thời | như trên | Cả điểm chốt #3 ở bảng trên |
| Test "bật/tắt judge không đổi kết quả E2E A9-2" | A9-2 | E2E A9-2 tồn tại |
| Cắm LLM thật vào `JudgePort` | điểm chốt #4 | Chốt model + ngân sách |
