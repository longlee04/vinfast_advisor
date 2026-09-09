# Hướng dẫn chạy dự án từ đầu

Làm theo đúng thứ tự dưới đây trên máy sạch (chưa có container, chưa có `.env`). Kết thúc bước 8, backend chạy 4 module (`auth`, `document`, `product`, `agent`) và luồng agent hoạt động đầy đủ gồm cả RAG. Agent chỉ được xem là sẵn sàng sau khi migration, dữ liệu vector, feature flags, backend và full flow đều đạt checklist ở mục 8.

**Ba bước bắt buộc cho agent, bỏ qua là luồng chạy nhưng câm phần mô tả:** `OPENAI_API_KEY` hợp lệ trong `.env` (mục 2), seed catalog (mục 6.2), và dựng corpus vector bằng `scripts/build_car_documents.py --load` (mục 6.4). Từ bước 9 trở đi là frontend, kết thúc bước 12 thì mở được `http://localhost:3000` và đăng nhập bằng tài khoản thật trong Postgres.

**Hiện trạng cần biết trước:** frontend đã nối API thật cho **Auth** (đăng nhập khách + đăng nhập nhân viên ở `/staff-login`, phiên, chặn theo role), **catalog** (`/vehicles`, `/compare`, `/tco`, `/admin/vehicles`), **locations** (`/locations`, cần chạy migration + seed locations ở mục 6) và **toàn bộ luồng agent** (`/consultation` chat thật, chờ duyệt qua SSE, `/advisor` hàng đợi + màn duyệt kèm ảnh so sánh). Các trang gợi ý, lịch sử khách và dashboard admin vẫn đọc từ `src/mocks/`. Đặt lịch lái thử ĐÃ nối API thật ở cả hai lối: trang `/test-drive` và thẻ chọn khung giờ trong hội thoại. Mục 13 liệt kê phần thật/mock; mục 14 hướng dẫn nối tiếp phần còn mock.

**Muốn test riêng luồng agent end-to-end trên giao diện:** làm hết Phần A, rồi nhảy thẳng tới **mục 11b** ở Phần B. Mục đó liệt kê đúng các bước tối thiểu và các bẫy đã gặp thật.

**Đã chạy xong một lượt rồi, chỉ muốn bật lại máy:** bỏ qua toàn bộ tài liệu này, xem mục **"Khởi động lại ở những lần sau"** ở cuối — ba lệnh là đủ, dữ liệu đã nạp vẫn còn trong Docker volume.

---

# Phần A — Backend

## 0. Yêu cầu

- Docker Engine với BuildKit và Docker Compose **2.17.0+** (frontend dùng `additional_contexts`)
- `uv` (Python package manager): `curl -LsSf https://astral.sh/uv/install.sh | sh`
- Node.js 20+ (cần cho phần B)
- Còn trống ít nhất ~10 GB đĩa: build image backend cần chỗ cho layer trung gian, hết đĩa giữa chừng sẽ fail và để lại build cache rác.

## 1. Cài dependency Python

```bash
uv sync
```

## 2. Tạo `.env`

```bash
cp .env.example .env
```

Sinh 2 secret **khác nhau** cho Auth (bắt buộc, khởi động sẽ fail nếu để trống hoặc trùng nhau):

```bash
uv run python -c "import secrets; print(secrets.token_urlsafe(48))"
uv run python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Mở `.env`, set:

```env
AUTH_ENABLED=true
AUTH_JWT_SIGNING_KEY=<secret 1>
AUTH_CSRF_SECRET=<secret 2>
AUTH_CORS_ORIGINS=http://localhost:3000,http://localhost:5173

DOCUMENT_ENABLED=true
DOCUMENT_ACCESS_KEY=p150_minio
DOCUMENT_SECRET_KEY=p150_minio_test_secret

# Phải khớp POSTGRES_PASSWORD; .env.example hiện dùng p150_local_dev.
AUTH_DATABASE_URL=postgresql+asyncpg://p150_auth:p150_local_dev@localhost:5432/p150_auth
DOCUMENT_DATABASE_URL=postgresql+asyncpg://p150_auth:p150_local_dev@localhost:5432/p150_auth
PRODUCT_DATABASE_URL=postgresql+asyncpg://p150_auth:p150_local_dev@localhost:5432/p150_auth
AGENT_DATABASE_URL=postgresql+asyncpg://p150_auth:p150_local_dev@localhost:5432/p150_auth
```

`AUTH_CORS_ORIGINS` phải chứa origin của frontend, nếu không mọi request từ trình duyệt bị trả `{"error":"origin_forbidden"}` kèm HTTP 403. Không được dùng `*`: Auth gửi request kèm cookie nên khởi động sẽ fail nếu thấy wildcard.

`DOCUMENT_ACCESS_KEY`/`DOCUMENT_SECRET_KEY` khớp `MINIO_ROOT_USER`/`MINIO_ROOT_PASSWORD` hard-code trong `docker-compose.yml` (chỉ dùng cho local dev).

`DOCUMENT_DATABASE_URL`/`PRODUCT_DATABASE_URL`/`AGENT_DATABASE_URL` để trống mặc định trong `.env.example` — phải tự điền, dùng chung Postgres với `AUTH_DATABASE_URL` (cùng user/password, khác bảng `*_alembic_version` để tách version riêng từng module).

`LANGCHAIN_API_KEY` không bắt buộc. Thiếu nó chỉ mất tracing LangSmith; nếu key sai/hết hạn thì log in `403 Client Error ... /runs/multipart` ở cuối mỗi lần chạy — vô hại, không ảnh hưởng kết quả.

`COMPARISON_IMAGE_DIR` quyết định chỗ lưu ảnh so sánh đã render. `.env.example` đặt `./data-p150/comparison_images`; giữ nguyên là được. **Không trỏ vào `data/`**: thư mục đó do container tạo nên thuộc `root`, tiến trình chạy bằng tài khoản thường không ghi được, và `image_for_review` nuốt `PermissionError` rồi trả ảnh rỗng — triệu chứng là bảng so sánh luôn `null` mà không có lỗi nào hiện ra.

`OPENAI_API_KEY` **bắt buộc nếu muốn dùng agent**. Nó phục vụ hai việc khác nhau: sinh embedding (`text-embedding-3-large`, rút còn 1024 chiều) và gọi LLM cho trích xuất slot / phân loại phạm vi / viết câu trả lời. Thiếu key, `OpenAIEmbeddingAdapter` **không báo lỗi** mà lặng lẽ tụt xuống vector băm 1536 chiều (`src/agents/adapters/embedding.py`) — ghi vào cột `Vector(1024)` sẽ vỡ, còn nếu lọt thì kết quả truy hồi vô nghĩa. Auth/document/product không cần key này.

## 3. Lên toàn bộ hệ thống bằng Docker Compose

```bash
docker compose up -d --build
docker compose ps   # đợi cả 5 service healthy
```

Lệnh trên dựng frontend production tại `http://localhost:3000` và backend tại `http://localhost:8000`. Docker Desktop phải hiển thị đủ `postgres`, `minio`, `pgadmin`, `backend` và `frontend`.

## 4. Chạy migration cho từng module

`uv run alembic` chạy process riêng ngoài Docker, không tự nạp `.env` (chỉ backend trong container mới được `env_file` nạp hộ). Export biến vào shell trước:

```bash
set -a
source .env
set +a
```

Cách này giữ đúng giá trị có ký tự đặc biệt hoặc khoảng trắng. Không dùng `export $(grep ... | xargs)` vì shell có thể tách hoặc biến đổi giá trị.

Mỗi module có Alembic chain riêng, phải gọi đúng file `-c`. **Thứ tự dưới đây bắt buộc, không đổi được:**

```bash
uv run alembic -c alembic-auth.ini upgrade head
uv run alembic -c alembic-products.ini upgrade head
uv run alembic -c alembic-document.ini upgrade head
uv run alembic -c alembic-agent.ini upgrade head
```

`products` phải chạy **trước** `document`: bảng `vehicle_documents` (thuộc chain document) có khoá ngoại trỏ tới `vehicles` (thuộc chain products). Đảo thứ tự thì migration document chết với `UndefinedTableError: relation "vehicle_documents" does not exist`, và mọi bước sau đó đổ theo — seed thiếu bảng, dựng corpus báo `Model khong co trong bang vehicles`. Lỡ chạy sai thứ tự thì chỉ cần chạy lại lệnh `document` sau khi `products` xong.

Kiểm tra nhanh đã có bảng:

```bash
docker exec p-150-postgres-1 psql -U p150_auth -d p150_auth -c "\dt" 2>&1 | grep -v WARNING
```

Cảnh báo `database "p150_auth" has a collation version mismatch` là vô hại (khác version libc giữa container/host), bỏ qua.

## 5. Tạo bucket MinIO cho Document

MinIO không tự tạo bucket. Tạo bằng chính client Python đã có trong `uv.lock`:

```bash
uv run python -c "
from minio import Minio
c = Minio('localhost:9000', access_key='p150_minio', secret_key='p150_minio_test_secret', secure=False)
if not c.bucket_exists('documents'):
    c.make_bucket('documents')
print('bucket ready')
"
```

## 6. Nạp dữ liệu

### 6.1. Auth — tạo tài khoản Admin đầu tiên

```bash
uv run python -m src.cli create-admin --email admin@example.com
```

Script hỏi mật khẩu qua prompt ẩn (không truyền qua argument/log). Mật khẩu phải qua được `validate_password` (đủ dài, không nằm trong danh sách yếu). Chỉ chạy được **một lần** — lần sau báo `An active Admin account already exists.`

Đây cũng là tài khoản dùng để đăng nhập frontend ở phần B. Tài khoản này vào thẳng trạng thái `active`, không cần xác thực email.

Lỡ chạy từ trước và quên mật khẩu thì dùng luồng `forgot-password`/`reset-password`. Không xoá riêng hàng `auth_users`: `create-admin` còn giữ claim `first_admin`, nên chạy lại vẫn báo `An active Admin account already exists.` Nếu đây là môi trường local bỏ được toàn bộ dữ liệu, dùng quy trình reset volume ở cuối tài liệu rồi migrate/seed lại từ đầu.

Tạo thêm tài khoản Advisor cần đăng nhập Admin qua `POST /api/v1/auth/staff/login`, rồi gọi `POST /api/v1/auth/staff`. Khi chưa cấu hình `AUTH_SENDGRID_API_KEY`, development email sender ghi mật khẩu tạm vào log backend:

```bash
docker compose logs backend --since 5m
```

Muốn test luồng agent thì cần **hai tài khoản nữa**: một `customer` và một `advisor`. Nhanh nhất là seed sẵn cả ba vai:

```bash
set -a; source .env; set +a
uv run python scripts/seed_auth_users.py
```

Script upsert ba tài khoản và **in mật khẩu ra log** khi chạy:

| Email | Vai | Mật khẩu |
|---|---|---|
| `admin@vinfast.local` | admin | `Admin@123456` |
| `customer@vinfast.local` | customer | `Customer@123456` |
| `advisor@vinfast.local` | advisor | `Advisor@123456` |

Một ràng buộc dễ vấp: **email khách bắt buộc domain `@gmail.com`** (`NormalizedEmail.parse_customer`). Tài khoản `customer@vinfast.local` ở trên đăng nhập được ở đường staff nhưng **không** đăng nhập được ở form khách. Để test màn `/consultation`, tạo một khách domain gmail — sửa `DEFAULT_USERS` trong script hoặc thêm hàng trực tiếp bằng hasher của dự án. Nhân sự thì ngược lại: đăng nhập ở `/staff-login` (`POST /api/v1/auth/staff/login`), không phải form khách.

### 6.2. Product — nạp catalog xe VinFast

```bash
uv run python scripts/seed_catalog_data.py --dsn "postgresql://p150_auth:p150_local_dev@localhost:5432/p150_auth"
```

Script đọc DSN từ biến `PRODUCT_DATABASE_URL_SYNC` (không phải `PRODUCT_DATABASE_URL`), biến này không có sẵn trong `.env` nên phải truyền `--dsn` tay — nếu bỏ qua, script rơi về DSN mặc định hard-code trong file (password khác `.env`) và báo `InvalidPasswordError`.

Đọc toàn bộ CSV ở `data-p150/catalog/` (51 xe, giá, khuyến mại, chính sách pin, feature definitions, need tags, feature flags, TCO assumptions) và insert theo đúng thứ tự FK. Idempotent (`ON CONFLICT DO NOTHING`) — chạy lại không lỗi trùng, nhưng cũng **không cập nhật** hàng đã có. Sửa CSV rồi muốn áp lại thì phải `--truncate`.

Sau bước này, dữ liệu quan hệ cho ô tô đã đủ để agent chạy: 10 xe CAR `ACTIVE` (VF Wild là concept chưa bán nên để `ARCHIVED`), mọi xe có đủ 3 loại giá, bảng `cars` không còn ô trống, 17 `feature_definitions`, 16 `feature_need_tags` phủ 8 need tag, và feature flags đã ở trạng thái duyệt sẵn.

Riêng `vehicle_documents` trong CSV chỉ là 119 dòng tóm tắt cũ, `status=ARCHIVED` và **không có embedding** — truy hồi bỏ qua chúng vì chỉ đọc hàng `ACTIVE`. Corpus thật dựng ở mục 6.4.

### 6.3. Document — không có data mẫu

Không có file seed cho module Document trong `data-p150/`: nội dung của module này là file người dùng tải lên qua API (`POST /api/v1/documents`), không phải dữ liệu nạp sẵn. Sau bước 5, module đã sẵn sàng nhận upload ngay.

### 6.4. Agent — dựng corpus vector cho RAG (bắt buộc)

Không có bước này thì Lớp 2 không có gì để đọc: agent vẫn trả lời được nhưng mất toàn bộ phần mô tả và trích dẫn tài liệu.

```bash
# Nếu đã source .env ở mục 4 thì không cần export lại.
# Không giữ nguyên placeholder `<password>`; password phải khớp POSTGRES_PASSWORD.
export PRODUCT_DATABASE_URL="postgresql+asyncpg://p150_auth:p150_local_dev@localhost:5432/p150_auth"
uv run python scripts/build_car_documents.py --dry-run   # xem thống kê lọc, chưa ghi gì
uv run python scripts/build_car_documents.py --load      # sinh embedding và ghi DB
```

Script đọc brochure trong `data-p150/car_pdf/*.md`, lọc bỏ nội dung chào hàng (hotline, khuyến mãi, trả góp), rác giao diện web, mọi con số tiền và mọi thông số kW/kWh/Nm/km — giá và thông số phải lấy từ `vehicle_prices`/`cars`, để trong tài liệu sẽ sinh hai nguồn số mâu thuẫn. Phần còn lại được cắt chunk, sinh embedding 1024 chiều và upsert vào `vehicle_documents` với `status=ACTIVE`.

Chunk mô tả ở mức model nên được gán cho mọi biến thể của model đó (VF 6 hai biến thể, VF 8 ba biến thể). Chạy lại nhiều lần an toàn: script xoá theo `created_by='car_brochure_import'` rồi upsert theo `document_id` sinh bằng `uuid5`.

Nạp thêm chunk từ nguồn ngoài brochure (bài báo, PDF chính sách) bằng CSV có cột `model_name,section_title,content,source_url,document_type`; dùng `model_name='*'` cho tài liệu áp dụng cho mọi xe đang bán:

```bash
uv run python scripts/build_car_documents.py --load --extra-chunks duong-dan/toi/chunks.csv
```

Chunk bổ sung đi qua đúng bộ lọc trên — nguồn khác không được miễn kiểm.

Repo đã có sẵn `data-p150/catalog/vehicle_documents_extra.csv` (23 đoạn VF 9 từ báo chí + 14 đoạn chính sách ưu đãi sạc từ PDF chính hãng). Script **tự nạp file này** nếu nó tồn tại, nên lệnh `--load` trần ở trên đã bao gồm nó; không cần thêm cờ.

Kết quả tham chiếu khi chạy xong trên bộ dữ liệu hiện tại (số lượng có thể đổi khi CSV/corpus đổi):

```
Tong chunk sach: 159
Theo model: *=14, VF 2=17, VF 3=16, VF 5=18, VF 6=17, VF 7=13, VF 8=30, VF 9=34
Da ghi 362 hang vehicle_documents cho 8 model.
```

Số hàng (362) lớn hơn số chunk (159) vì chunk ở mức model được gán cho từng biến thể, và 14 đoạn chính sách (`model_name='*'`) được gán cho cả 10 xe đang bán.

### 6.5. Agent — đồng bộ ảnh xe vào MinIO (bắt buộc nếu muốn có ảnh so sánh)

Bảng so sánh gửi khách lấy ảnh từ `vehicles.image_object_key`. Seed catalog chỉ điền `image_url` (URL ngoài), cột object key vẫn rỗng, nên chưa chạy bước này thì bảng so sánh vẫn dựng được nhưng **mọi xe ra ô giữ chỗ chỉ có tên model**.

```bash
set -a; source .env; set +a
uv run python -m src.products.cli.sync_vehicle_images
```

In ra một dòng `synced=<n> skipped=<n> failed=<n>`. Lệnh idempotent: chạy lần hai trên dữ liệu không đổi cho `synced=0`. Vài URL nguồn ở `vinfastvietnam.com.vn` tải chập chờn nên `failed` xê dịch giữa các lần chạy — chạy lại để phủ nốt, lệnh giữ nguyên asset cũ cho xe lỗi chứ không xoá.

Kiểm chứng:

```bash
docker exec -e PGPASSWORD=p150_local_dev p-150-postgres-1 psql -U p150_auth -d p150_auth -tA \
  -c "select count(*) filter (where image_object_key is not null), count(*) from vehicles"
```

Lần chạy tham chiếu cho kết quả `49|51` (2 xe có URL hỏng). Chi tiết và cách xử lý sự cố: `docs/runbooks/dong-bo-anh-xe.md`.

## 7. Khởi động lại backend để áp `.env` mới

`.env` sửa ở bước 2 (bật `AUTH_ENABLED`/`DOCUMENT_ENABLED`, mở CORS) chưa có hiệu lực với container `backend` đã chạy từ bước 3:

```bash
docker compose up -d --build backend
```

Về sau, **mỗi lần pull code mới hoặc sửa `.env` đều phải chạy lại lệnh này**. Container giữ nguyên image cũ cho tới khi build lại — không build thì route mới không tồn tại và frontend nhận 404.

## 8. Kiểm tra backend

```bash
curl http://localhost:8000/health
# {"status":"ok","env":"development"}

curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -H "Origin: http://localhost:3000" \
  -d '{"email":"vidu@gmail.com","password":"mat-khau-bat-ky"}'
```

Header `Origin` là bắt buộc — thiếu nó Auth trả `origin_forbidden`.

**`/api/v1/auth/login` chỉ dành cho khách hàng** — `NormalizedEmail.parse_customer` (`src/auth/domain/values.py`) bắt buộc email đuôi `@gmail.com`, sai domain thì trả `invalid_credentials` y hệt sai mật khẩu, **kể cả gõ đúng password**. Tài khoản Admin/Advisor dùng endpoint riêng `POST /api/v1/auth/staff/login`; `/auth/staff` dùng để Admin tạo thêm Advisor/Admin.

Kiểm tra CORS đã mở đúng (401 là đúng, nghĩa là request đã đi lọt vào tầng auth):

```bash
curl -s -i -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -H "Origin: http://localhost:3000" \
  -d '{"email":"khong-ton-tai@gmail.com","password":"sai-mat-khau"}' | head -12
```

Cần thấy đủ 2 header:

```
access-control-allow-origin: http://localhost:3000
access-control-allow-credentials: true
```

Kiểm tra route xe đã lên và trả dữ liệu thật:

```bash
docker exec p-150-postgres-1 psql -U p150_auth -d p150_auth -c "select count(*) from vehicles;"
# 51

curl -s "http://localhost:8000/api/v1/vehicles?page=1&page_size=2" | head -c 300
```

Swagger UI: `http://localhost:8000/docs`.
pgAdmin: `http://localhost:5050` (đăng nhập bằng `PGADMIN_DEFAULT_EMAIL`/`PGADMIN_DEFAULT_PASSWORD` trong `.env`). Đăng nhập xong pgAdmin chưa tự thấy Postgres — phải tự add server (Object Explorer → click phải `Servers` → `Register` → `Server...`):

| Field | Giá trị |
|---|---|
| General → Name | tuỳ đặt, vd `P-150 Postgres` |
| Connection → Host name/address | `postgres` (tên service trong docker network, **không phải** `localhost`) |
| Connection → Port | `5432` |
| Connection → Maintenance database | `p150_auth` |
| Connection → Username | `p150_auth` |
| Connection → Password | giá trị `POSTGRES_PASSWORD`/`AUTH_DATABASE_URL` trong `.env` |
| Connection → Save password? | bật, đỡ phải gõ lại |

Sau khi connect, cây bên trái phải bấm mở sâu hết `Databases → p150_auth → Schemas → public → Tables` mới thấy danh sách bảng — mặc định cây thu gọn, không phải dữ liệu bị mất.

MinIO Console: `http://localhost:9001` (`p150_minio` / `p150_minio_test_secret`).

Product có route API (`src/products/presentation`), gồm 17 endpoint — public không cần đăng nhập, `/admin/*` cần role admin:

| Method | Endpoint | Mục đích |
|---|---|---|
| GET | `/api/v1/vehicles` | Lấy danh sách xe công khai |
| GET | `/api/v1/vehicles/search` | Tìm kiếm xe |
| GET | `/api/v1/vehicles/_schema-types` | Schema loại dữ liệu |
| GET | `/api/v1/vehicles/{identifier}` | Chi tiết một xe (id hoặc slug) |
| GET | `/api/v1/vehicles/{identifier}/tco` | Ước tính tổng chi phí sở hữu của một xe |
| GET | `/api/v1/vehicles/{identifier}/rag-context` | RAG context của xe |
| GET | `/api/v1/admin/vehicles` | Admin liệt kê xe |
| POST | `/api/v1/admin/vehicles` | Admin tạo xe |
| PATCH | `/api/v1/admin/vehicles/{vehicle_id}` | Admin cập nhật một phần thông tin xe |
| DELETE | `/api/v1/admin/vehicles/{vehicle_id}` | Admin xoá (archive mềm) xe |
| POST | `/api/v1/admin/vehicles/{vehicle_id}/restore` | Admin khôi phục xe đã archive |
| PUT | `/api/v1/admin/vehicles/{vehicle_id}/prices` | Admin thay bộ giá hiện hành |
| PUT | `/api/v1/admin/vehicles/{vehicle_id}/prices/{price_id}` | Admin sửa một bản ghi giá |
| PUT | `/api/v1/admin/vehicles/{vehicle_id}/specs` | Admin cập nhật specs |
| PUT | `/api/v1/admin/vehicles/{vehicle_id}/feature-flags/{feature_code}` | Admin cập nhật feature flag |
| GET | `/api/v1/admin/feature-flags` | Admin liệt kê feature flags |
| POST | `/api/v1/admin/feature-flags/{vehicle_id}/{feature_code}/review` | Admin duyệt feature flag |

**Lưu ý:** `DELETE /api/v1/admin/vehicles/{id}` là archive mềm (đổi trạng thái sang `ARCHIVED`), không xoá hàng cứng. Để gỡ archive, dùng `POST /api/v1/admin/vehicles/{id}/restore`.

### Kiểm tra Agent, PostgreSQL và pgvector

Agent hiện đã có API `POST /api/v1/agent/turn`. pgvector nằm **bên trong PostgreSQL**, không phải một vector database riêng. Chạy lại migration Agent từ project root trước khi kiểm tra:

```bash
uv run alembic -c alembic-agent.ini upgrade head
```

Lệnh trên chỉ nâng migration, không tự seed dữ liệu và không có nghĩa migration đã được chạy thành công. Xác nhận version hiện tại và kiểm tra extension, embedding, nội dung cùng HNSW index:

```bash
docker exec p-150-postgres-1 psql -U p150_auth -d p150_auth -c "select version_num from agent_alembic_version;"
docker exec p-150-postgres-1 psql -U p150_auth -d p150_auth -c "select extversion from pg_extension where extname = 'vector';"
docker exec p-150-postgres-1 psql -U p150_auth -d p150_auth -c "select count(*) as documents, count(*) filter (where embedding is null) as null_embeddings, count(*) filter (where content is null or btrim(content) = '') as empty_content, count(*) filter (where vector_dims(embedding) = 1024) as dimensions_1024 from vehicle_documents;"
docker exec p-150-postgres-1 psql -U p150_auth -d p150_auth -c "select indexname, indexdef from pg_indexes where tablename = 'vehicle_documents' and indexdef ilike '%hnsw%';"
```

Kết quả khỏe cần có: extension `vector` hoạt động, embedding có 1024 dimensions, `null_embeddings = 0`, nội dung rỗng bằng 0, và có HNSW index dùng cosine distance. Nếu thiếu bảng hoặc cột `vehicle_documents`, chạy migration Document `uv run alembic -c alembic-document.ini upgrade head`; nếu thiếu bảng thuộc Agent, chạy migration Agent `uv run alembic -c alembic-agent.ini upgrade head`. Sau đó seed lại dữ liệu theo mục 6.2 nếu cần.

Kiểm tra độ phủ dữ liệu quan hệ, vector và feature flags:

```bash
docker exec p-150-postgres-1 psql -U p150_auth -d p150_auth -c "select count(*) as vehicles from vehicles;"
docker exec p-150-postgres-1 psql -U p150_auth -d p150_auth -c "select count(distinct vehicle_id) as vehicles_with_documents from vehicle_documents;"
docker exec p-150-postgres-1 psql -U p150_auth -d p150_auth -c "select verification_status, count(*) from vehicle_feature_flags group by verification_status order by verification_status;"
docker exec p-150-postgres-1 psql -U p150_auth -d p150_auth -c "select count(*) as vehicles_without_price from vehicles v left join vehicle_prices p on p.vehicle_id = v.vehicle_id where p.vehicle_id is null;"
```

Độ phủ dữ liệu rất quan trọng: Agent có thể vượt qua kiểm tra toàn vẹn vector nhưng vẫn truy xuất hoặc đề xuất không hữu ích nếu xe thiếu tài liệu, giá hoặc feature flag `APPROVED`.

**Chỉ flag `APPROVED` mới có tác dụng.** Lớp 2 lọc cứng `verification_status == 'APPROVED'` (`src/agents/adapters/feature_retriever.py`), nên flag `PENDING` là vô hình với luồng tư vấn. Flag do agent tự suy ra từ tài liệu luôn được ghi ở mức `PENDING` và chờ người duyệt qua `POST /api/v1/admin/feature-flags/{vehicle_id}/{feature_code}/review`.

Ngưỡng tối thiểu để coi là chạy được cho ô tô:

```bash
docker exec p-150-postgres-1 psql -U p150_auth -d p150_auth -c "
select
  (select count(*) from vehicles where vehicle_type='CAR' and status='ACTIVE') as xe_ban,
  (select count(*) from vehicle_documents where status='ACTIVE' and embedding is not null) as chunk_dung_duoc,
  (select count(distinct d.vehicle_id) from vehicle_documents d
     join vehicles v on v.vehicle_id=d.vehicle_id
    where v.status='ACTIVE' and d.status='ACTIVE' and d.embedding is not null) as xe_co_tai_lieu,
  (select count(*) from vehicle_feature_flags f
     join vehicles v on v.vehicle_id=f.vehicle_id
    where v.vehicle_type='CAR' and v.status='ACTIVE' and f.verification_status='APPROVED') as flag_dung_duoc;"
```

Mọi xe đang bán phải có tài liệu (`xe_co_tai_lieu` bằng `xe_ban`), nếu không thì khách hỏi đúng xe đó sẽ nhận câu trả lời không dẫn chứng.

Chạy đúng hướng dẫn trên database trống cho ra:

```
 xe_ban | chunk_dung_duoc | xe_co_tai_lieu | flag_dung_duoc
      10 |             362 |             10 |             80
```

Điều kiện lọc `d.status='ACTIVE' and d.embedding is not null` là bắt buộc: bỏ đi thì 119 dòng seed cũ (`ARCHIVED`, không embedding) bị đếm vào và `xe_co_tai_lieu` nhảy lên 47, che mất việc corpus chưa được dựng.

Gọi API Agent sau khi backend đã được build lại và đang chạy:

```bash
curl -s -X POST http://localhost:8000/api/v1/agent/turn \
  -H "Content-Type: application/json" \
  -d '{"session_id":"00000000-0000-0000-0000-000000000001","message":"Tư vấn xe VinFast phù hợp cho gia đình 4 người"}'
```

Payload có thể thay đổi theo schema hiện tại trong Swagger tại `http://localhost:8000/docs`. Full flow chỉ đạt khi request này trả response hợp lệ, truy vấn được dữ liệu PostgreSQL/pgvector, và không có lỗi cấu hình LLM hoặc tracing.

### Kiểm tra Lớp 2 thật sự đọc được tài liệu

Đây là bước phân biệt "API trả 200" với "RAG hoạt động". Lưu file sau rồi chạy — nó gọi thẳng bộ truy hồi Lớp 2 trên 3 xe đầu tiên:

```bash
export PRODUCT_DATABASE_URL="postgresql+asyncpg://p150_auth:p150_local_dev@localhost:5432/p150_auth" PYTHONPATH=.
uv run python - <<'PY'
import asyncio, os
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from src.agents.adapters.feature_retriever import FeatureRetrievalAdapter
from src.agents.adapters.embedding import OpenAIEmbeddingAdapter
from src.products.infrastructure.models import VehicleRow

async def main():
    engine = create_async_engine(os.environ["PRODUCT_DATABASE_URL"])
    async with async_sessionmaker(engine)() as session:
        rows = (await session.execute(
            select(VehicleRow.vehicle_id, VehicleRow.model_name)
            .where(VehicleRow.vehicle_type == "CAR", VehicleRow.status == "ACTIVE")
            .order_by(VehicleRow.model_name).limit(3))).all()
        names = {UUID(i): n for i, n in rows}
        adapter = FeatureRetrievalAdapter(session, embedding_port=OpenAIEmbeddingAdapter())
        for assertion in await adapter.resolve(
            "nhà tôi 6 người, cần xe rộng đi chơi cuối tuần", "CAR", list(names)
        ):
            print(f"{names[assertion.vehicle_id]:6} {assertion.feature_code:16} "
                  f"{assertion.status:8} {assertion.source:8} {(assertion.excerpt or '')[:60]}")
    await engine.dispose()

asyncio.run(main())
PY
```

Đạt yêu cầu khi: **mỗi xe** đều có ít nhất một dòng `DOCUMENT` kèm đoạn trích, và có dòng `FLAG` cho tính năng khớp nhu cầu. Chỉ thấy `FLAG` nghĩa là corpus rỗng — quay lại mục 6.4. Trích dẫn hiện ra nhưng nội dung lệch chủ đề thì corpus thiếu nội dung cho câu hỏi đó, không phải lỗi code.

Trạng thái `UNKNOWN` trên dòng `DOCUMENT` là **đúng thiết kế**: tài liệu trúng truy vấn ngữ nghĩa không đồng nghĩa xe có tính năng đó, nên hệ thống chỉ kết luận `YES` khi đoạn trích thật sự nhắc tới tính năng đang xét. Đoạn không khớp vẫn được giữ để làm dẫn chứng cho phần diễn giải.

### Lệnh test Agent

```bash
export AGENT_DATABASE_URL="postgresql+asyncpg://p150_auth:p150_local_dev@localhost:5432/p150_auth"
uv run pytest tests/agents -q --tb=short
```

**Phải export `AGENT_DATABASE_URL` trước.** `tests/agents/integration/conftest.py` có DSN mặc định hard-code với password `p150_local_dev`; nếu `.env` dùng password khác thì pytest chết ngay ở bước collection với `asyncpg.exceptions.InvalidPasswordError`, trước cả khi chạy test nào. Test integration tự tạo database tạm `p150_agent_test_*` rồi migrate, không đụng vào dữ liệu dev.

**Snapshot kiểm tra gần nhất (2026-08-12), không phải tiêu chí cố định:** 545 test agent pass; 362 chunk vector, tất cả `ACTIVE` và có embedding 1024 chiều (222 `OVERVIEW` + 140 `POLICY`); 10/10 xe CAR đang bán đều có tài liệu; 80 feature flag `APPROVED`, 0 flag `PENDING`; pgvector với HNSW cosine index. Kiểm tra lại sau mỗi lần seed.

Coi là chạy được full flow khi đủ: migration cả 4 module ở `head`, backend chạy, `OPENAI_API_KEY` hợp lệ, corpus vector dựng xong ở mục 6.4, mọi xe đang bán có tài liệu, flag cần dùng ở `APPROVED`, script kiểm tra Lớp 2 ở trên cho ra dòng `DOCUMENT` cho từng xe, và `pytest tests/agents` pass. Lỗi `403` từ LangSmith không tính là blocker.

---

# Phần B — Frontend

## 9. Cấu hình frontend production

Nếu đã chạy mục 3 thì frontend production đã được cài dependency từ `package-lock.json`, build và khởi động trong Docker. Không cần chạy `npm install` hoặc `npm run dev` trên máy host.

Compose build frontend với các giá trị mặc định:

```env
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1
NEXT_PUBLIC_DEMO_MODE=false
```

`NEXT_PUBLIC_DEMO_MODE=false` khiến role guard dùng dữ liệu Auth thật. Chỉ đổi thành `true` trong `docker-compose.yml` khi cần xem prototype không đăng nhập.

`NEXT_PUBLIC_API_BASE_URL` phải là `localhost`, **không** đổi thành tên service `backend` hoặc `127.0.0.1`. Request được gửi từ trình duyệt, nơi hostname `backend` không tồn tại. Cookie phiên dùng tiền tố `__Host-`, nên frontend và backend cũng phải dùng cùng hostname `localhost`.

Cả hai cùng chạy trên `localhost` (khác port) thì trình duyệt xem là **same-site**, nên `SameSite=lax` của cookie phiên vẫn hoạt động. Cookie đặt cờ `Secure`, và `http://localhost` được Chrome/Firefox tính là secure context nên không cần HTTPS cho local.

## 10. Mở frontend hoặc chạy hot reload tùy chọn

Frontend production mở tại `http://localhost:3000`.

`NEXT_PUBLIC_*` được Next.js nhúng vào bundle tại lúc build. Sau khi đổi giá trị, phải chạy `docker compose up -d --build frontend`; chỉ restart container sẽ không áp dụng giá trị mới.

Khi đang sửa giao diện và cần hot reload, dừng riêng container frontend rồi chạy local:

```bash
docker compose stop frontend
cd frontend
cp .env.example .env
npm install
npm run dev
```

File `frontend/.env` mặc định cho local vẫn dùng:

```env
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000/api/v1
NEXT_PUBLIC_DEMO_MODE=false
```

## 11. Kiểm tra luồng dữ liệu thật

**Không dùng form Đăng ký.** `POST /api/v1/auth/register` tạo tài khoản ở trạng thái `pending_verification` rồi gửi mail xác thực qua SendGrid. Máy dev không cấu hình `AUTH_SENDGRID_API_KEY` thì bước gửi mail ném `EmailDeliveryError`, cả transaction rollback — **không có tài khoản nào được tạo**, request treo tới khi timeout. Token xác thực chỉ lưu dạng hash trong `auth_one_time_tokens` nên cũng không moi lại được từ DB. Dùng tài khoản Admin tạo ở bước 6.1.

Kiểm tra tài khoản đã `active`:

```bash
docker exec p-150-postgres-1 psql -U p150_auth -d p150_auth \
  -c "select email, role, state from auth_users;"
```

Cột `state` phải là `active`. Nếu là `pending_verification` thì đăng nhập sẽ bị chặn ngay tầng domain.

Sau đó:

1. Vào `http://localhost:3000/login`, đăng nhập bằng tài khoản bước 6.1. **Hiện frontend form vẫn gọi `/auth/login` dành cho CUSTOMER**, dù client đã có `staffLogin`; vì vậy Admin chưa đăng nhập được qua form cho tới khi frontend chọn `/auth/staff/login` cho staff. Để kiểm tra backend Admin ngay, gọi endpoint staff trực tiếp hoặc dùng Swagger.
2. Đăng nhập xong, header phải hiện email thật lấy từ `GET /api/v1/auth/me` (bấm "Tài khoản" để mở popover).
3. Mở DevTools → Application → Cookies → `http://localhost`. Phải thấy 3 cookie:

| Cookie | Path | HttpOnly | Vai trò |
|---|---|---|---|
| `__Host-p150_access` | `/` | có | access token |
| `__Secure-p150_refresh` | `/api/v1/auth` | có | refresh token |
| `__Host-p150_csrf` | `/` | không | frontend đọc rồi echo qua header `X-CSRF-Token` |

4. Bấm Đăng xuất — cookie phải bị xoá, header quay về trạng thái chưa đăng nhập.

Thiếu cookie thì xem mục 15.

## 11b. Test luồng agent end-to-end trên giao diện

Đây là luồng chính của sản phẩm: khách chat với agent → agent dựng bản nháp → tư vấn viên thấy hàng đợi, đọc bản nháp kèm ảnh so sánh, bấm duyệt → khách nhận nội dung ngay trên trang đang mở, không cần tải lại.

### Điều kiện trước khi bắt đầu

| Cần có | Kiểm tra bằng |
|---|---|
| `OPENAI_API_KEY` hợp lệ trong `.env` | mục 2 — thiếu thì agent không trích được slot, hỏi vòng quanh mãi |
| Corpus vector đã dựng | mục 6.4 |
| Ảnh xe đã đồng bộ | mục 6.5 — thiếu thì ảnh so sánh ra ô giữ chỗ |
| `COMPARISON_IMAGE_DIR` trỏ thư mục ghi được | mục 2 — thiếu thì ảnh luôn `null` |
| Một tài khoản `customer` domain `@gmail.com` | mục 6.1 |
| Một tài khoản `advisor` | mục 6.1 |
| `NEXT_PUBLIC_DEMO_MODE=false` trong `docker-compose.yml` (production) hoặc `frontend/.env` (hot reload local) | mục 12 |

### Bẫy cổng 8000

Container `p-150-backend-1` giữ cổng 8000. Nếu bạn vừa sửa code backend mà **không** build lại image (mục 7), container vẫn chạy code cũ và `/api/v1/agent/review` trả 404 trong khi mọi thứ khác trông vẫn bình thường. Hai cách:

```bash
# Cách 1 — build lại container (giữ nguyên mọi thứ khác)
docker compose up -d --build backend

# Cách 2 — nhường cổng cho uvicorn chạy từ mã nguồn đang sửa
docker stop p-150-backend-1
set -a; source .env; set +a
export LANGCHAIN_TRACING_V2=false LANGSMITH_TRACING=false
uv run uvicorn src.main:app --port 8000
# xong việc: docker start p-150-backend-1
```

Xác nhận đang chạy đúng bản có agent review:

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/api/v1/agent/review
# 401 = endpoint tồn tại, chỉ thiếu đăng nhập. 404 = đang chạy image cũ.
```

### Chạy kịch bản

Mở **hai cửa sổ trình duyệt tách biệt** — một thường, một ẩn danh. Hai vai dùng chung một cửa sổ sẽ ghi đè cookie phiên của nhau.

**Cửa sổ 1 — khách:**

1. `http://localhost:3000/login`, đăng nhập tài khoản `customer` domain `@gmail.com`.
2. Vào `http://localhost:3000/consultation`, gõ: `Tôi cần xe điện 5 chỗ, ngân sách 800 triệu`.
3. Trả lời các câu hỏi tiếp theo. Trả lời **thẳng vào câu đang hỏi** — gộp nhiều ý một lần thì phần trích slot hay bỏ sót, agent sẽ hỏi lại đúng câu đó. Ví dụ khi bị hỏi số chỗ, trả lời `Xe chở 5 người`.
4. Khi màn hình chuyển sang "Đề xuất đang được tư vấn viên kiểm tra", **để nguyên tab đó**, đừng tải lại.

**Cửa sổ 2 — tư vấn viên:**

5. `http://localhost:3000/staff-login`, đăng nhập tài khoản `advisor`.
6. Vào `http://localhost:3000/advisor` — bản nháp vừa tạo phải nằm trong hàng đợi, trạng thái "Chờ duyệt".
7. Bấm "Xem & duyệt". Màn chi tiết phải hiện **bản nháp đầy đủ và ảnh bảng so sánh**. Đây là điểm kiểm chính: thấy ảnh nghĩa là mục 6.5 và `COMPARISON_IMAGE_DIR` đều đúng.
8. Bấm "Duyệt nguyên trạng".

**Quay lại cửa sổ 1:** nội dung đã duyệt kèm ảnh so sánh phải tự hiện ra trong vài giây, **không tải lại trang**. Đó là kênh SSE `/api/v1/agent/events/{session_id}` hoạt động.

### Kiểm chứng bằng dữ liệu

```bash
docker exec -e PGPASSWORD=p150_local_dev p-150-postgres-1 psql -U p150_auth -d p150_auth -tA \
  -c "select status, count(*) from review_queue group by status"
```

Phải có ít nhất một dòng `APPROVED`.

### Khi không ra như mong đợi

| Triệu chứng | Nguyên nhân đã gặp thật |
|---|---|
| Lượt chat trả `terminal_reason: GUARDRAIL_FAILED_ADVISOR_HANDOFF`, không vào hàng đợi | Guardrail từ chối bản nháp sau 3 lần thử. Là hành vi backend, không phải lỗi UI — tạo phiên mới và chat lại thường qua được |
| Agent hỏi đi hỏi lại đúng một câu | Phần trích slot không lấy được giá trị từ câu trả lời. Trả lời ngắn, thẳng vào câu hỏi |
| Màn duyệt hiện "Chưa dựng được ảnh so sánh cho mục này" | Run chỉ xếp hạng được dưới 2 xe, hoặc chưa chạy mục 6.5, hoặc `COMPARISON_IMAGE_DIR` không ghi được |
| Cửa sổ khách chờ mãi dù advisor đã duyệt | `InMemoryTurnEventBroker` sống trong **một** process — không chạy uvicorn với `--workers > 1` |
| `/advisor` báo không có quyền | Đăng nhập nhầm đường. Nhân sự phải vào `/staff-login`, không phải `/login` |
| Đăng nhập khách báo `invalid_credentials` dù mật khẩu đúng | Email khách không thuộc domain `@gmail.com` |

Runbook rút gọn chỉ cho phần demo này: `docs/runbooks/demo-agent-frontend.md`. Bản kiểm chứng thuần HTTP (không qua giao diện): `docs/runbooks/smoke-agent-end-to-end.md`.

## 12. Bật chặn theo role thật

Với `NEXT_PUBLIC_DEMO_MODE=true`, `/advisor` và `/admin` mở cho mọi người, không kiểm tra role. Muốn chặn thật theo role trong DB, giữ cấu hình sau trong build args của service `frontend` ở `docker-compose.yml` (production) hoặc trong `frontend/.env` (hot reload local):

```env
NEXT_PUBLIC_DEMO_MODE=false
```

Biến `NEXT_PUBLIC_*` được nhúng lúc build. Với production Docker, áp dụng thay đổi bằng `docker compose up -d --build frontend`. Với hot reload local, dừng rồi chạy lại `npm run dev`.

Khi đó `RoleGuard` (`src/components/shared/role-guard.tsx`) lấy role từ `/api/v1/auth/me`:

- chưa đăng nhập → tự chuyển về `/login`
- sai role → hiện "Không có quyền truy cập"
- `/admin` cần role `admin`, `/advisor` cần role `advisor`

Tài khoản tạo bằng `create-admin` có role `admin` nên vào được `/admin`, và **bị chặn** ở `/advisor` — đây là hành vi đúng.

## 13. Phần nào là dữ liệu thật, phần nào còn mock

| Khu vực | Nguồn dữ liệu | Ghi chú |
|---|---|---|
| Đăng nhập / Đăng xuất / phiên | **Thật** — `/api/v1/auth/*` | `src/lib/api/auth.ts` |
| Email + role trên header | **Thật** — `/api/v1/auth/me` | `src/store/auth-store.tsx` |
| Chặn role `/admin`, `/advisor` | **Thật** khi `NEXT_PUBLIC_DEMO_MODE=false` | `src/components/shared/role-guard.tsx` |
| Đăng ký tài khoản | Gọi API thật nhưng **hỏng trên máy dev** | Cần SendGrid, xem mục 11 |
| Danh sách xe (`/vehicles`) | **Thật** — `/api/v1/vehicles` | `src/lib/api/vehicles.ts` → `src/components/catalog/vehicle-catalog.tsx` |
| So sánh xe (`/compare`) | **Thật** — `/api/v1/vehicles` | `src/components/comparison/vehicle-comparison.tsx` |
| TCO (`/tco`) | **Thật** — `/api/v1/vehicles/{identifier}/tco` | `src/components/tco/tco-calculator.tsx` |
| Trạm sạc & showroom (`/locations`) | **Thật** — `/api/v1/locations*` | `src/lib/api/locations.ts` → `src/components/locations/location-finder.tsx`; cần migration + seed locations (mục 6) |
| Admin: danh sách xe (`/admin/vehicles`) | **Thật** — `/api/v1/admin/vehicles` | `src/components/admin/catalog-preview.tsx` |
| Admin: quản lý user | **Thật** — `/api/v1/admin/*` | `src/components/admin/user-management-preview.tsx` |
| Menu xe trên header | **Mock** — `src/mocks/vehicles.ts` | `src/components/shared/app-header.tsx` |
| Gợi ý (`/recommendations`) | **Mock** | `src/mocks/recommendations.ts`, `src/mocks/vehicles.ts` |
| Đặt lịch lái thử (trang `/test-drive`) | **Thật** — `/api/v1/agent/bookings/options` rồi `POST /api/v1/agent/bookings` | `src/lib/api/assignments.ts` → `src/components/booking/booking-form.tsx` |
| Đặt lịch lái thử **trong hội thoại** | **Thật** — thẻ chọn showroom + khung giờ; đổi ngày gọi `GET /api/v1/agent/test-drive/availability` | `src/components/consultation/test-drive-card.tsx`; mã nút là giấy phép có chữ ký, xem `docs/adr/0001-giay-phep-khung-gio-lai-thu.md` |
| Hội thoại tư vấn (`/consultation`) | **Thật** — `/api/v1/agent/turn` | `src/lib/api/agent.ts` → `src/components/consultation/consultation-flow.tsx`; phiên giữ trong `src/store/agent-session.tsx` |
| Chờ duyệt + nhận nội dung đã duyệt | **Thật** — SSE `/api/v1/agent/events/{session_id}` rồi `/api/v1/agent/deliveries/{session_id}` | `src/components/consultation/pending-approval.tsx`, `delivered-answer.tsx` |
| Hàng chờ advisor | **Thật** — `/api/v1/agent/review` | `src/components/advisor/advisor-queue-table.tsx` |
| Duyệt đề xuất + ảnh so sánh | **Thật** — `/api/v1/agent/review/{id}` rồi `claim`/`approve`/`reject` | `src/components/advisor/advisor-review-panel.tsx` |
| Lịch sử khách hàng | **Mock** | `src/components/customer/customer-history.tsx` |
| Khách hàng của advisor | **Mock** | `src/mocks/people.ts` |
| Thông báo nội bộ (advisor + admin) | **Mock** | `src/mocks/admin.ts` |
| Dashboard admin (số liệu) | **Mock** | `src/mocks/admin.ts` |

Backend đã có API thật cho phần lớn mảng còn mock ở trên (booking, history, notice, analytics — xem `src/api/router.py`); phần thiếu là client và component phía frontend.

Hai giới hạn của phần agent đã nối: hàng đợi advisor chỉ hiện mục `PENDING` vì `GET /api/v1/agent/review` chưa nhận tham số lọc trạng thái — muốn có tab "Đã duyệt"/"Đã từ chối" thì phải mở rộng backend trước. Và trang `/recommendations` vẫn là mock, tách biệt hoàn toàn với nội dung agent gửi qua `/consultation`.

## 14. Nối phần frontend còn lại vào API thật

Catalog đã nối xong: `frontend/src/lib/api/vehicles.ts` và `frontend/src/lib/api/locations.ts` đã tồn tại và được các trang `/vehicles`, `/compare`, `/tco`, `/locations`, `/admin/vehicles` dùng thật. Việc còn lại là nối các component trong bảng mục 13 đang đánh dấu **Mock**.

Cách làm cho mỗi mảng:

1. Liệt kê file còn dùng mock:

   ```bash
   grep -rn "@/mocks" frontend/src
   ```

2. Viết client mới trong `frontend/src/lib/api/` theo đúng khuôn `auth.ts` / `vehicles.ts`: dùng chung `API_BASE_URL` (`process.env.NEXT_PUBLIC_API_BASE_URL`), `credentials: "include"` cho endpoint cần đăng nhập, và echo cookie CSRF `__Host-p150_csrf` qua header `X-CSRF-Token` cho mọi request đổi trạng thái (POST/PATCH/PUT/DELETE).
3. Ánh xạ lại field: API trả `{ data: [...], pagination, meta }` và spec dạng chuỗi số (vd `"210.00"`), tên trường khác nhau giữa `CAR` và `ELECTRIC_MOTORBIKE`; mock là mảng phẳng đã chuẩn hoá. Hai shape khác nhau nên phải viết lớp chuyển đổi trong client, không thay thẳng import được — xem cách `vehicles.ts` chuyển `ApiVehicleDetail` → `CatalogVehicle`.
4. Mẫu tham chiếu gần nhất là phần agent vừa nối xong: `src/lib/api/agent.ts` (client), `src/store/agent-session.tsx` (state của một phiên, reducer thuần có test ở `agent-session.test.ts`), và ba component `consultation-flow.tsx`, `pending-approval.tsx`, `advisor-review-panel.tsx`. Đây cũng là chỗ duy nhất trong frontend có test tự động — chạy bằng `npx vitest run` trong `frontend/`.

## 15. Sự cố thường gặp

### Agent và RAG

**`pytest tests/agents` chết ngay với `asyncpg.exceptions.InvalidPasswordError`** — chưa export `AGENT_DATABASE_URL`. Xem mục "Lệnh test Agent".

**Agent trả lời được nhưng không bao giờ có trích dẫn tài liệu** — corpus rỗng. Kiểm tra `select count(*) from vehicle_documents where status='ACTIVE' and embedding is not null;`. Bằng 0 thì chạy mục 6.4. Lưu ý 119 dòng seed từ CSV đều `ARCHIVED` và không có embedding nên không tính.

**Ghi embedding vào DB báo lỗi số chiều** — `OPENAI_API_KEY` sai hoặc hết hạn. Adapter nuốt lỗi API rồi tụt xuống vector băm 1536 chiều, trong khi cột là `Vector(1024)`. `build_car_documents.py` chặn sẵn trường hợp này và dừng với thông báo `Embedding sai chieu`.

**Một xe không bao giờ được đề xuất** — kiểm tra `vehicles.status`. VF Wild để `ARCHIVED` có chủ đích: đây là xe concept ra mắt CES 2024, chưa từng sản xuất hay bán, nên không được xuất hiện trong tư vấn.

**Feature flag đã có trong DB nhưng agent không dùng** — flag đang ở `PENDING`. Lớp 2 chỉ đọc `APPROVED`.

**Tài liệu có nội dung đúng nhưng agent vẫn trả `UNKNOWN`** — đúng thiết kế, không phải lỗi. Đoạn trích phải nhắc tới đúng tính năng thì mới được kết luận `YES`; trúng truy vấn ngữ nghĩa là chưa đủ.

**Ảnh so sánh luôn `null` mà không có lỗi nào** — `image_for_review` bắt mọi ngoại lệ rồi trả `None`, nên hỏng ở đâu cũng ra cùng một triệu chứng. Kiểm tra theo thứ tự: `COMPARISON_IMAGE_DIR` có ghi được bằng tài khoản đang chạy backend không (mục 2); `vehicles.image_object_key` đã khác rỗng chưa (mục 6.5); run có xếp hạng được từ 2 xe trở lên không. Traceback thật nằm ở `logs/app.log`, tìm dòng `khong dung duoc anh so sanh`.

**`POST /api/v1/agent/turn` trả 500 ngay lượt đầu** — uvicorn định tuyến log qua cấu hình của app nên traceback **không** hiện ở stdout của tiến trình; đọc `logs/app.log`.

### Auth, frontend và hạ tầng

**`{"error":"origin_forbidden"}` (403)** — `Origin` của request không nằm trong `AUTH_CORS_ORIGINS`. Sửa `.env` gốc rồi `docker compose up -d --build backend`. Gọi bằng curl không kèm `-H "Origin: http://localhost:3000"` cũng dính lỗi này.

**Đăng nhập báo thành công nhưng vẫn hiện chưa đăng nhập** — cookie không được gửi kèm. Kiểm tra theo thứ tự: `NEXT_PUBLIC_API_BASE_URL` dùng `localhost` chứ không phải `127.0.0.1`; DevTools → Network → request `login` có header `set-cookie`; không mở frontend qua IP LAN (cookie `__Host-` gắn host-only).

**Form Đăng ký treo rồi báo lỗi** — thiếu SendGrid, xem mục 11. Đây là hành vi đã biết, không phải hỏng cấu hình. Gọi thẳng API cũng vô ích: `POST /api/v1/auth/register` trả `{"error":"registration_unavailable"}` khi tính năng đang tắt. Tài khoản test lấy từ mục 6.1.

**Sửa cấu hình frontend mà giao diện không đổi hành vi** — biến `NEXT_PUBLIC_*` được nhúng lúc build. Với Docker, chạy `docker compose up -d --build frontend`; với dev-server local, tắt `npm run dev` rồi chạy lại. Tải lại trang hoặc chỉ restart container là không đủ.

**`/api/v1/agent/review` trả 404 trong khi các endpoint khác bình thường** — container `p-150-backend-1` đang chạy image cũ hơn mã nguồn. Xem "Bẫy cổng 8000" ở mục 11b.

**Đăng nhập trả `invalid_credentials` dù mật khẩu đúng** — các nguyên nhân:
- Email CUSTOMER không phải đuôi `@gmail.com`. `/api/v1/auth/login` chỉ dành cho khách hàng, domain khác bị từ chối ngay ở bước validate email.
- Admin/Advisor đang bị gửi nhầm vào `/api/v1/auth/login`; dùng `POST /api/v1/auth/staff/login`. Frontend hiện chưa tự chọn endpoint staff trong form login.
- Kiểm tra `state` trong `auth_users`. `pending_verification`, `temporary_password` hoặc `disabled` không đi qua luồng login active thông thường.

**Frontend gọi `/api/v1/vehicles` nhận 404** — container backend còn image cũ, chưa có route xe. Chạy `docker compose up -d --build backend`.

**`{"detail":"Vehicle catalog service unavailable"}` (503)** — backend không đọc được `PRODUCT_DATABASE_URL`. Biến này lấy trực tiếp từ biến môi trường của tiến trình (fallback sang `AUTH_DATABASE_URL`), **không** tự nạp từ file `.env`. Chạy trong Docker thì `env_file` lo việc này; chạy `uvicorn` tay ngoài Docker thì phải export trước:

```bash
export PRODUCT_DATABASE_URL="postgresql+asyncpg://p150_auth:p150_local_dev@localhost:5432/p150_auth"
```

**`docker compose build` dừng ở `Failed to download distribution due to network timeout`** — mạng tới registry/PyPI chậm, không phải lỗi dependency. Chạy lại thường tận dụng cache. Nếu lặp lại, tăng timeout trong build bằng cách thêm `ENV UV_HTTP_TIMEOUT=300` trước dòng `RUN uv sync ...` trong `Dockerfile`, rồi build lại. Lưu ý biến `UV_HTTP_TIMEOUT=300` ở shell không tự truyền vào Docker build nếu Dockerfile không khai báo `ARG`/`ENV`.

**`npm install` hoặc `docker compose build` báo `too many levels of symbolic links`** — `frontend/node_modules` bị biến thành symlink trỏ vào chính nó. Sửa:

```bash
cd frontend && rm -f node_modules && npm install
```

**`docker compose build` fail giữa chừng, sau đó đĩa đầy** — build dở dang để lại cache rác. Kiểm tra và dọn:

```bash
df -h /
docker system df
docker builder prune -f    # chỉ xoá build cache, không đụng image/container/volume
```

**Cảnh báo `collation version mismatch` từ psql** — vô hại, do khác version libc giữa container và host. Cảnh báo này cũng làm các test tích hợp cần Postgres báo lỗi hàng loạt; test unit không bị ảnh hưởng.

**Không mở được `http://localhost:5050`, hoặc pgAdmin báo sai tài khoản dù gõ đúng** — kiểm tra `docker compose ps pgadmin`. Nếu `STATUS` là `Restarting` liên tục, xem log: `docker logs p-150-pgadmin-1 --tail 20`. Container crash-loop, không liên quan gì tới việc gõ sai email/mật khẩu — port không bao giờ lên nên trình duyệt không kết nối được. Nguyên nhân hay gặp: `PGADMIN_DEFAULT_EMAIL` dùng domain dự trữ (`.test`, `.example`, `.invalid`, `.local`...) bị thư viện validate email của pgAdmin từ chối thẳng. Đổi sang domain thường (`.com`) trong `.env`, xoá volume cũ rồi tạo lại:

```bash
docker compose stop pgadmin
docker rm -f p-150-pgadmin-1
docker volume rm p-150_pgadmin_data
docker compose up -d pgadmin
docker compose ps pgadmin   # đợi healthy
```

**`RuntimeError: ..._DATABASE_URL is required...` khi chạy `uv run alembic` hoặc `uv run python -m src.cli`** — biến trong `.env` không tự nạp vào lệnh chạy tay ngoài Docker (chỉ container `backend` được `env_file` nạp hộ). Export trước, **mỗi terminal/phiên mới đều phải export lại** vì biến không lưu qua các lần mở shell khác nhau:

```bash
set -a
source .env
set +a
```

Cách này giữ đúng giá trị có ký tự đặc biệt hoặc khoảng trắng. Không dùng `export $(grep ... | xargs)` vì shell có thể tách hoặc biến đổi giá trị.

Kiểm tra nhanh biến đã có chưa: `echo "$AUTH_DATABASE_URL"` — rỗng nghĩa là export chưa chạy trong shell hiện tại.

**`src.auth.composition.AuthStartupError: Auth resources are unavailable; Auth is disabled or not started`** khi chạy `create-admin` — `.env` đang có `AUTH_ENABLED=false` (giá trị mặc định trong `.env.example`). Xác nhận đã set `AUTH_ENABLED=true` ở bước 2 rồi export lại (xem mục ngay trên).

**`asyncpg.exceptions.InvalidPasswordError: password authentication failed for user "p150_auth"`** dù `.env` đúng — ba nguyên nhân hay gặp:
- DSN còn placeholder nguyên văn như `<password>` hoặc dùng `change-me-locally`, trong khi `.env.example` đặt `POSTGRES_PASSWORD=p150_local_dev`. Mọi `*_DATABASE_URL` phải dùng cùng password với `POSTGRES_PASSWORD`.
- Volume Postgres đã tồn tại từ trước với password khác (script khởi tạo trong `docker-entrypoint` chỉ chạy **một lần** lúc volume rỗng; đổi `POSTGRES_PASSWORD`/`.env` sau đó không tự áp lại). Reset password khớp `.env` qua kết nối nội bộ container:
  ```bash
  docker exec p-150-postgres-1 psql -U p150_auth -d p150_auth \
    -c "ALTER USER p150_auth WITH PASSWORD 'p150_local_dev';"
  ```
- `scripts/seed_catalog_data.py` đọc DSN từ biến `PRODUCT_DATABASE_URL_SYNC` (không phải `PRODUCT_DATABASE_URL`), biến này không có trong `.env` nên rơi về DSN mặc định hard-code trong script (password khác). Truyền `--dsn` tay, xem mục 6.2.

---

## Khởi động lại ở những lần sau

Mục 1–8 là việc **một lần**. Đã chạy xong một lượt thì những lần sau bỏ qua toàn bộ migration, seed catalog, dựng corpus vector, đồng bộ ảnh và tạo tài khoản — dữ liệu nằm trong Docker volume, sống độc lập với container.

Ba lệnh để bật và kiểm tra toàn bộ hệ thống:

```bash
cd <thư mục repo>
docker compose up -d --build
docker compose ps
```

Khi cần sửa frontend với hot reload thay vì chạy image production:

```bash
docker compose stop frontend
cd frontend && npm install && npm run dev
```

Kiểm tra trong mười giây:

```bash
docker compose ps                                  # cả 5 service phải "healthy"
curl -s -o /dev/null -w "%{http_code}\n" localhost:3000
curl -s localhost:8000/health                      # {"status":"ok",...}
curl -s -o /dev/null -w "%{http_code}\n" localhost:8000/api/v1/agent/review
```

Lệnh cuối trả `401` là đúng — endpoint tồn tại, chỉ thiếu đăng nhập. Trả `404` nghĩa container backend đang chạy image cũ hơn mã nguồn: `docker compose up -d --build backend`.

**Xoá container không làm mất dữ liệu.** Đã kiểm chứng: sau khi container `p-150-postgres-1` biến mất hoàn toàn khỏi Docker, `docker compose up -d postgres minio` dựng lại và dữ liệu còn nguyên (51 xe, 362 chunk vector, 49 xe có ảnh, tài khoản và hàng đợi duyệt). Chỉ `docker compose down -v` hoặc xoá tay volume `p-150_postgres_data` / `p-150_minio_data` mới mất — khi đó phải làm lại từ mục 4.

Một cái bẫy đáng nhớ: nếu Docker daemon khởi động lại hoặc ai đó chạy `docker compose down` trong khi uvicorn local vẫn sống, backend **vẫn trả `401` bình thường** cho `/api/v1/agent/review` vì đường đó chỉ kiểm cookie, chưa chạm database. Hệ thống trông như đang chạy cho tới khi có request thật sự đọc DB. Vì vậy luôn xem `docker compose ps` trước khi kết luận mọi thứ ổn.

Kiểm tra nhanh dữ liệu còn đủ hay không:

```bash
docker exec -e PGPASSWORD=p150_local_dev p-150-postgres-1 psql -U p150_auth -d p150_auth -tA \
  -c "select (select count(*) from vehicles) as xe,
             (select count(*) from vehicle_documents where status='ACTIVE' and embedding is not null) as chunk_vector,
             (select count(*) from vehicles where image_object_key is not null) as co_anh,
             (select count(*) from auth_users) as tai_khoan"
```

Cột nào bằng 0 thì chạy lại đúng mục tương ứng: `xe` → 6.2, `chunk_vector` → 6.4, `co_anh` → 6.5, `tai_khoan` → 6.1.

## Chạy lại từ đầu

Chỉ frontend:

```bash
cd frontend
rm -rf .next node_modules
npm install
npm run dev
```

Toàn bộ, xoá sạch volume:

```bash
docker compose down -v
```

rồi làm lại từ bước 3. `-v` xoá luôn `postgres_data`/`minio_data`/`pgadmin_data` — mất hết dữ liệu đã nạp (kể cả tài khoản Admin và catalog xe), chỉ dùng khi thực sự muốn tái tạo sạch.
