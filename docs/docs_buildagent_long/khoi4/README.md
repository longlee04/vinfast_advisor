# Thứ tự thực thi — Khối 4 (Long)

10 task, xếp theo phụ thuộc đã ghi ở mục 2 của từng file.

| Thứ tự | Task | File | Lý do đứng ở vị trí này | Nghiệm thu |
|---:|---|---|---|---|
| 1 | A7-1 | Đã thực thi | Không ghi phụ thuộc nào. Migration `agent_0004` tạo `review_queue` — mọi task A7 sau đó thao tác trên bảng này. | ✅ [nghiemthu/A7-1.md](nghiemthu/A7-1.md) |
| 2 | A8-1 | Đã thực thi | Không ghi phụ thuộc nào. `agent_0005` có `down_revision = "agent_0004"` nên chuỗi migration phải đứng sau A7-1. Làm sớm để mở khoá A8-4. | ✅ [nghiemthu/A8-1.md](nghiemthu/A8-1.md) |
| 3 | A7-2 | Đã thực thi | Không ghi phụ thuộc nào. Cần bảng `review_queue` của A7-1. Claim là bước đứng trước mọi hành động duyệt. | ✅ [nghiemthu/A7-2.md](nghiemthu/A7-2.md) |
| 4 | A8-4 | Đã thực thi | Không ghi phụ thuộc nào, chỉ cần schema của A8-1. **Đẩy lên sớm vì A10-5 của Dương ghi rõ "chờ A8-4 Long"** — để muộn là chặn Khối 1. | ✅ [nghiemthu/A8-4.md](nghiemthu/A8-4.md) |
| 5 | A8-3 | Đã thực thi | Không ghi phụ thuộc nào, chỉ cần schema của A8-1. Độc lập với luồng duyệt nên xen vào lúc đang chờ A6-1 của Ngọc. | ✅ [nghiemthu/A8-3.md](nghiemthu/A8-3.md) |
| 6 | A7-3 | Đã thực thi | Task duy nhất có chú thích phụ thuộc khối khác: **"chờ A6-1 Ngọc — `INSERT` tay"**. Cần A7-2 xong trước vì duyệt thao tác trên mục đã claim. Đây là chỗ dựng fake sẽ xoá ở Ráp 3. | ✅ [nghiemthu/A7-3.md](nghiemthu/A7-3.md) |
| 7 | A8-2 | Đã thực thi | Test đòi "run **chưa duyệt** → bị chặn" (cần trạng thái duyệt của A7-3) và "ghi `internal_notices`" (cần A8-1 + luồng notice A8-4). | ✅ [nghiemthu/A8-2.md](nghiemthu/A8-2.md) |
| 8 | A9-1 | Đã thực thi | View `funnel_metrics` đọc `test_drive_bookings` — cần A8-1; kiểm chéo số liệu có ý nghĩa khi luồng booking A8-2 đã chạy. | ✅ [nghiemthu/A9-1.md](nghiemthu/A9-1.md) |
| 9 | A9-2 | [A9-2.md](A9-2.md) | Mục "Ba điểm ráp chung": **"Cuối — A9-2 E2E + A9-3 KPI — Long chủ trì, cần cả 4 người xác nhận xong phần mình."** Phải sau Ráp 3 (xoá `INSERT` tay) và sau A9-1. | ⛔ **bị chặn** — Khối 1/2/3 chưa xong |
| 10 | A9-3 | [A9-3.md](A9-3.md) | Cột Test bắt buộc có dòng "**bật/tắt judge không đổi kết quả E2E A9-2**" → bắt buộc đứng sau A9-2. | 🟡 [nghiemthu/A9-3-phan-1.md](nghiemthu/A9-3-phan-1.md) — xong phần không bị chặn |

## Ba mốc phụ thuộc chéo

- **Chờ khối khác:** chỉ A7-3 (chờ A6-1 của Ngọc) — né tạm bằng `INSERT` tay, xoá ở Ráp 3.
- **Bị khối khác chờ:** A8-4 (A10-5 của Dương chờ) — nên làm sớm, đã đẩy lên vị trí 4.
- **Chờ cả nhóm:** A9-2 và A9-3 — theo mục "Ba điểm ráp chung", cần cả 4 người xác nhận xong phần mình.

## Trạng thái (cập nhật 2026-08-09)

- **8/10 task nghiệm thu xong**, mỗi task một commit và một file trong `nghiemthu/`.
- **A9-2 bị chặn thật:** 10/13 node trong `src/agents/nodes/` vẫn là stub, `src/agents/chain.py` và `src/agents/api/routes.py` (Khối 2 — Đạt) chưa tồn tại, và Ráp 3 chưa làm được vì A6-1 của Ngọc chưa có. E2E không mock quanh được.
- **A9-3 làm trước phần không bị chặn:** bộ 55 câu hỏi, ba KPI, khung judge, test biên một chiều. Phần "số thật" và đo tải chờ A9-2.
