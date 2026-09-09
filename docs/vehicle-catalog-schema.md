# Vehicle Catalog Schema

## 1. Mục đích và phạm vi

Tài liệu này mô tả schema catalog phương tiện cho VinFast AI Sales Advisor. Phạm vi chỉ gồm dữ liệu phương tiện, giá, khuyến mại, chính sách pin dạng structured tối thiểu, feature flags, giả định TCO và dữ liệu RAG gắn với phương tiện. Các bảng hội thoại, người dùng, booking và tài liệu nguồn vật lý nằm ngoài phạm vi này.

Thiết kế giữ hai bảng thông số chính ban đầu:

- `cars`: thông số riêng của ô tô.
- `motorbikes`: thông số riêng của xe máy điện.

Bảng `vehicles` là registry chung, dùng làm khóa liên kết cho dữ liệu phụ. Cách này giữ được mô hình hai bảng specs nhưng tránh phải dùng `car_id`/`motorbike_id` nullable trong mọi bảng phụ.

## 2. Kiến trúc hai lớp

```text
Lớp 1 - SQL Hard Filter
  vehicles + cars/motorbikes + vehicle_prices
  Lọc các điều kiện bắt buộc: loại xe, ngân sách, số ghế,
  tầm hoạt động, tải trọng, tốc độ, trạng thái bán.
  Output: candidate_vehicle_ids

Lớp 2 - Need & Feature Retriever
  feature_definitions + vehicle_feature_flags + feature_need_tags
  + vehicle_documents
  Một cửa duy nhất, năm nhánh, chọn nguồn rẻ trước:

    2a  khớp tính năng   câu khách -> feature_code       (vector, in-memory)
    2b  khớp nhu cầu     câu khách -> need_tag           (vector, in-memory)
    2c  tra flags        feature_code -> YES/NO/UNKNOWN  (SQL)
    2d  nở nhu cầu       need_tag -> feature_code[] -> 2c (SQL)
    2e  đọc tài liệu     hybrid dense + FTS, scoped      (CÓ ĐIỀU KIỆN)

  Nhánh 2a-2d chạy mọi lượt. Nhánh 2e chỉ nổ khi:
    - 2a và 2b đều không khớp được mã nào, HOẶC
    - flag trả UNKNOWN cho đúng điều kiện khách đang nêu, HOẶC
    - khách hỏi một câu diễn giải.

  Output: list[FeatureAssertion]

Ngoài hai lớp - Giả định TCO
  tco_assumptions
  Giá điện, phí lăn bánh, chi phí bảo dưỡng theo loại phương tiện.
  Không tham gia lọc; là input của công thức TCO.

Sau xếp hạng - Giới thiệu theo nhu cầu
  feature_need_tags
  Ánh xạ nhu cầu đã xác nhận sang feature đáng giới thiệu.
  Không tham gia lọc; quyết định feature nào được nói tới
  mà khách chưa hỏi.
```

Nguyên tắc:

1. Dữ liệu cần tính, lọc hoặc so sánh phải là field có kiểu số/enum trong database.
2. RAG không được quyết định giá, số ghế, tầm hoạt động hoặc điều kiện cứng.
3. RAG chỉ được tìm trong `vehicle_id` đã qua Lớp 1.
4. Xe chưa ở trạng thái `ACTIVE` không được dùng cho tư vấn khách hàng.
5. Admin tạo hoặc cập nhật catalog trong một transaction.
6. **Luật thẩm quyền `FLAG` / `DOCUMENT`** — quyết định lọc và xếp hạng thuộc về structured data; tài liệu chỉ được bổ sung. Chi tiết ở mục 7.2.
7. Mọi chiều mở rộng của catalog phải là **một dòng dữ liệu**, không phải một cột mới, một nhánh code hay một dòng prompt. Feature mới đi qua `feature_definitions`; nhu cầu mới đi qua `feature_need_tags`; con số mới được phép nói ra đi qua allowlist ở mục 7.5.

### Vì sao hai lớp chứ không phải ba

Bản trước tách `vehicle_feature_flags` (Lớp 2) và `vehicle_documents` (Lớp 3) thành hai lớp tuần tự, trong đó Lớp 3 bị **cấm** chạy khi feature đã có mã. Ba hệ quả khiến thiết kế đó phải đổi:

1. **Xe `UNKNOWN` kẹt vĩnh viễn.** Xe mới tạo mang toàn bộ flag `UNKNOWN` (mục 6.1/6.2). Feature có mã nên Lớp 3 bị cấm, không có đường nào nâng `UNKNOWN` lên `YES` — Agent trả lời "chưa xác định" cho tới khi Admin nhập tay từng ô.
2. **Nhu cầu mềm không có đường xử lý.** Khách nói "hay đi trong phố" không khớp `feature_code` nào; Lớp 2 bỏ qua, Lớp 3 chỉ diễn giải chứ không nuôi xếp hạng. Slot rơi mất.
3. **Đọc tài liệu xong thì vứt.** Mỗi lượt đọc lại từ đầu, không để lại gì.

Gộp thành một lớp với điều kiện nổ đặt lại theo **"flags có kết luận được hay không"** (thay vì "feature có mã hay không") giải quyết cả ba, và mở đường cho vòng ghi ngược ở mục 7.2.

## 3. Quy ước dữ liệu

### 3.1. Kiểu dữ liệu

Thiết kế mục tiêu là PostgreSQL 16, SQLAlchemy 2 và Alembic.

| Quy ước | Khuyến nghị |
|---|---|
| ID thực thể catalog (`vehicle_id`, `price_id`, `promotion_id`...) | `uuid` |
| ID người dùng tham chiếu tới module auth (`created_by`, `updated_by`, `approved_by`) | `varchar(64)` |
| Tiền | `bigint` lưu số VND nguyên, không dùng `float` |
| Đo lường | `numeric` hoặc `integer` với đơn vị nằm trong tên field |
| Thời gian | `timestamptz` |
| Cờ | `boolean` |
| Trạng thái | enum PostgreSQL hoặc `CHECK` |
| Nội dung mở | `text` |
| Điều kiện ít query | `jsonb`, không dùng cho điều kiện hard filter |

Không lưu các giá trị như `"420 km"`, `"3.500 W"` hoặc `"6 giờ"` trong field cần query. Lưu lần lượt là `420`, `3500`, `360` với đơn vị thể hiện trong tên cột.

**ID thực thể và ID người dùng không cùng kiểu, không được nhầm lẫn.** `auth_users.id` (module auth) là `VARCHAR(64)`, không phải `UUID` — mọi cột tham chiếu tới người dùng (`created_by`, `updated_by`, `approved_by`) trên toàn bộ catalog phải khai `VARCHAR(64)` để khớp, dù chỉ là tham chiếu mềm (không FK, vì catalog không phụ thuộc cứng vào schema auth). Khai UUID cho các cột này là sai kiểu, không so sánh được với `auth_users.id` nếu sau này cần join hoặc validate.

### 3.2. Trạng thái chung

```text
DRAFT       Dữ liệu đang nhập, chưa xuất hiện với khách hàng.
ACTIVE      Dữ liệu đã kiểm tra và được dùng cho truy vấn.
INACTIVE    Tạm ngừng bán hoặc tạm ẩn.
ARCHIVED    Ngừng sử dụng lâu dài nhưng giữ lại lịch sử.
```

---

# 4. Các bảng catalog

## 4.1. Bảng `vehicles`

### Mục đích

Registry chung cho mỗi phiên bản xe có thể tư vấn/bán. Bảng này chứa thông tin dùng chung và là đầu mối để join với `cars`, `motorbikes`, giá, feature và RAG.

Một phiên bản như `VF 6 Plus 2025` là một record riêng, không gộp vào `VF 6` nếu giá hoặc thông số khác nhau.

### Schema

```sql
CREATE TABLE vehicles (
    vehicle_id UUID PRIMARY KEY,
    vehicle_type VARCHAR(32) NOT NULL,
    brand VARCHAR(100) NOT NULL,
    model_name VARCHAR(150) NOT NULL,
    variant_name VARCHAR(150),
    model_year INTEGER,
    status VARCHAR(32) NOT NULL DEFAULT 'DRAFT',
    slug VARCHAR(220) NOT NULL,
    image_url TEXT,
    detail_url TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    created_by VARCHAR(64),
    updated_by VARCHAR(64),
    CONSTRAINT ck_vehicles_type CHECK (
        vehicle_type IN ('CAR', 'ELECTRIC_MOTORBIKE')
    ),
    CONSTRAINT ck_vehicles_status CHECK (
        status IN ('DRAFT', 'ACTIVE', 'INACTIVE', 'ARCHIVED')
    ),
    CONSTRAINT uq_vehicles_slug UNIQUE (slug),
    CONSTRAINT uq_vehicles_identity UNIQUE NULLS NOT DISTINCT (
        vehicle_type, brand, model_name, variant_name, model_year
    )
);

CREATE INDEX ix_vehicles_type_status
    ON vehicles (vehicle_type, status);
```

### Fields

| Field | Kiểu | Bắt buộc | Dùng để |
|---|---|---:|---|
| `vehicle_id` | UUID | Có | Khóa chính và ID dùng chung trong các bảng liên quan. Nên bất biến sau khi tạo. |
| `vehicle_type` | VARCHAR/enum | Có | Phân biệt `CAR` và `ELECTRIC_MOTORBIKE`, giúp chọn đúng bảng specs và tránh trộn loại xe. |
| `brand` | VARCHAR | Có | Tên hãng; hiện tại thường là `VinFast`. |
| `model_name` | VARCHAR | Có | Tên dòng xe, ví dụ `VF 6`, `VF 8`, `Evo200`. |
| `variant_name` | VARCHAR | Không | Phiên bản/trang bị, ví dụ `Eco`, `Plus`, `Lite`. |
| `model_year` | INTEGER | Không | Phân biệt các đời xe có cùng tên. |
| `status` | VARCHAR/enum | Có | Kiểm soát vòng đời. Chỉ `ACTIVE` được truy vấn production. |
| `slug` | VARCHAR | Có | Định danh ổn định cho URL hoặc lookup ngoài database. |
| `image_url` | TEXT | Không | Ảnh đại diện nếu MVP chỉ cần một ảnh. Nhiều ảnh có thể tách bảng sau. |
| `detail_url` | TEXT | Không | Link trang chi tiết sản phẩm. |
| `created_at` | TIMESTAMPTZ | Có | Thời điểm tạo record. |
| `updated_at` | TIMESTAMPTZ | Có | Thời điểm cập nhật gần nhất. |
| `created_by` | VARCHAR(64) | Không | ID người dùng ở module auth (`auth_users.id`), không phải UUID — tham chiếu mềm, không FK. |
| `updated_by` | VARCHAR(64) | Không | ID người dùng ở module auth, cùng quy ước với `created_by`. |

### Quan hệ

```text
vehicles.vehicle_id 1 ── 0..1 cars
vehicles.vehicle_id 1 ── 0..1 motorbikes
vehicles.vehicle_id 1 ── N vehicle_prices
vehicles.vehicle_id 1 ── N vehicle_feature_flags
feature_definitions.feature_code 1 ── N vehicle_feature_flags
vehicles.vehicle_id 1 ── N vehicle_documents

Một `vehicle` chỉ được có một bảng specs tương ứng:
- `vehicle_type = CAR` → có record trong `cars`.
- `vehicle_type = ELECTRIC_MOTORBIKE` → có record trong `motorbikes`.
```

Mỗi vehicle chỉ được có một bảng specs tương ứng với `vehicle_type`.

### Vì sao `uq_vehicles_identity` cần `NULLS NOT DISTINCT`

`variant_name` và `model_year` đều nullable. Theo hành vi mặc định của PostgreSQL, `NULL` không bằng `NULL` trong so sánh UNIQUE — nghĩa là hai xe cùng `vehicle_type`/`brand`/`model_name` mà cả hai đều để trống `variant_name` và `model_year` **không** vi phạm constraint mặc định, dù đó chính xác là bản ghi trùng cần chặn (ví dụ nhập tay hai lần một mẫu xe chưa phân biệt trim/năm). `NULLS NOT DISTINCT` (PostgreSQL 15+, dự án dùng pg16) coi `NULL` bằng `NULL` trong constraint này, đóng đúng lỗ hổng đó.

## 4.2. Bảng `cars`

### Mục đích

Lưu thông số có cấu trúc riêng của ô tô. Đây là nguồn chính cho SQL Hard Filter, bảng so sánh và các phép tính liên quan đến ô tô.

### Schema

```sql
CREATE TABLE cars (
    vehicle_id UUID PRIMARY KEY REFERENCES vehicles(vehicle_id) ON DELETE RESTRICT,
    body_type VARCHAR(50),
    seat_count INTEGER,
    range_km NUMERIC(10, 2),
    range_cycle VARCHAR(32),
    energy_consumption_kwh_per_100km NUMERIC(10, 3),
    battery_capacity_kwh NUMERIC(10, 3),
    motor_power_kw NUMERIC(10, 3),
    torque_nm NUMERIC(10, 3),
    max_speed_kmh NUMERIC(10, 2),
    acceleration_0_100_seconds NUMERIC(10, 2),
    curb_weight_kg NUMERIC(10, 2),
    gross_weight_kg NUMERIC(10, 2),
    fast_charge_power_kw NUMERIC(10, 3),
    fast_charge_time_minutes INTEGER,
    fast_charge_from_percent SMALLINT,
    fast_charge_to_percent SMALLINT,
    home_charge_time_minutes INTEGER,
    charging_port VARCHAR(50),
    cargo_volume_standard_l NUMERIC(10, 2),
    cargo_volume_maximum_l NUMERIC(10, 2),
    towing_supported BOOLEAN,
    towing_capacity_kg NUMERIC(10, 2),
    specs_version INTEGER NOT NULL DEFAULT 1,
    effective_from TIMESTAMPTZ,
    effective_to TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT ck_cars_seats CHECK (seat_count IS NULL OR seat_count > 0),
    CONSTRAINT ck_cars_range CHECK (range_km IS NULL OR range_km >= 0),
    CONSTRAINT ck_cars_charge_window CHECK (
        fast_charge_from_percent IS NULL
        OR fast_charge_to_percent IS NULL
        OR fast_charge_to_percent > fast_charge_from_percent
    )
);

CREATE INDEX ix_cars_filter_range_seats
    ON cars (range_km, seat_count);
```

### Fields

| Field | Kiểu | Bắt buộc | Dùng để |
|---|---|---:|---|
| `vehicle_id` | UUID | Có | PK và FK tới `vehicles`; xác định đây là specs của xe nào. |
| `body_type` | VARCHAR | Không | Kiểu thân xe như SUV, sedan, hatchback. Dùng để lọc hoặc hiển thị. |
| `seat_count` | INTEGER | Không | Số chỗ. Dùng hard filter `seat_count >= passenger_count`. |
| `range_km` | NUMERIC | Không | Tầm hoạt động theo km. Dùng hard filter và so sánh. |
| `range_cycle` | VARCHAR | Không | Chuẩn đo tầm hoạt động, ví dụ WLTP hoặc NEDC. |
| `energy_consumption_kwh_per_100km` | NUMERIC | Không | Mức tiêu thụ điện; input cho TCO. |
| `battery_capacity_kwh` | NUMERIC | Không | Dung lượng pin; dùng so sánh và TCO. |
| `motor_power_kw` | NUMERIC | Không | Công suất động cơ. |
| `torque_nm` | NUMERIC | Không | Mô-men xoắn. |
| `max_speed_kmh` | NUMERIC | Không | Tốc độ tối đa. |
| `acceleration_0_100_seconds` | NUMERIC | Không | Thời gian tăng tốc 0-100 km/h. |
| `curb_weight_kg` | NUMERIC | Không | Khối lượng xe không tải. |
| `gross_weight_kg` | NUMERIC | Không | Khối lượng toàn tải. |
| `fast_charge_power_kw` | NUMERIC | Không | Công suất sạc nhanh tối đa. |
| `fast_charge_time_minutes` | INTEGER | Không | Thời gian sạc nhanh theo khoảng phần trăm đã công bố. |
| `fast_charge_from_percent` | SMALLINT | Không | Mức pin bắt đầu khi đo sạc nhanh. |
| `fast_charge_to_percent` | SMALLINT | Không | Mức pin kết thúc khi đo sạc nhanh. |
| `home_charge_time_minutes` | INTEGER | Không | Thời gian sạc tại nhà. |
| `charging_port` | VARCHAR | Không | Chuẩn cổng sạc. |
| `cargo_volume_standard_l` | NUMERIC | Không | Dung tích khoang hành lý ở cấu hình thông thường. |
| `cargo_volume_maximum_l` | NUMERIC | Không | Dung tích tối đa khi gập ghế nếu có. |
| `towing_supported` | BOOLEAN | Không | Xe có hỗ trợ kéo tải hay không. |
| `towing_capacity_kg` | NUMERIC | Không | Khối lượng kéo tối đa. |
| `specs_version` | INTEGER | Có | Phiên bản bộ thông số, giúp proposal cũ truy vết đúng dữ liệu. |
| `effective_from`/`effective_to` | TIMESTAMPTZ | Không | Khoảng thời gian bộ specs có hiệu lực. |
| `created_at`/`updated_at` | TIMESTAMPTZ | Có | Audit thời điểm tạo/cập nhật. |

## 4.3. Bảng `motorbikes`

### Mục đích

Lưu thông số có cấu trúc riêng của xe máy điện. Đây là nguồn chính cho hard filter, so sánh và TCO của xe máy điện.

### Schema

```sql
CREATE TABLE motorbikes (
    vehicle_id UUID PRIMARY KEY REFERENCES vehicles(vehicle_id) ON DELETE RESTRICT,
    motor_power_w INTEGER,
    max_power_w INTEGER,
    torque_nm NUMERIC(10, 2),
    max_speed_kmh NUMERIC(10, 2),
    battery_type VARCHAR(50),
    battery_capacity_kwh NUMERIC(10, 3),
    battery_quantity SMALLINT,
    battery_removable BOOLEAN,
    battery_swappable BOOLEAN,
    energy_consumption_kwh_per_100km NUMERIC(10, 3),
    range_min_km NUMERIC(10, 2),
    range_max_km NUMERIC(10, 2),
    range_cycle VARCHAR(32),
    charging_time_minutes INTEGER,
    charging_method VARCHAR(50),
    curb_weight_kg NUMERIC(10, 2),
    max_load_kg NUMERIC(10, 2),
    seat_height_mm NUMERIC(10, 2),
    wheel_size_front_inch NUMERIC(5, 2),
    wheel_size_rear_inch NUMERIC(5, 2),
    license_requirement VARCHAR(32),
    specs_version INTEGER NOT NULL DEFAULT 1,
    effective_from TIMESTAMPTZ,
    effective_to TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT ck_motorbikes_range CHECK (
        range_min_km IS NULL OR range_max_km IS NULL OR range_max_km >= range_min_km
    ),
    CONSTRAINT ck_motorbikes_license CHECK (
        license_requirement IS NULL
        OR license_requirement IN ('NONE', 'A1', 'A', 'UNKNOWN')
    )
);

CREATE INDEX ix_motorbikes_filter_range_load
    ON motorbikes (range_max_km, max_load_kg);
```

### Fields

| Field | Kiểu | Bắt buộc | Dùng để |
|---|---|---:|---|
| `vehicle_id` | UUID | Có | PK và FK tới `vehicles`. |
| `motor_power_w` | INTEGER | Không | Công suất danh định của motor. |
| `max_power_w` | INTEGER | Không | Công suất cực đại. |
| `torque_nm` | NUMERIC | Không | Mô-men xoắn. |
| `max_speed_kmh` | NUMERIC | Không | Tốc độ tối đa. |
| `battery_type` | VARCHAR | Không | Loại pin, ví dụ lithium-ion. |
| `battery_capacity_kwh` | NUMERIC | Không | Tổng dung lượng pin. |
| `battery_quantity` | SMALLINT | Không | Số lượng pin. |
| `battery_removable` | BOOLEAN | Không | Pin có tháo rời để sạc hay không. |
| `battery_swappable` | BOOLEAN | Không | Có hỗ trợ đổi pin hay không. |
| `energy_consumption_kwh_per_100km` | NUMERIC | Không | Mức tiêu thụ điện; input bắt buộc cho TCO xe máy điện, đối xứng với `cars`. Xem quy tắc suy ra ở dưới. |
| `range_min_km` | NUMERIC | Không | Tầm hoạt động thấp nhất đã công bố/ước tính. |
| `range_max_km` | NUMERIC | Không | Tầm hoạt động tối đa; thường dùng để hard filter. |
| `range_cycle` | VARCHAR | Không | Chuẩn đo tầm hoạt động. |
| `charging_time_minutes` | INTEGER | Không | Thời gian sạc. |
| `charging_method` | VARCHAR | Không | Cách sạc: tại xe, tháo pin hoặc đổi pin. |
| `curb_weight_kg` | NUMERIC | Không | Khối lượng xe không tải. |
| `max_load_kg` | NUMERIC | Không | Tải trọng tối đa; dùng lọc nhu cầu chở người/hàng. |
| `seat_height_mm` | NUMERIC | Không | Chiều cao yên; dùng tư vấn độ phù hợp người lái. |
| `wheel_size_front_inch` | NUMERIC | Không | Kích thước bánh trước. |
| `wheel_size_rear_inch` | NUMERIC | Không | Kích thước bánh sau. |
| `license_requirement` | VARCHAR | Không | Yêu cầu bằng lái: `NONE`, `A1`, `A`, `UNKNOWN`. |
| `specs_version` | INTEGER | Có | Phiên bản thông số. |
| `effective_from`/`effective_to` | TIMESTAMPTZ | Không | Khoảng hiệu lực của specs. |
| `created_at`/`updated_at` | TIMESTAMPTZ | Có | Audit thời điểm tạo/cập nhật. |

### Quy tắc tiêu thụ điện cho TCO

TCO phải tính được cho cả hai loại phương tiện, nên `energy_consumption_kwh_per_100km` là input bắt buộc về mặt nghiệp vụ dù cột cho phép NULL. Thứ tự lấy giá trị:

1. Nếu Admin đã nhập `energy_consumption_kwh_per_100km`, dùng trực tiếp giá trị đó.
2. Nếu NULL nhưng có đủ `battery_capacity_kwh`, `battery_quantity` và `range_max_km > 0`, suy ra:
   `consumption = battery_capacity_kwh * COALESCE(battery_quantity, 1) / range_max_km * 100`.
   Kết quả này phải được đánh dấu là giá trị dẫn xuất (`derived`) trong assumption của TCO, không ghi đè vào cột specs.
3. Nếu cả hai đường trên đều không đủ dữ liệu, TCO trả `TCO_UNAVAILABLE` kèm tên field còn thiếu; Agent không được tự đoán.

Nhánh 2 tồn tại vì brochure xe máy điện thường công bố dung lượng pin và tầm hoạt động thay vì mức tiêu thụ. Nhánh này chỉ áp dụng cho `ELECTRIC_MOTORBIKE`; với `CAR` mức tiêu thụ phải do Admin nhập, không suy ra.

---

## 4.4. Bảng `vehicle_prices`

### Mục đích

Lưu giá structured để lọc ngân sách và tính toán. Giá không được lấy độc quyền từ RAG vì hệ thống cần so sánh số học và ngăn đề xuất vượt ngân sách.

### Schema

```sql
CREATE TABLE vehicle_prices (
    price_id UUID PRIMARY KEY,
    vehicle_id UUID NOT NULL REFERENCES vehicles(vehicle_id) ON DELETE RESTRICT,
    price_type VARCHAR(40) NOT NULL,
    amount_vnd BIGINT NOT NULL,
    currency CHAR(3) NOT NULL DEFAULT 'VND',
    region_code VARCHAR(16) NOT NULL DEFAULT 'VN',
    status VARCHAR(24) NOT NULL DEFAULT 'DRAFT',
    valid_from TIMESTAMPTZ NOT NULL,
    valid_to TIMESTAMPTZ,
    created_by VARCHAR(64),
    updated_by VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT ck_vehicle_prices_amount CHECK (amount_vnd >= 0),
    CONSTRAINT ck_vehicle_prices_currency CHECK (currency = 'VND'),
    CONSTRAINT ck_vehicle_prices_status CHECK (
        status IN ('DRAFT', 'ACTIVE', 'EXPIRED', 'CANCELLED')
    ),
    CONSTRAINT ck_vehicle_prices_period CHECK (
        valid_to IS NULL OR valid_to > valid_from
    )
);

CREATE INDEX ix_vehicle_prices_current_filter
    ON vehicle_prices (vehicle_id, price_type, status, valid_from, valid_to);

CREATE UNIQUE INDEX uq_vehicle_prices_one_active
    ON vehicle_prices (vehicle_id, price_type, region_code)
    WHERE status = 'ACTIVE';
```

Mục 5.2 quy tắc 4 nói "chỉ có một giá hiện hành cho cùng `(vehicle_id, price_type, region_code)`" nhưng trước đây chỉ là quy ước ở tầng application, không có gì ở DB chặn nếu code có bug ghi hai dòng `ACTIVE` cùng lúc. `uq_vehicle_prices_one_active` là **partial unique index** — chỉ áp dụng khi `status = 'ACTIVE'` — nên nhiều dòng `DRAFT`/`EXPIRED`/`CANCELLED` lịch sử vẫn được phép tồn tại bình thường, chỉ riêng trạng thái `ACTIVE` bị giới hạn còn đúng một dòng. Đây là cách đơn giản hơn EXCLUDE constraint kiểu GIST cho cùng mục tiêu: bài toán ở đây là "tối đa một dòng đang bật `ACTIVE`", không phải "không dòng nào chồng khoảng thời gian" — không cần `btree_gist` hay range type.

### Fields

| Field | Kiểu | Bắt buộc | Dùng để |
|---|---|---:|---|
| `price_id` | UUID | Có | Định danh một phiên bản giá. |
| `vehicle_id` | UUID | Có | Xe được áp dụng giá. |
| `price_type` | VARCHAR | Có | Phân biệt giá niêm yết, giá gồm pin hoặc phí thuê pin. |
| `amount_vnd` | BIGINT | Có | Số tiền VND nguyên, dùng hard filter/TCO. |
| `currency` | CHAR(3) | Có | Cờ an toàn, MVP chỉ cho `VND`. |
| `region_code` | VARCHAR | Có | Khu vực áp dụng, hiện tại `VN`. |
| `status` | VARCHAR | Có | Vòng đời bản ghi giá. |
| `valid_from`/`valid_to` | TIMESTAMPTZ | Có/Không | Khoảng thời gian giá có hiệu lực. |
| `created_by`/`updated_by` | VARCHAR(64) | Không | ID người dùng ở module auth (`auth_users.id`), không phải UUID. |
| `created_at`/`updated_at` | TIMESTAMPTZ | Có | Audit. |

`price_type` tối thiểu:

```text
STARTING_PRICE
BATTERY_INCLUDED_PRICE
BATTERY_SUBSCRIPTION_MONTHLY
```

## 4.5. Bảng `promotions`

### Mục đích

Lưu thông tin khuyến mại dạng structured khi promotion cần lọc theo thời hạn, khu vực hoặc xe áp dụng. Nội dung điều kiện dài vẫn có thể được giải thích bằng RAG.

### Schema

```sql
CREATE TABLE promotions (
    promotion_id UUID PRIMARY KEY,
    promotion_code VARCHAR(100) NOT NULL,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    promotion_type VARCHAR(40) NOT NULL,
    discount_amount_vnd BIGINT,
    discount_percent NUMERIC(5, 2),
    region_code VARCHAR(16) NOT NULL DEFAULT 'VN',
    eligibility_rules JSONB NOT NULL DEFAULT '{}'::jsonb,
    status VARCHAR(24) NOT NULL DEFAULT 'DRAFT',
    valid_from TIMESTAMPTZ NOT NULL,
    valid_to TIMESTAMPTZ,
    created_by VARCHAR(64),
    approved_by VARCHAR(64),
    approved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT uq_promotions_code UNIQUE (promotion_code),
    CONSTRAINT ck_promotions_type CHECK (
        promotion_type IN (
            'FIXED_DISCOUNT', 'PERCENT_DISCOUNT', 'GIFT',
            'FINANCING', 'REGISTRATION_SUPPORT', 'OTHER'
        )
    ),
    CONSTRAINT ck_promotions_status CHECK (
        status IN ('DRAFT', 'ACTIVE', 'EXPIRED', 'CANCELLED')
    ),
    CONSTRAINT ck_promotions_period CHECK (
        valid_to IS NULL OR valid_to > valid_from
    ),
    CONSTRAINT ck_promotions_discount CHECK (
        discount_amount_vnd IS NULL OR discount_amount_vnd >= 0
    )
);

CREATE INDEX ix_promotions_active_period
    ON promotions (status, region_code, valid_from, valid_to);
```

### Fields

| Field | Kiểu | Bắt buộc | Dùng để |
|---|---|---:|---|
| `promotion_id` | UUID | Có | Khóa chính. |
| `promotion_code` | VARCHAR | Có | Mã duy nhất để Admin và hệ thống tra cứu. |
| `title` | VARCHAR | Có | Tên hiển thị ngắn. |
| `description` | TEXT | Không | Mô tả tổng quan. |
| `promotion_type` | VARCHAR | Có | Loại ưu đãi. |
| `discount_amount_vnd` | BIGINT | Không | Số tiền giảm cố định nếu có. |
| `discount_percent` | NUMERIC | Không | Phần trăm giảm nếu có. |
| `region_code` | VARCHAR | Có | Khu vực áp dụng. |
| `eligibility_rules` | JSONB | Có | Điều kiện ít query, ví dụ phương thức thanh toán. |
| `status` | VARCHAR | Có | Trạng thái promotion. |
| `valid_from`/`valid_to` | TIMESTAMPTZ | Có/Không | Hiệu lực chương trình. |
| `created_by`/`approved_by` | VARCHAR(64) | Không | ID người dùng ở module auth, không phải UUID. Audit người tạo/người duyệt. |
| `approved_at` | TIMESTAMPTZ | Không | Thời điểm duyệt. |
| `created_at`/`updated_at` | TIMESTAMPTZ | Có | Audit. |

## 4.6. Bảng `promotion_vehicles`

### Mục đích

Bảng nối nhiều-nhiều giữa promotion và phương tiện. Một chương trình có thể áp dụng cho nhiều mẫu xe, một xe có thể có nhiều promotion theo thời gian.

### Schema

```sql
CREATE TABLE promotion_vehicles (
    promotion_id UUID NOT NULL
        REFERENCES promotions(promotion_id) ON DELETE CASCADE,
    vehicle_id UUID NOT NULL
        REFERENCES vehicles(vehicle_id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (promotion_id, vehicle_id)
);

CREATE INDEX ix_promotion_vehicles_vehicle
    ON promotion_vehicles (vehicle_id, promotion_id);
```

### Fields

| Field | Kiểu | Dùng để |
|---|---|---|
| `promotion_id` | UUID | Trỏ tới chương trình khuyến mại. |
| `vehicle_id` | UUID | Trỏ tới xe được áp dụng. |
| `created_at` | TIMESTAMPTZ | Ghi thời điểm liên kết được tạo. |

## 4.7. Bảng `battery_policies`

### Mục đích

Lưu các con số chính sách pin cần cho TCO hoặc lọc. Phần điều khoản diễn giải dài có thể đưa vào RAG, nhưng input số học không nên chỉ nằm trong văn bản.

### Schema

```sql
CREATE TABLE battery_policies (
    battery_policy_id UUID PRIMARY KEY,
    vehicle_id UUID NOT NULL REFERENCES vehicles(vehicle_id) ON DELETE RESTRICT,
    ownership_model VARCHAR(32) NOT NULL,
    monthly_fee_vnd BIGINT,
    purchase_price_vnd BIGINT,
    included_distance_km NUMERIC(10, 2),
    excess_fee_per_km_vnd BIGINT,
    deposit_amount_vnd BIGINT,
    warranty_months INTEGER,
    warranty_distance_km NUMERIC(10, 2),
    status VARCHAR(24) NOT NULL DEFAULT 'DRAFT',
    valid_from TIMESTAMPTZ NOT NULL,
    valid_to TIMESTAMPTZ,
    version INTEGER NOT NULL DEFAULT 1,
    created_by VARCHAR(64),
    updated_by VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT ck_battery_policies_model CHECK (
        ownership_model IN ('INCLUDED', 'PURCHASE', 'SUBSCRIPTION', 'SWAP', 'NOT_APPLICABLE')
    ),
    CONSTRAINT ck_battery_policies_status CHECK (
        status IN ('DRAFT', 'ACTIVE', 'EXPIRED', 'CANCELLED')
    ),
    CONSTRAINT ck_battery_policies_period CHECK (
        valid_to IS NULL OR valid_to > valid_from
    ),
    CONSTRAINT ck_battery_policies_amounts CHECK (
        (monthly_fee_vnd IS NULL OR monthly_fee_vnd >= 0)
        AND (purchase_price_vnd IS NULL OR purchase_price_vnd >= 0)
        AND (deposit_amount_vnd IS NULL OR deposit_amount_vnd >= 0)
        AND (excess_fee_per_km_vnd IS NULL OR excess_fee_per_km_vnd >= 0)
    )
);

CREATE INDEX ix_battery_policies_vehicle_period
    ON battery_policies (vehicle_id, status, valid_from, valid_to);
```

### Fields

| Field | Kiểu | Dùng để |
|---|---|---|
| `battery_policy_id` | UUID | Định danh chính sách pin. |
| `vehicle_id` | UUID | Xe áp dụng chính sách. |
| `ownership_model` | VARCHAR | Phân biệt pin đi kèm, mua, thuê hoặc đổi pin. |
| `monthly_fee_vnd` | BIGINT | Phí thuê pin tháng, dùng TCO. |
| `purchase_price_vnd` | BIGINT | Giá mua pin, dùng TCO. |
| `included_distance_km` | NUMERIC | Số km đã bao gồm trong phí thuê. |
| `excess_fee_per_km_vnd` | BIGINT | Phí mỗi km vượt mức. |
| `deposit_amount_vnd` | BIGINT | Tiền đặt cọc nếu có. |
| `warranty_months` | INTEGER | Thời hạn bảo hành dạng số. |
| `warranty_distance_km` | NUMERIC | Giới hạn km bảo hành. |
| `status` | VARCHAR | Trạng thái bản ghi policy. |
| `valid_from`/`valid_to` | TIMESTAMPTZ | Hiệu lực theo thời gian. |
| `version` | INTEGER | Phiên bản chính sách. |
| `created_by`/`updated_by` | VARCHAR(64) | ID người dùng ở module auth, không phải UUID. |
| `created_at`/`updated_at` | TIMESTAMPTZ | Audit. |

---

## 4.8. Bảng `feature_definitions`

### Mục đích

Danh mục trung tâm của các feature mà hệ thống hiểu được. Bảng này cho phép Admin thêm feature mới qua API mà không cần thêm column vào `cars` hoặc `motorbikes`.

`feature_definitions` mô tả feature là gì, áp dụng cho loại phương tiện nào, nhận kiểu giá trị nào và được dùng để loại xe, chấm điểm hay chỉ hiển thị.

### Schema

```sql
CREATE TABLE feature_definitions (
    feature_code VARCHAR(100) PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    description TEXT,
    vehicle_type VARCHAR(32),
    category VARCHAR(100) NOT NULL,
    value_type VARCHAR(32) NOT NULL DEFAULT 'BOOLEAN',
    unit VARCHAR(32),
    allowed_values JSONB,
    filter_behavior VARCHAR(32) NOT NULL DEFAULT 'PREFERENCE',
    status VARCHAR(24) NOT NULL DEFAULT 'ACTIVE',
    display_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    created_by VARCHAR(64),
    updated_by VARCHAR(64),
    CONSTRAINT ck_feature_definitions_vehicle_type CHECK (
        vehicle_type IS NULL
        OR vehicle_type IN ('CAR', 'ELECTRIC_MOTORBIKE')
    ),
    CONSTRAINT ck_feature_definitions_value_type CHECK (
        value_type IN ('BOOLEAN', 'NUMBER', 'TEXT', 'ENUM')
    ),
    CONSTRAINT ck_feature_definitions_filter_behavior CHECK (
        filter_behavior IN ('REQUIRED', 'PREFERENCE', 'INFORMATIONAL')
    ),
    CONSTRAINT ck_feature_definitions_status CHECK (
        status IN ('ACTIVE', 'ARCHIVED')
    ),
    CONSTRAINT ck_feature_definitions_display_order CHECK (display_order >= 0)
);

CREATE INDEX ix_feature_definitions_type_status
    ON feature_definitions (vehicle_type, status);

CREATE INDEX ix_feature_definitions_category_status
    ON feature_definitions (category, status);
```

### Fields

| Field | Kiểu | Bắt buộc | Dùng để |
|---|---|---:|---|
| `feature_code` | VARCHAR(100) | Có | Mã kỹ thuật duy nhất, dùng trong API, query và Agent. |
| `name` | VARCHAR(200) | Có | Tên hiển thị cho Admin và người dùng. |
| `description` | TEXT | Không | Giải thích ý nghĩa và phạm vi của feature. |
| `vehicle_type` | VARCHAR(32) | Không | `CAR`, `ELECTRIC_MOTORBIKE` hoặc null nếu dùng chung. |
| `category` | VARCHAR(100) | Có | Nhóm như `SAFETY`, `COMFORT`, `BATTERY`, `CONNECTIVITY`. |
| `value_type` | VARCHAR(32) | Có | `BOOLEAN`, `NUMBER`, `TEXT` hoặc `ENUM`. |
| `unit` | VARCHAR(32) | Không | Đơn vị cho feature dạng số. |
| `allowed_values` | JSONB | Không | Danh sách giá trị hợp lệ cho feature dạng `ENUM`. |
| `filter_behavior` | VARCHAR(32) | Có | `REQUIRED`, `PREFERENCE` hoặc `INFORMATIONAL`. |
| `status` | VARCHAR(24) | Có | `ACTIVE` hoặc `ARCHIVED`; feature archived không dùng cho request mới. |
| `display_order` | INTEGER | Có | Thứ tự hiển thị trên giao diện Admin. |
| `created_at`/`updated_at` | TIMESTAMPTZ | Có | Audit thời điểm tạo và cập nhật. |
| `created_by`/`updated_by` | VARCHAR(64) | Không | ID người dùng ở module auth. Admin tạo và cập nhật feature. |

### Ví dụ

```text
feature_code = BATTERY_REMOVABLE
vehicle_type = ELECTRIC_MOTORBIKE
category = BATTERY
value_type = BOOLEAN
filter_behavior = PREFERENCE
```

## 4.9. Bảng `vehicle_feature_flags`

**Endpoint:** `GET /api/v1/admin/feature-flags` (liệt kê, lọc theo `verification_status`/`vehicle_id`); `POST /api/v1/admin/feature-flags/{vehicle_id}/{feature_code}/review` (Admin duyệt — ghi `verification_status`).

### Mục đích

Bảng này phục vụ Lớp 2. Mỗi dòng thể hiện trạng thái và giá trị của một feature trên một xe. `feature_code` tham chiếu tới `feature_definitions`, nhờ đó Admin không thể gán feature chưa được định nghĩa.

### Schema

```sql
CREATE TABLE vehicle_feature_flags (
    vehicle_id UUID NOT NULL
        REFERENCES vehicles(vehicle_id) ON DELETE CASCADE,
    feature_code VARCHAR(100) NOT NULL
        REFERENCES feature_definitions(feature_code) ON DELETE RESTRICT,
    status VARCHAR(16) NOT NULL,
    value_text TEXT,
    value_number NUMERIC(14, 3),
    value_boolean BOOLEAN,
    verification_status VARCHAR(24) NOT NULL DEFAULT 'PENDING',
    confidence NUMERIC(4, 3),
    updated_by VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (vehicle_id, feature_code),
    CONSTRAINT ck_vehicle_features_status CHECK (
        status IN ('YES', 'NO', 'UNKNOWN')
    ),
    CONSTRAINT ck_vehicle_features_verification CHECK (
        verification_status IN ('PENDING', 'APPROVED', 'REJECTED')
    ),
    CONSTRAINT ck_vehicle_features_confidence CHECK (
        confidence IS NULL OR confidence BETWEEN 0 AND 1
    )
);

CREATE INDEX ix_vehicle_feature_flags_lookup
    ON vehicle_feature_flags (feature_code, status, vehicle_id);
```

### Fields

| Field | Kiểu | Dùng để |
|---|---|---|
| `vehicle_id` | UUID | Xe có feature. |
| `feature_code` | VARCHAR | Mã feature ổn định, ví dụ `ADAS_LEVEL_2`, `BATTERY_REMOVABLE`. |
| `status` | VARCHAR | `YES`, `NO` hoặc `UNKNOWN`. Không được coi `UNKNOWN` là `NO`. |
| `value_text` | TEXT | Giá trị mô tả nếu feature không chỉ là cờ có/không. |
| `value_number` | NUMERIC | Giá trị số của feature nếu cần. |
| `value_boolean` | BOOLEAN | Giá trị boolean khi cần phân biệt rõ. |
| `verification_status` | VARCHAR | Kiểm soát dữ liệu đã được Admin duyệt hay chưa. Xem quy tắc bên dưới. |
| `confidence` | NUMERIC | Độ tin cậy từ 0 đến 1 nếu flag được trích xuất tự động. |
| `updated_by` | VARCHAR(64) | ID người dùng ở module auth, không phải UUID. Admin cập nhật. |
| `created_at`/`updated_at` | TIMESTAMPTZ | Audit. |

### Quy tắc `verification_status` (bắt buộc, tránh Lớp 2 rỗng)

Query Lớp 2 ở mục 7.2 lọc `verification_status = 'APPROVED'`, nên nếu mọi dòng đều nằm ở `PENDING` thì Lớp 2 luôn trả rỗng và Agent mất hẳn một tầng. Quy tắc chốt:

- Flag do **Admin nhập/sửa qua API catalog** được ghi thẳng `verification_status = 'APPROVED'`, vì hành vi của một tài khoản ADMIN chính là sự duyệt. Áp dụng cho cả ba `status` `YES`/`NO`/`UNKNOWN`.
- `PENDING` chỉ dành cho flag do pipeline tự động trích xuất từ brochure (có `confidence`), và **không** tham gia truy vấn tư vấn khách hàng cho tới khi Admin duyệt.
- `DEFAULT 'PENDING'` ở tầng database được giữ nguyên làm lưới an toàn cho đường nạp dữ liệu tự động; tầng application chịu trách nhiệm set `APPROVED` cho đường Admin.
- `REJECTED` không bao giờ tham gia truy vấn.

Hệ quả cho luồng Admin ở mục 6.1/6.2: các flag seed lúc tạo xe mang `status = 'UNKNOWN'` **và** `verification_status = 'APPROVED'` — nghĩa là "đã duyệt rằng hệ thống chưa xác định được tính năng này", đúng ngữ nghĩa ba trạng thái mà PRD yêu cầu.

Trong MVP có thể bỏ qua các cột giá trị mở (`value_text`, `value_number`, `value_boolean`) nếu toàn bộ feature ban đầu là boolean. Khi cần feature dạng số, text hoặc enum thì sử dụng các cột tương ứng và validate theo `feature_definitions.value_type` ở application service.

Danh sách feature ban đầu có thể seed vào `feature_definitions`; không cần sửa schema `cars` hoặc `motorbikes` khi thêm feature mới.

## 4.10. Bảng `vehicle_documents`

### Mục đích

Lưu các đoạn nội dung đã chuẩn bị cho RAG và gắn với `vehicle_id`. Bảng này dùng để tìm kiếm ngữ nghĩa và giải thích chính sách, không dùng để hard filter hoặc thay thế giá structured.

Tên `vehicle_documents` ở đây chỉ có nghĩa là corpus RAG gắn với xe. File gốc và metadata lưu trữ vật lý được quản lý bởi Document Module hiện có. **Trong thi công, bảng này do module `document` sở hữu** (`src/document/infrastructure/models.py`, migration `d0cument0002`), không phải module `products`/catalog; nó tham chiếu `vehicles.vehicle_id` qua FK liên module. Mười một bảng còn lại ở mục 4 do module `products` sở hữu (migration `d4e5f6a7b8c9`).

### Schema

```sql
CREATE TABLE vehicle_documents (
    document_id UUID PRIMARY KEY,
    vehicle_id UUID REFERENCES vehicles(vehicle_id) ON DELETE CASCADE,
    source_document_id UUID REFERENCES documents(id) ON DELETE SET NULL,
    source_content_hash VARCHAR(128),
    source_revision VARCHAR(40),
    document_type VARCHAR(40) NOT NULL,
    title VARCHAR(255) NOT NULL,
    content TEXT NOT NULL,
    chunk_index INTEGER NOT NULL DEFAULT 0,
    section_title VARCHAR(255),
    page_number INTEGER,
    source_url TEXT,
    embedding_model VARCHAR(100),
    embedding_version VARCHAR(40),
    embedding vector(1024),
    content_tsv tsvector GENERATED ALWAYS AS (
        to_tsvector('simple', coalesce(section_title, '') || ' ' || content)
    ) STORED,
    status VARCHAR(24) NOT NULL DEFAULT 'DRAFT',
    valid_from TIMESTAMPTZ,
    valid_to TIMESTAMPTZ,
    created_by VARCHAR(64),
    approved_by VARCHAR(64),
    approved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT ck_vehicle_documents_status CHECK (
        status IN ('DRAFT', 'ACTIVE', 'EXPIRED', 'ARCHIVED')
    ),
    CONSTRAINT ck_vehicle_documents_period CHECK (
        valid_to IS NULL OR valid_from IS NULL OR valid_to > valid_from
    ),
    CONSTRAINT ck_vehicle_documents_content CHECK (length(trim(content)) > 0),
    CONSTRAINT ck_vehicle_documents_approval CHECK (
        status <> 'ACTIVE'
        OR (approved_by IS NOT NULL AND approved_at IS NOT NULL)
    )
);

CREATE INDEX ix_vehicle_documents_scope
    ON vehicle_documents (vehicle_id, status, document_type, valid_from, valid_to);

CREATE INDEX ix_vehicle_documents_source_document
    ON vehicle_documents (source_document_id);

CREATE INDEX ix_vehicle_documents_content_tsv
    ON vehicle_documents USING gin (content_tsv);

-- Chỉ tạo sau khi đã chốt model và số chiều embedding.
CREATE INDEX ix_vehicle_documents_embedding_hnsw
    ON vehicle_documents USING hnsw (embedding vector_cosine_ops);
```

### Vì sao `content_tsv` thuộc bảng `vehicle_documents` (module document), không thuộc module agent

Lớp 3 dùng hybrid search: vector cho câu hỏi diễn giải, full-text cho từ khoá chính xác (tên chính sách, mã điều khoản), hợp nhất bằng RRF. Cả hai đều là **cách đọc** corpus này, nên cột phục vụ chúng thuộc về bảng.

Nếu để module agent tự `ALTER TABLE` thêm cột vào bảng `vehicle_documents` (do module `document` sở hữu) thì vi phạm ranh giới sở hữu: module chủ bảng không biết cột đó tồn tại và có thể drop nó ở một migration sau, còn agent thì không thể tự khôi phục. Cột được khai báo ở đây (migration `d0cument0002`), migration của agent chỉ tạo `CREATE EXTENSION vector`.

Dùng `'simple'` thay vì `'english'` vì corpus là tiếng Việt: bộ stemmer tiếng Anh sẽ cắt sai gốc từ, còn `'simple'` chỉ hạ chữ thường và tách token — đủ cho việc khớp từ khoá và không làm hỏng dấu.

### Vì sao có `ck_vehicle_documents_approval`

Bảng đã có `approved_by`/`approved_at` nhưng trước đây không có gì bắt buộc chúng, nên một đoạn nội dung chưa ai duyệt vẫn có thể mang `status = 'ACTIVE'` và đi thẳng vào câu trả lời cho khách. CHECK này biến quy tắc duyệt từ thoả thuận bằng lời thành ràng buộc database, cùng tinh thần với quy tắc `verification_status` ở mục 4.9.

### Vì sao có `source_document_id`/`source_content_hash`/`source_revision`

Trước bản vá này, `vehicle_documents` không có cách nào trỏ ngược về file gốc trong `documents` (module document, cùng chỗ chứa file người dùng tải lên/Admin nạp). Khi khách hỏi "thông tin này lấy từ đâu", Agent chỉ trả lời được bằng `title`/`section_title`/`page_number` — đủ để hiển thị citation, nhưng không đủ để tư vấn viên hoặc kiểm toán mở lại đúng file PDF/DOCX gốc đã sinh ra đoạn này.

- **`source_document_id`** — FK sang `documents.id`, nullable vì một chunk có thể do Admin gõ tay (không xuất phát từ file tải lên). `ON DELETE SET NULL`: xoá file gốc không được kéo theo xoá nội dung RAG đã duyệt và đang dùng để trả lời khách; chỉ mất khả năng trỏ ngược, nội dung vẫn còn.
- **`source_content_hash`** — sao chép `documents.content_hash` tại thời điểm tạo chunk. Dùng để phát hiện **trôi dữ liệu**: nếu `documents.content_hash` hiện tại khác giá trị đã lưu ở đây, nghĩa là file gốc đã được thay bằng bản khác sau khi chunk này được duyệt — dấu hiệu cần Admin xem lại, không tự động vô hiệu hoá chunk.
- **`source_revision`** — nhãn phiên bản tự do do Admin đặt (ví dụ `"brochure VF8 2026-08"`), dùng khi nhiều lần nạp cùng một tài liệu logic nhưng khác file vật lý, và `content_hash` một mình không đủ ngữ cảnh cho người đọc.

Ba cột này **không tham gia Lớp 3** (không lọc, không xếp hạng) — chỉ phục vụ truy vết và kiểm toán. Chunk không có `source_document_id` vẫn hợp lệ và vẫn được retrieval bình thường.

> `vector(1024)` chỉ là ví dụ. Số chiều phải khớp embedding model thực tế. Nếu chưa chốt model, trì hoãn migration vector index hoặc dùng kiểu/schema phù hợp với quyết định cuối cùng.

### Fields

| Field | Kiểu | Dùng để |
|---|---|---|
| `document_id` | UUID | Định danh đoạn RAG. |
| `vehicle_id` | UUID nullable | Giới hạn kết quả theo xe. Null dùng cho policy chung áp dụng nhiều xe. |
| `source_document_id` | UUID nullable | FK → `documents.id`. Trỏ ngược về file gốc để citation truy vết được; null nếu chunk do Admin gõ tay. |
| `source_content_hash` | VARCHAR(128) nullable | Bản sao `documents.content_hash` tại thời điểm tạo chunk, dùng phát hiện file gốc đã đổi. |
| `source_revision` | VARCHAR(40) nullable | Nhãn phiên bản tự do do Admin đặt, dùng khi tài liệu logic được nạp lại nhiều lần. |
| `document_type` | VARCHAR | Phân loại nội dung như `WARRANTY_POLICY`, `BATTERY_POLICY`, `PROMOTION_POLICY`. |
| `title` | VARCHAR | Tiêu đề hiển thị/citation. |
| `content` | TEXT | Nội dung đưa vào semantic search và context LLM. |
| `chunk_index` | INTEGER | Thứ tự chunk trong cùng tài liệu. |
| `section_title` | VARCHAR | Giữ ngữ cảnh section, ví dụ “Điều kiện bảo hành pin”. |
| `page_number` | INTEGER | Citation về trang nguồn nếu có. |
| `source_url` | TEXT | Link để kiểm chứng. |
| `embedding_model` | VARCHAR | Model đã tạo vector. |
| `embedding_version` | VARCHAR | Version pipeline embedding. |
| `embedding` | VECTOR | Vector dùng pgvector. |
| `content_tsv` | TSVECTOR generated | Nhánh full-text của hybrid search Lớp 3. Sinh tự động từ `section_title` + `content`, không ghi tay. |
| `status` | VARCHAR | Chỉ `ACTIVE` mới được retrieval production. |
| `valid_from`/`valid_to` | TIMESTAMPTZ | Lọc đúng policy đang hiệu lực. |
| `created_by` | VARCHAR(64) | ID người dùng ở module auth, không phải UUID. Người tạo/import. |
| `approved_by`/`approved_at` | VARCHAR(64)/TIMESTAMPTZ | Duyệt nội dung trước khi dùng. Bắt buộc khi `status = 'ACTIVE'` theo `ck_vehicle_documents_approval`. |
| `created_at`/`updated_at` | TIMESTAMPTZ | Audit. |

### Nội dung nào nên đưa vào RAG?

- Điều kiện và ngoại lệ bảo hành.
- Quy trình thuê, mua hoặc đổi pin.
- Diễn giải chương trình khuyến mại.
- Hướng dẫn sạc.
- Mô tả tính năng bằng ngôn ngữ tự nhiên.
- Điều khoản dài khó biểu diễn thành field.

### Nội dung nào không được chỉ để trong RAG?

- Giá dùng để lọc ngân sách.
- Số ghế.
- Tầm hoạt động dùng hard filter.
- Tải trọng.
- Tốc độ tối đa nếu dùng để lọc.
- Phí thuê pin dùng trong công thức TCO.
- Khoảng thời gian hiệu lực cần kiểm tra bằng SQL.

---

## 4.11. Bảng `tco_assumptions`

### Mục đích

Lưu các giả định dùng để tính tổng chi phí sở hữu: giá điện, phí lăn bánh, chi phí bảo dưỡng. PRD yêu cầu TCO gồm cả phí lăn bánh và bảo dưỡng, và cấu hình phải tách riêng theo loại phương tiện vì chu kỳ bảo dưỡng cùng mức tiêu thụ của ô tô và xe máy điện khác nhau đáng kể.

Bảng này do Admin quản lý. Agent không được tự đoán bất kỳ con số nào ở đây; thiếu bộ giả định hiệu lực thì TCO trả `TCO_UNAVAILABLE`.

### Schema

```sql
CREATE TABLE tco_assumptions (
    assumption_id UUID PRIMARY KEY,
    vehicle_type VARCHAR(32) NOT NULL,
    region_code VARCHAR(16) NOT NULL DEFAULT 'VN',
    assumption_version INTEGER NOT NULL DEFAULT 1,
    electricity_vnd_per_kwh BIGINT NOT NULL,
    registration_fee_percent NUMERIC(5, 2),
    registration_fee_flat_vnd BIGINT,
    plate_fee_vnd BIGINT,
    inspection_fee_vnd BIGINT,
    mandatory_insurance_vnd_per_year BIGINT,
    road_fee_vnd_per_year BIGINT,
    maintenance_vnd_per_service BIGINT,
    maintenance_interval_km NUMERIC(10, 2),
    horizon_months INTEGER NOT NULL DEFAULT 60,
    source_note TEXT,
    status VARCHAR(24) NOT NULL DEFAULT 'DRAFT',
    valid_from TIMESTAMPTZ NOT NULL,
    valid_to TIMESTAMPTZ,
    created_by VARCHAR(64),
    updated_by VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT ck_tco_assumptions_vehicle_type CHECK (
        vehicle_type IN ('CAR', 'ELECTRIC_MOTORBIKE')
    ),
    CONSTRAINT ck_tco_assumptions_status CHECK (
        status IN ('DRAFT', 'ACTIVE', 'EXPIRED', 'CANCELLED')
    ),
    CONSTRAINT ck_tco_assumptions_period CHECK (
        valid_to IS NULL OR valid_to > valid_from
    ),
    CONSTRAINT ck_tco_assumptions_horizon CHECK (horizon_months > 0),
    CONSTRAINT ck_tco_assumptions_amounts CHECK (
        electricity_vnd_per_kwh >= 0
        AND (registration_fee_flat_vnd IS NULL OR registration_fee_flat_vnd >= 0)
        AND (plate_fee_vnd IS NULL OR plate_fee_vnd >= 0)
        AND (inspection_fee_vnd IS NULL OR inspection_fee_vnd >= 0)
        AND (mandatory_insurance_vnd_per_year IS NULL OR mandatory_insurance_vnd_per_year >= 0)
        AND (road_fee_vnd_per_year IS NULL OR road_fee_vnd_per_year >= 0)
        AND (maintenance_vnd_per_service IS NULL OR maintenance_vnd_per_service >= 0)
        AND (maintenance_interval_km IS NULL OR maintenance_interval_km > 0)
    ),
    CONSTRAINT uq_tco_assumptions_version UNIQUE (
        vehicle_type, region_code, assumption_version
    )
);

CREATE INDEX ix_tco_assumptions_lookup
    ON tco_assumptions (vehicle_type, region_code, status, valid_from, valid_to);
```

### Fields

| Field | Kiểu | Bắt buộc | Dùng để |
|---|---|---:|---|
| `assumption_id` | UUID | Có | Định danh bộ giả định; được TCO lưu lại để truy vết. |
| `vehicle_type` | VARCHAR | Có | `CAR` hoặc `ELECTRIC_MOTORBIKE`; mỗi loại có bộ giả định riêng. |
| `region_code` | VARCHAR | Có | Khu vực áp dụng, hiện tại `VN`. |
| `assumption_version` | INTEGER | Có | Phiên bản bộ giả định; kết quả TCO cũ truy vết đúng phiên bản đã dùng. |
| `electricity_vnd_per_kwh` | BIGINT | Có | Giá điện dùng tính chi phí sạc. |
| `registration_fee_percent` | NUMERIC | Không | Lệ phí trước bạ theo phần trăm giá xe. |
| `registration_fee_flat_vnd` | BIGINT | Không | Lệ phí trước bạ dạng số tiền cố định nếu áp dụng. |
| `plate_fee_vnd` | BIGINT | Không | Phí biển số. |
| `inspection_fee_vnd` | BIGINT | Không | Phí đăng kiểm; thường chỉ áp dụng ô tô. |
| `mandatory_insurance_vnd_per_year` | BIGINT | Không | Bảo hiểm bắt buộc mỗi năm. |
| `road_fee_vnd_per_year` | BIGINT | Không | Phí đường bộ mỗi năm. |
| `maintenance_vnd_per_service` | BIGINT | Không | Chi phí một lần bảo dưỡng. |
| `maintenance_interval_km` | NUMERIC | Không | Chu kỳ bảo dưỡng theo km. |
| `horizon_months` | INTEGER | Có | Kỳ tính TCO, mặc định 60 tháng. |
| `source_note` | TEXT | Không | Nguồn của các con số, phục vụ hiển thị giả định cho khách. |
| `status` | VARCHAR | Có | Chỉ `ACTIVE` được dùng để tính. |
| `valid_from`/`valid_to` | TIMESTAMPTZ | Có/Không | Khoảng hiệu lực. |
| `created_by`/`updated_by` | VARCHAR(64) | Không | ID người dùng ở module auth (`auth_users.id`), không phải UUID. |
| `created_at`/`updated_at` | TIMESTAMPTZ | Có | Audit. |

Phí lăn bánh được cộng từ các thành phần áp dụng được cho loại phương tiện đó: trước bạ
(phần trăm giá cộng khoản cố định nếu dữ liệu quy định cả hai), biển số, đăng kiểm theo số mốc,
bảo hiểm bắt buộc và phí đường bộ. Thành phần chưa đủ dữ liệu phải được ghi rõ là chưa mô hình
hóa; không được biến `0` thành tuyên bố miễn trừ pháp lý hay thay bằng số phỏng đoán.

Chỉ được tồn tại một bộ giả định `ACTIVE` cho cùng `(vehicle_type, region_code)` tại một thời điểm.

### Quy tắc bắt buộc để TCO deterministic (cùng input → cùng output, mọi lần chạy)

Hai chỗ trước đây chưa chốt, có thể làm hai lần chạy cùng input ra hai kết quả khác nhau nếu người viết code tự suy diễn:

**1. Quy đổi km/ngày sang km/tháng.** Slot khách khai là "quãng đường/ngày" (mục 7.0), nhưng `energy_vnd` cần tính theo tháng để nhân với `horizon_months`. Quy đổi cố định, không cấu hình được:

```text
monthly_distance_km = daily_distance_km × 30
```

Hằng số `30` (ngày/tháng) là **hằng số miền nghiệp vụ**, khai báo một chỗ trong code domain TCO (`DAYS_PER_MONTH = 30`), không phải input Admin và không được suy ra từ số ngày thật của từng tháng — mục tiêu là một công thức tái lập được, không phải lịch chính xác.

**2. `STARTING_PRICE` và `BATTERY_INCLUDED_PRICE` không bao giờ cộng cùng nhau.** TCO cho
catalog xe bán mới dùng một giá ổn định, không dùng promotion và không cộng chính sách thuê/mua
pin lịch sử. Thứ tự chọn giá bắt buộc:

```text
1. Dùng giá ACTIVE `BATTERY_INCLUDED`/`BATTERY_INCLUDED_PRICE` nếu có.
2. Nếu không có, dùng giá ACTIVE `STARTING_PRICE`.
3. Không chọn `PROMOTION_PRICE` hoặc `BATTERY_SUBSCRIPTION`.
4. `battery_vnd = 0`; dữ liệu `battery_policies` lịch sử không đóng góp vào estimate xe bán mới.
5. Không có giá ACTIVE áp dụng được → `TCO_UNAVAILABLE`, không suy đoán giá.
```

Quy tắc chịu lực: **chỉ một giá catalog đóng góp vào `total_vnd`; promotion và policy pin lịch
sử không đóng góp**. `src/products/domain/tco.py` là calculator chuẩn duy nhất; adapter Agent
không được triển khai lại công thức.

---

## 4.12. Bảng `feature_need_tags`

### Mục đích

Trả lời câu hỏi mà `feature_definitions` không trả lời được: **nhu cầu đã xác nhận của khách thì nên nói tới feature nào.**

`feature_definitions.category` mô tả **bản chất** của feature (`SAFETY`, `COMFORT`, `BATTERY`, `CONNECTIVITY`), không mô tả **nhu cầu mà nó giải quyết**. Biết `ADAS_LEVEL_2` thuộc `SAFETY` không cho biết nó đáng nói với ai; khách đi đường dài trên cao tốc cần nó, khách chỉ đi trong phố thì không. Bảng này là chỗ chứa ánh xạ đó.

Đây là bảng làm cho Agent **giới thiệu theo nhu cầu thay vì chào hàng**. Không có nó, Agent chỉ có hai lựa chọn: hoặc im lặng về mọi feature khách không hỏi, hoặc để LLM tự chọn feature nào nghe hay — tức là chào hàng.

### Vì sao gắn tag vào `feature_code`, không gắn vào `(vehicle_id, feature_code)`

Đây là quyết định chịu lực của bảng. `ADAS_LEVEL_2` phục vụ nhu cầu an toàn đường dài **ở mọi xe có nó** — không có xe nào mà ADAS lại phục vụ nhu cầu khác. Nhu cầu mà một feature giải quyết là thuộc tính của **feature**, còn xe nào có feature đó thì `vehicle_feature_flags` đã trả lời.

Hệ quả về chi phí nhập liệu: gắn vào `feature_code` thì khối lượng bằng **số feature**, tức phép cộng — 12 feature seed × 1–3 tag ≈ 25–30 dòng, nhập một lần. Gắn vào `(xe × feature)` thì khối lượng là **phép nhân** — thêm một xe là nhập lại toàn bộ tag cho xe đó. Xe mới thêm sau này tự động thừa hưởng tag qua `feature_code`, không ai phải nhập thêm dòng nào.

### Schema

```sql
CREATE TABLE feature_need_tags (
    feature_code VARCHAR(100) NOT NULL
        REFERENCES feature_definitions(feature_code) ON DELETE CASCADE,
    need_tag VARCHAR(40) NOT NULL,
    relevance NUMERIC(3,2) NOT NULL DEFAULT 1.00,
    note TEXT,
    created_by VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (feature_code, need_tag),
    CONSTRAINT ck_feature_need_tags_tag_format CHECK (
        need_tag = upper(need_tag) AND need_tag ~ '^[A-Z][A-Z0-9_]*$'
    ),
    CONSTRAINT ck_feature_need_tags_relevance CHECK (
        relevance > 0 AND relevance <= 1
    )
);

CREATE INDEX ix_feature_need_tags_need_tag
    ON feature_need_tags (need_tag, relevance DESC);
```

Khoá chính là `(feature_code, need_tag)`: một feature phục vụ nhiều nhu cầu, một nhu cầu được nhiều feature phục vụ, nhưng một cặp chỉ khai báo một lần. Index theo `need_tag` vì hướng truy vấn ở runtime luôn là *nhu cầu → feature*, không bao giờ ngược lại.

### Fields

| Field | Kiểu | Bắt buộc | Dùng để |
|---|---|---|---|
| `feature_code` | VARCHAR | Có | FK tới `feature_definitions`. Feature bị xoá thì tag đi theo. |
| `need_tag` | VARCHAR | Có | Mã nhu cầu, uppercase snake case. Tập giá trị ở mục 7.4. |
| `relevance` | NUMERIC(3,2) | Có | Mức liên quan trong `(0, 1]`. Dùng để xếp thứ tự khi một nhu cầu có nhiều feature, chọn cái đáng nói nhất trước. |
| `note` | TEXT | Không | Ghi chú cho Admin về lý do gắn tag, không đưa vào câu trả lời khách. |
| `created_by` | VARCHAR(64) | Không | ID người dùng ở module auth, không phải UUID. Admin khai báo. |
| `created_at`/`updated_at` | TIMESTAMPTZ | Có | Audit. |

### Ví dụ seed

```text
ADAS_LEVEL_2        LONG_DISTANCE       0.90
ADAS_LEVEL_2        HIGHWAY_SAFETY      1.00
CAMERA_360          URBAN_TRAFFIC       0.90
CAMERA_360          FAMILY_LARGE        0.60
PANORAMIC_ROOF      FAMILY_LARGE        0.70
POWER_ADJUST_SEAT   LONG_DISTANCE       0.60
BATTERY_REMOVABLE   NO_HOME_CHARGING    1.00
BATTERY_SWAPPABLE   NO_HOME_CHARGING    0.90
BATTERY_SWAPPABLE   DELIVERY_USE        1.00
ANTI_THEFT_ALARM    DELIVERY_USE        0.70
```

`relevance` không phải độ quan trọng của feature nói chung, mà là **mức liên quan tới nhu cầu cụ thể đó**. `CAMERA_360` liên quan mạnh tới lái trong phố (`0.90`) và yếu hơn tới gia đình đông người (`0.60`); cùng một feature, hai con số khác nhau vì hai nhu cầu khác nhau.

### Feature không có tag

Được phép, và là trạng thái mặc định của feature mới. Feature không có tag nào thì **không bao giờ được Agent chủ động giới thiệu** — nó vẫn tham gia Lớp 2 bình thường khi khách hỏi trực tiếp.

Đây là hành vi cố ý, không phải thiếu sót: thiếu tag làm hệ thống **im lặng**, không làm nó **sai**. Đổi lại, khi thiếu dữ liệu thì mất một câu nói thêm, còn Lớp 1, Lớp 2, lý do đề xuất và TCO đều không bị ảnh hưởng.

---

# 5. Quan hệ và quy tắc toàn vẹn

## 5.1. Quan hệ chính

```text
vehicles (1) ─── (0..1) cars
vehicles (1) ─── (0..1) motorbikes
vehicles (1) ─── (N) vehicle_prices
vehicles (1) ─── (N) battery_policies
vehicles (1) ─── (N) vehicle_feature_flags
feature_definitions (1) ─── (N) vehicle_feature_flags
feature_definitions (1) ─── (N) feature_need_tags
vehicles (1) ─── (N) vehicle_documents
promotions (1) ─── (N) promotion_vehicles (N) ─── (1) vehicles
tco_assumptions không tham chiếu vehicle_id; khớp theo (vehicle_type, region_code)
```

## 5.2. Quy tắc ứng dụng bắt buộc

Database đảm bảo FK, còn application service phải đảm bảo:

1. `CAR` chỉ được tạo record ở `cars`.
2. `ELECTRIC_MOTORBIKE` chỉ được tạo record ở `motorbikes`.
3. Xe `ACTIVE` phải có specs tương ứng trước khi publish.
4. Chỉ có một giá hiện hành cho cùng `(vehicle_id, price_type, region_code)` tại một thời điểm.
5. Một promotion chỉ áp dụng cho xe `ACTIVE` hoặc xe đang được chuẩn bị publish.
6. Không hard delete xe đã có lịch sử tư vấn.
7. Policy và RAG có `valid_from`/`valid_to` phải được lọc theo thời điểm query.
8. Giá và input TCO phải lấy từ structured data, không parse trực tiếp từ RAG.
9. Flag do Admin nhập qua API mang `verification_status = 'APPROVED'`; chỉ flag từ pipeline tự động mới ở `PENDING` và không tham gia truy vấn tư vấn (mục 4.9).
10. Chỉ có một bộ `tco_assumptions` `ACTIVE` cho cùng `(vehicle_type, region_code)` tại một thời điểm.
11. Mỗi xe `ACTIVE` phải tra được mức tiêu thụ điện theo mục 4.3 trước khi được đưa vào kết quả có kèm TCO.
12. Đoạn RAG chỉ được chuyển sang `ACTIVE` khi đã có `approved_by` và `approved_at` (mục 4.10). Nội dung chưa duyệt không được đi vào câu trả lời cho khách.
13. Feature chỉ được **chủ động giới thiệu** khi có ít nhất một `need_tag` khớp nhu cầu đã xác nhận của khách (mục 7.4). Không có tag khớp thì không giới thiệu; tuyệt đối không thay bằng lời khen chung chung.
14. Mọi con số xuất hiện trong câu trả lời phải đến từ allowlist ở mục 7.5 và được render bởi code, không do LLM tự viết ra.

Nếu dùng PostgreSQL, có thể bổ sung exclusion constraint hoặc transaction locking để ngăn hai khoảng thời gian giá active bị chồng lấn.

---

# 6. Luồng Admin CRUD

## 6.1. Tạo ô tô

```text
Admin submit form
  -> validate vehicle_type = CAR
  -> INSERT vehicles(status = DRAFT)
  -> INSERT cars(vehicle_id, specs)
  -> INSERT vehicle_prices nếu có
  -> INSERT feature flags cần thiết với status = UNKNOWN,
     verification_status = APPROVED (mục 4.9)
  -> commit transaction
  -> Admin review và chuyển ACTIVE
```

## 6.2. Tạo xe máy điện

```text
Admin submit form
  -> validate vehicle_type = ELECTRIC_MOTORBIKE
  -> INSERT vehicles(status = DRAFT)
  -> INSERT motorbikes(vehicle_id, specs)
  -> INSERT vehicle_prices nếu có
  -> INSERT feature flags cần thiết với status = UNKNOWN,
     verification_status = APPROVED (mục 4.9)
  -> commit transaction
  -> Admin review và chuyển ACTIVE
```

## 6.3. Cập nhật giá

**Endpoint:** `PUT /api/v1/admin/vehicles/{vehicle_id}/prices`

Không overwrite lịch sử giá đã dùng:

```text
old_price.valid_to = thời điểm bắt đầu giá mới
new_price.status = ACTIVE
new_price.valid_from = thời điểm bắt đầu giá mới
```

## 6.4. Cập nhật specs

**Endpoint:** `PATCH /api/v1/admin/vehicles/{vehicle_id}`

MVP có thể update trực tiếp record specs và tăng `specs_version`. Khi cần lịch sử đầy đủ, chuyển sang bảng version riêng mà không phải thay đổi `vehicles` hoặc các bảng phụ.

## 6.5. Archive

**Endpoint:** `DELETE /api/v1/admin/vehicles/{vehicle_id}` (archive mềm); Restore: `POST /api/v1/admin/vehicles/{vehicle_id}/restore`

Archive mềm bằng:

```text
vehicles.status = ARCHIVED
```

Không xóa cascade dữ liệu giá, feature hoặc RAG nếu cần giữ lịch sử và citation.

## 6.6. Khai báo nhu cầu cho feature

```text
Admin mở feature trong danh mục
  -> chọn một hoặc nhiều need_tag từ tập đóng (mục 7.4)
  -> đặt relevance cho từng cặp
  -> INSERT/UPDATE feature_need_tags
  -> commit
```

Luồng này **không** gắn với xe. Khai báo một lần cho `feature_code`, mọi xe có feature đó đều thừa hưởng, kể cả xe thêm vào sau.

`need_tag` không nằm trong tập đóng ở mục 7.4 thì bị từ chối. Lý do: tag tự do sinh ra hai mã cho cùng một nhu cầu (`LONG_TRIP` với `LONG_DISTANCE`), và runtime tra theo tag chính xác nên một nửa dữ liệu sẽ không bao giờ khớp. Cần nhu cầu mới thì bổ sung vào tập đóng trước, kèm ánh xạ từ slot ở mục 7.4.

---

# 7. Mapping với hai lớp truy vấn

## 7.0. Ánh xạ slot nhu cầu sang cột schema

PRD yêu cầu Agent khai thác một bộ slot rồi mới tra cứu. Bảng dưới chốt mỗi slot đi vào đâu, để không có slot nào bị thu thập rồi bỏ rơi, và không slot nào bị Agent tự suy diễn.

| Slot PRD | Áp dụng | Đi vào | Cách dùng |
|---|---|---|---|
| Loại phương tiện | cả hai | `vehicles.vehicle_type` | Hard filter, quyết định join `cars` hay `motorbikes` |
| Số người sử dụng | ô tô | `cars.seat_count` | Hard filter `seat_count >= :passenger_count` |
| Quãng đường/ngày | cả hai | `cars.range_km` / `motorbikes.range_max_km`; và input TCO | Hard filter tầm hoạt động + tính chi phí sạc |
| Khả năng sạc tại nhà | cả hai | `cars.home_charge_time_minutes`; `motorbikes.battery_removable`, `charging_method` | Scoring, không hard filter |
| Ngân sách | cả hai | `vehicle_prices.amount_vnd` | Hard filter `<= budget_max_vnd` |
| Mục đích sử dụng | xem mục dưới | không có cột trực tiếp | Suy ra tiêu chí, xem quy tắc dưới |
| Ưu tiên bổ sung | cả hai | `vehicle_feature_flags` qua `feature_definitions` | Lớp 2 nhánh 2a → 2c: lọc/xếp hạng |
| Thói quen sử dụng | cả hai | `feature_need_tags` qua tập `need_tag` đóng | Lớp 2 nhánh 2b → 2d: **chỉ xếp hạng**, không hard filter |

### Slot `habit_need_tags`

Slot "ưu tiên bổ sung" trước đây chỉ chứa được **tính năng có tên gọi**. Khách trả lời bằng thói quen ("tôi hay đi trong phố", "cuối tuần hay chạy đường dài") thì không khớp `feature_code` nào và bị bỏ rơi.

Slot `habit_need_tags` nhận phần đó. Giá trị của nó là **danh sách `need_tag` thuộc tập đóng**, do nhánh 2b suy ra từ câu khách, rồi **ghi vào `conversation_slots`** như mọi slot khác. Ba hệ quả:

- Bền qua các lượt, sửa được, hiện ra trong hàng đợi HITL để tư vấn viên thấy Agent đã hiểu nhu cầu thành cái gì.
- Quy tắc "suy `need_tag` từ slot đã xác nhận, không từ câu chữ" (mục 7.4) giữ nguyên nghĩa đen — vì lúc scoring đọc, nó đã là slot.
- Thêm một slot là thêm **dòng** trong `conversation_slots`, không phải thêm cột.

Tag ngoài tập đóng bị từ chối. Nhánh 2b không khớp được tag nào → slot để trống, câu trả lời rơi về nhánh 2e (diễn giải có trích dẫn) và **không** đổi thứ hạng.

### Quy tắc slot mục đích sử dụng

Schema không có cột "mục đích sử dụng" và không nên có, vì đây là thông tin về người dùng chứ không phải thuộc tính của xe. Slot này được ánh xạ thành tiêu chí đã tồn tại:

Ô tô — `gia_dinh` ưu tiên `seat_count` cao và `cargo_volume_standard_l`; `ca_nhan` không thêm ràng buộc, chỉ dùng để xếp hạng; `kinh_doanh` ưu tiên `range_km` cao và chi phí vận hành thấp theo `energy_consumption_kwh_per_100km`.

Xe máy điện — `di_lam` ưu tiên `range_max_km` đủ cho quãng đường đã khai báo; `giao_hang` thêm ràng buộc `max_load_kg` và ưu tiên `battery_swappable`/`battery_removable`; `ca_nhan` chỉ dùng để xếp hạng.

Các ánh xạ này là **preference dùng để xếp hạng**, không phải hard filter, trừ `max_load_kg` cho nhánh giao hàng. Lý do: mục đích sử dụng là suy luận về nhu cầu, nếu biến thành điều kiện cứng thì dễ loại oan xe phù hợp. Ánh xạ phải nằm ở một bảng tra cứu tường minh trong code, không để LLM tự quyết.

## 7.1. Lớp 1: SQL Hard Filter

### Ô tô

```sql
SELECT v.vehicle_id
FROM vehicles AS v
JOIN cars AS c ON c.vehicle_id = v.vehicle_id
JOIN vehicle_prices AS p ON p.vehicle_id = v.vehicle_id
WHERE v.vehicle_type = 'CAR'
  AND v.status = 'ACTIVE'
  AND c.seat_count >= :passenger_count
  AND c.range_km >= :required_range_km
  AND p.price_type = 'STARTING_PRICE'
  AND p.amount_vnd <= :budget_max_vnd
  AND p.status = 'ACTIVE'
  AND p.valid_from <= :now
  AND (p.valid_to IS NULL OR p.valid_to > :now);
```

### Xe máy điện

```sql
SELECT v.vehicle_id
FROM vehicles AS v
JOIN motorbikes AS m ON m.vehicle_id = v.vehicle_id
JOIN vehicle_prices AS p ON p.vehicle_id = v.vehicle_id
WHERE v.vehicle_type = 'ELECTRIC_MOTORBIKE'
  AND v.status = 'ACTIVE'
  AND m.range_max_km >= :required_range_km
  AND m.max_load_kg >= :required_load_kg
  AND p.price_type = 'STARTING_PRICE'
  AND p.amount_vnd <= :budget_max_vnd
  AND p.status = 'ACTIVE'
  AND p.valid_from <= :now
  AND (p.valid_to IS NULL OR p.valid_to > :now);
```

Output của Lớp 1 là `candidate_vehicle_ids`.

## 7.2. Lớp 2: Need & Feature Retriever

Một cửa duy nhất nhận `candidate_vehicle_ids` từ Lớp 1 cộng câu khách vừa nói, trả về `list[FeatureAssertion]`.

### Contract đầu ra

Mọi thứ phía sau Lớp 2 — chấm điểm, so sánh, synthesis, guardrail, HITL — **chỉ** tiêu thụ kiểu này, không biết bằng chứng đến từ đâu:

```text
FeatureAssertion
    vehicle_id     : UUID
    feature_code   : str | None          None = mới chỉ có bằng chứng văn bản
    status         : YES | NO | UNKNOWN
    source         : FLAG | DOCUMENT
    confidence     : Decimal
    evidence_ref   : (vehicle_id, feature_code)      khi source = FLAG
                     (document_id, chunk_index)      khi source = DOCUMENT
```

### Luật thẩm quyền (nguyên tắc 6, mục 2)

| | `source = FLAG` | `source = DOCUMENT` |
|---|---|---|
| Phát `YES` | được | được, kèm trích dẫn |
| Phát `NO` | được | **chỉ khi có bằng chứng dương** (xem dưới) |
| Loại xe khỏi candidate | được | không |
| Đổi thứ hạng | được | không (ở MVP) |
| Cung cấp con số | được | không bao giờ |

Lý do `DOCUMENT` không được loại xe: `NO` là trạng thái duy nhất **xoá xe khỏi tầm mắt tư vấn viên**. Một `YES` sai bị HITL bắt lại trước khi tới khách; một `NO` sai thì xe không vào candidate, không lên hàng đợi duyệt, không ai thấy để mà sửa. Thiệt hại bất đối xứng nên thẩm quyền cũng bất đối xứng.

### 2a — Khớp tính năng

Câu khách được so khớp ngữ nghĩa với `feature_definitions` (`name` + `description`) của đúng `vehicle_type`, lấy `feature_code` vượt ngưỡng. Nhờ đó "cửa sổ trời", "kính toàn cảnh", "nóc kính" đều ra `PANORAMIC_ROOF`.

Vector nạp vào bộ nhớ lúc khởi động từ `SELECT feature_code, name, description FROM feature_definitions WHERE status='ACTIVE'`. **Không** thêm cột `embedding` vào bảng ở MVP — danh mục cỡ vài chục dòng, embed lúc startup rẻ hơn nhiều so với chi phí một migration và một pipeline đồng bộ.

### 2b — Khớp nhu cầu

Tương tự 2a nhưng đích đến là tập `need_tag` **đóng** (mục 4.12), so khớp trên mô tả tiếng Việt của từng tag. "Hay đi trong phố" → `URBAN_TRAFFIC`. Kết quả ghi vào slot `habit_need_tags` (mục 7.0).

### 2c — Tra flags

```sql
SELECT vehicle_id, feature_code, status, verification_status, confidence
FROM vehicle_feature_flags
WHERE vehicle_id = ANY(:candidate_vehicle_ids)
  AND feature_code = ANY(:feature_codes)
  AND verification_status = 'APPROVED';
```

Quy tắc tri-state giữ nguyên:

- `YES` → `FeatureAssertion(FLAG, YES)`.
- `NO` → loại xe khi feature là điều kiện bắt buộc (khách nêu đích danh, hoặc `filter_behavior='REQUIRED'`).
- `UNKNOWN` → **không** suy thành `NO`; xe giữ lại kèm cờ cần xác minh, và mở đường cho 2e.

Xe còn sống sau bước loại này là `alive_vehicle_ids` — phạm vi của 2e.

### 2d — Nở nhu cầu thành tính năng

```sql
SELECT fnt.feature_code, fnt.relevance
FROM feature_need_tags AS fnt
JOIN feature_definitions AS fd ON fd.feature_code = fnt.feature_code
WHERE fnt.need_tag = ANY(:need_tags)
  AND fd.status = 'ACTIVE'
  AND (fd.vehicle_type IS NULL OR fd.vehicle_type = :vehicle_type);
```

`feature_code` thu được đi tiếp qua 2c. `relevance` trở thành trọng số khi chấm điểm.

Đây là chỗ nhu cầu mềm được phục vụ mà **thứ hạng vẫn do dữ liệu ai đó đã khẳng định về xe quyết định**, không do câu văn quảng cáo trong brochure. Lý do đưa ra cho khách vẫn diễn đạt tự nhiên: *"xe này có camera 360 và tự động đỗ — đỡ vất vả khi đi trong phố đông."*

### 2e — Đọc tài liệu (có điều kiện)

```sql
SELECT document_id, chunk_index, vehicle_id, title, content,
       section_title, page_number
FROM vehicle_documents
WHERE vehicle_id = ANY(:alive_vehicle_ids)
  AND status = 'ACTIVE'
  AND (valid_from IS NULL OR valid_from <= :now)
  AND (valid_to IS NULL OR valid_to > :now)
ORDER BY embedding <=> :query_embedding
LIMIT :top_k;
```

Hợp nhất với nhánh full-text trên `content_tsv` bằng RRF (k=60).

**Điều kiện nổ** — đúng ba trường hợp:

1. 2a và 2b đều không khớp được mã nào (khách nói thứ chưa có trong danh mục).
2. 2c trả `UNKNOWN` cho đúng điều kiện khách đang nêu.
3. Khách hỏi một câu diễn giải ("bảo hành pin có điều kiện gì").

Nếu flag đã trả `YES`/`NO` đã duyệt thì **không** mở tài liệu — đọc lại để xác nhận điều đã biết chắc là lãng phí, và nó ăn vào ngân sách độ trễ.

Đây là khác biệt cốt lõi so với thiết kế ba lớp cũ: điều kiện đặt theo **"flags có kết luận được hay không"**, không phải **"feature có mã hay không"**. Có mã không còn cấm đọc tài liệu; `UNKNOWN` là lời mời đi đọc.

Giới hạn: tối đa **một** lần tìm kiếm vector mỗi lượt hội thoại.

### Khi nào 2e được phát `NO`

Chỉ khi có **bằng chứng dương**, không bao giờ từ sự im lặng:

| Retriever thấy gì | Kết quả |
|---|---|
| Chunk khẳng định có ("trang bị cửa sổ trời toàn cảnh") | `YES(DOCUMENT)` |
| Chunk khẳng định không có ("không trang bị", "chỉ có ở bản Plus", "tuỳ chọn") | `NO(DOCUMENT)` |
| Bảng trang bị có dòng cho feature đó, ô của xe này trống / gạch ngang | `NO(DOCUMENT)` |
| Không có chunk nào liên quan | `UNKNOWN` — **không** phải `NO` |

"Không tìm thấy" có bốn nguyên nhân và chỉ một biện minh cho `NO`: xe thật sự không có; brochure diễn đạt khác; chunking cắt ngang câu; brochure đơn giản không liệt kê (nó là tài liệu marketing, không phải bảng thông số đầy đủ). Từ một kết quả rỗng không phân biệt được bốn cái này.

Hệ quả cho khâu chuẩn bị dữ liệu: nếu brochure có **bảng trang bị theo phiên bản**, phải giữ nguyên cấu trúc bảng khi chunk. Đó là nguồn `NO` chất lượng cao nhất, và cũng là thứ dễ mất nhất trong tiền xử lý.

### Ghi ngược — vòng học

Mỗi khi 2e sinh ra kết luận về một feature **đã có mã**, ghi lại một đề xuất chờ duyệt:

```sql
INSERT INTO vehicle_feature_flags (vehicle_id, feature_code, status,
                                   verification_status, confidence, ...)
VALUES (:vehicle_id, :feature_code, :status, 'PENDING', :retrieval_score, ...)
ON CONFLICT (vehicle_id, feature_code) DO UPDATE
   SET status = EXCLUDED.status,
       confidence = EXCLUDED.confidence
 WHERE vehicle_feature_flags.verification_status = 'PENDING';
```

Mệnh đề `WHERE` cuối là hàng rào bắt buộc: **không bao giờ ghi đè một dòng đã `APPROVED` hoặc `REJECTED`**. Quyết định của Admin luôn thắng máy.

Dòng `PENDING` không tham gia truy vấn tư vấn khách hàng (mục 4.9) cho tới khi Admin duyệt. Đúng ngữ nghĩa mà mục 4.9 đã dành sẵn cho `PENDING`: *"flag do pipeline tự động trích xuất từ brochure (có `confidence`)"* — retriever chính là pipeline đó.

Trường hợp im lặng (không chunk nào liên quan) vẫn được ghi đề xuất `NO` với `confidence` thấp (0.3–0.5), kèm điều kiện brochure của xe đó **có** mục thông số/trang bị rõ ràng. Tín hiệu yếu nhưng có thật, và nó đi qua cửa Admin chứ không tự ý lọc.

Ảnh hưởng tới lượt hiện tại — `DOCUMENT` **không** đổi điểm, chỉ:

- gỡ nhãn "cần xác minh" khi nâng được `UNKNOWN` lên `YES`;
- cấp trích dẫn cho câu trả lời.

Tần suất 2e giảm dần theo thời gian: catalog vừa seed thì gần như mọi lượt đều nổ (mọi flag đều `UNKNOWN`); sau vài tuần Admin duyệt các đề xuất thì chỉ còn câu hỏi diễn giải. Chi phí đắt nhất tự giảm mà không ai phải tối ưu.

### Ràng buộc không đổi

RAG chỉ giải thích trong scope đã được SQL xác định. Không dùng RAG để mở rộng lại candidate set hoặc đưa về xe vượt ngân sách.

## 7.4. Sau xếp hạng: giới thiệu feature theo nhu cầu

Mục này chốt cách Agent nói về feature khách **chưa hỏi**. Nó chạy sau khi đã có danh sách xe xếp hạng, không tham gia lọc.

### Phân biệt hai loại câu, phải giữ tách nhau

| | Lý do đề xuất | Feature giới thiệu thêm |
|---|---|---|
| Trả lời câu hỏi | Vì sao xe này khớp điều khách **đã nói** | Điều khách **chưa hỏi** nhưng quan trọng với nhu cầu đã nêu |
| Hướng | Nhìn lại slot đã thu thập | Nhìn tới nhu cầu suy ra từ slot |
| Nguồn | Slot đã xác nhận | `feature_need_tags` |

Feature mà khách **đã tự nêu** thuộc nhóm bên trái, không thuộc nhóm bên phải. Nói lại một feature khách vừa yêu cầu như thể mình đang giới thiệu là chào hàng, dù nội dung đúng.

### Tập `need_tag` đóng và ánh xạ từ slot

Tag **suy ra từ slot đã xác nhận**, không suy từ câu chữ khách nói. Vì cây slot đã đóng (nhánh ô tô 6 slot, nhánh xe máy điện 5 slot), tập tag cũng đóng:

| `need_tag` | Suy ra từ | Điều kiện |
|---|---|---|
| `LONG_DISTANCE` | quãng đường/ngày | `>= 150` km |
| `URBAN_TRAFFIC` | quãng đường/ngày | `< 50` km |
| `HIGHWAY_SAFETY` | mục đích + quãng đường | `kinh_doanh` hoặc `LONG_DISTANCE` |
| `FAMILY_LARGE` | số người | `>= 6` |
| `NO_HOME_CHARGING` | khả năng sạc tại nhà | không sạc được tại nhà |
| `DELIVERY_USE` | mục đích cụ thể | `giao_hang` |
| `LOW_OPERATING_COST` | mục đích | `kinh_doanh` |
| `TIGHT_BUDGET` | ngân sách | nằm ở nhóm thấp nhất của dải giá đang bán |

Slot `ca_nhan` ở cả hai nhánh **không sinh tag nào** — theo mục 7.0 nó chỉ dùng để xếp hạng. Slot "ưu tiên bổ sung" cũng không sinh tag, vì feature khách tự nêu thuộc nhóm lý do đề xuất.

Ngưỡng trong bảng phải nằm ở một bảng tra cứu tường minh trong code, cùng chỗ với ánh xạ slot ở mục 7.0. Không để LLM tự quyết khách có phải `LONG_DISTANCE` hay không.

### Query

```sql
SELECT fnt.feature_code, fnt.need_tag, fnt.relevance,
       fd.name, fd.category, vff.status, vff.value_boolean,
       vff.value_number, vff.value_text
FROM feature_need_tags AS fnt
JOIN feature_definitions AS fd ON fd.feature_code = fnt.feature_code
JOIN vehicle_feature_flags AS vff ON vff.feature_code = fnt.feature_code
WHERE fnt.need_tag = ANY(:confirmed_need_tags)
  AND vff.vehicle_id = :ranked_vehicle_id
  AND vff.status = 'YES'
  AND vff.verification_status = 'APPROVED'
  AND fd.status = 'ACTIVE'
  AND fnt.feature_code <> ALL(:features_customer_already_asked)
ORDER BY fnt.relevance DESC, fd.display_order
LIMIT :max_introductions;
```

### Sáu quy tắc bắt buộc

1. Chỉ `status = 'YES'` được giới thiệu. `UNKNOWN` là chưa xác minh, nói ra là khẳng định điều mình không biết; `NO` thì hiển nhiên.
2. Chỉ `verification_status = 'APPROVED'`, cùng lý do mục 4.9.
3. Feature khách đã tự nêu bị loại khỏi query — nó thuộc lý do đề xuất.
4. Feature mà **mọi** xe trong danh sách đều có thì không giúp khách chọn được gì. Dùng differentiator query để loại; nói về nó là mô tả dòng sản phẩm, không phải tư vấn.
5. Giới hạn số câu giới thiệu mỗi lượt. Nói năm feature một lúc là chào hàng bất kể mỗi câu đều đúng.
6. Không có feature nào đủ điều kiện thì **trả về rỗng**. Không được rơi về lời khen chung chung — chào hàng không có trạng thái im lặng, nên nếu cho phép fallback thì mọi quy tắc trên đều vô nghĩa.

Quy tắc 6 là quy tắc chịu lực. Năm quy tắc đầu quyết định *cái gì được nói*; quy tắc 6 quyết định *chuyện gì xảy ra khi không có gì để nói*, và đó chính là chỗ hệ thống trượt về chào hàng.

## 7.5. Allowlist con số được phép nói ra

Mọi con số trong câu trả lời phải đi qua bảng ánh xạ này. Bảng nằm trong code (dict hằng), không nằm trong database, vì nó là ánh xạ **mã → cột schema** nên đổi cùng nhịp với schema chứ không phải với dữ liệu.

| `fact_code` | Nguồn | Đơn vị |
|---|---|---|
| `CAR_RANGE_KM` | `cars.range_km` | km |
| `CAR_SEAT_COUNT` | `cars.seat_count` | chỗ |
| `CARGO_VOLUME_STANDARD_L` | `cars.cargo_volume_standard_l` | lít |
| `FAST_CHARGE_TIME_MINUTES` | `cars.fast_charge_time_minutes` | phút |
| `HOME_CHARGE_TIME_MINUTES` | `cars.home_charge_time_minutes` | phút |
| `MOTORBIKE_RANGE_MAX_KM` | `motorbikes.range_max_km` | km |
| `MOTORBIKE_MAX_LOAD_KG` | `motorbikes.max_load_kg` | kg |
| `STARTING_PRICE_VND` | `vehicle_prices.amount_vnd` | VND |
| `TCO_TOTAL_VND` | kết quả `vinfast_tco_v1` | VND |
| `BATTERY_RENT_VND_PER_MONTH` | `battery_policies` | VND/tháng |

### Cách render

LLM **không viết số**. LLM sinh câu có placeholder, code thay bằng giá trị từ snapshot:

```text
LLM sinh:  "Xe này đi được {CAR_RANGE_KM} một lần sạc, đủ cho quãng đường
            {DAILY_DISTANCE_KM} mỗi ngày mà không cần sạc giữa ngày."
Code thay: "Xe này đi được 399 km một lần sạc, đủ cho quãng đường
            180 km mỗi ngày mà không cần sạc giữa ngày."
```

Placeholder không có trong allowlist → reject trước khi render, không cần hỏi lại LLM.

### Vì sao placeholder mạnh hơn kiểm tra sau khi sinh

Guardrail hậu-synthesis (đối chiếu số trong câu trả lời với snapshot, sai thì retry) **phát hiện** số bịa sau khi nó đã được sinh ra. Placeholder làm số bịa **không thể xuất hiện**, vì LLM không có cơ hội viết chữ số nào.

Khác biệt thực tế là chi phí: với guardrail đơn thuần, mỗi lần LLM viết lệch một con số là thêm một lượt gọi lại, và retry nằm trên đường đi bình thường. Với placeholder, retry trở thành đường ngoại lệ — chỉ xảy ra khi LLM dùng placeholder sai tên, tức lỗi cú pháp dễ sửa hơn lỗi nội dung. Guardrail vẫn giữ nguyên làm lưới an toàn cuối, không bỏ.

---

# 8. Quyết định đơn giản hóa

## Giữ trong MVP

```text
vehicles
cars
motorbikes
vehicle_prices
promotions
promotion_vehicles
battery_policies
feature_definitions
vehicle_feature_flags
vehicle_documents
tco_assumptions
feature_need_tags
```

`feature_definitions` nằm trong MVP vì `vehicle_feature_flags.feature_code` tham chiếu tới nó bằng FK (mục 4.9); không thể bỏ mà vẫn dựng được Lớp 2. Danh sách feature ban đầu được seed sẵn, Admin thêm feature mới qua API mà không sửa schema.

`tco_assumptions` nằm trong MVP vì PRD yêu cầu TCO gồm phí lăn bánh và bảo dưỡng, và các con số này khác nhau giữa ô tô với xe máy điện nên không thể hardcode.

`feature_need_tags` nằm trong MVP vì PRD 5.3 đòi Agent tư vấn theo nhu cầu. Không có bảng này, việc chọn feature nào đáng nói với khách nào chỉ còn hai đường: hardcode trong code hoặc để LLM tự quyết. Cả hai đều làm mất tính truy vết mà PRD yêu cầu, và đường thứ hai là chào hàng. Giá của bảng là hai cột và khoảng 25–30 dòng seed.

## Chưa cần trong schema catalog MVP

```text
vehicle_change_logs
catalog_versions
catalog_import_jobs
vehicle_images
vehicle_selling_points
```

Các bảng này chỉ cần khi:

- Cần audit field-level đầy đủ.
- Cần publish hàng loạt theo catalog version.
- Cần import CSV theo batch.
- Một xe có nhiều ảnh quản lý độc lập.
- Cần Admin soạn câu chữ marketing riêng cho từng biến thể xe.

Riêng `vehicle_selling_points` (kèm bảng nguồn dẫn chứng và bảng nối tag của nó) là bước nâng cấp tự nhiên của `feature_need_tags`: khi cần câu văn tinh chỉnh theo giọng thương hiệu cho từng biến thể, thay vì template chung render từ giá trị flag. Để sau MVP vì khối lượng nhập liệu của nó là **số xe nhân số feature** chứ không phải số feature, nên nếu chưa có người phụ trách soạn và duyệt nội dung thì bảng sẽ rỗng và Agent không giới thiệu được gì. `feature_need_tags` chạy được với 25–30 dòng, và các `need_tag` đã khai báo dùng lại được nguyên vẹn khi nâng cấp.

## Phân chia structured và RAG

| Loại dữ liệu | Nơi lưu | Được quyền làm gì | Lý do |
|---|---|---|---|
| Giá hiện tại | `vehicle_prices` | lọc, xếp hạng, cấp số | Cần `<= budget` chính xác. |
| Giá thuê pin dùng TCO | `battery_policies` | lọc, xếp hạng, cấp số | Cần tính số học. |
| Số ghế, range, tải trọng | `cars`/`motorbikes` | lọc, xếp hạng, cấp số | Cần hard filter. |
| Feature có/không/chưa biết | `vehicle_feature_flags` | lọc, xếp hạng | Cần quyết định có loại xe hay không. |
| Nhu cầu ↔ feature | `feature_need_tags` | xếp hạng | Nhu cầu mềm không phải thuộc tính của xe, không được thành điều kiện cứng. |
| Điều khoản bảo hành | `vehicle_documents` | **chỉ diễn giải** | Nội dung dài, cần semantic search. |
| Ngoại lệ chính sách | `vehicle_documents` | **chỉ diễn giải** | Khó biểu diễn hết bằng column. |
| Mô tả tự nhiên | `vehicle_documents` | **chỉ diễn giải** | Phù hợp RAG và citation. |

Cột "được quyền làm gì" là luật thẩm quyền ở mục 7.2 nhìn từ phía dữ liệu. Ngoại lệ duy nhất của dòng `vehicle_documents`: nhánh 2e được phát `NO` khi có bằng chứng dương, và kết luận đó đi vào `vehicle_feature_flags` ở trạng thái `PENDING` chờ Admin duyệt — tức nó chuyển sang cột structured trước khi có quyền lọc, chứ không tự lọc.

## Kết luận

Kiến trúc phù hợp nhất cho MVP là giữ `cars` và `motorbikes`, thêm `vehicles` làm registry chung, sau đó thêm các bảng phụ cho dữ liệu cần query. Chính sách dài và điều khoản diễn giải có thể dùng RAG, nhưng mọi con số được dùng để lọc hoặc tính TCO phải được lưu structured trong database.
