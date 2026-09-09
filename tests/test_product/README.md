# Hướng dẫn chạy test & xử lý bug — Vehicle Catalog (Refactored Schema)

Tài liệu này mô tả cách chạy test, xác minh dữ liệu CSV, và xử lý các bug
thường gặp sau khi refactor module **Products** theo schema mới (11 bảng) định
nghĩa tại:

- `src/products/domain/entities.py`
- `src/products/domain/values.py`
- `migrations/products/versions/d4e5f6a7b8c9_product_schema.py`

> Ba file trên là **source of truth** — không sửa.

---

## 1. Yêu cầu môi trường

- Python ≥ 3.11
- Postgres ≥ 14 (chỉ cần khi muốn seed/import dữ liệu thật)
- Tất cả dependency khai báo trong `pyproject.toml`. Cài bằng `uv` (khuyến nghị)
  hoặc `pip`:
  ```bash
  uv sync
  # hoặc
  pip install -e .[dev]
  ```

---

## 2. Cấu trúc đã chỉnh sửa

```
src/products/
├── application/
│   ├── __init__.py             # Port + DTO (VehicleDetail, CatalogSnapshot, PageParams)
│   └── vehicle_service.py      # VehicleCatalogService (Customer + Admin use cases)
├── composition.py              # Wiring engine → repo → service
├── domain/
│   ├── entities.py             # KHÔNG SỬA — source of truth
│   ├── errors.py               # ProductDomainError / NotFound / Permission
│   └── values.py               # Enum bám CHECK constraint trong migration
├── infrastructure/
│   ├── csv_import.py           # Loader 9 bảng catalog từ CSV
│   ├── models.py               # SQLAlchemy ORM (1-1 với migration)
│   ├── repositories.py         # SqlAlchemyVehicleRepository + _build_detail
│   └── seed_catalog.py         # Insert idempotent vào Postgres
└── presentation/
    ├── __init__.py             # Pydantic DTO + Standard Envelope
    └── routes.py               # FastAPI router (Customer + Admin)

crawl/data/refactor_vehicle_catalog/
├── vehicles.csv                # 52 xe (VinFast)
├── cars.csv                    # 11 dòng (VinFast cars)
├── motorbikes.csv              # 41 dòng (VinFast scooters)
├── vehicle_prices.csv          # 62 giá
├── promotions.csv              # 8 khuyến mãi
├── promotion_vehicles.csv      # 8 liên kết
├── battery_policies.csv        # 43 policy
├── feature_definitions.csv     # 7 feature definitions
├── vehicle_feature_flags.csv   # 114 flag
└── vehicle_documents.csv       # THUỘC document module — KHÔNG sửa

scripts/
└── refactor_csv_to_schema.py   # Idempotent: đọc CSV cũ → ghi CSV theo schema mới
```

---

## 3. Quy trình chuẩn sau khi pull source mới

```bash
# 1) Cài đặt deps
uv sync                                # hoặc: pip install -e .[dev]

# 2) Chạy lại script refactor CSV nếu CSV input thay đổi (idempotent)
python scripts/refactor_csv_to_schema.py

# 3) Chạy unit test
pytest tests/test_product/ -v --tb=short

# 4) (Tùy chọn) Lint
ruff check src/products tests/test_product
```

---

## 4. Chạy test

### 4.1 Tất cả test của Products

```bash
pytest tests/test_product/ -v
```

Kết quả mong đợi: **32 passed** trong thời gian < 1 giây.

### 4.2 Test một file cụ thể

```bash
pytest tests/test_product/test_csv_import.py -v
pytest tests/test_product/test_services.py -v
```

### 4.3 Test một case cụ thể

```bash
pytest tests/test_product/test_services.py::test_admin_create_vehicle_requires_admin -v
```

### 4.4 Các test được đảm bảo

| Nhóm | Test | Mục đích |
| --- | --- | --- |
| CSV | `test_load_all_returns_full_dataset` | Toàn bộ 9 bảng load được |
| CSV | `test_load_vehicles_returns_correct_entity` | Vehicle enum hợp lệ |
| CSV | `test_load_vehicle_prices_uses_vnd` | `currency=Currency.VND` |
| Integrity | `test_dataset_integrity_no_orphan_*` (×4) | FK không orphan |
| Integrity | `test_dataset_no_duplicate_*` (×2) | Unique constraint không vi phạm |
| Integrity | `test_dataset_cars_and_motorbikes_disjoint` | 1 vehicle chỉ thuộc 1 specs table |
| Service | `test_list_active_vehicles_filters_by_status` | ACTIVE filter |
| Service | `test_get_vehicle_detail_inactive_raises` | INACTIVE → 404 |
| Service | `test_admin_create_vehicle_requires_admin` | RBAC |
| Service | `test_rag_context_render` | Snapshot render markdown |

---

## 5. Seed dữ liệu vào Postgres (tùy chọn)

```bash
# 1) Khởi động Postgres + Alembic
docker compose up -d postgres
alembic -c alembic-products.ini upgrade head

# 2) Seed từ CSV đã refactor
python -m src.products.infrastructure.seed_catalog
```

Seed dùng `ON CONFLICT DO NOTHING` → chạy nhiều lần vẫn an toàn.

---

## 6. Bug thường gặp & cách xử lý

### 6.1 `ImportError: cannot import name 'VehicleDetail' from 'src.products.domain.entities'`

**Nguyên nhân**: Code cũ import `VehicleDetail` (DTO) từ domain. Trong schema mới,
`VehicleDetail` là application-layer DTO (xem `src/products/application/__init__.py`).

**Fix**:
```python
# SAI (cũ)
from src.products.domain.entities import VehicleDetail

# ĐÚNG (mới)
from src.products.application import VehicleDetail
```

### 6.2 `ValueError: invalid vehicle_type 'Xe ô tô'`

**Nguyên nhân**: CSV chưa qua refactor vẫn còn giá trị tiếng Việt hoặc lowercase.

**Fix**:
```bash
# Chạy lại script refactor CSV
python scripts/refactor_csv_to_schema.py
```
Script sẽ chuẩn hoá về `CAR` / `ELECTRIC_MOTORBIKE`. Nếu vẫn lỗi, kiểm tra
cột `vehicle_type` trong `vehicles.csv` — chỉ chấp nhận 2 giá trị trên.

### 6.3 `IntegrityError: null value in column "model_name" violates not-null constraint`

**Nguyên nhân**: Dòng CSV có `model_name` rỗng.

**Fix**:
1. Sửa file CSV nguồn để có `model_name` hợp lệ.
2. Nếu dữ liệu thật sự thiếu → **KHÔNG TỰ BỊA**. Giữ dòng đó và loại khỏi
   seed, hoặc đánh dấu `status=ARCHIVED` trong `vehicles.csv`.

### 6.4 `IntegrityError: duplicate key value violates unique constraint "uq_vehicles_slug"`

**Nguyên nhân**: Hai xe trùng slug. Có thể do seed chạy nhiều lần với `id` khác
nhau nhưng slug giống nhau.

**Fix**:
- Trong repository, slug đã được auto-de-duplicate bằng hậu tố `-1`, `-2`…
- Nếu chạy SQL thủ công: chỉnh slug trong CSV trước khi seed.

### 6.5 `CHECK constraint "ck_vehicle_features_status" violated`

**Nguyên nhân**: Cột `vehicle_feature_flags.status` không thuộc
`('YES', 'NO', 'UNKNOWN')`.

**Fix**: Đảm bảo script `refactor_csv_to_schema.py` được chạy — nó map
`True/False/None` sang `YES/NO/UNKNOWN`. Nếu tự thêm feature thủ công, dùng đúng
3 giá trị trên.

### 6.6 `CHECK constraint "ck_motorbikes_license" violated`

**Nguyên nhân**: `motorbikes.license_requirement` không thuộc
`('NONE', 'A1', 'A', 'UNKNOWN')` hoặc `NULL`.

**Fix**: Hiện tại CSV không chứa cột này → mapper để `NULL`. Nếu thêm dữ liệu,
dùng đúng 4 giá trị trên.

### 6.7 Test fail ở `test_admin_create_vehicle_requires_admin` với message
`ProductPermissionError`

**Đây không phải bug** — đó là hành vi đúng. Service ném lỗi khi caller không
phải admin. Kiểm tra route handler có truyền `is_admin` đúng từ auth context.

### 6.8 `ModuleNotFoundError: No module named 'src.products.application.car_service'`

**Nguyên nhân**: Code cũ vẫn import `CarService`/`MotorbikeService`/`PolicyService`.
Trong schema mới, các service này đã được gộp thành `VehicleCatalogService`.

**Fix**:
```python
# SAI
from src.products.application.car_service import CarService
from src.products.application.motorbike_service import MotorbikeService
from src.products.application.policy_service import PolicyService

# ĐÚNG
from src.products.application.vehicle_service import VehicleCatalogService
```

### 6.9 Postgres báo `psycopg2` / `asyncpg` không tìm thấy

```bash
pip install asyncpg     # nếu dùng SQLAlchemy async
pip install psycopg2-binary  # nếu dùng sync
```

### 6.10 Lint `ruff` cảnh báo `UP017 datetime.UTC`

Chạy auto-fix:
```bash
ruff check src/products tests/test_product --fix
```

---

## 7. Báo cáo refactor

### CSV đã refactor (10 file)

| File | Số dòng | Ghi chú |
| --- | --- | --- |
| `vehicles.csv` | 52 | UUID giữ nguyên; status chuẩn hoá về `ACTIVE/DRAFT/...` |
| `cars.csv` | 11 | Tách unit khỏi JSON-string `{'value':..., 'unit':...}` |
| `motorbikes.csv` | 41 | Tương tự `cars.csv` |
| `vehicle_prices.csv` | 62 | Đổi `amount`→`amount_vnd`, thêm `currency`/`region_code` |
| `promotions.csv` | 8 | Thêm `promotion_code`, `eligibility_rules` (JSONB), `approved_at` |
| `promotion_vehicles.csv` | 8 | Junction table, khoá chính `(promotion_id, vehicle_id)` |
| `battery_policies.csv` | 43 | Đổi `policy_type`→`ownership_model` enum |
| `feature_definitions.csv` | 7 | PK là `feature_code` (string) thay vì UUID |
| `vehicle_feature_flags.csv` | 114 | Map `feature_id` (UUID cũ) → `feature_code` qua bảng definitions |
| `vehicle_documents.csv` | — | KHÔNG SỬA (thuộc document module) |

### Code đã chỉnh sửa (Products module only)

| File | Thay đổi |
| --- | --- |
| `src/products/domain/values.py` | Thêm 12 enum (`VehicleType`, `VehicleStatus`, `Currency`, …) |
| `src/products/infrastructure/models.py` | Viết lại 11 bảng SQLAlchemy (đúng migration) |
| `src/products/infrastructure/csv_import.py` | Loader mới cho 9 bảng + `load_all()` |
| `src/products/infrastructure/repositories.py` | Repo duy nhất `SqlAlchemyVehicleRepository` |
| `src/products/infrastructure/seed_catalog.py` | Insert idempotent qua `pg_insert` |
| `src/products/application/__init__.py` | Port + DTO mới |
| `src/products/application/vehicle_service.py` | `VehicleCatalogService` thay thế 3 service cũ |
| `src/products/application/{car,motorbike,policy}_service.py` | **Đã xoá** |
| `src/products/presentation/__init__.py` | Pydantic DTO bám schema mới |
| `src/products/presentation/routes.py` | Router dùng `VehicleCatalogService` |
| `src/products/composition.py` | Wiring engine → repo → service |
| `scripts/refactor_csv_to_schema.py` | Mới — script reproducible |
| `tests/test_product/test_csv_import.py` | Viết lại theo schema mới |
| `tests/test_product/test_services.py` | Viết lại với `FakeVehicleRepository` |

### Không thay đổi (source of truth)

- `src/products/domain/entities.py`
- `src/products/domain/values.py` *(chỉ thêm enum, không sửa dataclass)*
- `migrations/products/versions/d4e5f6a7b8c9_product_schema.py`

### Dữ liệu thiếu & cách xử lý

| Trường | Lý do thiếu | Xử lý |
| --- | --- | --- |
| `model_year` | Crawl không có năm rõ ràng | Suy ra từ tên xe qua regex; nếu không có → `NULL` |
| `energy_consumption_kwh_per_100km` (motorbike) | Crawl không có | `NULL` (giữ NULL) |
| `towing_capacity_kg` | Crawl ghi `"0"` | Parse thành `Decimal("0")` → `towing_supported=false` |
| `eligibility_rules` | Crawl không có | `{}` (JSONB rỗng) |
| `created_by` / `updated_by` | Crawl không có | `"refactor_seed"` |
| `home_charge_time_minutes` | Crawl không có | `NULL` |
| `license_requirement` (motorbike) | Crawl không có | `NULL` (schema cho phép) |

### Kết quả kiểm tra tính toàn vẹn

| Test | Kết quả |
| --- | --- |
| FK orphan (prices/promotions/battery/flags) | **0** |
| Duplicate `vehicle_id` | **0** |
| Duplicate `slug` | **0** |
| Cars ∩ Motorbikes overlap | **0** (rỗng) |
| `pytest tests/test_product/ -v` | **32 passed** |

---

## 8. Đề xuất tiếp theo (ngoài scope hiện tại)

1. **Bổ sung `tco_assumptions.csv` & `feature_need_tags.csv`** — schema có sẵn
   nhưng CSV chưa có. Có thể đặt giá trị mặc định theo từng `vehicle_type` /
   `region_code`.
2. **Thêm bảng `tco_*` vào seed script** nếu dữ liệu có.
3. **Permission**: hiện `_get_role` đọc từ `request.cookies["access_token"]`.
   Có thể thay bằng `Depends(get_current_role)` của auth module.
4. **Pagination lớn**: hiện `OFFSET ... LIMIT` — chuyển sang keyset pagination
   nếu catalog > 100k dòng.
