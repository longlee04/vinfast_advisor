# Runbook: đồng bộ ảnh xe vào MinIO

Ảnh so sánh gửi khách đọc từ `vehicles.image_object_key`. Khi cột này rỗng,
bảng so sánh vẫn dựng được nhưng mọi xe ra ô giữ chỗ mang tên mẫu.

## Khi nào chạy

- Sau khi seed hoặc cập nhật catalog xe.
- Sau khi đổi `vehicles.image_url` của bất kỳ mẫu nào.
- Sau khi dựng lại volume MinIO.

## Điều kiện

- `p-150-minio-1` đang chạy và healthy.
- `.env` có `DOCUMENT_MINIO_ENDPOINT`, `DOCUMENT_BUCKET_NAME`,
  `DOCUMENT_ACCESS_KEY`, `DOCUMENT_SECRET_KEY`, `DOCUMENT_DATABASE_URL`.

## Lệnh

    set -a; source .env; set +a
    uv run python -m src.products.cli.sync_vehicle_images

Kết quả in ra `synced=<n> skipped=<n> failed=<n>`. Lệnh idempotent: chạy lần
hai trên dữ liệu không đổi cho `synced=0`.

## Kiểm chứng

    docker exec -e PGPASSWORD=change-me-locally p-150-postgres-1 \
      psql -U p150_auth -d p150_auth -tA \
      -c "select count(*) filter (where image_object_key is not null), count(*) from vehicles"

## Kết quả lần chạy đầu (2026-08-12)

- Trước khi chạy: `0|51`.
- Lần chạy đầu: `synced=49 skipped=0 failed=2`; sau đó dữ liệu là `49|49|51`
  (`image_object_key` và `image_sha256` khớp nhau).
- Lần chạy lại ngay sau: `synced=0 skipped=48 failed=3`. `synced=0` là bằng
  chứng idempotent. Số `failed` xê dịch giữa hai lần vì vài URL nguồn ở
  `vinfastvietnam.com.vn` tải chập chờn, không phải lỗi của lệnh.

## Xử lý sự cố

- `failed > 0`: URL ảnh của một số xe hỏng hoặc quá `8 MiB`. Lệnh giữ nguyên
  asset cũ cho những xe đó, không xoá. Sửa `vehicles.image_url` rồi chạy lại.
  Nếu `failed` đổi số giữa các lần chạy trong khi dữ liệu không đổi, nguyên
  nhân là URL nguồn tải chập chờn — chạy lại để phủ nốt.
- Ảnh vẫn ra ô giữ chỗ sau khi đồng bộ: kiểm tra API và lệnh đồng bộ dùng cùng
  `DOCUMENT_BUCKET_NAME`, và `AGENT_DATABASE_URL` trỏ cùng database với
  `DOCUMENT_DATABASE_URL`.
