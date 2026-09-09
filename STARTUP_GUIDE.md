# Hướng dẫn khởi động dự án và mở Swagger

Tài liệu này hướng dẫn người mới chạy dự án P-150 trên máy local và mở Swagger UI để thử các API Chat, Auth và Document.

> Phạm vi: môi trường phát triển local. Không dùng các giá trị bên dưới cho production.

## 1. Các thành phần sau khi khởi động

| Thành phần | Địa chỉ |
|---|---|
| FastAPI backend mặc định | http://localhost:8000 |
| Swagger UI mặc định | http://localhost:8000/docs |
| OpenAPI JSON | http://localhost:8000/openapi.json |
| PostgreSQL | localhost:5432 |
| MinIO API | http://localhost:9000 |
| MinIO Console | http://localhost:9001 |
| pgAdmin | http://localhost:5050 |

Khi cần xem **Auth và Document cùng lúc trên Swagger**, chạy một tiến trình FastAPI riêng ở cổng `8001`. Khi đó mở:

```text
http://localhost:8001/docs
```

Cổng `8001` không phải cổng mặc định của Docker Compose. Đây là cổng local tùy chọn để chạy Swagger với Auth và Document đã bật.

## 2. Yêu cầu cài đặt

Cần có:

- Python 3.11 trở lên.
- Git.
- Docker Desktop hoặc Docker Engine có Docker Compose.
- `uv` để cài dependency và chạy lệnh Python.
- Terminal Bash hoặc terminal tương đương.
- Trình duyệt web như Chrome, Firefox hoặc Edge.

Kiểm tra nhanh:

```bash
python --version
git --version
docker --version
docker compose version
uv --version
```

Nếu chưa có `uv`, cài trên Linux/macOS bằng:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Sau khi cài, đóng và mở lại terminal nếu lệnh `uv` chưa được nhận diện.

## 3. Clone dự án

Nếu chưa có mã nguồn:

```bash
git clone <URL_REPOSITORY>
cd P-150
```

Nếu dự án đã có trên máy:

```bash
cd /duong/dan/toi/P-150
```

Kiểm tra bạn đang đứng ở thư mục gốc. Thư mục này phải có các file như:

```text
pyproject.toml
docker-compose.yml
.env.example
alembic-auth.ini
alembic-document.ini
src/
tests/
```

## 4. Cài dependency Python

Tại thư mục gốc dự án, chạy:

```bash
uv sync --locked
```

Lệnh này tạo hoặc cập nhật môi trường Python của dự án dựa trên `uv.lock`.

Nếu `--locked` báo lockfile chưa đồng bộ, không tự ý sửa dependency. Báo lại cho người phụ trách dự án để kiểm tra `pyproject.toml` và `uv.lock`.

## 5. Tạo file môi trường `.env`

Copy file mẫu:

```bash
cp .env.example .env
```

Mở `.env` bằng VS Code hoặc trình soạn thảo bạn thường dùng:

```bash
code .env
```

Nếu không dùng VS Code:

```bash
nano .env
```

### 5.1. Cấu hình local cơ bản

Các giá trị PostgreSQL local phải khớp với service `postgres` trong `docker-compose.yml`:

```dotenv
POSTGRES_USER=p150_auth
POSTGRES_PASSWORD=change-me-locally
POSTGRES_DB=p150_auth
PGADMIN_PORT=5050
PGADMIN_DEFAULT_EMAIL=admin@example.com
PGADMIN_DEFAULT_PASSWORD=change-me-locally
APP_ENV=development
APP_PORT=8000
APP_HOST=0.0.0.0
```

Nếu Docker volume PostgreSQL đã được khởi tạo trước đó, thay đổi `POSTGRES_PASSWORD` trong `.env` không đổi mật khẩu đã lưu trong database. Khi gặp lỗi đăng nhập PostgreSQL, cần dùng đúng mật khẩu của volume hiện tại hoặc nhờ người quản lý môi trường xử lý. Không xóa volume để chữa lỗi nếu chưa được phép.

### 5.2. Cấu hình Auth

Auth là module tùy chọn. Để chạy các Auth API, đặt:

```dotenv
AUTH_ENABLED=true
AUTH_DATABASE_URL=postgresql+asyncpg://p150_auth:change-me-locally@localhost:5432/p150_auth
AUTH_JWT_ALGORITHM=HS256
AUTH_JWT_ISSUER=p150-auth
AUTH_JWT_AUDIENCE=p150-app
AUTH_CORS_ORIGINS=http://localhost:3000,http://localhost:5173
AUTH_FRONTEND_ORIGIN=http://localhost:3000
AUTH_COOKIE_SECURE=false
AUTH_SENDGRID_API_KEY=local-placeholder
AUTH_SENDGRID_FROM_EMAIL=noreply@localhost
```

Tạo hai secret riêng biệt:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Gán kết quả vào:

```dotenv
AUTH_JWT_SIGNING_KEY=<ket-qua-lenh-thu-nhat>
AUTH_CSRF_SECRET=<ket-qua-lenh-thu-hai>
```

Hai secret phải khác nhau, đủ dài và không được chứa giá trị mẫu như `change-me`.

`AUTH_COOKIE_SECURE=false` chỉ dùng cho local HTTP. Production phải dùng HTTPS và cookie Secure.

### 5.3. Cấu hình Document và MinIO

Document cũng là module tùy chọn. Để hiển thị Document API trên Swagger, đặt:

```dotenv
DOCUMENT_ENABLED=true
DOCUMENT_DATABASE_URL=postgresql+asyncpg://p150_auth:change-me-locally@localhost:5432/p150_auth
DOCUMENT_MINIO_ENDPOINT=http://localhost:9000
DOCUMENT_BUCKET_NAME=documents
DOCUMENT_ACCESS_KEY=p150_minio
DOCUMENT_SECRET_KEY=p150_minio_test_secret
DOCUMENT_BUCKET_PRIVATE=true
```

Document yêu cầu:

- PostgreSQL URL dùng driver `postgresql+asyncpg`.
- MinIO đang chạy tại `http://localhost:9000`.
- Bucket phải là private.
- Access key và secret key phải khớp cấu hình MinIO local.
- Database Document phải được migrate trước khi bật module.

> Nếu Auth và Document dùng chung database local, chỉ chạy migration khi database đang ở trạng thái đúng. Nếu dùng database riêng, thay URL bằng database tương ứng. Không ghi đè lịch sử migration, không xóa database/bảng và không xóa Docker volume để bỏ qua lỗi migration.

## 6. Kiểm tra secrets không bị commit

Kiểm tra `.env` đã bị Git bỏ qua:

```bash
git check-ignore -v .env
```

Lệnh phải trả về rule trong `.gitignore`. Không chạy các lệnh như sau:

```bash
git add .env
git commit -m "add env"
```

Không đưa các giá trị sau vào Git:

- `AUTH_JWT_SIGNING_KEY`.
- `AUTH_CSRF_SECRET`.
- `AUTH_SENDGRID_API_KEY`.
- `DOCUMENT_SECRET_KEY`.
- Mật khẩu PostgreSQL, pgAdmin hoặc production token.

## 7. Khởi động PostgreSQL, MinIO và pgAdmin

Khởi động các service nền:

```bash
docker compose up -d postgres minio pgadmin
```

Kiểm tra trạng thái:

```bash
docker compose ps
```

PostgreSQL phải có trạng thái `healthy`. MinIO cũng phải đang chạy.

Kiểm tra PostgreSQL:

```bash
docker compose exec postgres pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"
```

Nếu biến môi trường chưa được nạp vào shell, dùng giá trị local rõ ràng:

```bash
docker compose exec postgres pg_isready -U p150_auth -d p150_auth
```

Kiểm tra MinIO:

```bash
curl -fsS http://localhost:9000/minio/health/live
```

Nếu trả về phản hồi thành công, MinIO đã sẵn sàng.

## 8. Chạy migration cho Auth

Chỉ chạy bước này khi `AUTH_ENABLED=true`:

```bash
uv run alembic -c alembic-auth.ini upgrade head
```

Lưu ý:

- Luôn chỉ rõ `-c alembic-auth.ini`.
- Không dùng `uv run alembic upgrade head` vì có thể chọn nhầm cấu hình.
- Migration dùng biến `AUTH_DATABASE_URL` trong `.env`.
- Lệnh `upgrade head` là migration tiến về revision mới nhất, không xóa dữ liệu.

Nếu Auth đang tắt, giữ:

```dotenv
AUTH_ENABLED=false
```

và bỏ qua migration Auth.

## 9. Chạy migration cho Document

Chỉ chạy bước này khi `DOCUMENT_ENABLED=true`:

```bash
uv run alembic -c alembic-document.ini upgrade head
```

Migration dùng biến `DOCUMENT_DATABASE_URL` trong `.env`.

Nếu Document đang tắt, giữ:

```dotenv
DOCUMENT_ENABLED=false
```

và bỏ qua migration Document.

### Khi migration báo lỗi bảng đã tồn tại

Không dùng các thao tác ghi đè lịch sử migration, xóa database/bảng, xóa Docker volume hoặc hạ toàn bộ stack kèm volume để né lỗi.

Các thao tác trên có thể làm mất dữ liệu hoặc làm lịch sử migration không còn đáng tin cậy. Hãy kiểm tra:

1. Database URL có trỏ đúng database không.
2. Migration version table có tồn tại không.
3. Database có phải database được tạo bởi cùng phiên bản code không.
4. Có process khác đang chạy migration không.

Nếu database có bảng Auth/Document nhưng thiếu metadata migration, dừng lại và hỏi người quản lý dự án trước khi sửa.

## 10. Tạo tài khoản Admin Auth

Sau khi Auth migration thành công, chạy:

```bash
uv run python -m src.cli create-admin --email admin@example.com
```

Terminal sẽ yêu cầu nhập mật khẩu và nhập lại mật khẩu. Mật khẩu không được truyền trực tiếp trên command line.

Chỉ tài khoản Admin đầu tiên mới được bootstrap bằng lệnh này. Không ghi mật khẩu vào file, shell history hoặc Git.

## 11. Chạy FastAPI ở cổng mặc định 8000

Có hai cách chạy.

### Cách A: Chạy trực tiếp ở foreground

```bash
uv run uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

Giữ terminal này mở. Dừng server bằng:

```text
Ctrl+C
```

Mở Swagger:

```text
http://localhost:8000/docs
```

Kiểm tra health:

```bash
curl http://localhost:8000/health
```

Kết quả mong đợi tương tự:

```json
{"status":"ok","env":"development"}
```

### Cách B: Chạy nền để giữ terminal dùng cho lệnh khác

Linux:

```bash
setsid uv run uvicorn src.main:app --host 0.0.0.0 --port 8000 </dev/null >/tmp/p150-fastapi.log 2>&1 & disown
```

Xem log:

```bash
tail -f /tmp/p150-fastapi.log
```

Kiểm tra server:

```bash
curl -fsS http://localhost:8000/health
```

## 12. Chạy Swagger đầy đủ Auth + Document ở cổng 8001

Dùng cách này khi cổng `8000` đang được dùng cho backend cũ hoặc bạn muốn giữ một server riêng để xem toàn bộ Auth và Document API.

Trước tiên, bảo đảm các biến sau đã được đặt trong `.env` hoặc được truyền vào process:

```dotenv
AUTH_ENABLED=true
DOCUMENT_ENABLED=true
AUTH_DATABASE_URL=postgresql+asyncpg://p150_auth:<mat-khau>@localhost:5432/<auth-db>
DOCUMENT_DATABASE_URL=postgresql+asyncpg://p150_auth:<mat-khau>@localhost:5432/<document-db>
DOCUMENT_MINIO_ENDPOINT=http://127.0.0.1:9000
DOCUMENT_BUCKET_NAME=documents
DOCUMENT_ACCESS_KEY=p150_minio
DOCUMENT_SECRET_KEY=p150_minio_test_secret
DOCUMENT_BUCKET_PRIVATE=true
```

Tạo secret runtime cho server Swagger:

```bash
export AUTH_JWT_SIGNING_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
export AUTH_CSRF_SECRET="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
```

Sau đó chạy:

```bash
setsid env \
  AUTH_ENABLED=true \
  DOCUMENT_ENABLED=true \
  AUTH_JWT_SIGNING_KEY="$AUTH_JWT_SIGNING_KEY" \
  AUTH_CSRF_SECRET="$AUTH_CSRF_SECRET" \
  AUTH_COOKIE_SECURE=false \
  setsid uv run uvicorn src.main:app \
    --host 127.0.0.1 \
    --port 8001 \
  </dev/null >/tmp/p150-swagger.log 2>&1 & disown
```

Nếu `AUTH_DATABASE_URL`, `DOCUMENT_DATABASE_URL` và các biến MinIO đã nằm trong `.env`, ứng dụng sẽ đọc chúng từ `.env`. Nếu muốn tránh nhầm database, truyền chúng rõ ràng trong cùng lệnh:

```bash
setsid env \
  AUTH_ENABLED=true \
  DOCUMENT_ENABLED=true \
  AUTH_DATABASE_URL='postgresql+asyncpg://p150_auth:<mat-khau>@127.0.0.1:5432/<auth-db>' \
  DOCUMENT_DATABASE_URL='postgresql+asyncpg://p150_auth:<mat-khau>@127.0.0.1:5432/<document-db>' \
  DOCUMENT_MINIO_ENDPOINT='http://127.0.0.1:9000' \
  DOCUMENT_BUCKET_NAME='documents' \
  DOCUMENT_ACCESS_KEY='p150_minio' \
  DOCUMENT_SECRET_KEY='p150_minio_test_secret' \
  DOCUMENT_BUCKET_PRIVATE=true \
  AUTH_JWT_SIGNING_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')" \
  AUTH_CSRF_SECRET="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')" \
  AUTH_COOKIE_SECURE=false \
  uv run uvicorn src.main:app --host 127.0.0.1 --port 8001 \
  </dev/null >/tmp/p150-swagger.log 2>&1 & disown
```

Kiểm tra:

```bash
curl -fsS http://127.0.0.1:8001/health
curl -fsS http://127.0.0.1:8001/openapi.json
```

Mở:

```text
http://localhost:8001/docs
```

Khi cấu hình đúng, Swagger sẽ hiển thị:

- Các API cũ: Chat, Status, Health.
- 12 Auth endpoints dưới tag Auth.
- 5 thao tác Document dưới các path:
  - `POST /api/v1/documents`
  - `GET /api/v1/documents`
  - `GET /api/v1/documents/{document_id}`
  - `GET /api/v1/documents/{document_id}/download`
  - `POST /api/v1/documents/{document_id}/archive`

## 13. Cách dùng Swagger cho người mới

### 13.1. Kiểm tra health

1. Mở Swagger.
2. Tìm `GET /health`.
3. Bấm **Try it out**.
4. Bấm **Execute**.
5. Kiểm tra HTTP `200` và JSON có `status: ok`.

### 13.2. Đăng ký tài khoản

1. Mở `POST /api/v1/auth/register`.
2. Bấm **Try it out**.
3. Điền request body theo schema Swagger.
4. Bấm **Execute**.
5. Ghi nhớ email đã dùng.

Auth có thể yêu cầu email Gmail và email verification tùy rule hiện tại của module.

### 13.3. Đăng nhập

1. Mở `POST /api/v1/auth/login`.
2. Điền email và mật khẩu.
3. Bấm **Execute**.
4. Nếu thành công, server đặt cookie phiên đăng nhập.
5. Dùng `GET /api/v1/auth/me` để kiểm tra tài khoản hiện tại.

Các request thay đổi dữ liệu dùng cookie có thể cần CSRF token. Nếu Swagger báo lỗi CSRF, kiểm tra cookie và header `X-CSRF-Token` theo response/schema của endpoint.

### 13.4. Upload Document

1. Đăng nhập trước.
2. Mở `POST /api/v1/documents`.
3. Bấm **Try it out**.
4. Chọn file đúng loại:
   - `.pdf`
   - `.docx`
   - `.txt`
   - `.csv`
5. Nhập `title`.
6. Có thể nhập `description`, `document_type`, `source_url`.
7. Bấm **Execute**.

Giới hạn upload hiện tại là 25 MiB. Bucket MinIO phải tồn tại và phải private.

### 13.5. List, detail, download và archive

Sau khi upload thành công:

1. Dùng `GET /api/v1/documents` để lấy danh sách.
2. Copy `document_id` từ response.
3. Dùng `GET /api/v1/documents/{document_id}` để xem chi tiết.
4. Dùng `GET /api/v1/documents/{document_id}/download` để lấy URL tải tạm thời.
5. Dùng `POST /api/v1/documents/{document_id}/archive` để archive document.

URL download là presigned URL và chỉ có hiệu lực trong thời gian ngắn.

## 14. Kiểm tra OpenAPI bằng command line

Liệt kê toàn bộ path của server mặc định:

```bash
curl -fsS http://localhost:8000/openapi.json | python -c 'import json,sys; print("\n".join(json.load(sys.stdin)["paths"]))'
```

Liệt kê path của server Auth + Document:

```bash
curl -fsS http://localhost:8001/openapi.json | python -c 'import json,sys; print("\n".join(json.load(sys.stdin)["paths"]))'
```

Nếu không thấy `/api/v1/auth/...` hoặc `/api/v1/documents...`, kiểm tra:

- `AUTH_ENABLED=true` hoặc `DOCUMENT_ENABLED=true` đã được process đọc chưa.
- Server có được restart sau khi sửa `.env` chưa.
- Migration tương ứng đã chạy chưa.
- Log server có lỗi startup không.

## 15. Xem log và tìm lỗi

Server mặc định chạy foreground sẽ in log trực tiếp trong terminal. Nếu chạy nền:

```bash
tail -f /tmp/p150-fastapi.log
```

Swagger server ở cổng 8001:

```bash
tail -f /tmp/p150-swagger.log
```

Log Docker:

```bash
docker compose logs -f postgres
docker compose logs -f minio
docker compose logs -f backend
```

## 16. Các lỗi thường gặp

### Lỗi `command not found: uv`

Cài `uv`, mở lại terminal rồi kiểm tra:

```bash
uv --version
```

### Lỗi cổng đã được sử dụng

Kiểm tra process đang dùng cổng:

```bash
ss -ltnp | grep -E ':8000|:8001|:5432|:9000|:9001|:5050'
```

Không dùng `killall` hoặc `pkill` bừa bãi. Dừng đúng process do bạn khởi động hoặc chọn một cổng khác.

### Lỗi PostgreSQL không healthy

Kiểm tra:

```bash
docker compose ps
docker compose logs postgres
```

Đảm bảo `.env` có `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`. Nếu volume đã tồn tại, dùng đúng credential lúc volume được tạo.

### Lỗi `AUTH_DATABASE_URL` không hợp lệ

Auth chỉ chấp nhận PostgreSQL async URL:

```text
postgresql+asyncpg://user:password@host:5432/database
```

SQLite không dùng được cho Auth.

### Lỗi MinIO hoặc `document storage unavailable`

Kiểm tra:

```bash
curl -fsS http://localhost:9000/minio/health/live
docker compose logs minio
```

Kiểm tra lại:

```dotenv
DOCUMENT_MINIO_ENDPOINT=http://localhost:9000
DOCUMENT_ACCESS_KEY=p150_minio
DOCUMENT_SECRET_KEY=p150_minio_test_secret
DOCUMENT_BUCKET_PRIVATE=true
```

Bucket `documents` phải tồn tại. Không đặt bucket public.

### Swagger không có Auth hoặc Document API

1. Dừng server hiện tại bằng `Ctrl+C` nếu chạy foreground.
2. Kiểm tra `AUTH_ENABLED` và `DOCUMENT_ENABLED`.
3. Kiểm tra migration.
4. Khởi động lại FastAPI.
5. Mở lại `/openapi.json` và `/docs`.

### Lỗi bảng đã tồn tại khi migration

Dừng lại, lưu log lỗi và kiểm tra database/migration metadata. Không dùng thao tác ghi đè lịch sử migration, xóa dữ liệu hoặc xóa volume để che lỗi.

## 17. Dừng dự án an toàn

Nếu FastAPI chạy foreground:

```text
Ctrl+C
```

Dừng các service Docker nhưng giữ lại database và file MinIO:

```bash
docker compose stop backend postgres minio pgadmin
```

Hoặc nếu backend đang chạy ngoài Docker:

```bash
docker compose stop postgres minio pgadmin
```

Không dùng lệnh hạ stack kèm xóa volume trong quy trình thường ngày. Thao tác này chỉ được thực hiện khi người phụ trách dự án yêu cầu rõ ràng và bạn đã xác nhận dữ liệu local có thể bị xóa.

## 18. Checklist nhanh cho người mới

- [ ] Đã cài Python 3.11+, Docker Compose và `uv`.
- [ ] Đã chạy `uv sync --locked`.
- [ ] Đã copy `.env.example` thành `.env`.
- [ ] `.env` không bị commit vào Git.
- [ ] PostgreSQL và MinIO có trạng thái đang chạy.
- [ ] Đã chạy Auth migration nếu `AUTH_ENABLED=true`.
- [ ] Đã chạy Document migration nếu `DOCUMENT_ENABLED=true`.
- [ ] `curl http://localhost:8000/health` hoặc `curl http://localhost:8001/health` trả về `status: ok`.
- [ ] Mở được `/docs`.
- [ ] OpenAPI có các endpoint cần thiết.
- [ ] Đã tạo Admin nếu cần thử Auth.
- [ ] Đã đăng nhập trước khi thử Document.

Sau khi hoàn tất, người mới có thể dùng Swagger UI để thử API mà không cần viết frontend hoặc gọi API bằng Postman.
