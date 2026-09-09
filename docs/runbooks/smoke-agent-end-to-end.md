# Runbook: kiểm chứng chuỗi agent end-to-end trên app thật

Chạy đúng một lần chuỗi đầy đủ trên `src/main.py`: khách chat → agent dựng nháp
→ tư vấn viên thấy hàng đợi, đọc bản nháp → duyệt → khách nhận nội dung.

Mọi lệnh dưới đây chạy từ gốc repo. Đặt biến môi trường trước:

    set -a; source .env; set +a
    export LANGCHAIN_TRACING_V2=false LANGSMITH_TRACING=false

Auth chặn theo `Origin`, nên mọi lệnh `curl` phải mang header
`Origin: http://localhost:3000` (đúng giá trị `AUTH_FRONTEND_ORIGIN` trong `.env`).

## 1. Khởi động API

    uv run uvicorn src.main:app --port 8077

Kết quả mong đợi: `curl -s localhost:8077/health` trả `{"status":"ok",...}`.

## 2. Tài khoản

Khách và nhân sự đăng nhập ở **hai đường khác nhau**, và email khách bắt buộc
domain `@gmail.com` (`NormalizedEmail.parse_customer`):

- khách: `POST /api/v1/auth/login`
- tư vấn viên: `POST /api/v1/auth/staff/login`

`POST /api/v1/auth/register` đang tắt (`registration_unavailable`), nên tài khoản
smoke tạo bằng `scripts/seed_auth_users.py` hoặc `uv run python -m src.cli create-staff`.

    O='Origin: http://localhost:3000'
    curl -s -c /tmp/khach.txt -X POST localhost:8077/api/v1/auth/login -H "$O" \
      -H 'Content-Type: application/json' \
      -d '{"email":"<khach>@gmail.com","password":"<mat-khau>"}'
    curl -s -b /tmp/khach.txt -H "$O" localhost:8077/api/v1/auth/me

Kết quả mong đợi: `/auth/me` trả hồ sơ khách, không phải 401.

## 3. Gửi lượt chat

    SESSION=$(python3 -c "import uuid;print(uuid.uuid4())")
    curl -s -b /tmp/khach.txt -H "$O" -X POST localhost:8077/api/v1/agent/turn \
      -H 'Content-Type: application/json' \
      -d "{\"session_id\":\"$SESSION\",\"message\":\"Toi can xe dien 5 cho, ngan sach 800 trieu\"}"

Kết quả mong đợi: HTTP 200 với `pending_question`. Không cần tạo phiên trước:
lượt đầu tự mở phiên cho đúng chủ sở hữu. Trả lời tiếp các câu hỏi cho tới khi
`answer` là thông báo "đang gửi tư vấn viên kiểm tra".

Slot bắt buộc gồm cả số chỗ; câu trả lời gộp nhiều ý có thể không trích đủ, khi
đó trả lời thẳng vào câu đang hỏi (ví dụ `Xe cho 5 nguoi`).

## 4. Hàng đợi của tư vấn viên

    curl -s -c /tmp/tuvan.txt -X POST localhost:8077/api/v1/auth/staff/login -H "$O" \
      -H 'Content-Type: application/json' \
      -d '{"email":"<tuvan>@vinfast.local","password":"<mat-khau>"}'
    curl -s -b /tmp/tuvan.txt -H "$O" localhost:8077/api/v1/agent/review

Kết quả mong đợi: mảng có ít nhất một phần tử `status: PENDING` kèm `content`.
Lấy `review_id` cho các bước sau.

## 5. Đọc chi tiết kèm ảnh so sánh

    curl -s -b /tmp/tuvan.txt -H "$O" localhost:8077/api/v1/agent/review/$REVIEW \
      | python3 -c "import json,sys,base64;d=json.load(sys.stdin);print('status',d['status']);print('len_content',len(d['content']));img=d['comparison_image_base64'];print('anh_png', bool(img) and base64.b64decode(img).startswith(b'\x89PNG'))"

Kết quả mong đợi: `status PENDING`, `len_content` lớn hơn 0, `anh_png True`.

## 6. Mở SSE rồi duyệt

Terminal riêng:

    curl -N -b /tmp/khach.txt -H "$O" localhost:8077/api/v1/agent/events/$SESSION

Terminal chính:

    curl -s -b /tmp/tuvan.txt -H "$O" -X POST localhost:8077/api/v1/agent/review/$REVIEW/claim
    curl -s -b /tmp/tuvan.txt -H "$O" -X POST localhost:8077/api/v1/agent/review/$REVIEW/approve \
      -H 'Content-Type: application/json' -d '{}'

Kết quả mong đợi: claim trả `{"granted":true}`, và terminal SSE in ra
`data: {"review_id":"<REVIEW>"}` ngay sau lệnh approve.

## 7. Khách lấy nội dung đã duyệt

    curl -s -b /tmp/khach.txt -H "$O" localhost:8077/api/v1/agent/deliveries/$SESSION \
      | python3 -c "import json,sys,base64;d=json.load(sys.stdin);i=d['items'][0];print('len_content',len(i['content']));img=i['comparison_image_base64'];print('anh_png', bool(img) and base64.b64decode(img).startswith(b'\x89PNG'))"

## 8. Kiểm chứng dữ liệu

    docker exec -e PGPASSWORD=change-me-locally p-150-postgres-1 \
      psql -U p150_auth -d p150_auth -tA \
      -c "select status, count(*) from review_queue group by status"

Kết quả mong đợi: có ít nhất một dòng `APPROVED|1`.

## Giới hạn đã biết

- Ảnh so sánh cache vào `data/comparison_images`. Thư mục `data/` do container
  tạo nên thuộc `root`; khi chạy uvicorn bằng tài khoản thường,
  `image_for_review` nuốt `PermissionError` và trả ảnh `null`. Cấp quyền một lần
  trước khi smoke: `sudo chown -R $USER:$USER data`.
- `InMemoryTurnEventBroker` chỉ sống trong một process. Chạy uvicorn với
  `--workers > 1` sẽ khiến SSE im lặng không nhận event. Không tăng `--workers`
  khi chưa thay broker bằng bản chia sẻ giữa process.
- PostgreSQL cảnh báo collation version mismatch (database tạo ở `2.41`, OS cho
  `2.36`) trên mọi truy vấn. Cảnh báo này không làm sai kết quả và nằm ngoài
  phạm vi plan.
- Bước gửi lượt chat gọi LLM thật, nên cần `OPENAI_API_KEY` hợp lệ trong `.env`.
- uvicorn định tuyến log qua cấu hình của app: traceback của lỗi 500 nằm ở
  `logs/app.log`, không nằm ở stdout của tiến trình.
