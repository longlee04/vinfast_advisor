# Nghiệm thu comparison-image — Service render ảnh so sánh mẫu xe

File test: `tests/agents/unit/services/test_comparison_image.py`, `tests/agents/integration/test_comparison_image_delivery.py`
File code mới: `src/agents/services/operations/comparison_image.py`
File code sửa: `src/agents/services/operations/review.py`, `src/agents/api/review_routes.py`, `src/agents/api/schemas.py`
Tài sản mới: `src/agents/assets/fonts/DejaVuSans.ttf`, `src/agents/assets/fonts/DejaVuSans-Bold.ttf`
Phụ thuộc mới: `pillow` (thêm vào `pyproject.toml`)

## 1. Đối chiếu Test bắt buộc → bằng chứng

| Điều kiện (nguyên văn từ `phan-cong-thanh-vien.md`) | Tên hàm test | Kết quả |
|---|---|---|
| Cùng một input snapshot → ảnh sinh ra **byte-identical** giữa 2 lần chạy | `test_the_same_snapshot_renders_byte_identical_images` | PASSED |
| Mọi con số trên ảnh **lấy từ `run_snapshots`**, không query lại catalog — spy trên session: **không phát sinh query DB nào** | `test_rendering_does_not_touch_the_database` | PASSED |
| So sánh chéo loại xe → service **từ chối render** | `test_a_table_mixing_vehicle_types_is_refused` | PASSED |
| Ô nguồn `DOCUMENT` trên ảnh **có nhãn "chưa xác minh"** | `test_a_document_sourced_cell_carries_the_unverified_label` | PASSED |
| Ảnh đi kèm câu trả lời **vẫn qua HITL A7** — run chưa `APPROVED` thì endpoint gửi khách không trả được ảnh | `test_an_unapproved_run_does_not_release_the_comparison_image` | PASSED |
| Service lỗi (font thiếu, dữ liệu rỗng) → **không làm chết lượt chat**, câu trả lời văn bản vẫn gửi được, chỉ thiếu ảnh | `test_a_failing_render_returns_none_instead_of_breaking_the_turn` | PASSED |

Test âm và test biên kèm theo (DoD điều 2):

| Nhánh code | Tên hàm test | Kết quả |
|---|---|---|
| Ô nguồn `FLAG` **không** bị gắn nhãn thừa | `test_a_flag_sourced_cell_has_no_extra_label` | PASSED |
| Bảng rỗng → lỗi render tường minh | `test_an_empty_table_is_reported_as_a_render_error` | PASSED |
| Một mẫu xe → lỗi (A5-4 so 2–3 mẫu) | `test_a_single_vehicle_table_is_reported_as_a_render_error` | PASSED |
| Bốn mẫu xe → lỗi | `test_a_four_vehicle_table_is_reported_as_a_render_error` | PASSED |
| Thiếu font → không làm chết lượt | `test_a_missing_font_does_not_break_the_turn` | PASSED |
| Đầu ra thật sự là PNG, không phải chuỗi rỗng qua mặt test byte-identical | `test_a_valid_table_renders_a_png` | PASSED |
| Run đã duyệt → ảnh mới được trả | `test_an_approved_run_releases_the_comparison_image` | PASSED |
| Đã duyệt nhưng không có ảnh → phần văn bản vẫn gửi được | `test_an_approved_run_without_an_image_still_delivers_the_text` | PASSED |
| Run bị từ chối cũng là chưa duyệt → không trả ảnh | `test_a_rejected_run_does_not_release_the_comparison_image` | PASSED |

## 2. Bẫy dễ sai đã xử lý thế nào

### (a) Byte-identical giữa 2 lần chạy

Ba nguồn phi tất định bị chặn trong `comparison_image.py`:

1. **Metadata PNG** — lưu bằng `optimize=False`, không truyền `pnginfo`, nên Pillow không nhét thời gian tạo file vào ảnh.
2. **Font** — đọc từ `src/agents/assets/fonts/` đóng gói cạnh code, không dùng font hệ thống.
3. **Thứ tự dữ liệu** — chỉ duyệt theo `rows`/`vehicle_ids` của bảng đầu vào, không duyệt `dict`/`set`.

Ngoài ra `captured_at` và thời điểm render đều **không** được vẽ lên ảnh.

**Kiểm chứng bằng đột biến:** tạm thêm `PngInfo` chứa `datetime.now()` vào lúc lưu → `test_the_same_snapshot_renders_byte_identical_images` **đỏ**. Khôi phục → xanh.

### (b) Service lỗi không được làm chết lượt chat

`render_comparison_image_or_none` nuốt đúng ba loại lỗi (`ComparisonImageError`, `CrossVehicleTypeComparisonError`, `OSError`) và trả `None`. Endpoint gửi khách trả `comparison_image_base64 = None` mà phần `content` vẫn nguyên vẹn — có test riêng cho tình huống này.

### (c) Bẫy phát sinh — Pillow âm thầm rơi về font hệ thống

**Test đã bắt được lỗi thật trong bản code đầu tiên của em.** `test_a_missing_font_does_not_break_the_turn` chạy với thư mục font không tồn tại, kỳ vọng `None`, nhưng nhận về một ảnh PNG hoàn chỉnh.

Nguyên nhân: `ImageFont.truetype` khi không thấy file ở đường dẫn đã cho sẽ **tự tìm font hệ thống theo tên**. Máy này có `DejaVuSans.ttf` nên nó vẽ được như không có chuyện gì.

Hậu quả nếu để nguyên: hai máy có hai phiên bản DejaVu khác nhau sẽ render ra hai chuỗi byte khác nhau, và E2E A9-2 sẽ đỏ ngẫu nhiên ở nơi không ai ngờ tới. Đã sửa: `_load_fonts` kiểm tra `path.is_file()` trước, thiếu file là `ComparisonImageError`, không để Pillow tự thay thế.

### (d) Đột biến kiểm chứng ràng buộc loại xe

Tạm bỏ kiểm tra trộn loại xe trong `_reject_cross_vehicle_type` → `test_a_table_mixing_vehicle_types_is_refused` **đỏ**. Khôi phục → xanh.

## 3. Kết quả 3 lệnh kiểm tra

```
$ uv run pytest tests/agents -q
260 passed, 1 warning in 210.60s (0:03:30)

$ uv run ruff check src/agents tests/agents
All checks passed!

$ uv run mypy src/agents
src/agents/adapters/feature_retriever.py:131: error: Argument "status" to "FeatureAssertion" has incompatible type "str"; expected "Literal['YES', 'NO', 'UNKNOWN']"  [arg-type]
src/agents/adapters/feature_retriever.py:282: error: Incompatible types in assignment (expression has type "float", variable has type "SQLCoreOperations[Decimal | None] | Decimal | None")  [assignment]
Found 2 errors in 1 file (checked 64 source files)
```

Ghi chú về mypy: vẫn đúng 2 lỗi tồn đọng của Khối 1 (Dương), không phải do task này.

## 4. Toàn bộ suite

| Mốc | Kết quả |
|---|---|
| Trước task này | `6 failed, 997 passed, 4 skipped, 102 errors` |
| Sau task này | `6 failed, 1012 passed, 4 skipped, 102 errors` |

- Chênh lệch đúng **+15 passed** = 11 test unit + 4 test giao ảnh. `failed` và `errors` **không đổi**.
- Contract dùng chung: **không sửa** `ports.py`, `contracts.py`, `state.py`, `domain/values.py`, `services/registry.py`, `composition.py`, `nodes/__init__.py`.
- `domain/comparison.py` của Ngọc chỉ được **đọc**, không sửa một dòng.

## 5. Điểm lệch so với plan

Bảy điểm ở mục "Cần chốt trước khi code" đã được anh Long uỷ quyền quyết hết. Quyết định cuối:

| # | Điểm | Quyết định | Lý do |
|---|---|---|---|
| 1 | Nơi lưu ảnh | **Lưu ra đĩa** theo `run_id` (`ComparisonImageStore`), endpoint gửi khách trả base64 | Xem phần đổi ý bên dưới |
| 2 | Hình dạng dữ liệu đầu vào | Dùng thẳng `ComparisonTable` của Ngọc trong `domain/comparison.py` | A5-4 **đã code xong** nên không phải đoán contract; không có nguy cơ sửa assert lúc ráp |
| 3 | Thư viện render | **Pillow** (`uv add pillow`) | Dự án chưa có thư viện ảnh nào; Pillow cho phép tắt metadata để đạt byte-identical |
| 4 | Định dạng đầu ra | **PNG** | Cột Test bắt buộc nói "byte-identical"; "slide" chỉ là mô tả bố cục |
| 5 | Font | **Đóng gói DejaVuSans + Bold vào `src/agents/assets/fonts/`** | Dùng font hệ thống là phá byte-identical giữa các máy — xem bẫy (c) |
| 6 | Đường ảnh tới khách | Dùng lại đúng cửa `deliver` của A7-3 | Không mở cửa thứ hai; ảnh thừa hưởng nguyên chốt chặn 409 đã có |
| 7 | Số mẫu trên ảnh | 2–3, đúng như A5-4 | Kế thừa ràng buộc, có test âm cho 1 mẫu và 4 mẫu |

**Một quyết định đã đổi giữa chừng, ghi rõ để không bị hiểu là sai sót:**

Ban đầu em chốt điểm 1 là "trả base64, không lưu gì". Khi viết test cho dòng "ảnh vẫn qua HITL A7" mới lộ ra lỗ: ảnh sinh ở **lượt chat**, còn ảnh được gửi ở **bước duyệt sau đó** — hai thời điểm khác nhau, base64 trong bộ nhớ không sống qua được ranh giới ấy. Đã đổi sang lưu ra đĩa theo `run_id`; endpoint vẫn trả base64 cho FE. Không cần thêm cột vào bảng nào, không cần migration.

**Đã cân nhắc rồi chốt giữ nguyên (2026-08-09):** có đề xuất chuyển kho ảnh sang MinIO (dự án đã chạy sẵn, module document đang dùng) hoặc lưu URL vào DB kèm migration `agent_0007`. Anh Long chốt **giữ phương án ban đầu** — lưu đĩa server, trả base64. Giới hạn đã biết: khi nào nhân bản app lên nhiều instance thì mỗi instance có một kho ảnh riêng, lúc đó phải chuyển sang kho dùng chung. Hiện `docker-compose.yml` chỉ chạy một bản app nên chưa ảnh hưởng.

**Hai việc còn lại của task, nằm ngoài phạm vi phần Long:**

| Việc | Ai làm | Trạng thái |
|---|---|---|
| Node gọi service, chèn vào graph sau A5-4 trước A5-6 | Đạt | Chưa làm — service đã sẵn sàng để gọi |
| Thêm field `comparison_image_url` vào `AgentState` | Cả 4 người duyệt (PR contract theo luật A0 §2.2) | Chưa mở PR |

Service đã có sẵn hai lối gọi để Đạt lắp vào: `render_comparison_image(table)` khi muốn lỗi nổ ra, và `render_comparison_image_or_none(table)` cho đường chạy thật của lượt chat. Lưu ảnh bằng `ComparisonImageStore(...).save(run_id, image)`.
