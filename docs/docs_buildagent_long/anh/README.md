# Task ảnh so sánh mẫu xe trong chat

| | |
|---|---|
| **Định danh** | `comparison-image` (chưa có ID chính thức trong `vinfast-agent-mvp.md`) |
| **Phần của Long** | Service render ảnh — `services/operations/comparison_image.py` |
| **Trạng thái** | ✅ **Đã code xong**, 15 test xanh |
| **Nghiệm thu** | [nghiemthu/comparison-image.md](nghiemthu/comparison-image.md) |

## Bảy điểm chờ chốt — đã chốt hết

| # | Điểm | Quyết định |
|---|---|---|
| 1 | Nơi lưu ảnh | Lưu ra đĩa theo `run_id`; endpoint gửi khách trả base64. Đã cân nhắc MinIO / URL trong DB, chốt giữ nguyên — xem lại khi app chạy nhiều instance |
| 2 | Hình dạng dữ liệu đầu vào | `ComparisonTable` của Ngọc (`domain/comparison.py`) — A5-4 đã xong nên không phải đoán |
| 3 | Thư viện render | Pillow (đã thêm vào `pyproject.toml`) |
| 4 | Định dạng đầu ra | PNG |
| 5 | Font | DejaVuSans + Bold đóng gói trong `src/agents/assets/fonts/` |
| 6 | Đường ảnh tới khách | Dùng lại cửa `deliver` của A7-3, không mở cửa thứ hai |
| 7 | Số mẫu trên ảnh | 2–3, đúng như A5-4 |

## Ngoài phạm vi phần Long — chưa làm

| Việc | Ai làm |
|---|---|
| Node gọi service, chèn vào graph sau A5-4 trước A5-6 | Đạt |
| Thêm field `comparison_image_url` vào `AgentState` | Cả 4 người duyệt — PR contract riêng theo luật A0 §2.2 |
