# Integration Test Safety Runbook

## Mục đích

Runbook này hướng dẫn chạy integration test có PostgreSQL/MinIO mà không tác động DB dev, staging hoặc production.

`Integration test` là test nhiều thành phần phối hợp với nhau, ví dụ API + repository + PostgreSQL + MinIO + migration. Nó không phải test merge nhánh Git. `Image` là module quản lý ảnh của ứng dụng, không phải Docker image.

## Quy tắc bắt buộc

1. Không đặt `TEST_DATABASE_ADMIN_URL` bằng credential có quyền truy cập DB dev/staging/production.
2. Không đặt `DOCUMENT_DATABASE_URL` hoặc `AUTH_DATABASE_URL` của môi trường thật trước khi chạy full suite.
3. Chỉ DB có dạng `p150_<module>_test_<uuid>` mới được phép truncate/drop/downgrade.
4. Chỉ bucket có dạng `document-test-<uuid>` hoặc `image-test-<uuid>` mới được phép cleanup.
5. Không chạy test nếu coding agent chưa xác nhận guard đang hoạt động.

## Chuẩn bị local

Khởi động PostgreSQL và MinIO test service riêng. File Compose này dùng cổng và vùng dữ liệu tạm, không dùng chung volume với stack dev:

```powershell
docker compose -f docker-compose.test.yml -p p150-integration-test up -d --wait
```

Thiết lập biến trong PowerShell hiện tại, sử dụng credential test riêng:

```powershell
$env:TEST_DATABASE_ADMIN_URL = "postgresql+asyncpg://p150_test_admin:p150_test_only_password@localhost:55432/postgres"
$env:DOCUMENT_MINIO_ENDPOINT = "http://localhost:19000"
$env:DOCUMENT_ACCESS_KEY = "p150_test_minio"
$env:DOCUMENT_SECRET_KEY = "p150_test_minio_password"
```

Không lưu credential thật vào `.env.test.example` hoặc Git.

Sau khi test xong, xóa đúng stack test dùng một lần:

```powershell
docker compose -f docker-compose.test.yml -p p150-integration-test down -v
```

## Lệnh chạy

Chạy safety contract trước:

```powershell
pytest tests/test_integration_database_safety.py -v --tb=short
```

Sau đó mới chạy từng module:

```powershell
pytest tests/document/integration/ -v --tb=short
pytest tests/images/integration/ -v --tb=short
```

Cuối cùng mới chạy full suite:

```powershell
ruff check src/ tests/
pytest tests/ -v --tb=short
```

## Dấu hiệu chạy đúng

- PostgreSQL chỉ xuất hiện DB tạm có prefix `p150_document_test_` hoặc `p150_image_test_`.
- Mỗi tên kết thúc bằng UUID 32 ký tự hex.
- Test kết thúc thì các DB tạm không còn tồn tại.
- MinIO bucket test có prefix đúng và được xóa khi test kết thúc.
- Count/checksum các bảng dev không thay đổi.

## Fail-safe mong đợi

Fixture phải dừng trước destructive SQL nếu:

- thiếu `TEST_DATABASE_ADMIN_URL`;
- URL không phải PostgreSQL;
- connection live không trỏ đúng DB fixture đã tạo;
- DB name là `p150_auth`, `postgres`, template DB hoặc chứa `prod`;
- DB name không có prefix/UUID hợp lệ;
- teardown được yêu cầu xóa DB/bucket không thuộc fixture hiện tại.

Thiếu biến cấu hình test thì test DB-dependent được skip an toàn; không được fallback về DB dev.

## DB tạm bị sót sau khi process bị kill

Không xóa bằng wildcard ngay lập tức. Trước tiên:

1. Liệt kê tên DB và xác nhận đúng prefix + UUID.
2. Xác nhận không còn pytest process sử dụng DB đó.
3. Dùng test admin role terminate connection của đúng tên DB.
4. Drop từng DB đã xác minh.

Không drop `p150_auth`, `postgres`, `template0`, `template1` hoặc bất kỳ tên nào chứa `prod`.

## Build và deploy

- CI test job dùng PostgreSQL/MinIO service dùng một lần.
- Runtime image build không cần kết nối DB dev.
- Deploy chỉ chạy migration `upgrade head` sau backup.
- Deploy không chạy pytest, `downgrade`, `TRUNCATE` hoặc seed `--truncate` trên môi trường đích.

## Corpus bảo hành

Isolation chỉ ngăn tái diễn mất dữ liệu; nó không tự khôi phục corpus. Khôi phục `vehicle_documents` phải là workflow riêng, có nguồn authoritative, source hash/revision, embedding model/version, row count/checksum và canary policy QA.
