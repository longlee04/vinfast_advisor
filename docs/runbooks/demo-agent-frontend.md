# Runbook: demo luồng agent trên frontend

Chạy đầy đủ luồng agent từ giao diện frontend: khách chat → agent dựng nháp kèm ảnh so sánh → tư vấn viên thấy hàng đợi, duyệt → khách nhận nội dung đã phê duyệt trên giao diện.

## Chuẩn bị một lần

- Ảnh xe đã đồng bộ vào MinIO: xem `docs/runbooks/dong-bo-anh-xe.md`.
- `.env` có `COMPARISON_IMAGE_DIR` trỏ thư mục tài khoản đang chạy ghi được (xem `docs/runbooks/dong-bo-anh-xe.md`).
- `frontend/.env.local` có `NEXT_PUBLIC_DEMO_MODE=false` và
  `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1`.
- Có sẵn một tài khoản vai `customer` với email domain `@gmail.com` và một vai `advisor` (có thể từ `scripts/seed_auth_users.py` hoặc `uv run python -m src.cli create-staff`).

## Chạy

Mở hai terminal tách biệt.

**Terminal 1: Dừng container backend cũ và khởi động backend local:**

    docker stop p-150-backend-1
    cd /home/pdat1301/Documents/git/P-150
    set -a; source .env; set +a
    export LANGCHAIN_TRACING_V2=false LANGSMITH_TRACING=false
    uv run uvicorn src.main:app --port 8000

Kết quả mong đợi: `curl -s localhost:8000/health` trả `{"status":"ok",...}`.

**Terminal 2: Khởi động frontend (sau khi backend sẵn sàng):**

    cd /home/pdat1301/Documents/git/P-150/frontend
    npm run dev

Kết quả mong đợi: dev server in ra `ready on http://localhost:3000`.

Nếu đã chạy `npm run dev` trước đó (trước khi cập nhật `.env.local`), phải dừng và khởi động lại để Next.js đọc lại biến `NEXT_PUBLIC_*`.

## Kịch bản trình diễn

Mở hai cửa sổ trình duyệt tách biệt (một cửa sổ ẩn danh) để hai phiên đăng nhập khách hàng và tư vấn viên không đè cookie của nhau.

### Cửa sổ 1: Khách hàng

1. Vào `http://localhost:3000/login`.
2. Đăng nhập với email `@gmail.com` của vai `customer`.
3. Sau khi đăng nhập, vào `/consultation`.
4. Gửi tin nhắn đầu tiên, ví dụ: "Tôi cần xe điện 5 chỗ, ngân sách 800 triệu".
5. Trả lời các câu hỏi mà agent đặt ra cho tới khi màn hình chuyển sang trạng thái "Đề xuất đang được tư vấn viên kiểm tra".
6. **Giữ tab này mở, không đóng cũng không tải lại** để nhận update từ backend qua SSE.

### Cửa sổ 2: Tư vấn viên (ẩn danh)

1. Mở một cửa sổ ẩn danh (Incognito / Private).
2. Vào `http://localhost:3000/staff-login`.
3. Đăng nhập với email và mật khẩu của vai `advisor` (domain `@vinfast.local` nếu từ seed).
4. Sau khi đăng nhập, vào `/advisor`.
5. Tìm mục vừa tạo từ bước khách ở cửa sổ 1 (status `PENDING`, chứa nội dung bản nháp).
6. Bấm "Xem & duyệt" để mở chi tiết.
7. **Kiểm tra ảnh so sánh có hiện ra** trong phần bản nháp (nếu run có từ 2 xe được xếp hạng; nếu chỉ 1 xe hoặc không xếp được, sẽ có cảnh báo "Chưa dựng được ảnh so sánh").
8. Bấm "Duyệt nguyên trạng" để phê duyệt.

### Cửa sổ 1: Quay lại khách hàng

- Không cần làm gì thêm: trang sẽ **tự động cập nhật** nội dung đã duyệt kèm ảnh so sánh (qua SSE) **mà không cần tải lại trang**.
- Nếu sau vài giây vẫn không thấy cập nhật, tải lại trang một lần để chắc chắn.

## Giới hạn đã biết

- `InMemoryTurnEventBroker` chỉ sống trong một process: không chạy uvicorn với
  `--workers > 1`, SSE sẽ im lặng.
- Hai vai (khách và tư vấn viên) phải ở hai cửa sổ tách biệt; đăng nhập chồng sẽ ghi đè cookie phiên và làm hỏng trải nghiệm.
- Email khách bắt buộc domain `@gmail.com`; nhân sự đăng nhập ở `/staff-login` với email riêng (thường `@vinfast.local`).
- Bước chat gọi LLM thật, cần `OPENAI_API_KEY` hợp lệ trong `.env`.
- Ảnh so sánh chỉ có khi run có từ hai xe được xếp hạng; ít hơn thì màn duyệt
  hiện cảnh báo "Chưa dựng được ảnh so sánh cho mục này".
- Backend cũ (container `p-150-backend-1`) không có endpoint `/api/v1/agent/review`, nên phải dừng container trước khi chạy backend local trên cùng cổng 8000.
- `npm run dev` đọc biến `.env.local` tại lúc dev-server khởi động, nên nếu đã chạy dev-server rồi mới cập nhật `.env.local`, phải dừng và khởi động lại `npm run dev`.
- Một số phiên kết thúc với `terminal_reason: GUARDRAIL_FAILED_ADVISOR_HANDOFF` thay vì tiếp tục tới hàng đợi duyệt; đó là guardrail backend từ chối bản nháp sau khi retry. Không phải lỗi UI. Tạo phiên mới để tiếp tục.
- `npm run build` hiện có 4 lỗi TypeScript pre-existing ở `src/components/showroom/` liên quan đến module `@/data/vinfast-models` chưa tồn tại, nhưng không ảnh hưởng `npm run dev` (được dùng trong demo).
